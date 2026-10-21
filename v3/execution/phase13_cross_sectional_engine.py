#!/usr/bin/env python3
"""
AlphaNSE Phase 13: Cross-Sectional Relative Strength / Portfolio Selection Engine

Hypothesis:
Instead of predicting small absolute intraday price fluctuations on single stocks,
relative performance across the 10 liquid constituent universe contains persistent
structural information. Relative leaders and laggards over multi-day windows exhibit
predictable relative divergence or mean-reverting rebalancing that may overcome transaction friction.

Methodological Protocol (Strictly Enforced):
1. Research Set (June 29 – August 31, 2026):
   - Evaluate multi-day cross-sectional ranking models (Momentum vs Reversal, Directional vs Spread).
   - Select and FREEZE the single best parameter configuration based strictly on research net expectancy.
2. Locked September Test Set (September 1 – 25, 2026):
   - Evaluate the frozen parameter configuration ONCE out-of-sample.
   - Zero parameter tuning or retroactive adjustments.
   - Full BASE execution friction (spread, slippage, statutory taxes on Rs 1,500 capital).
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
class CrossSectionalSignal:
    signal_id: str
    date: date
    symbol: str
    side: str  # "BUY" or "SELL"
    entry_time: datetime
    entry_price: float
    lookback_days: int
    excess_return_pct: float
    rank: int  # 1 = bottom laggard, 10 = top leader
    regime: str  # "MACRO_BULL" or "MACRO_BEAR"
    partition: str  # "RESEARCH" or "LOCKED_TEST"


@dataclass
class CrossSectionalTradeResult:
    signal: CrossSectionalSignal
    exit_time: datetime
    exit_price: float
    exit_reason: str
    gross_pnl: float
    net_pnl: float
    friction: float
    gross_ret_pct: float


class Phase13CrossSectionalEngine:
    def __init__(
        self,
        initial_capital: float = 1500.0,
        intraday_leverage: float = 5.0,
        max_daily_loss: float = 30.0,
        workspace_root: Optional[str] = None
    ):
        self.initial_capital = initial_capital
        self.purchasing_power = initial_capital * intraday_leverage  # Rs 7,500 per leg
        self.max_daily_loss = max_daily_loss
        self.workspace_root = workspace_root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        self.symbols = [
            'AXISBANK.NS', 'BAJFINANCE.NS', 'BHARTIARTL.NS', 'HDFCBANK.NS',
            'ICICIBANK.NS', 'INFY.NS', 'RELIANCE.NS', 'SBIN.NS', 'TATACAP.NS', 'TCS.NS'
        ]

    def load_and_prepare_data(self) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame], List[date], List[date]]:
        """Loads data, prepares daily bars and intraday 5m bars, partitions dates."""
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

        # Build Daily Bars for clean ranking
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

        return df, daily_dfs, research_dates, locked_dates

    def generate_daily_signals(
        self,
        target_date: date,
        daily_dfs: Dict[str, pd.DataFrame],
        intraday_df: pd.DataFrame,
        common_dates: List[date],
        strategy_config: Dict[str, Any],
        partition_name: str,
        sig_start_idx: int = 1
    ) -> List[CrossSectionalSignal]:
        """Generates cross-sectional signals for target_date based on lookback relative performance."""
        k = strategy_config["lookback_days"]
        model_type = strategy_config["model_type"]  # "DIR_REV", "DIR_MOM", "SPREAD_REV"

        date_idx = common_dates.index(target_date)
        if date_idx < k + 1:
            return []

        # Previous day D-1 and lookback D-k
        d_minus_1 = common_dates[date_idx - 1]
        d_minus_k = common_dates[date_idx - 1 - k]

        # Benchmark NIFTY return and Daily EMA50
        nifty_daily = daily_dfs['^NSEI']
        nifty_closes = nifty_daily["close"].loc[:d_minus_1]
        nifty_ema50 = nifty_closes.ewm(span=50, adjust=False).mean().iloc[-1]
        nifty_d1_close = nifty_closes.iloc[-1]
        macro_bull = nifty_d1_close > nifty_ema50
        regime_str = "MACRO_BULL" if macro_bull else "MACRO_BEAR"

        nifty_ret_k = (nifty_d1_close - nifty_daily.loc[d_minus_k, "close"]) / nifty_daily.loc[d_minus_k, "close"]

        # Constituent excess returns over lookback k
        excess_returns: Dict[str, float] = {}
        for sym in self.symbols:
            c_d1 = daily_dfs[sym].loc[d_minus_1, "close"]
            c_dk = daily_dfs[sym].loc[d_minus_k, "close"]
            sym_ret_k = (c_d1 - c_dk) / c_dk
            excess_returns[sym] = (sym_ret_k - nifty_ret_k) * 100.0

        ranked_syms = sorted(excess_returns.items(), key=lambda x: x[1])
        bot_sym, bot_excess = ranked_syms[0]  # Rank 1: Laggard
        top_sym, top_excess = ranked_syms[-1]  # Rank 10: Leader

        # Determine target orders for today
        target_orders = []
        if model_type == "DIR_REV":
            # Buy bottom laggard if macro bull, sell top leader if macro bear
            if macro_bull:
                target_orders.append((bot_sym, "BUY", bot_excess, 1))
            else:
                target_orders.append((top_sym, "SELL", top_excess, 10))

        elif model_type == "DIR_MOM":
            # Buy top leader if macro bull, sell bottom laggard if macro bear
            if macro_bull:
                target_orders.append((top_sym, "BUY", top_excess, 10))
            else:
                target_orders.append((bot_sym, "SELL", bot_excess, 1))

        elif model_type == "SPREAD_REV":
            # Market-neutral spread: Long bottom laggard + Short top leader
            target_orders.append((bot_sym, "BUY", bot_excess, 1))
            target_orders.append((top_sym, "SELL", top_excess, 10))

        signals: List[CrossSectionalSignal] = []
        for sym, side, excess, rank_val in target_orders:
            sbars = intraday_df[(intraday_df["symbol"] == sym) & (intraday_df["date"] == target_date)].sort_values("timestamp")
            if len(sbars) < 25:
                continue

            # Enter at 09:30 (bar 3) to allow opening rotation to stabilize
            entry_bar = sbars.iloc[3]
            signals.append(CrossSectionalSignal(
                signal_id=f"SIG_CS_{partition_name[:3]}_{sig_start_idx + len(signals):03d}",
                date=target_date,
                symbol=sym,
                side=side,
                entry_time=entry_bar["timestamp"],
                entry_price=float(entry_bar["close"]),
                lookback_days=k,
                excess_return_pct=round(excess, 2),
                rank=rank_val,
                regime=regime_str,
                partition=partition_name
            ))

        return signals

    def simulate_trade(
        self,
        signal: CrossSectionalSignal,
        intraday_df: pd.DataFrame,
        broker: RealisticSimulatedBroker
    ) -> CrossSectionalTradeResult:
        """Simulates single trade held until strict 15:15 EOD square-off with full BASE friction."""
        sbars = intraday_df[
            (intraday_df["symbol"] == signal.symbol) &
            (intraday_df["date"] == signal.date)
        ].sort_values("timestamp")

        entry_px = signal.entry_price
        side = signal.side
        qty = max(1, int(self.purchasing_power / entry_px))

        # Intraday holding to 15:15 square-off
        exit_bar = sbars.iloc[-2]  # ~15:15
        exit_px = float(exit_bar["close"])
        exit_time = exit_bar["timestamp"]
        exit_reason = "15:15_EOD_SQUAREOFF"

        action_entry = "BUY" if side == "BUY" else "SELL"
        action_exit = "SELL" if side == "BUY" else "BUY"

        order_in = broker.submit_order(
            symbol=signal.symbol, side=action_entry, quantity=qty, mid_price=entry_px, timestamp=signal.entry_time
        )
        if order_in.status == "REJECTED":
            return CrossSectionalTradeResult(
                signal=signal, exit_time=signal.entry_time, exit_price=entry_px,
                exit_reason="ENTRY_REJECTED", gross_pnl=0.0, net_pnl=0.0,
                friction=0.0, gross_ret_pct=0.0
            )

        order_out = broker.force_eod_square_off(
            symbol=signal.symbol, side=action_exit, quantity=qty, mid_price=exit_px, timestamp=exit_time
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

        return CrossSectionalTradeResult(
            signal=signal,
            exit_time=exit_time,
            exit_price=round(exec_exit_px, 2),
            exit_reason=exit_reason,
            gross_pnl=round(gross_pnl, 2),
            net_pnl=round(net_pnl, 2),
            friction=round(total_cost, 2),
            gross_ret_pct=round(gross_ret_pct, 2)
        )

    def run_research_phase(
        self,
        intraday_df: pd.DataFrame,
        daily_dfs: Dict[str, pd.DataFrame],
        research_dates: List[date],
        all_common_dates: List[date]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Evaluates lookback and strategy configurations on Research Set and freezes best model."""
        broker = RealisticSimulatedBroker(regime=ExecutionRegime.BASE, seed=42)
        candidate_configs = [
            {"name": "CS_DIR_REV_2D", "lookback_days": 2, "model_type": "DIR_REV"},
            {"name": "CS_DIR_MOM_2D", "lookback_days": 2, "model_type": "DIR_MOM"},
            {"name": "CS_SPREAD_REV_2D", "lookback_days": 2, "model_type": "SPREAD_REV"},
            {"name": "CS_DIR_REV_3D", "lookback_days": 3, "model_type": "DIR_REV"},
            {"name": "CS_DIR_REV_1D", "lookback_days": 1, "model_type": "DIR_REV"},
        ]

        results_summary = {}
        best_cfg = candidate_configs[0]
        best_net_exp = -999.0

        for cfg in candidate_configs:
            k = cfg["lookback_days"]
            all_signals: List[CrossSectionalSignal] = []
            sig_idx = 1
            for d in research_dates[k+1:]:
                sigs = self.generate_daily_signals(
                    target_date=d,
                    daily_dfs=daily_dfs,
                    intraday_df=intraday_df,
                    common_dates=all_common_dates,
                    strategy_config=cfg,
                    partition_name="RESEARCH",
                    sig_start_idx=sig_idx
                )
                all_signals.extend(sigs)
                sig_idx += len(sigs)

            trades: List[CrossSectionalTradeResult] = []
            for sig in all_signals:
                tr = self.simulate_trade(sig, intraday_df, broker=broker)
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
        intraday_df: pd.DataFrame,
        daily_dfs: Dict[str, pd.DataFrame],
        locked_dates: List[date],
        all_common_dates: List[date],
        frozen_cfg: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluates the frozen parameter set ONCE out-of-sample on locked September test set."""
        k = frozen_cfg["lookback_days"]
        all_signals: List[CrossSectionalSignal] = []
        sig_idx = 1

        for d in locked_dates:
            sigs = self.generate_daily_signals(
                target_date=d,
                daily_dfs=daily_dfs,
                intraday_df=intraday_df,
                common_dates=all_common_dates,
                strategy_config=frozen_cfg,
                partition_name="LOCKED_TEST",
                sig_start_idx=sig_idx
            )
            all_signals.extend(sigs)
            sig_idx += len(sigs)

        broker = RealisticSimulatedBroker(regime=ExecutionRegime.BASE, seed=42)
        trades: List[CrossSectionalTradeResult] = []

        for sig in all_signals:
            tr = self.simulate_trade(sig, intraday_df, broker=broker)
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
    engine = Phase13CrossSectionalEngine()
    print("Loading data and computing daily cross-sectional matrices...")
    intraday_df, daily_dfs, res_dates, lock_dates = engine.load_and_prepare_data()
    all_dates = sorted(daily_dfs['^NSEI'].index)

    print("\n" + "=" * 80)
    print("STEP 1 & 2: RESEARCH SET EVALUATION & PARAMETER FREEZE (June 29 - August 31, 2026)")
    print("=" * 80)
    best_cfg, res_summary = engine.run_research_phase(intraday_df, daily_dfs, res_dates, all_dates)

    for name, stats in res_summary.items():
        print(f"Config: {name:18s} | Trades: {stats['trades']:2d} | WinRate: {stats['win_rate']:4.1f}% | GrossExp: Rs {stats['gross_exp']:+6.2f} | Friction: Rs {stats['friction_exp']:5.2f} | NetExp: Rs {stats['net_exp']:+6.2f} | PF: {stats['profit_factor']:4.2f} | MaxDD: Rs {stats['max_dd_rs']:6.2f}")

    print(f"\n>>> PARAMETER SET FROZEN FOR OUT-OF-SAMPLE TEST: {best_cfg['name']} <<<")

    print("\n" + "=" * 80)
    print("STEP 3: LOCKED SEPTEMBER OUT-OF-SAMPLE EVALUATION (September 1 - 25, 2026)")
    print("=" * 80)
    locked_res = engine.run_locked_test_phase(intraday_df, daily_dfs, lock_dates, all_dates, best_cfg)

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
        print(f"[{s.signal_id}] {s.date} {s.symbol:12s} {s.side:4s} (Rank={s.rank:2d}, Excess={s.excess_return_pct:+5.2f}%) -> Net: Rs {tr.net_pnl:+6.2f} (Gross: {tr.gross_ret_pct:+5.2f}%) | Regime: {s.regime}")


if __name__ == "__main__":
    main()
