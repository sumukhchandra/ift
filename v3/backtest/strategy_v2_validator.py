#!/usr/bin/env python3
"""
v3/backtest/strategy_v2_validator.py
Validation & Replay Engine for Strategy V2 (15m/5m/1m Trend + Momentum).

Strict Invariants:
1. Sequential bar-by-bar historical replay (Zero Lookahead).
2. Base Friction Regime (Spread: 3 bps, Slippage: 4 bps, Statutory Taxes + Brokerage).
3. Capital: Rs. 1,500 Max, Max Positions: 1, Zero Leverage, Cash Equity Only, No Short Selling.
4. Pre-Trade Gate: EdgeFrictionGate (Target 1.50% vs All-in Friction).
5. Cross-Asset Testing: Evaluates INFY, SBIN, HDFCBANK, RELIANCE to prevent single-stock overfitting.
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
from typing import List, Dict, Any, Optional
import numpy as np

# Ensure workspace root in sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.execution.realistic_simulated_broker import RealisticSimulatedBroker
from v3.execution.edge_friction_gate import EdgeFrictionGate, EdgeFrictionEvaluation
from v3.strategy.v2_multitimeframe_trend import StrategyV2MultiTimeframe
from v3.analytics.performance import PerformanceAnalytics


class StrategyV2BacktestEngine:
    def __init__(
        self,
        symbol: str,
        csv_path: str,
        starting_capital: float = 1500.0,
        max_daily_loss: float = 30.0,
    ):
        self.symbol = symbol
        self.csv_path = csv_path
        self.starting_capital = starting_capital
        self.max_daily_loss = max_daily_loss
        self.edge_gate = EdgeFrictionGate(
            half_spread_bps=3.0,
            slippage_bps=4.0,
            safety_margin_rs=0.50,
            min_net_expectancy_rs=0.25
        )
        self.bars = self._load_data()

    def _load_data(self) -> List[Dict[str, Any]]:
        bars = []
        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                dt = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                bars.append({
                    "timestamp": dt,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(float(row["volume"])),
                })
        bars.sort(key=lambda x: x["timestamp"])
        return bars

    def run_backtest(self) -> Dict[str, Any]:
        broker = RealisticSimulatedBroker(
            scenario="BASE",
            starting_cash=self.starting_capital,
            max_daily_loss=self.max_daily_loss,
            seed=101,
            max_positions=1,
        )
        strategy = StrategyV2MultiTimeframe(
            target_profit_pct=0.0150,   # 1.50% target
            stop_loss_pct=0.0075,        # 0.75% stop loss
            trail_breakeven_pct=0.0080,  # 0.80% breakeven trail
            volume_mult=1.25
        )

        history_bars: List[Dict[str, Any]] = []
        equity_curve = [self.starting_capital]
        current_day = None

        signals_count = 0
        gate_accepted = 0
        gate_rejected = 0

        for bar in self.bars:
            bar_time: datetime = bar["timestamp"]
            bar_date = bar_time.date()
            mid_price = bar["close"]
            bar_vol = bar["volume"]

            # Daily rollover: reset daily circuit breaker if equity intact
            if current_day != bar_date:
                current_day = bar_date
                broker.realized_pnl_today = 0.0
                broker.circuit_breaker_tripped = False
                broker.circuit_breaker_reason = ""

            history_bars.append(bar)

            # Strategy evaluation
            decision = strategy.evaluate_1m_bar(
                bar_1m=bar,
                recent_1m_bars=history_bars[-25:],
                position=broker.position
            )

            action = decision.get("action", "HOLD")

            # Execute Exit
            if action == "SELL" and broker.position:
                broker.execute_order(
                    symbol=self.symbol,
                    side="SELL",
                    requested_qty=broker.position.quantity,
                    mid_price=mid_price,
                    bar_volume=bar_vol,
                    signal_timestamp=bar_time,
                )

            # Execute Entry
            elif action == "BUY" and not broker.position and not broker.circuit_breaker_tripped:
                signals_count += 1
                available_cash = min(broker.cash, self.starting_capital)
                qty = int(available_cash // mid_price)

                if qty >= 1:
                    # Pass through EdgeFrictionGate
                    eval_res: EdgeFrictionEvaluation = self.edge_gate.evaluate_signal(
                        symbol=self.symbol,
                        side="BUY",
                        quantity=qty,
                        mid_price=mid_price,
                        expected_move_pct=0.0150  # 1.50% target
                    )

                    if eval_res.approved:
                        gate_accepted += 1
                        broker.execute_order(
                            symbol=self.symbol,
                            side="BUY",
                            requested_qty=qty,
                            mid_price=mid_price,
                            bar_volume=bar_vol,
                            signal_timestamp=bar_time,
                        )
                    else:
                        gate_rejected += 1

            state = broker.get_portfolio_state(mid_price)
            equity_curve.append(state["true_equity"])

        # Compute complete metrics
        metrics = PerformanceAnalytics.calculate_comprehensive_metrics(
            trade_logs=broker.trade_logs,
            starting_capital=self.starting_capital,
            equity_curve=equity_curve,
            total_spread=broker.total_spread_paid,
            total_slippage=broker.total_slippage_paid,
            total_brokerage=broker.total_brokerage_paid,
            total_taxes=broker.total_taxes_paid,
        )
        metrics["symbol"] = self.symbol
        metrics["signals_generated"] = signals_count
        metrics["gate_accepted"] = gate_accepted
        metrics["gate_rejected"] = gate_rejected
        metrics["trade_logs"] = broker.trade_logs
        return metrics


def run_v2_multi_asset_validation():
    assets = [
        {"symbol": "INFY", "file": "INFY_1m_weekend.csv"},
        {"symbol": "SBIN", "file": "SBIN_1m_weekend.csv"},
        {"symbol": "HDFCBANK", "file": "HDFCBANK_1m_weekend.csv"},
        {"symbol": "RELIANCE", "file": "RELIANCE_1m_weekend.csv"},
    ]

    print("=" * 88)
    print("  [+] STRATEGY V2: MULTI-TIMEFRAME (15m/5m/1m) TREND + MOMENTUM VALIDATION")
    print("  ARCHITECTURE: 15m Trend Filter -> 5m Momentum -> 1m Vol Crossover -> Edge Gate")
    print("  TARGET / STOP: +1.50% Target / -0.75% Stop Loss (2.0:1 Reward:Risk)")
    print("  BROKER: RealisticSimulatedBroker (Base Regime: 3 bps spread, 4 bps slippage)")
    print("  SANDBOX: Rs. 1,500 Capital | Max 1 Position | Zero Leverage | No Shorts")
    print("=" * 88)

    all_results = {}
    combined_trades = []
    total_signals = 0
    total_accepted = 0
    total_rejected = 0

    for asset in assets:
        csv_file = os.path.join(WORKSPACE_ROOT, "QA", "data", asset["file"])
        if not os.path.exists(csv_file):
            print(f"Skipping {asset['symbol']}: File not found.")
            continue

        engine = StrategyV2BacktestEngine(
            symbol=asset["symbol"],
            csv_path=csv_file,
            starting_capital=1500.0,
            max_daily_loss=30.0
        )
        res = engine.run_backtest()
        all_results[asset["symbol"]] = res
        combined_trades.extend(res["trade_logs"])
        total_signals += res["signals_generated"]
        total_accepted += res["gate_accepted"]
        total_rejected += res["gate_rejected"]

        print(f"\n[{asset['symbol']:10s}] Signals: {res['signals_generated']} (Accepted: {res['gate_accepted']}, Rejected: {res['gate_rejected']})")
        print(f"  Trades: {res['total_trades']} | Win Rate: {res['win_rate_pct']}% | Profit Factor: {res['profit_factor']}")
        print(f"  Gross P&L: Rs. {res['gross_pnl_rs']:+.2f} | Friction: Rs. {res['total_friction_rs']:.2f}")
        print(f"  Net P&L:   Rs. {res['net_pnl_rs']:+.2f} | Net Expectancy: Rs. {res['net_expectancy_rs']:+.2f} / trade")

    # Aggregate Portfolio Metrics
    tot_spread = sum(r["spread_cost_rs"] for r in all_results.values())
    tot_slip = sum(r["slippage_cost_rs"] for r in all_results.values())
    tot_brok = sum(r["brokerage_rs"] for r in all_results.values())
    tot_tax = sum(r["statutory_taxes_rs"] for r in all_results.values())

    portfolio_metrics = PerformanceAnalytics.calculate_comprehensive_metrics(
        trade_logs=combined_trades,
        starting_capital=1500.0,
        equity_curve=None,
        total_spread=tot_spread,
        total_slippage=tot_slip,
        total_brokerage=tot_brok,
        total_taxes=tot_tax,
    )
    portfolio_metrics["total_signals"] = total_signals
    portfolio_metrics["gate_accepted"] = total_accepted
    portfolio_metrics["gate_rejected"] = total_rejected
    portfolio_metrics["sample_adequate"] = len(combined_trades) >= 15

    print("\n" + "=" * 88)
    print("  [PORTFOLIO AGGREGATE SUMMARY -- STRATEGY V2]")
    print(f"  Total Trades Across 4 Assets: {portfolio_metrics['total_trades']} (Sample Adequate >= 15: {portfolio_metrics['sample_adequate']})")
    print(f"  Win Rate: {portfolio_metrics['win_rate_pct']}% | Profit Factor: {portfolio_metrics['profit_factor']}")
    print(f"  Gross P&L: Rs. {portfolio_metrics['gross_pnl_rs']:+.2f}")
    print(f"  Total Friction: Rs. {portfolio_metrics['total_friction_rs']:.2f} (Spread: Rs. {tot_spread:.2f}, Slippage: Rs. {tot_slip:.2f})")
    print(f"  Net Realized: Rs. {portfolio_metrics['net_pnl_rs']:+.2f}")
    print(f"  Net Expectancy Per Trade: Rs. {portfolio_metrics['net_expectancy_rs']:+.2f} / trade")
    print("=" * 88)

    # Save Strategy V2 Report
    report_path = os.path.join(WORKSPACE_ROOT, "v3", "reports", "STRATEGY_V2_VALIDATION_REPORT.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 🚀 AlphaNSE Strategy V2 — Multi-Timeframe Trend & Momentum Audit\n\n")
        f.write(f"**Strategy Type:** Multi-Timeframe (15m Trend + 5m Momentum + 1m Volume Trigger)  \n")
        f.write(f"**Target / Stop Loss:** **`+1.50%`** Target / **`-0.75%`** Stop Loss (2.0:1 Reward:Risk)  \n")
        f.write(f"**Execution Mode:** `RealisticSimulatedBroker` (Base Friction: 3 bps spread, 4 bps slippage)  \n")
        f.write(f"**Gatekeeper:** `EdgeFrictionGate` (Required: $\\text{{Gross Edge}} > \\text{{Friction}} + \\text{{Safety Margin}}$)  \n")
        f.write(f"**Capital Sandbox:** ₹1,500 Max Capital | Max 1 Position | Zero Leverage | No Shorts | ₹30 Daily Loss Limit  \n\n")
        f.write("---\n\n")

        f.write("## 1. Cross-Asset Performance Comparison Matrix\n\n")
        f.write("| Performance Metric | INFY | SBIN | HDFCBANK | RELIANCE | Combined Portfolio |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: |\n")

        infy = all_results.get("INFY", {})
        sbin = all_results.get("SBIN", {})
        hdfc = all_results.get("HDFCBANK", {})
        rel = all_results.get("RELIANCE", {})
        comb = portfolio_metrics

        f.write(f"| **Signals Generated** | {infy.get('signals_generated', 0)} | {sbin.get('signals_generated', 0)} | {hdfc.get('signals_generated', 0)} | {rel.get('signals_generated', 0)} | {comb.get('total_signals', 0)} |\n")
        f.write(f"| **Edge Gate Accepted** | {infy.get('gate_accepted', 0)} | {sbin.get('gate_accepted', 0)} | {hdfc.get('gate_accepted', 0)} | {rel.get('gate_accepted', 0)} | {comb.get('gate_accepted', 0)} |\n")
        f.write(f"| **Paper Trades Executed** | {infy.get('total_trades', 0)} | {sbin.get('total_trades', 0)} | {hdfc.get('total_trades', 0)} | {rel.get('total_trades', 0)} | **{comb.get('total_trades', 0)}** |\n")
        f.write(f"| **Win Rate (%)** | {infy.get('win_rate_pct', 0.0)}% | {sbin.get('win_rate_pct', 0.0)}% | {hdfc.get('win_rate_pct', 0.0)}% | {rel.get('win_rate_pct', 0.0)}% | **{comb.get('win_rate_pct', 0.0)}%** |\n")
        f.write(f"| **Gross Theoretical P&L** | ₹{infy.get('gross_pnl_rs', 0.0):+.2f} | ₹{sbin.get('gross_pnl_rs', 0.0):+.2f} | ₹{hdfc.get('gross_pnl_rs', 0.0):+.2f} | ₹{rel.get('gross_pnl_rs', 0.0):+.2f} | **₹{comb.get('gross_pnl_rs', 0.0):+.2f}** |\n")
        f.write(f"| **Spread Cost Paid** | ₹{infy.get('spread_cost_rs', 0.0):.2f} | ₹{sbin.get('spread_cost_rs', 0.0):.2f} | ₹{hdfc.get('spread_cost_rs', 0.0):.2f} | ₹{rel.get('spread_cost_rs', 0.0):.2f} | ₹{tot_spread:.2f} |\n")
        f.write(f"| **Adverse Slippage** | ₹{infy.get('slippage_cost_rs', 0.0):.2f} | ₹{sbin.get('slippage_cost_rs', 0.0):.2f} | ₹{hdfc.get('slippage_cost_rs', 0.0):.2f} | ₹{rel.get('slippage_cost_rs', 0.0):.2f} | ₹{tot_slip:.2f} |\n")
        f.write(f"| **Brokerage & Taxes** | ₹{infy.get('brokerage_rs', 0.0) + infy.get('statutory_taxes_rs', 0.0):.2f} | ₹{sbin.get('brokerage_rs', 0.0) + sbin.get('statutory_taxes_rs', 0.0):.2f} | ₹{hdfc.get('brokerage_rs', 0.0) + hdfc.get('statutory_taxes_rs', 0.0):.2f} | ₹{rel.get('brokerage_rs', 0.0) + rel.get('statutory_taxes_rs', 0.0):.2f} | ₹{tot_brok + tot_tax:.2f} |\n")
        f.write(f"| **Total Friction Paid** | ₹{infy.get('total_friction_rs', 0.0):.2f} | ₹{sbin.get('total_friction_rs', 0.0):.2f} | ₹{hdfc.get('total_friction_rs', 0.0):.2f} | ₹{rel.get('total_friction_rs', 0.0):.2f} | **₹{comb.get('total_friction_rs', 0.0):.2f}** |\n")
        f.write(f"| **Net Realized P&L** | ₹{infy.get('net_pnl_rs', 0.0):+.2f} | ₹{sbin.get('net_pnl_rs', 0.0):+.2f} | ₹{hdfc.get('net_pnl_rs', 0.0):+.2f} | ₹{rel.get('net_pnl_rs', 0.0):+.2f} | **₹{comb.get('net_pnl_rs', 0.0):+.2f}** |\n")
        f.write(f"| **Net Expectancy / Trade** | ₹{infy.get('net_expectancy_rs', 0.0):+.2f} | ₹{sbin.get('net_expectancy_rs', 0.0):+.2f} | ₹{hdfc.get('net_expectancy_rs', 0.0):+.2f} | ₹{rel.get('net_expectancy_rs', 0.0):+.2f} | **₹{comb.get('net_expectancy_rs', 0.0):+.2f}** |\n")
        f.write(f"| **Profit Factor** | {infy.get('profit_factor', 0.0)} | {sbin.get('profit_factor', 0.0)} | {hdfc.get('profit_factor', 0.0)} | {rel.get('profit_factor', 0.0)} | **{comb.get('profit_factor', 0.0)}** |\n")
        f.write(f"| **Max Drawdown (₹ / %)** | ₹{infy.get('max_drawdown_rs', 0.0)} | ₹{sbin.get('max_drawdown_rs', 0.0)} | ₹{hdfc.get('max_drawdown_rs', 0.0)} | ₹{rel.get('max_drawdown_rs', 0.0)} | ₹{comb.get('max_drawdown_rs', 0.0)} ({comb.get('max_drawdown_pct', 0.0)}%) |\n")
        f.write(f"| **Avg Holding Time** | {infy.get('avg_holding_minutes', 0.0)}m | {sbin.get('avg_holding_minutes', 0.0)}m | {hdfc.get('avg_holding_minutes', 0.0)}m | {rel.get('avg_holding_minutes', 0.0)}m | {comb.get('avg_holding_minutes', 0.0)}m |\n")

        f.write("\n---\n\n")
        f.write("## 2. Head-to-Head Comparison: V1 (Micro-Momentum) vs V2 (Multi-Timeframe Trend)\n\n")
        f.write("| Feature / Metric | Strategy V1 (1m EMA Crossover) | Strategy V2 (15m Trend + 5m Mom + 1m Trigger) |\n")
        f.write("| :--- | :---: | :---: |\n")
        f.write(f"| **Higher Timeframe Filter** | None (Noise prone) | **15m EMA 10/30 Alignment** |\n")
        f.write(f"| **Target / Stop Geometry** | +0.85% / -0.40% | **+1.50% / -0.75% (2.0:1 R:R)** |\n")
        f.write(f"| **Hurdle Clearance Room** | ~0.60% net room | **~1.25% net headroom over friction** |\n")
        f.write(f"| **Sample Adequacy (>= 15 Trades)** | FAILED (10 trades in 3 sessions) | {'PASSED' if comb['sample_adequate'] else 'INSUFFICIENT'} ({comb['total_trades']} trades) |\n")
        f.write(f"| **Net Expectancy / Trade** | -₹4.18 / trade | **₹{comb['net_expectancy_rs']:+.2f} / trade** |\n")

    print(f"\n[SUCCESS] Strategy V2 Report generated at: {report_path}")


if __name__ == "__main__":
    run_v2_multi_asset_validation()
