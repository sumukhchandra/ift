#!/usr/bin/env python3
"""
tests/test_benchmark_and_batching.py
Comprehensive Test Suite for Pipeline Benchmarking, Vectorized Batching, and Fail-Closed Robustness.

Verifies:
1. Numerical equivalence between OneMinPredictor.predict_batch_1m and predict_next_1m (< 1e-6 tolerance).
2. Robustness to edge cases: empty batches, short history, missing columns, NaNs, and mixed valid/invalid inputs.
3. EdgeFrictionGate fail-closed rejection of stale quotes and sub-hurdle expectancy.
4. OptionsEngine fail-closed behavior on empty, illiquid, or unaffordable option chains.
5. Benchmark profiling helper accuracy, warm-up discarding, and percentile monotonic ordering.
"""

import unittest
import os
import sys
import numpy as np
import pandas as pd

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from QA.models.one_min_predictor import OneMinPredictor
from v3.execution.edge_friction_gate import EdgeFrictionGate
from v3.execution.options_engine import OptionsEngine, calculate_black_scholes_greeks
from v3.intelligence.opportunity_engine import OpportunityDiscoveryEngine
from benchmarks.profile_pipeline import profile_stage


def make_synthetic_candle_buffer(symbol: str, n_bars: int = 30, base_price: float = 1000.0, seed: int = 42) -> pd.DataFrame:
    """Generates deterministic pseudo-market OHLCV candles for testing."""
    rng = np.random.RandomState(seed)
    returns = rng.normal(0.0001, 0.001, n_bars)
    prices = [base_price]
    for r in returns[1:]:
        prices.append(prices[-1] * (1.0 + r))

    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-10-14 09:15:00", periods=n_bars, freq="1min"),
        "open": prices,
        "high": [p * 1.0008 for p in prices],
        "low": [p * 0.9992 for p in prices],
        "close": prices,
        "volume": [int(v) for v in rng.uniform(1000, 5000, n_bars)],
        "symbol": [symbol] * n_bars
    })
    return df


class TestSequentialVsBatchEquivalence(unittest.TestCase):
    """Verifies that vectorized batched inference produces identical results to sequential inference."""

    @classmethod
    def setUpClass(cls):
        cls.predictor = OneMinPredictor()
        cls.symbols = ["INFY.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS"]
        cls.candle_buffers = {}
        for idx, sym in enumerate(cls.symbols):
            cls.candle_buffers[sym] = make_synthetic_candle_buffer(sym, n_bars=35, base_price=500.0 * (idx + 1), seed=100 + idx)

    def test_numerical_equivalence_across_symbols(self):
        """Verifies predicted returns and confidence are bitwise/numerically identical (< 1e-6 diff)."""
        # Batched inference
        batch_results = self.predictor.predict_batch_1m(self.candle_buffers)

        self.assertEqual(len(batch_results), len(self.symbols))

        for sym in self.symbols:
            seq_res = self.predictor.predict_next_1m(self.candle_buffers[sym])
            bat_res = batch_results[sym]

            self.assertTrue(seq_res["prediction_valid"])
            self.assertTrue(bat_res["prediction_valid"])

            # Test numerical equivalence
            ret_diff = abs(seq_res["predicted_return_pct"] - bat_res["predicted_return_pct"])
            prob_diff = abs(seq_res["confidence"] - bat_res["confidence"])

            self.assertLess(ret_diff, 1e-6, f"Return difference on {sym} ({ret_diff}) exceeded 1e-6 tolerance")
            self.assertLess(prob_diff, 1e-6, f"Confidence difference on {sym} ({prob_diff}) exceeded 1e-6 tolerance")
            self.assertEqual(seq_res["signal"], bat_res["signal"], f"Signal mismatch on {sym}")
            self.assertEqual(seq_res["direction"], bat_res["direction"], f"Direction mismatch on {sym}")


class TestBatchPredictorEdgeCases(unittest.TestCase):
    """Verifies fail-closed behavior and robustness to malformed inputs in predict_batch_1m."""

    @classmethod
    def setUpClass(cls):
        cls.predictor = OneMinPredictor()

    def test_empty_batch_dict(self):
        """Empty input dict returns empty output dict without exception."""
        res = self.predictor.predict_batch_1m({})
        self.assertEqual(res, {})

    def test_short_candle_history(self):
        """Buffers with < 15 candles return prediction_valid=False and confidence=0.0."""
        short_buf = make_synthetic_candle_buffer("TINY.NS", n_bars=8)
        res = self.predictor.predict_batch_1m({"TINY.NS": short_buf})

        self.assertIn("TINY.NS", res)
        self.assertFalse(res["TINY.NS"]["prediction_valid"])
        self.assertEqual(res["TINY.NS"]["confidence"], 0.0)
        self.assertEqual(res["TINY.NS"]["signal"], "HOLD")
        self.assertIn("INSUFFICIENT_HISTORY", res["TINY.NS"]["error"])

    def test_empty_dataframe(self):
        """Empty dataframe returns prediction_valid=False gracefully."""
        empty_df = pd.DataFrame()
        res = self.predictor.predict_batch_1m({"EMPTY.NS": empty_df})

        self.assertIn("EMPTY.NS", res)
        self.assertFalse(res["EMPTY.NS"]["prediction_valid"])
        self.assertEqual(res["EMPTY.NS"]["confidence"], 0.0)
        self.assertEqual(res["EMPTY.NS"]["signal"], "HOLD")

    def test_missing_required_columns(self):
        """Dataframe missing required OHLCV columns returns prediction_valid=False."""
        bad_df = pd.DataFrame({"close": [100.0, 101.0, 102.0], "volume": [100, 200, 300]})
        res = self.predictor.predict_batch_1m({"BAD.NS": bad_df})

        self.assertIn("BAD.NS", res)
        self.assertFalse(res["BAD.NS"]["prediction_valid"])
        self.assertEqual(res["BAD.NS"]["signal"], "HOLD")

    def test_mixed_valid_and_invalid_batch(self):
        """A batch containing both valid and invalid data processes valid symbols accurately while failing invalid symbols closed."""
        valid_buf = make_synthetic_candle_buffer("VALID.NS", n_bars=30, base_price=1500.0, seed=55)
        short_buf = make_synthetic_candle_buffer("SHORT.NS", n_bars=5)
        empty_df = pd.DataFrame()

        mixed_batch = {
            "VALID.NS": valid_buf,
            "SHORT.NS": short_buf,
            "EMPTY.NS": empty_df
        }

        res = self.predictor.predict_batch_1m(mixed_batch)

        self.assertEqual(len(res), 3)
        self.assertTrue(res["VALID.NS"]["prediction_valid"])
        self.assertFalse(res["SHORT.NS"]["prediction_valid"])
        self.assertFalse(res["EMPTY.NS"]["prediction_valid"])
        self.assertIsNone(res["VALID.NS"]["error"])
        self.assertIsNotNone(res["SHORT.NS"]["error"])
        self.assertIsNotNone(res["EMPTY.NS"]["error"])

    def test_nans_in_buffer_handled_cleanly(self):
        """Buffer with occasional NaNs in price data does not crash or raise unhandled exceptions."""
        nan_buf = make_synthetic_candle_buffer("NAN.NS", n_bars=30)
        nan_buf.loc[5, "high"] = np.nan
        nan_buf.loc[12, "volume"] = np.nan

        res = self.predictor.predict_batch_1m({"NAN.NS": nan_buf})
        self.assertIn("NAN.NS", res)
        self.assertTrue(res["NAN.NS"]["prediction_valid"])
        self.assertIsInstance(res["NAN.NS"]["predicted_return_pct"], float)


class TestEdgeFrictionGateStaleAndHurdleChecks(unittest.TestCase):
    """Verifies that EdgeFrictionGate strictly enforces transaction cost hurdles and OpportunityEngine rejects stale quotes."""

    def setUp(self):
        self.gate = EdgeFrictionGate(min_net_expectancy_rs=0.25, half_spread_bps=3.0, slippage_bps=4.0)

    def test_negative_net_expectancy_rejected(self):
        """When gross predicted return is smaller than roundtrip friction, trade is rejected."""
        # 1 share at ₹1000 with a tiny 0.02% (2 bps) expected move -> gross profit Rs 0.20
        # Friction: spread (6 bps = 0.60) + slippage (8 bps = 0.80) + brokerage + taxes + margin (0.50) > Rs 2.00
        # Net edge < Rs 0.25 -> must be rejected
        eval_res = self.gate.evaluate_signal(
            symbol="INFY.NS",
            side="BUY",
            quantity=1,
            mid_price=1000.0,
            expected_move_pct=0.0002
        )
        self.assertFalse(eval_res.approved)
        self.assertIn("EDGE_INSUFFICIENT", eval_res.rejection_reason)
        self.assertLess(eval_res.net_edge_rs, 0.25)

    def test_strong_edge_passes_gate(self):
        """When expected return comfortably exceeds all-in friction and margin, trade is approved."""
        # 10 shares at ₹500 with a substantial 0.50% (50 bps) move -> gross profit Rs 25.00
        eval_res = self.gate.evaluate_signal(
            symbol="TCS.NS",
            side="BUY",
            quantity=10,
            mid_price=500.0,
            expected_move_pct=0.0050
        )
        self.assertTrue(eval_res.approved)
        self.assertEqual(eval_res.rejection_reason, "")
        self.assertGreater(eval_res.net_edge_rs, 0.25)

    def test_stale_quote_skipped_by_opportunity_engine(self):
        """Quotes marked is_stale=True or with BUFFER_FALLBACK are strictly ignored by OpportunityDiscoveryEngine."""
        opp_engine = OpportunityDiscoveryEngine(bankroll=1500.0)
        stale_quotes = {
            "STALE.NS": {
                "ltp": 1000.0,
                "bid": 999.5,
                "ask": 1000.5,
                "volume": 10000,
                "is_stale": True,
                "source": "KOTAK_NEO"
            },
            "FALLBACK.NS": {
                "ltp": 500.0,
                "bid": 499.5,
                "ask": 500.5,
                "volume": 5000,
                "is_stale": False,
                "source": "BUFFER_FALLBACK"
            }
        }
        buf = make_synthetic_candle_buffer("STALE.NS", n_bars=30)
        buffers = {"STALE.NS": buf, "FALLBACK.NS": buf}

        candidates = opp_engine.scan_and_rank_opportunities(stale_quotes, buffers)
        # Both symbols must be skipped due to stale/fallback quote validation
        candidate_symbols = [c.symbol for c in candidates]
        self.assertNotIn("STALE.NS", candidate_symbols)
        self.assertNotIn("FALLBACK.NS", candidate_symbols)


class TestOptionsEngineFailClosed(unittest.TestCase):
    """Verifies fail-closed behavior of OptionsEngine on invalid or missing option chain data."""

    def setUp(self):
        self.options_engine = OptionsEngine(starting_bankroll=1500.0, underlying_symbol="NIFTY")

    def test_empty_chain_returns_hold(self):
        """Empty option chain returns HOLD safely without raising an exception."""
        decision = self.options_engine.evaluate_ce_pe_signal(
            spot_price=25000.0,
            predicted_return=0.0025,
            confidence=65.0,
            contracts=[]
        )
        self.assertEqual(decision["signal"], "HOLD")
        self.assertTrue(decision["reason"].startswith("NO_ELIGIBLE_CONTRACTS"))
        self.assertIsNone(decision["contract"])

    def test_unaffordable_contracts_rejected(self):
        """Contracts with lot cost exceeding available bankroll are rejected with INSUFFICIENT_CASH."""
        expensive_chain = [
            {
                "symbol": "NIFTY26OCT25000CE",
                "underlying": "NIFTY",
                "strike": 25000.0,
                "option_type": "CE",
                "expiry": "2026-10-29",
                "ltp": 100.0,
                "lot_size": 25,  # Total cost: 100 * 25 = 2,500 > 1,500 bankroll
                "bid": 99.5,
                "ask": 100.5,
                "volume": 10000,
                "open_interest": 50000,
                "is_simulated_chain": True
            }
        ]
        decision = self.options_engine.evaluate_ce_pe_signal(
            spot_price=25000.0,
            predicted_return=0.0025,
            confidence=65.0,
            contracts=expensive_chain
        )
        self.assertEqual(decision["signal"], "HOLD")
        self.assertIn("INSUFFICIENT_CASH", decision["reason"])
        self.assertIsNone(decision["contract"])

    def test_black_scholes_boundary_conditions(self):
        """Black-Scholes Greeks calculation handles zero/negative expiry and zero volatility gracefully."""
        # Non-positive expiry
        greeks_expired = calculate_black_scholes_greeks(
            spot=100.0,
            strike=100.0,
            time_to_expiry_years=0.0,
            iv=0.20,
            option_type="CE"
        )
        self.assertEqual(greeks_expired["delta"], 0.5)
        self.assertEqual(greeks_expired["gamma"], 0.0)
        self.assertEqual(greeks_expired["theoretical_price"], 0.0)

        # Zero volatility
        greeks_zero_vol = calculate_black_scholes_greeks(
            spot=100.0,
            strike=100.0,
            time_to_expiry_years=0.1,
            iv=0.0,
            option_type="CE"
        )
        self.assertEqual(greeks_zero_vol["delta"], 0.5)
        self.assertEqual(greeks_zero_vol["gamma"], 0.0)


class TestBenchmarkProfilingHelper(unittest.TestCase):
    """Verifies that the benchmark profiler calculates statistics accurately and discards warm-up."""

    def test_profiler_statistics_monotonicity_and_warmup(self):
        """Verifies p50 <= p95 <= p99 <= max and warm-up cycles are properly discarded."""
        call_count = 0

        def dummy_stage():
            nonlocal call_count
            call_count += 1
            # Small deterministic work
            _ = sum(i * i for i in range(500))

        warmup_n = 5
        iter_n = 20

        stats = profile_stage(
            name="TestStage",
            func=dummy_stage,
            iterations=iter_n,
            warmup=warmup_n,
            data_type="UNIT_TEST",
            notes="Testing profiling helper."
        )

        # Verify call count is warmup + iterations
        self.assertEqual(call_count, warmup_n + iter_n)
        self.assertEqual(stats["iterations"], iter_n)
        self.assertEqual(stats["warmup_iterations"], warmup_n)

        # Monotonicity checks
        self.assertLessEqual(stats["min_ms"], stats["p50_ms"])
        self.assertLessEqual(stats["p50_ms"], stats["p95_ms"])
        self.assertLessEqual(stats["p95_ms"], stats["p99_ms"])
        self.assertLessEqual(stats["p99_ms"], stats["max_ms"])
        self.assertGreater(stats["mean_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()
