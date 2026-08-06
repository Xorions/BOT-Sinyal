"""Mengirim pesan ke Telegram via Bot API (HTTP langsung, tanpa library besar)."""

import requests

from config import REQUEST_TIMEOUT, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


class TelegramSendError(Exception):
    """Gagal mengirim pesan ke Telegram."""


def send_telegram(text: str, chat_id: str = "") -> None:
    token = TELEGRAM_BOT_TOKEN.strip()
    chat = (chat_id or TELEGRAM_CHAT_ID).strip()
    if not token or not chat:
        raise TelegramSendError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diisi di .env")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        raise TelegramSendError(f"Telegram API error {resp.status_code}: {resp.text[:200]}")
