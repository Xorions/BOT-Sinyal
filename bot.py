"""Entry point bot sinyal trading.

Jalankan sekali: setiap panggilan men-scan data lalu kirim hasil ke Telegram.
Jadwal per-jam diatur oleh GitHub Actions (lihat .github/workflows/hourly.yml).
Untuk uji lokal:  python bot.py
"""

import logging
import sys
import time
from datetime import datetime

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (ValueError, OSError):
        pass

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from data.market import MarketDataError, get_ohlc, get_top_coins
from data.onchain import get_tvl_change
from signals.engine import build_signal, format_message
from telegram_sender import TelegramSendError, send_telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("signal-bot")


def run_scan() -> str:
    log.info("Mengambil daftar top koin dari CoinGecko...")
    coins = get_top_coins()
    log.info("Ditemukan %d koin.", len(coins))

    signals = []
    for i, coin in enumerate(coins):
        try:
            prices, volumes = get_ohlc(coin["id"], days=2)
        except MarketDataError as exc:
            log.warning("Lewati %s: %s", coin["id"], exc)
            continue

        tvl_change = get_tvl_change(coin["id"])

        signals.append(build_signal(coin, prices, volumes, tvl_change))
        log.info(
            "Sinyal %s -> %s (skor %.1f)",
            coin["symbol"].upper(), signals[-1].action, signals[-1].score,
        )

        if i < len(coins) - 1:
            time.sleep(2.0)

    timestamp = datetime.now().strftime("%d %b %Y, %H:%M WIB")
    return format_message(signals, timestamp)


def main() -> int:
    try:
        message = run_scan()
    except Exception as exc:  # noqa: BLE001 - laporkan error apa pun agar terlihat di CI
        log.error("Gagal menjalankan scan: %s", exc)
        return 1

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Kredensial belum diisi di .env - hasil hanya ditampilkan di konsol.")
        print("\n" + message + "\n")
        return 0

    try:
        send_telegram(message)
        log.info("Pesan terkirim ke Telegram.")
        return 0
    except TelegramSendError as exc:
        log.error("Gagal mengirim: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
