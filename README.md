# BOT-Sinyal-Trading

Bot Telegram **Day Trading Lanjutan** yang mengirim sinyal trading crypto **2x sehari** (07:00 WIB Sesi Pagi & 19:00 WIB Sesi Malam) berdasarkan analisis **Multi-Timeframe (MTF)** dari data CoinGecko (gratis, tanpa API key berbayar).

## Fitur

- **Analisis Multi-Timeframe**: HTF 4H/1D menentukan **Trend Bias**, LTF 1H/15M menentukan **Entry, SL, TP**.
- **Konfluensi indikator**:
  - Utama: Support/Resistance, Supply/Demand, SMC (BOS/CHoCH), Order Block (bullish/bearish).
  - Pendukung: MACD crossover, RSI divergence, deteksi Volume/Whale Spike.
- **Confluence Checklist** di setiap sinyal: SMC/OB, S&D/S&R, MACD/RSI, Whale/Vol.
- **Evaluasi sinyal sesi sebelumnya** di bagian atas pesan (HIT TP1/TP2/SL, FLOATING) — Sesi Malam mengevaluasi Sesi Pagi, Sesi Pagi mengevaluasi Sesi Malam.
- **SL/TP berbasis ATR** (default SL 1.5× ATR, TP1 2×, TP2 3×).

## Cara Kerja

Setiap sesi (07:00 & 19:00 WIB), GitHub Actions menjalankan `bot.py`:
1. Satu panggilan CoinGecko mengambil **Top 250 koin** (market cap) + sparkline 7 hari — stablecoin disaring.
2. **Quick scan** semua koin → shortlist kandidat momentum terkuat (`MTF_SCAN_LIMIT`, default 6).
3. **Deep scan MTF** per kandidat: chart 30 hari (1H/4H/1D) + 2 hari (15M). Hitung konfluensi SMC/OB, S&D/S&R, MACD/RSI, Whale/Volume.
4. **Evaluasi sesi sebelumnya**: membaca `data/history.json` (per kunci tanggal+sesi), membandingkan Entry/SL/TP dengan harga terkini → hasil HIT TP1/TP2/SL atau FLOATING, ditampilkan paling atas.
5. Pilih **TOP 5 sinyal terbaik** (BUY/LONG & SELL/SHORT paling solid), kirim ke Telegram, simpan sinyal sesi ini ke history (di-commit kembali agar terseusur antar sesi).

## Setup

1. Buat bot di [@BotFather](https://t.me/BotFather) → salin token.
2. Cek chat ID kamu di [@userinfobot](https://t.me/userinfobot).
3. Salin `.env.example` menjadi `.env` dan isi:
   ```
   TELEGRAM_BOT_TOKEN=<token bot>
   TELEGRAM_CHAT_ID=<id chat kamu>
   ```
4. Uji lokal: `venv\Scripts\python.exe bot.py`
5. Push ke GitHub, lalu tambahkan **repository secrets**:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - Opsional: `vars` `MTF_SCAN_LIMIT`, `CONFLUENCE_MIN`.

## Konfigurasi

| Variabel | Default | Keterangan |
|---|---|---|
| `TOP_COINS` | 250 | Jumlah koin dipindai |
| `TOP_SIGNALS` | 5 | Jumlah sinyal dikirim |
| `MTF_SCAN_LIMIT` | 6 | Kandidat deep-scan MTF |
| `CONFLUENCE_MIN` | 2 | Minimal kategori Confluence untuk BUY/SELL |
| `ATR_SL_MULT` | 1.5 | SL = ATR × pengali |
| `ATR_TP1_MULT` | 2.0 | TP1 = ATR × pengali |
| `ATR_TP2_MULT` | 3.0 | TP2 = ATR × pengali |
| `WHALE_VOLUME_MULT` | 2.5 | Ambang deteksi Whale Spike volume |
| `BUY_THRESHOLD` | 3.0 | Skor minimum untuk BUY |
| `SELL_THRESHOLD` | -3.0 | Skor minimum untuk SELL |

## Struktur

```
bot.py                        # Entry point: quick scan → deep MTF scan → evaluasi → kirim
config.py                     # Konfigurasi & kredensial dari .env
telegram_sender.py            # Kirim pesan ke Telegram
data/market.py                # CoinGecko (top coins, sparkline 7d, market_chart OHLC MTF)
data/history.py               # Simpan & evaluasi performa sinyal per sesi
data/history.json             # History sinyal yang dikirim (di-commit tiap sesi)
signals/indicators.py         # RSI, SMA, EMA, MACD, ATR, BOS/CHoCH, OB, S/R, S&D, RSI div, Whale
signals/engine.py             # Skoring MTF + Confluence Checklist → format pesan
tests/                        # Tes unit (unittest, tanpa network)
.github/workflows/daily.yml   # Scheduler 2x sehari (07:00 & 19:00 WIB)
```

## Disclaimer

Sinyal berbasis indikator otomatis & data publik — bukan saran finansial. Selalu lakukan riset sendiri (DYOR).
