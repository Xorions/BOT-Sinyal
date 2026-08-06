"""Mesin skoring sinyal: gabungkan tren, RSI, volume, dan data on-chain.

Skor positif = bullish (BUY), negatif = bearish (SELL).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config import BUY_THRESHOLD, DISCLAIMER, SELL_THRESHOLD
from signals.indicators import sma, rsi, volume_spike_ratio

ACTION_BUY = "BUY"
ACTION_SELL = "SELL"
ACTION_NEUTRAL = "NEUTRAL"


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


def _score_trend(prices: List[float], price_change_24h: float, reasons: List[str]) -> float:
    score = 0.0
    avg = sma(prices)
    current = prices[-1] if prices else None
    if avg and current:
        if current > avg:
            score += 1.5
            reasons.append(f"harga di atas SMA 12j")
        else:
            score -= 1.5
            reasons.append(f"harga di bawah SMA 12j")
    if price_change_24h >= 2.0:
        score += 1.0
        reasons.append(f"naik {price_change_24h:.1f}% (24j)")
    elif price_change_24h <= -2.0:
        score -= 1.0
        reasons.append(f"turun {price_change_24h:.1f}% (24j)")
    return score


def _score_rsi(prices: List[float], reasons: List[str]) -> float:
    value = rsi(prices)
    if value is None:
        return 0.0
    if value < 30:
        reasons.append(f"RSI {value:.0f} (oversold)")
        return 2.0
    if value < 40:
        reasons.append(f"RSI {value:.0f} (mendekati oversold)")
        return 1.0
    if value > 70:
        reasons.append(f"RSI {value:.0f} (overbought)")
        return -2.0
    if value > 60:
        reasons.append(f"RSI {value:.0f} (mendekati overbought)")
        return -1.0
    return 0.0


def _score_volume(volumes: List[float], prices: List[float], reasons: List[str]) -> float:
    ratio = volume_spike_ratio(volumes)
    if ratio is None or ratio < 1.4:
        return 0.0
    up = len(prices) >= 2 and prices[-1] >= prices[-2]
    direction = 1.5 if up else -1.5
    trend = "kenaikan" if up else "penurunan"
    reasons.append(f"volume spike {ratio:.1f}x ({trend})")
    return direction


def _score_onchain(tvl_change: Optional[float], reasons: List[str]) -> float:
    if tvl_change is None:
        return 0.0
    if tvl_change >= 2.0:
        reasons.append(f"TVL chain +{tvl_change:.1f}%")
        return 1.0
    if tvl_change <= -2.0:
        reasons.append(f"TVL chain {tvl_change:.1f}%")
        return -1.0
    return 0.0


def _confidence(score: float) -> int:
    return max(40, min(95, 55 + int(abs(score) * 7)))


def build_signal(
    coin: Dict[str, object],
    prices: List[float],
    volumes: List[float],
    tvl_change: Optional[float],
) -> Signal:
    reasons: List[str] = []
    score = 0.0
    score += _score_trend(prices, float(coin.get("price_change_percentage_24h") or 0), reasons)
    score += _score_rsi(prices, reasons)
    score += _score_volume(volumes, prices, reasons)
    score += _score_onchain(tvl_change, reasons)

    if score >= BUY_THRESHOLD:
        action = ACTION_BUY
    elif score <= SELL_THRESHOLD:
        action = ACTION_SELL
    else:
        action = ACTION_NEUTRAL

    return Signal(
        coin_id=coin["id"],
        symbol=coin["symbol"].upper(),
        name=coin["name"],
        price=float(coin["current_price"] or 0),
        price_change_24h=float(coin.get("price_change_percentage_24h") or 0),
        score=score,
        action=action,
        confidence=_confidence(score),
        reasons=reasons,
    )


def _format_price(value: float) -> str:
    if value >= 1000:
        return f"${value:,.0f}"
    if value >= 1:
        return f"${value:,.2f}"
    return f"${value:.6f}"


def _icon(action: str) -> str:
    return {"BUY": "🟢", "SELL": "🔴", "NEUTRAL": "⚪"}.get(action, "⚪")


def format_message(signals: List[Signal], timestamp: str) -> str:
    lines = [
        f"<b>📊 Crypto Signal Bot</b>",
        f"🕐 {timestamp}",
        "",
    ]
    for sig in sorted(signals, key=lambda s: abs(s.score), reverse=True):
        icon = _icon(sig.action)
        lines.append(
            f"{icon} <b>{sig.symbol}</b> — {sig.action} ({sig.confidence}%)"
        )
        lines.append(
            f"   {sig.name} · {_format_price(sig.price)} "
            f"({sig.price_change_24h:+.1f}% 24j)"
        )
        if sig.reasons:
            lines.append(f"   <i>{', '.join(sig.reasons)}</i>")
        lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)
