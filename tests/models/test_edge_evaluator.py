"""
Unit Tests for Frozen Model Invariant, Edge Evaluator & Tri-State Gate.
Verifies:
  1. Frozen estimator enforcement: ModelFrozenError on post-freeze modifications.
  2. Signal quality vs Trading quality separation.
  3. Effective Sample Size (ESS) calculation.
  4. Trade-level expectancy calculation (N = trades).
  5. Tri-state Edge Gate: PASS, FAIL, INCONCLUSIVE.
"""

import unittest
import numpy as np
import pandas as pd
from v2.models.estimators import (
    ModelFrozenError,
    RidgeReturnRegressor,
    LightGBMReturnRegressor,
    CalibratedDirectionClassifier
)
from v2.models.edge_evaluator import (
    EdgeGateConfig,
    EdgeEvaluator,
    SignalQualityMetrics,
    TradeQualityMetrics,
    FoldResult
)


class TestEdgeEvaluator(unittest.TestCase):

    def setUp(self):
        self.config = EdgeGateConfig(
            min_oos_trades=10,
            min_oos_sessions=5,
            min_effective_sample_size=20.0,
            min_ic=0.03,
            min_baseline_expectancy_bps=0.0,
            min_stressed_expectancy_bps=0.0,
            min_win_rate_pct=51.5,
            max_drawdown_pct=5.0,
            min_positive_folds_pct=60.0
        )
        self.evaluator = EdgeEvaluator(config=self.config)

    def test_frozen_model_invariant(self):
        """Verify that frozen models reject any further fit or calibrate calls."""
        X = np.random.randn(50, 4)
        y = np.random.randn(50)

        # Ridge
        ridge = RidgeReturnRegressor()
        ridge.fit(X, y)
        ridge.freeze()
        with self.assertRaises(ModelFrozenError):
            ridge.fit(X, y)
        with self.assertRaises(ModelFrozenError):
            ridge.tune_and_calibrate(X, y)

        # LightGBM
        lgb = LightGBMReturnRegressor()
        lgb.fit(X, y)
        lgb.freeze()
        with self.assertRaises(ModelFrozenError):
            lgb.fit(X, y)

        # Classifier
        clf = CalibratedDirectionClassifier()
        clf.fit(X, y)
        clf.freeze()
        with self.assertRaises(ModelFrozenError):
            clf.fit(X, y)

    def test_effective_sample_size(self):
        """Verify ESS computation with positive autocorrelation."""
        # Uncorrelated noise -> ESS ~ N
        np.random.seed(42)
        uncorrelated = np.random.randn(200)
        ess_uncorr = self.evaluator.compute_effective_sample_size(uncorrelated)
        self.assertAlmostEqual(ess_uncorr, 200.0, delta=25.0)

        # Highly autocorrelated noise -> ESS < N
        autocorr = np.zeros(200)
        for i in range(1, 200):
            autocorr[i] = 0.8 * autocorr[i - 1] + 0.2 * np.random.randn()
        ess_corr = self.evaluator.compute_effective_sample_size(autocorr)
        self.assertLess(ess_corr, 100.0)

    def test_trade_level_expectancy(self):
        """Verify trade-level expectancy only counts trades N, not all observations."""
        timestamps = pd.date_range("2026-09-01 09:15", periods=20, freq="5min")
        test_df = pd.DataFrame({
            "timestamp": timestamps,
            "symbol": ["TEST.NS"] * 20,
            "raw_close": [1000.0] * 20,
            "raw_volume": [50000.0] * 20,
            "predicted_return": [0.0005] * 15 + [0.0025] * 5,  # 5 trades exceed 15 bps (0.0015)
            "target_return": [0.0002] * 15 + [0.0030] * 5      # 30 bps gross return on trades
        })

        trades = self.evaluator.generate_hypothetical_trades(
            test_df,
            pred_col="predicted_return",
            true_return_col="target_return",
            threshold_bps=15.0
        )
        self.assertEqual(len(trades), 5)  # exactly 5 trades generated

        trading_metrics, _ = self.evaluator.evaluate_trading_quality(trades, stress_multiplier=1.0)
        self.assertEqual(trading_metrics.trade_count, 5)
        self.assertAlmostEqual(trading_metrics.gross_expectancy_bps, 30.0, places=1)
        self.assertGreater(trading_metrics.cost_expectancy_bps, 0.0)
        self.assertAlmostEqual(
            trading_metrics.net_expectancy_bps,
            trading_metrics.gross_expectancy_bps - trading_metrics.cost_expectancy_bps,
            places=1
        )

    def test_inconclusive_verdict_on_insufficient_evidence(self):
        """Verify that failing sample size / trade count yields INCONCLUSIVE, not FAIL or PASS."""
        signal_metrics = SignalQualityMetrics(
            ic_pearson=0.08,
            ic_spearman=0.07,
            mae=0.002,
            directional_accuracy_pct=55.0,
            n_observations=50,
            effective_sample_size=10.0  # < required 20.0
        )
        trading_metrics = TradeQualityMetrics(
            trade_count=5,  # < required 10
            gross_expectancy_bps=25.0,
            cost_expectancy_bps=12.0,
            net_expectancy_bps=13.0,
            win_rate_pct=60.0,
            profit_factor=2.0,
            max_drawdown_pct=1.0,
            total_net_pnl_bps=65.0,
            trades_per_session=1.0
        )
        fold_results = [
            FoldResult(1, 10, 2, 2, 2, 0.08, 15.0, 10.0, 60.0),
            FoldResult(2, 10, 2, 2, 3, 0.07, 12.0, 8.0, 60.0),
        ]

        verdict = self.evaluator.evaluate_gate(
            signal_metrics=signal_metrics,
            baseline_trading=trading_metrics,
            stressed_trading=trading_metrics,
            extreme_trading=trading_metrics,
            fold_results=fold_results,
            n_oos_sessions=4  # < required 5
        )

        self.assertEqual(verdict.status, "INCONCLUSIVE")
        self.assertIn("INCONCLUSIVE: Insufficient statistical sample evidence", verdict.summary_message)


if __name__ == "__main__":
    unittest.main()
