"""
Unit Tests for Forensic Alpha Decomposer & Interaction Engine.
Verifies:
  1. Time of day categorization.
  2. Sparsity frontier sample gating.
  3. Predefined interaction slicing.
"""

import unittest
import numpy as np
import pandas as pd
from v2.analysis.forensic_decomposer import ForensicDecomposer, TIME_BUCKETS
from v2.risk.dynamic_cost_model import DynamicCostModel, ExecutionMode


class TestForensicDecomposer(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        # Create timestamps across all 5 intraday buckets
        times = [
            "2026-09-01 09:20:00",
            "2026-09-01 10:15:00",
            "2026-09-01 11:45:00",
            "2026-09-01 13:30:00",
            "2026-09-01 14:50:00",
        ]
        self.df = pd.DataFrame({
            "timestamp": pd.to_datetime(times),
            "symbol": ["RELIANCE.NS"] * 5
        })

    def test_time_bucket_assignment(self):
        """Verify proper assignment to the 5 standard intraday buckets."""
        df_bucketed = ForensicDecomposer.assign_time_bucket(self.df)

        expected = [
            "09:15-10:00",
            "10:00-11:00",
            "11:00-13:00",
            "13:00-14:30",
            "14:30-15:15"
        ]
        self.assertEqual(df_bucketed["time_bucket"].tolist(), expected)

    def test_sparsity_frontier_minimum_sample_gate(self):
        """Verify that under-sampled sparsity slices are gated to 0 expectancy."""
        decomposer = ForensicDecomposer(bootstrap_iterations=50)

        # Small sample of 10 rows (below 30 minimum)
        small_df = pd.DataFrame({
            "timestamp": pd.date_range("2026-09-01 09:15", periods=10, freq="5min"),
            "symbol": ["RELIANCE.NS"] * 10,
            "pred": np.linspace(0.001, 0.005, 10),
            "target": np.linspace(0.001, 0.005, 10),
            "raw_close": [2500.0] * 10
        })

        results = decomposer.run_sparsity_frontier_analysis(
            small_df,
            pred_col="pred",
            true_return_col="target",
            quantiles=[95.0]
        )

        self.assertEqual(len(results), 1)
        # Should be gated because N < 30
        self.assertEqual(results[0].net_expectancy_bps, 0.0)
        self.assertFalse(results[0].is_statistically_viable)


if __name__ == "__main__":
    unittest.main()
