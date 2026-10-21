"""
Unit Tests for Cluster-Robust Statistical Inference & Session Block Bootstrap.
Verifies:
  1. Session Block Bootstrap resamples full sessions and generates valid 95% CIs.
  2. Session-clustered, symbol-clustered, and two-way clustered SE calculations.
  3. Cluster SE adjustment reflects positive within-cluster correlation.
"""

import unittest
import numpy as np
import pandas as pd
from v2.analysis.cluster_inference import SessionBlockBootstrap, ClusterRobustInference, ClusteredSEStats


class TestClusterInference(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        dates = pd.date_range("2026-07-01", periods=20, freq="B").date
        symbols = ["SYM_A", "SYM_B", "SYM_C", "SYM_D"]

        records = []
        for d in dates:
            session_shock = np.random.randn() * 2.0  # Shared session component
            for sym in symbols:
                for bar in range(5):
                    val = session_shock + np.random.randn() - 0.5  # Mean slightly negative
                    records.append({
                        "timestamp": pd.Timestamp(d) + pd.Timedelta(minutes=5 * bar),
                        "date": d,
                        "symbol": sym,
                        "net_return_bps": val
                    })

        self.df = pd.DataFrame(records)

    def test_session_block_bootstrap(self):
        """Verify session block bootstrap produces expected structure and CIs."""
        bootstrapper = SessionBlockBootstrap(n_bootstrap_iterations=200, random_seed=42)
        res = bootstrapper.run_session_bootstrap(self.df, metric_col="net_return_bps")

        self.assertEqual(res.n_sessions, 20)
        self.assertEqual(res.n_trades, len(self.df))
        self.assertLess(res.ci_lower_95, res.observed_mean)
        self.assertGreater(res.ci_upper_95, res.observed_mean)
        self.assertGreater(res.bootstrap_std, 0.0)

    def test_clustered_standard_errors(self):
        """Verify session, symbol, and two-way clustered SEs."""
        stats = ClusterRobustInference.compute_clustered_stats(
            self.df,
            value_col="net_return_bps",
            session_col="date",
            symbol_col="symbol"
        )

        self.assertIsInstance(stats, ClusteredSEStats)
        self.assertEqual(stats.n_sessions, 20)
        self.assertEqual(stats.n_symbols, 4)
        self.assertEqual(stats.n_observations, len(self.df))

        # Because of the shared session shock, session-clustered SE should exceed pooled OLS SE
        self.assertGreater(stats.session_clustered_se, stats.pooled_se)
        self.assertGreater(stats.twoway_clustered_se, stats.pooled_se)


if __name__ == "__main__":
    unittest.main()
