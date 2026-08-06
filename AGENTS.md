# AGENTS.md

Panduan untuk AI agent dan developer yang bekerja di project **BOT-Sinyal-Trading**.

## 1. Overview Arsitektur & Tech Stack

### Arsitektur
Bot sinyal trading Telegram yang dijalankan **sekali setiap hari (07:00 WIB)** melalui GitHub Actions (cron). Alur per eksekusi: scan top koin dalam satu panggilan CoinGecko → hitung skor sinyal → pilih TOP-5 sinyal terbaik → kirim Daily Briefing ke Telegram.

```
bot.py                        # Entry point: scan + kirim Daily Briefing
config.py                     # Memuat konfigurasi & kredensial dari .env
telegram_sender.py            # Kirim pesan ke Telegram (HTTP Bot API)
data/market.py                # CoinGecko: top koin + sparkline 7d (1 panggilan API)
signals/indicators.py         # RSI (Wilder), SMA
signals/engine.py             # Skoring → BUY/SELL/NEUTRAL, pilih TOP-5, format pesan
.github/workflows/daily.yml   # Scheduler harian (cron 0 0 * * * = 07:00 WIB)
.env                          # Kredensial (TIDAK di-commit)
```

### Tech Stack
- **Python 3.12** (virtual environment di `venv/`)
- **requests** untuk semua HTTP (CoinGecko, Telegram)
- **python-dotenv** untuk memuat `.env`
- **GitHub Actions** (cron `0 0 * * *`) sebagai scheduler gratis — tidak butuh server 24/7
- **Sumber data publik gratis**: CoinGecko API, Telegram Bot API

## 2. Aturan Skoring Sinyal

Semua indikator dihitung dari **satu panggilan** `GET /coins/markets` (CoinGecko) yang berisi harga terkini, perubahan harga 1j/24j/7d, dan sparkline harga 7 hari. Skor positif = bullish (**BUY/LONG**), negatif = bearish (**SELL/SHORT**). Skor dihitung di `signals/engine.py`; ambang konfigurasi ada di `config.py` (`BUY_THRESHOLD = 3.0`, `SELL_THRESHOLD = -3.0`).

| Komponen | Kondisi | Poin |
|---|---|---|
| RSI | < 30 (oversold) | **+2.0** |
| RSI | 30–40 (mendekati oversold) | **+1.0** |
| RSI | > 70 (overbought) | **-2.0** |
| RSI | 60–70 (mendekati overbought) | **-1.0** |
| Tren — harga vs SMA 24 jam | harga > SMA | **+1.5** |
| Tren — harga vs SMA 24 jam | harga < SMA | **-1.5** |
| Momentum 1 jam | >= +1.5% / <= -1.5% | **+1.0 / -1.0** |
| Momentum 24 jam | >= +3% / <= -3% | **+1.5 / -1.5** |
| Momentum 7 hari | >= +8% / <= -8% | **+1.0 / -1.0** |
| Volume aktif (turnover top 10%) | harga 24j naik / turun | **+1.5 / -1.5** |
| Volume aktif (turnover top 25%) | harga 24j naik / turun | **+1.0 / -1.0** |

- **BUY** jika skor >= 3.0, **SELL** jika skor <= -3.0, selain itu **NEUTRAL**.
- Confidence: `max(45, min(95, 55 + round(|skor| * 5)))`.
- **Pemilihan sinyal**: semua koin diskor, lalu diurutkan berdasarkan kekuatan (`|skor|`) dan diambil **TOP `TOP_SIGNALS`** (default 5).
- Detail indikator di `signals/indicators.py`: RSI smoothing Wilder (14 periode), SMA (24 bar). "Volume aktif" = rasio `total_volume / market_cap` dibandingkan terhadap seluruh koin yang dipindai (percentile).

### Alur Daily Briefing
1. Satu panggilan `GET /coins/markets` (`per_page=250`, `sparkline=true`, `price_change_percentage=1h,24h,7d`) → daftar top koin + data indikator.
2. Filter stablecoin (USDT, USDC, DAI, FDUSD, dll) — lihat `STABLECOINS` di `data/market.py`.
3. Hitung skor tiap koin (`build_signal`) dan pilih TOP-5 paling solid (`rank_signals`).
4. Kirim Daily Briefing ke Telegram lewat `format_message`.

## 3. Panduan Pengembangan

### Menambah indikator baru
1. Tambahkan fungsi di `signals/indicators.py` — murni, tanpa I/O, menerima list angka → mengembalikan angka atau `None`.
2. Di `signals/engine.py`, buat fungsi `_score_<nama>` (menerima data + list `reasons`), panggil di `build_signal`, lalu jumlahkan ke `score`.
3. Ikuti konvensi: poin positif untuk bullish, negatif untuk bearish, dan tiap threshold seragam (mis. ±1.0 hingga ±2.0).
4. Jika indikator butuh data baru (mis. funding rate), tambahkan fetcher di `data/` lalu teruskan datanya ke `build_signal`.

### Mengubah cara pengiriman pesan
- Format pesan di `signals/engine.py` → `format_message()`. Saat ini memakai **HTML parse mode** (default di `telegram_sender.py`).
- Ganti format ke Markdown, kirim foto/chart, atau tambahkan inline buttons dengan mengubah payload di `telegram_sender.py::send_telegram` (Bot API `sendMessage`, `sendPhoto`, dll).
- Tambahkan handler perintah (mis. `/start`, `/help`) bila ingin bot interaktif — gunakan long polling.

### Menjalankan & menguji
```powershell
# Dari root project
venv\Scripts\python.exe bot.py     # scan sekali + kirim ke Telegram
```
Untuk uji indikator tanpa network, jalankan script dengan `PYTHONPATH` menunjuk ke root project agar `config.py` & paket `data/`/`signals/` terbaca.

## 4. Keamanan Kredensial
- `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID` disimpan di `.env` — file ini **sudah masuk `.gitignore` dan tidak boleh di-commit**.
- Jangan pernah hardcode token, chat ID, atau API key di dalam kode.
- `.env.example` adalah template publik dan **harus tetap berisi placeholder/kosong**.
- Di GitHub Actions, kredensial disuntikkan lewat repository secrets (`${{ secrets.TELEGRAM_BOT_TOKEN }}`), bukan lewat file.
- Saat debugging, jangan pernah mencetak isi token/secret ke log atau output.
- (Opsional) `COINGECKO_API_KEY` juga disimpan di `.env`/secret, bukan di kode.
