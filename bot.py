"""Entry point bot sinyal trading.

Menjalankan Daily Briefing: scan top koin (satu panggilan CoinGecko),
pilih TOP-5 sinyal terbaik, lalu kirim ke Telegram. Sebelum mengirim,
bot mengevaluasi sinyal kemarin dari data/history.json dan menampilkan
ringkasannya di bagian paling atas pesan (performance tracking).
Setelah sukses terkirim, sinyal hari ini disimpan ke history.

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
from data.history import append_signals, format_evaluation, load_last_entry
from data.market import coin_price_map, get_prices_for_ids, get_top_coins
from signals.engine import format_message, rank_signals
from telegram_sender import TelegramSendError, send_telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("signal-bot")


def run_scan() -> tuple:
    log.info("Mengambil top %d koin dari CoinGecko...", TOP_COINS)
    coins = get_top_coins()
    log.info("Ditemukan %d koin (setelah filter stablecoin).", len(coins))

    signals = rank_signals(coins)
    log.info("Terpilih %d sinyal terbaik.", len(signals))
    for sig in signals:
        log.info("Sinyal %s -> %s (skor %+.1f)", sig.symbol, sig.action, sig.score)
    return signals, coins


def evaluate_yesterday(coins: list) -> str:
    """Baca sinyal kemarin dari history, bandingkan dengan harga saat ini."""
    prev_entry = load_last_entry()
    price_map = coin_price_map(coins)
    missing_ids = [
        record.get("coin_id")
        for record in (prev_entry or {}).get("signals", [])
        if record.get("coin_id") and record.get("coin_id") not in price_map
    ]
    if missing_ids:
        try:
            price_map.update(get_prices_for_ids(missing_ids))
        except Exception as exc:  # noqa: BLE001 - evaluasi tidak boleh menggagalkan briefing
            log.warning("Gagal mengambil harga evaluasi kemarin: %s", exc)
    return format_evaluation(prev_entry, price_map)


def main() -> int:
    try:
        signals, coins = run_scan()
    except Exception as exc:  # noqa: BLE001 - laporkan error apa pun agar terlihat di CI
        log.error("Gagal menjalankan scan: %s", exc)
        return 1

    try:
        evaluation = evaluate_yesterday(coins)
    except Exception as exc:  # noqa: BLE001
        log.warning("Gagal mengevaluasi sinyal kemarin: %s", exc)
        evaluation = "<b>📊 EVALUASI SINYAL KEMARIN</b>\n🗓️ Gagal memuat data evaluasi."

    timestamp = datetime.now().strftime("%A, %d %b %Y, %H:%M WIB")
    body = format_message(signals, timestamp, len(coins))
    message = evaluation + "\n\n" + body

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Kredensial belum diisi di .env - hasil hanya ditampilkan di konsol.")
        print("\n" + message + "\n")
        return 0

    try:
        send_telegram(message)
        append_signals(signals)
        log.info("Pesan terkirim ke Telegram & history sinyal tersimpan.")
        return 0
    except TelegramSendError as exc:
        log.error("Gagal mengirim: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
