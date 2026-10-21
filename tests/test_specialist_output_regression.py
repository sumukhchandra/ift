#!/usr/bin/env python3
"""
tests/test_specialist_output_regression.py
Regression tests for Specialist-Model Output Handling (Task 2):
1. Valid float outputs.
2. Valid dict outputs with required fields.
3. Valid 1D size-1 array outputs.
4. Missing model results (None) fail safely without fabricated scores or confidences.
5. Malformed dicts missing required fields are rejected with explicit reasons.
6. Malformed shape outputs (multi-dimensional / multi-element arrays) are rejected.
7. Malformed types (strings, bools, etc.) are rejected safely.
8. Non-finite outputs (NaN, +Inf, -Inf) are rejected safely with explicit reasons.
9. Malformed specialist weights (missing fields, wrong length, NaNs) return None and fail closed.
"""

import os
import sys
import math
import unittest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.intelligence.opportunity_engine import (
    OpportunityDiscoveryEngine,
    MarketRegime,
    RegimeDetector
)


class TestSpecialistOutputHandling(unittest.TestCase):

    def setUp(self):
        self.engine = OpportunityDiscoveryEngine(
            min_net_expectancy_rs=0.20,
            min_confidence_pct=40.0,
            bankroll=1500.0
        )
        self.sample_candles = [
            {"open": 1000.0 + i*0.5, "high": 1005.0 + i*0.5, "low": 995.0 + i*0.5, "close": 1002.0 + i*0.5, "volume": 2000}
            for i in range(25)
        ]
        self.quotes = {
            "INFY.NS": {"ltp": 1014.0, "open": 1000.0, "high": 1016.0, "low": 998.0, "volume": 2000, "bid": 1013.8, "ask": 1014.2, "is_stale": False}
        }
        self.buffers = {"INFY.NS": self.sample_candles}

    def _mock_ml_prediction(self, ret_pct=0.50, conf=60.0, sig="BUY"):
        self.engine.predictor.predict_batch_1m = MagicMock(return_value={
            "INFY.NS": {
                "prediction_valid": True,
                "predicted_return_pct": ret_pct,
                "confidence": conf,
                "signal": sig,
                "micro_rsi": 55.0,
                "wick_pressure": 0.1
            }
        })

    def test_01_valid_float_output(self):
        """Verifies valid float alpha is parsed, validated, and produces viable opportunity when concurrent."""
        self._mock_ml_prediction(ret_pct=0.50, conf=60.0, sig="BUY")
        self.engine._predict_specialist_linear = MagicMock(return_value=0.0005)

        is_valid, alpha, reason = self.engine.validate_specialist_output(0.0005)
        self.assertTrue(is_valid)
        self.assertAlmostEqual(alpha, 0.0005)
        self.assertIsNone(reason)

        regime_mock = MarketRegime("TREND_CONTINUATION", "BULLISH", 25.0, 1.2, 0.01, 1.1, "Healthy trend")
        with patch.object(RegimeDetector, "detect", return_value=regime_mock):
            cands = self.engine.scan_and_rank_opportunities(self.quotes, self.buffers)
            self.assertEqual(len(cands), 1)
            c = cands[0]
            self.assertTrue(c.viable)
            self.assertEqual(c.side, "BUY")
            self.assertEqual(c.direction, "LONG")
            self.assertEqual(c.specialist_alpha_bps, 5.0)
            self.assertGreater(c.score, 0.0)

    def test_02_valid_dict_output_with_required_fields(self):
        """Verifies dict output containing 'predicted_alpha' is validated and parsed correctly."""
        dict_output = {"predicted_alpha": 0.0006, "confidence": 65.0, "horizon": "1m"}
        is_valid, alpha, reason = self.engine.validate_specialist_output(dict_output)
        self.assertTrue(is_valid)
        self.assertAlmostEqual(alpha, 0.0006)
        self.assertIsNone(reason)

        # Alternative field 'alpha'
        is_valid2, alpha2, reason2 = self.engine.validate_specialist_output({"alpha": -0.0004})
        self.assertTrue(is_valid2)
        self.assertAlmostEqual(alpha2, -0.0004)
        self.assertIsNone(reason2)

    def test_03_valid_1d_size_1_array_output(self):
        """Verifies 1D scalar-equivalent array output is unpacked and validated."""
        arr_output = np.array([0.00045])
        is_valid, alpha, reason = self.engine.validate_specialist_output(arr_output)
        self.assertTrue(is_valid)
        self.assertAlmostEqual(alpha, 0.00045)
        self.assertIsNone(reason)

    def test_04_missing_specialist_output_fails_safely_no_fabricated_scores(self):
        """Verifies missing specialist output (None) rejects safely without fabricating score or confidence."""
        self._mock_ml_prediction(ret_pct=0.50, conf=60.0, sig="BUY")
        self.engine._predict_specialist_linear = MagicMock(return_value=None)

        is_valid, alpha, reason = self.engine.validate_specialist_output(None)
        self.assertFalse(is_valid)
        self.assertIsNone(alpha)
        self.assertIn("INVALID_SPECIALIST_OUTPUT", reason)
        self.assertIn("missing", reason.lower())

        regime_mock = MarketRegime("TREND_CONTINUATION", "BULLISH", 25.0, 1.2, 0.01, 1.1, "Healthy trend")
        with patch.object(RegimeDetector, "detect", return_value=regime_mock):
            cands = self.engine.scan_and_rank_opportunities(self.quotes, self.buffers)
            self.assertEqual(len(cands), 1)
            c = cands[0]
            # Safety invariants: MUST NOT trade, MUST NOT fabricate scores
            self.assertFalse(c.viable)
            self.assertEqual(c.score, 0.0)
            self.assertEqual(c.side, "HOLD")
            self.assertEqual(c.direction, "FLAT")
            self.assertEqual(c.gross_gain_rs, 0.0)
            self.assertEqual(c.net_expectancy_rs, 0.0)
            self.assertEqual(c.net_expectancy_bps, -9999.0)
            self.assertTrue(any("INVALID_SPECIALIST_OUTPUT" in r for r in c.rejection_reasons))

    def test_05_malformed_dict_missing_required_fields(self):
        """Verifies dict missing 'predicted_alpha' or 'alpha' is rejected with explicit reason."""
        malformed = {"signal": "BUY", "confidence": 80.0}
        is_valid, alpha, reason = self.engine.validate_specialist_output(malformed)
        self.assertFalse(is_valid)
        self.assertIsNone(alpha)
        self.assertIn("Missing required field 'predicted_alpha'", reason)

    def test_06_malformed_shape_rejected(self):
        """Verifies multi-element or multi-dimensional array is rejected with explicit shape mismatch."""
        multi_arr = np.array([0.001, 0.002])
        is_valid, alpha, reason = self.engine.validate_specialist_output(multi_arr)
        self.assertFalse(is_valid)
        self.assertIsNone(alpha)
        self.assertIn("Shape mismatch", reason)

    def test_07_malformed_type_rejected(self):
        """Verifies non-numeric types (strings, booleans, objects) are rejected safely."""
        for bad_val in ["0.005", True, False, object()]:
            is_valid, alpha, reason = self.engine.validate_specialist_output(bad_val)
            self.assertFalse(is_valid)
            self.assertIsNone(alpha)
            self.assertIn("INVALID_SPECIALIST_OUTPUT", reason)

    def test_08_non_finite_outputs_nan_and_inf_rejected(self):
        """Verifies NaN, +Inf, -Inf outputs are rejected with explicit non-finite reason."""
        for non_finite in [float("nan"), float("inf"), float("-inf"), np.nan, np.inf]:
            is_valid, alpha, reason = self.engine.validate_specialist_output(non_finite)
            self.assertFalse(is_valid)
            self.assertIsNone(alpha)
            self.assertIn("Non-finite", reason)

            # In opportunity engine loop, NaN output must zero score and reject
            self._mock_ml_prediction(ret_pct=0.50, conf=60.0, sig="BUY")
            self.engine._predict_specialist_linear = MagicMock(return_value=non_finite)
            regime_mock = MarketRegime("TREND_CONTINUATION", "BULLISH", 25.0, 1.2, 0.01, 1.1, "Healthy trend")
            with patch.object(RegimeDetector, "detect", return_value=regime_mock):
                cands = self.engine.scan_and_rank_opportunities(self.quotes, self.buffers)
                self.assertEqual(len(cands), 1)
                c = cands[0]
                self.assertFalse(c.viable)
                self.assertEqual(c.score, 0.0)
                self.assertTrue(any("Non-finite" in r for r in c.rejection_reasons))

    def test_09_specialist_weights_validation_and_fail_closed(self):
        """Verifies _predict_specialist_linear validates weights schema, lengths, and returns None on defects."""
        # 1. Missing weights dict
        engine_no_weights = OpportunityDiscoveryEngine(specialist_weights=None)
        self.assertIsNone(engine_no_weights._predict_specialist_linear("INFY.NS", [0.0]*19))

        # 2. Corrupt model (missing bias)
        corrupt_weights = {
            "V2_15M": {"weights": [0.0]*19, "means": [0.0]*19, "stds": [1.0]*19}
        }
        engine_corrupt = OpportunityDiscoveryEngine(specialist_weights=corrupt_weights)
        self.assertIsNone(engine_corrupt._predict_specialist_linear("INFY.NS", [0.0]*19))

        # 3. Wrong length (18 weights instead of 19)
        wrong_len_weights = {
            "V2_15M": {"weights": [0.0]*18, "bias": 0.0, "means": [0.0]*19, "stds": [1.0]*19}
        }
        engine_wrong_len = OpportunityDiscoveryEngine(specialist_weights=wrong_len_weights)
        self.assertIsNone(engine_wrong_len._predict_specialist_linear("INFY.NS", [0.0]*19))

        # 4. Non-finite values in weights
        nan_weights = {
            "V2_15M": {"weights": [float("nan")]*19, "bias": 0.0, "means": [0.0]*19, "stds": [1.0]*19}
        }
        engine_nan = OpportunityDiscoveryEngine(specialist_weights=nan_weights)
        self.assertIsNone(engine_nan._predict_specialist_linear("INFY.NS", [0.0]*19))

        # 5. Valid 19 weights
        valid_weights = {
            "V2_15M": {"weights": [0.001]*19, "bias": 0.0001, "means": [0.0]*19, "stds": [1.0]*19}
        }
        engine_valid = OpportunityDiscoveryEngine(specialist_weights=valid_weights)
        pred = engine_valid._predict_specialist_linear("INFY.NS", [1.0]*19)
        self.assertIsNotNone(pred)
        self.assertAlmostEqual(pred, 0.001*19 + 0.0001, places=5)


if __name__ == "__main__":
    unittest.main()
