"""Mesin sinyal Day Trading Lanjutan dengan Analisis Multi-Timeframe (MTF).

Alur kerja:
1. Quick scan — dari satu panggilan `markets` (sparkline 7d + turnover), hitung
   skor momentum cepat untuk semua koin lalu ambil kandidat TOP `MTF_SCAN_LIMIT`.
2. Deep scan (MTF) — untuk tiap kandidat ambil chart historis CoinGecko:
   LTF 1H/15M (entry, SL, TP) dan HTF 4H/1D (trend bias). Analisis komponen:
   - Utama: Support/Resistance, Supply/Demand, SMC (BOS/CHoCH), Order Block.
   - Pendukung: MACD crossover, RSI divergence, deteksi Volume/Whale Spike.
3. Gabung skor quick + poin konfluensi MTF -> BUY/SELL/NEUTRAL. Sinyal butuh
   minimal `CONFLUENCE_MIN` kategori selaras agar dipromosikan. Entry/SL/TP
   berbasis ATR (fallback persen bila ATR tidak tersedia).
4. Format pesan menyertakan "Confluence Checklist" per sinyal.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from config import (
    ATR_SL_MULT,
    ATR_TP1_MULT,
    ATR_TP2_MULT,
    BUY_THRESHOLD,
    CONFLUENCE_MIN,
    DISCLAIMER,
    MTF_SCAN_LIMIT,
    SELL_THRESHOLD,
    TOP_SIGNALS,
    WHALE_VOLUME_MULT,
)
from data.market import MarketDataError, build_candles, get_market_chart
from signals.indicators import (
    atr,
    demand_supply_zones,
    ema,
    macd,
    nearest_levels,
    order_block,
    rsi,
    rsi_divergence,
    rsi_series,
    sma,
    structure_break,
    volume_ratio,
    volume_spike,
)

ACTION_BUY = "BUY"
ACTION_SELL = "SELL"
ACTION_NEUTRAL = "NEUTRAL"

MIN_SPARKLINE_POINTS = 24

CHECKLIST_CATEGORIES = ("SMC/OB", "S&D/S&R", "MACD/RSI", "Whale/Vol")


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
    sl: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    atr_value: float = 0.0
    ht_bias: str = ""
    ltf: str = "1H"
    checklist: Dict[str, Tuple[int, int]] = field(default_factory=dict)


@dataclass
class MTFResult:
    """Hasil analisis Multi-Timeframe untuk satu koin."""

    coin_id: str
    ht_bias: str  # BULLISH / BEARISH / NEUTRAL (dari 4H + 1D)
    bos_kind: str  # BOS / CHoCH / ""
    bos_direction: str  # BULL / BEAR / ""
    ob_bullish: bool
    ob_bearish: bool
    support: Optional[float]
    resistance: Optional[float]
    near_support: bool
    near_resistance: bool
    demand_zone: bool
    supply_zone: bool
    macd_cross: str  # BULLISH_CROSS / BEARISH_CROSS / ""
    rsi_value: Optional[float]
    rsi_div: str  # BULLISH_DIV / BEARISH_DIV / ""
    rsi_bull_aligned: bool
    rsi_bear_aligned: bool
    whale_bull: bool
    whale_bear: bool
    volume_ratio: Optional[float]
    atr_1h: Optional[float]
    bull_points: float
    bear_points: float
    bull_reasons: List[str] = field(default_factory=list)
    bear_reasons: List[str] = field(default_factory=list)
    ltf: str = "1H"


# ---------------------------------------------------------------------------
# Quick scan (dari sparkline 7d / turnover) — dipakai untuk shortlist kandidat
# ---------------------------------------------------------------------------


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


def _atr_levels(price: float, atr_value: float, action: str) -> Tuple[float, float, float]:
    """SL/TP berbasis ATR (LTF 1H). Fallback ke persentase bila ATR kosong."""
    if atr_value and atr_value > 0:
        if action == ACTION_SELL:
            return (
                price + atr_value * ATR_SL_MULT,
                price - atr_value * ATR_TP1_MULT,
                price - atr_value * ATR_TP2_MULT,
            )
        return (
            price - atr_value * ATR_SL_MULT,
            price + atr_value * ATR_TP1_MULT,
            price + atr_value * ATR_TP2_MULT,
        )
    if action == ACTION_SELL:
        return price * 1.08, price * 0.95, price * 0.90
    return price * 0.92, price * 1.05, price * 1.10


def build_signal(coin: Dict[str, Any], turnover_pct: float) -> Signal:
    """Skor cepat (momentum + volume + RSI sparkline) — untuk shortlist."""
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

    price = float(coin["current_price"] or 0)
    sl, tp1, tp2 = _atr_levels(price, 0.0, action)

    return Signal(
        coin_id=coin["id"],
        symbol=coin["symbol"].upper(),
        name=coin["name"],
        price=price,
        price_change_24h=price_change_24h,
        score=score,
        action=action,
        confidence=max(45, min(95, 55 + int(abs(score) * 5))),
        reasons=reasons,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
    )


# ---------------------------------------------------------------------------
# Analisis Multi-Timeframe (deep scan)
# ---------------------------------------------------------------------------


def _macd_cross(histogram: List[Optional[float]]) -> str:
    valid = [h for h in histogram if h is not None]
    if len(valid) < 3:
        return ""
    if valid[-1] > 0 and valid[-2] <= 0:
        return "BULLISH_CROSS"
    if valid[-1] < 0 and valid[-2] >= 0:
        return "BEARISH_CROSS"
    return ""


def _htf_bias(candles_4h: List[Any], candles_1d: List[Any]) -> str:
    c4 = [c.close for c in candles_4h]
    h4 = [c.high for c in candles_4h]
    l4 = [c.low for c in candles_4h]
    c1 = [c.close for c in candles_1d]

    score = 0.0
    e20, e50 = ema(c4, 20), ema(c4, 50)
    if e20 is not None and e50 is not None:
        score += 1.0 if e20 > e50 else -1.0
    _, direction = structure_break(h4, l4, c4, window=3)
    if direction == "BULL":
        score += 1.0
    elif direction == "BEAR":
        score -= 1.0
    e10, e20d = ema(c1, 10), ema(c1, 20)
    if e10 is not None and e20d is not None:
        score += 1.0 if e10 > e20d else -1.0

    if score > 0:
        return "BULLISH"
    if score < 0:
        return "BEARISH"
    return "NEUTRAL"


def analyze_mtf(coin_id: str) -> Optional[MTFResult]:
    """Ambil chart historis koin dan hitung konfluensi MTF.

    Returns None bila data historis tidak cukup / gagal diambil (kandidat dilewati).
    """
    try:
        chart_30d = get_market_chart(coin_id, 30)
    except MarketDataError:
        return None

    candles_1h = build_candles(chart_30d, 60)
    candles_4h = build_candles(chart_30d, 240)
    candles_1d = build_candles(chart_30d, 1440)
    if len(candles_1h) < 40 or len(candles_4h) < 20 or len(candles_1d) < 20:
        return None

    candles_15m: List[Any] = []
    try:
        candles_15m = build_candles(get_market_chart(coin_id, 2), 15)
    except MarketDataError:
        pass  # 15M opsional; analisis tetap jalan dengan LTF 1H

    o1, h1, l1, c1, v1 = _candle_arrays(candles_1h)
    o15, h15, l15, c15, v15 = _candle_arrays(candles_15m)

    price = c1[-1]
    atr_1h = atr(h1, l1, c1)

    ht_bias = _htf_bias(candles_4h, candles_1d)

    bos_kind, bos_direction = structure_break(h1, l1, c1, window=3)

    ob_bull = order_block(o1, h1, l1, c1, "BULL")
    ob_bear = order_block(o1, h1, l1, c1, "BEAR")
    ob_bullish = bool(ob_bull and price > ob_bull[1])
    ob_bearish = bool(ob_bear and price < ob_bear[1])

    support, resistance = nearest_levels(h1, l1, c1)
    near_support = bool(
        support is not None and atr_1h is not None and price - support <= atr_1h * 1.0
    )
    near_resistance = bool(
        resistance is not None and atr_1h is not None and resistance - price <= atr_1h * 1.0
    )

    demand, supply = None, None
    if atr_1h:
        demand, supply = demand_supply_zones(o1, h1, l1, c1, atr_1h)
    demand_zone = bool(demand is not None and price >= demand[1] - (atr_1h or 0) * 0.5)
    supply_zone = bool(supply is not None and price <= supply[0] + (atr_1h or 0) * 0.5)

    _, _, hist = macd(c1)
    macd_cross = _macd_cross(hist)

    rsi_value = rsi(c1)
    rsi_series_1h = rsi_series(c1)
    rsi_div = rsi_divergence(c1, [r if r is not None else 50.0 for r in rsi_series_1h])
    rsi_bull_aligned = rsi_div == "BULLISH_DIV" or (rsi_value is not None and rsi_value < 35)
    rsi_bear_aligned = rsi_div == "BEARISH_DIV" or (rsi_value is not None and rsi_value > 65)

    whale_up = volume_spike(v1, WHALE_VOLUME_MULT) and len(c1) >= 2 and c1[-1] > c1[-2]
    whale_down = volume_spike(v1, WHALE_VOLUME_MULT) and len(c1) >= 2 and c1[-1] < c1[-2]
    vol_ratio = volume_ratio(v1)

    bull_points, bear_points = 0.0, 0.0
    bull_reasons: List[str] = []
    bear_reasons: List[str] = []

    if ht_bias == "BULLISH":
        bull_points += 1.5
        bull_reasons.append("HTF bias bullish (4H/1D)")
    elif ht_bias == "BEARISH":
        bear_points += 1.5
        bear_reasons.append("HTF bias bearish (4H/1D)")

    if bos_direction == "BULL":
        bull_points += 1.0
        bull_reasons.append(f"SMC: {bos_kind} bullish (LTF)")
    elif bos_direction == "BEAR":
        bear_points += 1.0
        bear_reasons.append(f"SMC: {bos_kind} bearish (LTF)")
    if ob_bullish:
        bull_points += 1.0
        bull_reasons.append("SMC: bullish Order Block bertahan")
    if ob_bearish:
        bear_points += 1.0
        bear_reasons.append("SMC: bearish Order Block bertahan")

    if demand_zone:
        bull_points += 0.5
        bull_reasons.append("S&D: harga di Demand Zone")
    if supply_zone:
        bear_points += 0.5
        bear_reasons.append("S&D: harga di Supply Zone")
    if near_support and support is not None:
        bull_points += 0.5
        bull_reasons.append(f"S&R: dekat Support {support:.5g}")
    if near_resistance and resistance is not None:
        bear_points += 0.5
        bear_reasons.append(f"S&R: dekat Resistance {resistance:.5g}")

    if macd_cross == "BULLISH_CROSS":
        bull_points += 1.0
        bull_reasons.append("MACD bullish crossover")
    elif macd_cross == "BEARISH_CROSS":
        bear_points += 1.0
        bear_reasons.append("MACD bearish crossover")
    if rsi_div == "BULLISH_DIV":
        bull_points += 1.0
        bull_reasons.append("RSI bullish divergence")
    elif rsi_div == "BEARISH_DIV":
        bear_points += 1.0
        bear_reasons.append("RSI bearish divergence")
    if rsi_value is not None:
        if rsi_value < 35:
            bull_points += 0.5
            bull_reasons.append(f"RSI {rsi_value:.0f} mendekati oversold")
        elif rsi_value > 65:
            bear_points += 0.5
            bear_reasons.append(f"RSI {rsi_value:.0f} mendekati overbought")

    if whale_up:
        bull_points += 0.5
        bull_reasons.append("Whale Spike volume (kenaikan)")
    elif whale_down:
        bear_points += 0.5
        bear_reasons.append("Whale Spike volume (penurunan)")

    ltf = "1H/15M" if candles_15m else "1H"

    return MTFResult(
        coin_id=coin_id,
        ht_bias=ht_bias,
        bos_kind=bos_kind,
        bos_direction=bos_direction,
        ob_bullish=ob_bullish,
        ob_bearish=ob_bearish,
        support=support,
        resistance=resistance,
        near_support=near_support,
        near_resistance=near_resistance,
        demand_zone=demand_zone,
        supply_zone=supply_zone,
        macd_cross=macd_cross,
        rsi_value=rsi_value,
        rsi_div=rsi_div,
        rsi_bull_aligned=rsi_bull_aligned,
        rsi_bear_aligned=rsi_bear_aligned,
        whale_bull=whale_up,
        whale_bear=whale_down,
        volume_ratio=vol_ratio,
        atr_1h=atr_1h,
        bull_points=bull_points,
        bear_points=bear_points,
        bull_reasons=bull_reasons,
        bear_reasons=bear_reasons,
        ltf=ltf,
    )


def _candle_arrays(candles: List[Any]) -> Tuple[List[float], List[float], List[float], List[float], List[float]]:
    opens = [c.open for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]
    return opens, highs, lows, closes, volumes


# ---------------------------------------------------------------------------
# Gabungan skor + Confluence Checklist
# ---------------------------------------------------------------------------


def build_checklist(action: str, mtf: MTFResult) -> Dict[str, Tuple[int, int]]:
    """Checklist konfluensi 4 kategori, diselaraskan dengan arah sinyal."""
    d_bull = action == ACTION_BUY
    d_bear = action == ACTION_SELL

    def aligned(bull_ok: bool, bear_ok: bool) -> int:
        if d_bull and bull_ok:
            return 1
        if d_bear and bear_ok:
            return 1
        return 0

    smc = aligned(mtf.bos_direction == "BULL", mtf.bos_direction == "BEAR") + aligned(
        mtf.ob_bullish, mtf.ob_bearish
    )
    sd = aligned(mtf.demand_zone, mtf.supply_zone) + aligned(mtf.near_support, mtf.near_resistance)
    macd_rsi = aligned(mtf.macd_cross == "BULLISH_CROSS", mtf.macd_cross == "BEARISH_CROSS") + aligned(
        mtf.rsi_bull_aligned, mtf.rsi_bear_aligned
    )
    whale = aligned(mtf.whale_bull, mtf.whale_bear)

    return {
        "SMC/OB": (smc, 2),
        "S&D/S&R": (sd, 2),
        "MACD/RSI": (macd_rsi, 2),
        "Whale/Vol": (whale, 1),
    }


def build_final_signal(quick: Signal, mtf: MTFResult) -> Signal:
    """Gabungkan skor quick dengan konfluensi MTF menjadi sinyal final."""
    total = quick.score + (mtf.bull_points - mtf.bear_points)

    if total >= BUY_THRESHOLD:
        action = ACTION_BUY
    elif total <= SELL_THRESHOLD:
        action = ACTION_SELL
    else:
        action = ACTION_NEUTRAL

    checklist = build_checklist(action, mtf)
    aligned_total = sum(ok for ok, _ in checklist.values())
    total_checks = sum(total for _, total in checklist.values())

    if action != ACTION_NEUTRAL and aligned_total < CONFLUENCE_MIN:
        action = ACTION_NEUTRAL

    if action == ACTION_BUY:
        reasons = list(mtf.bull_reasons)
    elif action == ACTION_SELL:
        reasons = list(mtf.bear_reasons)
    else:
        reasons = (
            list(mtf.bull_reasons + mtf.bear_reasons)
            if mtf.bull_reasons or mtf.bear_reasons
            else list(quick.reasons)
        )

    if total_checks > 0:
        confidence = int(round(50 + aligned_total / total_checks * 45))
    else:
        confidence = 55 + int(abs(total) * 5)
    confidence = max(45, min(95, confidence))

    sl, tp1, tp2 = _atr_levels(quick.price, mtf.atr_1h or 0.0, action)

    return Signal(
        coin_id=quick.coin_id,
        symbol=quick.symbol,
        name=quick.name,
        price=quick.price,
        price_change_24h=quick.price_change_24h,
        score=total,
        action=action,
        confidence=confidence,
        reasons=reasons,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
        atr_value=mtf.atr_1h or 0.0,
        ht_bias=mtf.ht_bias,
        ltf=mtf.ltf,
        checklist=checklist,
    )


def rank_signals(coins: List[Dict[str, Any]]) -> List[Signal]:
    """Shortlist quick-scan -> deep scan MTF -> TOP-`TOP_SIGNALS` sinyal.

    Bila deep scan gagal total (mis. kuota API habis), fallback ke hasil
    quick-scan agar bot tetap mengirim.
    """
    percentiles = _turnover_percentiles(coins)
    quick_signals: List[Signal] = []
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
        quick_signals.append(build_signal(coin, percentiles.get(coin["id"])))

    quick_signals.sort(key=lambda s: abs(s.score), reverse=True)
    shortlist = quick_signals[:MTF_SCAN_LIMIT]

    final_signals: List[Signal] = []
    for quick in shortlist:
        mtf = analyze_mtf(quick.coin_id)
        if mtf is None:
            continue
        final_signals.append(build_final_signal(quick, mtf))

    final_signals.sort(key=lambda s: abs(s.score), reverse=True)
    result = final_signals[:TOP_SIGNALS]
    if not result:
        return quick_signals[:TOP_SIGNALS]
    return result


# ---------------------------------------------------------------------------
# Format pesan
# ---------------------------------------------------------------------------


def _format_price(value: float) -> str:
    if value >= 1000:
        return f"${value:,.0f}"
    if value >= 1:
        return f"${value:,.2f}"
    return f"${value:.6f}"


def signal_levels(sig: Signal) -> tuple:
    """Level SL/TP sinyal (dipakai evaluasi history)."""
    return sig.sl, sig.tp1, sig.tp2


def _signal_lines(sig: Signal, number: int) -> List[str]:
    sl_tag = f"ATR {ATR_SL_MULT:.1f}x" if sig.atr_value > 0 else "8%"
    lines = [
        f"{number}. <b>#{sig.symbol}</b> — {sig.action} ({sig.confidence}%)",
        f"🧭 HTF Bias: <b>{sig.ht_bias or '-'}</b> · LTF: {sig.ltf}",
        f"🔑 Entry: <b>{_format_price(sig.price)}</b>",
        f"🪓 SL: <b>{_format_price(sig.sl)}</b> ({sl_tag})",
        f"💰 TP1: <b>{_format_price(sig.tp1)}</b> (ATR {ATR_TP1_MULT:.1f}x)" if sig.atr_value > 0
        else f"💰 TP1: <b>{_format_price(sig.tp1)}</b> (5%)",
        f"💰 TP2: <b>{_format_price(sig.tp2)}</b> (ATR {ATR_TP2_MULT:.1f}x)" if sig.atr_value > 0
        else f"💰 TP2: <b>{_format_price(sig.tp2)}</b> (10%)",
        "",
        "🧩 <b>CONFLUENCE CHECKLIST</b>",
    ]
    for category in CHECKLIST_CATEGORIES:
        aligned, total = sig.checklist.get(category, (0, 0))
        mark = "✅" if aligned == total else ("⚠️" if aligned > 0 else "❌")
        lines.append(f"  {mark} {category:<10}: {aligned}/{total}")
    lines.append("")
    lines.append("📝 Note:")
    if sig.reasons:
        lines.extend(f"   - {reason}" for reason in sig.reasons)
    else:
        lines.append("   - —")
    lines.append("---")
    return lines


def format_message(
    signals: List[Signal],
    timestamp: str,
    total_scanned: int,
    session_label: str = "",
    eval_text: str = "",
) -> str:
    """Rangkai pesan Telegram: evaluasi (opsional) + daftar sinyal + checklist."""
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
        "<b>📊 Day Trading Signals</b>",
        f"🕐 {timestamp}" + (f" · {session_label}" if session_label else ""),
        f"🔎 Dipindai: {total_scanned} koin · HTF 4H/1D · LTF 1H/15M",
        "",
    ]

    if eval_text:
        lines.insert(0, eval_text + "\n")

    number = 1
    if buys:
        lines.append("<b>📈 SINYAL LONG (BUY)</b>")
        lines.append("")
        for sig in buys:
            lines.extend(_signal_lines(sig, number))
            number += 1

    if sells:
        lines.append("<b>📉 SINYAL SHORT (SELL)</b>")
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
