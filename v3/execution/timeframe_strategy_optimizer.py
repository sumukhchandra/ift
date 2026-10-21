#!/usr/bin/env python3
"""
AlphaNSE Phase 6: Timeframe, Regime, and Signal Optimization Engine
Tests multi-timeframe candidates (5m, 15m, 60m) with trend, volume, and time-of-day filters
to discover true positive gross alpha before testing survival against realistic friction.

Candidates Evaluated on Unseen Out-of-Sample Walk-Forward Period:
- Candidate A (Control): 5m Raw Momentum (No volume/regime filter)
- Candidate B: 15m Trend + Volume Expansion Filter (V2_15M style)
- Candidate C: 15m Pullback / Mean-Reversion in Bull Trend (HYPO001 style)
- Candidate D: 60m Structural Momentum (V3_60M style)
"""

import os
import sys
import glob
from dataclasses import dataclass
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
from v3.execution.market_data_guards import MarketDataGuard, IST


@dataclass
class CandidateResult:
    candidate_id: str
    name: str
    timeframe: str
    total_trades: int
    win_rate_pct: float
    gross_pnl: float
    total_friction: float
    net_pnl: float
    net_roi_pct: float
    profit_factor: float
    gross_expectancy_per_trade: float
    net_expectancy_per_trade: float
    max_drawdown_rupees: float
    max_drawdown_pct: float
    largest_loss: float
    longest_losing_streak: int
    avg_holding_mins: float
    turnover_rupees: float


class TimeframeStrategyOptimizer:
    def __init__(
        self,
        initial_capital: float = 1500.0,
        intraday_leverage: float = 5.0,
        max_daily_loss: float = 30.0,
        workspace_root: Optional[str] = None
    ):
        self.initial_capital = initial_capital
        self.purchasing_power = initial_capital * intraday_leverage
        self.max_daily_loss = max_daily_loss
        self.workspace_root = workspace_root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )

    def load_data(self) -> pd.DataFrame:
        """Loads and sorts historical 5m adjusted data."""
        base_path = os.path.join(self.workspace_root, "v2", "data", "storage", "adjusted", "historical_5m_adjusted.parquet")
        df = pd.read_parquet(base_path)
        
        fresh_pattern = os.path.join(self.workspace_root, "v2", "data", "storage", "fresh", "session_*_5m.parquet")
        fresh_files = sorted(glob.glob(fresh_pattern))
        if fresh_files:
            fresh_dfs = [pd.read_parquet(f) for f in fresh_files]
            df = pd.concat([df] + fresh_dfs, ignore_index=True)

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
        return df

    def resample_symbol_data(self, df_sym: pd.DataFrame, freq: str) -> pd.DataFrame:
        """Resamples 5m bars to 15m ('15min') or 60m ('60min')."""
        if freq == "5min":
            res = df_sym.copy()
        else:
            df_indexed = df_sym.set_index("timestamp")
            res = df_indexed.resample(freq).agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "symbol": "first"
            }).dropna().reset_index()

        # Calculate indicators
        res["ema_9"] = res["close"].ewm(span=9, adjust=False).mean()
        res["ema_20"] = res["close"].ewm(span=20, adjust=False).mean()
        res["ema_21"] = res["close"].ewm(span=21, adjust=False).mean()
        res["ema_50"] = res["close"].ewm(span=50, adjust=False).mean()
        res["vol_sma_20"] = res["volume"].rolling(20).mean()

        delta = res["close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        res["rsi_14"] = 100 - (100 / (1 + rs))

        return res

    def evaluate_candidate(
        self,
        df_all: pd.DataFrame,
        symbols: List[str],
        candidate_id: str,
        name: str,
        timeframe: str,
        entry_signal_fn,
        stop_loss_pct: float,
        take_profit_pct: float,
        max_holding_bars: int,
        allowed_hours_fn
    ) -> CandidateResult:
        """
        Executes a walk-forward simulation for a candidate strategy under BASE execution friction.
        """
        broker = RealisticSimulatedBroker(regime=ExecutionRegime.BASE, seed=42)
        guard = MarketDataGuard(
            max_staleness_seconds=5.0,
            max_daily_loss=self.max_daily_loss,
            max_capital=self.purchasing_power
        )

        # Prepare resampled data
        symbol_data = {}
        for sym in symbols:
            s_df = df_all[df_all["symbol"] == sym].sort_values("timestamp").reset_index(drop=True)
            if len(s_df) > 50:
                symbol_data[sym] = self.resample_symbol_data(s_df, timeframe)

        # Identify unified evaluation timestamps (last 10 market sessions)
        all_ts = sorted(list(set.union(*[set(d["timestamp"]) for d in symbol_data.values()])))
        
        # Take the last 10 days of bars
        if timeframe == "5min":
            eval_ts = all_ts[-750:]
            bar_minutes = 5
        elif timeframe == "15min":
            eval_ts = all_ts[-250:]
            bar_minutes = 15
        else:  # 60min
            eval_ts = all_ts[-65:]
            bar_minutes = 60

        capital = self.initial_capital
        peak_capital = capital
        max_dd_rupees = 0.0
        current_daily_loss = 0.0
        current_day = None

        active_position = None
        completed_trades: List[CompletedTrade] = []
        total_turnover = 0.0
        trade_counter = 0

        for ts in eval_ts:
            bar_date = ts.date()
            if bar_date != current_day:
                current_day = bar_date
                current_daily_loss = 0.0

            # 1. Manage Active Position
            if active_position is not None:
                sym = active_position["symbol"]
                sym_df = symbol_data[sym]
                bar_match = sym_df[sym_df["timestamp"] == ts]
                if not bar_match.empty:
                    bar = bar_match.iloc[0]
                    current_price = bar["close"]
                    entry_price = active_position["entry_price"]
                    qty = active_position["quantity"]
                    bars_held = active_position["bars_held"] + 1
                    active_position["bars_held"] = bars_held

                    unrealized_return = (current_price - entry_price) / entry_price
                    should_exit = False
                    exit_reason = ""

                    if unrealized_return <= -stop_loss_pct:
                        should_exit = True
                        exit_reason = f"STOP_LOSS ({stop_loss_pct*100:.1f}%)"
                    elif unrealized_return >= take_profit_pct:
                        should_exit = True
                        exit_reason = f"TAKE_PROFIT ({take_profit_pct*100:.1f}%)"
                    elif bars_held >= max_holding_bars:
                        should_exit = True
                        exit_reason = f"MAX_HOLD ({bars_held * bar_minutes}m)"
                    elif ts.time() >= pd.to_datetime("15:15:00").time():
                        should_exit = True
                        exit_reason = "INTRADAY_SQUARE_OFF"

                    if should_exit:
                        exit_order = broker.submit_order(
                            symbol=sym,
                            side="SELL",
                            quantity=qty,
                            mid_price=current_price,
                            timestamp=ts
                        )
                        if exit_order.status == "FILLED":
                            exec_exit_price = exit_order.executed_price
                            entry_val = active_position["entry_exec_price"] * qty
                            exit_val = exec_exit_price * qty
                            total_turnover += (entry_val + exit_val)

                            gross_pnl = (exec_exit_price - active_position["entry_exec_price"]) * qty
                            b_paid, stat_paid, slip_paid, total_cost = broker.compute_trade_costs(
                                entry_val=entry_val,
                                exit_val=exit_val,
                                entry_slippage=active_position["entry_slippage"],
                                exit_slippage=exit_order.slippage_paid
                            )
                            net_pnl = gross_pnl - total_cost

                            capital += net_pnl
                            if net_pnl < 0:
                                current_daily_loss += abs(net_pnl)

                            if capital > peak_capital:
                                peak_capital = capital
                            dd = peak_capital - capital
                            if dd > max_dd_rupees:
                                max_dd_rupees = dd

                            trade_counter += 1
                            completed_trades.append(CompletedTrade(
                                trade_id=f"TRD_{candidate_id}_{trade_counter:04d}",
                                symbol=sym,
                                model_name=name,
                                entry_time=active_position["entry_time"],
                                exit_time=ts,
                                quantity=qty,
                                entry_price=active_position["entry_exec_price"],
                                exit_price=exec_exit_price,
                                gross_pnl=round(gross_pnl, 2),
                                slippage=round(slip_paid, 2),
                                brokerage=round(b_paid, 2),
                                statutory_taxes=round(stat_paid, 2),
                                total_cost=round(total_cost, 2),
                                net_pnl=round(net_pnl, 2),
                                holding_minutes=bars_held * bar_minutes,
                                exit_reason=exit_reason
                            ))
                            active_position = None

            # 2. Check Entry Signal
            if active_position is None and allowed_hours_fn(ts.time()):
                for sym in symbols:
                    if sym not in symbol_data:
                        continue
                    sym_df = symbol_data[sym]
                    bar_match = sym_df[sym_df["timestamp"] == ts]
                    if bar_match.empty:
                        continue
                    bar = bar_match.iloc[0]

                    if entry_signal_fn(bar):
                        close_px = bar["close"]
                        share_qty = int(self.purchasing_power // close_px)
                        if share_qty < 1:
                            continue

                        proposed_trade_val = share_qty * close_px

                        quote_packet = {
                            "status": "success",
                            "data": {
                                "NSE_EQ": {
                                    sym: {
                                        "last_price": close_px,
                                        "last_trade_time": ts.strftime("%Y-%m-%d %H:%M:%S"),
                                        "ohlc": {
                                            "open": bar["open"],
                                            "high": bar["high"],
                                            "low": bar["low"],
                                            "close": bar["close"]
                                        }
                                    }
                                }
                            }
                        }

                        guard_pass, _, _ = guard.evaluate_pre_trade_gates(
                            security_id=sym,
                            quote_packet=quote_packet,
                            current_daily_loss=current_daily_loss,
                            proposed_trade_value=proposed_trade_val,
                            current_dt=ts,
                            bypass_market_hours=True
                        )

                        if not guard_pass:
                            continue

                        entry_order = broker.submit_order(
                            symbol=sym,
                            side="BUY",
                            quantity=share_qty,
                            mid_price=close_px,
                            timestamp=ts
                        )

                        if entry_order.status == "FILLED":
                            active_position = {
                                "symbol": sym,
                                "quantity": share_qty,
                                "entry_time": ts,
                                "entry_price": close_px,
                                "entry_exec_price": entry_order.executed_price,
                                "entry_slippage": entry_order.slippage_paid,
                                "bars_held": 0
                            }
                            break

        # Calculate metrics
        n_trades = len(completed_trades)
        wins = [t for t in completed_trades if t.net_pnl > 0]
        n_wins = len(wins)
        win_rate = (n_wins / n_trades * 100.0) if n_trades > 0 else 0.0

        gross_pnl = sum(t.gross_pnl for t in completed_trades)
        total_friction = sum(t.total_cost for t in completed_trades)
        net_pnl = sum(t.net_pnl for t in completed_trades)
        net_roi = (net_pnl / self.initial_capital) * 100.0

        gross_gain = sum(t.gross_pnl for t in completed_trades if t.gross_pnl > 0)
        gross_loss = abs(sum(t.gross_pnl for t in completed_trades if t.gross_pnl < 0))
        profit_factor = round(gross_gain / gross_loss, 2) if gross_loss > 0 else (99.9 if gross_gain > 0 else 0.0)

        gross_expectancy = round(gross_pnl / n_trades, 2) if n_trades > 0 else 0.0
        net_expectancy = round(net_pnl / n_trades, 2) if n_trades > 0 else 0.0

        largest_loss = min([t.net_pnl for t in completed_trades], default=0.0)

        max_streak = 0
        current_streak = 0
        for t in completed_trades:
            if t.net_pnl < 0:
                current_streak += 1
                if current_streak > max_streak:
                    max_streak = current_streak
            else:
                current_streak = 0

        avg_holding = (sum(t.holding_minutes for t in completed_trades) / n_trades) if n_trades > 0 else 0.0
        max_dd_pct = (max_dd_rupees / self.initial_capital) * 100.0

        return CandidateResult(
            candidate_id=candidate_id,
            name=name,
            timeframe=timeframe,
            total_trades=n_trades,
            win_rate_pct=round(win_rate, 2),
            gross_pnl=round(gross_pnl, 2),
            total_friction=round(total_friction, 2),
            net_pnl=round(net_pnl, 2),
            net_roi_pct=round(net_roi, 2),
            profit_factor=profit_factor,
            gross_expectancy_per_trade=gross_expectancy,
            net_expectancy_per_trade=net_expectancy,
            max_drawdown_rupees=round(max_dd_rupees, 2),
            max_drawdown_pct=round(max_dd_pct, 2),
            largest_loss=round(largest_loss, 2),
            longest_losing_streak=max_streak,
            avg_holding_mins=round(avg_holding, 1),
            turnover_rupees=round(total_turnover, 2)
        )

    def run_all_candidates(self) -> List[CandidateResult]:
        """Executes all candidate strategies across the exact same dataset."""
        df_all = self.load_data()
        symbols = ["INFY.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "BAJFINANCE.NS"]
        results = []

        # -------------------------------------------------------------
        # Candidate A: 5m Raw Momentum (Control)
        # -------------------------------------------------------------
        print("-> Running Candidate A: 5m Raw Momentum (Control)...")
        res_a = self.evaluate_candidate(
            df_all=df_all,
            symbols=symbols,
            candidate_id="CAND_A",
            name="5m Raw Momentum (Control)",
            timeframe="5min",
            entry_signal_fn=lambda b: (
                b["ema_9"] > b["ema_21"] and 45.0 <= b["rsi_14"] <= 68.0 and b["close"] > b["ema_9"]
            ),
            stop_loss_pct=0.0040,  # 0.40%
            take_profit_pct=0.0100,  # 1.00%
            max_holding_bars=12,   # 60 mins
            allowed_hours_fn=lambda t: pd.to_datetime("09:20:00").time() <= t <= pd.to_datetime("14:30:00").time()
        )
        results.append(res_a)

        # -------------------------------------------------------------
        # Candidate B: 15m Trend + Volume Expansion Filter (V2_15M style)
        # -------------------------------------------------------------
        print("-> Running Candidate B: 15m Trend + Volume Filter (V2_15M)...")
        # Entry rule: Close > EMA 50, EMA 9 > EMA 21, Volume > 1.25x 20-period SMA, Avoid lunch chop (11:30-13:30)
        res_b = self.evaluate_candidate(
            df_all=df_all,
            symbols=symbols,
            candidate_id="CAND_B",
            name="15m Trend + Volume Filter",
            timeframe="15min",
            entry_signal_fn=lambda b: (
                b["close"] > b["ema_50"] and 
                b["ema_9"] > b["ema_21"] and 
                b["volume"] > 1.25 * b["vol_sma_20"] and 
                50.0 <= b["rsi_14"] <= 70.0
            ),
            stop_loss_pct=0.0060,  # 0.60% stop
            take_profit_pct=0.0160,  # 1.60% target (2.67:1 R:R)
            max_holding_bars=12,   # 180 mins
            allowed_hours_fn=lambda t: (
                (pd.to_datetime("09:30:00").time() <= t <= pd.to_datetime("11:30:00").time()) or
                (pd.to_datetime("13:30:00").time() <= t <= pd.to_datetime("14:30:00").time())
            )
        )
        results.append(res_b)

        # -------------------------------------------------------------
        # Candidate C: 15m Mean Reversion Pullback in Trend (HYPO001 style)
        # -------------------------------------------------------------
        print("-> Running Candidate C: 15m Pullback in Bull Trend (HYPO001)...")
        # Entry rule: EMA 20 > EMA 50, RSI oversold pullback (38 <= RSI <= 48), Bullish candle (Close > Open)
        res_c = self.evaluate_candidate(
            df_all=df_all,
            symbols=symbols,
            candidate_id="CAND_C",
            name="15m Trend Pullback Reversion",
            timeframe="15min",
            entry_signal_fn=lambda b: (
                b["ema_20"] > b["ema_50"] and 
                38.0 <= b["rsi_14"] <= 50.0 and 
                b["close"] > b["open"]
            ),
            stop_loss_pct=0.0050,  # 0.50% stop
            take_profit_pct=0.0150,  # 1.50% target (3:1 R:R)
            max_holding_bars=8,    # 120 mins
            allowed_hours_fn=lambda t: pd.to_datetime("09:45:00").time() <= t <= pd.to_datetime("14:00:00").time()
        )
        results.append(res_c)

        # -------------------------------------------------------------
        # Candidate D: 60m Structural Momentum (V3_60M style)
        # -------------------------------------------------------------
        print("-> Running Candidate D: 60m Structural Momentum (V3_60M)...")
        # Entry rule: Close > EMA 20, RSI > 52, Volume > SMA
        res_d = self.evaluate_candidate(
            df_all=df_all,
            symbols=symbols,
            candidate_id="CAND_D",
            name="60m Structural Momentum",
            timeframe="60min",
            entry_signal_fn=lambda b: (
                b["close"] > b["ema_20"] and 
                b["close"] > b["open"] and 
                52.0 <= b["rsi_14"] <= 72.0 and
                b["volume"] > b["vol_sma_20"]
            ),
            stop_loss_pct=0.0100,  # 1.00% stop
            take_profit_pct=0.0250,  # 2.50% target (2.5:1 R:R)
            max_holding_bars=6,    # 360 mins
            allowed_hours_fn=lambda t: pd.to_datetime("09:30:00").time() <= t <= pd.to_datetime("13:30:00").time()
        )
        results.append(res_d)

        return results


def generate_optimization_report(results: List[CandidateResult], output_path: str):
    """Generates the Phase 6 Timeframe & Signal Optimization Report."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    lines = []
    lines.append("# AlphaNSE Phase 6: Timeframe, Regime & Signal Optimization Report")
    lines.append("")
    lines.append("**Objective:** Isolate true positive gross market alpha before testing survival against realistic execution friction.")
    lines.append("**Execution Regime:** BASE Friction (5 bps slippage, 3 bps half-spread, 2% rejection, Zerodha statutory cost schedule)")
    lines.append("**Baseline Capital:** ₹1,500.00 (with 5x SEBI Intraday MIS Leverage = ₹7,500 purchasing power)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. Candidate Comparison Matrix")
    lines.append("")
    lines.append("| Candidate | Timeframe | Trades | Win Rate | Gross P&L | Total Friction | Net P&L | Net ROI | Profit Factor | **Gross Exp/Trd** | **Net Exp/Trd** | Max DD (%) |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

    for r in results:
        lines.append(
            f"| **{r.name}** | {r.timeframe} | {r.total_trades} | {r.win_rate_pct:.1f}% | "
            f"₹{r.gross_pnl:+,.2f} | ₹{r.total_friction:,.2f} | ₹{r.net_pnl:+,.2f} | "
            f"{r.net_roi_pct:+.1f}% | {r.profit_factor:.2f} | "
            f"**₹{r.gross_expectancy_per_trade:+,.2f}** | **₹{r.net_expectancy_per_trade:+,.2f}** | {r.max_drawdown_pct:.1f}% |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 2. Quantitative Insights & Comparative Analysis")
    lines.append("")

    for r in results:
        status_flag = "🟢 POSITIVE GROSS ALPHA" if r.gross_expectancy_per_trade > 0 else "🔴 NEGATIVE GROSS ALPHA"
        net_flag = "🟢 SURVIVES FRICTION" if r.net_expectancy_per_trade > 0 else "🔴 DESTROYED BY FRICTION"
        lines.append(f"### {r.candidate_id}: {r.name} ({r.timeframe})")
        lines.append(f"- **Gross Alpha Status:** {status_flag} (₹{r.gross_expectancy_per_trade:+,.2f} / trade)")
        lines.append(f"- **Net Viability Status:** {net_flag} (₹{r.net_expectancy_per_trade:+,.2f} / trade)")
        lines.append(f"- **Friction Impact:** Incurred ₹{r.total_friction:,.2f} in friction across {r.total_trades} trades (average ₹{r.total_friction/r.total_trades if r.total_trades else 0:.2f} per trade).")
        lines.append(f"- **Holding Duration:** Average holding duration was {r.avg_holding_mins:.1f} minutes.")
        lines.append("")

    report_content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    return report_content


if __name__ == "__main__":
    print("\n" + "=" * 75)
    print("      AlphaNSE Phase 6: Timeframe & Signal Optimization Engine")
    print("=" * 75)
    
    optimizer = TimeframeStrategyOptimizer(initial_capital=1500.0)
    results = optimizer.run_all_candidates()

    report_file = os.path.join(
        optimizer.workspace_root, "v3", "reports", "TIMEFRAME_AND_SIGNAL_OPTIMIZATION_REPORT.md"
    )
    generate_optimization_report(results, report_file)

    print("\n" + "=" * 75)
    print("Optimization experiment completed successfully!")
    print(f"Report written to -> {report_file}")
    print("=" * 75 + "\n")
