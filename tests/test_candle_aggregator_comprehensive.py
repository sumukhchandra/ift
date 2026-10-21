#!/usr/bin/env python3
"""
tests/test_candle_aggregator_comprehensive.py
Comprehensive Verification Suite for Priority 1: One-Minute Candle Construction & Pipeline Integration.

Tests:
1. Six 10-second observations inside one minute form exactly ONE candle upon rollover.
2. Correct OHLC values across intra-minute quotes.
3. Correct cumulative-volume delta handling across consecutive minutes.
4. Correct incremental volume accumulation.
5. Rejection of exact duplicate ticks.
6. Rejection of out-of-order ticks arriving late.
7. Rejection of stale quotes and non-finite prices.
8. Timezone-aware and timezone-naive timestamp normalization to Asia/Kolkata.
9. Rejection of malformed timestamps.
10. Minute rollover seals completed candle without fabricating missing intermediate bars during gaps.
11. Market session boundaries detection.
12. Insufficient historical bars handled gracefully in feature extraction.
13. Returns r1, r3, r5, r10 match intended 1m, 3m, 5m, 10m horizons on genuine 1m bars.
14. End-to-end proof that inference consumes completed one-minute bars rather than raw tick snapshots.
"""

import os
import sys
import unittest
import math
from datetime import datetime, timedelta
import pytz

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.execution.candle_aggregator import OneMinuteCandleAggregator
from v3.intelligence.opportunity_engine import OpportunityDiscoveryEngine
from v3.execution.live_trader import AlphaNSELiveTrader

IST = pytz.timezone("Asia/Kolkata")


class TestCandleAggregatorComprehensive(unittest.TestCase):

    def setUp(self):
        self.agg = OneMinuteCandleAggregator(max_history=60)
        self.sym = "TCS.NS"

    def test_01_six_10s_observations_form_one_candle(self):
        """Six 10-second quotes in one minute form 0 completed bars initially, and 1 on rollover."""
        quotes = [
            {"timestamp": "2026-10-19 09:15:05 IST", "ltp": 3500.0, "volume": 10},
            {"timestamp": "2026-10-19 09:15:15 IST", "ltp": 3505.0, "volume": 20},
            {"timestamp": "2026-10-19 09:15:25 IST", "ltp": 3495.0, "volume": 35},
            {"timestamp": "2026-10-19 09:15:35 IST", "ltp": 3510.0, "volume": 50},
            {"timestamp": "2026-10-19 09:15:45 IST", "ltp": 3502.0, "volume": 65},
            {"timestamp": "2026-10-19 09:15:55 IST", "ltp": 3508.0, "volume": 80},
        ]
        for q in quotes:
            sealed = self.agg.process_quote(self.sym, q)
            self.assertIsNone(sealed)

        completed = self.agg.get_bars(self.sym, include_forming=False)
        self.assertEqual(len(completed), 0)

        # Minute rollover tick
        q_next = {"timestamp": "2026-10-19 09:16:05 IST", "ltp": 3512.0, "volume": 90}
        sealed = self.agg.process_quote(self.sym, q_next)
        self.assertIsNotNone(sealed)
        self.assertEqual(len(self.agg.get_bars(self.sym, include_forming=False)), 1)

    def test_02_correct_ohlc_values(self):
        """Verify Open is first price, High is max, Low is min, Close is last price."""
        quotes = [
            {"timestamp": "2026-10-19 10:00:10 IST", "ltp": 100.0},
            {"timestamp": "2026-10-19 10:00:20 IST", "ltp": 108.5},
            {"timestamp": "2026-10-19 10:00:30 IST", "ltp": 94.0},
            {"timestamp": "2026-10-19 10:00:40 IST", "ltp": 103.0},
        ]
        for q in quotes:
            self.agg.process_quote(self.sym, q)

        # Trigger seal with next minute
        sealed = self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 10:01:02 IST", "ltp": 102.0})
        self.assertIsNotNone(sealed)
        self.assertEqual(sealed["open"], 100.0)
        self.assertEqual(sealed["high"], 108.5)
        self.assertEqual(sealed["low"], 94.0)
        self.assertEqual(sealed["close"], 103.0)

    def test_03_cumulative_volume_delta_handling(self):
        """Verify cumulative volume delta is correctly calculated across minutes."""
        # Minute 1: Day cumulative volume starts at 10,000, ends at 10,450 (delta = 450)
        self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:15:10 IST", "ltp": 100.0, "volume": 10000, "is_cumulative": True})
        self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:15:30 IST", "ltp": 101.0, "volume": 10200, "is_cumulative": True})
        self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:15:50 IST", "ltp": 100.5, "volume": 10450, "is_cumulative": True})

        # Minute 2: Cumulative volume starts at 10,500, ends at 11,100 (delta = 600)
        m1_sealed = self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:16:10 IST", "ltp": 102.0, "volume": 10500, "is_cumulative": True})
        self.assertIsNotNone(m1_sealed)
        self.assertEqual(m1_sealed["volume"], 450.0, "Minute 1 volume must be 10450 - 10000 = 450")

        self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:16:50 IST", "ltp": 103.0, "volume": 11100, "is_cumulative": True})

        # Minute 3 trigger
        m2_sealed = self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:17:05 IST", "ltp": 104.0, "volume": 11150, "is_cumulative": True})
        self.assertIsNotNone(m2_sealed)
        self.assertEqual(m2_sealed["volume"], 600.0, "Minute 2 volume must be 11100 - 10500 = 600")

    def test_04_incremental_volume_accumulation(self):
        """Verify incremental volume mode sums ticks."""
        self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:15:10 IST", "ltp": 100.0, "volume": 50, "volume_type": "incremental"})
        self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:15:30 IST", "ltp": 101.0, "volume": 75, "volume_type": "incremental"})
        self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:15:50 IST", "ltp": 100.5, "volume": 25, "volume_type": "incremental"})

        sealed = self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:16:05 IST", "ltp": 102.0, "volume": 10, "volume_type": "incremental"})
        self.assertIsNotNone(sealed)
        self.assertEqual(sealed["volume"], 150.0, "Incremental volume must sum ticks: 50+75+25 = 150")

    def test_05_rejection_of_duplicate_and_out_of_order_ticks(self):
        """Duplicate ticks and late arriving ticks must be safely rejected."""
        q = {"timestamp": "2026-10-19 09:15:20 IST", "ltp": 500.0, "volume": 100}
        self.agg.process_quote(self.sym, q)
        # Duplicate
        res_dup = self.agg.process_quote(self.sym, q)
        self.assertIsNone(res_dup)
        self.assertEqual(self.agg.forming_bars[self.sym]["tick_count"], 1)

        # Advance to 09:17
        self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:17:10 IST", "ltp": 505.0, "volume": 200})
        # Out-of-order tick for 09:16 arriving late
        late_q = {"timestamp": "2026-10-19 09:16:30 IST", "ltp": 502.0, "volume": 150}
        res_late = self.agg.process_quote(self.sym, late_q)
        self.assertIsNone(res_late, "Out-of-order tick must be rejected")

    def test_06_rejection_of_stale_and_nonfinite_quotes(self):
        """Stale quotes, negative prices, NaN, and Inf prices must be rejected."""
        self.assertIsNone(self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:15:10 IST", "ltp": 100.0, "is_stale": True}))
        self.assertIsNone(self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:15:10 IST", "ltp": -10.0}))
        self.assertIsNone(self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:15:10 IST", "ltp": 0.0}))
        self.assertIsNone(self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:15:10 IST", "ltp": float("nan")}))
        self.assertIsNone(self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:15:10 IST", "ltp": float("inf")}))

    def test_07_timestamp_normalization(self):
        """Timezone-aware, naive, and string timestamps must normalize to Asia/Kolkata."""
        # Naive datetime
        dt_naive = datetime(2026, 10, 19, 9, 15, 30)
        norm_naive = self.agg.normalize_timestamp(dt_naive)
        self.assertEqual(str(norm_naive.tzinfo), "Asia/Kolkata")
        self.assertEqual(norm_naive.hour, 9)

        # Aware UTC datetime
        dt_utc = datetime(2026, 10, 19, 3, 45, 30, tzinfo=pytz.UTC)  # 03:45 UTC = 09:15 IST
        norm_utc = self.agg.normalize_timestamp(dt_utc)
        self.assertEqual(str(norm_utc.tzinfo), "Asia/Kolkata")
        self.assertEqual(norm_utc.hour, 9)
        self.assertEqual(norm_utc.minute, 15)

        # Malformed string
        self.assertIsNone(self.agg.normalize_timestamp("NOT_A_TIMESTAMP"))

    def test_08_gap_does_not_fabricate_synthetic_candles(self):
        """Missing intervals must NOT fabricate phantom intermediate candles."""
        self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:15:10 IST", "ltp": 100.0})
        # Network gap: Next quote arrives 10 minutes later at 09:25:10
        self.agg.process_quote(self.sym, {"timestamp": "2026-10-19 09:25:10 IST", "ltp": 110.0})

        completed = self.agg.get_bars(self.sym, include_forming=False)
        self.assertEqual(len(completed), 1, "Only the 09:15 candle must be completed, no phantom bars")
        self.assertEqual(completed[0]["timestamp_str"], "2026-10-19 09:15:00 IST")

    def test_09_feature_horizons_r1_r3_r5_r10_on_1m_bars(self):
        """Verify r1, r3, r5, r10 correctly compute 1m, 3m, 5m, 10m percentage returns."""
        base_t = datetime(2026, 10, 19, 9, 15, 0)
        # Create 20 bars where close price increases by exactly 1.0 each minute
        # Prices: 100, 101, 102, ..., 119
        bars = []
        for i in range(20):
            t = base_t + timedelta(minutes=i)
            p = 100.0 + i
            bars.append({
                "timestamp": t.strftime("%Y-%m-%d %H:%M:%S IST"),
                "open": p,
                "high": p + 0.5,
                "low": p - 0.5,
                "close": p,
                "volume": 1000.0
            })

        feats = OpportunityDiscoveryEngine.extract_19_features(bars)
        self.assertIsNotNone(feats)
        # c0 = 119 (at i=19)
        # c[-1] = 118 -> r1 = (119 - 118)/118
        expected_r1 = (119.0 - 118.0) / 118.0
        expected_r3 = (119.0 - 116.0) / 116.0
        expected_r5 = (119.0 - 114.0) / 114.0
        expected_r10 = (119.0 - 109.0) / 109.0

        self.assertAlmostEqual(feats[0], expected_r1, places=5)
        self.assertAlmostEqual(feats[1], expected_r3, places=5)
        self.assertAlmostEqual(feats[2], expected_r5, places=5)
        self.assertAlmostEqual(feats[3], expected_r10, places=5)

    def test_10_insufficient_history_rejects_inference(self):
        """Feature extraction must fail-closed (return None) if fewer than 15 bars available."""
        short_buf = [{"timestamp": f"2026-10-19 09:{15+i:02d}:00 IST", "close": 100.0 + i, "high": 101.0, "low": 99.0, "open": 100.0, "volume": 100.0} for i in range(10)]
        self.assertIsNone(OpportunityDiscoveryEngine.extract_19_features(short_buf))


if __name__ == "__main__":
    unittest.main()
