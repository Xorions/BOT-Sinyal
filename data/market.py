"""Data pasar dari CoinGecko (gratis, tanpa API key).

Satu panggilan endpoint `markets` sudah mencakup daftar top koin, perubahan
harga (1j/24j/7d), dan sparkline harga 7 hari untuk semua koin — hemat kuota API.
"""

import time
from typing import Any, Dict, List, Optional

import requests

from config import (
    COINGECKO_API_KEY,
    COINGECKO_BASE_URL,
    REQUEST_RETRIES,
    REQUEST_TIMEOUT,
    TOP_COINS,
)

STABLECOINS = {
    "usdt", "usdc", "dai", "busd", "tusd", "usdd", "usde", "pyusd",
    "fdusd", "eurs", "ustc", "susde", "euroc", "usd1", "usdx",
}


class MarketDataError(Exception):
    """Gagal mengambil data pasar."""


def _sleep_seconds(attempt: int) -> float:
    return float(5 * (attempt + 1))


def _coingecko_headers() -> Dict[str, str]:
    if COINGECKO_API_KEY:
        return {"x-cg-demo-api-key": COINGECKO_API_KEY}
    return {}


def _get(url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Any:
    last_error: Optional[Exception] = None
    for attempt in range(REQUEST_RETRIES):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                try:
                    wait = min(float(retry_after), 60.0)
                except (TypeError, ValueError):
                    wait = 15.0
                time.sleep(wait)
                last_error = requests.HTTPError(f"429 rate limit, menunggu {wait:.0f}s")
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < REQUEST_RETRIES - 1:
                time.sleep(_sleep_seconds(attempt))
    raise MarketDataError(f"Gagal mengambil data {url}: {last_error}")


def get_top_coins() -> List[Dict[str, Any]]:
    """Daftar top-N koin berdasarkan market cap, tanpa stablecoin.

    Satu panggilan API menyediakan harga terkini, perubahan harga 1j/24j/7d,
    dan sparkline harga 7 hari untuk setiap koin.
    """
    url = f"{COINGECKO_BASE_URL}/coins/markets"
    per_page = min(TOP_COINS + len(STABLECOINS), 250)
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": per_page,
        "page": 1,
        "sparkline": "true",
        "price_change_percentage": "1h,24h,7d",
    }
    data = _get(url, params, headers=_coingecko_headers())
    filtered = [c for c in data if c["symbol"].lower() not in STABLECOINS]
    return filtered[:TOP_COINS]
