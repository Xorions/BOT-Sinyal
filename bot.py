"""Entry point bot sinyal trading.

Menjalankan Daily Briefing: scan top koin (satu panggilan CoinGecko),
pilih TOP-5 sinyal terbaik, lalu kirim ke Telegram.
Jadwal harian (07:00 WIB) diatur oleh GitHub Actions (lihat .github/workflows/daily.yml).
Untuk uji lokal:  python bot.py
"""

import logging
import sys
from datetime import datetime

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (ValueError, OSError):
        pass

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TOP_COINS
from data.market import get_top_coins
from signals.engine import format_message, rank_signals
from telegram_sender import TelegramSendError, send_telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("signal-bot")


def run_scan() -> str:
    log.info("Mengambil top %d koin dari CoinGecko...", TOP_COINS)
    coins = get_top_coins()
    log.info("Ditemukan %d koin (setelah filter stablecoin).", len(coins))

    signals = rank_signals(coins)
    log.info("Terpilih %d sinyal terbaik.", len(signals))
    for sig in signals:
        log.info("Sinyal %s -> %s (skor %+.1f)", sig.symbol, sig.action, sig.score)

    timestamp = datetime.now().strftime("%A, %d %b %Y, %H:%M WIB")
    return format_message(signals, timestamp, len(coins))


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
