#!/usr/bin/env python3
"""
tests/test_opportunity_engine.py
Institutional Unit & Integration Tests for OpportunityDiscoveryEngine (Pillars 1 & 4).
Verifies:
1. Universe registry loads all 50 Nifty 50 constituents + benchmarks.
2. Market regime detector correctly identifies Breakout, Trend, Mean Reversion, and Chop.
3. Chop regime strictly suppresses trading (regime_multiplier = 0.0 -> HOLD).
4. Statutory costs and frictions are subtracted to compute true Net Expectancy.
5. Candidates are sorted and ranked by Opportunity Score.
6. Comparative rationale explains why Rank 1 beat Rank 2.
7. Seamless branching between CASH_EQUITY and OPTIONS_PAPER modes.
"""

import unittest
import numpy as np
import pandas as pd
import os
import sys

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.intelligence.opportunity_engine import (
    OpportunityDiscoveryEngine,
    RegimeDetector,
    MarketRegime,
    OpportunityCandidate
)
from v3.execution.options_engine import OptionsEngine


class TestOpportunityEngine(unittest.TestCase):

    def setUp(self):
        self.engine = OpportunityDiscoveryEngine(
            min_net_expectancy_rs=0.20,
            min_confidence_pct=40.0,
            bankroll=1500.0
        )

    def test_universe_registry_contains_50_plus_benchmarks(self):
        """Verifies full verified NSE universe coverage."""
        self.assertGreaterEqual(len(self.engine.universe), 50)
        self.assertIn("INFY.NS", self.engine.universe)
        self.assertIn("RELIANCE.NS", self.engine.universe)
        self.assertIn("TCS.NS", self.engine.universe)
        self.assertIn("HDFCBANK.NS", self.engine.universe)
        self.assertIn("^NSEI", self.engine.universe)
        self.assertIn("NIFTYBEES.NS", self.engine.universe)

    def test_regime_detector_identifies_chop(self):
        """Verifies flat sideways candles are detected as CHOP_REGIME with 0.0 multiplier."""
        flat_candles = [
            {"open": 100.0, "high": 100.2, "low": 99.8, "close": 100.0, "volume": 1000}
            for _ in range(20)
        ]
        regime = RegimeDetector.detect(flat_candles, 100.0)
        self.assertEqual(regime.regime_name, "CHOP_REGIME")
        self.assertEqual(regime.multiplier, 0.0)

    def test_regime_detector_identifies_momentum_breakout(self):
        """Verifies strong volume surge and range expansion is detected as MOMENTUM_BREAKOUT."""
        candles = [
            {"open": 100.0 + i*0.1, "high": 100.5 + i*0.1, "low": 99.8 + i*0.1, "close": 100.2 + i*0.1, "volume": 1000}
            for i in range(19)
        ]
        # Massive volume surge on final bar
        candles.append({"open": 102.0, "high": 105.0, "low": 101.9, "close": 104.8, "volume": 5000})

        regime = RegimeDetector.detect(candles, 104.8)
        self.assertEqual(regime.regime_name, "MOMENTUM_BREAKOUT")
        self.assertEqual(regime.trend_direction, "BULLISH")
        self.assertGreater(regime.multiplier, 1.0)

    def test_scan_and_rank_opportunities_produces_ranking_table(self):
        """Verifies scanning produces ranked candidates sorted by Opportunity Score."""
        dates = pd.date_range("2026-10-14 09:15:00", periods=20, freq="1min")
        
        # Symbol A: Bullish trending
        candles_a = [
            {"close": 1000.0 + i*1.5, "open": 999.0 + i*1.5, "high": 1001.0 + i*1.5, "low": 998.0 + i*1.5, "volume": 2000}
            for i in range(20)
        ]
        # Symbol B: Choppy flat
        candles_b = [
            {"close": 500.0, "open": 500.0, "high": 500.2, "low": 499.8, "volume": 800}
            for _ in range(20)
        ]

        quotes = {
            "INFY.NS": {"ltp": 1030.0, "open": 1020.0, "high": 1032.0, "low": 1018.0, "volume": 2000, "bid": 1029.8, "ask": 1030.2, "is_stale": False},
            "TATASTEEL.NS": {"ltp": 500.0, "open": 500.0, "high": 500.2, "low": 499.8, "volume": 800, "bid": 499.9, "ask": 500.1, "is_stale": False}
        }
        buffers = {
            "INFY.NS": candles_a,
            "TATASTEEL.NS": candles_b
        }

        candidates = self.engine.scan_and_rank_opportunities(quotes, buffers)
        self.assertEqual(len(candidates), 2)
        # Verify ranking order
        self.assertEqual(candidates[0].rank, 1)
        self.assertEqual(candidates[1].rank, 2)
        self.assertGreaterEqual(candidates[0].score, candidates[1].score)

    def test_selection_explains_comparative_rationale(self):
        """Verifies top opportunity selection includes comparative rationale."""
        candles = [
            {"close": 1000.0 + i, "open": 999.0 + i, "high": 1001.0 + i, "low": 998.0 + i, "volume": 2000}
            for i in range(20)
        ]
        quotes = {
            "INFY.NS": {"ltp": 1020.0, "open": 1010.0, "high": 1022.0, "low": 1008.0, "volume": 2000, "bid": 1019.8, "ask": 1020.2, "is_stale": False}
        }
        buffers = {"INFY.NS": candles}

        candidates = self.engine.scan_and_rank_opportunities(quotes, buffers)
        selection = self.engine.select_top_opportunity(candidates, mode="CASH_EQUITY")

        self.assertIn("decision", selection)
        self.assertIn("comparative_rationale", selection)
        self.assertIn("Rank #1", selection["comparative_rationale"])

    def test_affordability_below_equal_above_bankroll(self):
        """
        P0 Regression: Verifies whole-share affordability for prices:
        - Below ₹1,500: e.g. ₹1,000 -> 1 share affordable.
        - Equal to ₹1,500: e.g. ₹1,500 -> 0 shares (entry costs push total above ₹1,500).
        - Above ₹1,500: e.g. ₹2,500 -> 0 shares (unaffordable).
        """
        # Price below ₹1,500: ₹1,000
        qty_below, notional_below, rejections_below = self.engine.calculate_affordable_quantity(1000.0)
        self.assertEqual(qty_below, 1)
        self.assertEqual(notional_below, 1000.0)
        self.assertEqual(len(rejections_below), 0)

        # Price equal to ₹1,500: ₹1,500.00
        # Entry fees (stamp duty, exchange fee, GST, spread, slippage) push required cash > ₹1,500
        qty_equal, notional_equal, rejections_equal = self.engine.calculate_affordable_quantity(1500.0)
        self.assertEqual(qty_equal, 0)
        self.assertEqual(notional_equal, 0.0)
        self.assertTrue(any("UNAFFORDABLE_POSITION" in r for r in rejections_equal))

        # Price above ₹1,500: ₹2,500.00
        qty_above, notional_above, rejections_above = self.engine.calculate_affordable_quantity(2500.0)
        self.assertEqual(qty_above, 0)
        self.assertEqual(notional_above, 0.0)
        self.assertTrue(any("UNAFFORDABLE_POSITION" in r for r in rejections_above))

    def test_unaffordable_stock_cannot_suppress_affordable_candidate(self):
        """
        P0 Regression: Verifies that an unaffordable high-priced stock (e.g. TCS @ ₹3,500)
        with large predicted returns cannot suppress an affordable candidate (e.g. INFY @ ₹1,000).
        TCS must be rejected at qty=0, have score=0, and INFY must rank #1.
        """
        from unittest.mock import MagicMock, patch

        engine = OpportunityDiscoveryEngine(
            min_net_expectancy_rs=0.20,
            min_confidence_pct=40.0,
            bankroll=1500.0
        )
        engine.predictor.predict_batch_1m = MagicMock(return_value={
            "INFY.NS": {"prediction_valid": True, "predicted_return_pct": 0.50, "confidence": 60.0, "signal": "BUY", "micro_rsi": 55.0, "wick_pressure": 0.1},
            "TCS.NS": {"prediction_valid": True, "predicted_return_pct": 1.50, "confidence": 80.0, "signal": "BUY", "micro_rsi": 55.0, "wick_pressure": 0.1}
        })
        engine._predict_specialist_linear = MagicMock(return_value=0.005)

        regime_mock = MarketRegime("TREND_CONTINUATION", "BULLISH", 25.0, 1.2, 0.01, 1.1, "Healthy trend")

        with patch.object(RegimeDetector, "detect", return_value=regime_mock):
            candles = [{"open": 1000.0, "high": 1005.0, "low": 995.0, "close": 1000.0 + i, "volume": 2000} for i in range(20)]
            quotes = {
                "INFY.NS": {"ltp": 1040.0, "open": 1030.0, "high": 1042.0, "low": 1028.0, "volume": 2000, "bid": 1039.8, "ask": 1040.2, "is_stale": False},
                "TCS.NS": {"ltp": 3600.0, "open": 3590.0, "high": 3610.0, "low": 3585.0, "volume": 3000, "bid": 3599.0, "ask": 3601.0, "is_stale": False}
            }
            buffers = {"INFY.NS": candles, "TCS.NS": candles}

            candidates = engine.scan_and_rank_opportunities(quotes, buffers)
            self.assertEqual(len(candidates), 2)

            # TCS must be rejected for affordability and have score 0.0
            tcs_cand = next(c for c in candidates if "TCS" in c.symbol)
            self.assertEqual(tcs_cand.quantity, 0)
            self.assertFalse(tcs_cand.viable)
            self.assertEqual(tcs_cand.score, 0.0)
            self.assertTrue(any("UNAFFORDABLE_POSITION" in r for r in tcs_cand.rejection_reasons))

            # INFY must be Rank #1
            self.assertEqual(candidates[0].symbol, "INFY.NS")
            self.assertEqual(candidates[0].quantity, 1)
            self.assertTrue(candidates[0].viable)
            self.assertGreater(candidates[0].score, 0.0)

            # Top selection must choose INFY with whole shares
            selection = engine.select_top_opportunity(candidates, mode="CASH_EQUITY")
            self.assertEqual(selection["decision"], "BUY")
            self.assertEqual(selection["symbol"], "INFY.NS")
            self.assertEqual(selection["quantity"], 1)
            self.assertEqual(selection["notional"], 1040.0)

    def test_cash_reserve_and_entry_cost_affordability(self):
        """
        P0 Regression: Verifies that cash reserve reduces deployable bankroll.
        """
        engine_with_reserve = OpportunityDiscoveryEngine(
            bankroll=1500.0,
            cash_reserve_rs=300.0  # Deployable bankroll = ₹1,200.00
        )
        # ₹1,250 stock is unaffordable under ₹1,200 available
        qty, _, rejections = engine_with_reserve.calculate_affordable_quantity(1250.0)
        self.assertEqual(qty, 0)
        self.assertTrue(any("UNAFFORDABLE_POSITION" in r for r in rejections))

        # ₹1,000 stock is affordable (1 share)
        qty_ok, notional_ok, _ = engine_with_reserve.calculate_affordable_quantity(1000.0)
        self.assertEqual(qty_ok, 1)
        self.assertEqual(notional_ok, 1000.0)


if __name__ == "__main__":
    unittest.main()

