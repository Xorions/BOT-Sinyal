"""Mesin skoring sinyal harian untuk Daily Briefing.

Sinyal dihitung hanya dari satu panggilan CoinGecko (markets + sparkline 7d):
- RSI dari sparkline harga (oversold/overbought)
- Tren: harga vs SMA 24 jam
- Momentum: perubahan harga 1j / 24j / 7d
- Volume aktif: rasio volume terhadap market cap dibanding seluruh koin

Skor positif = bullish (BUY/LONG), negatif = bearish (SELL/SHORT).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from config import BUY_THRESHOLD, DISCLAIMER, SELL_THRESHOLD, TOP_SIGNALS
from signals.indicators import rsi, sma

ACTION_BUY = "BUY"
ACTION_SELL = "SELL"
ACTION_NEUTRAL = "NEUTRAL"

MIN_SPARKLINE_POINTS = 24


@dataclass
class Signal:
    coin_id: str
    symbol: str
    name: str
    price: float
    price_change_24h: float
    score: float
    action: str
    confidence: int
    reasons: List[str] = field(default_factory=list)


def _sparkline_prices(coin: Dict[str, Any]) -> List[float]:
    raw = coin.get("sparkline_in_7d", {}).get("price", []) or []
    prices: List[float] = []
    for value in raw:
        try:
            p = float(value)
        except (TypeError, ValueError):
            continue
        if p > 0:
            prices.append(p)
    return prices


def _score_rsi(prices: List[float], reasons: List[str]) -> float:
    value = rsi(prices)
    if value is None:
        return 0.0
    if value < 30:
        reasons.append(f"RSI {value:.0f} oversold")
        return 2.0
    if value < 40:
        reasons.append(f"RSI {value:.0f} mendekati oversold")
        return 1.0
    if value > 70:
        reasons.append(f"RSI {value:.0f} overbought")
        return -2.0
    if value > 60:
        reasons.append(f"RSI {value:.0f} mendekati overbought")
        return -1.0
    return 0.0


def _score_trend(prices: List[float], reasons: List[str]) -> float:
    avg = sma(prices, period=24)
    if avg is None or not prices:
        return 0.0
    if prices[-1] > avg:
        reasons.append("Atas SMA 24j")
        return 1.5
    reasons.append("Bawah SMA 24j")
    return -1.5


def _score_momentum(coin: Dict[str, Any], reasons: List[str]) -> float:
    score = 0.0
    p1h = coin.get("price_change_percentage_1h_in_currency")
    p24h = coin.get("price_change_percentage_24h")
    p7d = coin.get("price_change_percentage_7d_in_currency")

    if p1h is not None:
        if p1h >= 1.5:
            score += 1.0
            reasons.append(f"Momentum 1j +{p1h:.1f}%")
        elif p1h <= -1.5:
            score -= 1.0
            reasons.append(f"Momentum 1j {p1h:.1f}%")

    if p24h is not None:
        if p24h >= 3.0:
            score += 1.5
            reasons.append(f"Momentum 24j +{p24h:.1f}%")
        elif p24h <= -3.0:
            score -= 1.5
            reasons.append(f"Momentum 24j {p24h:.1f}%")

    if p7d is not None:
        if p7d >= 8.0:
            score += 1.0
            reasons.append(f"Momentum 7d +{p7d:.1f}%")
        elif p7d <= -8.0:
            score -= 1.0
            reasons.append(f"Momentum 7d {p7d:.1f}%")

    return score


def _score_volume(turnover_pct: float, price_change_24h: float, reasons: List[str]) -> float:
    if turnover_pct is None or price_change_24h is None or abs(price_change_24h) < 0.5:
        return 0.0
    direction = 1.0 if price_change_24h > 0 else -1.0
    if turnover_pct >= 0.90:
        reasons.append("Volume sangat aktif")
        return direction * 1.5
    if turnover_pct >= 0.75:
        reasons.append("Volume aktif")
        return direction * 1.0
    return 0.0


def _turnover(coin: Dict[str, Any]) -> float:
    try:
        volume = float(coin.get("total_volume") or 0)
        cap = float(coin.get("market_cap") or 0)
    except (TypeError, ValueError):
        return 0.0
    if volume <= 0 or cap <= 0:
        return 0.0
    return volume / cap


def _turnover_percentiles(coins: List[Dict[str, Any]]) -> Dict[str, float]:
    values = [(c["id"], _turnover(c)) for c in coins]
    values = [(cid, v) for cid, v in values if v > 0]
    values.sort(key=lambda item: item[1])
    count = len(values)
    if count == 0:
        return {}
    return {cid: (index + 1) / count for index, (cid, _) in enumerate(values)}


def build_signal(coin: Dict[str, Any], turnover_pct: float) -> Signal:
    prices = _sparkline_prices(coin)
    reasons: List[str] = []
    score = 0.0
    score += _score_rsi(prices, reasons)
    score += _score_trend(prices, reasons)
    score += _score_momentum(coin, reasons)
    score += _score_volume(turnover_pct, coin.get("price_change_percentage_24h"), reasons)

    if score >= BUY_THRESHOLD:
        action = ACTION_BUY
    elif score <= SELL_THRESHOLD:
        action = ACTION_SELL
    else:
        action = ACTION_NEUTRAL

    try:
        price_change_24h = float(coin.get("price_change_percentage_24h") or 0)
    except (TypeError, ValueError):
        price_change_24h = 0.0

    return Signal(
        coin_id=coin["id"],
        symbol=coin["symbol"].upper(),
        name=coin["name"],
        price=float(coin["current_price"] or 0),
        price_change_24h=price_change_24h,
        score=score,
        action=action,
        confidence=max(45, min(95, 55 + int(abs(score) * 5))),
        reasons=reasons,
    )


def rank_signals(coins: List[Dict[str, Any]]) -> List[Signal]:
    """Hitung skor semua koin lalu pilih TOP-N sinyal paling solid."""
    percentiles = _turnover_percentiles(coins)
    signals: List[Signal] = []
    for coin in coins:
        try:
            price = float(coin["current_price"] or 0)
            cap = float(coin["market_cap"] or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0 or cap <= 0:
            continue
        if len(_sparkline_prices(coin)) < MIN_SPARKLINE_POINTS:
            continue
        signals.append(build_signal(coin, percentiles.get(coin["id"])))

    signals.sort(key=lambda s: abs(s.score), reverse=True)
    return signals[:TOP_SIGNALS]


def _format_price(value: float) -> str:
    if value >= 1000:
        return f"${value:,.0f}"
    if value >= 1:
        return f"${value:,.2f}"
    return f"${value:.6f}"


def _levels(sig: Signal) -> tuple:
    """Entry/SL/TP berdasarkan arah sinyal.

    BUY/LONG:  SL 8% di bawah entry, TP1 +5%, TP2 +10%.
    SELL/SHORT: SL 8% di atas entry, TP1 -5%, TP2 -10%.
    """
    if sig.action == ACTION_SELL:
        return sig.price * 1.08, sig.price * 0.95, sig.price * 0.90
    return sig.price * 0.92, sig.price * 1.05, sig.price * 1.10


def _signal_lines(sig: Signal, number: int) -> List[str]:
    sl, tp1, tp2 = _levels(sig)
    summary = " | ".join(sig.reasons) if sig.reasons else "—"
    levels = (
        f"   SL: <b>{_format_price(sl)}</b> (8%) | "
        f"TP1: <b>{_format_price(tp1)}</b> (5%) | "
        f"TP2: <b>{_format_price(tp2)}</b> (10%)"
    )
    return [
        f"{number}. <b>#{sig.symbol}</b> — {sig.action} ({sig.confidence}%)",
        f"   Entry: <b>{_format_price(sig.price)}</b>",
        levels,
        f"   <i>{summary}</i>",
        "---",
    ]


def format_message(signals: List[Signal], timestamp: str, total_scanned: int) -> str:
    buys = sorted(
        (s for s in signals if s.action == ACTION_BUY),
        key=lambda s: abs(s.score),
        reverse=True,
    )
    sells = sorted(
        (s for s in signals if s.action == ACTION_SELL),
        key=lambda s: abs(s.score),
        reverse=True,
    )
    neutrals = [s for s in signals if s.action == ACTION_NEUTRAL]

    lines = [
        "<b>📊 Daily Briefing Crypto</b>",
        f"🕐 {timestamp}",
        f"🔎 Dipantau: {total_scanned} koin (Top market cap)",
        "",
    ]

    number = 1
    if buys:
        lines.append("<b>🟢 SINYAL LONG (BUY)</b>")
        lines.append("")
        for sig in buys:
            lines.extend(_signal_lines(sig, number))
            number += 1

    if sells:
        lines.append("<b>🔴 SINYAL SHORT (SELL)</b>")
        lines.append("")
        for sig in sells:
            lines.extend(_signal_lines(sig, number))
            number += 1

    if neutrals:
        lines.append("<b>⚪ WATCHLIST (NEUTRAL)</b>")
        lines.append("")
        for sig in neutrals:
            lines.extend(_signal_lines(sig, number))
            number += 1

    lines.append(DISCLAIMER)
    return "\n".join(lines)
