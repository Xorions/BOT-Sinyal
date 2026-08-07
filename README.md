# BOT-Sinyal-Trading

Bot Telegram yang mengirim **Daily Briefing sinyal trading crypto** setiap hari jam 07:00 WIB, berdasarkan data pasar CoinGecko (gratis, tanpa API key berbayar).

## Cara Kerja

Setiap hari (07:00 WIB), GitHub Actions menjalankan `bot.py`:
1. Satu panggilan CoinGecko mengambil **Top 250 koin** (market cap) + sparkline harga 7 hari — stablecoin disaring.
2. **Evaluasi sinyal kemarin**: membaca `data/history.json`, membandingkan Entry/SL/TP dengan harga terkini (atau high/low 24j) → hasil **HIT TP1, HIT TP2, HIT SL, atau FLOATING**. Ringkasan ditampilkan paling atas di pesan Telegram.
3. Hitung skor tiap koin dari indikator teknikal: **RSI, tren (SMA 24j), momentum 1j/24j/7d, volume aktif**.
4. Pilih **TOP 5 sinyal terbaik** (BUY/LONG maupun SELL/SHORT paling solid).
5. Kirim Daily Briefing ke Telegram, lalu simpan sinyal hari ini ke `data/history.json` (history di-commit kembali agar terseusur antar hari).

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

## Struktur

```
bot.py                        # Entry point: scan + evaluasi kemarin + kirim Daily Briefing
config.py                     # Konfigurasi & kredensial dari .env
telegram_sender.py            # Kirim pesan ke Telegram
data/market.py                # CoinGecko (top coins + sparkline 7d)
data/history.py               # Simpan & evaluasi performa sinyal kemarin
data/history.json             # History sinyal yang dikirim (di-commit tiap hari)
signals/indicators.py         # RSI, SMA
signals/engine.py             # Skoring BUY/SELL/NEUTRAL, pilih TOP-5
.github/workflows/daily.yml   # Scheduler harian (07:00 WIB)
```

## Disclaimer

Sinyal berbasis indikator otomatis & data publik — bukan saran finansial. Selalu lakukan riset sendiri (DYOR).
