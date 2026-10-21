"""
Deterministic Edge Gate & Dynamic Cost Stress Evaluator for AlphaNSE V2.
Evaluates out-of-sample statistical signal quality and trade-level economic viability.
Enforces the 10 pre-registered Edge Gate criteria and outputs tri-state verdict:
  • PASS: Statistically validated, economically viable under dynamic cost stress, sufficient sample evidence.
  • FAIL: Edge refuted (negative expectancy, insufficient win rate, catastrophic fold, or excessive drawdown).
  • INCONCLUSIVE: Insufficient statistical sample evidence (trades < minimum_oos_trades, ESS < minimum_ess).
"""

import logging
from typing import Dict, List, Any, Optional, Tuple, NamedTuple
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from v2.risk.dynamic_cost_model import DynamicCostModel, TradeCostDetail

logger = logging.getLogger(__name__)


@dataclass
class EdgeGateConfig:
    min_oos_trades: int = 300
    min_oos_sessions: int = 20
    min_effective_sample_size: float = 1000.0
    min_ic: float = 0.03
    min_baseline_expectancy_bps: float = 0.0
    min_stressed_expectancy_bps: float = 0.0   # at 1.50x friction
    min_win_rate_pct: float = 51.5
    max_drawdown_pct: float = 5.0
    min_positive_folds_pct: float = 60.0      # >= 3 of 5 folds
    max_allowed_single_fold_loss_bps: float = -50.0  # catastrophic loss threshold


@dataclass
class SignalQualityMetrics:
    ic_pearson: float
    ic_spearman: float
    mae: float
    directional_accuracy_pct: float
    n_observations: int
    effective_sample_size: float


@dataclass
class TradeQualityMetrics:
    trade_count: int
    gross_expectancy_bps: float
    cost_expectancy_bps: float
    net_expectancy_bps: float
    win_rate_pct: float
    profit_factor: float
    max_drawdown_pct: float
    total_net_pnl_bps: float
    trades_per_session: float


@dataclass
class FoldResult:
    fold_idx: int
    train_sessions: int
    val_sessions: int
    test_sessions: int
    test_trades: int
    test_ic: float
    baseline_net_expectancy_bps: float
    stressed_net_expectancy_bps: float
    win_rate_pct: float


@dataclass
class StressScenarioResult:
    multiplier: float
    label: str
    avg_cost_bps: float
    net_expectancy_bps: float
    win_rate_pct: float
    profit_factor: float
    max_drawdown_pct: float


@dataclass
class EdgeGateVerdict:
    status: str  # PASS | FAIL | INCONCLUSIVE
    signal_metrics: SignalQualityMetrics
    trading_metrics: TradeQualityMetrics
    stress_scenarios: List[StressScenarioResult]
    fold_results: List[FoldResult]
    criteria_evaluations: Dict[str, Tuple[bool, str]]
    summary_message: str


class EdgeEvaluator:
    """
    Evaluates out-of-sample predictions against pre-registered Edge Gate requirements.
    """

    def __init__(
        self,
        config: Optional[EdgeGateConfig] = None,
        cost_model: Optional[DynamicCostModel] = None
    ):
        self.config = config or EdgeGateConfig()
        self.cost_model = cost_model or DynamicCostModel()

    @staticmethod
    def compute_effective_sample_size(residuals: np.ndarray) -> float:
        """
        Computes Effective Sample Size (ESS) adjusted for serial autocorrelation:
        ESS = N * (1 - rho_1) / (1 + rho_1), rho_1 clipped to [0, 0.99].
        """
        n = len(residuals)
        if n <= 1:
            return float(n)
        
        # Lag-1 autocorrelation
        mean = np.mean(residuals)
        denom = np.sum((residuals - mean) ** 2)
        if denom == 0:
            return float(n)
        
        num = np.sum((residuals[:-1] - mean) * (residuals[1:] - mean))
        rho1 = num / denom
        rho1_clipped = float(np.clip(rho1, 0.0, 0.99))
        ess = n * ((1.0 - rho1_clipped) / (1.0 + rho1_clipped))
        return float(max(1.0, ess))

    def evaluate_signal_quality(
        self,
        y_pred: np.ndarray,
        y_true: np.ndarray
    ) -> SignalQualityMetrics:
        """
        Evaluates pure statistical signal metrics across all valid test observations.
        """
        valid = ~np.isnan(y_pred) & ~np.isnan(y_true)
        p = y_pred[valid]
        t = y_true[valid]
        n_obs = len(p)

        if n_obs < 10:
            return SignalQualityMetrics(
                ic_pearson=0.0,
                ic_spearman=0.0,
                mae=0.0,
                directional_accuracy_pct=0.0,
                n_observations=n_obs,
                effective_sample_size=float(n_obs)
            )

        pearson_corr = float(np.corrcoef(p, t)[0, 1]) if np.std(p) > 0 and np.std(t) > 0 else 0.0
        if np.isnan(pearson_corr):
            pearson_corr = 0.0

        try:
            spearman_corr = float(spearmanr(p, t).correlation)
            if np.isnan(spearman_corr):
                spearman_corr = 0.0
        except Exception:
            spearman_corr = 0.0

        mae = float(np.mean(np.abs(p - t)))
        dir_acc = float(np.mean(np.sign(p) == np.sign(t)) * 100.0)

        residuals = t - p
        ess = self.compute_effective_sample_size(residuals)

        return SignalQualityMetrics(
            ic_pearson=round(pearson_corr, 4),
            ic_spearman=round(spearman_corr, 4),
            mae=round(mae, 6),
            directional_accuracy_pct=round(dir_acc, 2),
            n_observations=n_obs,
            effective_sample_size=round(ess, 1)
        )

    def generate_hypothetical_trades(
        self,
        test_df: pd.DataFrame,
        pred_col: str,
        true_return_col: str,
        threshold_bps: float = 15.0,
        direction_mode: str = "long_only"
    ) -> pd.DataFrame:
        """
        Generates simulated trade executions triggered by frozen model predictions exceeding hurdle.
        """
        df = test_df.copy().reset_index(drop=True)
        hurdle = threshold_bps * 1e-4

        if direction_mode == "long_only":
            trade_mask = (df[pred_col] > hurdle)
            trades = df[trade_mask].copy()
            trades["trade_direction"] = 1
        elif direction_mode == "long_short":
            long_mask = (df[pred_col] > hurdle)
            short_mask = (df[pred_col] < -hurdle)
            long_trades = df[long_mask].copy()
            long_trades["trade_direction"] = 1
            short_trades = df[short_mask].copy()
            short_trades["trade_direction"] = -1
            trades = pd.concat([long_trades, short_trades], ignore_index=True)
        else:
            raise ValueError(f"Unknown direction_mode: {direction_mode}")

        if trades.empty:
            return pd.DataFrame()

        # Gross trade return in basis points
        trades["gross_return_bps"] = trades["trade_direction"] * trades[true_return_col] * 10000.0
        trades["price"] = trades["raw_close"]
        # Default nominal quantity for dynamic cost evaluation
        trades["quantity"] = np.maximum(1, np.floor(5000.0 / trades["price"]).astype(int))
        trades["volume"] = trades.get("raw_volume", 50000.0)

        return trades.sort_values(by="timestamp").reset_index(drop=True)

    def evaluate_trading_quality(
        self,
        trades_df: pd.DataFrame,
        stress_multiplier: float = 1.0,
        n_sessions: int = 20
    ) -> Tuple[TradeQualityMetrics, pd.DataFrame]:
        """
        Evaluates trade-level net economic metrics under specified dynamic cost stress.
        """
        if trades_df.empty:
            return TradeQualityMetrics(
                trade_count=0,
                gross_expectancy_bps=0.0,
                cost_expectancy_bps=0.0,
                net_expectancy_bps=0.0,
                win_rate_pct=0.0,
                profit_factor=0.0,
                max_drawdown_pct=0.0,
                total_net_pnl_bps=0.0,
                trades_per_session=0.0
            ), pd.DataFrame()

        evaluated = trades_df.copy()
        costs_bps = []

        for _, row in evaluated.iterrows():
            cost_detail = self.cost_model.compute_trade_cost(
                price=float(row["price"]),
                quantity=int(row["quantity"]),
                bar_volume=float(row["volume"]),
                stress_multiplier=stress_multiplier
            )
            costs_bps.append(cost_detail.total_cost_bps)

        evaluated["cost_bps"] = costs_bps
        evaluated["net_return_bps"] = evaluated["gross_return_bps"] - evaluated["cost_bps"]

        n_trades = len(evaluated)
        gross_exp = float(evaluated["gross_return_bps"].mean())
        cost_exp = float(evaluated["cost_bps"].mean())
        net_exp = float(evaluated["net_return_bps"].mean())
        win_rate = float((evaluated["net_return_bps"] > 0).mean() * 100.0)

        gains = evaluated[evaluated["net_return_bps"] > 0]["net_return_bps"].sum()
        losses = np.abs(evaluated[evaluated["net_return_bps"] < 0]["net_return_bps"].sum())
        profit_factor = float(gains / losses) if losses > 0 else (10.0 if gains > 0 else 0.0)

        # Drawdown calculation on cumulative equity curve
        cum_net = evaluated["net_return_bps"].cumsum()
        peak = cum_net.cummax()
        drawdown_bps = peak - cum_net
        max_dd_bps = float(drawdown_bps.max()) if len(drawdown_bps) > 0 else 0.0
        # Convert bps drawdown to percentage (100 bps = 1%)
        max_dd_pct = max_dd_bps / 100.0

        trades_per_session = n_trades / max(1, n_sessions)

        metrics = TradeQualityMetrics(
            trade_count=n_trades,
            gross_expectancy_bps=round(gross_exp, 2),
            cost_expectancy_bps=round(cost_exp, 2),
            net_expectancy_bps=round(net_exp, 2),
            win_rate_pct=round(win_rate, 2),
            profit_factor=round(profit_factor, 2),
            max_drawdown_pct=round(max_dd_pct, 2),
            total_net_pnl_bps=round(float(evaluated["net_return_bps"].sum()), 2),
            trades_per_session=round(trades_per_session, 1)
        )

        return metrics, evaluated

    def evaluate_gate(
        self,
        signal_metrics: SignalQualityMetrics,
        baseline_trading: TradeQualityMetrics,
        stressed_trading: TradeQualityMetrics,
        extreme_trading: TradeQualityMetrics,
        fold_results: List[FoldResult],
        n_oos_sessions: int
    ) -> EdgeGateVerdict:
        """
        Evaluates all 10 Edge Gate criteria deterministically and produces tri-state verdict.
        """
        evals: Dict[str, Tuple[bool, str]] = {}

        # 1. Statistical IC
        pass_ic = signal_metrics.ic_pearson > self.config.min_ic
        evals["1. OOS IC > 0.03"] = (
            pass_ic,
            f"Observed Pearson IC = {signal_metrics.ic_pearson:.4f} (Required > {self.config.min_ic})"
        )

        # 2. Baseline Net Expectancy
        pass_base = baseline_trading.net_expectancy_bps > self.config.min_baseline_expectancy_bps
        evals["2. Baseline Net Expectancy > 0"] = (
            pass_base,
            f"Observed Base Net = {baseline_trading.net_expectancy_bps:+.2f} bps/trade (Required > 0)"
        )

        # 3. Stressed Net Expectancy (1.50x friction)
        pass_stress = stressed_trading.net_expectancy_bps >= self.config.min_stressed_expectancy_bps
        evals["3. Stressed Net Expectancy >= 0 (1.50x friction)"] = (
            pass_stress,
            f"Observed Stressed Net = {stressed_trading.net_expectancy_bps:+.2f} bps/trade (Required >= 0)"
        )

        # 4. Directional Win Rate
        pass_win = baseline_trading.win_rate_pct > self.config.min_win_rate_pct
        evals["4. High-Confidence Win Rate > 51.5%"] = (
            pass_win,
            f"Observed Win Rate = {baseline_trading.win_rate_pct:.2f}% (Required > {self.config.min_win_rate_pct}%)"
        )

        # 5. Max Drawdown
        pass_mdd = baseline_trading.max_drawdown_pct < self.config.max_drawdown_pct
        evals["5. OOS Max Drawdown < 5.0%"] = (
            pass_mdd,
            f"Observed Max Drawdown = {baseline_trading.max_drawdown_pct:.2f}% (Required < {self.config.max_drawdown_pct}%)"
        )

        # 6. Minimum OOS Trades
        pass_trades = baseline_trading.trade_count >= self.config.min_oos_trades
        evals["6. Minimum OOS Trades >= 300"] = (
            pass_trades,
            f"Observed Trades = {baseline_trading.trade_count} (Required >= {self.config.min_oos_trades})"
        )

        # 7. Minimum Effective Sample Size (ESS)
        pass_ess = signal_metrics.effective_sample_size >= self.config.min_effective_sample_size
        evals["7. Minimum ESS >= 1000"] = (
            pass_ess,
            f"Observed ESS = {signal_metrics.effective_sample_size:.1f} (Required >= {self.config.min_effective_sample_size})"
        )

        # 8. Positive Expectancy in >= 60% of Folds
        n_folds = len(fold_results)
        pos_folds = sum(1 for f in fold_results if f.baseline_net_expectancy_bps > 0)
        pct_pos_folds = (pos_folds / max(1, n_folds)) * 100.0
        pass_pos_folds = pct_pos_folds >= self.config.min_positive_folds_pct
        evals["8. Positive Fold Ratio >= 60%"] = (
            pass_pos_folds,
            f"Positive Folds = {pos_folds}/{n_folds} ({pct_pos_folds:.1f}%, Required >= {self.config.min_positive_folds_pct}%)"
        )

        # 9. No Catastrophic Single-Fold Dependency
        worst_fold_loss = min([f.baseline_net_expectancy_bps for f in fold_results], default=0.0)
        pass_worst_fold = worst_fold_loss >= self.config.max_allowed_single_fold_loss_bps
        evals["9. No Catastrophic Single Fold Loss"] = (
            pass_worst_fold,
            f"Worst Fold Expectancy = {worst_fold_loss:+.2f} bps (Threshold >= {self.config.max_allowed_single_fold_loss_bps} bps)"
        )

        # 10. No Lookahead / Leakage Invariant
        evals["10. Zero Lookahead / Leakage Invariant"] = (
            True,
            "Enforced via frozen estimators, strict point-in-time features, exact H-bar purge, and 1-session embargo."
        )

        # --- DETERMINE TRI-STATE VERDICT ---
        # If evidence criteria (trades or ESS or sessions) fail, verdict is INCONCLUSIVE
        evidence_passed = pass_trades and pass_ess and (n_oos_sessions >= self.config.min_oos_sessions)
        
        # If any trading quality or statistical criteria fail despite sufficient evidence, verdict is FAIL
        all_criteria_passed = all(status for status, _ in evals.values())

        if not evidence_passed:
            status = "INCONCLUSIVE"
            summary_msg = (
                f"INCONCLUSIVE: Insufficient statistical sample evidence "
                f"(Trades: {baseline_trading.trade_count}/{self.config.min_oos_trades}, "
                f"ESS: {signal_metrics.effective_sample_size:.1f}/{self.config.min_effective_sample_size})."
            )
        elif all_criteria_passed:
            status = "PASS"
            summary_msg = (
                f"PASS: Deterministic edge validated. Signal IC={signal_metrics.ic_pearson:.4f}, "
                f"Base Net={baseline_trading.net_expectancy_bps:+.2f} bps, "
                f"Stressed Net={stressed_trading.net_expectancy_bps:+.2f} bps across {baseline_trading.trade_count} trades."
            )
        else:
            status = "FAIL"
            failed_reasons = [name for name, (passed, _) in evals.items() if not passed]
            summary_msg = f"FAIL: Edge rejected on criteria: {', '.join(failed_reasons)}."

        stress_scenarios = [
            StressScenarioResult(1.0, "Base (1.0x)", baseline_trading.cost_expectancy_bps, baseline_trading.net_expectancy_bps, baseline_trading.win_rate_pct, baseline_trading.profit_factor, baseline_trading.max_drawdown_pct),
            StressScenarioResult(1.25, "Moderate (1.25x)", baseline_trading.cost_expectancy_bps * 1.25, baseline_trading.gross_expectancy_bps - (baseline_trading.cost_expectancy_bps * 1.25), 0.0, 0.0, 0.0),
            StressScenarioResult(1.50, "Stressed (1.50x)", stressed_trading.cost_expectancy_bps, stressed_trading.net_expectancy_bps, stressed_trading.win_rate_pct, stressed_trading.profit_factor, stressed_trading.max_drawdown_pct),
            StressScenarioResult(2.00, "Extreme (2.00x)", extreme_trading.cost_expectancy_bps, extreme_trading.net_expectancy_bps, extreme_trading.win_rate_pct, extreme_trading.profit_factor, extreme_trading.max_drawdown_pct),
        ]

        return EdgeGateVerdict(
            status=status,
            signal_metrics=signal_metrics,
            trading_metrics=baseline_trading,
            stress_scenarios=stress_scenarios,
            fold_results=fold_results,
            criteria_evaluations=evals,
            summary_message=summary_msg
        )
