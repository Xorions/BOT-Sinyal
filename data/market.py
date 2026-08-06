"""Data pasar dari Binance & CoinGecko (keduanya gratis, tanpa API key).

Binance digunakan sebagai sumber utama OHLC karena rate limit-nya besar.
CoinGecko dipakai untuk daftar top koin & sebagai fallback bila pair tidak ada.
"""

import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from config import (
    COINGECKO_API_KEY,
    COINGECKO_BASE_URL,
    REQUEST_RETRIES,
    REQUEST_TIMEOUT,
    TOP_COINS,
)

BINANCE_BASE_URL = "https://api.binance.com/api/v3"

STABLECOINS = {
    "usdt", "usdc", "dai", "busd", "tusd", "usdd", "usde", "pyusd",
    "fdusd", "eurs", "ustc",
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
    """Daftar top-N koin berdasarkan market cap, tanpa stablecoin."""
    url = f"{COINGECKO_BASE_URL}/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": TOP_COINS + len(STABLECOINS),
        "page": 1,
        "sparkline": "false",
    }
    data = _get(url, params, headers=_coingecko_headers())
    filtered = [c for c in data if c["symbol"].lower() not in STABLECOINS]
    return filtered[:TOP_COINS]


def get_ohlc_binance(symbol: str) -> Optional[Tuple[List[float], List[float]]]:
    """Harga + volume per jam dari Binance (48 candle terakhir).

    Mengembalikan (prices, volumes) atau None bila pair tidak tersedia.
    """
    base = symbol.upper().replace("USDT", "")
    if not base or base == "USDT":
        return None
    pair = f"{base}USDT"
    try:
        resp = requests.get(
            f"{BINANCE_BASE_URL}/klines",
            params={"symbol": pair, "interval": "1h", "limit": 48},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        prices = [float(k[4]) for k in data]
        volumes = [float(k[5]) for k in data]
        return (prices, volumes)
    except (requests.RequestException, ValueError, IndexError):
        return None


def get_ohlc_coingecko(coin_id: str, days: int = 2) -> Tuple[List[float], List[float]]:
    """Harga + volume dari CoinGecko sebagai fallback."""
    url = f"{COINGECKO_BASE_URL}/coins/{coin_id}/market_chart"
    data = _get(url, {"vs_currency": "usd", "days": days}, headers=_coingecko_headers())
    prices = [p[1] for p in data.get("prices", [])]
    volumes = [v[1] for v in data.get("total_volumes", [])]
    return (prices, volumes)
