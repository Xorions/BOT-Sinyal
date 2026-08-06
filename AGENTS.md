# AGENTS.md

Panduan untuk AI agent dan developer yang bekerja di project **BOT-Sinyal-Trading**.

## 1. Overview Arsitektur & Tech Stack

### Arsitektur
Bot sinyal trading Telegram yang dijalankan **sekali setiap jam** melalui GitHub Actions (cron). Alur per eksekusi: ambil data pasar & on-chain → hitung skor sinyal per koin → kirim ringkasan ke Telegram.

```
bot.py                        # Entry point: scan + kirim ke Telegram
config.py                     # Memuat konfigurasi & kredensial dari .env
telegram_sender.py            # Kirim pesan ke Telegram (HTTP Bot API)
data/market.py                # Binance (utama) + CoinGecko (fallback): OHLC, daftar top koin
data/onchain.py               # DefiLlama: perubahan TVL harian per chain
signals/indicators.py         # RSI (Wilder), SMA, rasio volume spike
signals/engine.py             # Skoring → BUY/SELL/NEUTRAL + confidence; format pesan
.github/workflows/hourly.yml  # Scheduler tiap jam penuh (cron 0 * * * *)
.env                          # Kredensial (TIDAK di-commit)
```

### Tech Stack
- **Python 3.12** (virtual environment di `venv/`)
- **requests** untuk semua HTTP (Binance, CoinGecko, DefiLlama, Telegram)
- **python-dotenv** untuk memuat `.env`
- **GitHub Actions** (cron `0 * * * *`) sebagai scheduler gratis — tidak butuh server 24/7
- **Sumber data publik gratis**: Binance Public API, CoinGecko API, DefiLlama API, Telegram Bot API

## 2. Aturan Skoring Sinyal

Skor positif = bullish (**BUY**), negatif = bearish (**SELL**). Skor dihitung di `signals/engine.py`; ambang konfigurasi ada di `config.py` (`BUY_THRESHOLD = 3.0`, `SELL_THRESHOLD = -3.0`).

| Komponen | Kondisi | Poin |
|---|---|---|
| Tren — harga vs SMA 12 jam | harga > SMA | **+1.5** |
| Tren — harga vs SMA 12 jam | harga < SMA | **-1.5** |
| Perubahan harga 24 jam | >= +2% | **+1.0** |
| Perubahan harga 24 jam | <= -2% | **-1.0** |
| RSI | < 30 (oversold) | **+2.0** |
| RSI | 30–40 (mendekati oversold) | **+1.0** |
| RSI | > 70 (overbought) | **-2.0** |
| RSI | 60–70 (mendekati overbought) | **-1.0** |
| Volume spike >= 1.4x | harga jam terakhir naik | **+1.5** |
| Volume spike >= 1.4x | harga jam terakhir turun | **-1.5** |
| TVL chain (on-chain) | >= +2% | **+1.0** |
| TVL chain (on-chain) | <= -2% | **-1.0** |

- **BUY** jika skor >= 3.0, **SELL** jika skor <= -3.0, selain itu **NEUTRAL**.
- Confidence: `max(40, min(95, 55 + round(|skor| * 7)))`.
- Detail indikator di `signals/indicators.py`: RSI dengan smoothing Wilder (14 periode), SMA (12 bar terakhir), rasio volume spike (volume jam terakhir vs rata-rata 12 jam sebelumnya).

### Alur per koin
1. Ambil daftar top-N koin dari CoinGecko (stablecoin disaring).
2. Ambil harga + volume 48 bar per jam — Binance dulu, fallback CoinGecko bila gagal.
3. Ambil perubahan TVL harian chain terkait dari DefiLlama (opsional; dapat bernilai `None`).
4. Hitung skor & sinyal, lalu kumpulkan alasan untuk ditampilkan di pesan.

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
