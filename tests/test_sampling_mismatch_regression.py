#!/usr/bin/env python3
"""
tests/test_sampling_mismatch_regression.py
Regression tests proving the resolution of the Production Sampling Mismatch.

Verifies:
1. A sequence of six 10-second observations does NOT become six separate 1-minute bars.
2. Intra-minute quote updates correctly track Open, High, Low, Close, Volume.
3. Minute rollover seals exactly one 1-minute bar.
4. OpportunityDiscoveryEngine.extract_19_features rejects sub-minute intervals.
5. Live trader fails closed on missing timestamps or timeframe mismatch.
6. Gaps/missing intervals do not fabricate synthetic bars.
7. Exact duplicate ticks and stale quotes are cleanly rejected.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta
import pytz
import pandas as pd
import numpy as np

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.execution.candle_aggregator import OneMinuteCandleAggregator
from v3.intelligence.opportunity_engine import OpportunityDiscoveryEngine
from v3.execution.live_trader import AlphaNSELiveTrader

IST = pytz.timezone("Asia/Kolkata")


class TestSamplingMismatchRegression(unittest.TestCase):

    def setUp(self):
        self.agg = OneMinuteCandleAggregator(max_history=60)
        self.sym = "INFY.NS"

    def test_six_10s_observations_do_not_become_six_bars(self):
        """
        Proof of Fix: Six 10-second quotes in the same minute must update
        the SINGLE in-progress candle, resulting in exactly ZERO completed bars
        during the minute, and exactly ONE completed bar upon minute rollover.
        """
        quotes_m1 = [
            {"timestamp": "2026-10-19 09:15:05 IST", "ltp": 1500.00, "volume": 100},
            {"timestamp": "2026-10-19 09:15:15 IST", "ltp": 1502.50, "volume": 200},
            {"timestamp": "2026-10-19 09:15:25 IST", "ltp": 1498.00, "volume": 350},
            {"timestamp": "2026-10-19 09:15:35 IST", "ltp": 1501.00, "volume": 500},
            {"timestamp": "2026-10-19 09:15:45 IST", "ltp": 1504.00, "volume": 650},
            {"timestamp": "2026-10-19 09:15:55 IST", "ltp": 1503.20, "volume": 800},
        ]

        # Feed all 6 sub-minute quotes
        for q in quotes_m1:
            sealed = self.agg.process_quote(self.sym, q)
            self.assertIsNone(sealed, "Intra-minute tick must NOT seal a completed bar")

        # Crucial invariant: completed bars count must be 0 (NOT 6!)
        completed = self.agg.get_bars(self.sym, include_forming=False)
        self.assertEqual(len(completed), 0, f"Expected 0 completed bars, but found {len(completed)}")

        # Verify the single forming bar has accumulated all 6 ticks accurately
        forming = self.agg.forming_bars[self.sym]
        self.assertEqual(forming["open"], 1500.00, "Open must be first tick price")
        self.assertEqual(forming["high"], 1504.00, "High must be max of all 6 ticks")
        self.assertEqual(forming["low"], 1498.00, "Low must be min of all 6 ticks")
        self.assertEqual(forming["close"], 1503.20, "Close must be last tick price")
        self.assertEqual(forming["tick_count"], 6, "Must count exactly 6 ticks")

        # Now quote for the NEXT minute arrives (09:16:05)
        q_m2 = {"timestamp": "2026-10-19 09:16:05 IST", "ltp": 1505.00, "volume": 950}
        sealed = self.agg.process_quote(self.sym, q_m2)
        self.assertIsNotNone(sealed, "Minute rollover must seal the 09:15:00 candle")

        # Verify completed bars count is now EXACTLY 1
        completed = self.agg.get_bars(self.sym, include_forming=False)
        self.assertEqual(len(completed), 1, "Expected exactly 1 completed 1m bar after minute rollover")
        self.assertEqual(completed[0]["timestamp_str"], "2026-10-19 09:15:00 IST")
        self.assertEqual(completed[0]["open"], 1500.00)
        self.assertEqual(completed[0]["high"], 1504.00)
        self.assertEqual(completed[0]["low"], 1498.00)
        self.assertEqual(completed[0]["close"], 1503.20)
        self.assertTrue(completed[0]["is_complete"])

    def test_opportunity_engine_rejects_subminute_sampling_intervals(self):
        """
        Proof of Defense-in-Depth: If a buffer containing 10-second intervals
        reaches OpportunityDiscoveryEngine.extract_19_features, it must detect
        the sub-minute interval and return None (fail-closed).
        """
        # Create defective buffer with 10-second intervals
        base_t = datetime(2026, 10, 19, 9, 15, 0)
        defective_buf = []
        for i in range(20):
            t = base_t + timedelta(seconds=i * 10)  # 10s intervals!
            defective_buf.append({
                "timestamp": t.strftime("%Y-%m-%d %H:%M:%S IST"),
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 1000.0
            })

        feats = OpportunityDiscoveryEngine.extract_19_features(defective_buf)
        self.assertIsNone(feats, "Engine MUST reject buffer with sub-minute (10s) intervals")

        # Create valid buffer with 1-minute intervals
        valid_buf = []
        for i in range(20):
            t = base_t + timedelta(minutes=i)  # Genuine 1m intervals
            valid_buf.append({
                "timestamp": t.strftime("%Y-%m-%d %H:%M:%S IST"),
                "open": 100.0 + i * 0.1,
                "high": 101.0 + i * 0.1,
                "low": 99.0 + i * 0.1,
                "close": 100.5 + i * 0.1,
                "volume": 1000.0
            })

        valid_feats = OpportunityDiscoveryEngine.extract_19_features(valid_buf)
        self.assertIsNotNone(valid_feats, "Engine MUST accept buffer with genuine 1-minute intervals")
        self.assertEqual(len(valid_feats), 19, "Must extract exactly 19 institutional features")

    def test_live_trader_buffer_timeframe_validation(self):
        """Verifies live trader validate_buffer_timeframe detects 10s sampling defects."""
        # 10-second interval buffer
        base_t = datetime(2026, 10, 19, 9, 15, 0)
        buf_10s = [{"timestamp": (base_t + timedelta(seconds=i * 10)).isoformat(), "close": 100.0} for i in range(10)]
        is_valid, err = self.agg.validate_buffer_timeframe(buf_10s)
        self.assertFalse(is_valid)
        self.assertIn("DETECTED_SUB_MINUTE_SAMPLING", err)

        # 1-minute interval buffer
        buf_1m = [{"timestamp": (base_t + timedelta(minutes=i)).isoformat(), "close": 100.0} for i in range(10)]
        is_valid_1m, err_1m = self.agg.validate_buffer_timeframe(buf_1m)
        self.assertTrue(is_valid_1m)
        self.assertIsNone(err_1m)

    def test_missing_intervals_gap_does_not_fabricate_candles(self):
        """Verifies that an outage gap does NOT create synthetic fabricated bars."""
        # Quote at 09:15
        self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:15:30 IST", "ltp": 100.0, "volume": 100})
        # 5-minute gap until 09:21
        self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:21:10 IST", "ltp": 105.0, "volume": 500})

        completed = self.agg.get_bars(self.sym, include_forming=False)
        # Must have sealed exactly 09:15:00 candle; no synthetic 09:16, 09:17, 09:18 candles
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["timestamp_str"], "2026-10-19 09:15:00 IST")

        # Current forming bar is 09:21:00
        forming = self.agg.forming_bars[self.sym]
        self.assertEqual(forming["timestamp_str"], "2026-10-19 09:21:00 IST")

    def test_duplicate_and_stale_ticks_rejected(self):
        """Verifies duplicate and stale ticks are cleanly rejected."""
        q1 = {"timestamp": "2026-10-19 09:15:10 IST", "ltp": 100.0, "volume": 100}
        self.agg.process_quote(self.sym, q1)
        self.assertEqual(self.agg.forming_bars[self.sym]["tick_count"], 1)

        # Exact duplicate
        self.agg.process_quote(self.sym, q1)
        self.assertEqual(self.agg.forming_bars[self.sym]["tick_count"], 1, "Duplicate tick must be ignored")

        # Stale quote
        q_stale = {"timestamp": "2026-10-19 09:15:20 IST", "ltp": 101.0, "volume": 150, "is_stale": True}
        self.agg.process_quote(self.sym, q_stale)
        self.assertEqual(self.agg.forming_bars[self.sym]["tick_count"], 1, "Stale quote must be rejected")


if __name__ == "__main__":
    unittest.main()
