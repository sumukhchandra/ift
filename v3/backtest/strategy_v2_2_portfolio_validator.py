#!/usr/bin/env python3
"""
v3/backtest/strategy_v2_2_portfolio_validator.py
Multi-Asset Portfolio Replay Engine for Strategy V2.2.

Upgrades in V2.2:
1. MAX 2 Sequential / Concurrent Opportunities (Addressing the Opportunity Lock Bottleneck):
   - Sizing: Allocates capital up to 50% (Rs. 750) per position, or remaining cash for qualifying leaders.
   - Prevents capital from being frozen in a single 3-hour trade while other sector leaders breakout.
2. 15m Trend + 5m Momentum + 1m Trigger + Volume Surge.
3. 09:30 - 12:45 IST Entry Cutoff (Protects from 15:15 closing auction volatility).
4. Relative-Strength Leader Selection: Discards flat/lagging assets, picks the highest RS candidate.
5. Edge/Friction Gate: Validates 1.50% target > All-in Friction + Safety Margin.
6. Target / Stop: +1.50% Target / -0.75% Stop Loss (2.0:1 Reward:Risk) + Trailing Breakeven (+0.25%).
7. Strict Invariants:
   - Capital: Rs. 1,500 Max
   - Leverage: 1.0x (Cash Equity Only)
   - Short Selling: OFF
   - Daily Loss Limit: Rs. 30.00 (Hard Circuit Breaker)
   - Compounding: OFF
   - Live Trading: OFF (Air-gapped)
"""

import os
import sys

# Configure UTF-8 for console output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import csv
import json
from datetime import datetime, time
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import numpy as np

# Ensure workspace root in sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.execution.realistic_simulated_broker import RealisticSimulatedBroker
from v3.execution.edge_friction_gate import EdgeFrictionGate, EdgeFrictionEvaluation
from v3.strategy.v2_1_relative_strength_trend import StrategyV2_1RelativeStrength
from v3.analytics.performance import PerformanceAnalytics


class MultiAssetV2_2PortfolioEngine:
    def __init__(
        self,
        symbols: List[str],
        data_dir: str,
        starting_capital: float = 1500.0,
        max_daily_loss: float = 30.0,
        max_positions: int = 2,  # V2.2 Upgrade: Max 2 Opportunities
    ):
        self.symbols = symbols
        self.data_dir = data_dir
        self.starting_capital = starting_capital
        self.max_daily_loss = max_daily_loss
        self.max_positions = max_positions

        self.broker = RealisticSimulatedBroker(
            scenario="BASE",
            starting_cash=self.starting_capital,
            max_daily_loss=self.max_daily_loss,
            seed=303,
            max_positions=self.max_positions,
            allow_short=False,
            leverage=1.0,
        )
        self.edge_gate = EdgeFrictionGate(
            half_spread_bps=3.0,
            slippage_bps=4.0,
            safety_margin_rs=0.50,
            min_net_expectancy_rs=0.25
        )
        self.strategies: Dict[str, StrategyV2_1RelativeStrength] = {
            s: StrategyV2_1RelativeStrength(
                target_profit_pct=0.0150,     # +1.50% target
                stop_loss_pct=0.0075,          # -0.75% stop loss
                trail_breakeven_pct=0.0080,    # +0.80% breakeven trail
                volume_mult=1.25,
                entry_start=time(9, 30),
                entry_cutoff=time(12, 45),     # Hard 12:45 IST cutoff
            )
            for s in self.symbols
        }

        self.symbol_bars: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.recent_bars: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.all_timestamps: List[str] = []
        self._load_all_data()

    def _load_all_data(self):
        """Loads and aligns all asset bars by minute timestamp."""
        ts_set = set()
        for sym in self.symbols:
            fname = os.path.join(self.data_dir, f"{sym}_1m_weekend.csv")
            if not os.path.exists(fname):
                continue
            self.symbol_bars[sym] = {}
            with open(fname, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts = row["timestamp"]
                    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    bar = {
                        "timestamp": dt,
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": int(float(row["volume"])),
                        "symbol": sym,
                    }
                    self.symbol_bars[sym][ts] = bar
                    ts_set.add(ts)

        self.all_timestamps = sorted(list(ts_set))

    def run_simulation(self) -> Dict[str, Any]:
        equity_curve = [self.starting_capital]
        current_day = None

        total_signals_seen = 0
        signals_filtered_by_gate = 0
        signals_filtered_by_selection = 0

        for ts in self.all_timestamps:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            bar_date = dt.date()

            # Day rollover
            if current_day != bar_date:
                current_day = bar_date
                self.broker.realized_pnl_today = 0.0
                self.broker.circuit_breaker_tripped = False
                self.broker.circuit_breaker_reason = ""

            # Step 1: Update all strategy aggregators and bar histories
            current_minute_bars: Dict[str, Dict[str, Any]] = {}
            for sym in self.symbols:
                if sym in self.symbol_bars and ts in self.symbol_bars[sym]:
                    bar = self.symbol_bars[sym][ts]
                    current_minute_bars[sym] = bar
                    self.recent_bars[sym].append(bar)

            # Step 2: Manage active open positions
            open_symbols = list(self.broker.positions.keys())
            for held_sym in open_symbols:
                if held_sym in current_minute_bars and held_sym in self.broker.positions:
                    pos = self.broker.positions[held_sym]
                    bar = current_minute_bars[held_sym]
                    setattr(pos, "last_price", bar["close"])

                    strat = self.strategies[held_sym]
                    dec = strat.evaluate_1m_bar(
                        bar_1m=bar,
                        recent_1m_bars=self.recent_bars[held_sym][-25:],
                        position=pos
                    )
                    if dec.get("action") == "SELL":
                        self.broker.execute_order(
                            symbol=held_sym,
                            side="SELL",
                            requested_qty=pos.quantity,
                            mid_price=bar["close"],
                            bar_volume=bar["volume"],
                            signal_timestamp=dt,
                        )

            # Step 3: If position count < max_positions, evaluate entry candidates
            current_pos_count = len(self.broker.positions)
            if current_pos_count < self.max_positions and not self.broker.circuit_breaker_tripped:
                buy_candidates = []
                for sym, bar in current_minute_bars.items():
                    # Skip if already holding a position in this symbol
                    if sym in self.broker.positions:
                        continue

                    strat = self.strategies[sym]
                    dec = strat.evaluate_1m_bar(
                        bar_1m=bar,
                        recent_1m_bars=self.recent_bars[sym][-25:],
                        position=None
                    )
                    if dec.get("action") == "BUY":
                        total_signals_seen += 1
                        mid_px = bar["close"]

                        # V2.2 Position Sizing: Up to 50% of starting capital (Rs. 750) or remaining cash
                        allocation_cap = self.starting_capital / self.max_positions
                        max_cash_for_pos = min(self.broker.cash, allocation_cap if current_pos_count == 0 else self.broker.cash)
                        qty = int(max_cash_for_pos // mid_px)

                        # If mid_px > allocation_cap but mid_px <= cash and no open positions, allow 1 share
                        if qty == 0 and current_pos_count == 0 and self.broker.cash >= mid_px:
                            qty = 1

                        if qty >= 1:
                            # Evaluate through EdgeFrictionGate
                            eval_res: EdgeFrictionEvaluation = self.edge_gate.evaluate_signal(
                                symbol=sym,
                                side="BUY",
                                quantity=qty,
                                mid_price=mid_px,
                                expected_move_pct=0.0150  # 1.50% target
                            )
                            if eval_res.approved:
                                buy_candidates.append({
                                    "symbol": sym,
                                    "mid_price": mid_px,
                                    "quantity": qty,
                                    "volume": bar["volume"],
                                    "rs_score": dec.get("rs_score", 0.0),
                                })
                            else:
                                signals_filtered_by_gate += 1

                # Step 4: Relative Strength Leader Selection
                if buy_candidates:
                    # Sort descending by Relative Strength
                    buy_candidates.sort(key=lambda x: x["rs_score"], reverse=True)
                    # How many slots available?
                    slots_available = self.max_positions - len(self.broker.positions)
                    leaders_to_enter = buy_candidates[:slots_available]
                    signals_filtered_by_selection += max(0, len(buy_candidates) - len(leaders_to_enter))

                    for leader in leaders_to_enter:
                        if self.broker.cash >= leader["mid_price"] * leader["quantity"]:
                            self.broker.execute_order(
                                symbol=leader["symbol"],
                                side="BUY",
                                requested_qty=leader["quantity"],
                                mid_price=leader["mid_price"],
                                bar_volume=leader["volume"],
                                signal_timestamp=dt,
                            )

            # Mark to market tracking
            state = self.broker.get_portfolio_state()
            equity_curve.append(state["true_equity"])

        # Compute complete portfolio metrics
        metrics = PerformanceAnalytics.calculate_comprehensive_metrics(
            trade_logs=self.broker.trade_logs,
            starting_capital=self.starting_capital,
            equity_curve=equity_curve,
            total_spread=self.broker.total_spread_paid,
            total_slippage=self.broker.total_slippage_paid,
            total_brokerage=self.broker.total_brokerage_paid,
            total_taxes=self.broker.total_taxes_paid,
        )
        metrics["total_signals_seen"] = total_signals_seen
        metrics["signals_filtered_by_gate"] = signals_filtered_by_gate
        metrics["signals_filtered_by_selection"] = signals_filtered_by_selection
        metrics["trade_logs"] = self.broker.trade_logs
        metrics["sample_adequate"] = len(self.broker.trade_logs) >= 15
        return metrics


def run_v2_2_portfolio_validation():
    universe = ["HDFCBANK", "SBIN", "RELIANCE", "INFY", "AXISBANK", "TATASTEEL", "ICICIBANK", "BAJFINANCE"]
    data_dir = os.path.join(WORKSPACE_ROOT, "QA", "data")

    print("=" * 88)
    print("  [+] STRATEGY V2.2: MULTI-ASSET PORTFOLIO VALIDATION (MAX 2 OPPORTUNITIES)")
    print(f"  UNIVERSE: {', '.join(universe)}")
    print("  ENTRY WINDOW: 09:30 - 12:45 IST")
    print("  OPPORTUNITY THROUGHPUT: Max 2 Concurrent / Sequential Opportunities")
    print("  TARGET / STOP: +1.50% Target / -0.75% Stop Loss (2.0:1 Reward:Risk)")
    print("  BROKER: RealisticSimulatedBroker (Base Regime: 3 bps spread, 4 bps slippage)")
    print("  SANDBOX: Rs. 1,500 Capital | Max 2 Positions | Leverage 1.0x (Cash) | No Shorts")
    print("=" * 88)

    engine = MultiAssetV2_2PortfolioEngine(
        symbols=universe,
        data_dir=data_dir,
        starting_capital=1500.0,
        max_daily_loss=30.0,
        max_positions=2
    )
    res = engine.run_simulation()

    print("\n[PORTFOLIO EXECUTION RESULTS -- STRATEGY V2.2]")
    print(f"  Total Signals Evaluated:     {res['total_signals_seen']}")
    print(f"  Signals Filtered by Gate:    {res['signals_filtered_by_gate']}")
    print(f"  Signals Filtered by RS Rank: {res['signals_filtered_by_selection']}")
    print(f"  Paper Trades Executed:       {res['total_trades']} (Sample Adequate >= 15: {res['sample_adequate']})")
    print(f"  Winning Trades / Losing:     {res['winning_trades']}W / {res['losing_trades']}L")
    print(f"  Win Rate (%):                {res['win_rate_pct']}%")
    print(f"  Profit Factor:               {res['profit_factor']}")
    print(f"  Gross Theoretical P&L:       Rs. {res['gross_pnl_rs']:+.2f}")
    print(f"  Total Friction Paid:         Rs. {res['total_friction_rs']:.2f} (Spread: Rs. {res['spread_cost_rs']:.2f}, Slippage: Rs. {res['slippage_cost_rs']:.2f})")
    print(f"  Brokerage & Taxes:           Rs. {res['brokerage_rs'] + res['statutory_taxes_rs']:.2f}")
    print(f"  Net Realized P&L:            Rs. {res['net_pnl_rs']:+.2f}")
    print(f"  Net Expectancy Per Trade:    Rs. {res['net_expectancy_rs']:+.2f} / trade")
    print(f"  Max Drawdown (Rs. / %):      Rs. {res['max_drawdown_rs']:.2f} ({res['max_drawdown_pct']:.2f}%)")
    print(f"  Average Holding Time:        {res['avg_holding_minutes']:.1f} minutes")
    print("=" * 88)

    # Detailed trade breakdown
    print("\nDETAILED TRADE LOGS:")
    for idx, t in enumerate(res["trade_logs"], 1):
        print(f"  Trade {idx:02d} [{t['symbol']:10s}]: {t['entry_time']} -> {t['exit_time']} | Qty: {t['quantity']} | Gross: Rs. {t['gross_pnl']:+6.2f} | Fric: Rs. {t['total_friction']:4.2f} | Net: Rs. {t['net_pnl']:+6.2f} | Hold: {t['holding_minutes']}m")

    # Save Strategy V2.2 Report & Ledger
    report_path = os.path.join(WORKSPACE_ROOT, "v3", "reports", "STRATEGY_V2_2_PORTFOLIO_REPORT.md")
    ledger_path = os.path.join(WORKSPACE_ROOT, "v3", "reports", "STRATEGY_V2_2_TRADE_LEDGER.json")

    with open(ledger_path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 🚀 AlphaNSE Strategy V2.2 — Multi-Asset Portfolio Validation Report\n\n")
        f.write(f"**Strategy Architecture:** V2.2 (15m Trend + 5m Mom + 1m Trigger) + Relative Strength Leader Selection  \n")
        f.write(f"**Structural Upgrade:** Max **`2`** Concurrent / Sequential Opportunities (Resolving Opportunity Lock)  \n")
        f.write(f"**Execution Window:** `09:30 – 12:45 IST` (Strict Cutoff)  \n")
        f.write(f"**Target / Stop Loss:** **`+1.50%`** Target / **`-0.75%`** Stop Loss (2.0:1 Reward:Risk)  \n")
        f.write(f"**Universe:** 8 Liquid NSE Equities (`HDFCBANK`, `SBIN`, `RELIANCE`, `INFY`, `AXISBANK`, `TATASTEEL`, `ICICIBANK`, `BAJFINANCE`)  \n")
        f.write(f"**Execution Broker:** `RealisticSimulatedBroker` (Base Regime: 3 bps spread, 4 bps slippage)  \n")
        f.write(f"**Sandbox Limits:** Capital: **`₹1,500.00`** | Max Positions: **`2`** | Leverage: **`1.0x`** | Daily Loss Limit: **`₹30.00`**  \n\n")
        f.write("---\n\n")

        f.write("## 1. Evolution Matrix: V1 vs V2 vs V2.1 vs V2.2\n\n")
        f.write("| Performance Metric | Strategy V1 (1m Scalp) | Strategy V2 (Single Stock) | Strategy V2.1 (1 Pos Leader) | Strategy V2.2 (Max 2 Opps) |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: |\n")
        f.write(f"| **Opportunity Capacity** | 1 Position | 1 Position | 1 Position | **Max 2 Opportunities** |\n")
        f.write(f"| **Entry Cutoff Window** | 09:20 - 14:45 | 09:30 - 14:45 | 09:30 - 12:45 | **09:30 - 12:45 IST** |\n")
        f.write(f"| **Paper Trades Executed** | 23 | 12 | 6 | **{res['total_trades']}** |\n")
        f.write(f"| **Sample Adequacy (>= 15 Trades)** | PASSED (23 trades) | INSUFFICIENT (12 trades) | INSUFFICIENT (6 trades) | **{'PASSED' if res['sample_adequate'] else 'INSUFFICIENT'} ({res['total_trades']} trades)** |\n")
        f.write(f"| **Winning Trades / Losing** | 2W / 21L | 3W / 9L | 1W / 5L | **{res['winning_trades']}W / {res['losing_trades']}L** |\n")
        f.write(f"| **Win Rate (%)** | 8.7% | 25.0% | 16.67% | **{res['win_rate_pct']}%** |\n")
        f.write(f"| **Gross Theoretical P&L** | ₹-15.83 | ₹-27.22 | ₹-15.42 | **₹{res['gross_pnl_rs']:+.2f}** |\n")
        f.write(f"| **Total Friction Paid** | ₹36.16 | ₹38.79 | ₹18.64 | **₹{res['total_friction_rs']:.2f}** |\n")
        f.write(f"| **Net Realized P&L** | ₹-51.99 | ₹-66.01 | ₹-34.06 | **₹{res['net_pnl_rs']:+.2f}** |\n")
        f.write(f"| **Net Expectancy / Trade** | ₹-2.26 | ₹-5.50 | ₹-5.68 | **₹{res['net_expectancy_rs']:+.2f} / trade** |\n")
        f.write(f"| **Profit Factor** | 0.26 | 0.57 | 0.57 | **{res['profit_factor']}** |\n")
        f.write(f"| **Max Drawdown (₹ / %)** | ₹45.60 (3.04%) | ₹73.96 (4.93%) | ₹25.58 (1.71%) | **₹{res['max_drawdown_rs']:.2f} ({res['max_drawdown_pct']:.2f}%)** |\n")
        f.write(f"| **Average Holding Time** | 10.6 mins | 171.2 mins | 208.0 mins | **{res['avg_holding_minutes']:.1f} mins** |\n")

        f.write("\n---\n\n")
        f.write("## 2. Decision Tree Evaluation\n\n")

        passed_exp = res["net_expectancy_rs"] > 0
        passed_smp = res["sample_adequate"]

        f.write("```text\n")
        f.write("Strategy V2.2 Portfolio Test\n")
        f.write("        │\n")
        if passed_exp and passed_smp:
            f.write("        └── Net Expectancy > 0 AND Sample >= 15 (PASSED: ₹{:+.2f}/trade)\n".format(res['net_expectancy_rs']))
            f.write("                │\n")
            f.write("                ▼\n")
            f.write("        Proceed to Controlled Live Deployment Review on Dhan Adapter\n")
        elif passed_exp and not passed_smp:
            f.write("        └── Net Expectancy > 0 BUT Sample < 15 (TENTATIVE POSITIVE)\n")
            f.write("                │\n")
            f.write("                ▼\n")
            f.write("        Continue Forward Paper Trading to Reach >= 15 Trades\n")
        else:
            f.write("        └── Net Expectancy <= 0 (FAILED: ₹{:+.2f}/trade)\n".format(res['net_expectancy_rs']))
            f.write("                │\n")
            f.write("                ▼\n")
            f.write("        DO NOT TRADE LIVE -> Modify Strategy / Structural Iteration\n")
        f.write("```\n\n")

        f.write("## 3. Trade-by-Trade Execution Ledger\n\n")
        f.write("| # | Symbol | Entry Time | Exit Time | Qty | Gross P&L | Friction | Net P&L | Holding Mins |\n")
        f.write("| :-: | :---: | :---: | :---: | :-: | :---: | :---: | :---: | :-: |\n")
        for idx, t in enumerate(res["trade_logs"], 1):
            f.write(f"| {idx:02d} | **{t['symbol']}** | {t['entry_time']} | {t['exit_time']} | {t['quantity']} | ₹{t['gross_pnl']:+.2f} | ₹{t['total_friction']:.2f} | **₹{t['net_pnl']:+.2f}** | {t['holding_minutes']}m |\n")

    print(f"\n[SUCCESS] Strategy V2.2 Report generated at: {report_path}")
    print(f"[SUCCESS] Strategy V2.2 Ledger saved at: {ledger_path}")


if __name__ == "__main__":
    run_v2_2_portfolio_validation()
