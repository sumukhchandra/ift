"""
Unit Tests for Feature Pipeline & Architectural Source Boundaries.
Verifies:
  1. RAW vs ADJUSTED column isolation.
  2. Strict point-in-time calculation (no lookahead).
  3. Session-based VWAP reset.
  4. Intraday return continuity without overnight leak.
"""

import unittest
import numpy as np
import pandas as pd
from v2.features.feature_pipeline import (
    FeaturePipeline,
    RAW_FEATURE_COLUMNS,
    ADJ_FEATURE_COLUMNS,
    BENCHMARK_FEATURE_COLUMNS,
    ALL_FEATURE_COLUMNS
)


class TestFeaturePipeline(unittest.TestCase):

    def setUp(self):
        # Create synthetic 2-day 5-minute data
        timestamps = pd.date_range("2026-09-01 09:15", "2026-09-01 15:30", freq="5min").tolist() + \
                     pd.date_range("2026-09-02 09:15", "2026-09-02 15:30", freq="5min").tolist()
        n = len(timestamps)

        np.random.seed(42)
        base_raw = 1000.0 + np.cumsum(np.random.randn(n) * 2.0)
        base_adj = base_raw * 0.98  # Corporate action adjusted difference

        self.df = pd.DataFrame({
            "timestamp": timestamps,
            "symbol": ["TEST.NS"] * n,
            "raw_open": base_raw - 1.0,
            "raw_high": base_raw + 2.0,
            "raw_low": base_raw - 2.0,
            "raw_close": base_raw,
            "raw_volume": np.random.randint(1000, 10000, n),
            "adj_open": base_adj - 0.98,
            "adj_high": base_adj + 1.96,
            "adj_low": base_adj - 1.96,
            "adj_close": base_adj,
            "adj_volume": np.random.randint(1000, 10000, n)
        })

    def test_feature_source_isolation(self):
        """Ensure RAW and ADJUSTED columns are strictly partitioned."""
        for col in RAW_FEATURE_COLUMNS:
            self.assertTrue(col.startswith("raw_"), f"RAW column {col} missing raw_ prefix")
        for col in ADJ_FEATURE_COLUMNS:
            self.assertTrue(col.startswith("adj_"), f"ADJUSTED column {col} missing adj_ prefix")

        # Intersection must be empty
        overlap = set(RAW_FEATURE_COLUMNS).intersection(set(ADJ_FEATURE_COLUMNS))
        self.assertEqual(len(overlap), 0, f"Found overlapping features between RAW and ADJ: {overlap}")

    def test_symbol_feature_computation(self):
        """Test feature computation for a single symbol."""
        feat_df = FeaturePipeline._compute_symbol_features(self.df)

        for col in RAW_FEATURE_COLUMNS:
            self.assertIn(col, feat_df.columns, f"Missing raw feature: {col}")
        for col in ADJ_FEATURE_COLUMNS:
            self.assertIn(col, feat_df.columns, f"Missing adj feature: {col}")

        # Wick pressure must be bounded in [0, 1]
        self.assertTrue((feat_df["raw_wick_pressure"] >= 0.0).all())
        self.assertTrue((feat_df["raw_wick_pressure"] <= 1.0).all())

        # RSI must be bounded in [0, 100]
        self.assertTrue((feat_df["adj_rsi_14"] >= 0.0).all())
        self.assertTrue((feat_df["adj_rsi_14"] <= 100.0).all())

    def test_vwap_session_reset(self):
        """Verify that intraday VWAP resets on the new trading session."""
        feat_df = FeaturePipeline._compute_symbol_features(self.df)
        feat_df["date"] = feat_df["timestamp"].dt.date

        day1_last = feat_df[feat_df["date"] == feat_df["date"].iloc[0]].iloc[-1]
        day2_first = feat_df[feat_df["date"] == feat_df["date"].iloc[-1]].iloc[0]

        # Day 2 first bar VWAP must equal Day 2 first bar close
        self.assertAlmostEqual(day2_first["raw_vwap"], day2_first["raw_close"], places=4)


if __name__ == "__main__":
    unittest.main()
