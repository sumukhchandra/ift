"""
Golden Fixture Equivalence Test for AlphaNSE V2.
Uses the real Friday dataset (QA/data/friday_session_features.csv) as an empirical fixture.
Validates that IncrementalFeatureEngine (streaming O(1)/O(W)) produces mathematically
equivalent features to batch compute_full_features within tight numerical tolerances (< 1e-4).
"""

import os
import unittest
import pandas as pd
from v2.data.schema import Bar
from v2.features.incremental_engine import IncrementalFeatureEngine, compute_full_features

FIXTURE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "QA", "data", "friday_session_features.csv")
)


class TestGoldenFixtureEquivalence(unittest.TestCase):

    def setUp(self):
        self.assertTrue(os.path.exists(FIXTURE_PATH), f"Fixture not found at {FIXTURE_PATH}")
        self.df_raw = pd.read_csv(FIXTURE_PATH)

    def test_equivalence_on_tatacap_fixture(self):
        """Test equivalence across 109 consecutive Friday bars of TATACAP.NS."""
        sub = self.df_raw[self.df_raw["symbol"] == "TATACAP.NS"].sort_values("candle_timestamp").reset_index(drop=True)
        self.assertGreater(len(sub), 50, "Insufficient rows in fixture for TATACAP.NS")

        bars = [
            Bar(
                timestamp=pd.to_datetime(r["candle_timestamp"]).to_pydatetime(),
                symbol=r["symbol"],
                open=float(r["current_price"]),
                high=float(r["current_price"]) * 1.001,
                low=float(r["current_price"]) * 0.999,
                close=float(r["current_price"]),
                volume=5000.0 + idx
            )
            for idx, r in sub.iterrows()
        ]

        # 1. Full batch calculation
        df_full = compute_full_features(bars)

        # 2. Incremental streaming calculation
        engine = IncrementalFeatureEngine(max_lookback=65)
        incr_records = [engine.update(b) for b in bars]
        df_incr = pd.DataFrame(incr_records)

        # 3. Compare all 30 features across all bars
        tolerance = 1e-4
        for feature_name in engine.FEATURE_NAMES:
            self.assertIn(feature_name, df_full.columns, f"Missing {feature_name} in df_full")
            self.assertIn(feature_name, df_incr.columns, f"Missing {feature_name} in df_incr")

            max_diff = (df_full[feature_name] - df_incr[feature_name]).abs().max()
            self.assertLess(
                max_diff,
                tolerance,
                f"Equivalence violation on feature '{feature_name}': max diff = {max_diff:.6e} (tolerance = {tolerance})"
            )

    def test_equivalence_on_reliance_fixture(self):
        """Test equivalence on RELIANCE.NS fixture."""
        sub = self.df_raw[self.df_raw["symbol"] == "RELIANCE.NS"].sort_values("candle_timestamp").reset_index(drop=True)
        self.assertGreater(len(sub), 50, "Insufficient rows in fixture for RELIANCE.NS")

        bars = [
            Bar(
                timestamp=pd.to_datetime(r["candle_timestamp"]).to_pydatetime(),
                symbol=r["symbol"],
                open=float(r["current_price"]),
                high=float(r["current_price"]) * 1.0008,
                low=float(r["current_price"]) * 0.9992,
                close=float(r["current_price"]),
                volume=10000.0 + (idx * 10)
            )
            for idx, r in sub.iterrows()
        ]

        df_full = compute_full_features(bars)
        engine = IncrementalFeatureEngine(max_lookback=65)
        df_incr = pd.DataFrame([engine.update(b) for b in bars])

        tolerance = 1e-4
        for feature_name in engine.FEATURE_NAMES:
            max_diff = (df_full[feature_name] - df_incr[feature_name]).abs().max()
            self.assertLess(
                max_diff,
                tolerance,
                f"Equivalence violation on '{feature_name}': max diff = {max_diff:.6e}"
            )


if __name__ == "__main__":
    unittest.main()
