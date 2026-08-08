"""Tes unit untuk signals/indicators.py (tanpa network)."""

import unittest

from signals.indicators import (
    atr,
    ema,
    ema_series,
    macd,
    rsi,
    rsi_divergence,
    rsi_series,
    sma,
    structure_break,
    volume_ratio,
    volume_spike,
)


class TestSmaEma(unittest.TestCase):
    def test_sma(self):
        self.assertAlmostEqual(sma([1, 2, 3, 4], 4), 2.5)
        self.assertIsNone(sma([1, 2], 4))

    def test_ema_last(self):
        values = [float(i) for i in range(1, 51)]
        self.assertIsNotNone(ema(values, 10))
        self.assertGreater(ema(values, 5), ema(values, 30))  # tren naik

    def test_ema_series_padding(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        series = ema_series(values, 3)
        self.assertEqual(len(series), len(values))
        self.assertTrue(all(v is None for v in series[:2]))
        self.assertIsNotNone(series[-1])


class TestRsi(unittest.TestCase):
    def test_rsi_overbought_on_uptrend(self):
        values = [float(i) for i in range(1, 40)]
        self.assertGreater(rsi(values), 70)

    def test_rsi_oversold_on_downtrend(self):
        values = [float(40 - i) for i in range(40)]
        self.assertLess(rsi(values), 30)

    def test_rsi_series_aligned(self):
        values = [float(i) for i in range(1, 30)]
        series = rsi_series(values)
        self.assertEqual(len(series), len(values))
        self.assertIsNone(series[0])
        self.assertIsNotNone(series[-1])


class TestMacd(unittest.TestCase):
    def test_macd_uptrend_cross(self):
        # Datar lalu akselerasi naik -> histogram MACD jadi jelas positif
        values = [100.0] * 50 + [100, 101, 103, 106, 110, 115, 121, 128]
        _, _, hist = macd(values)
        valid = [h for h in hist if h is not None]
        self.assertGreater(valid[-1], 0)


class TestAtr(unittest.TestCase):
    def test_atr_positive(self):
        highs = [10, 11, 12, 13, 12, 11, 12, 13, 14, 15, 14, 13, 14, 15, 16, 17]
        lows = [9, 10, 11, 12, 11, 10, 11, 12, 13, 14, 13, 12, 13, 14, 15, 16]
        closes = [9.5, 10.5, 11.5, 12.5, 11.5, 10.5, 11.5, 12.5, 13.5, 14.5, 13.5, 12.5, 13.5, 14.5, 15.5, 16.5]
        value = atr(highs, lows, closes, 14)
        self.assertIsNotNone(value)
        self.assertGreater(value, 0)


class TestStructure(unittest.TestCase):
    def test_bullish_bos(self):
        # HH/HL lalu bar terakhir break di atas swing high terakhir (BOS)
        closes = [10.0, 10.2, 10.5, 10.3, 10.0, 10.3, 10.6, 10.9, 11.2, 10.9, 10.6, 10.7, 10.9, 11.5]
        highs = [10.1, 10.3, 10.6, 10.4, 10.2, 10.5, 10.7, 11.0, 11.3, 11.1, 10.8, 10.9, 11.1, 11.8]
        lows = [9.9, 10.0, 10.2, 10.1, 9.9, 10.2, 10.4, 10.6, 10.8, 10.7, 10.4, 10.6, 10.7, 11.2]
        kind, direction = structure_break(highs, lows, closes, window=2)
        self.assertEqual(direction, "BULL")
        self.assertEqual(kind, "BOS")

    def test_bearish_choch(self):
        # Tren naik (HH/HL) lalu bar terakhir break di bawah swing low = CHoCH bearish
        closes = [10.0, 10.2, 10.5, 10.3, 10.0, 10.3, 10.6, 10.9, 11.2, 10.9, 10.6, 10.7, 10.5, 9.6]
        highs = [10.1, 10.3, 10.6, 10.4, 10.2, 10.5, 10.7, 11.0, 11.3, 11.1, 10.9, 10.8, 10.6, 9.8]
        lows = [9.9, 10.0, 10.2, 10.1, 9.9, 10.2, 10.4, 10.6, 10.8, 10.7, 10.4, 10.6, 10.5, 9.4]
        kind, direction = structure_break(highs, lows, closes, window=2)
        self.assertEqual(direction, "BEAR")
        self.assertEqual(kind, "CHoCH")


class TestDivergenceVolume(unittest.TestCase):
    def test_bullish_divergence(self):
        # Harga membuat LL (index 5 -> 11) tapi RSI membuat HL
        prices = [10.5, 10.0, 9.6, 9.8, 9.7, 9.4, 9.5, 9.6, 9.3, 9.5, 9.4, 8.9, 9.0, 9.2]
        rsi_vals = [52, 48, 44, 43, 41, 38, 40, 41, 39, 40, 39, 46, 47, 48]
        self.assertEqual(rsi_divergence(prices, rsi_vals, window=2), "BULLISH_DIV")

    def test_volume_spike(self):
        volumes = [100.0] * 22 + [1000.0]
        self.assertTrue(volume_spike(volumes, multiplier=2.5, period=20))

    def test_volume_ratio(self):
        volumes = [100.0] * 22 + [500.0]
        ratio = volume_ratio(volumes, period=20)
        self.assertAlmostEqual(ratio, 5.0)


if __name__ == "__main__":
    unittest.main()
