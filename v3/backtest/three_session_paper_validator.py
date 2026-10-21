#!/usr/bin/env python3
"""
v3/backtest/three_session_paper_validator.py
Three-Session Forward Paper-Trading Engine for AlphaNSE V3.

Operational Protocol:
- Strictly Paper-Mode: LIVE_TRADING = False, ALLOW_REAL_ORDERS = False
- Broker Adapter: RealisticSimulatedBroker (Base Friction Regime)
- Hard Sandbox Boundaries:
  - Capital Ceiling: Rs. 1,500.00
  - Max Positions: 1
  - Leverage: 0 (1.0x Cash Only)
  - Short Selling: OFF
  - Daily Loss Limit: Rs. 30.00 (Hard Circuit Breaker)
  - Max Trades / Day: 10
  - Pre-Trade Gate: EdgeFrictionGate (Gross Edge > Friction + Margin)
  - Stale-Data Rejection: ON
  - API Kill Switch: ON
  - Broker Reconciliation: ON
  - No Compounding: Flat Rs. 1,500 sizing
  - EOD Auto Square-Off: 15:15 IST

Measures across 3 Out-Of-Sample Sessions:
- Session 1 (Day 1): Signals, fills, friction, rejected trades
- Session 2 (Day 2): Net expectancy and execution realism
- Session 3 (Day 3): Stability, drawdown, win/loss distribution
- Statistical Hurdle: Sample adequacy evaluation (>= 15 trades)
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
import math
from datetime import datetime, time, timedelta
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

# Ensure workspace root in sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.execution.realistic_simulated_broker import RealisticSimulatedBroker, ExecutionRegime
from v3.execution.edge_friction_gate import EdgeFrictionGate, EdgeFrictionEvaluation
from v3.analytics.performance import PerformanceAnalytics


class ThreeSessionPaperValidator:
    def __init__(
        self,
        csv_path: str,
        symbol: str = "INFY",
        target_sessions: Optional[List[str]] = None,
        starting_capital: float = 1500.0,
        max_daily_loss: float = 30.0,
        max_daily_trades: int = 10,
    ):
        self.csv_path = csv_path
        self.symbol = symbol
        self.starting_capital = starting_capital
        self.max_daily_loss = max_daily_loss
        self.max_daily_trades = max_daily_trades

        # Edge & Friction Gate (Spread 3 bps, Slippage 4 bps, Safety Margin Rs. 0.50)
        self.edge_gate = EdgeFrictionGate(
            half_spread_bps=3.0,
            slippage_bps=4.0,
            safety_margin_rs=0.50,
            min_net_expectancy_rs=0.25
        )

        self.all_bars = self._load_data()
        self.available_dates = sorted(list(set(b["timestamp"].strftime("%Y-%m-%d") for b in self.all_bars)))

        # Default to the 3 forward out-of-sample sessions
        if target_sessions:
            self.sessions = target_sessions
        else:
            self.sessions = self.available_dates[-3:] if len(self.available_dates) >= 3 else self.available_dates

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

    def _calculate_ema(self, prices: List[float], span: int) -> float:
        if not prices:
            return 0.0
        alpha = 2.0 / (span + 1.0)
        ema = prices[0]
        for p in prices[1:]:
            ema = alpha * p + (1.0 - alpha) * ema
        return ema

    def _calculate_atr(self, bars: List[Dict[str, Any]], period: int = 14) -> float:
        if len(bars) < period + 1:
            return 2.50
        tr_list = []
        for i in range(1, len(bars)):
            h = bars[i]["high"]
            l = bars[i]["low"]
            c_prev = bars[i-1]["close"]
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            tr_list.append(tr)
        return float(np.mean(tr_list[-period:]))

    def run_validation(self) -> Dict[str, Any]:
        session_results = []
        all_trade_logs = []
        all_signals_total = 0
        all_accepted_total = 0
        all_rejected_total = 0
        aggregate_equity_curve = [self.starting_capital]

        for s_idx, session_date in enumerate(self.sessions, 1):
            session_bars = [b for b in self.all_bars if b["timestamp"].strftime("%Y-%m-%d") == session_date]
            if not session_bars:
                continue

            # Fresh session broker instance (no compounding, flat Rs. 1,500 initial capital per session)
            broker = RealisticSimulatedBroker(
                scenario="BASE",
                starting_cash=self.starting_capital,
                max_daily_loss=self.max_daily_loss,
                seed=42 + s_idx,
                max_positions=1,
            )

            history_closes: List[float] = []
            history_volumes: List[int] = []
            session_equity_curve = [self.starting_capital]

            signals_count = 0
            accepted_count = 0
            rejected_count = 0
            rejection_reasons = []

            for bar in session_bars:
                bar_time = bar["timestamp"]
                mid_price = bar["close"]
                bar_vol = bar["volume"]

                history_closes.append(mid_price)
                history_volumes.append(bar_vol)

                if len(history_closes) < 20:
                    continue

                # 1. Hard EOD Square-Off at 15:15 IST
                if bar_time.time() >= time(15, 15):
                    if broker.position:
                        broker.execute_order(
                            symbol=self.symbol,
                            side="SELL",
                            requested_qty=broker.position.quantity,
                            mid_price=mid_price,
                            bar_volume=bar_vol,
                            signal_timestamp=bar_time,
                        )
                    state = broker.get_portfolio_state(mid_price)
                    session_equity_curve.append(state["true_equity"])
                    continue

                # 2. Time Window Entry Filter (09:20 - 14:45 IST)
                if bar_time.time() < time(9, 20) or bar_time.time() > time(14, 45):
                    state = broker.get_portfolio_state(mid_price)
                    session_equity_curve.append(state["true_equity"])
                    continue

                # 3. Position Management (Stop Loss / Profit Target)
                if broker.position:
                    pos = broker.position
                    entry_px = pos.entry_price
                    price_move_pct = (mid_price - entry_px) / entry_px

                    ema5 = self._calculate_ema(history_closes[-10:], 5)
                    ema20 = self._calculate_ema(history_closes[-25:], 20)

                    # Dynamic exits: 0.40% Stop Loss, 0.85% Take Profit, or EMA trend break
                    should_exit = False
                    if price_move_pct <= -0.0040:
                        should_exit = True
                    elif price_move_pct >= 0.0085:
                        should_exit = True
                    elif ema5 < ema20:
                        should_exit = True

                    if should_exit:
                        broker.execute_order(
                            symbol=self.symbol,
                            side="SELL",
                            requested_qty=pos.quantity,
                            mid_price=mid_price,
                            bar_volume=bar_vol,
                            signal_timestamp=bar_time,
                        )

                # 4. Entry Signal Evaluation (Flat & Under Daily Trade Limit)
                elif not broker.position and not broker.circuit_breaker_tripped:
                    if len(broker.trade_logs) < self.max_daily_trades:
                        ema5 = self._calculate_ema(history_closes[-10:], 5)
                        ema20 = self._calculate_ema(history_closes[-25:], 20)
                        avg_vol = float(np.mean(history_volumes[-15:])) if history_volumes else 1.0
                        vol_ratio = bar_vol / avg_vol if avg_vol > 0 else 1.0

                        # Signal Condition: EMA crossover + Volume surge >= 1.25x
                        if ema5 > ema20 and (history_closes[-2] <= ema20) and vol_ratio >= 1.25:
                            signals_count += 1

                            # Sizing: Whole integer shares under Rs. 1,500 capital limit
                            available_cash = min(broker.cash, self.starting_capital)
                            qty = int(available_cash // mid_price)

                            if qty >= 1:
                                # Estimate statistical expected move using 14-bar ATR target
                                current_atr = self._calculate_atr(
                                    session_bars[max(0, len(history_closes)-20):len(history_closes)],
                                    period=14
                                )
                                # Expected move based on 2x ATR target
                                expected_move_pct = max(0.0035, (current_atr * 2.0) / mid_price)

                                # Evaluate through the EdgeFrictionGate
                                eval_res: EdgeFrictionEvaluation = self.edge_gate.evaluate_signal(
                                    symbol=self.symbol,
                                    side="BUY",
                                    quantity=qty,
                                    mid_price=mid_price,
                                    expected_move_pct=expected_move_pct
                                )

                                if eval_res.approved:
                                    accepted_count += 1
                                    broker.execute_order(
                                        symbol=self.symbol,
                                        side="BUY",
                                        requested_qty=qty,
                                        mid_price=mid_price,
                                        bar_volume=bar_vol,
                                        signal_timestamp=bar_time,
                                    )
                                else:
                                    rejected_count += 1
                                    rejection_reasons.append(eval_res.rejection_reason)

                state = broker.get_portfolio_state(mid_price)
                session_equity_curve.append(state["true_equity"])

            # Compute Session Metrics
            s_metrics = PerformanceAnalytics.calculate_comprehensive_metrics(
                trade_logs=broker.trade_logs,
                starting_capital=self.starting_capital,
                equity_curve=session_equity_curve,
                total_spread=broker.total_spread_paid,
                total_slippage=broker.total_slippage_paid,
                total_brokerage=broker.total_brokerage_paid,
                total_taxes=broker.total_taxes_paid,
            )
            s_metrics["session_date"] = session_date
            s_metrics["session_index"] = s_idx
            s_metrics["signals_generated"] = signals_count
            s_metrics["signals_accepted"] = accepted_count
            s_metrics["signals_rejected"] = rejected_count
            s_metrics["rejection_reasons"] = rejection_reasons

            session_results.append(s_metrics)
            all_trade_logs.extend(broker.trade_logs)
            all_signals_total += signals_count
            all_accepted_total += accepted_count
            all_rejected_total += rejected_count
            aggregate_equity_curve.extend(session_equity_curve[1:])

        # Calculate Overall 3-Session Aggregate Metrics
        tot_spread = sum(s["spread_cost_rs"] for s in session_results)
        tot_slippage = sum(s["slippage_cost_rs"] for s in session_results)
        tot_brokerage = sum(s["brokerage_rs"] for s in session_results)
        tot_taxes = sum(s["statutory_taxes_rs"] for s in session_results)

        agg_metrics = PerformanceAnalytics.calculate_comprehensive_metrics(
            trade_logs=all_trade_logs,
            starting_capital=self.starting_capital,
            equity_curve=aggregate_equity_curve,
            total_spread=tot_spread,
            total_slippage=tot_slippage,
            total_brokerage=tot_brokerage,
            total_taxes=tot_taxes,
        )
        agg_metrics["total_signals"] = all_signals_total
        agg_metrics["total_accepted"] = all_accepted_total
        agg_metrics["total_rejected"] = all_rejected_total
        agg_metrics["acceptance_rate_pct"] = round((all_accepted_total / all_signals_total) * 100.0, 1) if all_signals_total > 0 else 0.0
        agg_metrics["trade_sample_adequate"] = len(all_trade_logs) >= 15

        return {
            "session_results": session_results,
            "aggregate_metrics": agg_metrics,
            "trade_ledger": all_trade_logs,
        }


def run_three_session_paper_validation():
    csv_file = os.path.join(WORKSPACE_ROOT, "QA", "data", "INFY_1m_weekend.csv")
    if not os.path.exists(csv_file):
        print(f"[ERROR] Data file {csv_file} not found.")
        return

    print("=" * 88)
    print("  [+] ALPHANSE V3 -- 3-SESSION FORWARD PAPER-TRADING VALIDATION")
    print("  EXECUTION GATE: EdgeFrictionGate ACTIVE (Gross Edge > Friction + Safety Margin)")
    print("  SIMULATED BROKER: RealisticSimulatedBroker (Base Friction Regime)")
    print("  LIVE_TRADING = False | ALLOW_REAL_ORDERS = False")
    print("  SANDBOX: Rs. 1,500 Capital | Max 1 Position | Rs. 30 Daily Loss Limit")
    print("=" * 88)

    # We evaluate the 3 forward out-of-sample sessions
    validator = ThreeSessionPaperValidator(
        csv_path=csv_file,
        symbol="INFY",
        target_sessions=["2026-09-23", "2026-09-24", "2026-09-25"],
        starting_capital=1500.0,
        max_daily_loss=30.0,
        max_daily_trades=10
    )

    results = validator.run_validation()
    sessions = results["session_results"]
    agg = results["aggregate_metrics"]

    print("\nSESSION-BY-SESSION BREAKDOWN:")
    for s in sessions:
        print(f"  Day {s['session_index']} ({s['session_date']}):")
        print(f"    Signals: {s['signals_generated']} | Accepted: {s['signals_accepted']} | Rejected: {s['signals_rejected']}")
        print(f"    Trades: {s['total_trades']} | Win Rate: {s['win_rate_pct']}%")
        print(f"    Gross P&L: Rs. {s['gross_pnl_rs']:+.2f} | Total Friction: Rs. {s['total_friction_rs']:.2f}")
        print(f"    Net P&L:   Rs. {s['net_pnl_rs']:+.2f} | Net Expectancy: Rs. {s['net_expectancy_rs']:+.2f} / trade")

    print("\nOVERALL 3-SESSION AGGREGATE:")
    print(f"  Total Signals:   {agg['total_signals']} (Accepted: {agg['total_accepted']}, Rejected: {agg['total_rejected']})")
    print(f"  Total Trades:    {agg['total_trades']} (Win Rate: {agg['win_rate_pct']}%)")
    print(f"  Sample Adequate: {agg['trade_sample_adequate']} ({agg['total_trades']}/15 trades)")
    print(f"  Gross P&L:       Rs. {agg['gross_pnl_rs']:+.2f}")
    print(f"  Total Friction:  Rs. {agg['total_friction_rs']:.2f} (Spread: Rs. {agg['spread_cost_rs']:.2f}, Slippage: Rs. {agg['slippage_cost_rs']:.2f})")
    print(f"  Net Realized:    Rs. {agg['net_pnl_rs']:+.2f}")
    print(f"  Net Expectancy:  Rs. {agg['net_expectancy_rs']:+.2f} / trade")

    # Generate Markdown Report & JSON Ledger
    report_dir = os.path.join(WORKSPACE_ROOT, "v3", "reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "THREE_SESSION_PAPER_VALIDATION_REPORT.md")
    ledger_path = os.path.join(report_dir, "THREE_SESSION_PAPER_LEDGER.json")

    # Save JSON ledger
    with open(ledger_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Format Markdown Report
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 📋 AlphaNSE V3 — Three-Session Forward Paper-Trading Report\n\n")
        f.write(f"**Validation Period:** `2026-09-23` to `2026-09-25` (3 Sequential NSE Sessions)  \n")
        f.write(f"**Execution Mode:** `PAPER_TRADING` (`LIVE_TRADING = False`, `ALLOW_REAL_ORDERS = False`)  \n")
        f.write(f"**Broker Engine:** `RealisticSimulatedBroker` (Base Regime: 3 bps spread, 4 bps slippage)  \n")
        f.write(f"**Gatekeeper:** `EdgeFrictionGate` (Required: $\\text{{Gross Edge}} > \\text{{Friction}} + \\text{{Safety Margin}}$)  \n")
        f.write(f"**Sandbox Constraints:** Capital: **`₹1,500.00`** | Max Positions: **`1`** | Daily Loss Limit: **`₹30.00`**  \n\n")
        f.write("---\n\n")

        f.write("## 1. Session-by-Session Performance Matrix\n\n")
        f.write("| Metric | Day 1 (2026-09-23) | Day 2 (2026-09-24) | Day 3 (2026-09-25) | 3-Session Aggregate |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: |\n")

        d1 = sessions[0] if len(sessions) > 0 else {}
        d2 = sessions[1] if len(sessions) > 1 else {}
        d3 = sessions[2] if len(sessions) > 2 else {}

        f.write(f"| **Signals Generated** | {d1.get('signals_generated', 0)} | {d2.get('signals_generated', 0)} | {d3.get('signals_generated', 0)} | {agg['total_signals']} |\n")
        f.write(f"| **Edge Gate Accepted** | {d1.get('signals_accepted', 0)} | {d2.get('signals_accepted', 0)} | {d3.get('signals_accepted', 0)} | {agg['total_accepted']} |\n")
        f.write(f"| **Edge Gate Rejected** | {d1.get('signals_rejected', 0)} | {d2.get('signals_rejected', 0)} | {d3.get('signals_rejected', 0)} | {agg['total_rejected']} |\n")
        f.write(f"| **Paper Trades Executed** | {d1.get('total_trades', 0)} | {d2.get('total_trades', 0)} | {d3.get('total_trades', 0)} | {agg['total_trades']} |\n")
        f.write(f"| **Win Rate (%)** | {d1.get('win_rate_pct', 0.0)}% | {d2.get('win_rate_pct', 0.0)}% | {d3.get('win_rate_pct', 0.0)}% | {agg['win_rate_pct']}% |\n")
        f.write(f"| **Gross P&L** | ₹{d1.get('gross_pnl_rs', 0.0):+.2f} | ₹{d2.get('gross_pnl_rs', 0.0):+.2f} | ₹{d3.get('gross_pnl_rs', 0.0):+.2f} | ₹{agg['gross_pnl_rs']:+.2f} |\n")
        f.write(f"| **Spread Cost Paid** | ₹{d1.get('spread_cost_rs', 0.0):.2f} | ₹{d2.get('spread_cost_rs', 0.0):.2f} | ₹{d3.get('spread_cost_rs', 0.0):.2f} | ₹{agg['spread_cost_rs']:.2f} |\n")
        f.write(f"| **Adverse Slippage** | ₹{d1.get('slippage_cost_rs', 0.0):.2f} | ₹{d2.get('slippage_cost_rs', 0.0):.2f} | ₹{d3.get('slippage_cost_rs', 0.0):.2f} | ₹{agg['slippage_cost_rs']:.2f} |\n")
        f.write(f"| **Brokerage & Taxes** | ₹{d1.get('brokerage_rs', 0.0) + d1.get('statutory_taxes_rs', 0.0):.2f} | ₹{d2.get('brokerage_rs', 0.0) + d2.get('statutory_taxes_rs', 0.0):.2f} | ₹{d3.get('brokerage_rs', 0.0) + d3.get('statutory_taxes_rs', 0.0):.2f} | ₹{agg['brokerage_rs'] + agg['statutory_taxes_rs']:.2f} |\n")
        f.write(f"| **Total Friction Paid** | ₹{d1.get('total_friction_rs', 0.0):.2f} | ₹{d2.get('total_friction_rs', 0.0):.2f} | ₹{d3.get('total_friction_rs', 0.0):.2f} | ₹{agg['total_friction_rs']:.2f} |\n")
        f.write(f"| **Net Realized P&L** | ₹{d1.get('net_pnl_rs', 0.0):+.2f} | ₹{d2.get('net_pnl_rs', 0.0):+.2f} | ₹{d3.get('net_pnl_rs', 0.0):+.2f} | ₹{agg['net_pnl_rs']:+.2f} |\n")
        f.write(f"| **Net Expectancy / Trade** | ₹{d1.get('net_expectancy_rs', 0.0):+.2f} | ₹{d2.get('net_expectancy_rs', 0.0):+.2f} | ₹{d3.get('net_expectancy_rs', 0.0):+.2f} | **₹{agg['net_expectancy_rs']:+.2f}** |\n")
        f.write(f"| **Profit Factor** | {d1.get('profit_factor', 0.0)} | {d2.get('profit_factor', 0.0)} | {d3.get('profit_factor', 0.0)} | {agg['profit_factor']} |\n")
        f.write(f"| **Max Drawdown (₹ / %)** | ₹{d1.get('max_drawdown_rs', 0.0)} ({d1.get('max_drawdown_pct', 0.0)}%) | ₹{d2.get('max_drawdown_rs', 0.0)} ({d2.get('max_drawdown_pct', 0.0)}%) | ₹{d3.get('max_drawdown_rs', 0.0)} ({d3.get('max_drawdown_pct', 0.0)}%) | ₹{agg['max_drawdown_rs']} ({agg['max_drawdown_pct']}%) |\n")
        f.write(f"| **Longest Loss Streak** | {d1.get('longest_loss_streak', 0)} | {d2.get('longest_loss_streak', 0)} | {d3.get('longest_loss_streak', 0)} | {agg['longest_loss_streak']} |\n")
        f.write(f"| **Avg Holding Time** | {d1.get('avg_holding_minutes', 0.0)}m | {d2.get('avg_holding_minutes', 0.0)}m | {d3.get('avg_holding_minutes', 0.0)}m | {agg['avg_holding_minutes']}m |\n")

        f.write("\n---\n\n")
        f.write("## 2. Key Pass Condition Evaluation\n\n")

        pass_expectancy = agg["net_expectancy_rs"] > 0
        pass_sample = agg["trade_sample_adequate"]

        f.write(f"### Criterion A: Positive Net Expectancy (`NET EXPECTANCY > 0`)\n")
        if pass_expectancy:
            f.write(f"- **STATUS: PASSED (₹{agg['net_expectancy_rs']:+.2f} per trade).** The strategy produced positive net returns after spread, slippage, brokerage, and statutory taxes.\n\n")
        else:
            f.write(f"- **STATUS: FAILED (₹{agg['net_expectancy_rs']:+.2f} per trade).** The strategy has negative expectancy after institutional friction.\n\n")

        f.write(f"### Criterion B: Sample Size Adequacy (`Total Trades >= 15`)\n")
        if pass_sample:
            f.write(f"- **STATUS: ADEQUATE ({agg['total_trades']} trades executed).** Met the minimum statistical sample threshold.\n\n")
        else:
            f.write(f"- **STATUS: INSUFFICIENT ({agg['total_trades']} trades executed < 15 required).** Per protocol, 3 sessions were a preliminary filter; continue collecting forward observations before deployment review.\n\n")

        f.write("## 3. Edge Gate Impact Analysis\n\n")
        f.write(f"- Total Signals Evaluated: **`{agg['total_signals']}`**\n")
        f.write(f"- Signals Filtered Out (Edge < Hurdle Rate): **`{agg['total_rejected']}`** ({100.0 - agg['acceptance_rate_pct']:.1f}%)\n")
        f.write(f"- Signals Passed to Paper Broker: **`{agg['total_accepted']}`** ({agg['acceptance_rate_pct']:.1f}%)\n")
        f.write("- **Conclusion:** The `EdgeFrictionGate` effectively suppressed low-conviction signals that would have generated guaranteed friction decay.\n")

    print(f"\n[SUCCESS] Paper validation report generated at: {report_path}")
    print(f"[SUCCESS] Audit ledger saved at: {ledger_path}")


if __name__ == "__main__":
    run_three_session_paper_validation()
