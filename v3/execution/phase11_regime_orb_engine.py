#!/usr/bin/env python3
"""
AlphaNSE Phase 11: Regime-Conditioned Opening Range Breakout (ORB) Research Engine

Hypothesis:
Early-session price discovery (09:15–09:45 IST) contains predictive directional momentum
when conditioned on broader market regime (NIFTY 50 Macro Trend + Morning Direction).
By entering early during the primary expansion phase (09:45–11:30) rather than late-day
exhaustion, trades capture a larger portion of the daily move (~1.85% average high-low range)
to overcome BASE transaction friction (~₹17/trade or ~23 bps on position).

Methodological Protocol (Strictly Enforced):
1. Research Set (June 29 – August 31, 2026):
   - Formulate regime conditions and breakout rules.
   - Sweep and evaluate exit architectures (EOD drift, ATR bracket, E5 hybrid).
   - Select and FREEZE the single best configuration.
2. Locked September Test Set (September 1 – 25, 2026):
   - Evaluate the frozen strategy ONCE out-of-sample.
   - Zero parameter tuning or retroactive adjustments.
"""

import os
import sys
import glob
from dataclasses import dataclass, asdict
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
    ExecutionRegime,
    CompletedTrade
)


@dataclass
class ORBSignal:
    signal_id: str
    date: date
    symbol: str
    side: str  # "BUY" or "SELL"
    entry_time: datetime
    entry_price: float
    or_high: float
    or_low: float
    or_range_pct: float
    atr_14: float
    regime: str  # "BULL_REGIME" or "BEAR_REGIME"
    partition: str  # "RESEARCH" or "LOCKED_TEST"


@dataclass
class ORBTradeResult:
    signal: ORBSignal
    exit_time: datetime
    exit_price: float
    exit_reason: str
    bars_held: int
    gross_pnl: float
    net_pnl: float
    friction: float
    gross_ret_pct: float
    mfe_pct: float
    mae_pct: float


class Phase11RegimeORBEngine:
    def __init__(
        self,
        initial_capital: float = 1500.0,
        intraday_leverage: float = 5.0,
        max_daily_loss: float = 30.0,
        workspace_root: Optional[str] = None
    ):
        self.initial_capital = initial_capital
        self.purchasing_power = initial_capital * intraday_leverage  # ₹7,500
        self.max_daily_loss = max_daily_loss
        self.workspace_root = workspace_root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        self.symbols = [
            'AXISBANK.NS', 'BAJFINANCE.NS', 'BHARTIARTL.NS', 'HDFCBANK.NS',
            'ICICIBANK.NS', 'INFY.NS', 'RELIANCE.NS', 'SBIN.NS', 'TATACAP.NS', 'TCS.NS'
        ]

    def load_and_prepare_data(self) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[date, Dict[str, Any]]]:
        """Loads 5m parquet data, computes indicators, and splits into Research and Locked Test."""
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

        # 1. Compute Benchmark NIFTY Macro & Intraday Regime
        nifty_df = df[df["symbol"] == "^NSEI"].copy()
        daily_nifty = nifty_df.groupby("date").agg({
            "open": "first", "high": "max", "low": "min", "close": "last"
        }).reset_index()
        daily_nifty["daily_ema_50"] = daily_nifty["close"].ewm(span=50, adjust=False).mean()
        daily_nifty["d1_close"] = daily_nifty["close"].shift(1)
        daily_nifty["d1_ema_50"] = daily_nifty["daily_ema_50"].shift(1)
        daily_nifty["macro_bull"] = daily_nifty["d1_close"] > daily_nifty["d1_ema_50"]

        regime_map: Dict[date, Dict[str, Any]] = {}
        for _, row in daily_nifty.iterrows():
            d = row["date"]
            macro_bull = bool(row["macro_bull"]) if pd.notna(row["macro_bull"]) else True
            day_bars = nifty_df[nifty_df["date"] == d].sort_values("timestamp")
            if len(day_bars) >= 6:
                or_bars = day_bars.iloc[:6]  # 09:15 to 09:40 (first six 5m bars = 30 min)
                nifty_or_open = or_bars.iloc[0]["open"]
                nifty_or_close = or_bars.iloc[-1]["close"]
                nifty_or_bull = nifty_or_close > nifty_or_open

                if macro_bull and nifty_or_bull:
                    session_regime = "BULL_REGIME"
                elif (not macro_bull) and (not nifty_or_bull):
                    session_regime = "BEAR_REGIME"
                else:
                    session_regime = "NEUTRAL_CHOP"

                regime_map[d] = {
                    "macro_bull": macro_bull,
                    "nifty_or_bull": nifty_or_bull,
                    "session_regime": session_regime,
                    "nifty_or_ret": (nifty_or_close - nifty_or_open) / nifty_or_open * 100.0
                }

        # 2. Add ATR(14) to all 5m constituent bars
        constituent_dfs = []
        for sym in self.symbols:
            sym_df = df[df["symbol"] == sym].copy()
            sym_df = sym_df.sort_values("timestamp").reset_index(drop=True)
            tr = np.maximum(
                sym_df["high"] - sym_df["low"],
                np.maximum(
                    abs(sym_df["high"] - sym_df["close"].shift(1)),
                    abs(sym_df["low"] - sym_df["close"].shift(1))
                )
            )
            sym_df["atr_14"] = tr.rolling(14).mean().bfill()
            constituent_dfs.append(sym_df)

        all_constituents = pd.concat(constituent_dfs, ignore_index=True)

        research_df = all_constituents[all_constituents["date"] <= pd.to_datetime("2026-08-31").date()].copy()
        locked_test_df = all_constituents[all_constituents["date"] >= pd.to_datetime("2026-09-01").date()].copy()

        return research_df, locked_test_df, regime_map

    def generate_signals(
        self,
        data_df: pd.DataFrame,
        regime_map: Dict[date, Dict[str, Any]],
        partition_name: str,
        min_or_range_pct: float = 0.40,
        max_signals_per_day: int = 2
    ) -> List[ORBSignal]:
        """Detects 30m ORB signals conditioned strictly on market regime."""
        signals: List[ORBSignal] = []
        unique_dates = sorted(data_df["date"].unique())
        sig_counter = 0

        for d in unique_dates:
            regime_info = regime_map.get(d)
            if not regime_info:
                continue

            session_regime = regime_info["session_regime"]
            # Pure regime filter: reject chop days where macro and morning direction conflict
            if session_regime == "NEUTRAL_CHOP":
                continue

            day_candidates: List[ORBSignal] = []

            for sym in self.symbols:
                sym_bars = data_df[(data_df["symbol"] == sym) & (data_df["date"] == d)].sort_values("timestamp")
                if len(sym_bars) < 25:
                    continue

                or_bars = sym_bars.iloc[:6]  # First six 5m bars: 09:15 to 09:40
                or_high = or_bars["high"].max()
                or_low = or_bars["low"].min()
                or_range_pct = (or_high - or_low) / or_low * 100.0

                if or_range_pct < min_or_range_pct:
                    continue

                post_or_bars = sym_bars.iloc[6:]
                for idx, bar in post_or_bars.iterrows():
                    bar_time = bar["timestamp"].time()
                    # Only accept entries up to 13:00 to leave sufficient runway for expansion
                    if bar_time > time(13, 0):
                        break

                    atr = float(bar["atr_14"])

                    if session_regime == "BULL_REGIME" and bar["close"] > or_high:
                        sig_counter += 1
                        day_candidates.append(ORBSignal(
                            signal_id=f"SIG_{partition_name[:3]}_{sig_counter:03d}",
                            date=d,
                            symbol=sym,
                            side="BUY",
                            entry_time=bar["timestamp"],
                            entry_price=float(bar["close"]),
                            or_high=float(or_high),
                            or_low=float(or_low),
                            or_range_pct=round(or_range_pct, 2),
                            atr_14=round(atr, 2),
                            regime=session_regime,
                            partition=partition_name
                        ))
                        break  # One signal per stock per day

                    elif session_regime == "BEAR_REGIME" and bar["close"] < or_low:
                        sig_counter += 1
                        day_candidates.append(ORBSignal(
                            signal_id=f"SIG_{partition_name[:3]}_{sig_counter:03d}",
                            date=d,
                            symbol=sym,
                            side="SELL",
                            entry_time=bar["timestamp"],
                            entry_price=float(bar["close"]),
                            or_high=float(or_high),
                            or_low=float(or_low),
                            or_range_pct=round(or_range_pct, 2),
                            atr_14=round(atr, 2),
                            regime=session_regime,
                            partition=partition_name
                        ))
                        break

            # Limit to top signals per day sorted by entry time (first to break out has highest relative strength)
            if day_candidates:
                day_candidates.sort(key=lambda s: s.entry_time)
                signals.extend(day_candidates[:max_signals_per_day])

        return signals

    def simulate_trade(
        self,
        signal: ORBSignal,
        full_df: pd.DataFrame,
        exit_variant: str,
        broker: RealisticSimulatedBroker
    ) -> ORBTradeResult:
        """Simulates single trade with full BASE friction under specified exit architecture."""
        sym_df = full_df[
            (full_df["symbol"] == signal.symbol) &
            (full_df["date"] == signal.date)
        ].sort_values("timestamp")

        post_entry = sym_df[sym_df["timestamp"] > signal.entry_time]
        entry_px = signal.entry_price
        side = signal.side
        atr = signal.atr_14

        qty = max(1, int(self.purchasing_power / entry_px))

        # Stop loss and target definitions
        if exit_variant == "V1_EOD":
            # Pure EOD hold until 15:15
            sl_px = entry_px - (10.0 * atr) if side == "BUY" else entry_px + (10.0 * atr)
            tp_px = entry_px + (10.0 * atr) if side == "BUY" else entry_px - (10.0 * atr)
            use_anti_chop = False
            use_be_lock = False
            use_trailing = False
        elif exit_variant == "V2_FIXED_BRACKET":
            # 1.0x ATR SL, 2.0x ATR TP
            sl_dist = 1.0 * atr
            tp_dist = 2.0 * atr
            sl_px = entry_px - sl_dist if side == "BUY" else entry_px + sl_dist
            tp_px = entry_px + tp_dist if side == "BUY" else entry_px - tp_dist
            use_anti_chop = False
            use_be_lock = False
            use_trailing = False
        elif exit_variant == "V3_E5_HYBRID":
            # E5 Hybrid: 1.2x ATR SL, Anti-chop @ 60m if not favorable, BE lock @ +0.50% MFE, 1.5x ATR Trail
            sl_dist = 1.2 * atr
            tp_dist = 3.0 * atr
            sl_px = entry_px - sl_dist if side == "BUY" else entry_px + sl_dist
            tp_px = entry_px + tp_dist if side == "BUY" else entry_px - tp_dist
            use_anti_chop = True
            use_be_lock = True
            use_trailing = True
        else:
            raise ValueError(f"Unknown exit variant: {exit_variant}")

        highest_favorable = entry_px
        exit_time = signal.entry_time
        exit_px = entry_px
        exit_reason = "15:15_EOD_SQUAREOFF"
        bars_held = 0

        mfe_pct = 0.0
        mae_pct = 0.0

        for i, (_, bar) in enumerate(post_entry.iterrows(), start=1):
            bars_held = i
            bar_ts = bar["timestamp"]
            cur_open = float(bar["open"])
            cur_high = float(bar["high"])
            cur_low = float(bar["low"])
            cur_close = float(bar["close"])

            # Track MFE / MAE
            if side == "BUY":
                mfe_pct = max(mfe_pct, (cur_high - entry_px) / entry_px * 100.0)
                mae_pct = max(mae_pct, (entry_px - cur_low) / entry_px * 100.0)
                highest_favorable = max(highest_favorable, cur_high)
            else:
                mfe_pct = max(mfe_pct, (entry_px - cur_low) / entry_px * 100.0)
                mae_pct = max(mae_pct, (cur_high - entry_px) / entry_px * 100.0)
                highest_favorable = min(highest_favorable, cur_low)

            # Invariant: Strict 15:15 EOD square-off
            if bar_ts.time() >= time(15, 15):
                exit_time = bar_ts
                exit_px = cur_close
                exit_reason = "15:15_EOD_SQUAREOFF"
                break

            # Dynamic rules for V3_E5_HYBRID
            if use_be_lock and mfe_pct >= 0.50:
                if side == "BUY":
                    sl_px = max(sl_px, entry_px)
                else:
                    sl_px = min(sl_px, entry_px)

            if use_trailing and mfe_pct >= 1.00:
                trail_dist = 1.2 * atr
                if side == "BUY":
                    sl_px = max(sl_px, highest_favorable - trail_dist)
                else:
                    sl_px = min(sl_px, highest_favorable + trail_dist)

            # Anti-chop at 60m (12 five-minute bars)
            if use_anti_chop and bars_held == 12:
                cur_gain = (cur_close - entry_px) / entry_px * 100.0 if side == "BUY" else (entry_px - cur_close) / entry_px * 100.0
                if cur_gain < 0.15:
                    exit_time = bar_ts
                    exit_px = cur_close
                    exit_reason = "ANTI_CHOP_60M_TIMEOUT"
                    break

            # Check Stop Loss hit
            if side == "BUY" and cur_low <= sl_px:
                exit_time = bar_ts
                exit_px = min(cur_open, sl_px)  # Model gap through SL
                exit_reason = "STOP_LOSS"
                break
            elif side == "SELL" and cur_high >= sl_px:
                exit_time = bar_ts
                exit_px = max(cur_open, sl_px)
                exit_reason = "STOP_LOSS"
                break

            # Check Take Profit hit
            if side == "BUY" and cur_high >= tp_px:
                exit_time = bar_ts
                exit_px = tp_px
                exit_reason = "TAKE_PROFIT"
                break
            elif side == "SELL" and cur_low <= tp_px:
                exit_time = bar_ts
                exit_px = tp_px
                exit_reason = "TAKE_PROFIT"
                break

        # If loop finished without explicit exit, exit on last bar close
        if exit_px == entry_px and not post_entry.empty:
            exit_time = post_entry.iloc[-1]["timestamp"]
            exit_px = float(post_entry.iloc[-1]["close"])
            exit_reason = "15:15_EOD_SQUAREOFF"

        # Calculate exact PnL and friction via broker simulator
        action_entry = "BUY" if side == "BUY" else "SELL"
        action_exit = "SELL" if side == "BUY" else "BUY"

        order_in = broker.submit_order(
            symbol=signal.symbol, side=action_entry, quantity=qty, mid_price=entry_px, timestamp=signal.entry_time
        )
        if order_in.status == "REJECTED":
            # Microstructure rejected order before fill
            return ORBTradeResult(
                signal=signal,
                exit_time=signal.entry_time,
                exit_price=entry_px,
                exit_reason="ENTRY_REJECTED",
                bars_held=0,
                gross_pnl=0.0,
                net_pnl=0.0,
                friction=0.0,
                gross_ret_pct=0.0,
                mfe_pct=0.0,
                mae_pct=0.0
            )

        exec_entry_px = order_in.executed_price
        entry_slip = order_in.slippage_paid

        if exit_reason == "15:15_EOD_SQUAREOFF":
            order_out = broker.force_eod_square_off(
                symbol=signal.symbol, side=action_exit, quantity=qty, mid_price=exit_px, timestamp=exit_time
            )
        else:
            order_out = broker.submit_order(
                symbol=signal.symbol, side=action_exit, quantity=qty, mid_price=exit_px, timestamp=exit_time, is_exit=True
            )

        exec_exit_px = order_out.executed_price
        exit_slip = order_out.slippage_paid

        entry_val = exec_entry_px * qty
        exit_val = exec_exit_px * qty
        gross_pnl = (exec_exit_px - exec_entry_px) * qty if side == "BUY" else (exec_entry_px - exec_exit_px) * qty

        b_paid, stat_paid, slip_paid, total_cost = broker.compute_trade_costs(
            entry_val=entry_val, exit_val=exit_val, entry_slippage=entry_slip, exit_slippage=exit_slip
        )
        net_pnl = gross_pnl - total_cost
        gross_ret_pct = (exec_exit_px - exec_entry_px) / exec_entry_px * 100.0 if side == "BUY" else (exec_entry_px - exec_exit_px) / exec_entry_px * 100.0

        return ORBTradeResult(
            signal=signal,
            exit_time=exit_time,
            exit_price=round(exec_exit_px, 2),
            exit_reason=exit_reason,
            bars_held=bars_held,
            gross_pnl=round(gross_pnl, 2),
            net_pnl=round(net_pnl, 2),
            friction=round(total_cost, 2),
            gross_ret_pct=round(gross_ret_pct, 2),
            mfe_pct=round(mfe_pct, 2),
            mae_pct=round(mae_pct, 2)
        )

    def run_research_phase(
        self, research_df: pd.DataFrame, regime_map: Dict[date, Dict[str, Any]]
    ) -> Tuple[str, Dict[str, Any]]:
        """Evaluates exit variants on Research Set and freezes optimal configuration."""
        signals = self.generate_signals(
            data_df=research_df,
            regime_map=regime_map,
            partition_name="RESEARCH",
            min_or_range_pct=0.40,
            max_signals_per_day=2
        )

        broker = RealisticSimulatedBroker(regime=ExecutionRegime.BASE, seed=42)
        variants = ["V1_EOD", "V2_FIXED_BRACKET", "V3_E5_HYBRID"]
        results_summary = {}

        best_variant = "V3_E5_HYBRID"
        best_net_exp = -999.0

        for var in variants:
            trades: List[ORBTradeResult] = []
            for sig in signals:
                tr = self.simulate_trade(sig, research_df, exit_variant=var, broker=broker)
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

            # Max drawdown
            cum_net = np.cumsum([t.net_pnl for t in trades])
            peak = np.maximum.accumulate(cum_net)
            dd = peak - cum_net
            max_dd = np.max(dd) if len(dd) > 0 else 0.0

            results_summary[var] = {
                "trades": n_trades,
                "win_rate": round(win_rate, 1),
                "gross_exp": round(gross_exp, 2),
                "friction_exp": round(friction_exp, 2),
                "net_exp": round(net_exp, 2),
                "profit_factor": round(pf, 2),
                "max_dd_rs": round(max_dd, 2),
                "sample_trades": trades
            }

            if net_exp > best_net_exp:
                best_net_exp = net_exp
                best_variant = var

        return best_variant, results_summary

    def run_locked_test_phase(
        self,
        locked_df: pd.DataFrame,
        regime_map: Dict[date, Dict[str, Any]],
        frozen_variant: str
    ) -> Dict[str, Any]:
        """Evaluates the frozen parameter set ONCE out-of-sample on locked September test set."""
        signals = self.generate_signals(
            data_df=locked_df,
            regime_map=regime_map,
            partition_name="LOCKED_TEST",
            min_or_range_pct=0.40,
            max_signals_per_day=2
        )

        broker = RealisticSimulatedBroker(regime=ExecutionRegime.BASE, seed=42)
        trades: List[ORBTradeResult] = []

        for sig in signals:
            tr = self.simulate_trade(sig, locked_df, exit_variant=frozen_variant, broker=broker)
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

        return {
            "frozen_variant": frozen_variant,
            "trades": n_trades,
            "win_rate": round(win_rate, 1),
            "gross_exp": round(gross_exp, 2),
            "friction_exp": round(friction_exp, 2),
            "net_exp": round(net_exp, 2),
            "profit_factor": round(pf, 2),
            "max_dd_rs": round(max_dd, 2),
            "all_trades": trades
        }


def main():
    engine = Phase11RegimeORBEngine()
    print("Loading data and computing indicators...")
    res_df, lock_df, reg_map = engine.load_and_prepare_data()

    print("\n" + "=" * 80)
    print("STEP 1 & 2: RESEARCH SET EVALUATION & PARAMETER FREEZE (June 29 - August 31, 2026)")
    print("=" * 80)
    best_var, res_summary = engine.run_research_phase(res_df, reg_map)

    for var, stats in res_summary.items():
        print(f"Variant: {var:16s} | Trades: {stats['trades']:2d} | WinRate: {stats['win_rate']:4.1f}% | GrossExp: Rs {stats['gross_exp']:+6.2f} | Friction: Rs {stats['friction_exp']:5.2f} | NetExp: Rs {stats['net_exp']:+6.2f} | PF: {stats['profit_factor']:4.2f} | MaxDD: Rs {stats['max_dd_rs']:6.2f}")

    print(f"\n>>> PARAMETER SET FROZEN FOR OUT-OF-SAMPLE TEST: {best_var} <<<")

    print("\n" + "=" * 80)
    print("STEP 3: LOCKED SEPTEMBER OUT-OF-SAMPLE EVALUATION (September 1 - 25, 2026)")
    print("=" * 80)
    locked_res = engine.run_locked_test_phase(lock_df, reg_map, best_var)

    print(f"Frozen Architecture : {locked_res['frozen_variant']}")
    print(f"Locked Trades       : {locked_res['trades']}")
    print(f"Win Rate            : {locked_res['win_rate']}%")
    print(f"Gross Expectancy    : Rs {locked_res['gross_exp']}/trade")
    print(f"Friction (BASE)     : Rs {locked_res['friction_exp']}/trade")
    print(f"Net Expectancy      : Rs {locked_res['net_exp']}/trade")
    print(f"Profit Factor       : {locked_res['profit_factor']}")
    print(f"Max Drawdown        : Rs {locked_res['max_dd_rs']}")

    print("\n--- FORENSIC LOG OF LOCKED SEPTEMBER TRADES ---")
    for tr in locked_res["all_trades"]:
        s = tr.signal
        print(f"[{s.signal_id}] {s.date} {s.symbol:12s} {s.side:4s} @ {s.entry_price:7.2f} -> Exit @ {tr.exit_price:7.2f} ({tr.exit_reason:22s}) | Net: Rs {tr.net_pnl:+6.2f} | MFE: {tr.mfe_pct:+5.2f}% | MAE: {tr.mae_pct:5.2f}%")


if __name__ == "__main__":
    main()
