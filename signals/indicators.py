"""Indikator teknis: RSI, SMA, EMA, MACD, ATR, struktur SMC (BOS/CHoCH, Order Block),
Support/Resistance, Supply/Demand, RSI Divergence, dan deteksi Volume/Whale Spike.

Semua fungsi murni (tanpa I/O): menerima list angka dan mengembalikan angka,
list, atau None bila data tidak cukup. Threshold tersentralisasi di config.py
(dipakai oleh signals/engine.py).
"""

from typing import List, Optional, Tuple

RSI_PERIOD = 14
SMA_PERIOD = 24


def sma(values: List[float], period: int = SMA_PERIOD) -> Optional[float]:
    """Rata-rata sederhana dari `period` nilai terakhir."""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema_series(values: List[float], period: int) -> List[Optional[float]]:
    """Deret EMA sejajar dengan `values` (awal berisi None sampai data cukup)."""
    if period <= 0 or len(values) < period:
        return [None] * len(values)
    k = 2.0 / (period + 1)
    prev = sum(values[:period]) / period
    out: List[Optional[float]] = [None] * (period - 1)
    out.append(prev)
    for price in values[period:]:
        prev = price * k + prev * (1 - k)
        out.append(prev)
    return out


def ema(values: List[float], period: int) -> Optional[float]:
    """Nilai EMA terakhir dari `values`."""
    series = ema_series(values, period)
    return series[-1] if series else None


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


def rsi_series(prices: List[float], period: int = RSI_PERIOD) -> List[Optional[float]]:
    """Deret RSI sejajar dengan `prices` (awal berisi None sampai data cukup)."""
    return [rsi(prices[: i + 1], period) for i in range(len(prices))]


def macd(
    values: List[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """MACD. Mengembalikan (macd_line, signal_line, histogram) sejajar `values`.

    Histogram positif = momentum bullish, negatif = momentum bearish.
    Crossover bullish terjadi saat histogram berubah dari <=0 menjadi >0.
    """
    n = len(values)
    if n < slow + signal:
        return [None] * n, [None] * n, [None] * n
    fast_e = ema_series(values, fast)
    slow_e = ema_series(values, slow)
    macd_line: List[Optional[float]] = [
        (f - s) if f is not None and s is not None else None
        for f, s in zip(fast_e, slow_e)
    ]
    valid = [m for m in macd_line if m is not None]
    sig_valid = ema_series(valid, signal)
    signal_line: List[Optional[float]] = [None] * (n - len(valid))
    signal_line.extend(sig_valid)
    histogram = [
        (m - s) if m is not None and s is not None else None
        for m, s in zip(macd_line, signal_line)
    ]
    return macd_line, signal_line, histogram


def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
    """Average True Range (smoothing Wilder) — ukuran volatilitas untuk SL/TP."""
    n = len(closes)
    if n < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    prev = sum(trs[:period]) / period
    for tr in trs[period:]:
        prev = (prev * (period - 1) + tr) / period
    return prev


def swing_highs(highs: List[float], window: int = 3) -> List[int]:
    """Indeks pivot high (kiri & kanan `window` bar lebih rendah)."""
    if len(highs) < 2 * window + 1:
        return []
    idx = []
    for i in range(window, len(highs) - window):
        chunk = highs[i - window : i + window + 1]
        if highs[i] == max(chunk) and chunk.count(highs[i]) == 1:
            idx.append(i)
    return idx


def swing_lows(lows: List[float], window: int = 3) -> List[int]:
    """Indeks pivot low (kiri & kanan `window` bar lebih tinggi)."""
    if len(lows) < 2 * window + 1:
        return []
    idx = []
    for i in range(window, len(lows) - window):
        chunk = lows[i - window : i + window + 1]
        if lows[i] == min(chunk) and chunk.count(lows[i]) == 1:
            idx.append(i)
    return idx


def structure_break(
    highs: List[float], lows: List[float], closes: List[float], window: int = 3
) -> Tuple[str, str]:
    """Deteksi break struktur terakhir.

    Returns (kind, direction):
      kind      = "BOS" / "CHoCH" / "" (tidak ada break baru)
      direction = "BULL" / "BEAR" / ""
    """
    sh = swing_highs(highs, window)
    sl = swing_lows(lows, window)
    if len(sh) < 2 or len(sl) < 2:
        return "", ""
    prev_sh, last_sh = sh[-2], sh[-1]
    prev_sl, last_sl = sl[-2], sl[-1]
    close = closes[-1]
    uptrend = highs[last_sh] > highs[prev_sh] and lows[last_sl] > lows[prev_sl]
    downtrend = highs[last_sh] < highs[prev_sh] and lows[last_sl] < lows[prev_sl]
    if close > highs[last_sh]:
        return ("BOS", "BULL") if uptrend else ("CHoCH", "BULL")
    if close < lows[last_sl]:
        return ("BOS", "BEAR") if downtrend else ("CHoCH", "BEAR")
    return "", ""


def order_block(
    opens: List[float], highs: List[float], lows: List[float], closes: List[float], direction: str
) -> Optional[Tuple[float, float]]:
    """Order Block terakhir. Returns (zone_top, zone_bottom) atau None.

    BULL: candle bearish terakhir sebelum swing low terakhir (demand / retest support).
    BEAR: candle bullish terakhir sebelum swing high terakhir (supply / retest resistance).
    """
    window = 3
    if direction.upper() == "BULL":
        sl = swing_lows(lows, window)
        if not sl:
            return None
        low_idx = sl[-1]
        for i in range(low_idx - 1, max(0, low_idx - 6), -1):
            if closes[i] < closes[i - 1]:
                top = max(opens[i], closes[i])
                bottom = lows[i]
                return top, bottom
    elif direction.upper() == "BEAR":
        sh = swing_highs(highs, window)
        if not sh:
            return None
        high_idx = sh[-1]
        for i in range(high_idx - 1, max(0, high_idx - 6), -1):
            if closes[i] > closes[i - 1]:
                top = highs[i]
                bottom = min(opens[i], closes[i])
                return top, bottom
    return None


def nearest_levels(
    highs: List[float], lows: List[float], closes: List[float], window: int = 3
) -> Tuple[Optional[float], Optional[float]]:
    """(support terdekat di bawah harga, resistance terdekat di atas harga)."""
    price = closes[-1]
    sh = swing_highs(highs, window)
    sl = swing_lows(lows, window)
    resist = [highs[i] for i in sh if highs[i] > price]
    support = [lows[i] for i in sl if lows[i] < price]
    resistance = min(resist) if resist else None
    nearest_support = max(support) if support else None
    return nearest_support, resistance


def demand_supply_zones(
    opens: List[float], highs: List[float], lows: List[float], closes: List[float], atr_value: float
) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
    """Zona Demand & Supply terakhir dari candle ber-body kuat.

    Returns ((zone_top, zone_bottom) demand, (zone_top, zone_bottom) supply).
    """
    demand: Optional[Tuple[float, float]] = None
    supply: Optional[Tuple[float, float]] = None
    lookback = min(len(closes), 12)
    for i in range(len(closes) - 1, len(closes) - lookback - 1, -1):
        body = closes[i] - opens[i]
        if body >= 1.2 * atr_value and demand is None:
            demand = (closes[i], lows[i])
        elif body <= -1.2 * atr_value and supply is None:
            supply = (highs[i], opens[i])
        if demand is not None and supply is not None:
            break
    return demand, supply


def rsi_divergence(prices: List[float], rsi_values: List[float], window: int = 3) -> str:
    """Divergence RSI pada dua swing terakhir.

    BULLISH_DIV: harga membuat LL tapi RSI membuat HL (momentum melemah ke bawah).
    BEARISH_DIV: harga membuat HH tapi RSI membuat LH (momentum melemah ke atas).
    """
    if len(prices) < 2 * window + 1 or len(rsi_values) != len(prices):
        return ""
    pl = swing_lows(prices, window)
    ph = swing_highs(prices, window)
    if len(pl) >= 2:
        i1, i2 = pl[-2], pl[-1]
        if prices[i2] < prices[i1] and rsi_values[i2] > rsi_values[i1]:
            return "BULLISH_DIV"
    if len(ph) >= 2:
        i1, i2 = ph[-2], ph[-1]
        if prices[i2] > prices[i1] and rsi_values[i2] < rsi_values[i1]:
            return "BEARISH_DIV"
    return ""


def volume_spike(volumes: List[float], multiplier: float = 2.5, period: int = 20) -> bool:
    """Volume bar terakhir jauh di atas rata-rata periode sebelumnya (Whale Spike)."""
    if len(volumes) < period + 1:
        return False
    baseline = sum(volumes[-(period + 1) : -1]) / period
    if baseline <= 0:
        return False
    return volumes[-1] >= baseline * multiplier


def volume_ratio(volumes: List[float], period: int = 20) -> Optional[float]:
    """Rasio volume bar terakhir terhadap rata-rata periode sebelumnya."""
    if len(volumes) < period + 1:
        return None
    baseline = sum(volumes[-(period + 1) : -1]) / period
    if baseline <= 0:
        return None
    return volumes[-1] / baseline
