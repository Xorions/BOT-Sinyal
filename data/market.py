"""Data pasar dari CoinGecko (gratis, tanpa API key).

- `markets`: satu panggilan untuk daftar top koin + perubahan harga (1j/24j/7d)
  + sparkline 7 hari.
- `market_chart`: data harga & volume per koin untuk analisis Multi-Timeframe
  (MTF). `days=2` → granularitas 5 menit (dipakai untuk 15M/1H), `days=30` →
  granularitas 1 jam (dipakai untuk 1H/4H/1D). Candle di-bucket oleh
  `build_candles`.
"""

import time
from dataclasses import dataclass
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


@dataclass
class Candle:
    """Satu candle OHLCV hasil bucket dari seri harga/volume CoinGecko."""

    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


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


def get_market_chart(coin_id: str, days: int) -> Dict[str, Any]:
    """Data harga/volume historis satu koin (endpoint `/coins/{id}/market_chart`).

    Granularitas mengikuti `days`: 1-2 → 5 menit, 30 → 1 jam, 365 → harian.
    Dipakai untuk analisis Multi-Timeframe (15M/1H/4H/1D).
    """
    url = f"{COINGECKO_BASE_URL}/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": days}
    return _get(url, params, headers=_coingecko_headers())


def _bucket_candles(
    price_series: List[List[Any]], volume_series: List[List[Any]], interval_minutes: int
) -> List[Candle]:
    """Bucket seri `[ts_ms, value]` menjadi candle `interval_minutes` menit."""
    span = interval_minutes * 60 * 1000
    price_buckets: Dict[int, List[float]] = {}
    for item in price_series or []:
        try:
            ts, price = int(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        bucket = ts // span
        price_buckets.setdefault(bucket, []).append(price)

    volume_buckets: Dict[int, float] = {}
    for item in volume_series or []:
        try:
            ts, volume = int(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        bucket = ts // span
        volume_buckets[bucket] = volume_buckets.get(bucket, 0.0) + volume

    candles: List[Candle] = []
    for bucket in sorted(price_buckets):
        prices = price_buckets[bucket]
        candles.append(
            Candle(
                time=bucket * span,
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=volume_buckets.get(bucket, 0.0),
            )
        )
    return candles


def build_candles(raw: Dict[str, Any], interval_minutes: int) -> List[Candle]:
    """Bangun candle dari respons `market_chart` untuk interval menit tertentu.

    Contoh: `interval_minutes=15` → candle 15 menit, `=240` → 4 jam, `=1440` → harian.
    """
    return _bucket_candles(
        raw.get("prices", []), raw.get("total_volumes", []), interval_minutes
    )
