"""Tes unit untuk data/history.py: penyimpanan & evaluasi per sesi (PAGI/MALAM)."""

import os
import tempfile
import unittest

import data.history as history
from signals.engine import ACTION_BUY, ACTION_SELL, Signal


def _signal(symbol, coin_id, action=ACTION_BUY, price=100.0, sl=None, tp1=None, tp2=None):
    return Signal(
        coin_id=coin_id,
        symbol=symbol,
        name=symbol,
        price=price,
        price_change_24h=0.0,
        score=4.0,
        action=action,
        confidence=80,
        sl=sl if sl is not None else price * 0.92,
        tp1=tp1 if tp1 is not None else price * 1.05,
        tp2=tp2 if tp2 is not None else price * 1.10,
    )


class SessionTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        history.HISTORY_FILE = os.path.join(self._tmp.name, "history.json")

    def tearDown(self):
        self._tmp.cleanup()


class TestSessions(SessionTestCase):
    def test_append_and_load_by_session(self):
        history.append_signals([_signal("BTC", "bitcoin")], session=history.SESSION_PAGI)
        entry = history.load_last_entry(session=history.SESSION_MALAM)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["session"], history.SESSION_PAGI)
        self.assertEqual(entry["signals"][0]["symbol"], "BTC")

    def test_same_session_overwrites(self):
        history.append_signals([_signal("BTC", "bitcoin", price=100.0)], session=history.SESSION_PAGI)
        history.append_signals([_signal("ETH", "ethereum", price=50.0)], session=history.SESSION_PAGI)
        entries = history.load_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["signals"][0]["symbol"], "ETH")

    def test_malam_evaluates_pagi(self):
        history.append_signals([_signal("BTC", "bitcoin", price=100.0)], session=history.SESSION_PAGI)
        price_map = {
            "bitcoin": {"current_price": 112.0, "high_24h": 115.0, "low_24h": 99.0}
        }
        entry = history.load_last_entry(session=history.SESSION_MALAM)
        evals = history.evaluate_entry(entry, price_map)
        self.assertEqual(evals[0].result, history.RESULT_TP2)

    def test_pagi_evaluates_previous_day_malam(self):
        history.append_signals([_signal("BTC", "bitcoin", price=100.0)], session=history.SESSION_MALAM)
        entry = history.load_last_entry(session=history.SESSION_PAGI)
        self.assertEqual(entry["session"], history.SESSION_MALAM)

    def test_old_entry_without_session_defaults_pagi(self):
        history._save_entries(
            [
                {
                    "date": "2026-08-07",
                    "signals": [
                        {"coin_id": "x", "symbol": "X", "action": "BUY", "entry": 1, "sl": 0.9, "tp1": 1.05, "tp2": 1.1}
                    ],
                }
            ]
        )
        entry = history.load_last_entry(session=history.SESSION_MALAM)
        self.assertEqual(entry.get("session", history.DEFAULT_SESSION), history.DEFAULT_SESSION)


if __name__ == "__main__":
    unittest.main()
