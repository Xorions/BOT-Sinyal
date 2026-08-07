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


def coin_price_map(coins: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Peta coin_id -> {harga terkini, high 24j, low 24j} untuk evaluasi sinyal."""
    price_map: Dict[str, Dict[str, float]] = {}
    for coin in coins:
        try:
            price_map[coin["id"]] = {
                "current_price": float(coin.get("current_price") or 0),
                "high_24h": float(coin.get("high_24h") or 0),
                "low_24h": float(coin.get("low_24h") or 0),
            }
        except (TypeError, ValueError):
            continue
    return price_map


def get_prices_for_ids(ids: List[str]) -> Dict[str, Dict[str, float]]:
    """Harga terkini + high/low 24j untuk daftar id koin (satu panggilan batch).

    Dipakai untuk mengevaluasi sinyal kemarin yang koornya tidak lagi berada
    di Top-250 pada scan hari ini.
    """
    ids = [cid for cid in ids if cid]
    if not ids:
        return {}
    url = f"{COINGECKO_BASE_URL}/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": ",".join(ids),
        "order": "market_cap_desc",
        "per_page": 250,
    }
    data = _get(url, params, headers=_coingecko_headers())
    return coin_price_map(data)


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
