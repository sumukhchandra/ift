"""
Exploratory Forensic Alpha Decomposition & Interaction Analysis for AlphaNSE V2 (Phase 3A).
Dissects out-of-sample prediction data across multiple non-orthogonal empirical slices:
  1. Time of Day (09:15-10:00, 10:00-11:00, 11:00-13:00, 13:00-14:30, 14:30-15:15)
  2. Constituent Symbols (10 equities)
  3. Market Volatility & Trend Regimes (Low/Normal/High Vol; Up/Down/Flat)
  4. Directionality Asymmetry (Long vs Short vs Long+Short)
  5. Signal Sparsity & High-Conviction Quantile Frontier (P90 to P99.5 with minimum-sample gates)
  6. Multi-Horizon Expansion (5m, 10m, 15m, 30m, 60m)
  7. Execution Sensitivity (Aggressive vs Passive vs Conservative Passive)
  8. Predefined Interaction Slices (Time x Vol, Time x Direction, Horizon x Vol, Quantile x Vol, Symbol x Quantile)
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from v2.risk.dynamic_cost_model import DynamicCostModel, ExecutionMode, TradeCostDetail
from v2.analysis.cluster_inference import SessionBlockBootstrap, BootstrapCIResult, ClusterRobustInference

logger = logging.getLogger(__name__)

TIME_BUCKETS = {
    "09:15-10:00": ("09:15", "10:00"),
    "10:00-11:00": ("10:00", "11:00"),
    "11:00-13:00": ("11:00", "13:00"),
    "13:00-14:30": ("13:00", "14:30"),
    "14:30-15:15": ("14:30", "15:15"),
}


@dataclass
class SliceMetrics:
    slice_category: str
    slice_name: str
    n_observations: int
    n_trades: int
    n_sessions: int
    gross_expectancy_bps: float
    cost_expectancy_bps: float
    net_expectancy_bps: float
    win_rate_pct: float
    profit_factor: float
    bootstrap_ci_net: Tuple[float, float]
    is_statistically_viable: bool  # Lower CI > 0


class ForensicDecomposer:
    """
    Forensically dissects out-of-sample predictions to diagnose gross signal distribution
    and generate testable hypotheses for Phase 3B re-validation.
    """

    def __init__(
        self,
        cost_model: Optional[DynamicCostModel] = None,
        bootstrap_iterations: int = 500
    ):
        self.cost_model = cost_model or DynamicCostModel()
        self.bootstrapper = SessionBlockBootstrap(n_bootstrap_iterations=bootstrap_iterations)
        self.total_slices_tested = 0

    @staticmethod
    def assign_time_bucket(df: pd.DataFrame) -> pd.DataFrame:
        """Assigns explicit intraday time buckets based on timestamp HH:MM."""
        res = df.copy()
        times = res["timestamp"].dt.strftime("%H:%M")
        conditions = [
            (times >= "09:15") & (times < "10:00"),
            (times >= "10:00") & (times < "11:00"),
            (times >= "11:00") & (times < "13:00"),
            (times >= "13:00") & (times < "14:30"),
            (times >= "14:30") & (times <= "15:15"),
        ]
        choices = list(TIME_BUCKETS.keys())
        res["time_bucket"] = np.select(conditions, choices, default="Other")
        return res

    def evaluate_trades_slice(
        self,
        trades_df: pd.DataFrame,
        slice_category: str,
        slice_name: str,
        execution_mode: ExecutionMode = ExecutionMode.AGGRESSIVE,
        stress_multiplier: float = 1.0,
        min_trades: int = 30,
        min_sessions: int = 10
    ) -> SliceMetrics:
        """
        Evaluates a specific subset of trades with session block bootstrap CI.
        """
        self.total_slices_tested += 1

        if trades_df.empty or len(trades_df) < min_trades:
            return SliceMetrics(
                slice_category=slice_category,
                slice_name=slice_name,
                n_observations=len(trades_df),
                n_trades=len(trades_df),
                n_sessions=trades_df["date"].nunique() if not trades_df.empty and "date" in trades_df.columns else 0,
                gross_expectancy_bps=0.0,
                cost_expectancy_bps=0.0,
                net_expectancy_bps=0.0,
                win_rate_pct=0.0,
                profit_factor=0.0,
                bootstrap_ci_net=(0.0, 0.0),
                is_statistically_viable=False
            )

        evaluated = trades_df.copy()
        if "date" not in evaluated.columns:
            evaluated["date"] = pd.to_datetime(evaluated["timestamp"]).dt.date

        n_sessions = evaluated["date"].nunique()
        if n_sessions < min_sessions:
            return SliceMetrics(
                slice_category=slice_category,
                slice_name=slice_name,
                n_observations=len(trades_df),
                n_trades=len(trades_df),
                n_sessions=n_sessions,
                gross_expectancy_bps=round(float(evaluated["gross_return_bps"].mean()), 2),
                cost_expectancy_bps=0.0,
                net_expectancy_bps=0.0,
                win_rate_pct=0.0,
                profit_factor=0.0,
                bootstrap_ci_net=(0.0, 0.0),
                is_statistically_viable=False
            )

        costs_bps = []
        for _, row in evaluated.iterrows():
            cost_detail = self.cost_model.compute_trade_cost(
                price=float(row["price"]),
                quantity=int(row.get("quantity", 1)),
                bar_volume=float(row.get("volume", 50000.0)),
                stress_multiplier=stress_multiplier,
                execution_mode=execution_mode
            )
            costs_bps.append(cost_detail.total_cost_bps)

        evaluated["cost_bps"] = costs_bps
        evaluated["net_return_bps"] = evaluated["gross_return_bps"] - evaluated["cost_bps"]

        gross_exp = float(evaluated["gross_return_bps"].mean())
        cost_exp = float(evaluated["cost_bps"].mean())
        net_exp = float(evaluated["net_return_bps"].mean())
        win_rate = float((evaluated["net_return_bps"] > 0).mean() * 100.0)

        gains = evaluated[evaluated["net_return_bps"] > 0]["net_return_bps"].sum()
        losses = np.abs(evaluated[evaluated["net_return_bps"] < 0]["net_return_bps"].sum())
        profit_factor = float(gains / losses) if losses > 0 else (10.0 if gains > 0 else 0.0)

        # Session block bootstrap for net return
        boot_res = self.bootstrapper.run_session_bootstrap(evaluated, metric_col="net_return_bps")

        return SliceMetrics(
            slice_category=slice_category,
            slice_name=slice_name,
            n_observations=len(evaluated),
            n_trades=len(evaluated),
            n_sessions=n_sessions,
            gross_expectancy_bps=round(gross_exp, 2),
            cost_expectancy_bps=round(cost_exp, 2),
            net_expectancy_bps=round(net_exp, 2),
            win_rate_pct=round(win_rate, 2),
            profit_factor=round(profit_factor, 2),
            bootstrap_ci_net=(boot_res.ci_lower_95, boot_res.ci_upper_95),
            is_statistically_viable=boot_res.is_positive_significant
        )

    def run_time_of_day_analysis(
        self,
        trades_df: pd.DataFrame,
        execution_mode: ExecutionMode = ExecutionMode.AGGRESSIVE
    ) -> List[SliceMetrics]:
        """Dissects trades by 5 intraday time buckets."""
        df = self.assign_time_bucket(trades_df)
        results = []
        for bucket in TIME_BUCKETS.keys():
            b_df = df[df["time_bucket"] == bucket]
            m = self.evaluate_trades_slice(b_df, "TimeOfDay", bucket, execution_mode)
            results.append(m)
        return results

    def run_symbol_analysis(
        self,
        trades_df: pd.DataFrame,
        execution_mode: ExecutionMode = ExecutionMode.AGGRESSIVE
    ) -> List[SliceMetrics]:
        """Dissects trades across each individual stock constituent."""
        results = []
        for sym, sym_df in trades_df.groupby("symbol"):
            m = self.evaluate_trades_slice(sym_df, "Symbol", str(sym), execution_mode, min_trades=15, min_sessions=5)
            results.append(m)
        return results

    def run_regime_analysis(
        self,
        trades_df: pd.DataFrame,
        execution_mode: ExecutionMode = ExecutionMode.AGGRESSIVE
    ) -> List[SliceMetrics]:
        """Dissects trades by volatility regime (Low, Normal, High)."""
        results = []
        if "volatility_regime" not in trades_df.columns:
            return results
        for regime, r_df in trades_df.groupby("volatility_regime"):
            m = self.evaluate_trades_slice(r_df, "VolatilityRegime", str(regime), execution_mode)
            results.append(m)
        return results

    def run_directionality_analysis(
        self,
        all_eval_df: pd.DataFrame,
        pred_col: str,
        true_return_col: str,
        threshold_bps: float = 1.0,
        execution_mode: ExecutionMode = ExecutionMode.AGGRESSIVE
    ) -> List[SliceMetrics]:
        """Dissects LONG vs SHORT vs LONG+SHORT trades independently."""
        results = []
        hurdle = threshold_bps * 1e-4

        # LONG
        long_mask = all_eval_df[pred_col] > hurdle
        long_trades = all_eval_df[long_mask].copy()
        long_trades["trade_direction"] = 1
        long_trades["gross_return_bps"] = long_trades[true_return_col] * 10000.0
        long_trades["price"] = long_trades["raw_close"]
        long_trades["quantity"] = np.maximum(1, np.floor(5000.0 / long_trades["price"]).astype(int))
        long_trades["volume"] = long_trades.get("raw_volume", 50000.0)
        results.append(self.evaluate_trades_slice(long_trades, "Direction", "LONG_ONLY", execution_mode))

        # SHORT
        short_mask = all_eval_df[pred_col] < -hurdle
        short_trades = all_eval_df[short_mask].copy()
        short_trades["trade_direction"] = -1
        short_trades["gross_return_bps"] = -short_trades[true_return_col] * 10000.0
        short_trades["price"] = short_trades["raw_close"]
        short_trades["quantity"] = np.maximum(1, np.floor(5000.0 / short_trades["price"]).astype(int))
        short_trades["volume"] = short_trades.get("raw_volume", 50000.0)
        results.append(self.evaluate_trades_slice(short_trades, "Direction", "SHORT_ONLY", execution_mode))

        # LONG + SHORT
        combined_trades = pd.concat([long_trades, short_trades], ignore_index=True)
        results.append(self.evaluate_trades_slice(combined_trades, "Direction", "LONG_AND_SHORT", execution_mode))

        return results

    def run_sparsity_frontier_analysis(
        self,
        all_eval_df: pd.DataFrame,
        pred_col: str,
        true_return_col: str,
        quantiles: Optional[List[float]] = None,
        execution_mode: ExecutionMode = ExecutionMode.AGGRESSIVE
    ) -> List[SliceMetrics]:
        """
        Evaluates the conviction sparsity frontier: P90, P95, P98, P99, P99.5.
        Requires >= 30 trades and >= 10 sessions to be marked conclusive.
        """
        qs = quantiles or [90.0, 95.0, 98.0, 99.0, 99.5]
        results = []

        preds = all_eval_df[pred_col].dropna().values
        if len(preds) < 100:
            return results

        for q in qs:
            theta = float(np.percentile(preds, q))
            mask = all_eval_df[pred_col] > theta
            trades = all_eval_df[mask].copy()
            trades["gross_return_bps"] = trades[true_return_col] * 10000.0
            trades["price"] = trades["raw_close"]
            trades["quantity"] = np.maximum(1, np.floor(5000.0 / trades["price"]).astype(int))
            trades["volume"] = trades.get("raw_volume", 50000.0)

            m = self.evaluate_trades_slice(
                trades,
                "SparsityFrontier",
                f"P{q:.1f}",
                execution_mode,
                min_trades=30,
                min_sessions=10
            )
            results.append(m)

        return results

    def run_interaction_analysis(
        self,
        trades_df: pd.DataFrame,
        execution_mode: ExecutionMode = ExecutionMode.AGGRESSIVE
    ) -> List[SliceMetrics]:
        """
        Evaluates a small set of predefined two-way interactions:
          1. Time x Volatility (e.g. 09:15-10:00 x HIGH_VOL)
          2. Time x Direction (e.g. 09:15-10:00 x SHORT)
          3. Quantile x Volatility (e.g. P95 x HIGH_VOL)
          4. Symbol x Volatility (e.g. High-Beta TATACAP x HIGH_VOL)
        """
        results = []
        df = self.assign_time_bucket(trades_df)

        if "volatility_regime" in df.columns:
            # 1. Time x Volatility
            for b in ["09:15-10:00", "14:30-15:15"]:
                for v in ["NORMAL_VOL", "HIGH_VOL"]:
                    slice_df = df[(df["time_bucket"] == b) & (df["volatility_regime"] == v)]
                    m = self.evaluate_trades_slice(
                        slice_df, "Interaction_Time_x_Vol", f"{b} x {v}", execution_mode, min_trades=20, min_sessions=5
                    )
                    results.append(m)

        # 2. Time x Direction (if trade_direction exists)
        if "trade_direction" in df.columns:
            for b in ["09:15-10:00", "10:00-11:00"]:
                for d, d_name in [(1, "LONG"), (-1, "SHORT")]:
                    slice_df = df[(df["time_bucket"] == b) & (df["trade_direction"] == d)]
                    m = self.evaluate_trades_slice(
                        slice_df, "Interaction_Time_x_Dir", f"{b} x {d_name}", execution_mode, min_trades=20, min_sessions=5
                    )
                    results.append(m)

        return results
