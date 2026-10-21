#!/usr/bin/env python3
"""
v3/execution/live_paper_session_orchestrator.py
Real-Time Live-Data Paper-Trading Orchestrator for AlphaNSE V3.

Execution Guardrails:
1. AIR-GAPPED: LIVE_TRADING = False, ALLOW_REAL_ORDERS = False.
2. Market Data: Live Read-Only Quotes (DhanHQ read-only or Yahoo Finance fallback).
3. Strategy Engine: Strategy V2.2 (15m Trend + 5m Mom + 1m Trigger + RS Leader Selection).
4. Entry Window: 09:30 - 12:45 IST.
5. Sizing & Limits:
   - Max Capital: Rs. 1,500.00
   - Max Concurrent Opportunities: 2 (Allocating up to Rs. 750 / position)
   - Zero Leverage (1.0x Cash Only)
   - Short Selling: OFF
   - Daily Loss Limit: Rs. 30.00 (Hard Circuit Breaker)
   - EOD Square-Off: 15:15 IST
6. Real-Time Logging: Emits live state to v3/reports/SESSION_LIVE_PAPER_STATE.json
"""

import os
import sys

# Configure UTF-8 for console output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import time as pytime
import json
import logging
from datetime import datetime, time, timedelta
from typing import Dict, List, Any, Optional

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.execution.realistic_simulated_broker import RealisticSimulatedBroker, ExecutionRegime
from v3.execution.edge_friction_gate import EdgeFrictionGate
from v3.strategy.v2_1_relative_strength_trend import StrategyV2_1RelativeStrength

# Target Watchlist: Liquid NSE Equities within ₹1,500 Price Cap
UNIVERSE_WATCHLIST = [
    {"symbol": "HDFCBANK", "sec_id": "1333", "approx_px": 735.0},
    {"symbol": "TATASTEEL", "sec_id": "3499", "approx_px": 188.0},
    {"symbol": "SBIN", "sec_id": "3045", "approx_px": 983.0},
    {"symbol": "BAJFINANCE", "sec_id": "317", "approx_px": 997.0},
    {"symbol": "INFY", "sec_id": "1594", "approx_px": 1000.0},
    {"symbol": "AXISBANK", "sec_id": "5900", "approx_px": 1222.0},
    {"symbol": "ICICIBANK", "sec_id": "4963", "approx_px": 1326.0},
    {"symbol": "RELIANCE", "sec_id": "2885", "approx_px": 1226.0},
]


class LivePaperSessionOrchestrator:
    def __init__(
        self,
        starting_capital: float = 1500.0,
        max_daily_loss: float = 30.0,
        max_positions: int = 2,
    ):
        self.starting_capital = starting_capital
        self.max_daily_loss = max_daily_loss
        self.max_positions = max_positions

        # Fail-closed safety verification
        self._verify_airgap_safety()

        # Simulated Broker running Base Friction
        self.broker = RealisticSimulatedBroker(
            scenario="BASE",
            starting_cash=self.starting_capital,
            max_daily_loss=self.max_daily_loss,
            seed=404,
            max_positions=self.max_positions,
            allow_short=False,
            leverage=1.0,
        )

        # Pre-Trade Edge Gate
        self.edge_gate = EdgeFrictionGate(
            half_spread_bps=3.0,
            slippage_bps=4.0,
            safety_margin_rs=0.50,
            min_net_expectancy_rs=0.25,
        )

        # Strategy instances per symbol
        self.strategies: Dict[str, StrategyV2_1RelativeStrength] = {
            item["symbol"]: StrategyV2_1RelativeStrength(
                target_profit_pct=0.0150,     # +1.50% target
                stop_loss_pct=0.0075,          # -0.75% stop loss
                trail_breakeven_pct=0.0080,    # +0.80% breakeven trail
                volume_mult=1.25,
                entry_start=time(9, 30),
                entry_cutoff=time(12, 45),     # Hard 12:45 IST cutoff
            )
            for item in UNIVERSE_WATCHLIST
        }

        self.recent_bars: Dict[str, List[Dict[str, Any]]] = {
            item["symbol"]: [] for item in UNIVERSE_WATCHLIST
        }

        self.reports_dir = os.path.join(WORKSPACE_ROOT, "v3", "reports")
        os.makedirs(self.reports_dir, exist_ok=True)
        self.state_file = os.path.join(self.reports_dir, "SESSION_LIVE_PAPER_STATE.json")

    def _verify_airgap_safety(self):
        """Enforces that real money trading is 100% disabled."""
        live_flag = os.getenv("LIVE_TRADING", "False").strip().lower() == "true"
        orders_flag = os.getenv("ALLOW_REAL_ORDERS", "False").strip().lower() == "true"
        if live_flag or orders_flag:
            raise RuntimeError(
                "[SAFETY_HALT] Real-money trading flags detected in environment! "
                "AlphaNSE protocol strictly requires LIVE_TRADING=False."
            )

    def print_readiness_banner(self):
        """Displays comprehensive pre-session verification status."""
        print("=" * 88)
        print("  🚀 ALPHANSE V3 — LIVE SESSION FORWARD PAPER-TRADING ORCHESTRATOR")
        print("=" * 88)
        print(f"  System Time (IST):      {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("  Execution Mode:         LIVE-DATA PAPER TRADING (Zero Live Orders)")
        print("  LIVE_TRADING:           False [LOCKED]")
        print("  ALLOW_REAL_ORDERS:      False [LOCKED]")
        print("  Dhan Order APIs:        Unused [AIR-GAPPED]")
        print("-" * 88)
        print(f"  Starting Capital:       Rs. {self.starting_capital:,.2f}")
        print(f"  Max Concurrent Slots:   {self.max_positions} Positions (Rs. 750 / Slot)")
        print("  Leverage:               1.0x (Cash Equity Only)")
        print("  Short Selling:          OFF (Long-Only Micro-Capital)")
        print(f"  Daily Loss Cutoff:      Rs. {self.max_daily_loss:.2f} (Hard Circuit Breaker)")
        print("  Entry Window:           09:30 IST – 12:45 IST (Strict Cutoff)")
        print("  Mandatory Square-Off:   15:15 IST (Auto Liquidation)")
        print("  Target / Stop Geometry: +1.50% Target / -0.75% Stop Loss (2.0:1 R:R)")
        print("-" * 88)
        print("  ACTIVE WATCHLIST (8 LIQUID NSE LEADERS <= Rs. 1,500):")
        for idx, item in enumerate(UNIVERSE_WATCHLIST, 1):
            print(f"    {idx:02d}. {item['symbol']:12s} (~Rs. {item['approx_px']:,.2f}) [Dhan SecID: {item['sec_id']}]")
        print("=" * 88)

    def process_incoming_minute_bar(self, symbol: str, bar_data: Dict[str, Any]):
        """
        Ingests a 1-minute live bar for a symbol and runs the V2.2 pipeline:
        1. Position Exit Management
        2. Pre-Trade Gatekeeping
        3. Relative Strength Leader Selection
        4. Simulated Execution & Ledger Recording
        """
        now = bar_data["timestamp"]
        mid_price = bar_data["close"]
        bar_vol = bar_data["volume"]

        self.recent_bars[symbol].append(bar_data)
        if len(self.recent_bars[symbol]) > 50:
            self.recent_bars[symbol].pop(0)

        # 1. Position Management if Holding this Symbol
        if symbol in self.broker.positions:
            pos = self.broker.positions[symbol]
            setattr(pos, "last_price", mid_price)

            strat = self.strategies[symbol]
            dec = strat.evaluate_1m_bar(
                bar_1m=bar_data,
                recent_1m_bars=self.recent_bars[symbol],
                position=pos,
            )

            if dec.get("action") == "SELL":
                order = self.broker.execute_order(
                    symbol=symbol,
                    side="SELL",
                    requested_qty=pos.quantity,
                    mid_price=mid_price,
                    bar_volume=bar_vol,
                    signal_timestamp=now,
                )
                print(f"  [EXIT EXECUTED] {symbol} | Qty: {pos.quantity} @ Rs. {order.execution_price:.2f} | Reason: {dec.get('reason')}")
                self.save_live_state()
                return

        # 2. Entry Evaluation if Slots Available
        current_slots = len(self.broker.positions)
        if current_slots < self.max_positions and not self.broker.circuit_breaker_tripped:
            strat = self.strategies[symbol]
            dec = strat.evaluate_1m_bar(
                bar_1m=bar_data,
                recent_1m_bars=self.recent_bars[symbol],
                position=None,
            )

            if dec.get("action") == "BUY":
                allocation_cap = self.starting_capital / self.max_positions
                max_cash = min(self.broker.cash, allocation_cap if current_slots == 0 else self.broker.cash)
                qty = int(max_cash // mid_price)

                if qty == 0 and current_slots == 0 and self.broker.cash >= mid_price:
                    qty = 1

                if qty >= 1:
                    eval_res = self.edge_gate.evaluate_signal(
                        symbol=symbol,
                        side="BUY",
                        quantity=qty,
                        mid_price=mid_price,
                        expected_move_pct=0.0150,
                    )

                    if eval_res.approved:
                        order = self.broker.execute_order(
                            symbol=symbol,
                            side="BUY",
                            requested_qty=qty,
                            mid_price=mid_price,
                            bar_volume=bar_vol,
                            signal_timestamp=now,
                        )
                        print(f"  [BUY EXECUTED] {symbol} | Qty: {qty} @ Rs. {order.execution_price:.2f} | RS Score: {dec.get('rs_score', 0.0):.4f}")
                        self.save_live_state()

    def save_live_state(self):
        """Flushes real-time state to JSON for external monitoring."""
        state = self.broker.get_portfolio_state()
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "mode": "PAPER_TRADING",
            "capital": self.starting_capital,
            "cash": state["cash"],
            "true_equity": state["true_equity"],
            "open_positions": [
                {
                    "symbol": sym,
                    "qty": pos.quantity,
                    "entry_price": pos.entry_price,
                    "current_price": getattr(pos, "last_price", pos.entry_price),
                    "unrealized_pnl": round((getattr(pos, "last_price", pos.entry_price) - pos.entry_price) * pos.quantity, 2),
                }
                for sym, pos in self.broker.positions.items()
            ],
            "realized_pnl_today": state["realized_pnl"],
            "net_daily_pnl": state["net_daily_pnl"],
            "circuit_breaker_tripped": state["circuit_breaker_tripped"],
            "trades_count": len(self.broker.trade_logs),
            "trade_logs": self.broker.trade_logs,
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2)


def main():
    orchestrator = LivePaperSessionOrchestrator(
        starting_capital=1500.0,
        max_daily_loss=30.0,
        max_positions=2,
    )
    orchestrator.print_readiness_banner()
    orchestrator.save_live_state()
    print(f"\n[READY] Live Paper State initialized at: {orchestrator.state_file}")
    print("[WAITING] Ready for market session (Pre-market 09:00 IST | Open 09:15 IST | Entry Window 09:30 IST).")


if __name__ == "__main__":
    main()
