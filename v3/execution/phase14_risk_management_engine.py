#!/usr/bin/env python3
"""
AlphaNSE Phase 14: Cross-Sectional Risk Management & Tail-Loss Mitigation Engine

Hypothesis:
In Phase 13, the 2-Day Cross-Sectional Reversal strategy (CS_DIR_REV_2D) achieved the platform's
first positive out-of-sample gross expectancy (+Rs 4.66/trade, Profit Factor = 1.25) across 17
locked September trades. However, an unconstrained EOD holding rule allowed rare adverse tail-runaway
days (e.g. -1.45% Reliance move on Sep 2 losing Rs 107.35 net) to erode the positive gross profit
into a net loss of -Rs 8.47/trade after Rs 13.12 BASE friction.

Research Question:
Can structural risk management (catastrophe stops, volatility-scaled barriers, or time-decay filters)
truncate tail losses without prematurely stopping out mean-reverting positions, thereby achieving
positive net expectancy after BASE transaction friction?

Methodological Protocol (Strictly Enforced):
1. Research Set (June 29 – August 31, 2026):
   - Evaluate structural risk management variants on the 43 research trading sessions.
   - Zero tuning based on September performance (e.g. no retrofitting for the Sep 2 Reliance loss).
   - Select and FREEZE the single best risk management configuration based strictly on research metrics.
2. Locked September Test Set (September 1 – 25, 2026):
   - Evaluate the frozen model ONCE out-of-sample under ExecutionRegime.BASE on Rs 1,500 capital.
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

from v3.execution.realistic_simulated_broker import (
    RealisticSimulatedBroker,
    ExecutionRegime
)
from v3.execution.phase13_cross_sectional_engine import CrossSectionalSignal


@dataclass
class RiskManagedTradeResult:
    signal: CrossSectionalSignal
    exit_time: datetime
    exit_price: float
    exit_reason: str
    gross_pnl: float
    net_pnl: float
    friction: float
    gross_ret_pct: float
    mfe_pct: float
    mae_pct: float


class Phase14RiskManagementEngine:
    def __init__(
        self,
        initial_capital: float = 1500.0,
        intraday_leverage: float = 5.0,
        max_daily_loss: float = 30.0,
        workspace_root: Optional[str] = None
    ):
        self.initial_capital = initial_capital
        self.purchasing_power = initial_capital * intraday_leverage  # Rs 7,500
        self.max_daily_loss = max_daily_loss
        self.workspace_root = workspace_root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        self.symbols = [
            'AXISBANK.NS', 'BAJFINANCE.NS', 'BHARTIARTL.NS', 'HDFCBANK.NS',
            'ICICIBANK.NS', 'INFY.NS', 'RELIANCE.NS', 'SBIN.NS', 'TATACAP.NS', 'TCS.NS'
        ]

    def load_and_prepare_data(self) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame], List[date], List[date]]:
        """Loads data, prepares daily bars and continuous ATR on 5m bars, partitions dates."""
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

        # 1. Add continuous ATR(14) to all constituent bars
        prepared_dfs = []
        for sym in self.symbols:
            sym_df = df[df["symbol"] == sym].sort_values("timestamp").copy()
            tr = np.maximum(
                sym_df["high"] - sym_df["low"],
                np.maximum(
                    abs(sym_df["high"] - sym_df["close"].shift(1)),
                    abs(sym_df["low"] - sym_df["close"].shift(1))
                )
            )
            sym_df["atr_14"] = tr.rolling(14).mean().bfill()
            prepared_dfs.append(sym_df)

        all_prepared = pd.concat(prepared_dfs, ignore_index=True)
        all_prepared = all_prepared.sort_values(["timestamp", "symbol"]).reset_index(drop=True)

        # 2. Build Daily Bars for clean ranking
        daily_dfs: Dict[str, pd.DataFrame] = {}
        for sym in self.symbols + ['^NSEI']:
            sdf = df[df["symbol"] == sym].groupby("date").agg({
                "open": "first", "high": "max", "low": "min", "close": "last"
            }).dropna()
            daily_dfs[sym] = sdf

        common_dates = sorted(daily_dfs['^NSEI'].index)
        for sym in self.symbols:
            common_dates = [d for d in common_dates if d in daily_dfs[sym].index]

        research_dates = [d for d in common_dates if d <= pd.to_datetime("2026-08-31").date()]
        locked_dates = [d for d in common_dates if d >= pd.to_datetime("2026-09-01").date()]

        return all_prepared, daily_dfs, research_dates, locked_dates

    def generate_daily_signal(
        self,
        target_date: date,
        daily_dfs: Dict[str, pd.DataFrame],
        intraday_df: pd.DataFrame,
        common_dates: List[date],
        partition_name: str,
        sig_id_num: int
    ) -> Optional[CrossSectionalSignal]:
        """Generates CS_DIR_REV_2D signal for target_date."""
        k = 2  # 2-day lookback frozen from Phase 13
        date_idx = common_dates.index(target_date)
        if date_idx < k + 1:
            return None

        d_minus_1 = common_dates[date_idx - 1]
        d_minus_2 = common_dates[date_idx - 3]  # 2 days before D-1

        nifty_daily = daily_dfs['^NSEI']
        nifty_closes = nifty_daily["close"].loc[:d_minus_1]
        nifty_ema50 = nifty_closes.ewm(span=50, adjust=False).mean().iloc[-1]
        nifty_d1_close = nifty_closes.iloc[-1]
        macro_bull = nifty_d1_close > nifty_ema50
        regime_str = "MACRO_BULL" if macro_bull else "MACRO_BEAR"

        nifty_ret_2d = (nifty_d1_close - nifty_daily.loc[d_minus_2, "close"]) / nifty_daily.loc[d_minus_2, "close"]

        excess_returns = {}
        for sym in self.symbols:
            c_d1 = daily_dfs[sym].loc[d_minus_1, "close"]
            c_d2 = daily_dfs[sym].loc[d_minus_2, "close"]
            sym_ret_2d = (c_d1 - c_d2) / c_d2
            excess_returns[sym] = (sym_ret_2d - nifty_ret_2d) * 100.0

        ranked_syms = sorted(excess_returns.items(), key=lambda x: x[1])
        bot_sym, bot_excess = ranked_syms[0]  # Laggard (Rank 1)
        top_sym, top_excess = ranked_syms[-1]  # Leader (Rank 10)

        # Reversal rule: Buy bottom laggard if Bull; Sell top leader if Bear
        target_sym = bot_sym if macro_bull else top_sym
        target_side = "BUY" if macro_bull else "SELL"
        target_excess = bot_excess if macro_bull else top_excess
        rank_val = 1 if macro_bull else 10

        sbars = intraday_df[(intraday_df["symbol"] == target_sym) & (intraday_df["date"] == target_date)].sort_values("timestamp")
        if len(sbars) < 25:
            return None

        # Enter at 09:30 IST (bar 3)
        entry_bar = sbars.iloc[3]
        return CrossSectionalSignal(
            signal_id=f"SIG_P14_{partition_name[:3]}_{sig_id_num:03d}",
            date=target_date,
            symbol=target_sym,
            side=target_side,
            entry_time=entry_bar["timestamp"],
            entry_price=float(entry_bar["close"]),
            lookback_days=k,
            excess_return_pct=round(target_excess, 2),
            rank=rank_val,
            regime=regime_str,
            partition=partition_name
        )

    def simulate_trade_with_risk_rule(
        self,
        signal: CrossSectionalSignal,
        intraday_df: pd.DataFrame,
        risk_variant: str,
        broker: RealisticSimulatedBroker
    ) -> RiskManagedTradeResult:
        """Simulates single trade under specified risk management architecture with full BASE friction."""
        sbars = intraday_df[
            (intraday_df["symbol"] == signal.symbol) &
            (intraday_df["date"] == signal.date)
        ].sort_values("timestamp")

        entry_px = signal.entry_price
        side = signal.side
        qty = max(1, int(self.purchasing_power / entry_px))

        # Get ATR at entry
        entry_bar = sbars[sbars["timestamp"] == signal.entry_time].iloc[0]
        atr = float(entry_bar["atr_14"])

        # Determine stop-loss price and logic
        if risk_variant == "RM0_BASELINE_EOD":
            sl_px = 0.0 if side == "BUY" else 999999.0
            check_time_decay = False
        elif risk_variant == "RM1_CATASTROPHE_150":
            # 1.50% wide catastrophe stop
            sl_px = entry_px * 0.9850 if side == "BUY" else entry_px * 1.0150
            check_time_decay = False
        elif risk_variant == "RM2_VOLATILITY_15ATR":
            # 1.5x ATR stop loss
            sl_px = entry_px - (1.5 * atr) if side == "BUY" else entry_px + (1.5 * atr)
            check_time_decay = False
        elif risk_variant == "RM3_FIXED_100":
            # 1.00% fixed stop loss
            sl_px = entry_px * 0.9900 if side == "BUY" else entry_px * 1.0100
            check_time_decay = False
        elif risk_variant == "RM4_MIDDAY_FILTER":
            # Unconstrained stop, but if underwater by >0.50% at 12:00, abort trade
            sl_px = 0.0 if side == "BUY" else 999999.0
            check_time_decay = True
        else:
            raise ValueError(f"Unknown risk variant: {risk_variant}")

        post_bars = sbars[sbars["timestamp"] > signal.entry_time]
        exit_bar = sbars.iloc[-2]  # ~15:15
        exit_px = float(exit_bar["close"])
        exit_time = exit_bar["timestamp"]
        exit_reason = "15:15_EOD_SQUAREOFF"

        mfe_pct = 0.0
        mae_pct = 0.0

        for idx, bar in post_bars.iterrows():
            ts = bar["timestamp"]
            c = float(bar["close"])
            h = float(bar["high"])
            l = float(bar["low"])
            o = float(bar["open"])

            if side == "BUY":
                mfe_pct = max(mfe_pct, (h - entry_px) / entry_px * 100.0)
                mae_pct = max(mae_pct, (entry_px - l) / entry_px * 100.0)
            else:
                mfe_pct = max(mfe_pct, (entry_px - l) / entry_px * 100.0)
                mae_pct = max(mae_pct, (h - entry_px) / entry_px * 100.0)

            # Strict 15:15 EOD square-off
            if ts.time() >= time(15, 15):
                exit_px = c
                exit_time = ts
                exit_reason = "15:15_EOD_SQUAREOFF"
                break

            # Midday filter check (RM4)
            if check_time_decay and ts.time() >= time(12, 0):
                unrealized_pct = (c - entry_px) / entry_px * 100.0 if side == "BUY" else (entry_px - c) / entry_px * 100.0
                if unrealized_pct <= -0.50:
                    exit_px = c
                    exit_time = ts
                    exit_reason = "MIDDAY_UNDERWATER_EXIT"
                    break

            # Stop loss hit check
            if side == "BUY" and l <= sl_px:
                exit_px = min(o, sl_px)
                exit_time = ts
                exit_reason = "STOP_LOSS"
                break
            elif side == "SELL" and h >= sl_px:
                exit_px = max(o, sl_px)
                exit_time = ts
                exit_reason = "STOP_LOSS"
                break

        action_entry = "BUY" if side == "BUY" else "SELL"
        action_exit = "SELL" if side == "BUY" else "BUY"

        order_in = broker.submit_order(
            symbol=signal.symbol, side=action_entry, quantity=qty, mid_price=entry_px, timestamp=signal.entry_time
        )
        if order_in.status == "REJECTED":
            return RiskManagedTradeResult(
                signal=signal, exit_time=signal.entry_time, exit_price=entry_px,
                exit_reason="ENTRY_REJECTED", gross_pnl=0.0, net_pnl=0.0,
                friction=0.0, gross_ret_pct=0.0, mfe_pct=0.0, mae_pct=0.0
            )

        if exit_reason == "15:15_EOD_SQUAREOFF":
            order_out = broker.force_eod_square_off(
                symbol=signal.symbol, side=action_exit, quantity=qty, mid_price=exit_px, timestamp=exit_time
            )
        else:
            order_out = broker.submit_order(
                symbol=signal.symbol, side=action_exit, quantity=qty, mid_price=exit_px, timestamp=exit_time, is_exit=True
            )

        exec_entry_px = order_in.executed_price
        exec_exit_px = order_out.executed_price

        entry_val = exec_entry_px * qty
        exit_val = exec_exit_px * qty
        gross_pnl = (exec_exit_px - exec_entry_px) * qty if side == "BUY" else (exec_entry_px - exec_exit_px) * qty

        b_paid, stat_paid, slip_paid, total_cost = broker.compute_trade_costs(
            entry_val=entry_val, exit_val=exit_val, entry_slippage=order_in.slippage_paid, exit_slippage=order_out.slippage_paid
        )
        net_pnl = gross_pnl - total_cost
        gross_ret_pct = (exec_exit_px - exec_entry_px) / exec_entry_px * 100.0 if side == "BUY" else (exec_entry_px - exec_exit_px) / exec_entry_px * 100.0

        return RiskManagedTradeResult(
            signal=signal,
            exit_time=exit_time,
            exit_price=round(exec_exit_px, 2),
            exit_reason=exit_reason,
            gross_pnl=round(gross_pnl, 2),
            net_pnl=round(net_pnl, 2),
            friction=round(total_cost, 2),
            gross_ret_pct=round(gross_ret_pct, 2),
            mfe_pct=round(mfe_pct, 2),
            mae_pct=round(mae_pct, 2)
        )

    def run_research_phase(
        self,
        intraday_df: pd.DataFrame,
        daily_dfs: Dict[str, pd.DataFrame],
        research_dates: List[date],
        all_common_dates: List[date]
    ) -> Tuple[str, Dict[str, Any]]:
        """Evaluates risk management architectures on Research Set and freezes best configuration."""
        broker = RealisticSimulatedBroker(regime=ExecutionRegime.BASE, seed=42)
        signals: List[CrossSectionalSignal] = []
        sig_id = 1
        for d in research_dates[3:]:
            sig = self.generate_daily_signal(
                target_date=d,
                daily_dfs=daily_dfs,
                intraday_df=intraday_df,
                common_dates=all_common_dates,
                partition_name="RESEARCH",
                sig_id_num=sig_id
            )
            if sig:
                signals.append(sig)
                sig_id += 1

        variants = [
            "RM0_BASELINE_EOD",
            "RM1_CATASTROPHE_150",
            "RM2_VOLATILITY_15ATR",
            "RM3_FIXED_100",
            "RM4_MIDDAY_FILTER"
        ]

        results_summary = {}
        best_variant = variants[0]
        best_net_exp = -999.0

        for var in variants:
            trades: List[RiskManagedTradeResult] = []
            for sig in signals:
                tr = self.simulate_trade_with_risk_rule(sig, intraday_df, risk_variant=var, broker=broker)
                trades.append(tr)

            n_trades = len(trades)
            wins = [t for t in trades if t.net_pnl > 0]
            losses = [t for t in trades if t.net_pnl < 0]
            win_rate = (len(wins) / n_trades * 100.0) if n_trades > 0 else 0.0

            gross_total = sum(t.gross_pnl for t in trades)
            friction_total = sum(t.friction for t in trades)
            net_total = sum(t.net_pnl for t in trades)

            gross_exp = gross_total / n_trades if n_trades > 0 else 0.0
            friction_exp = friction_total / n_trades if n_trades > 0 else 0.0
            net_exp = net_total / n_trades if n_trades > 0 else 0.0

            gross_win = sum(t.gross_pnl for t in wins)
            gross_loss = abs(sum(t.gross_pnl for t in losses))
            pf = (gross_win / gross_loss) if gross_loss > 0 else 0.0

            cum_net = np.cumsum([t.net_pnl for t in trades])
            peak = np.maximum.accumulate(cum_net)
            dd = peak - cum_net
            max_dd = np.max(dd) if len(dd) > 0 else 0.0

            stop_hits = len([t for t in trades if t.exit_reason in ("STOP_LOSS", "MIDDAY_UNDERWATER_EXIT")])

            results_summary[var] = {
                "trades": n_trades,
                "win_rate": round(win_rate, 1),
                "gross_exp": round(gross_exp, 2),
                "friction_exp": round(friction_exp, 2),
                "net_exp": round(net_exp, 2),
                "profit_factor": round(pf, 2),
                "max_dd_rs": round(max_dd, 2),
                "stop_hits": stop_hits,
                "trades_list": trades
            }

            if net_exp > best_net_exp:
                best_net_exp = net_exp
                best_variant = var

        return best_variant, results_summary

    def run_locked_test_phase(
        self,
        intraday_df: pd.DataFrame,
        daily_dfs: Dict[str, pd.DataFrame],
        locked_dates: List[date],
        all_common_dates: List[date],
        frozen_variant: str
    ) -> Dict[str, Any]:
        """Evaluates the frozen risk architecture ONCE out-of-sample on locked September test set."""
        signals: List[CrossSectionalSignal] = []
        sig_id = 1
        for d in locked_dates:
            sig = self.generate_daily_signal(
                target_date=d,
                daily_dfs=daily_dfs,
                intraday_df=intraday_df,
                common_dates=all_common_dates,
                partition_name="LOCKED_TEST",
                sig_id_num=sig_id
            )
            if sig:
                signals.append(sig)
                sig_id += 1

        broker = RealisticSimulatedBroker(regime=ExecutionRegime.BASE, seed=42)
        trades: List[RiskManagedTradeResult] = []

        for sig in signals:
            tr = self.simulate_trade_with_risk_rule(sig, intraday_df, risk_variant=frozen_variant, broker=broker)
            trades.append(tr)

        n_trades = len(trades)
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl < 0]
        win_rate = (len(wins) / n_trades * 100.0) if n_trades > 0 else 0.0

        gross_total = sum(t.gross_pnl for t in trades)
        friction_total = sum(t.friction for t in trades)
        net_total = sum(t.net_pnl for t in trades)

        gross_exp = gross_total / n_trades if n_trades > 0 else 0.0
        friction_exp = friction_total / n_trades if n_trades > 0 else 0.0
        net_exp = net_total / n_trades if n_trades > 0 else 0.0

        gross_win = sum(t.gross_pnl for t in wins)
        gross_loss = abs(sum(t.gross_pnl for t in losses))
        pf = (gross_win / gross_loss) if gross_loss > 0 else 0.0

        cum_net = np.cumsum([t.net_pnl for t in trades])
        peak = np.maximum.accumulate(cum_net)
        dd = peak - cum_net
        max_dd = np.max(dd) if len(dd) > 0 else 0.0

        stop_hits = len([t for t in trades if t.exit_reason in ("STOP_LOSS", "MIDDAY_UNDERWATER_EXIT")])

        return {
            "frozen_variant": frozen_variant,
            "trades": n_trades,
            "win_rate": round(win_rate, 1),
            "gross_exp": round(gross_exp, 2),
            "friction_exp": round(friction_exp, 2),
            "net_exp": round(net_exp, 2),
            "profit_factor": round(pf, 2),
            "max_dd_rs": round(max_dd, 2),
            "stop_hits": stop_hits,
            "all_trades": trades
        }


def main():
    engine = Phase14RiskManagementEngine()
    print("Loading data and computing daily cross-sectional matrices with continuous ATR...")
    intraday_df, daily_dfs, res_dates, lock_dates = engine.load_and_prepare_data()
    all_dates = sorted(daily_dfs['^NSEI'].index)

    print("\n" + "=" * 80)
    print("STEP 1 & 2: RESEARCH SET EVALUATION & PARAMETER FREEZE (June 29 - August 31, 2026)")
    print("=" * 80)
    best_var, res_summary = engine.run_research_phase(intraday_df, daily_dfs, res_dates, all_dates)

    for name, stats in res_summary.items():
        print(f"Variant: {name:20s} | Trades: {stats['trades']:2d} | WinRate: {stats['win_rate']:4.1f}% | GrossExp: Rs {stats['gross_exp']:+6.2f} | Friction: Rs {stats['friction_exp']:5.2f} | NetExp: Rs {stats['net_exp']:+6.2f} | PF: {stats['profit_factor']:4.2f} | MaxDD: Rs {stats['max_dd_rs']:6.2f} | StopHits: {stats['stop_hits']:2d}")

    print(f"\n>>> RISK MANAGEMENT ARCHITECTURE FROZEN FOR OUT-OF-SAMPLE TEST: {best_var} <<<")

    print("\n" + "=" * 80)
    print("STEP 3: LOCKED SEPTEMBER OUT-OF-SAMPLE EVALUATION (September 1 - 25, 2026)")
    print("=" * 80)
    locked_res = engine.run_locked_test_phase(intraday_df, daily_dfs, lock_dates, all_dates, best_var)

    print(f"Frozen Architecture : {locked_res['frozen_variant']}")
    print(f"Locked Trades       : {locked_res['trades']}")
    print(f"Win Rate            : {locked_res['win_rate']}%")
    print(f"Gross Expectancy    : Rs {locked_res['gross_exp']}/trade")
    print(f"Friction (BASE)     : Rs {locked_res['friction_exp']}/trade")
    print(f"Net Expectancy      : Rs {locked_res['net_exp']}/trade")
    print(f"Profit Factor       : {locked_res['profit_factor']}")
    print(f"Max Drawdown        : Rs {locked_res['max_dd_rs']}")
    print(f"Stop Hits           : {locked_res['stop_hits']}")

    print("\n--- FORENSIC LOG OF LOCKED SEPTEMBER TRADES ---")
    for tr in locked_res["all_trades"]:
        s = tr.signal
        print(f"[{s.signal_id}] {s.date} {s.symbol:12s} {s.side:4s} @ {s.entry_price:7.2f} -> Exit @ {tr.exit_price:7.2f} ({tr.exit_reason:22s}) | Net: Rs {tr.net_pnl:+6.2f} (Gross: {tr.gross_ret_pct:+5.2f}%) | MFE: {tr.mfe_pct:+5.2f}% | MAE: {tr.mae_pct:5.2f}%")


if __name__ == "__main__":
    main()
