"""Penyimpanan & evaluasi performa sinyal kemarin (performance tracking).

Sinyal yang dikirim hari ini disimpan di `data/history.json`. Sebelum mengirim
Daily Briefing, bot membaca entri kemarin, membandingkan Entry/SL/TP dengan
harga terkini (atau high/low 24j) untuk menentukan hasil evaluasi:
HIT TP1, HIT TP2, HIT SL, atau FLOATING.

Prioritas hasil: HIT TP2 > HIT TP1 > HIT SL > FLOATING. Jika dalam satu hari
dua level terpenuhi (mis. TP2 dan SL), bot melaporkan level terbaik karena
urutan pencapaiannya tidak bisa diketahui dari high/low saja.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from signals.engine import ACTION_BUY, ACTION_SELL, Signal, signal_levels

HISTORY_FILE = "data/history.json"

RESULT_TP2 = "HIT TP2"
RESULT_TP1 = "HIT TP1"
RESULT_SL = "HIT SL"
RESULT_FLOATING = "FLOATING"

RESULTS_ORDER = (RESULT_TP2, RESULT_TP1, RESULT_SL, RESULT_FLOATING)

_RESULT_BADGE = {
    RESULT_TP2: "🎯",
    RESULT_TP1: "✅",
    RESULT_SL: "❌",
}


@dataclass
class Eval:
    symbol: str
    action: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    result: str
    price: float


def load_entries() -> List[Dict[str, Any]]:
    """Seluruh entri history yang tersimpan di HISTORY_FILE."""
    try:
        with open(HISTORY_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    entries = data.get("entries", [])
    return entries if isinstance(entries, list) else []


def _save_entries(entries: List[Dict[str, Any]]) -> None:
    parent = os.path.dirname(HISTORY_FILE)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = HISTORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"entries": entries}, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, HISTORY_FILE)


def append_signals(signals: List[Signal]) -> None:
    """Simpan sinyal BUY/SELL yang dikirim hari ini ke history.

    Jika bot dijalankan lebih dari sekali di hari yang sama, entri hari itu
    ditimpa sehingga satu hari selalu menghasilkan satu evaluasi.
    """
    records: List[Dict[str, Any]] = []
    for sig in signals:
        if sig.action not in (ACTION_BUY, ACTION_SELL):
            continue
        sl, tp1, tp2 = signal_levels(sig)
        records.append(
            {
                "coin_id": sig.coin_id,
                "symbol": sig.symbol,
                "name": sig.name,
                "action": sig.action,
                "entry": sig.price,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "confidence": sig.confidence,
            }
        )
    if not records:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    entries = [e for e in load_entries() if e.get("date") != today]
    entries.append(
        {
            "date": today,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "signals": records,
        }
    )
    _save_entries(entries)


def load_last_entry() -> Optional[Dict[str, Any]]:
    """Entri sinyal terakhir yang BUKAN milik hari ini (untuk dievaluasi)."""
    today = datetime.now().strftime("%Y-%m-%d")
    candidates = [e for e in load_entries() if e.get("date") != today]
    if not candidates:
        return None
    candidates.sort(key=lambda e: str(e.get("date", "")), reverse=True)
    return candidates[0]


def _evaluate_one(record: Dict[str, Any], price_info: Dict[str, float]) -> Eval:
    symbol = str(record.get("symbol", "?"))
    action = str(record.get("action", ACTION_BUY))
    entry = float(record.get("entry") or 0)
    sl = float(record.get("sl") or 0)
    tp1 = float(record.get("tp1") or 0)
    tp2 = float(record.get("tp2") or 0)
    current = float((price_info or {}).get("current_price") or 0)

    if current <= 0 or entry <= 0:
        return Eval(symbol, action, entry, sl, tp1, tp2, RESULT_FLOATING, current)

    high = float((price_info or {}).get("high_24h") or 0) or current
    low = float((price_info or {}).get("low_24h") or 0) or current

    if action == ACTION_SELL:
        if low <= tp2:
            result = RESULT_TP2
        elif low <= tp1:
            result = RESULT_TP1
        elif high >= sl:
            result = RESULT_SL
        else:
            result = RESULT_FLOATING
    else:
        if high >= tp2:
            result = RESULT_TP2
        elif high >= tp1:
            result = RESULT_TP1
        elif low <= sl:
            result = RESULT_SL
        else:
            result = RESULT_FLOATING
    return Eval(symbol, action, entry, sl, tp1, tp2, result, current)


def evaluate_entry(
    entry: Optional[Dict[str, Any]], price_map: Dict[str, Dict[str, float]]
) -> List[Eval]:
    """Evaluasi semua sinyal pada `entry` dengan peta harga terkini."""
    if not entry:
        return []
    evals: List[Eval] = []
    for record in entry.get("signals", []):
        info = price_map.get(str(record.get("coin_id", "")), {})
        evals.append(_evaluate_one(record, info))
    return evals


def _result_label(ev: Eval) -> str:
    if ev.result == RESULT_FLOATING:
        if ev.price <= 0:
            return "⏳ FLOATING (no data)"
        pct = (ev.price - ev.entry) / ev.entry * 100
        return f"⏳ FLOATING ({pct:+.1f}%)"
    level = {
        RESULT_TP2: ev.tp2,
        RESULT_TP1: ev.tp1,
        RESULT_SL: ev.sl,
    }[ev.result]
    pct = (level - ev.entry) / ev.entry * 100
    return f"{_RESULT_BADGE[ev.result]} {ev.result} ({pct:+.1f}%)"


def format_evaluation(
    entry: Optional[Dict[str, Any]], price_map: Dict[str, Dict[str, float]]
) -> str:
    """Ringkasan evaluasi sinyal kemarin, diletakkan di atas Daily Briefing."""
    if not entry:
        return "<b>📊 EVALUASI SINYAL KEMARIN</b>\n🗓️ Belum ada data sinyal kemarin."

    date_display = str(entry.get("date", ""))
    try:
        date_display = datetime.strptime(date_display, "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        pass

    evals = evaluate_entry(entry, price_map)
    counts = {result: 0 for result in RESULTS_ORDER}
    for ev in evals:
        counts[ev.result] = counts.get(ev.result, 0) + 1

    lines = [
        "<b>📊 EVALUASI SINYAL KEMARIN</b>",
        f"🗓️ {date_display}",
        (
            f"🎯 HIT TP2: {counts[RESULT_TP2]} · ✅ HIT TP1: {counts[RESULT_TP1]} · "
            f"❌ HIT SL: {counts[RESULT_SL]} · ⏳ FLOATING: {counts[RESULT_FLOATING]}"
        ),
    ]
    if not evals:
        lines.append("Tidak ada sinyal BUY/SELL untuk dievaluasi.")
        return "\n".join(lines)

    lines.append("━━━━━━━━━━━━")
    for index, ev in enumerate(evals, start=1):
        lines.append(f"{index}. #{ev.symbol} ({ev.action}) → {_result_label(ev)}")
    return "\n".join(lines)
