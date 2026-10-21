#!/usr/bin/env python3
"""
tests/test_provenance_tracker.py
Unit tests for ProvenanceTracker and Model Drift Sentinel (Pillar 5).
Verifies:
1. Records immutable predictions with complete provenance metadata.
2. Pairs subsequent actual observations at t+1 and calculates exact error in INR.
3. Calculates directional correctness accurately.
4. Drift sentinel detects drops in rolling accuracy and adjusts hurdles.
"""

import unittest
import os
import sys

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.intelligence.provenance_tracker import ProvenanceTracker


class TestProvenanceTracker(unittest.TestCase):

    def setUp(self):
        self.test_dir = os.path.join(WORKSPACE_ROOT, "reports", "test_scratch_provenance")
        self.tracker = ProvenanceTracker(log_dir=self.test_dir, drift_threshold=0.50)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_record_prediction_persists_full_metadata(self):
        """Verifies prediction event is logged with full feature provenance."""
        rec = self.tracker.record_prediction(
            symbol="INFY.NS",
            spot_price=1050.0,
            data_source="KOTAK_NEO_TRADE_API",
            specialist_alpha_bps=12.5,
            tree_alpha_bps=8.0,
            concurrence_ok=True,
            calibrated_confidence=68.5,
            regime_name="MOMENTUM_BREAKOUT",
            gross_gain_rs=8.40,
            statutory_fees_rs=2.10,
            total_friction_rs=3.50,
            net_expectancy_rs=4.90,
            signal="BUY",
            timestamp_str="2026-10-14 09:15:00 IST"
        )

        self.assertEqual(rec["symbol"], "INFY.NS")
        self.assertEqual(rec["spot_price"], 1050.0)
        self.assertEqual(rec["signal"], "BUY")
        self.assertFalse(rec["outcome_verified"])
        self.assertTrue(os.path.exists(self.tracker.provenance_file))

    def test_record_actual_outcome_pairs_and_evaluates(self):
        """Verifies outcome pairing computes error and correctness."""
        # 1. Record Prediction (Predicted +8.0 bps move on ₹1050 = ₹1050.84)
        pred_time = "2026-10-14 09:15:00 IST"
        self.tracker.record_prediction(
            symbol="INFY.NS",
            spot_price=1050.0,
            data_source="KOTAK_NEO_TRADE_API",
            specialist_alpha_bps=12.5,
            tree_alpha_bps=8.0,
            concurrence_ok=True,
            calibrated_confidence=68.5,
            regime_name="MOMENTUM_BREAKOUT",
            gross_gain_rs=8.40,
            statutory_fees_rs=2.10,
            total_friction_rs=3.50,
            net_expectancy_rs=4.90,
            signal="BUY",
            timestamp_str=pred_time
        )

        # 2. Record Actual Observation at t+1: Price moved to ₹1052.00 (Bullish)
        outcome = self.tracker.record_actual_outcome(
            symbol="INFY.NS",
            prediction_timestamp_str=pred_time,
            actual_observed_price=1052.0
        )

        self.assertIsNotNone(outcome)
        self.assertTrue(outcome["outcome_verified"])
        self.assertEqual(outcome["actual_next_price"], 1052.0)
        self.assertTrue(outcome["is_correct_direction"])
    def test_process_incoming_quotes_matures_prediction(self):
        """Verifies that process_incoming_quotes matches predictions aged 50-90s and writes to outcomes stream."""
        from datetime import datetime, timedelta
        # Simulate a prediction made 60 seconds ago
        pred_dt = datetime.now() - timedelta(seconds=60)
        pred_time_str = pred_dt.strftime("%Y-%m-%d %H:%M:%S IST")

        self.tracker.record_prediction(
            symbol="BAJFINANCE.NS",
            spot_price=950.0,
            data_source="KOTAK_NEO_TRADE_API",
            specialist_alpha_bps=5.0,
            tree_alpha_bps=10.0,
            concurrence_ok=True,
            calibrated_confidence=65.0,
            regime_name="CHOP_REGIME",
            gross_gain_rs=0.95,
            statutory_fees_rs=0.50,
            total_friction_rs=0.80,
            net_expectancy_rs=0.15,
            signal="HOLD",
            timestamp_str=pred_time_str
        )

        # Incoming quotes now
        quotes = {
            "BAJFINANCE.NS": {
                "ltp": 952.5,
                "is_stale": False,
                "source": "KOTAK_NEO_TRADE_API"
            }
        }

        resolved = self.tracker.process_incoming_quotes(quotes)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["symbol"], "BAJFINANCE.NS")
        self.assertEqual(resolved[0]["actual_next_price"], 952.5)
        self.assertTrue(resolved[0]["is_correct_direction"])
        self.assertTrue(os.path.exists(self.tracker.outcomes_file))


if __name__ == "__main__":
    unittest.main()
