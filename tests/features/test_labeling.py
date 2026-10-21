"""
Unit Tests for Raw Execution Price Labeling & Intraday Horizon Masking.
Verifies:
  1. Forward returns strictly use raw prices: ln(P_{raw, t+H} / P_{raw, t}).
  2. Cross-day observations are masked out with NaN (no overnight forward leakage).
  3. Directional hurdle target logic (-1, 0, 1).
"""

import unittest
import numpy as np
import pandas as pd
from v2.features.labeling import IntradayLabeler


class TestIntradayLabeler(unittest.TestCase):

    def setUp(self):
        # 2 sessions with 10 bars each
        day1 = pd.date_range("2026-09-01 09:15", periods=10, freq="5min")
        day2 = pd.date_range("2026-09-02 09:15", periods=10, freq="5min")
        timestamps = list(day1) + list(day2)

        raw_closes = [
            100.0, 102.0, 101.0, 103.0, 105.0, 104.0, 106.0, 108.0, 110.0, 112.0,  # Day 1
            120.0, 122.0, 121.0, 123.0, 125.0, 124.0, 126.0, 128.0, 130.0, 132.0   # Day 2
        ]

        self.df = pd.DataFrame({
            "timestamp": timestamps,
            "symbol": ["RELIANCE.NS"] * 20,
            "raw_close": raw_closes
        })

    def test_raw_forward_return_calculation(self):
        """Verify H=1 (5m) forward log return from raw prices."""
        labeler = IntradayLabeler(horizons=[1, 2, 3], cost_hurdle_bps=15.0)
        labeled = labeler.construct_forward_labels(self.df)

        # Bar 0: raw_close=100.0, next=102.0 -> ln(102/100) = 0.0198026
        expected_ret_0 = np.log(102.0 / 100.0)
        self.assertAlmostEqual(labeled["target_return_5m"].iloc[0], expected_ret_0, places=6)

        # Bar 0 for H=2 (10m): next 2 bars = 101.0 -> ln(101/100)
        expected_ret_10m = np.log(101.0 / 100.0)
        self.assertAlmostEqual(labeled["target_return_10m"].iloc[0], expected_ret_10m, places=6)

    def test_cross_session_masking(self):
        """Verify that the last bar of Day 1 has NaN target return (cannot peek into Day 2)."""
        labeler = IntradayLabeler(horizons=[1, 2, 3], cost_hurdle_bps=15.0)
        labeled = labeler.construct_forward_labels(self.df)

        # Day 1 index 9 is the last bar of Day 1
        self.assertTrue(np.isnan(labeled["target_return_5m"].iloc[9]), "Last bar of Day 1 must be NaN for 5m target")
        self.assertTrue(np.isnan(labeled["target_return_10m"].iloc[9]), "Last bar of Day 1 must be NaN for 10m target")
        self.assertTrue(np.isnan(labeled["target_return_10m"].iloc[8]), "Second to last bar of Day 1 must be NaN for 10m target")
        self.assertTrue(np.isnan(labeled["target_return_15m"].iloc[7]), "Third to last bar of Day 1 must be NaN for 15m target")

    def test_directional_hurdle_labels(self):
        """Verify directional hurdle classification (+1, 0, -1)."""
        labeler = IntradayLabeler(horizons=[1], cost_hurdle_bps=15.0)  # 15 bps = 0.0015
        labeled = labeler.construct_forward_labels(self.df)

        # Bar 0 return is ~1.98% > 0.15% -> label must be +1
        self.assertEqual(labeled["target_direction_5m"].iloc[0], 1)

        # Bar 1 return: 102 -> 101 = ln(101/102) = -0.00985 < -0.0015 -> label must be -1
        self.assertEqual(labeled["target_direction_5m"].iloc[1], -1)


if __name__ == "__main__":
    unittest.main()
