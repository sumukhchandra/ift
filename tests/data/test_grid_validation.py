"""
Tests for GridValidator and Deterministic Data Gate in AlphaNSE V2.
Validates session grid construction, missing bar detection, duplicate detection,
geometry checks, and deterministic gate decisions (DATA_LIMITED vs DATA_BLOCKED).
"""

import unittest
import pandas as pd
import numpy as np
from datetime import time
from v2.data.validation.grid_validator import GridValidator, DataCoverageDecision


def generate_synthetic_session(date_str: str, symbol: str, price_base: float = 100.0, volatility_scale: float = 0.001) -> pd.DataFrame:
    """Generate a clean 75-bar 5-minute session for testing with configurable volatility."""
    times = pd.date_range(f"{date_str} 09:15:00", f"{date_str} 15:25:00", freq="5min", tz="Asia/Kolkata")
    n = len(times)
    np.random.seed(int(pd.Timestamp(date_str).value % 100000))
    # Generate prices with specified volatility scale
    steps = np.random.normal(0, volatility_scale, n)
    prices = price_base * np.exp(np.cumsum(steps))
    return pd.DataFrame({
        "timestamp": times,
        "symbol": [symbol] * n,
        "open": prices,
        "high": prices * 1.001,
        "low": prices * 0.999,
        "close": prices,
        "volume": [1000.0] * n
    })


class TestGridValidator(unittest.TestCase):

    def test_construct_session_grid(self):
        validator = GridValidator(interval="5m")
        dates = [pd.Timestamp("2026-09-18")]
        grid = validator.construct_session_grid(dates)

        self.assertEqual(len(grid), 75)
        self.assertEqual(grid[0].time(), time(9, 15))
        self.assertEqual(grid[-1].time(), time(15, 25))
        self.assertIn(grid[0].tzname(), ("IST", "+0530"))

    def test_detects_missing_bars(self):
        validator = GridValidator(interval="5m")
        df = generate_synthetic_session("2026-09-18", "RELIANCE.NS")
        
        # Drop 5 bars
        df_missing = df.iloc[5:].reset_index(drop=True)  # 70 bars instead of 75

        decision = validator.validate_dataset(df_missing)
        sym_metric = decision.symbol_metrics["RELIANCE.NS"]

        self.assertEqual(sym_metric["expected_bars"], 75)
        self.assertEqual(sym_metric["actual_bars"], 70)
        self.assertEqual(sym_metric["missing_bars"], 5)
        self.assertEqual(sym_metric["missing_pct"], round(5 / 75 * 100.0, 2))

    def test_detects_duplicate_bars(self):
        validator = GridValidator(interval="5m")
        df = generate_synthetic_session("2026-09-18", "RELIANCE.NS")
        
        # Duplicate first row
        df_dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)

        decision = validator.validate_dataset(df_dup)
        sym_metric = decision.symbol_metrics["RELIANCE.NS"]

        self.assertEqual(sym_metric["duplicate_count"], 1)
        self.assertFalse(decision.criteria_results["max_duplicate_pct"]["passed"])
        self.assertEqual(decision.status, "DATA_BLOCKED")

    def test_detects_geometry_violations(self):
        validator = GridValidator(interval="5m")
        df = generate_synthetic_session("2026-09-18", "RELIANCE.NS")
        
        # Corrupt price geometry: high < low
        df.loc[0, "high"] = 50.0
        df.loc[0, "low"] = 150.0

        decision = validator.validate_dataset(df)
        sym_metric = decision.symbol_metrics["RELIANCE.NS"]

        self.assertEqual(sym_metric["geometry_violations"], 1)
        self.assertFalse(sym_metric["is_acceptable"])

    def test_deterministic_data_gate_blocks_on_insufficient_sessions(self):
        validator = GridValidator(interval="5m")
        # Only 5 sessions generated (threshold is 40)
        dfs = []
        for day in range(15, 20):
            dfs.append(generate_synthetic_session(f"2026-09-{day:02d}", "RELIANCE.NS"))
        df = pd.concat(dfs, ignore_index=True)

        decision = validator.validate_dataset(df)

        self.assertEqual(decision.session_count, 5)
        self.assertFalse(decision.criteria_results["minimum_sessions_required"]["passed"])
        self.assertFalse(decision.passed_gate)
        self.assertEqual(decision.status, "DATA_BLOCKED")

    def test_deterministic_data_gate_passes_when_all_criteria_met(self):
        validator = GridValidator(interval="5m")
        # Generate 42 sessions across 11 symbols
        symbols = [f"SYM_{i}.NS" for i in range(10)] + ["^NSEI"]
        dfs = []
        
        # Generate 42 dates (simulate 42 business days)
        date_series = pd.date_range("2026-07-01", periods=42, freq="B")
        
        for i, dt in enumerate(date_series):
            d_str = dt.strftime("%Y-%m-%d")
            vol_scale = 0.0005 if i < 20 else 0.0020
            for sym in symbols:
                dfs.append(generate_synthetic_session(d_str, sym, volatility_scale=vol_scale))

        df_full = pd.concat(dfs, ignore_index=True)
        decision = validator.validate_dataset(df_full)

        self.assertEqual(decision.session_count, 42)
        self.assertEqual(decision.symbol_count, 11)
        self.assertTrue(decision.passed_gate)
        self.assertEqual(decision.status, "DATA_LIMITED")
        for crit_name, crit in decision.criteria_results.items():
            self.assertTrue(crit["passed"])

    def test_volatility_regime_breakdown_and_gate(self):
        validator = GridValidator(interval="5m")
        # Generate 10 low vol sessions and 10 high vol sessions
        symbols = ["RELIANCE.NS", "HDFCBANK.NS"]
        dfs = []
        # Low vol sessions
        for d in range(1, 11):
            for sym in symbols:
                dfs.append(generate_synthetic_session(f"2026-07-{d:02d}", sym, volatility_scale=0.0002))
        # High vol sessions
        for d in range(11, 21):
            for sym in symbols:
                dfs.append(generate_synthetic_session(f"2026-07-{d:02d}", sym, volatility_scale=0.0030))

        df = pd.concat(dfs, ignore_index=True)
        decision = validator.validate_dataset(df)

        regimes = decision.regime_breakdown
        self.assertIn("regime_counts", regimes)
        self.assertGreaterEqual(regimes["regime_counts"]["LOW_VOL"], 1)
        self.assertGreaterEqual(regimes["regime_counts"]["HIGH_VOL"], 1)
        self.assertGreaterEqual(regimes["distinct_regimes_count"], 2)
        self.assertTrue(decision.criteria_results["required_regimes_covered"]["passed"])

    def test_max_missing_bar_pct_per_symbol_gate(self):
        validator = GridValidator(interval="5m")
        # Build 42 sessions for SYM_A (100% complete) and SYM_B (drop 10% of bars)
        date_series = pd.date_range("2026-07-01", periods=42, freq="B")
        dfs = []
        for dt in date_series:
            d_str = dt.strftime("%Y-%m-%d")
            dfs.append(generate_synthetic_session(d_str, "SYM_A.NS"))
            # For SYM_B, generate full session
            dfs.append(generate_synthetic_session(d_str, "SYM_B.NS"))

        df_full = pd.concat(dfs, ignore_index=True)
        # Artificially drop 350 bars (out of 42*75=3150 bars = ~11% missing) from SYM_B
        sym_b_indices = df_full[df_full["symbol"] == "SYM_B.NS"].index[:350]
        df_corrupted = df_full.drop(sym_b_indices).reset_index(drop=True)

        decision = validator.validate_dataset(df_corrupted)
        crit = decision.criteria_results["max_missing_bar_pct_per_symbol"]
        self.assertFalse(crit["passed"])
        self.assertGreater(crit["actual"], 5.0)
        self.assertEqual(decision.status, "DATA_BLOCKED")


if __name__ == "__main__":
    unittest.main()
