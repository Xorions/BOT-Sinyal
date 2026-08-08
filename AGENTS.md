# AGENTS.md

Panduan untuk AI agent dan developer yang bekerja di project **BOT-Sinyal-Trading**.

## 1. Overview Arsitektur & Tech Stack

### Arsitektur
Bot sinyal **Day Trading Lanjutan** Telegram yang dijalankan **2x sehari** (07:00 WIB Sesi Pagi & 19:00 WIB Sesi Malam) melalui GitHub Actions (cron). Setiap sesi **diawali evaluasi sinyal dari sesi sebelumnya** (Sesi Malam mengevaluasi Sesi Pagi hari yang sama; Sesi Pagi mengevaluasi Sesi Malam hari sebelumnya).

Alur per eksekusi: quick scan top koin (satu panggilan CoinGecko) → shortlist kandidat momentum → **deep scan Multi-Timeframe (MTF)** per kandidat (chart 30 hari → LTF 1H/15M, HTF 4H/1D) → gabung skor + konfluensi (SMC/OB, S&D/S&R, MACD/RSI, Whale/Volume) → pilih TOP-5 sinyal → evaluasi sesi sebelumnya dari `data/history.json` → kirim pesan ke Telegram → simpan sinyal sesi ini ke history.

```
bot.py                        # Entry point: quick scan → deep MTF scan → evaluasi → kirim
config.py                     # Memuat konfigurasi & kredensial dari .env
telegram_sender.py            # Kirim pesan ke Telegram (HTTP Bot API)
data/market.py                # CoinGecko: top koin + sparkline 7d + market_chart (OHLC MTF)
data/history.py               # Simpan & evaluasi performa sinyal per sesi (HIT TP1/TP2/SL, FLOATING)
data/history.json             # History sinyal yang dikirim (auto di-commit tiap sesi)
signals/indicators.py         # RSI, SMA, EMA, MACD, ATR, swing, BOS/CHoCH, OB, S/R, S&D, RSI div, Whale
signals/engine.py             # Skoring quick + analisis MTF + Confluence Checklist → format pesan
tests/                        # Tes unit (unittest, tanpa network)
.github/workflows/daily.yml   # Scheduler 2x sehari (cron 0 0,12 * * * = 07:00 & 19:00 WIB)
.env                          # Kredensial (TIDAK di-commit)
```

### Tech Stack
- **Python 3.12** (virtual environment di `venv/`)
- **requests** untuk semua HTTP (CoinGecko, Telegram)
- **python-dotenv** untuk memuat `.env`
- **GitHub Actions** (cron `0 0,12 * * *`) sebagai scheduler gratis
- **Sumber data publik gratis**: CoinGecko API, Telegram Bot API

## 2. Day Trading Lanjutan — Analisis Multi-Timeframe (MTF)

### 2a. Logika analisis (signals/engine.py)

Dua tahap skoring:

1. **Quick scan** (semua koin, satu panggilan `markets`): skor dari sparkline 7d (RSI, harga vs SMA 24j, momentum 1j/24j/7d) + turnover volume. Dipakai untuk **shortlist** `MTF_SCAN_LIMIT` kandidat (default 6).
2. **Deep scan MTF** (`analyze_mtf`) per kandidat:
   - **HTF (4H/1D)** → `_htf_bias`: EMA 20/50 (4H), struktur break (window 3), EMA 10/20 (1D). Hasil: BULLISH / BEARISH / NEUTRAL. Menentukan **Trend Bias**.
   - **LTF (1H/15M)** → menentukan **Entry, SL, TP**:
     - `structure_break` → BOS/CHoCH (SMC)
     - `order_block` → bullish/bearish Order Block (SMC)
     - `nearest_levels` → Support/Resistance terdekat (window 3)
     - `demand_supply_zones` → zona Demand/Supply dari candle ber-body kuat
     - `macd` (12/26/9) → `_macd_cross` deteksi bullish/bearish crossover
     - `rsi_divergence` + RSI oversold/overbought (RSI 14)
     - `volume_spike` → deteksi **Whale Spike** (volume 1H vs rata-rata 20 bar, ambang `WHALE_VOLUME_MULT`)
- **SL/TP berbasis ATR** (`_atr_levels`): SL = entry ∓ `ATR_SL_MULT`×ATR(1H), TP1 = entry ± `ATR_TP1_MULT`×ATR, TP2 = entry ± `ATR_TP2_MULT`×ATR. Fallback persentase bila ATR kosong.

### 2b. Confluence Checklist (kualitas sinyal)

Setiap sinyal final memuat checklist 4 kategori (selaras dengan arah BUY/SELL):

| Kategori | Total cek | Isi |
|---|---|---|
| SMC/OB | 2 | BOS/CHoCH selaras + Order Block bertahan |
| S&D/S&R | 2 | Zona Demand/Supply + dekat Support/Resistance |
| MACD/RSI | 2 | Crossover MACD + RSI divergensi/oversold-overbought |
| Whale/Vol | 1 | Whale Spike volume searah |

- Skor akhir = skor quick + (poin bull − poin bear) dari konfluensi MTF.
- **BUY** jika skor ≥ `BUY_THRESHOLD`, **SELL** jika ≤ `SELL_THRESHOLD`.
- Sinyal BUY/SELL **dipromosikan hanya jika ≥ `CONFLUENCE_MIN` kategori selaras**; selain itu diturunkan ke NEUTRAL (watchlist).
- Confidence: dari rasio cek selaras per kategori (50–95).

### 2c. Data MTF (data/market.py)

- `get_market_chart(coin_id, days)` → endpoint `/coins/{id}/market_chart`.
  - `days=30` → granularitas 1 jam → dibangun candle **1H/4H/1D**.
  - `days=2` → granularitas 5 menit → dibangun candle **15M** (opsional; bila gagal, LTF jatuh ke 1H saja).
- `build_candles(raw, interval_minutes)` → bucket `[ts_ms, value]` menjadi list `Candle` OHLCV.
- Free API CoinGecko ~10–30 req/menit; `MTF_SCAN_LIMIT` mengontrol jumlah kandidat deep scan untuk menjaga kuota.

### 2d. Performance Tracking per Sesi (data/history.py)

- Setelah pesan terkirim, `bot.py` memanggil `data.history.append_signals(signals, session)` — satu entri per kunci **(tanggal, sesi)** di `data/history.json` (`{"entries": [{"date": ..., "session": "PAGI"|"MALAM", "signals": [...]}]}`).
- Sebelum mengirim, `bot.py` memanggil `data.history.load_last_entry()` (entri terakhir yang bukan sesi berjalan) lalu `format_evaluation()` → ditampilkan di **bagian paling atas** pesan.
- Evaluasi membandingkan Entry/SL/TP dengan harga terkini / high-low 24j (via `data.market.coin_price_map`; koin yang hilang di-backfill `get_prices_for_ids`).
- Hasil: **HIT TP2** > **HIT TP1** > **HIT SL** > **FLOATING**.
- Agar history terseusur antar sesi di GitHub Actions, workflow meng-commit & push `data/history.json` (butuh `permissions: contents: write`).
- Entri lama tanpa field `session` diperlakukan sebagai `PAGI` (migrasi otomatis via `.get`).

## 3. Aturan Skoring Quick Scan (shortlist)

Skor quick (dari sparkline + turnover, satu panggilan `markets`):

| Komponen | Kondisi | Poin |
|---|---|---|
| RSI | < 30 (oversold) | **+2.0** |
| RSI | 30–40 | **+1.0** |
| RSI | > 70 (overbought) | **-2.0** |
| RSI | 60–70 | **-1.0** |
| Tren — harga vs SMA 24 jam | di atas / di bawah | **+1.5 / -1.5** |
| Momentum 1 jam | ≥ +1.5% / ≤ -1.5% | **+1.0 / -1.0** |
| Momentum 24 jam | ≥ +3% / ≤ -3% | **+1.5 / -1.5** |
| Momentum 7 hari | ≥ +8% / ≤ -8% | **+1.0 / -1.0** |
| Volume aktif (turnover top 10%) | harga naik / turun | **+1.5 / -1.5** |
| Volume aktif (turnover top 25%) | harga naik / turun | **+1.0 / -1.0** |

### Alur Day Trading Signals
1. `GET /coins/markets` (`per_page=250`, `sparkline=true`, `price_change_percentage=1h,24h,7d`) → top koin + filter stablecoin (`STABLECOINS` di `data/market.py`).
2. Quick score semua koin (`build_signal`) → shortlist `MTF_SCAN_LIMIT` terkuat.
3. Per kandidat: `analyze_mtf` (chart 30d + 2d) → konfluensi MTF → `build_final_signal`.
4. Ranking `|skor|` → TOP-`TOP_SIGNALS` (default 5). Jika deep scan gagal total (kuota API), fallback ke hasil quick scan.
5. Kirim pesan via `format_message` (termasuk **Confluence Checklist**), simpan history.

## 4. Panduan Pengembangan

### Menambah indikator / konfirmasi baru
1. Tambahkan fungsi murni (list angka → angka/None) di `signals/indicators.py`.
2. Di `signals/engine.py`, panggil di `analyze_mtf`, tambahkan poin ke `bull_points`/`bear_points` + reason, dan daftarkan cek di `build_checklist` bila termasuk kategori konfluensi.
3. Ambang baru ditaruh di `config.py` (default) + `.env.example`.

### Mengubah cara pengiriman pesan
- Format pesan di `signals/engine.py` → `format_message()`. Saat ini memakai **HTML parse mode**.
- `signal_levels()` mengembalikan (SL, TP1, TP2) dari atribut `Signal` — dipakai evaluasi history.

### Menjalankan & menguji
```powershell
# Dari root project
venv\Scripts\python.exe bot.py                 # scan + evaluasi + kirim ke Telegram
venv\Scripts\python.exe -m unittest discover -s tests -v   # tes unit (tanpa network)
```

## 5. Keamanan Kredensial
- `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID` disimpan di `.env` — sudah masuk `.gitignore`, tidak boleh di-commit.
- Jangan pernah hardcode token/chat ID/API key di kode.
- `.env.example` adalah template publik dan harus tetap berisi placeholder.
- Di GitHub Actions, kredensial disuntikkan lewat secrets; `MTF_SCAN_LIMIT`/`CONFLUENCE_MIN` opsional lewat `vars`.
- Saat debugging, jangan pernah mencetak isi token/secret ke log atau output.
