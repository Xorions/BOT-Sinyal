"""Penyimpanan & evaluasi performa sinyal antar sesi (performance tracking).

Bot berjalan 2x sehari (Sesi Pagi 07:00 WIB dan Sesi Malam 19:00 WIB). Sinyal
yang dikirim disimpan di `data/history.json` dengan kunci (tanggal, sesi).
Setiap sesi HARUS dievaluasi pada sesi berikutnya: sesi Malam mengevaluasi
sinyal sesi Pagi (hari yang sama), sesi Pagi mengevaluasi sinyal sesi Malam
(hari sebelumnya).

Evaluasi membandingkan Entry/SL/TP dengan harga terkini (atau high/low 24j):
HIT TP1, HIT TP2, HIT SL, atau FLOATING. Prioritas hasil: HIT TP2 > HIT TP1 >
HIT SL > FLOATING karena urutan pencapaian level tak bisa diketahui dari
high/low saja.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from signals.engine import ACTION_BUY, ACTION_SELL, Signal, signal_levels

HISTORY_FILE = "data/history.json"

SESSION_PAGI = "PAGI"
SESSION_MALAM = "MALAM"
SESSION_ORDER = {SESSION_PAGI: 0, SESSION_MALAM: 1}
DEFAULT_SESSION = SESSION_PAGI
WIB_OFFSET = timedelta(hours=7)

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

_SESSION_LABEL = {
    SESSION_PAGI: "Pagi (07:00 WIB)",
    SESSION_MALAM: "Malam (19:00 WIB)",
}


def _now_wib() -> datetime:
    return datetime.now(timezone(WIB_OFFSET))


def current_session() -> str:
    """Sesi saat ini berdasarkan jam lokal WIB (07:00 = PAGI, 19:00 = MALAM)."""
    return SESSION_PAGI if _now_wib().hour < 12 else SESSION_MALAM


def session_label(session: str) -> str:
    return _SESSION_LABEL.get(session, session or DEFAULT_SESSION)


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


def append_signals(signals: List[Signal], session: Optional[str] = None) -> None:
    """Simpan sinyal BUY/SELL yang dikirim sesi ini ke history.

    Satu kunci (tanggal, sesi) selalu menghasilkan satu evaluasi — entri dengan
    kunci yang sama ditimpa bila bot dijalankan ulang di sesi yang sama.
    """
    session = session or current_session()
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
    now = _now_wib()
    date = now.strftime("%Y-%m-%d")
    entries = [
        e
        for e in load_entries()
        if not (e.get("date") == date and e.get("session", DEFAULT_SESSION) == session)
    ]
    entries.append(
        {
            "date": date,
            "session": session,
            "saved_at": now.isoformat(timespec="seconds"),
            "signals": records,
        }
    )
    _save_entries(entries)


def _entry_key(entry: Dict[str, Any]) -> tuple:
    return (
        str(entry.get("date", "")),
        SESSION_ORDER.get(entry.get("session", DEFAULT_SESSION), -1),
    )


def load_last_entry(session: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Entri sesi terakhir yang BUKAN sesi berjalan (untuk dievaluasi)."""
    session = session or current_session()
    today = _now_wib().strftime("%Y-%m-%d")
    candidates = [
        e
        for e in load_entries()
        if not (e.get("date") == today and e.get("session", DEFAULT_SESSION) == session)
    ]
    if not candidates:
        return None
    candidates.sort(key=_entry_key, reverse=True)
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
    """Ringkasan evaluasi sinyal sesi sebelumnya, diletakkan di atas pesan."""
    if not entry:
        return "<b>📊 EVALUASI SINYAL SESI SEBELUMNYA</b>\n🗓️ Belum ada data sesi sebelumnya."

    date_display = str(entry.get("date", ""))
    try:
        date_display = datetime.strptime(date_display, "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        pass

    prev_session = str(entry.get("session", DEFAULT_SESSION))
    evals = evaluate_entry(entry, price_map)
    counts = {result: 0 for result in RESULTS_ORDER}
    for ev in evals:
        counts[ev.result] = counts.get(ev.result, 0) + 1

    lines = [
        "<b>📊 EVALUASI SINYAL SESI SEBELUMNYA</b>",
        f"🗓️ {date_display} · Sesi {session_label(prev_session)}",
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
