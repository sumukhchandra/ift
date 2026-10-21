#!/usr/bin/env python3
"""
tests/test_model_validity.py
P3 Regression Tests: Direction mapping, probability units, invalid inference,
and leakage prevention.
"""

import os
import sys
import math
import unittest
import numpy as np
import pandas as pd

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from QA.models.one_min_predictor import OneMinPredictor
from v3.research.forward_evaluation import ForwardEvaluationPipeline


class TestModelValidity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.predictor = OneMinPredictor()

    def _generate_synthetic_candles(self, n_bars: int = 40, trend: str = "UP") -> pd.DataFrame:
        np.random.seed(42)
        base = 1000.0
        prices = [base]
        for i in range(1, n_bars):
            if trend == "UP":
                delta = np.random.uniform(0.5, 2.5)
            elif trend == "DOWN":
                delta = np.random.uniform(-2.5, -0.5)
            else:
                delta = np.random.uniform(-0.5, 0.5)
            prices.append(prices[-1] + delta)

        df = pd.DataFrame({
            "timestamp": pd.date_range("2026-10-14 09:15:00", periods=n_bars, freq="1min"),
            "open": [p - 0.2 for p in prices],
            "high": [p + 0.8 for p in prices],
            "low": [p - 0.8 for p in prices],
            "close": prices,
            "volume": [10000 + i * 100 for i in range(n_bars)],
            "symbol": "INFY"
        })
        return df

    def test_direction_mapping(self):
        """Verify direction mapping: signals and directions strictly align with predicted returns."""
        for trend in ["UP", "DOWN", "FLAT"]:
            df = self._generate_synthetic_candles(n_bars=50, trend=trend)
            res = self.predictor.predict_next_1m(df)
            self.assertTrue(res["prediction_valid"])
            sig = res["signal"]
            direction = res["direction"]
            pred_ret = float(res["predicted_return_pct"])

            if sig == "BUY":
                self.assertGreaterEqual(pred_ret, 0.0, "BUY signal generated with negative return prediction!")
                self.assertEqual(direction, "LONG", "BUY signal did not map to LONG direction!")
            elif sig == "SELL":
                self.assertLessEqual(pred_ret, 0.0, "SELL signal generated with positive return prediction!")
                self.assertEqual(direction, "SHORT", "SELL signal did not map to SHORT direction!")
            else:
                self.assertEqual(sig, "HOLD")
                self.assertEqual(direction, "FLAT")

    def test_probability_units_and_bounds(self):
        """Verify that breakout probabilities and confidences are strictly bounded."""
        df = self._generate_synthetic_candles(n_bars=45, trend="UP")
        res = self.predictor.predict_next_1m(df)
        self.assertTrue(res["prediction_valid"])

        breakout_prob = float(res.get("raw_breakout_prob", 0.0))
        confidence = float(res.get("confidence", 0.0))

        # raw_breakout_prob is in [0.0, 100.0] or [0.0, 1.0]
        self.assertFalse(math.isnan(breakout_prob), "Breakout prob is NaN")
        self.assertFalse(math.isinf(breakout_prob), "Breakout prob is Infinite")
        self.assertGreaterEqual(breakout_prob, 0.0)
        self.assertLessEqual(breakout_prob, 100.0)

        self.assertFalse(math.isnan(confidence), "Confidence is NaN")
        self.assertFalse(math.isinf(confidence), "Confidence is Infinite")
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 100.0)

    def test_invalid_inference_fail_closed(self):
        """Verify fail-closed behavior on short, empty, or corrupted data buffers."""
        # 1. Empty dataframe
        empty_df = pd.DataFrame()
        res_empty = self.predictor.predict_next_1m(empty_df)
        self.assertFalse(res_empty.get("prediction_valid", True), "Empty df did not fail closed!")
        self.assertIsNotNone(res_empty.get("error"))

        # 2. Too few bars (< 20 bars)
        short_df = self._generate_synthetic_candles(n_bars=10)
        res_short = self.predictor.predict_next_1m(short_df)
        self.assertFalse(res_short.get("prediction_valid", True), "Short buffer did not fail closed!")

        # 3. Buffer filled with NaNs
        nan_df = self._generate_synthetic_candles(n_bars=35)
        nan_df["close"] = np.nan
        res_nan = self.predictor.predict_next_1m(nan_df)
        self.assertFalse(res_nan.get("prediction_valid", True), "NaN buffer did not fail closed!")

    def test_leakage_prevention(self):
        """Verify that predictor features at bar t contain zero future information."""
        pipeline = ForwardEvaluationPipeline()
        # Verify feature columns contain no forward looking column names
        self.assertTrue(pipeline.verify_no_future_leakage(pd.DataFrame(), self.predictor.feature_cols))

        df = self._generate_synthetic_candles(n_bars=40)
        feats = self.predictor.extract_features_1m(df)

        # Truncate at bar 25 and extract features independently
        df_sub = df.iloc[:26].copy()
        feats_sub = self.predictor.extract_features_1m(df_sub)

        # Feature at bar 25 must match exactly whether bar 26..40 exist or not
        row_full = feats.iloc[25][self.predictor.feature_cols].astype(float).values
        row_sub = feats_sub.iloc[25][self.predictor.feature_cols].astype(float).values

        np.testing.assert_allclose(
            row_full,
            row_sub,
            rtol=1e-5,
            atol=1e-5,
            err_msg="Lookahead leakage detected: feature values at t changed when future bars were appended!"
        )


if __name__ == "__main__":
    unittest.main()
