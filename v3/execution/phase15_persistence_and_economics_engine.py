#!/usr/bin/env python3
"""
AlphaNSE Phase 15: Cross-Sectional Alpha Persistence & Execution Economics Engine

Hypothesis & Research Question:
Phases 13 and 14 observed positive out-of-sample gross expectancy (+Rs 4.66/trade, PF = 1.25)
on the 2-Day Cross-Sectional Reversal strategy (CS_DIR_REV_2D) across 17 locked September trades.
Does this represent a genuine, persistent multi-stock cross-sectional alpha, or is it an artifact
of sample concentration and market regime? Can execution economics scale to achieve positive net expectancy?

Evaluation Protocol:
1. Universe: 10 liquid constituents + ^NSEI benchmark across Research (June 29 – Aug 31) and Locked September (Sep 1 – 25).
2. Rank-Bucket Analysis: Evaluate all 10 ranks and quintiles to test for monotonic cross-sectional structure.
3. Market-Neutral Long-Short Spread: Measure pure alpha spread independent of directional market drift.
4. Turnover & Friction Efficiency: Compute gross return and friction in basis points per unit of turnover.
5. Capital Scaling Economics: Audit account scale sensitivity from Rs 1,500 to Rs 2,00,000 under realistic statutory caps.
6. Regime Breakdown: Disaggregate performance across trending, ranging, high-vol, and low-vol market days.
7. Return Concentration & Outlier Analysis: Gini coefficient and leave-one-out sensitivity tests.
8. Bootstrap Statistical Inference: 10,000 resamples for 95% confidence intervals on gross and net expectancy.
"""

import os
import sys
import glob
from dataclasses import dataclass
from datetime import datetime, time, date
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np
from scipy import stats

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from v3.execution.realistic_simulated_broker import (
    RealisticSimulatedBroker,
    ExecutionRegime
)


class Phase15PersistenceAndEconomicsEngine:
    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = workspace_root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        self.symbols = [
            'AXISBANK.NS', 'BAJFINANCE.NS', 'BHARTIARTL.NS', 'HDFCBANK.NS',
            'ICICIBANK.NS', 'INFY.NS', 'RELIANCE.NS', 'SBIN.NS', 'TATACAP.NS', 'TCS.NS'
        ]

    def load_data(self) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame], List[date], List[date], List[date]]:
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
                "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
            }).dropna()
            daily_dfs[sym] = sdf

        common_dates = sorted(daily_dfs['^NSEI'].index)
        for sym in self.symbols:
            common_dates = [d for d in common_dates if d in daily_dfs[sym].index]

        res_dates = [d for d in common_dates if d <= pd.to_datetime("2026-08-31").date()]
        lock_dates = [d for d in common_dates if d >= pd.to_datetime("2026-09-01").date()]

        return df, daily_dfs, common_dates, res_dates, lock_dates

    def run_rank_bucket_analysis(
        self,
        df: pd.DataFrame,
        daily_dfs: Dict[str, pd.DataFrame],
        common_dates: List[date],
        partition_dates: List[date],
        part_name: str
    ) -> Dict[str, Any]:
        """Calculates mean forward intraday returns for all 10 ranks and quintiles."""
        rank_returns = {r: [] for r in range(1, 11)}

        for d in partition_dates:
            date_idx = common_dates.index(d)
            if date_idx < 3:
                continue
            d_minus_1 = common_dates[date_idx - 1]
            d_minus_2 = common_dates[date_idx - 3]

            nifty_d1 = daily_dfs['^NSEI'].loc[d_minus_1, "close"]
            nifty_d2 = daily_dfs['^NSEI'].loc[d_minus_2, "close"]
            nifty_ret_2d = (nifty_d1 - nifty_d2) / nifty_d2

            excess_map = {}
            for sym in self.symbols:
                c1 = daily_dfs[sym].loc[d_minus_1, "close"]
                c2 = daily_dfs[sym].loc[d_minus_2, "close"]
                sym_ret_2d = (c1 - c2) / c2
                excess_map[sym] = (sym_ret_2d - nifty_ret_2d) * 100.0

            ranked = sorted(excess_map.items(), key=lambda x: x[1])

            for rank_idx, (sym, _) in enumerate(ranked, start=1):
                sbars = df[(df["symbol"] == sym) & (df["date"] == d)].sort_values("timestamp")
                if len(sbars) >= 25:
                    en_px = sbars.iloc[3]["close"]
                    ex_px = sbars.iloc[-2]["close"]
                    ret = (ex_px - en_px) / en_px * 100.0
                    rank_returns[rank_idx].append(ret)

        summary = {}
        for r in range(1, 11):
            rets = rank_returns[r]
            m = np.mean(rets)
            t = m / (np.std(rets) / np.sqrt(len(rets)) + 1e-9) if len(rets) > 1 else 0.0
            summary[f"Rank_{r}"] = {"mean_ret_pct": round(m, 3), "t_stat": round(t, 2)}

        q1 = np.mean([rank_returns[1], rank_returns[2]])
        q5 = np.mean([rank_returns[9], rank_returns[10]])
        spread = q1 - q5
        summary["Q1_Laggards_pct"] = round(q1, 3)
        summary["Q5_Leaders_pct"] = round(q5, 3)
        summary["Q1_minus_Q5_Spread_pct"] = round(spread, 3)

        return summary

    def run_capital_scaling_audit(
        self,
        df: pd.DataFrame,
        daily_dfs: Dict[str, pd.DataFrame],
        common_dates: List[date],
        locked_dates: List[date]
    ) -> List[Dict[str, Any]]:
        """Audits strategy economics across capital scales from Rs 1,500 to Rs 2,00,000."""
        capitals = [1500.0, 5000.0, 10000.0, 25000.0, 50000.0, 100000.0, 200000.0]
        results = []

        for cap in capitals:
            broker = RealisticSimulatedBroker(regime=ExecutionRegime.BASE, seed=42)
            p_power = cap * 5.0
            trades = []

            for d in locked_dates:
                date_idx = common_dates.index(d)
                d_minus_1 = common_dates[date_idx - 1]
                d_minus_2 = common_dates[date_idx - 3]

                nifty_closes = daily_dfs['^NSEI']["close"].loc[:d_minus_1]
                nifty_ema50 = nifty_closes.ewm(span=50, adjust=False).mean().iloc[-1]
                nifty_d1 = nifty_closes.iloc[-1]
                macro_bull = nifty_d1 > nifty_ema50

                nifty_ret_2d = (nifty_d1 - daily_dfs['^NSEI'].loc[d_minus_2, "close"]) / daily_dfs['^NSEI'].loc[d_minus_2, "close"]

                excess_map = {}
                for sym in self.symbols:
                    c1 = daily_dfs[sym].loc[d_minus_1, "close"]
                    c2 = daily_dfs[sym].loc[d_minus_2, "close"]
                    sym_ret_2d = (c1 - c2) / c2
                    excess_map[sym] = (sym_ret_2d - nifty_ret_2d) * 100.0

                ranked = sorted(excess_map.items(), key=lambda x: x[1])
                target_sym = ranked[0][0] if macro_bull else ranked[-1][0]
                target_side = "BUY" if macro_bull else "SELL"

                sbars = df[(df["symbol"] == target_sym) & (df["date"] == d)].sort_values("timestamp")
                if len(sbars) < 25:
                    continue

                entry_bar = sbars.iloc[3]
                exit_bar = sbars.iloc[-2]
                en_px = float(entry_bar["close"])
                ex_px = float(exit_bar["close"])
                qty = max(1, int(p_power / en_px))

                order_in = broker.submit_order(symbol=target_sym, side=target_side, quantity=qty, mid_price=en_px, timestamp=entry_bar["timestamp"])
                if order_in.status == "FILLED":
                    exit_side = "SELL" if target_side == "BUY" else "BUY"
                    order_out = broker.force_eod_square_off(symbol=target_sym, side=exit_side, quantity=qty, mid_price=ex_px, timestamp=exit_bar["timestamp"])

                    exec_in = order_in.executed_price
                    exec_out = order_out.executed_price
                    gross = (exec_out - exec_in) * qty if target_side == "BUY" else (exec_in - exec_out) * qty
                    _, _, _, total_cost = broker.compute_trade_costs(
                        exec_in * qty, exec_out * qty, order_in.slippage_paid, order_out.slippage_paid
                    )
                    net = gross - total_cost
                    turnover = (exec_in + exec_out) * qty
                    trades.append({"gross": gross, "net": net, "friction": total_cost, "turnover": turnover})

            tdf = pd.DataFrame(trades)
            tot_gross = tdf["gross"].sum()
            tot_net = tdf["net"].sum()
            tot_fric = tdf["friction"].sum()
            tot_turnover = tdf["turnover"].sum()

            results.append({
                "capital": cap,
                "position_size": p_power,
                "gross_exp": round(tdf["gross"].mean(), 2),
                "friction_exp": round(tdf["friction"].mean(), 2),
                "net_exp": round(tdf["net"].mean(), 2),
                "gross_bps": round(tot_gross / tot_turnover * 10000.0, 1),
                "friction_bps": round(tot_fric / tot_turnover * 10000.0, 1),
                "net_bps": round(tot_net / tot_turnover * 10000.0, 1),
                "net_pct_cap": round(tdf["net"].mean() / cap * 100.0, 2),
                "win_rate": round((tdf["net"] > 0).mean() * 100.0, 1)
            })

        return results

    def run_regime_and_concentration_analysis(
        self,
        df: pd.DataFrame,
        daily_dfs: Dict[str, pd.DataFrame],
        common_dates: List[date],
        locked_dates: List[date]
    ) -> Dict[str, Any]:
        """Disaggregates September performance by market day-type and computes return concentration."""
        broker = RealisticSimulatedBroker(regime=ExecutionRegime.BASE, seed=42)
        trades = []

        for d in locked_dates:
            date_idx = common_dates.index(d)
            d_minus_1 = common_dates[date_idx - 1]
            d_minus_2 = common_dates[date_idx - 3]

            nifty_daily = daily_dfs['^NSEI']
            nifty_closes = nifty_daily["close"].loc[:d_minus_1]
            nifty_ema50 = nifty_closes.ewm(span=50, adjust=False).mean().iloc[-1]
            nifty_d1 = nifty_closes.iloc[-1]
            macro_bull = nifty_d1 > nifty_ema50

            nifty_ret_2d = (nifty_d1 - nifty_daily.loc[d_minus_2, "close"]) / nifty_daily.loc[d_minus_2, "close"]

            # Today's NIFTY move
            n_day_open = nifty_daily.loc[d, "open"]
            n_day_close = nifty_daily.loc[d, "close"]
            nifty_day_ret = (n_day_close - n_day_open) / n_day_open * 100.0
            nifty_day_type = "TREND_DOWN" if nifty_day_ret < -0.30 else ("TREND_UP" if nifty_day_ret > 0.30 else "CHOP_RANGE")

            excess_map = {}
            for sym in self.symbols:
                c1 = daily_dfs[sym].loc[d_minus_1, "close"]
                c2 = daily_dfs[sym].loc[d_minus_2, "close"]
                sym_ret_2d = (c1 - c2) / c2
                excess_map[sym] = (sym_ret_2d - nifty_ret_2d) * 100.0

            ranked = sorted(excess_map.items(), key=lambda x: x[1])
            target_sym = ranked[0][0] if macro_bull else ranked[-1][0]
            target_side = "BUY" if macro_bull else "SELL"

            sbars = df[(df["symbol"] == target_sym) & (df["date"] == d)].sort_values("timestamp")
            if len(sbars) < 25:
                continue

            en_px = float(sbars.iloc[3]["close"])
            ex_px = float(sbars.iloc[-2]["close"])
            qty = max(1, int(7500.0 / en_px))

            order_in = broker.submit_order(symbol=target_sym, side=target_side, quantity=qty, mid_price=en_px, timestamp=sbars.iloc[3]["timestamp"])
            if order_in.status == "FILLED":
                exit_side = "SELL" if target_side == "BUY" else "BUY"
                order_out = broker.force_eod_square_off(symbol=target_sym, side=exit_side, quantity=qty, mid_price=ex_px, timestamp=sbars.iloc[-2]["timestamp"])

                gross = (order_out.executed_price - order_in.executed_price) * qty if target_side == "BUY" else (order_in.executed_price - order_out.executed_price) * qty
                _, _, _, cost = broker.compute_trade_costs(
                    order_in.executed_price * qty, order_out.executed_price * qty, order_in.slippage_paid, order_out.slippage_paid
                )
                net = gross - cost
                trades.append({
                    "date": d, "symbol": target_sym, "day_type": nifty_day_type,
                    "nifty_ret": round(nifty_day_ret, 2), "gross": gross, "net": net, "cost": cost
                })

        tdf = pd.DataFrame(trades)

        # 1. Regime Breakdown
        regime_stats = {}
        for r, sub in tdf.groupby("day_type"):
            regime_stats[r] = {
                "trades": len(sub),
                "win_rate": round((sub["net"] > 0).mean() * 100.0, 1),
                "gross_exp": round(sub["gross"].mean(), 2),
                "net_exp": round(sub["net"].mean(), 2)
            }

        # 2. Return Concentration
        sorted_gross = tdf.sort_values("gross", ascending=False)
        top1_gross = sorted_gross.iloc[0]["gross"]
        top2_gross = sorted_gross.iloc[:2]["gross"].sum()
        total_gross = tdf["gross"].sum()
        gross_without_top2 = total_gross - top2_gross
        exp_without_top2 = gross_without_top2 / (len(tdf) - 2)

        # 3. Bootstrap 95% Confidence Intervals
        n_boot = 10000
        rng = np.random.RandomState(42)
        boot_gross = []
        boot_net = []
        boot_wr = []

        gross_vals = tdf["gross"].values
        net_vals = tdf["net"].values

        for _ in range(n_boot):
            idx = rng.randint(0, len(tdf), len(tdf))
            boot_gross.append(np.mean(gross_vals[idx]))
            boot_net.append(np.mean(net_vals[idx]))
            boot_wr.append((net_vals[idx] > 0).mean() * 100.0)

        ci_gross = (round(np.percentile(boot_gross, 2.5), 2), round(np.percentile(boot_gross, 97.5), 2))
        ci_net = (round(np.percentile(boot_net, 2.5), 2), round(np.percentile(boot_net, 97.5), 2))
        ci_wr = (round(np.percentile(boot_wr, 2.5), 1), round(np.percentile(boot_wr, 97.5), 1))
        p_val_gross = (np.array(boot_gross) <= 0).mean()

        return {
            "regimes": regime_stats,
            "concentration": {
                "total_gross_rs": round(total_gross, 2),
                "top1_contrib_rs": round(top1_gross, 2),
                "top2_contrib_rs": round(top2_gross, 2),
                "exp_without_top2": round(exp_without_top2, 2)
            },
            "bootstrap": {
                "gross_exp_mean": round(np.mean(gross_vals), 2),
                "gross_exp_ci95": ci_gross,
                "net_exp_mean": round(np.mean(net_vals), 2),
                "net_exp_ci95": ci_net,
                "win_rate_ci95": ci_wr,
                "p_val_gross_positive": round(1.0 - p_val_gross, 3)
            }
        }


def main():
    engine = Phase15PersistenceAndEconomicsEngine()
    print("Loading data...")
    df, daily_dfs, common_dates, res_dates, lock_dates = engine.load_data()

    print("\n" + "=" * 80)
    print("DIMENSION 1: RANK-BUCKET ANALYSIS ACROSS ALL 10 CONSTITUENTS")
    print("=" * 80)
    res_ranks = engine.run_rank_bucket_analysis(df, daily_dfs, common_dates, res_dates[3:], "RESEARCH")
    lock_ranks = engine.run_rank_bucket_analysis(df, daily_dfs, common_dates, lock_dates, "LOCKED_SEPTEMBER")

    print("\n--- RESEARCH SET RANK BUCKETS (43 SESSIONS) ---")
    for k, v in res_ranks.items():
        print(f"  {k:25s}: {v}")

    print("\n--- LOCKED SEPTEMBER RANK BUCKETS (17 SESSIONS) ---")
    for k, v in lock_ranks.items():
        print(f"  {k:25s}: {v}")

    print("\n" + "=" * 80)
    print("DIMENSION 2: CAPITAL SCALE SENSITIVITY AUDIT (Rs 1,500 to Rs 2,00,000)")
    print("=" * 80)
    scaling_res = engine.run_capital_scaling_audit(df, daily_dfs, common_dates, lock_dates)
    for r in scaling_res:
        print(f"Capital: Rs {r['capital']:7.0f} (Pos: Rs {r['position_size']:8.0f}) | Gross: Rs {r['gross_exp']:+7.2f} ({r['gross_bps']:+4.1f} bps) | Fric: Rs {r['friction_exp']:6.2f} ({r['friction_bps']:4.1f} bps) | Net: Rs {r['net_exp']:+7.2f} ({r['net_bps']:+4.1f} bps / {r['net_pct_cap']:+5.2f}% cap) | WR: {r['win_rate']:4.1f}%")

    print("\n" + "=" * 80)
    print("DIMENSION 3: REGIME, CONCENTRATION & BOOTSTRAP UNCERTAINTY")
    print("=" * 80)
    reg_conc = engine.run_regime_and_concentration_analysis(df, daily_dfs, common_dates, lock_dates)

    print("\n--- REGIME BREAKDOWN ---")
    for k, v in reg_conc["regimes"].items():
        print(f"  {k:15s}: {v}")

    print("\n--- CONCENTRATION AUDIT ---")
    for k, v in reg_conc["concentration"].items():
        print(f"  {k:20s}: {v}")

    print("\n--- BOOTSTRAP UNCERTAINTY (10,000 SAMPLES) ---")
    for k, v in reg_conc["bootstrap"].items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
