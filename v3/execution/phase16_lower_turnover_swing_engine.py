#!/usr/bin/env python3
"""
AlphaNSE Phase 16: Multi-Day Swing & Lower-Turnover Cross-Sectional Research Engine

Research Hypothesis:
Intraday strategies (Phases 10–15) attempted to extract small short-horizon price movements
(~15 to 40 bps) while paying an irreducible roundtrip transaction cost (~17 to 25 bps),
resulting in a structural economic deficit.

By expanding the holding horizon from intraday (1 session) to multi-day swing holding
(3 to 5 trading days), turnover is slashed by 3x–5x, while average price displacement expands
to ~180 to 250 bps. This tests whether lower-turnover portfolio selection can generate gross
movement large enough that transaction friction becomes a minor deduction rather than the
dominant determinant of P&L.

Methodological Protocol (Strictly Enforced):
1. Research Set (June 29 – August 31, 2026, 43 trading days):
   - Evaluate multi-day holding horizons (3-day vs 5-day) and lookbacks (5-day vs 10-day).
   - Test Relative Momentum vs Relative Reversal, and Unconstrained vs Macro Regime (Cash Filter).
   - Select and FREEZE the single best parameter configuration based strictly on research net return.
2. Locked September Test Set (September 1 – 25, 2026, 17 trading days):
   - Evaluate the frozen parameter configuration ONCE out-of-sample.
   - Zero parameter tuning or retroactive adjustments.
   - Realistic delivery friction modeling: 0.1% buy STT + 0.1% sell STT + exchange charges + SEBI + GST + spread + slippage (~35 bps roundtrip).
"""

import os
import sys
import glob
from dataclasses import dataclass
from datetime import datetime, time, date
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


@dataclass
class SwingCycleResult:
    cycle_id: str
    entry_date: date
    exit_date: date
    holding_days: int
    selected_symbols: List[str]
    side: str  # "LONG" or "CASH"
    macro_regime: str  # "BULL" or "BEAR"
    gross_return_pct: float
    friction_pct: float
    net_return_pct: float
    partition: str  # "RESEARCH" or "LOCKED_TEST"


class Phase16LowerTurnoverSwingEngine:
    def __init__(
        self,
        initial_capital: float = 1500.0,
        roundtrip_delivery_friction_bps: float = 35.0,  # 35 bps (0.35%)
        workspace_root: Optional[str] = None
    ):
        self.initial_capital = initial_capital
        self.friction_pct = roundtrip_delivery_friction_bps / 100.0  # 0.35%
        self.workspace_root = workspace_root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        self.symbols = [
            'AXISBANK.NS', 'BAJFINANCE.NS', 'BHARTIARTL.NS', 'HDFCBANK.NS',
            'ICICIBANK.NS', 'INFY.NS', 'RELIANCE.NS', 'SBIN.NS', 'TATACAP.NS', 'TCS.NS'
        ]

    def load_data(self) -> Tuple[pd.DataFrame, pd.Series, pd.Series, List[date], List[date], List[date]]:
        """Loads data, prepares daily price series, extracts benchmark and D-1 EMA50."""
        base_path = os.path.join(
            self.workspace_root, "v2", "data", "storage", "adjusted", "historical_5m_adjusted.parquet"
        )
        df = pd.read_parquet(base_path)

        fresh_pattern = os.path.join(
            self.workspace_root, "v2", "data", "storage", "fresh", "session_*_5m.parquet"
        )
        fresh_files = sorted(glob.glob(fresh_pattern))
        if fresh_files:
            fresh_dfs = [pd.read_parquet(f) for f in fresh_files]
            df = pd.concat([df] + fresh_dfs, ignore_index=True)

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["date"] = df["timestamp"].dt.date
        df = df.sort_values(["timestamp", "symbol"]).reset_index(drop=True)

        daily_dfs: Dict[str, pd.DataFrame] = {}
        for sym in self.symbols + ['^NSEI']:
            sdf = df[df["symbol"] == sym].groupby("date").agg({
                "open": "first", "high": "max", "low": "min", "close": "last"
            }).dropna()
            daily_dfs[sym] = sdf

        common_dates = sorted(daily_dfs['^NSEI'].index)
        for sym in self.symbols:
            common_dates = [d for d in common_dates if d in daily_dfs[sym].index]

        res_dates = [d for d in common_dates if d <= pd.to_datetime("2026-08-31").date()]
        lock_dates = [d for d in common_dates if d >= pd.to_datetime("2026-09-01").date()]

        daily_closes = pd.DataFrame({sym: [daily_dfs[sym].loc[d, 'close'] for d in common_dates] for sym in self.symbols}, index=common_dates)
        nifty_closes = pd.Series([daily_dfs['^NSEI'].loc[d, 'close'] for d in common_dates], index=common_dates)
        nifty_ema50 = nifty_closes.ewm(span=50, adjust=False).mean()

        return daily_closes, nifty_closes, nifty_ema50, common_dates, res_dates, lock_dates

    def simulate_swing_strategy(
        self,
        daily_closes: pd.DataFrame,
        nifty_closes: pd.Series,
        nifty_ema50: pd.Series,
        common_dates: List[date],
        rebal_dates: List[date],
        lookback_days: int,
        holding_days: int,
        model_type: str,  # "REVERSAL", "MOMENTUM"
        use_macro_filter: bool,
        partition_name: str
    ) -> List[SwingCycleResult]:
        """Simulates non-overlapping multi-day holding cycles with delivery friction."""
        cycles: List[SwingCycleResult] = []

        for i in range(len(rebal_dates) - 1):
            cur_d = rebal_dates[i]
            next_d = rebal_dates[i + 1]

            cur_idx = common_dates.index(cur_d)
            if cur_idx < lookback_days:
                continue
            past_d = common_dates[cur_idx - lookback_days]

            # 1. Macro Trend Check (NIFTY Close > 50 EMA)
            macro_bull = nifty_closes.loc[cur_d] > nifty_ema50.loc[cur_d]
            regime_str = "BULL" if macro_bull else "BEAR"

            # 2. Cross-Sectional Ranking over lookback L
            cur_close = daily_closes.loc[cur_d]
            past_close = daily_closes.loc[past_d]
            stock_ret_l = (cur_close - past_close) / past_close
            nifty_ret_l = (nifty_closes.loc[cur_d] - nifty_closes.loc[past_d]) / nifty_closes.loc[past_d]
            excess_l = stock_ret_l - nifty_ret_l

            ranked = excess_l.sort_values()
            bot2 = ranked.index[:2].tolist()
            top2 = ranked.index[-2:].tolist()

            target_symbols = bot2 if model_type == "REVERSAL" else top2

            # 3. Holding Return from cur_d close to next_d close
            fwd_rets = (daily_closes.loc[next_d] - cur_close) / cur_close * 100.0

            if use_macro_filter and not macro_bull:
                # Bear regime: 100% Cash preservation
                gross_ret = 0.0
                fric_ret = 0.0
                net_ret = 0.0
                side_str = "CASH"
                active_syms = []
            else:
                gross_ret = float(fwd_rets[target_symbols].mean())
                fric_ret = self.friction_pct  # 0.35% roundtrip delivery
                net_ret = gross_ret - fric_ret
                side_str = "LONG"
                active_syms = target_symbols

            cycles.append(SwingCycleResult(
                cycle_id=f"SWING_{partition_name[:3]}_{i+1:02d}",
                entry_date=cur_d,
                exit_date=next_d,
                holding_days=holding_days,
                selected_symbols=active_syms,
                side=side_str,
                macro_regime=regime_str,
                gross_return_pct=round(gross_ret, 2),
                friction_pct=round(fric_ret, 2),
                net_return_pct=round(net_ret, 2),
                partition=partition_name
            ))

        return cycles

    def run_research_phase(
        self,
        daily_closes: pd.DataFrame,
        nifty_closes: pd.Series,
        nifty_ema50: pd.Series,
        common_dates: List[date],
        res_dates: List[date]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Ablates swing models on Research Set and freezes top-performing candidate."""
        candidate_configs = [
            {"name": "SWING_REV_3D_MACRO", "H": 3, "L": 5, "model": "REVERSAL", "macro": True},
            {"name": "SWING_REV_3D_ALL", "H": 3, "L": 5, "model": "REVERSAL", "macro": False},
            {"name": "SWING_MOM_3D_MACRO", "H": 3, "L": 5, "model": "MOMENTUM", "macro": True},
            {"name": "SWING_REV_5D_MACRO", "H": 5, "L": 5, "model": "REVERSAL", "macro": True},
            {"name": "SWING_MOM_5D_MACRO", "H": 5, "L": 5, "model": "MOMENTUM", "macro": True},
        ]

        results_summary = {}
        best_cfg = candidate_configs[0]
        best_net_cum = -999.0

        for cfg in candidate_configs:
            H = cfg["H"]
            L = cfg["L"]
            rebal_dates = res_dates[L::H]

            cycles = self.simulate_swing_strategy(
                daily_closes=daily_closes,
                nifty_closes=nifty_closes,
                nifty_ema50=nifty_ema50,
                common_dates=common_dates,
                rebal_dates=rebal_dates,
                lookback_days=L,
                holding_days=H,
                model_type=cfg["model"],
                use_macro_filter=cfg["macro"],
                partition_name="RESEARCH"
            )

            n_cycles = len(cycles)
            active_cycles = [c for c in cycles if c.side == "LONG"]
            n_active = len(active_cycles)

            gross_returns = [c.gross_return_pct for c in cycles]
            net_returns = [c.net_return_pct for c in cycles]

            mean_gross = np.mean(gross_returns) if n_cycles > 0 else 0.0
            mean_net = np.mean(net_returns) if n_cycles > 0 else 0.0
            cum_gross = np.sum(gross_returns)
            cum_net = np.sum(net_returns)

            wins = [c for c in active_cycles if c.net_return_pct > 0]
            win_rate = (len(wins) / n_active * 100.0) if n_active > 0 else 0.0

            # Max Drawdown
            cum_curve = np.cumsum(net_returns)
            peak = np.maximum.accumulate(cum_curve)
            dd = peak - cum_curve
            max_dd = np.max(dd) if len(dd) > 0 else 0.0

            results_summary[cfg["name"]] = {
                "config": cfg,
                "cycles": n_cycles,
                "active_cycles": n_active,
                "win_rate": round(win_rate, 1),
                "mean_gross_pct": round(mean_gross, 2),
                "mean_net_pct": round(mean_net, 2),
                "cum_gross_pct": round(cum_gross, 2),
                "cum_net_pct": round(cum_net, 2),
                "max_dd_pct": round(max_dd, 2),
                "all_cycles": cycles
            }

            if cum_net > best_net_cum:
                best_net_cum = cum_net
                best_cfg = cfg

        return best_cfg, results_summary

    def run_locked_test_phase(
        self,
        daily_closes: pd.DataFrame,
        nifty_closes: pd.Series,
        nifty_ema50: pd.Series,
        common_dates: List[date],
        lock_dates: List[date],
        frozen_cfg: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluates the frozen swing strategy ONCE out-of-sample on locked September test set."""
        H = frozen_cfg["H"]
        L = frozen_cfg["L"]
        rebal_dates = lock_dates[::H]

        cycles = self.simulate_swing_strategy(
            daily_closes=daily_closes,
            nifty_closes=nifty_closes,
            nifty_ema50=nifty_ema50,
            common_dates=common_dates,
            rebal_dates=rebal_dates,
            lookback_days=L,
            holding_days=H,
            model_type=frozen_cfg["model"],
            use_macro_filter=frozen_cfg["macro"],
            partition_name="LOCKED_TEST"
        )

        n_cycles = len(cycles)
        active_cycles = [c for c in cycles if c.side == "LONG"]
        n_active = len(active_cycles)

        gross_returns = [c.gross_return_pct for c in cycles]
        net_returns = [c.net_return_pct for c in cycles]

        mean_gross = np.mean(gross_returns) if n_cycles > 0 else 0.0
        mean_net = np.mean(net_returns) if n_cycles > 0 else 0.0
        cum_gross = np.sum(gross_returns)
        cum_net = np.sum(net_returns)

        wins = [c for c in active_cycles if c.net_return_pct > 0]
        win_rate = (len(wins) / n_active * 100.0) if n_active > 0 else 0.0

        cum_curve = np.cumsum(net_returns)
        peak = np.maximum.accumulate(cum_curve)
        dd = peak - cum_curve
        max_dd = np.max(dd) if len(dd) > 0 else 0.0

        return {
            "frozen_config": frozen_cfg,
            "cycles": n_cycles,
            "active_cycles": n_active,
            "win_rate": round(win_rate, 1),
            "mean_gross_pct": round(mean_gross, 2),
            "mean_net_pct": round(mean_net, 2),
            "cum_gross_pct": round(cum_gross, 2),
            "cum_net_pct": round(cum_net, 2),
            "max_dd_pct": round(max_dd, 2),
            "all_cycles": cycles
        }


def main():
    engine = Phase16LowerTurnoverSwingEngine()
    print("Loading data and computing daily swing metrics...")
    daily_closes, nifty_closes, nifty_ema50, common_dates, res_dates, lock_dates = engine.load_data()

    print("\n" + "=" * 80)
    print("STEP 1 & 2: RESEARCH SET EVALUATION & PARAMETER FREEZE (June 29 - August 31, 2026)")
    print("=" * 80)
    best_cfg, res_summary = engine.run_research_phase(daily_closes, nifty_closes, nifty_ema50, common_dates, res_dates)

    for name, stats in res_summary.items():
        print(f"Model: {name:20s} | Cycles: {stats['cycles']:2d} (Act: {stats['active_cycles']:2d}) | WinRate: {stats['win_rate']:4.1f}% | MeanGross: {stats['mean_gross_pct']:+5.2f}% | MeanNet: {stats['mean_net_pct']:+5.2f}% | CumNet: {stats['cum_net_pct']:+6.2f}% | MaxDD: {stats['max_dd_pct']:5.2f}%")

    print(f"\n>>> MULTI-DAY SWING MODEL FROZEN FOR OUT-OF-SAMPLE TEST: {best_cfg['name']} <<<")

    print("\n" + "=" * 80)
    print("STEP 3: LOCKED SEPTEMBER OUT-OF-SAMPLE EVALUATION (September 1 - 25, 2026)")
    print("=" * 80)
    locked_res = engine.run_locked_test_phase(daily_closes, nifty_closes, nifty_ema50, common_dates, lock_dates, best_cfg)

    print(f"Frozen Model        : {locked_res['frozen_config']['name']}")
    print(f"Locked Cycles       : {locked_res['cycles']} (Active: {locked_res['active_cycles']})")
    print(f"Active Win Rate     : {locked_res['win_rate']}%")
    print(f"Mean Gross Return   : {locked_res['mean_gross_pct']}% per cycle")
    print(f"Mean Net Return     : {locked_res['mean_net_pct']}% per cycle")
    print(f"Cumulative Gross    : {locked_res['cum_gross_pct']}%")
    print(f"Cumulative Net      : {locked_res['cum_net_pct']}%")
    print(f"Max Drawdown        : {locked_res['max_dd_pct']}%")

    print("\n--- FORENSIC LOG OF LOCKED SEPTEMBER SWING CYCLES ---")
    for c in locked_res["all_cycles"]:
        print(f"[{c.cycle_id}] {c.entry_date} -> {c.exit_date} ({c.holding_days}d) | Side: {c.side:4s} {str(c.selected_symbols):35s} | Gross: {c.gross_return_pct:+5.2f}% | Net: {c.net_return_pct:+5.2f}% | Regime: {c.macro_regime}")


if __name__ == "__main__":
    main()
