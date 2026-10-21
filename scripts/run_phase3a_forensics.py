"""
Phase 3A Forensic Signal Decomposition & Economic Recovery Runner for AlphaNSE V2.
Explores the out-of-sample empirical dataset across multiple non-orthogonal lenses:
  1. Time of Day (09:15-10:00, 10:00-11:00, 11:00-13:00, 13:00-14:30, 14:30-15:15)
  2. Constituent Symbol Breakdown (10 equities)
  3. Market Volatility Regimes (Low, Normal, High)
  4. Directionality Asymmetry (Long vs Short vs Long+Short)
  5. Signal Sparsity Frontier (P90, P95, P98, P99, P99.5 with minimum-sample rules)
  6. Multi-Horizon Expansion (5m, 10m, 15m, 30m, 60m)
  7. Execution Microstructure Sensitivity (Aggressive vs Passive vs Conservative Passive)
  8. Predefined Interactions (Time x Vol, Time x Dir, Quantile x Vol, Symbol x Quantile)
  9. Cluster-Robust Inference & Session Block Bootstrap (1,000 iterations)
"""

import os
import sys
import json
import logging
from typing import Dict, Any, List
import numpy as np
import pandas as pd

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from v2.features.feature_pipeline import FeaturePipeline, ALL_FEATURE_COLUMNS
from v2.features.labeling import IntradayLabeler
from v2.models.walk_forward import PurgedWalkForwardCV, WalkForwardConfig
from v2.models.estimators import RidgeReturnRegressor
from v2.risk.dynamic_cost_model import DynamicCostModel, ExecutionMode
from v2.risk.cost_scenarios import (
    BrokerCostConfig,
    BrokerageType,
    ScenarioType,
    CostScenario,
    CostScenarioRegistry
)
from v2.models.hypothesis import CandidateHypothesis
from v2.analysis.forensic_decomposer import ForensicDecomposer, SliceMetrics, TIME_BUCKETS
from v2.analysis.cluster_inference import SessionBlockBootstrap, ClusterRobustInference

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_phase3a_forensics():
    logger.info("================================================================================")
    logger.info("  ALPHANSE V2 — PHASE 3A: FORENSIC SIGNAL DECOMPOSITION & ECONOMIC RECOVERY    ")
    logger.info("================================================================================")

    # 1. Feature Engineering & Multi-Horizon Forward Labeling
    logger.info("Step 1: Engineering features and multi-horizon forward returns (5m to 60m)...")
    pipeline = FeaturePipeline()
    feature_df = pipeline.compute_all_features()

    labeler = IntradayLabeler(horizons=[1, 2, 3, 6, 12], cost_hurdle_bps=15.0)
    labeled_df = labeler.construct_forward_labels(feature_df)

    tradable_df = labeled_df[labeled_df["symbol"] != "^NSEI"].copy().reset_index(drop=True)
    tradable_df["date"] = pd.to_datetime(tradable_df["timestamp"]).dt.date

    # Tag volatility regime based on daily realized return variance
    daily_vol = tradable_df.groupby("date")["adj_log_return_5m"].std() * np.sqrt(75 * 252) * 100.0
    vol_map = {}
    for d, v in daily_vol.items():
        if v < 15.0:
            vol_map[d] = "LOW_VOL"
        elif v <= 20.0:
            vol_map[d] = "NORMAL_VOL"
        else:
            vol_map[d] = "HIGH_VOL"
    tradable_df["volatility_regime"] = tradable_df["date"].map(vol_map).fillna("NORMAL_VOL")

    cost_model = DynamicCostModel()
    decomposer = ForensicDecomposer(cost_model=cost_model, bootstrap_iterations=500)
    bootstrapper = SessionBlockBootstrap(n_bootstrap_iterations=1000)

    horizons = [
        (1, "5m", "target_return_5m"),
        (2, "10m", "target_return_10m"),
        (3, "15m", "target_return_15m"),
        (6, "30m", "target_return_30m"),
        (12, "60m", "target_return_60m"),
    ]

    wf_config = WalkForwardConfig(
        n_folds=5,
        min_train_sessions=25,
        val_sessions_per_fold=6,
        test_sessions_per_fold=6,
        embargo_sessions=1
    )

    horizon_eval_dfs = {}
    logger.info("Step 2: Generating out-of-sample walk-forward predictions across all horizons...")

    for h_bars, h_name, target_col in horizons:
        wf_cv = PurgedWalkForwardCV(config=wf_config)
        splits = wf_cv.generate_splits(tradable_df, horizon_bars=h_bars)

        oos_preds_list = []
        for split in splits:
            train_data = tradable_df.iloc[split.train_indices].dropna(subset=[target_col] + ALL_FEATURE_COLUMNS)
            val_data = tradable_df.iloc[split.val_indices].dropna(subset=[target_col] + ALL_FEATURE_COLUMNS)
            test_data = tradable_df.iloc[split.test_indices].dropna(subset=[target_col] + ALL_FEATURE_COLUMNS)

            model = RidgeReturnRegressor(alpha=20.0)
            model.fit(train_data[ALL_FEATURE_COLUMNS].values, train_data[target_col].values)
            model.tune_and_calibrate(val_data[ALL_FEATURE_COLUMNS].values, val_data[target_col].values)
            model.freeze()

            preds = model.predict(test_data[ALL_FEATURE_COLUMNS].values)
            test_df = test_data.copy()
            test_df["predicted_return"] = preds
            test_df["fold_idx"] = split.fold_idx
            test_df["horizon"] = h_name
            oos_preds_list.append(test_df)

        horizon_eval_dfs[h_name] = pd.concat(oos_preds_list, ignore_index=True)

    # Use 5m and 15m as core reference datasets for forensic decomposition
    eval_5m = horizon_eval_dfs["5m"]
    eval_15m = horizon_eval_dfs["15m"]
    eval_30m = horizon_eval_dfs["30m"]

    # Select high-conviction trades for 5m (top 10% predictions)
    theta_5m = float(np.percentile(eval_5m["predicted_return"], 90.0))
    trades_5m = eval_5m[eval_5m["predicted_return"] > theta_5m].copy()
    trades_5m["gross_return_bps"] = trades_5m["target_return_5m"] * 10000.0
    trades_5m["price"] = trades_5m["raw_close"]
    trades_5m["quantity"] = np.maximum(1, np.floor(5000.0 / trades_5m["price"]).astype(int))
    trades_5m["volume"] = trades_5m.get("raw_volume", 50000.0)
    trades_5m["trade_direction"] = 1

    # Select high-conviction trades for 15m
    theta_15m = float(np.percentile(eval_15m["predicted_return"], 90.0))
    trades_15m = eval_15m[eval_15m["predicted_return"] > theta_15m].copy()
    trades_15m["gross_return_bps"] = trades_15m["target_return_15m"] * 10000.0
    trades_15m["price"] = trades_15m["raw_close"]
    trades_15m["quantity"] = np.maximum(1, np.floor(5000.0 / trades_15m["price"]).astype(int))
    trades_15m["volume"] = trades_15m.get("raw_volume", 50000.0)
    trades_15m["trade_direction"] = 1

    logger.info("Step 3: Running forensic decompositions across exploratory dimensions...")

    # --- 1. TIME OF DAY DECOMPOSITION ---
    tod_metrics_5m = decomposer.run_time_of_day_analysis(trades_5m)
    tod_metrics_15m = decomposer.run_time_of_day_analysis(trades_15m)

    # --- 2. CONSTITUENT SYMBOL ATTRIBUTION ---
    symbol_metrics = decomposer.run_symbol_analysis(trades_5m)

    # --- 3. MARKET VOLATILITY REGIMES ---
    regime_metrics = decomposer.run_regime_analysis(trades_5m)

    # --- 4. DIRECTIONALITY ASYMMETRY (LONG vs SHORT vs BOTH) ---
    direction_metrics_5m = decomposer.run_directionality_analysis(
        eval_5m, pred_col="predicted_return", true_return_col="target_return_5m", threshold_bps=1.0
    )
    direction_metrics_15m = decomposer.run_directionality_analysis(
        eval_15m, pred_col="predicted_return", true_return_col="target_return_15m", threshold_bps=1.0
    )

    # --- 5. SIGNAL SPARSITY FRONTIER (P90 -> P99.5) ---
    sparsity_metrics_5m = decomposer.run_sparsity_frontier_analysis(
        eval_5m, pred_col="predicted_return", true_return_col="target_return_5m",
        quantiles=[90.0, 95.0, 98.0, 99.0, 99.5]
    )
    sparsity_metrics_15m = decomposer.run_sparsity_frontier_analysis(
        eval_15m, pred_col="predicted_return", true_return_col="target_return_15m",
        quantiles=[90.0, 95.0, 98.0, 99.0, 99.5]
    )
    sparsity_metrics_30m = decomposer.run_sparsity_frontier_analysis(
        eval_30m, pred_col="predicted_return", true_return_col="target_return_30m",
        quantiles=[90.0, 95.0, 98.0, 99.0, 99.5]
    )

    # --- 6. MULTI-HORIZON SCALING (5m, 10m, 15m, 30m, 60m) ---
    horizon_metrics = []
    for h_bars, h_name, target_col in horizons:
        h_df = horizon_eval_dfs[h_name]
        q_theta = float(np.percentile(h_df["predicted_return"], 90.0))
        h_trades = h_df[h_df["predicted_return"] > q_theta].copy()
        h_trades["gross_return_bps"] = h_trades[target_col] * 10000.0
        h_trades["price"] = h_trades["raw_close"]
        h_trades["quantity"] = np.maximum(1, np.floor(5000.0 / h_trades["price"]).astype(int))
        h_trades["volume"] = h_trades.get("raw_volume", 50000.0)
        m = decomposer.evaluate_trades_slice(h_trades, "HorizonExpansion", h_name)
        horizon_metrics.append(m)

    # --- 7. EXECUTION SENSITIVITY (Aggressive vs Passive vs Conservative Passive) ---
    exec_aggr = decomposer.evaluate_trades_slice(trades_5m, "ExecutionSensitivity", "AGGRESSIVE", ExecutionMode.AGGRESSIVE)
    exec_pass = decomposer.evaluate_trades_slice(trades_5m, "ExecutionSensitivity", "PASSIVE", ExecutionMode.PASSIVE)
    exec_cpass = decomposer.evaluate_trades_slice(trades_5m, "ExecutionSensitivity", "CONSERVATIVE_PASSIVE", ExecutionMode.CONSERVATIVE_PASSIVE)
    exec_metrics = [exec_aggr, exec_pass, exec_cpass]

    # --- 8. PREDEFINED INTERACTIONS ---
    interaction_metrics = decomposer.run_interaction_analysis(trades_5m)

    # --- 9. CLUSTER-ROBUST STATISTICAL INFERENCE ---
    clustered_stats_5m = ClusterRobustInference.compute_clustered_stats(
        trades_5m, value_col="gross_return_bps", session_col="date", symbol_col="symbol"
    )
    bootstrap_ci_5m = bootstrapper.run_session_bootstrap(trades_5m, metric_col="gross_return_bps")

    logger.info("================================================================================")
    logger.info("                 PHASE 3A FORENSIC DECOMPOSITION SUMMARY                        ")
    logger.info("================================================================================")
    logger.info(f"Total exploratory slices evaluated: {decomposer.total_slices_tested}")
    logger.info(f"Pooled Gross Expectancy: {clustered_stats_5m.observed_mean:+.2f} bps | Session SE: {clustered_stats_5m.session_clustered_se:.2f} bps | Two-Way SE: {clustered_stats_5m.twoway_clustered_se:.2f} bps")
    logger.info(f"Session Block-Bootstrap 95% CI on Gross: [{bootstrap_ci_5m.ci_lower_95:+.2f}, {bootstrap_ci_5m.ci_upper_95:+.2f}] bps (Sessions: {bootstrap_ci_5m.n_sessions})")

    # Serialize results to JSON
    output_dir = os.path.join("v2", "analysis", "metrics")
    os.makedirs(output_dir, exist_ok=True)
    results_json = os.path.join(output_dir, "phase3a_forensic_results.json")

    def serialize_slices(slices: List[SliceMetrics]) -> List[Dict[str, Any]]:
        return [
            {
                "category": s.slice_category,
                "name": s.slice_name,
                "n_trades": s.n_trades,
                "n_sessions": s.n_sessions,
                "gross_bps": s.gross_expectancy_bps,
                "cost_bps": s.cost_expectancy_bps,
                "net_bps": s.net_expectancy_bps,
                "win_rate": s.win_rate_pct,
                "profit_factor": s.profit_factor,
                "ci_net_lower": s.bootstrap_ci_net[0],
                "ci_net_upper": s.bootstrap_ci_net[1],
                "viable": s.is_statistically_viable
            }
            for s in slices
        ]

    serialized = {
        "metadata": {
            "total_slices_tested": decomposer.total_slices_tested,
            "n_sessions": int(clustered_stats_5m.n_sessions),
            "n_symbols": int(clustered_stats_5m.n_symbols),
            "n_observations": int(clustered_stats_5m.n_observations),
            "clustered_stats_gross": {
                "mean": clustered_stats_5m.observed_mean,
                "pooled_se": clustered_stats_5m.pooled_se,
                "session_se": clustered_stats_5m.session_clustered_se,
                "symbol_se": clustered_stats_5m.symbol_clustered_se,
                "twoway_se": clustered_stats_5m.twoway_clustered_se,
                "twoway_t_stat": clustered_stats_5m.twoway_t_stat
            },
            "bootstrap_ci_gross": {
                "mean": bootstrap_ci_5m.observed_mean,
                "ci_lower_95": bootstrap_ci_5m.ci_lower_95,
                "ci_upper_95": bootstrap_ci_5m.ci_upper_95,
                "std": bootstrap_ci_5m.bootstrap_std
            }
        },
        "cost_scenarios_breakdown": {
            s.value: CostScenarioRegistry.get_scenario(s).compute_total_cost_bps(5000.0)
            for s in ScenarioType
        },
        "time_of_day_5m": serialize_slices(tod_metrics_5m),
        "time_of_day_15m": serialize_slices(tod_metrics_15m),
        "symbols": serialize_slices(symbol_metrics),
        "regimes": serialize_slices(regime_metrics),
        "directionality_5m": serialize_slices(direction_metrics_5m),
        "directionality_15m": serialize_slices(direction_metrics_15m),
        "sparsity_5m": serialize_slices(sparsity_metrics_5m),
        "sparsity_15m": serialize_slices(sparsity_metrics_15m),
        "sparsity_30m": serialize_slices(sparsity_metrics_30m),
        "horizons": serialize_slices(horizon_metrics),
        "execution_sensitivity": serialize_slices(exec_metrics),
        "interactions": serialize_slices(interaction_metrics)
    }

    # --- 10. GENERATE & FREEZE CANDIDATE HYPOTHESES FOR PHASE 3B HANDOFF ---
    candidate_hypotheses = [
        CandidateHypothesis.create(
            id="HYPO_3A_001_30M_MIDDAY_TREND",
            horizon="30m",
            side="LONG_AND_SHORT",
            time_window="11:00-13:00",
            volatility_regime="NORMAL_VOL",
            signal_threshold_quantile=95.0,
            interaction_rules={"time_regime": "11:00-13:00 x NORMAL_VOL"},
            execution_scenario="BASE_AGGRESSIVE",
            minimum_trade_size=30,
            feature_columns=ALL_FEATURE_COLUMNS
        ),
        CandidateHypothesis.create(
            id="HYPO_3A_002_60M_HIGH_BETA",
            horizon="60m",
            side="LONG_AND_SHORT",
            time_window=None,
            volatility_regime="NORMAL_VOL",
            signal_threshold_quantile=90.0,
            interaction_rules={"symbols": ["BAJFINANCE.NS", "TATACAP.NS"]},
            execution_scenario="PASSIVE",
            minimum_trade_size=30,
            feature_columns=ALL_FEATURE_COLUMNS
        ),
        CandidateHypothesis.create(
            id="HYPO_3A_003_15M_SHORT_SPARSITY",
            horizon="15m",
            side="SHORT",
            time_window="09:15-10:00",
            volatility_regime="HIGH_VOL",
            signal_threshold_quantile=98.0,
            interaction_rules={"time_vol_side": "09:15-10:00 x HIGH_VOL x SHORT"},
            execution_scenario="CONSERVATIVE_PASSIVE",
            minimum_trade_size=30,
            feature_columns=ALL_FEATURE_COLUMNS
        )
    ]

    hypotheses_dir = os.path.join("v2", "models", "hypotheses")
    os.makedirs(hypotheses_dir, exist_ok=True)
    hypotheses_file = os.path.join(hypotheses_dir, "candidate_hypotheses.json")
    for hyp in candidate_hypotheses:
        hyp.save_to_file(hypotheses_file)

    serialized["candidate_hypotheses"] = [h.to_dict() for h in candidate_hypotheses]

    with open(results_json, "w") as f:
        json.dump(serialized, f, indent=2)

    logger.info(f"Phase 3A forensic metrics written to: {results_json}")
    logger.info(f"Phase 3A candidate hypotheses frozen to: {hypotheses_file}")


if __name__ == "__main__":
    run_phase3a_forensics()
