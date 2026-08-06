"""Indikator teknis sederhana: RSI dan SMA."""

from typing import List, Optional

RSI_PERIOD = 14
SMA_PERIOD = 24


def sma(values: List[float], period: int = SMA_PERIOD) -> Optional[float]:
    """Rata-rata sederhana dari `period` nilai terakhir."""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def rsi(prices: List[float], period: int = RSI_PERIOD) -> Optional[float]:
    """Relative Strength Index dengan smoothing Wilder.

    Di bawah 30 = oversold (potensi naik), di atas 70 = overbought (potensi turun).
    """
    if len(prices) < period + 1:
        return None
    deltas = [prices[i + 1] - prices[i] for i in range(len(prices) - 1)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))
