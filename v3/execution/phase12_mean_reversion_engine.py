#!/usr/bin/env python3
"""
AlphaNSE Phase 12: Intraday Extreme Mean Reversion Research Engine

Hypothesis:
Unusually large intraday price extensions away from volume-weighted average price (VWAP)
represent short-term liquidity depletion or overshoots that subsequently revert toward
the session mean (VWAP).

Methodological Protocol (Strictly Enforced):
1. Research Set (June 29 – August 31, 2026):
   - Compute intraday cumulative VWAP and standard deviation bands (Z-score).
   - Formulate overextension entry and exit rules.
   - Sweep and evaluate candidate parameter configurations.
   - Select and FREEZE the single best configuration.
2. Locked September Test Set (September 1 – 25, 2026):
   - Evaluate the frozen parameter set ONCE out-of-sample.
   - Zero parameter tuning or retroactive adjustments.
   - Full BASE execution friction (spread, slippage, statutory charges on Rs 1,500 capital).
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


@dataclass
class MeanReversionSignal:
    signal_id: str
    date: date
    symbol: str
    side: str  # "BUY" (fade oversold) or "SELL" (fade overbought)
    entry_time: datetime
    entry_price: float
    vwap: float
    vwap_std: float
    z_score: float
    atr_14: float
    partition: str  # "RESEARCH" or "LOCKED_TEST"


@dataclass
class MeanReversionTradeResult:
    signal: MeanReversionSignal
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


class Phase12MeanReversionEngine:
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

    def load_and_prepare_data(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Loads 5m parquet data, computes continuous ATR, intraday VWAP, and Z-score."""
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

        prepared_dfs = []
        for sym in self.symbols:
            sym_df = df[df["symbol"] == sym].sort_values("timestamp").copy()
            # 1. Continuous 14-period ATR
            tr = np.maximum(
                sym_df["high"] - sym_df["low"],
                np.maximum(
                    abs(sym_df["high"] - sym_df["close"].shift(1)),
                    abs(sym_df["low"] - sym_df["close"].shift(1))
                )
            )
            sym_df["atr_14"] = tr.rolling(14).mean().bfill()

            # 2. Daily Intraday VWAP and Standard Deviation
            day_list = []
            for d, day_bars in sym_df.groupby("date"):
                day_bars = day_bars.sort_values("timestamp").copy()
                typ = (day_bars["high"] + day_bars["low"] + day_bars["close"]) / 3.0
                v = day_bars["volume"]
                cum_v = v.cumsum()
                cum_pv = (typ * v).cumsum()
                vwap = cum_pv / (cum_v + 1e-9)

                cum_pv2 = (typ**2 * v).cumsum()
                vwap_var = (cum_pv2 / (cum_v + 1e-9)) - (vwap**2)
                vwap_std = np.sqrt(np.maximum(0.0, vwap_var))

                day_bars["vwap"] = vwap
                day_bars["vwap_std"] = vwap_std
                day_bars["z_score"] = (day_bars["close"] - vwap) / (vwap_std + 1e-9)
                day_list.append(day_bars)

            prepared_dfs.append(pd.concat(day_list, ignore_index=True))

        all_prepared = pd.concat(prepared_dfs, ignore_index=True)
        all_prepared = all_prepared.sort_values(["timestamp", "symbol"]).reset_index(drop=True)

        research_df = all_prepared[all_prepared["date"] <= pd.to_datetime("2026-08-31").date()].copy()
        locked_test_df = all_prepared[all_prepared["date"] >= pd.to_datetime("2026-09-01").date()].copy()

        return research_df, locked_test_df

    def generate_signals(
        self,
        data_df: pd.DataFrame,
        partition_name: str,
        z_threshold: float = 2.0,
        max_signals_per_day: int = 2
    ) -> List[MeanReversionSignal]:
        """Detects extreme VWAP deviation signals with bar inflection."""
        signals: List[MeanReversionSignal] = []
        unique_dates = sorted(data_df["date"].unique())
        sig_counter = 0

        for d in unique_dates:
            day_candidates: List[MeanReversionSignal] = []

            for sym in self.symbols:
                bars = data_df[(data_df["symbol"] == sym) & (data_df["date"] == d)].sort_values("timestamp")
                if len(bars) < 25:
                    continue

                # Scan from 10:00 to 13:30 (allow VWAP to stabilize)
                for i in range(9, len(bars)):
                    bar = bars.iloc[i]
                    ts = bar["timestamp"]
                    if ts.time() > time(13, 30):
                        break

                    z = float(bar["z_score"])
                    c = float(bar["close"])
                    o = float(bar["open"])
                    vw = float(bar["vwap"])
                    std = float(bar["vwap_std"])
                    atr = float(bar["atr_14"])

                    # Oversold Reversal: Z <= -z_threshold AND green candle (Close > Open)
                    if z <= -z_threshold and c > o:
                        sig_counter += 1
                        day_candidates.append(MeanReversionSignal(
                            signal_id=f"SIG_MR_{partition_name[:3]}_{sig_counter:03d}",
                            date=d,
                            symbol=sym,
                            side="BUY",
                            entry_time=ts,
                            entry_price=c,
                            vwap=round(vw, 2),
                            vwap_std=round(std, 2),
                            z_score=round(z, 2),
                            atr_14=round(atr, 2),
                            partition=partition_name
                        ))
                        break  # Max 1 signal per stock per day

                    # Overbought Reversal: Z >= +z_threshold AND red candle (Close < Open)
                    elif z >= z_threshold and c < o:
                        sig_counter += 1
                        day_candidates.append(MeanReversionSignal(
                            signal_id=f"SIG_MR_{partition_name[:3]}_{sig_counter:03d}",
                            date=d,
                            symbol=sym,
                            side="SELL",
                            entry_time=ts,
                            entry_price=c,
                            vwap=round(vw, 2),
                            vwap_std=round(std, 2),
                            z_score=round(z, 2),
                            atr_14=round(atr, 2),
                            partition=partition_name
                        ))
                        break

            # Prioritize signals with the highest absolute deviation (most extreme extensions)
            if day_candidates:
                day_candidates.sort(key=lambda s: abs(s.z_score), reverse=True)
                signals.extend(day_candidates[:max_signals_per_day])

        return signals

    def simulate_trade(
        self,
        signal: MeanReversionSignal,
        full_df: pd.DataFrame,
        target_mode: str,
        broker: RealisticSimulatedBroker
    ) -> MeanReversionTradeResult:
        """Simulates single trade with full BASE friction under specified target mode."""
        sym_df = full_df[
            (full_df["symbol"] == signal.symbol) &
            (full_df["date"] == signal.date)
        ].sort_values("timestamp")

        post_entry = sym_df[sym_df["timestamp"] > signal.entry_time]
        entry_px = signal.entry_price
        side = signal.side
        atr = signal.atr_14
        entry_vwap = signal.vwap

        qty = max(1, int(self.purchasing_power / entry_px))

        # Stop loss: 1.2x ATR
        sl_dist = 1.2 * atr
        sl_px = entry_px - sl_dist if side == "BUY" else entry_px + sl_dist

        # Target price
        if target_mode == "FULL_VWAP":
            tp_px = entry_vwap
        elif target_mode == "HALFWAY_VWAP":
            tp_px = entry_px + 0.5 * (entry_vwap - entry_px) if side == "BUY" else entry_px - 0.5 * (entry_px - entry_vwap)
        elif target_mode == "FIXED_1ATR":
            tp_px = entry_px + (1.0 * atr) if side == "BUY" else entry_px - (1.0 * atr)
        else:
            raise ValueError(f"Unknown target mode: {target_mode}")

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
            cur_vwap = float(bar["vwap"])

            # Excursion tracking
            if side == "BUY":
                mfe_pct = max(mfe_pct, (cur_high - entry_px) / entry_px * 100.0)
                mae_pct = max(mae_pct, (entry_px - cur_low) / entry_px * 100.0)
            else:
                mfe_pct = max(mfe_pct, (entry_px - cur_low) / entry_px * 100.0)
                mae_pct = max(mae_pct, (cur_high - entry_px) / entry_px * 100.0)

            # Invariant: Strict 15:15 EOD square-off
            if bar_ts.time() >= time(15, 15):
                exit_time = bar_ts
                exit_px = cur_close
                exit_reason = "15:15_EOD_SQUAREOFF"
                break

            # Stop loss hit
            if side == "BUY" and cur_low <= sl_px:
                exit_time = bar_ts
                exit_px = min(cur_open, sl_px)
                exit_reason = "STOP_LOSS"
                break
            elif side == "SELL" and cur_high >= sl_px:
                exit_time = bar_ts
                exit_px = max(cur_open, sl_px)
                exit_reason = "STOP_LOSS"
                break

            # Take profit hit
            target_level = cur_vwap if target_mode == "FULL_VWAP" else tp_px
            if side == "BUY" and cur_high >= target_level:
                exit_time = bar_ts
                exit_px = target_level
                exit_reason = "TARGET_HIT"
                break
            elif side == "SELL" and cur_low <= target_level:
                exit_time = bar_ts
                exit_px = target_level
                exit_reason = "TARGET_HIT"
                break

            # Time stop: If no mean reversion after 45 minutes (9 bars), abort
            if bars_held >= 9:
                exit_time = bar_ts
                exit_px = cur_close
                exit_reason = "TIME_DECAY_45M"
                break

        # If loop finished without explicit exit, exit on last bar
        if exit_px == entry_px and not post_entry.empty:
            exit_time = post_entry.iloc[-1]["timestamp"]
            exit_px = float(post_entry.iloc[-1]["close"])
            exit_reason = "15:15_EOD_SQUAREOFF"

        action_entry = "BUY" if side == "BUY" else "SELL"
        action_exit = "SELL" if side == "BUY" else "BUY"

        order_in = broker.submit_order(
            symbol=signal.symbol, side=action_entry, quantity=qty, mid_price=entry_px, timestamp=signal.entry_time
        )
        if order_in.status == "REJECTED":
            return MeanReversionTradeResult(
                signal=signal, exit_time=signal.entry_time, exit_price=entry_px,
                exit_reason="ENTRY_REJECTED", bars_held=0, gross_pnl=0.0, net_pnl=0.0,
                friction=0.0, gross_ret_pct=0.0, mfe_pct=0.0, mae_pct=0.0
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

        return MeanReversionTradeResult(
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
        self, research_df: pd.DataFrame
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Evaluates deviation hurdles and exit modes on Research Set and freezes best configuration."""
        broker = RealisticSimulatedBroker(regime=ExecutionRegime.BASE, seed=42)
        candidate_configs = [
            {"name": "MR_Z20_FULL_VWAP", "z": 2.0, "mode": "FULL_VWAP"},
            {"name": "MR_Z20_HALFWAY", "z": 2.0, "mode": "HALFWAY_VWAP"},
            {"name": "MR_Z20_1ATR", "z": 2.0, "mode": "FIXED_1ATR"},
            {"name": "MR_Z25_FULL_VWAP", "z": 2.5, "mode": "FULL_VWAP"},
            {"name": "MR_Z25_HALFWAY", "z": 2.5, "mode": "HALFWAY_VWAP"},
            {"name": "MR_Z25_1ATR", "z": 2.5, "mode": "FIXED_1ATR"},
        ]

        results_summary = {}
        best_cfg = candidate_configs[0]
        best_net_exp = -999.0

        for cfg in candidate_configs:
            signals = self.generate_signals(
                data_df=research_df,
                partition_name="RESEARCH",
                z_threshold=cfg["z"],
                max_signals_per_day=2
            )

            trades: List[MeanReversionTradeResult] = []
            for sig in signals:
                tr = self.simulate_trade(sig, research_df, target_mode=cfg["mode"], broker=broker)
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

            results_summary[cfg["name"]] = {
                "config": cfg,
                "trades": n_trades,
                "win_rate": round(win_rate, 1),
                "gross_exp": round(gross_exp, 2),
                "friction_exp": round(friction_exp, 2),
                "net_exp": round(net_exp, 2),
                "profit_factor": round(pf, 2),
                "max_dd_rs": round(max_dd, 2),
            }

            if net_exp > best_net_exp:
                best_net_exp = net_exp
                best_cfg = cfg

        return best_cfg, results_summary

    def run_locked_test_phase(
        self,
        locked_df: pd.DataFrame,
        frozen_cfg: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluates the frozen parameter set ONCE out-of-sample on locked September test set."""
        signals = self.generate_signals(
            data_df=locked_df,
            partition_name="LOCKED_TEST",
            z_threshold=frozen_cfg["z"],
            max_signals_per_day=2
        )

        broker = RealisticSimulatedBroker(regime=ExecutionRegime.BASE, seed=42)
        trades: List[MeanReversionTradeResult] = []

        for sig in signals:
            tr = self.simulate_trade(sig, locked_df, target_mode=frozen_cfg["mode"], broker=broker)
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
            "frozen_config": frozen_cfg,
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
    engine = Phase12MeanReversionEngine()
    print("Loading data and computing continuous ATR and VWAP Z-scores...")
    res_df, lock_df = engine.load_and_prepare_data()

    print("\n" + "=" * 80)
    print("STEP 1 & 2: RESEARCH SET EVALUATION & PARAMETER FREEZE (June 29 - August 31, 2026)")
    print("=" * 80)
    best_cfg, res_summary = engine.run_research_phase(res_df)

    for name, stats in res_summary.items():
        print(f"Config: {name:18s} | Trades: {stats['trades']:2d} | WinRate: {stats['win_rate']:4.1f}% | GrossExp: Rs {stats['gross_exp']:+6.2f} | Friction: Rs {stats['friction_exp']:5.2f} | NetExp: Rs {stats['net_exp']:+6.2f} | PF: {stats['profit_factor']:4.2f} | MaxDD: Rs {stats['max_dd_rs']:6.2f}")

    print(f"\n>>> PARAMETER SET FROZEN FOR OUT-OF-SAMPLE TEST: {best_cfg['name']} (Z={best_cfg['z']}, Mode={best_cfg['mode']}) <<<")

    print("\n" + "=" * 80)
    print("STEP 3: LOCKED SEPTEMBER OUT-OF-SAMPLE EVALUATION (September 1 - 25, 2026)")
    print("=" * 80)
    locked_res = engine.run_locked_test_phase(lock_df, best_cfg)

    print(f"Frozen Architecture : {locked_res['frozen_config']['name']}")
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
        print(f"[{s.signal_id}] {s.date} {s.symbol:12s} {s.side:4s} @ {s.entry_price:7.2f} (Z={s.z_score:+4.2f}) -> Exit @ {tr.exit_price:7.2f} ({tr.exit_reason:22s}) | Net: Rs {tr.net_pnl:+6.2f} | MFE: {tr.mfe_pct:+5.2f}% | MAE: {tr.mae_pct:5.2f}%")


if __name__ == "__main__":
    main()
