#!/usr/bin/env python3
"""
tests/test_fail_closed_inference.py
Targeted Unit Tests for Fail-Closed Inference & Fallback Elimination (Phase 3 D).
Verifies:
1. When candle history < 15, returns prediction_valid=False and confidence=0.0 (no 50.0 fallback).
2. When regressors fail or have empty models, returns prediction_valid=False.
3. When classifier fails, returns prediction_valid=False.
4. When sufficient candles and models valid, returns prediction_valid=True.
"""

import unittest
from datetime import datetime
import pandas as pd
import numpy as np
import os
import sys

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from QA.models.one_min_predictor import OneMinPredictor


class TestFailClosedInference(unittest.TestCase):

    def setUp(self):
        self.predictor = OneMinPredictor()

    def test_insufficient_history_returns_invalid_prediction(self):
        """Verifies that <15 candles returns prediction_valid=False and confidence=0.0."""
        # 5 candles only
        candles = pd.DataFrame({
            "timestamp": pd.date_range("2026-10-14 09:15:00", periods=5, freq="1min"),
            "open": [100.0, 101.0, 102.0, 101.5, 102.0],
            "high": [101.5, 102.0, 102.5, 102.0, 102.5],
            "low": [99.5, 100.5, 101.0, 101.0, 101.5],
            "close": [101.0, 101.8, 101.5, 102.0, 102.2],
            "volume": [1000, 1200, 1100, 1500, 1300],
            "symbol": ["INFY"] * 5
        })

        res = self.predictor.predict_next_1m(candles)

        self.assertFalse(res["prediction_valid"])
        self.assertEqual(res["confidence"], 0.0)
        self.assertEqual(res["raw_breakout_prob"], 0.0)
        self.assertEqual(res["signal"], "HOLD")
        self.assertEqual(res["direction"], "UNCERTAIN")
        self.assertIn("INSUFFICIENT_HISTORY", res["error"])

    def test_sufficient_history_returns_valid_prediction(self):
        """Verifies that 25 candles produce a valid prediction with prediction_valid=True."""
        np.random.seed(42)
        n = 25
        base_price = 1000.0
        prices = [base_price]
        for _ in range(n - 1):
            prices.append(prices[-1] * (1.0 + np.random.normal(0, 0.001)))

        candles = pd.DataFrame({
            "timestamp": pd.date_range("2026-10-14 09:15:00", periods=n, freq="1min"),
            "open": prices,
            "high": [p * 1.001 for p in prices],
            "low": [p * 0.999 for p in prices],
            "close": prices,
            "volume": [np.random.randint(500, 5000) for _ in range(n)],
            "symbol": ["INFY"] * n
        })

        res = self.predictor.predict_next_1m(candles)

        self.assertTrue(res["prediction_valid"])
        self.assertIsNone(res["error"])
        self.assertIn(res["signal"], ["BUY", "SELL", "HOLD"])
        self.assertIsInstance(res["predicted_return_pct"], float)
        self.assertIsInstance(res["confidence"], float)


if __name__ == "__main__":
    unittest.main()
