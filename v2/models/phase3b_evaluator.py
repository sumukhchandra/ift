"""
Phase 3B Candidate Hypothesis Falsification Engine.
Enforces strict quantitative discipline for AlphaNSE V2:
  1. Two-Stage Lifecycle:
     - PROTOCOL_REPLAY: Quarantined historical execution. CANNOT certify PASS or unlock Phase 4.
     - FRESH_VALIDATION: Unseen chronological market data evaluation.
  2. Cryptographic Integrity: Loads frozen CandidateHypothesis objects and verifies SHA-256 hashes.
  3. No-Replacement Rule: Prohibits candidate substitution or tuning during Phase 3B.
  4. Restored Full 11-Point Pre-Registered Edge Gate.
  5. Side-by-side Candidate Comparison Report generation.
"""

import os
import json
import logging
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple, NamedTuple
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, pearsonr

from v2.models.hypothesis import (
    CandidateHypothesis,
    CandidateTamperingError,
    ProhibitedCandidateReplacementError,
    LOCKED_PHASE3B_CANDIDATE_IDS
)
from v2.risk.cost_scenarios import CostScenarioRegistry, ScenarioType, CostScenario
from v2.analysis.cluster_inference import SessionBlockBootstrap, ClusterRobustInference

logger = logging.getLogger(__name__)


class ValidationMode(str, Enum):
    PROTOCOL_REPLAY = "PROTOCOL_REPLAY"        # Quarantined historical verification; cannot emit PASS
    FRESH_VALIDATION = "FRESH_VALIDATION"      # Genuinely unseen chronological sessions


@dataclass
class CandidateEvaluationMetrics:
    candidate_id: str
    horizon: str
    execution_scenario: str
    trades: int
    sessions: int
    folds_evaluated: int
    positive_folds: int
    gross_expectancy_bps: float
    total_cost_bps: float
    base_net_expectancy_bps: float
    stressed_net_expectancy_bps: float
    worst_fold_net_bps: float
    win_rate_pct: float
    profit_factor: float
    max_drawdown_pct: float
    ic_pearson: float
    ci_lower_95_bps: float
    ci_upper_95_bps: float
    two_way_se_bps: float
    criteria_evaluations: Dict[str, Tuple[bool, str]]
    status: str                                # REPLAY_FAIL | REPLAY_SURVIVED | PASS | FAIL | INCONCLUSIVE
    gate_verdict: str
    summary_message: str


class Phase3BEvaluator:
    """
    Evaluates frozen candidate hypotheses against pre-registered quantitative criteria.
    """

    def __init__(
        self,
        mode: ValidationMode = ValidationMode.PROTOCOL_REPLAY,
        bootstrap_iterations: int = 500,
        random_seed: int = 42
    ):
        self.mode = mode
        self.bootstrap_iterations = bootstrap_iterations
        self.random_seed = random_seed
        self.bootstrapper = SessionBlockBootstrap(
            n_bootstrap_iterations=bootstrap_iterations,
            random_seed=random_seed
        )

    def load_and_verify_candidate(self, candidate_dict: Dict[str, Any]) -> CandidateHypothesis:
        """Loads candidate and validates against locked set and definition hash."""
        return CandidateHypothesis.load_from_dict(candidate_dict, enforce_locked_set=True)

    def filter_candidate_trades(
        self,
        df: pd.DataFrame,
        candidate: CandidateHypothesis
    ) -> pd.DataFrame:
        """
        Applies candidate's frozen pre-registered filter rules.
        """
        sub = df.copy()

        # 1. Horizon match
        if "horizon" in sub.columns:
            sub = sub[sub["horizon"] == candidate.horizon]

        # 2. Time of day filter
        if candidate.time_window and "time_window" in sub.columns:
            sub = sub[sub["time_window"] == candidate.time_window]

        # 3. Volatility regime filter
        if candidate.volatility_regime and "volatility_regime" in sub.columns:
            sub = sub[sub["volatility_regime"] == candidate.volatility_regime]

        # 4. Symbol interaction filter
        if "symbols" in candidate.interaction_rules:
            allowed_symbols = candidate.interaction_rules["symbols"]
            sub = sub[sub["symbol"].isin(allowed_symbols)]

        # 5. Conviction threshold filter
        pred_col = "pred_ridge"
        if pred_col not in sub.columns:
            raise KeyError(f"Required prediction column '{pred_col}' not found in predictions dataframe.")

        # Compute threshold quantile
        q = candidate.signal_threshold_quantile / 100.0
        abs_preds = sub[pred_col].abs()
        if len(abs_preds) == 0:
            return pd.DataFrame()

        hurdle = float(abs_preds.quantile(q))

        # 6. Directional mode filter
        if candidate.side == "LONG":
            sub = sub[sub[pred_col] >= hurdle].copy()
            sub["trade_direction"] = 1
        elif candidate.side == "SHORT":
            sub = sub[sub[pred_col] <= -hurdle].copy()
            sub["trade_direction"] = -1
        elif candidate.side in ["LONG_AND_SHORT", "LONG_SHORT"]:
            longs = sub[sub[pred_col] >= hurdle].copy()
            longs["trade_direction"] = 1
            shorts = sub[sub[pred_col] <= -hurdle].copy()
            shorts["trade_direction"] = -1
            sub = pd.concat([longs, shorts], ignore_index=True)
        else:
            raise ValueError(f"Unknown side: {candidate.side}")

        if sub.empty:
            return pd.DataFrame()

        # Compute trade gross return in bps
        true_col = "target_return"
        if true_col not in sub.columns:
            raise KeyError(f"Required target return column '{true_col}' not found.")

        sub["gross_return_bps"] = sub["trade_direction"] * sub[true_col] * 10000.0
        sub["date"] = pd.to_datetime(sub["timestamp"]).dt.date
        return sub.sort_values(by="timestamp").reset_index(drop=True)

    def evaluate_candidate(
        self,
        candidate: CandidateHypothesis,
        predictions_df: pd.DataFrame
    ) -> CandidateEvaluationMetrics:
        """
        Evaluates a single frozen candidate hypothesis against the restored 11-point Edge Gate.
        """
        if candidate.id not in LOCKED_PHASE3B_CANDIDATE_IDS:
            raise ProhibitedCandidateReplacementError(
                f"Candidate {candidate.id} is not in the locked Phase 3B candidate set: {sorted(list(LOCKED_PHASE3B_CANDIDATE_IDS))}. "
                "Candidate substitution during Phase 3B is strictly prohibited."
            )

        candidate.verify_integrity()

        filtered_trades = self.filter_candidate_trades(predictions_df, candidate)

        # Get scenario cost
        scenario_type = ScenarioType(candidate.execution_scenario)
        cost_scenario = CostScenarioRegistry.get_scenario(scenario_type)
        cost_dict = cost_scenario.compute_total_cost_bps(notional=5000.0)

        base_cost_bps = cost_dict["cost_per_completed_trade_bps"]
        # Stressed cost is base statutory + 1.5x execution friction
        stressed_exec_friction = cost_dict["execution_friction_bps"] * 1.5
        stressed_cost_bps = round(cost_dict["statutory_bps"] + stressed_exec_friction, 2)

        if filtered_trades.empty or len(filtered_trades) < 5:
            n_trades = len(filtered_trades)
            empty_evals = {
                "Sample Size": (False, f"Insufficient trades ({n_trades} < {candidate.minimum_trade_size})")
            }
            if self.mode == ValidationMode.FRESH_VALIDATION:
                status = "INCONCLUSIVE_NO_ELIGIBLE_TRADES" if n_trades == 0 else "INCONCLUSIVE"
                gate_verdict = "INCONCLUSIVE"
                summary_message = (
                    "No eligible trades triggered today (regime/conviction conditions not met). Awaiting subsequent sessions."
                    if n_trades == 0 else f"Insufficient trade samples ({n_trades} < {candidate.minimum_trade_size}). Accumulating sessions."
                )
            else:
                status = "REPLAY_FAIL" if n_trades == 0 else "INCONCLUSIVE"
                gate_verdict = "FAIL" if n_trades == 0 else "INCONCLUSIVE"
                summary_message = "Insufficient trade samples after filtering in historical replay."

            return CandidateEvaluationMetrics(
                candidate_id=candidate.id,
                horizon=candidate.horizon,
                execution_scenario=candidate.execution_scenario,
                trades=n_trades,
                sessions=0,
                folds_evaluated=0,
                positive_folds=0,
                gross_expectancy_bps=0.0,
                total_cost_bps=base_cost_bps,
                base_net_expectancy_bps=-base_cost_bps if n_trades > 0 else 0.0,
                stressed_net_expectancy_bps=-stressed_cost_bps if n_trades > 0 else 0.0,
                worst_fold_net_bps=-999.0,
                win_rate_pct=0.0,
                profit_factor=0.0,
                max_drawdown_pct=0.0,
                ic_pearson=0.0,
                ci_lower_95_bps=-999.0,
                ci_upper_95_bps=-999.0,
                two_way_se_bps=0.0,
                criteria_evaluations=empty_evals,
                status=status,
                gate_verdict=gate_verdict,
                summary_message=summary_message
            )

        # Net returns
        filtered_trades["cost_bps"] = base_cost_bps
        filtered_trades["net_return_bps"] = filtered_trades["gross_return_bps"] - base_cost_bps
        filtered_trades["stressed_net_return_bps"] = filtered_trades["gross_return_bps"] - stressed_cost_bps

        n_trades = len(filtered_trades)
        n_sessions = filtered_trades["date"].nunique()
        gross_exp = float(filtered_trades["gross_return_bps"].mean())
        base_net_exp = float(filtered_trades["net_return_bps"].mean())
        stressed_net_exp = float(filtered_trades["stressed_net_return_bps"].mean())
        win_rate = float((filtered_trades["net_return_bps"] > 0).mean() * 100.0)

        gains = filtered_trades[filtered_trades["net_return_bps"] > 0]["net_return_bps"].sum()
        losses = np.abs(filtered_trades[filtered_trades["net_return_bps"] < 0]["net_return_bps"].sum())
        profit_factor = float(gains / losses) if losses > 0 else (10.0 if gains > 0 else 0.0)

        # Max drawdown
        cum_net = filtered_trades["net_return_bps"].cumsum()
        peak = cum_net.cummax()
        max_dd_bps = float((peak - cum_net).max()) if len(cum_net) > 0 else 0.0
        max_dd_pct = max_dd_bps / 100.0

        # Pearson IC on trades
        if "target_return" in filtered_trades.columns and "pred_ridge" in filtered_trades.columns:
            r_val, _ = pearsonr(filtered_trades["pred_ridge"], filtered_trades["target_return"])
            ic_val = float(r_val) if not np.isnan(r_val) else 0.0
        else:
            ic_val = 0.0

        # Per-fold analysis
        fold_col = "fold" if "fold" in filtered_trades.columns else "fold_idx"
        fold_results = []
        if fold_col in filtered_trades.columns:
            for f_val, f_grp in filtered_trades.groupby(fold_col):
                fold_net = float(f_grp["net_return_bps"].mean())
                fold_results.append(fold_net)

        n_folds = len(fold_results) if fold_results else 1
        pos_folds = sum(1 for fn in fold_results if fn > 0) if fold_results else (1 if base_net_exp > 0 else 0)
        worst_fold_net = min(fold_results) if fold_results else base_net_exp

        # Bootstrap 95% CI on net return
        boot_res = self.bootstrapper.run_session_bootstrap(filtered_trades, metric_col="net_return_bps")
        ci_lower = boot_res.ci_lower_95
        ci_upper = boot_res.ci_upper_95

        # Two-way clustered SE
        cluster_stats = ClusterRobustInference.compute_clustered_stats(
            filtered_trades,
            value_col="net_return_bps",
            session_col="date",
            symbol_col="symbol" if "symbol" in filtered_trades.columns else "date"
        )
        two_way_se = cluster_stats.twoway_clustered_se

        # --- EVALUATE THE 11 RESTORED PRE-REGISTERED CRITERIA ---
        evals: Dict[str, Tuple[bool, str]] = {}

        # 1. Mean Baseline Net Expectancy > 0
        pass_base = base_net_exp > 0.0
        evals["1. Mean Baseline Net Expectancy > 0"] = (
            pass_base,
            f"Observed = {base_net_exp:+.2f} bps (Threshold > 0.00 bps)"
        )

        # 2. Mean Stressed Net Expectancy >= 0
        pass_stress = stressed_net_exp >= 0.0
        evals["2. Mean Stressed Net Expectancy >= 0"] = (
            pass_stress,
            f"Observed = {stressed_net_exp:+.2f} bps (Threshold >= 0.00 bps under 1.5x friction)"
        )

        # 3. Session-Bootstrap 95% CI Lower Bound > 0
        pass_ci = ci_lower > 0.0
        evals["3. Session Bootstrap 95% CI Lower Bound > 0"] = (
            pass_ci,
            f"Observed 95% CI = [{ci_lower:+.2f}, {ci_upper:+.2f}] bps"
        )

        # 4. Positive Net Expectancy in >= 60% of Folds
        pct_pos = (pos_folds / max(1, n_folds)) * 100.0
        pass_folds = pct_pos >= 60.0 and pos_folds >= 3 if n_folds >= 5 else (pct_pos >= 60.0)
        evals["4. Positive Net Expectancy in >= 60% Folds"] = (
            pass_folds,
            f"Positive Folds = {pos_folds}/{n_folds} ({pct_pos:.1f}%, Threshold >= 60%)"
        )

        # 5. No Catastrophic Fold (Worst fold >= -scenario_cost_bps)
        # Guarantees fold average gross return >= 0.0 bps
        catastrophic_threshold = -base_cost_bps
        pass_no_catastrophic = worst_fold_net >= catastrophic_threshold
        evals["5. No Catastrophic Fold (Worst Fold >= -Cost)"] = (
            pass_no_catastrophic,
            f"Worst Fold Net = {worst_fold_net:+.2f} bps (Threshold >= {catastrophic_threshold:.2f} bps)"
        )

        # 6. OOS Maximum Drawdown < 5.0%
        pass_mdd = max_dd_pct < 5.0
        evals["6. Maximum Drawdown < 5.0%"] = (
            pass_mdd,
            f"Observed Max Drawdown = {max_dd_pct:.2f}% (Threshold < 5.0%)"
        )

        # 7. High-Confidence Directional Win Rate > 51.5%
        pass_win = win_rate > 51.5
        evals["7. Directional Win Rate > 51.5%"] = (
            pass_win,
            f"Observed Win Rate = {win_rate:.2f}% (Threshold > 51.5%)"
        )

        # 8. Out-of-Sample IC >= 0.030
        pass_ic = ic_val >= 0.030
        evals["8. Out-of-Sample IC >= 0.030"] = (
            pass_ic,
            f"Observed Pearson IC = {ic_val:.4f} (Threshold >= 0.0300)"
        )

        # 9. Trade Count >= 30
        pass_trades = n_trades >= candidate.minimum_trade_size
        evals["9. Sample Trade Count >= 30"] = (
            pass_trades,
            f"Observed Trades = {n_trades} (Threshold >= {candidate.minimum_trade_size})"
        )

        # 10. Session Count >= 10
        pass_sessions = n_sessions >= 10
        evals["10. Sample Session Count >= 10"] = (
            pass_sessions,
            f"Observed Sessions = {n_sessions} (Threshold >= 10)"
        )

        # 11. Multi-Fold Coverage >= 3 folds
        pass_multifold = n_folds >= 3
        evals["11. Multi-Fold Coverage >= 3 Folds"] = (
            pass_multifold,
            f"Observed Folds = {n_folds} (Threshold >= 3)"
        )

        all_11_passed = all(status for status, _ in evals.values())
        evidence_adequate = pass_trades and pass_sessions and pass_multifold

        # Determine Status under Mode Guard
        if not evidence_adequate:
            gate_verdict = "INCONCLUSIVE"
            status = "INCONCLUSIVE"
            msg = f"INCONCLUSIVE: Insufficient statistical sample evidence (Trades={n_trades}, Sessions={n_sessions})."
        elif all_11_passed:
            gate_verdict = "PASS"
            if self.mode == ValidationMode.PROTOCOL_REPLAY:
                status = "REPLAY_SURVIVED_FOR_UNSEEN_TEST"
                msg = (
                    "HISTORICAL PROTOCOL REPLAY: Candidate satisfied all 11 criteria on historical replay. "
                    "CANNOT CERTIFY FINAL PASS (Contaminated Sample). Awaiting unseen sessions."
                )
            else:
                status = "PASS"
                msg = "PASS: Candidate validated on unseen chronological sessions under strict 11-point Edge Gate."
        else:
            gate_verdict = "FAIL"
            status = "FAIL" if self.mode == ValidationMode.FRESH_VALIDATION else "REPLAY_FAIL"
            failed_criteria = [name for name, (p, _) in evals.items() if not p]
            msg = f"FAIL: Candidate rejected on criteria: {', '.join(failed_criteria)}."

        return CandidateEvaluationMetrics(
            candidate_id=candidate.id,
            horizon=candidate.horizon,
            execution_scenario=candidate.execution_scenario,
            trades=n_trades,
            sessions=n_sessions,
            folds_evaluated=n_folds,
            positive_folds=pos_folds,
            gross_expectancy_bps=round(gross_exp, 2),
            total_cost_bps=round(base_cost_bps, 2),
            base_net_expectancy_bps=round(base_net_exp, 2),
            stressed_net_expectancy_bps=round(stressed_net_exp, 2),
            worst_fold_net_bps=round(worst_fold_net, 2),
            win_rate_pct=round(win_rate, 2),
            profit_factor=round(profit_factor, 2),
            max_drawdown_pct=round(max_dd_pct, 2),
            ic_pearson=round(ic_val, 4),
            ci_lower_95_bps=round(ci_lower, 2),
            ci_upper_95_bps=round(ci_upper, 2),
            two_way_se_bps=round(two_way_se, 2),
            criteria_evaluations=evals,
            status=status,
            gate_verdict=gate_verdict,
            summary_message=msg
        )

    def evaluate_all_candidates(
        self,
        candidates: List[CandidateHypothesis],
        predictions_df: pd.DataFrame
    ) -> List[CandidateEvaluationMetrics]:
        """
        Evaluates all locked candidate hypotheses and validates against prohibited replacements.
        """
        candidate_ids = set(c.id for c in candidates)
        if candidate_ids != LOCKED_PHASE3B_CANDIDATE_IDS:
            raise ProhibitedCandidateReplacementError(
                f"Candidate set {candidate_ids} does not match locked Phase 3B set: {LOCKED_PHASE3B_CANDIDATE_IDS}."
            )

        results = []
        for c in candidates:
            res = self.evaluate_candidate(c, predictions_df)
            results.append(res)
        return results

    def generate_comparison_table_markdown(self, results: List[CandidateEvaluationMetrics]) -> str:
        """Generates side-by-side Candidate Comparison Report table in markdown."""
        lines = [
            "| Candidate ID | Horizon | Scenario | Gross (bps) | Cost (bps) | Base Net | Stress Net | 95% CI (Net) | Win Rate | Worst Fold | Pos Folds | Trades | Sessions | Replay Verdict |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
        ]
        for r in results:
            ci_str = f"[{r.ci_lower_95_bps:+.2f}, {r.ci_upper_95_bps:+.2f}]"
            lines.append(
                f"| **{r.candidate_id}** | {r.horizon} | {r.execution_scenario} | "
                f"{r.gross_expectancy_bps:+.2f} | {r.total_cost_bps:.2f} | {r.base_net_expectancy_bps:+.2f} | "
                f"{r.stressed_net_expectancy_bps:+.2f} | {ci_str} | {r.win_rate_pct:.1f}% | "
                f"{r.worst_fold_net_bps:+.2f} bps | {r.positive_folds}/{r.folds_evaluated} | "
                f"{r.trades} | {r.sessions} | **{r.status}** |"
            )
        return "\n".join(lines)
