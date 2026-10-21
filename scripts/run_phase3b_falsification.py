"""
AlphaNSE V2 — Phase 3B Candidate Hypothesis Falsification Runner.
Executes the pre-registered falsification protocol across the 3 frozen candidate hypotheses:
  - HYPO_3A_001_30M_MIDDAY_TREND (30m, Normal Vol, Midday 11:00-13:00, Base Aggressive)
  - HYPO_3A_002_60M_HIGH_BETA (60m, Normal Vol, BAJFINANCE + TATACAP, Passive)
  - HYPO_3A_003_15M_SHORT_SPARSITY (15m, High Vol, Opening 09:15-10:00, Conservative Passive)

Two Execution Modes:
  1. protocol_replay: Quarantined historical execution. Strictly prohibits certifying PASS.
  2. fresh_validation: Genuinely unseen chronological market sessions.
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timezone, date
from typing import List, Dict, Any
import numpy as np
import pandas as pd

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from v2.features.feature_pipeline import FeaturePipeline, ALL_FEATURE_COLUMNS
from v2.features.labeling import IntradayLabeler
from v2.models.walk_forward import PurgedWalkForwardCV, WalkForwardConfig
from v2.models.estimators import RidgeReturnRegressor
from v2.models.hypothesis import (
    CandidateHypothesis,
    LOCKED_PHASE3B_CANDIDATE_IDS,
    ProhibitedCandidateReplacementError,
    CandidateTamperingError
)
from v2.models.phase3b_evaluator import (
    Phase3BEvaluator,
    ValidationMode,
    CandidateEvaluationMetrics
)
from v2.risk.cost_scenarios import CostScenarioRegistry, ScenarioType

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_phase3b(mode_str: str = "protocol_replay") -> int:
    mode = ValidationMode.PROTOCOL_REPLAY if mode_str == "protocol_replay" else ValidationMode.FRESH_VALIDATION

    logger.info("=" * 80)
    logger.info("  ALPHANSE V2 — PHASE 3B: CANDIDATE HYPOTHESIS FALSIFICATION ENGINE")
    logger.info("=" * 80)
    logger.info(f"Execution Mode: {mode.value}")
    if mode == ValidationMode.PROTOCOL_REPLAY:
        logger.info("NOTE: Historical Protocol Replay Mode Active — CANNOT certify PASS or unlock Phase 4.")
    else:
        logger.info("NOTE: Fresh Validation Mode Active — Evaluating unseen chronological sessions.")
    logger.info("-" * 80)

    # 1. Load and verify frozen candidate hypotheses
    hypotheses_path = os.path.join("v2", "models", "hypotheses", "candidate_hypotheses.json")
    if not os.path.exists(hypotheses_path):
        logger.error(f"Frozen candidate hypotheses file not found: {hypotheses_path}")
        return 1

    with open(hypotheses_path, "r") as f:
        hypo_raw_list = json.load(f)

    logger.info(f"Loading {len(hypo_raw_list)} frozen candidate hypotheses from: {hypotheses_path}")
    candidates: List[CandidateHypothesis] = []
    for d in hypo_raw_list:
        try:
            hypo = CandidateHypothesis.load_from_dict(d, enforce_locked_set=True)
            candidates.append(hypo)
            logger.info(f"  Verified Candidate: {hypo.id} | Hash: {hypo.definition_hash[:16]}... | Scenario: {hypo.execution_scenario}")
        except (CandidateTamperingError, ProhibitedCandidateReplacementError) as e:
            logger.error(f"  CRITICAL SECURITY FAILURE: {e}")
            return 1

    # Verify locked candidate set match
    loaded_ids = set(c.id for c in candidates)
    if loaded_ids != LOCKED_PHASE3B_CANDIDATE_IDS:
        logger.error(f"Candidate set {loaded_ids} does not match locked set {LOCKED_PHASE3B_CANDIDATE_IDS}!")
        return 1

    # 2. Ingest Features & Generate Out-of-Sample Predictions
    logger.info("Step 2: Engineering features and multi-horizon forward returns...")
    if mode == ValidationMode.FRESH_VALIDATION:
        fresh_dir = os.path.join("v2", "data", "storage", "fresh")
        fresh_files = [
            os.path.join(fresh_dir, f) for f in os.listdir(fresh_dir)
            if f.startswith("session_") and f.endswith(".parquet")
        ]
        if fresh_files:
            logger.info(f"Combining {len(fresh_files)} fresh session files with historical base for feature pipeline continuity...")
            hist_raw = pd.read_parquet("v2/data/storage/normalized/historical_5m_raw.parquet")
            hist_adj = pd.read_parquet("v2/data/storage/adjusted/historical_5m_adjusted.parquet")
            fresh_dfs = [pd.read_parquet(f) for f in fresh_files]
            combined_fresh = pd.concat(fresh_dfs, ignore_index=True)

            all_raw = pd.concat([hist_raw, combined_fresh], ignore_index=True).drop_duplicates(subset=["symbol", "timestamp"]).sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)
            all_adj = pd.concat([hist_adj, combined_fresh], ignore_index=True).drop_duplicates(subset=["symbol", "timestamp"]).sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)

            tmp_raw = os.path.join(fresh_dir, "_eval_raw.parquet")
            tmp_adj = os.path.join(fresh_dir, "_eval_adj.parquet")
            all_raw.to_parquet(tmp_raw, index=False)
            all_adj.to_parquet(tmp_adj, index=False)
            pipeline = FeaturePipeline(raw_parquet_path=tmp_raw, adj_parquet_path=tmp_adj)
        else:
            pipeline = FeaturePipeline()
    else:
        pipeline = FeaturePipeline()

    feature_df = pipeline.compute_all_features()

    labeler = IntradayLabeler(horizons=[3, 6, 12], cost_hurdle_bps=15.0)  # 15m, 30m, 60m
    labeled_df = labeler.construct_forward_labels(feature_df)

    tradable_df = labeled_df[labeled_df["symbol"] != "^NSEI"].copy().reset_index(drop=True)
    tradable_df["date"] = pd.to_datetime(tradable_df["timestamp"]).dt.date

    # Tag volatility regime
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

    # Time of day tagging
    time_series = pd.to_datetime(tradable_df["timestamp"]).dt.time
    t1 = datetime.strptime("10:00", "%H:%M").time()
    t2 = datetime.strptime("11:00", "%H:%M").time()
    t3 = datetime.strptime("13:00", "%H:%M").time()
    t4 = datetime.strptime("14:30", "%H:%M").time()

    conditions = [
        time_series < t1,
        (time_series >= t1) & (time_series < t2),
        (time_series >= t2) & (time_series < t3),
        (time_series >= t3) & (time_series < t4),
        time_series >= t4
    ]
    choices = [
        "09:15-10:00",
        "10:00-11:00",
        "11:00-13:00",
        "13:00-14:30",
        "14:30-15:15"
    ]
    tradable_df["time_window"] = np.select(conditions, choices, default="11:00-13:00")

    # 3. Generate walk-forward out-of-sample predictions
    horizons_map = {
        "15m": (3, "target_return_15m"),
        "30m": (6, "target_return_30m"),
        "60m": (12, "target_return_60m"),
    }

    wf_config = WalkForwardConfig(
        n_folds=5,
        min_train_sessions=25,
        val_sessions_per_fold=6,
        test_sessions_per_fold=6,
        embargo_sessions=1
    )

    if mode == ValidationMode.PROTOCOL_REPLAY:
        logger.info("Step 3: Running purged walk-forward cross validation across historical candidate horizons...")
        all_oos_predictions = []

        for h_name, (h_bars, target_col) in horizons_map.items():
            wf_cv = PurgedWalkForwardCV(config=wf_config)
            splits = wf_cv.generate_splits(tradable_df, horizon_bars=h_bars)

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
                test_df["pred_ridge"] = preds
                test_df["target_return"] = test_data[target_col]
                test_df["fold"] = split.fold_idx
                test_df["horizon"] = h_name
                all_oos_predictions.append(test_df)

        combined_eval_df = pd.concat(all_oos_predictions, ignore_index=True)
    else:
        # FRESH_VALIDATION MODE:
        # Historical training data (<= 2026-09-18) -> Frozen Model -> Fresh Test Data (>= 2026-09-21)
        logger.info("Step 3: Scoring genuinely unseen fresh sessions with frozen models trained on historical data...")
        hist_cutoff = date(2026, 9, 18)
        hist_df = tradable_df[tradable_df["date"] <= hist_cutoff].copy()
        fresh_df = tradable_df[tradable_df["date"] > hist_cutoff].copy()

        if fresh_df.empty:
            logger.error("No fresh sessions (> 2026-09-18) found for evaluation!")
            return 1

        all_oos_predictions = []
        for h_name, (h_bars, target_col) in horizons_map.items():
            train_data = hist_df.dropna(subset=[target_col] + ALL_FEATURE_COLUMNS)
            test_data = fresh_df.dropna(subset=[target_col] + ALL_FEATURE_COLUMNS)

            # Fit on historical data strictly
            model = RidgeReturnRegressor(alpha=20.0)
            model.fit(train_data[ALL_FEATURE_COLUMNS].values, train_data[target_col].values)
            model.freeze()

            preds = model.predict(test_data[ALL_FEATURE_COLUMNS].values)
            test_df = test_data.copy()
            test_df["pred_ridge"] = preds
            test_df["target_return"] = test_data[target_col]
            test_df["fold"] = 1
            test_df["horizon"] = h_name
            all_oos_predictions.append(test_df)

        combined_eval_df = pd.concat(all_oos_predictions, ignore_index=True)

    # 4. Evaluate candidates
    logger.info("Step 4: Evaluating candidates against the restored 11-point Edge Gate...")
    evaluator = Phase3BEvaluator(mode=mode, bootstrap_iterations=1000, random_seed=42)
    results = evaluator.evaluate_all_candidates(candidates, combined_eval_df)

    # Print Candidate Comparison Report
    logger.info("=" * 80)
    logger.info("                   PHASE 3B CANDIDATE COMPARISON REPORT                         ")
    logger.info("=" * 80)
    table_md = evaluator.generate_comparison_table_markdown(results)
    for line in table_md.split("\n"):
        logger.info(line)
    logger.info("=" * 80)

    # Serialize results to JSON
    output_dir = os.path.join("v2", "analysis", "metrics")
    os.makedirs(output_dir, exist_ok=True)
    results_json_path = os.path.join(output_dir, "phase3b_falsification_results.json")

    results_data = {
        "metadata": {
            "mode": mode.value,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "locked_candidate_ids": list(LOCKED_PHASE3B_CANDIDATE_IDS),
            "n_candidates_evaluated": len(results)
        },
        "candidates": [
            {
                "candidate_id": r.candidate_id,
                "horizon": r.horizon,
                "execution_scenario": r.execution_scenario,
                "status": r.status,
                "gate_verdict": r.gate_verdict,
                "gross_expectancy_bps": r.gross_expectancy_bps,
                "total_cost_bps": r.total_cost_bps,
                "base_net_expectancy_bps": r.base_net_expectancy_bps,
                "stressed_net_expectancy_bps": r.stressed_net_expectancy_bps,
                "worst_fold_net_bps": r.worst_fold_net_bps,
                "ci_lower_95_bps": r.ci_lower_95_bps,
                "ci_upper_95_bps": r.ci_upper_95_bps,
                "two_way_se_bps": r.two_way_se_bps,
                "win_rate_pct": r.win_rate_pct,
                "profit_factor": r.profit_factor,
                "max_drawdown_pct": r.max_drawdown_pct,
                "ic_pearson": r.ic_pearson,
                "trades": r.trades,
                "sessions": r.sessions,
                "positive_folds": r.positive_folds,
                "folds_evaluated": r.folds_evaluated,
                "summary_message": r.summary_message,
                "criteria_evaluations": {k: {"passed": v[0], "details": v[1]} for k, v in r.criteria_evaluations.items()}
            }
            for r in results
        ]
    }

    with open(results_json_path, "w") as f:
        json.dump(results_data, f, indent=2)
    logger.info(f"Metrics written to: {results_json_path}")

    # Generate Markdown Report
    generate_markdown_report(results, mode)
    return 0


def generate_markdown_report(results: List[CandidateEvaluationMetrics], mode: ValidationMode):
    report_path = "PHASE3B_FALSIFICATION_REPORT.md"
    mode_label = "Historical Protocol Replay" if mode == ValidationMode.PROTOCOL_REPLAY else "Fresh Validation"

    lines = [
        "# ALPHANSE V2 — PHASE 3B CANDIDATE HYPOTHESIS FALSIFICATION REPORT",
        "",
        f"**Evaluation Mode**: `{mode.value}` ({mode_label})  ",
        f"**Evaluation Date**: {datetime.now(timezone.utc).strftime('%B %d, %Y')}  ",
        "**Capital Router Status**: 🔒 STRICTLY LOCKED  ",
        "**Live Execution Status**: 🔒 PHYSICALLY DISABLED (`LiveExecutionDisabledError`)  ",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        "",
        "Phase 3B was executed as a pre-registered **falsification test** across the three frozen candidate hypotheses generated during Phase 3A forensic exploration.",
        "",
    ]

    if mode == ValidationMode.PROTOCOL_REPLAY:
        lines.extend([
            "> [!IMPORTANT]",
            "> **Protocol Replay Invariant**: This report reflects a quarantined historical protocol verification across the existing 59 sessions. **It cannot certify a final PASS or unlock Phase 4 Capital Router.** Terminal validation requires genuinely unseen chronological sessions.",
            ""
        ])

    lines.extend([
        "### Candidate Comparison Summary Table",
        "",
        "| Candidate ID | Horizon | Scenario | Gross (bps) | Cost (bps) | Base Net | Stress Net | 95% CI (Net) | Win Rate | Worst Fold | Pos Folds | Trades | Sessions | Gate Verdict |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    ])

    for r in results:
        ci_str = f"[{r.ci_lower_95_bps:+.2f}, {r.ci_upper_95_bps:+.2f}]"
        lines.append(
            f"| **{r.candidate_id}** | {r.horizon} | {r.execution_scenario} | "
            f"{r.gross_expectancy_bps:+.2f} | {r.total_cost_bps:.2f} | {r.base_net_expectancy_bps:+.2f} | "
            f"{r.stressed_net_expectancy_bps:+.2f} | {ci_str} | {r.win_rate_pct:.1f}% | "
            f"{r.worst_fold_net_bps:+.2f} bps | {r.positive_folds}/{r.folds_evaluated} | "
            f"{r.trades} | {r.sessions} | **{r.status}** |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 2. Detailed 11-Point Edge Gate Criteria Breakdown",
        ""
    ])

    for r in results:
        lines.extend([
            f"### Candidate: `{r.candidate_id}`",
            f"* **Horizon**: {r.horizon} | **Scenario**: {r.execution_scenario} | **Trades**: {r.trades} | **Sessions**: {r.sessions}",
            f"* **Net Expectancy**: Base = **{r.base_net_expectancy_bps:+.2f} bps** | Stressed = **{r.stressed_net_expectancy_bps:+.2f} bps**",
            f"* **Session Block-Bootstrap 95% CI**: [{r.ci_lower_95_bps:+.2f}, {r.ci_upper_95_bps:+.2f}] bps",
            f"* **Gate Verdict**: **{r.gate_verdict}** (`{r.status}`)",
            "",
            "| # | Criterion | Passed? | Metric Details |",
            "| :-: | :--- | :---: | :--- |"
        ])
        for crit_name, (passed, details) in r.criteria_evaluations.items():
            mark = "✅ PASS" if passed else "❌ FAIL"
            lines.append(f"| {crit_name.split('.')[0]} | {crit_name} | {mark} | {details} |")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 3. Methodological Invariants Enforced",
        "",
        "1. **No Candidate Tuning / Replacement**: The candidate set was strictly locked to `HYPO_3A_001`, `HYPO_3A_002`, and `HYPO_3A_003`. All definition hashes matched their frozen records.",
        "2. **Execution Tree Cost Model**: Passive and conservative passive scenarios incorporated probability-weighted queue fill, half-spread capture, adverse selection, and partial-fill completion penalties.",
        "3. **Physical Safety Gate**: Capital Router and Live Execution remain 100% locked.",
        "",
        "---",
        "*Report generated autonomously by AlphaNSE V2 Phase 3B Falsification Engine.*",
        ""
    ])

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"Phase 3B report written to: {report_path}")

    if mode == ValidationMode.FRESH_VALIDATION:
        fresh_report_path = "PHASE3B_FRESH_VALIDATION_REPORT.md"
        with open(fresh_report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"Fresh validation report written to: {fresh_report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Phase 3B Falsification Runner")
    parser.add_argument("--mode", choices=["protocol_replay", "fresh_validation"], default="protocol_replay")
    args = parser.parse_args()
    sys.exit(run_phase3b(args.mode))
