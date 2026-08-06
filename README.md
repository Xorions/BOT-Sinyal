# BOT-Sinyal-Trading

Bot Telegram yang mengirim sinyal trading crypto setiap 1 jam berdasarkan data pasar & on-chain (gratis, tanpa API key berbayar).

## Cara Kerja

Setiap jam penuh, GitHub Actions menjalankan `bot.py`:
1. Ambil 10 koin teratas (CoinGecko) — stablecoin disaring.
2. Ambil harga & volume 48 bar per jam (Binance, fallback CoinGecko).
3. Ambil perubahan TVL harian per chain (DefiLlama).
4. Hitung skor gabungan (SMA, RSI, volume spike, TVL) → `BUY` / `SELL` / `NEUTRAL`.
5. Kirim ringkasan ke Telegram.

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
bot.py                        # Entry point: scan + kirim
config.py                     # Konfigurasi & kredensial dari .env
telegram_sender.py            # Kirim pesan ke Telegram
data/market.py                # Binance + CoinGecko (OHLC, top coins)
data/onchain.py               # DefiLlama (TVL chain)
signals/indicators.py         # RSI, SMA, volume spike
signals/engine.py             # Skoring BUY/SELL/NEUTRAL + format pesan
.github/workflows/hourly.yml  # Scheduler tiap jam
```

## Disclaimer

Sinyal berbasis indikator otomatis & data publik — bukan saran finansial. Selalu lakukan riset sendiri (DYOR).
