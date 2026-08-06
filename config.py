"""Konfigurasi bot: memuat kredensial dari file .env"""

import os
from dotenv import load_dotenv

load_dotenv()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

TOP_COINS: int = int(os.getenv("TOP_COINS", "250"))
TOP_SIGNALS: int = int(os.getenv("TOP_SIGNALS", "5"))

# Opsional: free API key dari CoinGecko (https://www.coingecko.com/en/api)
# Tanpa key pakai kuota publik kecil, dengan key 30 req/menit.
COINGECKO_API_KEY: str = os.getenv("COINGECKO_API_KEY", "")
BUY_THRESHOLD: float = _env_float("BUY_THRESHOLD", 3.0)
SELL_THRESHOLD: float = _env_float("SELL_THRESHOLD", -3.0)

COINGECKO_BASE_URL: str = "https://api.coingecko.com/api/v3"
DEFILLAMA_BASE_URL: str = "https://api.llama.fi"

REQUEST_TIMEOUT: int = 30
REQUEST_RETRIES: int = 3

DISCLAIMER: str = (
    "⚠️ Disclaimer: Sinyal ini berbasis indikator otomatis & data publik. "
    "Bukan saran finansial. Selalu lakukan riset sendiri (DYOR)."
)
