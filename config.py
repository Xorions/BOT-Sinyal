"""Konfigurasi bot: memuat kredensial dari file .env"""

import os
from dotenv import load_dotenv

load_dotenv()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

TOP_COINS: int = _env_int("TOP_COINS", 250)
TOP_SIGNALS: int = _env_int("TOP_SIGNALS", 5)

# Day Trading Lanjutan — Analisis Multi-Timeframe (MTF)
# Jumlah kandidat yang dianalisis mendalam (ambil chart 2x per koin dari CoinGecko).
MTF_SCAN_LIMIT: int = _env_int("MTF_SCAN_LIMIT", 6)
# Minimal kategori Confluence yang harus selaras sebelum sinyal dipromosikan
# dari NEUTRAL menjadi BUY/SELL (kategori: SMC/OB, S&D/S&R, MACD/RSI, Whale/Vol).
CONFLUENCE_MIN: int = _env_int("CONFLUENCE_MIN", 2)
# SL/TP berbasis ATR (timeframe 1H). TP1 = 2x ATR, TP2 = 3x ATR.
ATR_SL_MULT: float = _env_float("ATR_SL_MULT", 1.5)
ATR_TP1_MULT: float = _env_float("ATR_TP1_MULT", 2.0)
ATR_TP2_MULT: float = _env_float("ATR_TP2_MULT", 3.0)
# Ambang deteksi Whale Spike (volume 1H vs rata-rata 20 bar sebelumnya).
WHALE_VOLUME_MULT: float = _env_float("WHALE_VOLUME_MULT", 2.5)

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
