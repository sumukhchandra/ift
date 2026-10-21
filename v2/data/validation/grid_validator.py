"""
Trading Session Grid Validator & Deterministic Data Gate for AlphaNSE V2.
Verifies intraday bar integrity against a dynamic 75-bar standard NSE session grid,
detects missing/duplicate/out-of-order bars, checks price geometry,
and enforces deterministic data readiness criteria (DATA_LIMITED vs DATA_BLOCKED).
"""

import os
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, time, timedelta
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CriterionResult:
    name: str
    target: str
    actual: Any
    passed: bool
    details: str = ""


@dataclass
class SymbolQualityMetrics:
    symbol: str
    actual_bars: int
    expected_bars: int
    missing_bars: int
    missing_pct: float
    duplicate_count: int
    zero_volume_count: int
    zero_volume_pct: float
    out_of_order_count: int
    geometry_violations: int
    min_price: float
    max_price: float
    start_time: str
    end_time: str
    is_acceptable: bool


@dataclass
class DataCoverageDecision:
    status: str  # "DATA_LIMITED" or "DATA_BLOCKED"
    passed_gate: bool
    session_count: int
    total_bars: int
    symbol_count: int
    criteria_results: Dict[str, Any]
    symbol_metrics: Dict[str, Any]
    regime_breakdown: Dict[str, Any]
    evaluation_time: str


class GridValidator:
    """
    Validates empirical parquet datasets against the official NSE trading session grid.
    """

    # Deterministic Data Gate Thresholds
    MIN_SESSIONS_REQUIRED: int = 40
    MAX_MISSING_BAR_PCT: float = 5.0
    MAX_MISSING_BAR_PCT_PER_SYMBOL: float = 5.0
    MIN_SYMBOLS_REQUIRED: int = 11  # 10 equities + 1 benchmark
    MAX_DUPLICATE_PCT: float = 0.0
    MIN_BARS_PER_SYMBOL: int = 2500
    MIN_REGIMES_REQUIRED: int = 2

    def __init__(self, interval: str = "5m"):
        self.interval = interval
        self.bars_per_session = 75 if interval == "5m" else 375
        self.step_minutes = 5 if interval == "5m" else 1

    def construct_session_grid(self, trading_dates: List[pd.Timestamp]) -> pd.DatetimeIndex:
        """
        Build a complete expected intraday timestamp grid for the detected trading dates.
        09:15 to 15:25 for 5m (75 bars per day).
        09:15 to 15:29 for 1m (375 bars per day).
        """
        grid_timestamps = []
        for dt in trading_dates:
            d = dt.date()
            start_dt = pd.Timestamp(year=d.year, month=d.month, day=d.day, hour=9, minute=15, tz="Asia/Kolkata")
            for b in range(self.bars_per_session):
                grid_timestamps.append(start_dt + pd.Timedelta(minutes=b * self.step_minutes))
        return pd.DatetimeIndex(grid_timestamps)

    def validate_dataset(self, df: pd.DataFrame) -> DataCoverageDecision:
        """
        Validate an empirical dataset (combined across universe) against the trading grid
        and apply the deterministic data gate.
        """
        if df.empty:
            return DataCoverageDecision(
                status="DATA_BLOCKED",
                passed_gate=False,
                session_count=0,
                total_bars=0,
                symbol_count=0,
                criteria_results={"empty_dataset": {"passed": False, "target": "> 0 bars", "actual": 0}},
                symbol_metrics={},
                regime_breakdown={},
                evaluation_time=datetime.now().isoformat()
            )

        # Standardize timestamps
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize("Asia/Kolkata")
        else:
            df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Kolkata")

        # Discover unique trading sessions across the dataset
        df["date"] = df["timestamp"].dt.date
        unique_dates = sorted(list(df["date"].unique()))
        session_count = len(unique_dates)
        trading_date_timestamps = [pd.Timestamp(d) for d in unique_dates]

        # Generate standard expected grid for all sessions
        expected_grid = self.construct_session_grid(trading_date_timestamps)
        expected_bars_per_symbol = len(expected_grid)

        symbols = sorted(df["symbol"].unique().tolist())
        symbol_count = len(symbols)

        symbol_metrics: Dict[str, SymbolQualityMetrics] = {}
        total_missing_bars = 0
        total_duplicates = 0
        total_geometry_violations = 0
        min_symbol_bars = 999999

        for sym in symbols:
            sym_df = df[df["symbol"] == sym].sort_values(by="timestamp").reset_index(drop=True)
            actual_count = len(sym_df)
            min_symbol_bars = min(min_symbol_bars, actual_count)

            # Check duplicates
            dup_count = sym_df.duplicated(subset=["timestamp"]).sum()
            total_duplicates += dup_count

            # Check out of order
            is_sorted = sym_df["timestamp"].is_monotonic_increasing
            out_of_order = 0 if is_sorted else 1

            # Check price geometry violations
            geom_viol = (
                (sym_df["high"] < sym_df["low"]) |
                (sym_df["high"] < sym_df["open"]) |
                (sym_df["high"] < sym_df["close"]) |
                (sym_df["low"] > sym_df["open"]) |
                (sym_df["low"] > sym_df["close"])
            ).sum()
            total_geometry_violations += int(geom_viol)

            # Check zero volume
            zero_vol = (sym_df["volume"] == 0).sum()
            zero_vol_pct = (zero_vol / actual_count * 100.0) if actual_count > 0 else 0.0

            # Missing bars against standard session grid
            sym_ts_set = set(sym_df["timestamp"])
            expected_set = set(expected_grid)
            missing_bars = len(expected_set - sym_ts_set)
            total_missing_bars += missing_bars
            missing_pct = (missing_bars / expected_bars_per_symbol * 100.0) if expected_bars_per_symbol > 0 else 0.0

            # Acceptability flag for individual symbol
            is_acceptable = bool(
                missing_pct <= self.MAX_MISSING_BAR_PCT and
                dup_count == 0 and
                out_of_order == 0 and
                geom_viol == 0
            )

            metrics = SymbolQualityMetrics(
                symbol=sym,
                actual_bars=int(actual_count),
                expected_bars=int(expected_bars_per_symbol),
                missing_bars=int(missing_bars),
                missing_pct=float(round(missing_pct, 2)),
                duplicate_count=int(dup_count),
                zero_volume_count=int(zero_vol),
                zero_volume_pct=float(round(zero_vol_pct, 2)),
                out_of_order_count=int(out_of_order),
                geometry_violations=int(geom_viol),
                min_price=float(sym_df["low"].min()),
                max_price=float(sym_df["high"].max()),
                start_time=str(sym_df["timestamp"].min()),
                end_time=str(sym_df["timestamp"].max()),
                is_acceptable=is_acceptable
            )
            symbol_metrics[sym] = metrics

        total_expected_all_symbols = expected_bars_per_symbol * symbol_count
        overall_missing_pct = (total_missing_bars / total_expected_all_symbols * 100.0) if total_expected_all_symbols > 0 else 0.0

        # Volatility Regime Evaluation across sessions
        # Calculate daily annualized realized volatility from 5m log returns across the equity universe
        equities_df = df[df["symbol"] != "^NSEI"]
        session_vols: Dict[str, float] = {}
        for d, grp in equities_df.groupby("date"):
            sym_vols = []
            for sym, sgrp in grp.groupby("symbol"):
                closes = sgrp["close"].values
                if len(closes) > 1:
                    ret = np.diff(np.log(closes))
                    rv = np.sqrt(np.sum(ret**2)) * np.sqrt(252)
                    sym_vols.append(rv)
            if sym_vols:
                session_vols[str(d)] = float(np.mean(sym_vols))

        # Standard quantitative volatility regime classification:
        # LOW_VOL: < 15.0% annualized
        # NORMAL_VOL: 15.0% - 19.0% annualized
        # HIGH_VOL: > 19.0% annualized
        regime_counts = {"LOW_VOL": 0, "NORMAL_VOL": 0, "HIGH_VOL": 0}
        session_regimes: Dict[str, str] = {}
        for d_str, vol_val in session_vols.items():
            if vol_val < 0.150:
                reg = "LOW_VOL"
            elif vol_val <= 0.190:
                reg = "NORMAL_VOL"
            else:
                reg = "HIGH_VOL"
            regime_counts[reg] += 1
            session_regimes[d_str] = reg

        distinct_regimes_covered = int(sum(1 for cnt in regime_counts.values() if cnt > 0))

        # Deterministic Data Gate Evaluation
        crit_sessions = CriterionResult(
            name="minimum_sessions_required",
            target=f">= {self.MIN_SESSIONS_REQUIRED}",
            actual=int(session_count),
            passed=bool(session_count >= self.MIN_SESSIONS_REQUIRED),
            details=f"Identified {session_count} distinct NSE trading sessions"
        )
        crit_missing = CriterionResult(
            name="max_missing_bar_pct",
            target=f"<= {self.MAX_MISSING_BAR_PCT}%",
            actual=float(round(overall_missing_pct, 2)),
            passed=bool(overall_missing_pct <= self.MAX_MISSING_BAR_PCT),
            details=f"Overall grid missing rate is {overall_missing_pct:.2f}% ({total_missing_bars}/{total_expected_all_symbols} bars)"
        )
        crit_symbols = CriterionResult(
            name="min_symbols_required",
            target=f">= {self.MIN_SYMBOLS_REQUIRED}",
            actual=int(symbol_count),
            passed=bool(symbol_count >= self.MIN_SYMBOLS_REQUIRED),
            details=f"Found {symbol_count} distinct assets in universe"
        )
        crit_dups = CriterionResult(
            name="max_duplicate_pct",
            target=f"== {self.MAX_DUPLICATE_PCT}%",
            actual=float(round(total_duplicates / len(df) * 100.0, 2)),
            passed=bool(total_duplicates == 0),
            details=f"{total_duplicates} duplicate timestamps detected"
        )
        crit_bars_per_sym = CriterionResult(
            name="min_bars_per_symbol",
            target=f">= {self.MIN_BARS_PER_SYMBOL}",
            actual=int(min_symbol_bars),
            passed=bool(min_symbol_bars >= self.MIN_BARS_PER_SYMBOL),
            details=f"Minimum bars for any symbol is {min_symbol_bars}"
        )
        # Per-Symbol Missing Bar Gate
        max_sym_missing_pct = max(m.missing_pct for m in symbol_metrics.values()) if symbol_metrics else 0.0
        worst_sym = max(symbol_metrics.keys(), key=lambda s: symbol_metrics[s].missing_pct) if symbol_metrics else "None"
        all_symbols_pass_missing = bool(all(m.missing_pct <= self.MAX_MISSING_BAR_PCT_PER_SYMBOL for m in symbol_metrics.values()))

        crit_sym_missing = CriterionResult(
            name="max_missing_bar_pct_per_symbol",
            target=f"<= {self.MAX_MISSING_BAR_PCT_PER_SYMBOL}%",
            actual=float(round(max_sym_missing_pct, 2)),
            passed=bool(all_symbols_pass_missing),
            details=f"Worst symbol missing rate is {max_sym_missing_pct:.2f}% ({worst_sym}). All {symbol_count} symbols satisfy <= {self.MAX_MISSING_BAR_PCT_PER_SYMBOL}%"
        )
        crit_regimes = CriterionResult(
            name="required_regimes_covered",
            target=f">= {self.MIN_REGIMES_REQUIRED}",
            actual=int(distinct_regimes_covered),
            passed=bool(distinct_regimes_covered >= self.MIN_REGIMES_REQUIRED),
            details=f"{distinct_regimes_covered} distinct regimes: {regime_counts['LOW_VOL']} LOW_VOL, {regime_counts['NORMAL_VOL']} NORMAL_VOL, {regime_counts['HIGH_VOL']} HIGH_VOL"
        )

        all_criteria = [crit_sessions, crit_missing, crit_sym_missing, crit_symbols, crit_dups, crit_bars_per_sym, crit_regimes]
        all_passed = bool(all(c.passed for c in all_criteria))

        # Status: DATA_LIMITED if all criteria pass, else DATA_BLOCKED
        status = "DATA_LIMITED" if all_passed else "DATA_BLOCKED"

        criteria_dict = {c.name: asdict(c) for c in all_criteria}
        metrics_dict = {sym: asdict(m) for sym, m in symbol_metrics.items()}
        regime_breakdown = {
            "distinct_regimes_count": distinct_regimes_covered,
            "regime_counts": regime_counts,
            "session_regimes": session_regimes
        }

        return DataCoverageDecision(
            status=status,
            passed_gate=all_passed,
            session_count=session_count,
            total_bars=len(df),
            symbol_count=symbol_count,
            criteria_results=criteria_dict,
            symbol_metrics=metrics_dict,
            regime_breakdown=regime_breakdown,
            evaluation_time=datetime.now().isoformat()
        )
