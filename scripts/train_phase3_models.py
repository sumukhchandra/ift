"""
Phase 3 Model Training, Purged Walk-Forward Cross-Validation & Edge Gate Evaluation Script.
Evaluates 5-minute, 10-minute, and 15-minute signals across candidate estimators:
  1. Ridge Regression (L2 Baseline)
  2. LightGBM Regressor (Nonlinear Trees)
  3. Calibrated LightGBM Classifier (Directional Hurdle with Isotonic Calibration)
Strictly enforces:
  • Raw execution price forward labels
  • Feature source boundary (RAW vs ADJUSTED)
  • No test peeking (Train -> Val -> Freeze -> Test)
  • Exact H-bar purge and 1-session embargo
  • Dynamic cost stress testing (1.0x, 1.25x, 1.50x, 2.00x)
  • Deterministic 10-point Pre-Registered Edge Gate with tri-state verdict
"""

import os
import sys
import json
import logging
import pickle
from typing import Dict, Any, List
import numpy as np
import pandas as pd

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from v2.features.feature_pipeline import FeaturePipeline, ALL_FEATURE_COLUMNS
from v2.features.labeling import IntradayLabeler
from v2.models.walk_forward import PurgedWalkForwardCV, WalkForwardConfig
from v2.models.estimators import (
    RidgeReturnRegressor,
    LightGBMReturnRegressor,
    CalibratedDirectionClassifier
)
from v2.risk.dynamic_cost_model import DynamicCostModel
from v2.models.edge_evaluator import (
    EdgeGateConfig,
    EdgeEvaluator,
    FoldResult,
    EdgeGateVerdict
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_phase3_pipeline():
    logger.info("================================================================================")
    logger.info("  ALPHANSE V2 — PHASE 3: 5-MINUTE SIGNAL PROVING & DYNAMIC COST STRESS GATE    ")
    logger.info("================================================================================")

    # 1. Feature Engineering
    logger.info("Step 1: Engineering Point-in-Time Features across Raw and Adjusted datasets...")
    pipeline = FeaturePipeline()
    feature_df = pipeline.compute_all_features()
    logger.info(f"Features computed: {len(ALL_FEATURE_COLUMNS)} columns across {len(feature_df)} rows.")

    # 2. Multi-Horizon Raw Execution Price Labeling
    logger.info("Step 2: Labeling Multi-Horizon Forward Raw Execution Price Returns (H in {1, 2, 3})...")
    labeler = IntradayLabeler(horizons=[1, 2, 3], cost_hurdle_bps=15.0)
    labeled_df = labeler.construct_forward_labels(feature_df)

    # Exclude benchmark ^NSEI from tradable universe (it was only used for market relative strength)
    tradable_df = labeled_df[labeled_df["symbol"] != "^NSEI"].copy().reset_index(drop=True)
    logger.info(f"Tradable universe observations: {len(tradable_df)} across {tradable_df['symbol'].nunique()} stocks.")

    # 3. Setup Walk-Forward Engine and Dynamic Cost Model
    wf_config = WalkForwardConfig(
        n_folds=5,
        min_train_sessions=25,
        val_sessions_per_fold=6,
        test_sessions_per_fold=6,
        embargo_sessions=1
    )
    cost_model = DynamicCostModel(base_half_spread_bps=1.0, base_slippage_bps=2.0)
    edge_gate_config = EdgeGateConfig(
        min_oos_trades=300,
        min_oos_sessions=20,
        min_effective_sample_size=1000.0,
        min_ic=0.03,
        min_baseline_expectancy_bps=0.0,
        min_stressed_expectancy_bps=0.0,
        min_win_rate_pct=51.5,
        max_drawdown_pct=5.0,
        min_positive_folds_pct=60.0
    )
    edge_evaluator = EdgeEvaluator(config=edge_gate_config, cost_model=cost_model)

    horizons = [
        (1, "5m", "target_return_5m"),
        (2, "10m", "target_return_10m"),
        (3, "15m", "target_return_15m")
    ]

    all_horizon_results = {}
    saved_models_dir = os.path.join("v2", "models", "saved_models_5m")
    metrics_dir = os.path.join("v2", "models", "metrics")
    os.makedirs(saved_models_dir, exist_ok=True)
    os.makedirs(metrics_dir, exist_ok=True)

    for h_bars, h_name, target_col in horizons:
        logger.info("--------------------------------------------------------------------------------")
        logger.info(f"Evaluating Horizon: H={h_bars} bars ({h_name}) | Target: {target_col}")
        logger.info("--------------------------------------------------------------------------------")

        wf_cv = PurgedWalkForwardCV(config=wf_config)
        splits = wf_cv.generate_splits(tradable_df, horizon_bars=h_bars)

        # We test three candidate architectures:
        estimators = {
            "Ridge": lambda: RidgeReturnRegressor(alpha=50.0),
            "LightGBM": lambda: LightGBMReturnRegressor(n_estimators=60, learning_rate=0.02, max_depth=3, num_leaves=7),
            "Classifier": lambda: CalibratedDirectionClassifier(n_estimators=60, learning_rate=0.02, max_depth=3, num_leaves=7)
        }

        estimator_results = {}

        for est_name, est_factory in estimators.items():
            logger.info(f"  --> Model: {est_name} ({h_name}) across {len(splits)} purged folds...")
            fold_results: List[FoldResult] = []
            oos_predictions_list = []
            all_fold_trades = []

            for split in splits:
                train_data = tradable_df.iloc[split.train_indices].copy()
                val_data = tradable_df.iloc[split.val_indices].copy()
                test_data = tradable_df.iloc[split.test_indices].copy()

                # Filter valid target rows
                train_valid = train_data.dropna(subset=[target_col] + ALL_FEATURE_COLUMNS)
                val_valid = val_data.dropna(subset=[target_col] + ALL_FEATURE_COLUMNS)
                test_valid = test_data.dropna(subset=[target_col] + ALL_FEATURE_COLUMNS)

                X_train = train_valid[ALL_FEATURE_COLUMNS].values
                y_train = train_valid[target_col].values

                X_val = val_valid[ALL_FEATURE_COLUMNS].values
                y_val = val_valid[target_col].values

                X_test = test_valid[ALL_FEATURE_COLUMNS].values
                y_test = test_valid[target_col].values

                # Instantiate and fit estimator strictly on Train
                model = est_factory()
                model.fit(X_train, y_train)

                # Calibrate / tune strictly on Validation
                model.tune_and_calibrate(X_val, y_val)

                # --- SELECT THRESHOLD ON VALIDATION (NO TEST PEEKING) ---
                if est_name == "Classifier":
                    val_probs = model.predict_proba(X_val)
                    val_preds = (val_probs - 0.5) * 0.0040
                else:
                    val_preds = model.predict(X_val)

                # Candidate quantiles for signal conviction on Validation
                candidate_quantiles = [80.0, 85.0, 90.0, 95.0, 98.0]
                best_q = 90.0
                best_val_net = -999999.0

                for q in candidate_quantiles:
                    q_theta = float(np.percentile(val_preds, q))
                    val_trade_mask = val_preds > q_theta
                    if val_trade_mask.sum() >= 10:
                        val_gross = float(np.mean(y_val[val_trade_mask]) * 10000.0)
                        val_net = val_gross - 14.7  # approximate base roundtrip cost
                        if val_net > best_val_net:
                            best_val_net = val_net
                            best_q = q

                frozen_theta = float(np.percentile(val_preds, best_q))

                # FREEZE EVERYTHING before touching Test
                model.freeze()

                # Out-of-sample predictions on Test
                if est_name == "Classifier":
                    test_probs = model.predict_proba(X_test)
                    test_preds = (test_probs - 0.5) * 0.0040
                else:
                    test_preds = model.predict(X_test)

                # Record predictions
                test_eval_df = test_valid.copy()
                test_eval_df["predicted_return"] = test_preds
                test_eval_df["fold_idx"] = split.fold_idx
                test_eval_df["frozen_theta"] = frozen_theta
                oos_predictions_list.append(test_eval_df)

                # Fold-level metrics
                valid_corr = ~np.isnan(test_preds) & ~np.isnan(y_test)
                fold_ic = float(np.corrcoef(test_preds[valid_corr], y_test[valid_corr])[0, 1]) if valid_corr.sum() > 5 else 0.0

                fold_trades = edge_evaluator.generate_hypothetical_trades(
                    test_eval_df,
                    pred_col="predicted_return",
                    true_return_col=target_col,
                    threshold_bps=frozen_theta * 10000.0,
                    direction_mode="long_only"
                )
                fold_trading_base, _ = edge_evaluator.evaluate_trading_quality(fold_trades, stress_multiplier=1.0)
                fold_trading_stress, _ = edge_evaluator.evaluate_trading_quality(fold_trades, stress_multiplier=1.5)

                all_fold_trades.append(fold_trades)

                fold_results.append(FoldResult(
                    fold_idx=split.fold_idx,
                    train_sessions=len(split.train_dates),
                    val_sessions=len(split.val_dates),
                    test_sessions=len(split.test_dates),
                    test_trades=fold_trading_base.trade_count,
                    test_ic=round(fold_ic, 4),
                    baseline_net_expectancy_bps=fold_trading_base.net_expectancy_bps,
                    stressed_net_expectancy_bps=fold_trading_stress.net_expectancy_bps,
                    win_rate_pct=fold_trading_base.win_rate_pct
                ))

            # Aggregate all OOS test observations across folds
            all_oos_df = pd.concat(oos_predictions_list, ignore_index=True)
            y_pred_all = all_oos_df["predicted_return"].values
            y_true_all = all_oos_df[target_col].values

            # Signal Quality across all test observations
            signal_metrics = edge_evaluator.evaluate_signal_quality(y_pred_all, y_true_all)

            # Aggregate all OOS hypothetical trades from frozen fold evaluations
            all_oos_trades = pd.concat(all_fold_trades, ignore_index=True) if all_fold_trades else pd.DataFrame()

            total_oos_sessions = sum(f.test_sessions for f in fold_results)
            base_trading, evaluated_trades_df = edge_evaluator.evaluate_trading_quality(
                all_oos_trades, stress_multiplier=1.0, n_sessions=total_oos_sessions
            )
            stress_trading, _ = edge_evaluator.evaluate_trading_quality(
                all_oos_trades, stress_multiplier=1.5, n_sessions=total_oos_sessions
            )
            extreme_trading, _ = edge_evaluator.evaluate_trading_quality(
                all_oos_trades, stress_multiplier=2.0, n_sessions=total_oos_sessions
            )

            # Edge Gate Evaluation
            verdict = edge_evaluator.evaluate_gate(
                signal_metrics=signal_metrics,
                baseline_trading=base_trading,
                stressed_trading=stress_trading,
                extreme_trading=extreme_trading,
                fold_results=fold_results,
                n_oos_sessions=total_oos_sessions
            )

            estimator_results[est_name] = {
                "verdict": verdict,
                "signal_metrics": signal_metrics,
                "base_trading": base_trading,
                "stress_trading": stress_trading,
                "extreme_trading": extreme_trading,
                "fold_results": fold_results
            }

            # Save the final frozen model from fold 5
            model_path = os.path.join(saved_models_dir, f"{est_name.lower()}_{h_name}.pkl")
            with open(model_path, "wb") as f:
                pickle.dump(model, f)

        all_horizon_results[h_name] = estimator_results

    # 4. Generate Comprehensive Output & Metrics JSON
    logger.info("================================================================================")
    logger.info("                    PHASE 3 EDGE EVALUATION RESULTS SUMMARY                     ")
    logger.info("================================================================================")

    serializable_results = {}
    for h_name, est_map in all_horizon_results.items():
        serializable_results[h_name] = {}
        for est_name, data in est_map.items():
            verdict: EdgeGateVerdict = data["verdict"]
            logger.info(f"[{h_name} | {est_name}] Status: {verdict.status}")
            logger.info(f"  Summary: {verdict.summary_message}")
            logger.info(f"  Signal IC (Pearson): {verdict.signal_metrics.ic_pearson:+.4f} | ESS: {verdict.signal_metrics.effective_sample_size:.1f}")
            logger.info(f"  OOS Trades: {verdict.trading_metrics.trade_count} | Base Net: {verdict.trading_metrics.net_expectancy_bps:+.2f} bps | Stressed Net: {data['stress_trading'].net_expectancy_bps:+.2f} bps")
            logger.info(f"  Win Rate: {verdict.trading_metrics.win_rate_pct:.1f}% | Max Drawdown: {verdict.trading_metrics.max_drawdown_pct:.2f}% | Profit Factor: {verdict.trading_metrics.profit_factor:.2f}")

            serializable_results[h_name][est_name] = {
                "status": verdict.status,
                "summary": verdict.summary_message,
                "signal_metrics": {
                    "ic_pearson": verdict.signal_metrics.ic_pearson,
                    "ic_spearman": verdict.signal_metrics.ic_spearman,
                    "mae": verdict.signal_metrics.mae,
                    "directional_accuracy_pct": verdict.signal_metrics.directional_accuracy_pct,
                    "n_observations": verdict.signal_metrics.n_observations,
                    "effective_sample_size": verdict.signal_metrics.effective_sample_size
                },
                "trading_metrics_base": {
                    "trade_count": verdict.trading_metrics.trade_count,
                    "gross_expectancy_bps": verdict.trading_metrics.gross_expectancy_bps,
                    "cost_expectancy_bps": verdict.trading_metrics.cost_expectancy_bps,
                    "net_expectancy_bps": verdict.trading_metrics.net_expectancy_bps,
                    "win_rate_pct": verdict.trading_metrics.win_rate_pct,
                    "profit_factor": verdict.trading_metrics.profit_factor,
                    "max_drawdown_pct": verdict.trading_metrics.max_drawdown_pct,
                    "total_net_pnl_bps": verdict.trading_metrics.total_net_pnl_bps,
                    "trades_per_session": verdict.trading_metrics.trades_per_session
                },
                "trading_metrics_stressed": {
                    "trade_count": data["stress_trading"].trade_count,
                    "gross_expectancy_bps": data["stress_trading"].gross_expectancy_bps,
                    "cost_expectancy_bps": data["stress_trading"].cost_expectancy_bps,
                    "net_expectancy_bps": data["stress_trading"].net_expectancy_bps,
                    "win_rate_pct": data["stress_trading"].win_rate_pct,
                    "profit_factor": data["stress_trading"].profit_factor,
                    "max_drawdown_pct": data["stress_trading"].max_drawdown_pct
                },
                "stress_scenarios": [
                    {
                        "multiplier": s.multiplier,
                        "label": s.label,
                        "avg_cost_bps": s.avg_cost_bps,
                        "net_expectancy_bps": s.net_expectancy_bps,
                        "win_rate_pct": s.win_rate_pct,
                        "profit_factor": s.profit_factor,
                        "max_drawdown_pct": s.max_drawdown_pct
                    }
                    for s in verdict.stress_scenarios
                ],
                "fold_results": [
                    {
                        "fold_idx": f.fold_idx,
                        "train_sessions": f.train_sessions,
                        "val_sessions": f.val_sessions,
                        "test_sessions": f.test_sessions,
                        "test_trades": f.test_trades,
                        "test_ic": f.test_ic,
                        "baseline_net_expectancy_bps": f.baseline_net_expectancy_bps,
                        "stressed_net_expectancy_bps": f.stressed_net_expectancy_bps,
                        "win_rate_pct": f.win_rate_pct
                    }
                    for f in verdict.fold_results
                ],
                "criteria_evaluations": {
                    k: {"passed": v[0], "detail": v[1]}
                    for k, v in verdict.criteria_evaluations.items()
                }
            }

    metrics_file = os.path.join(metrics_dir, "phase3_edge_results.json")
    with open(metrics_file, "w") as f:
        json.dump(serializable_results, f, indent=2)
    logger.info(f"Full results written to: {metrics_file}")


if __name__ == "__main__":
    run_phase3_pipeline()
