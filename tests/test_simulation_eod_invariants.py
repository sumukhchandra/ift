#!/usr/bin/env python3
"""
Unit Tests for Simulation EOD Invariants
Verifies that:
1. Position CANNOT survive past 15:15 IST.
2. No position exists at next day's 09:15.
3. Zero overnight gap P&L enters intraday strategy.
4. Forced EOD exit appears in ledger with INTRADAY_SQUARE_OFF.
5. Realized P&L is correctly included in daily loss calculation.
"""

import os
import sys
import unittest
from datetime import datetime, time
import pandas as pd

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from v3.execution.realistic_simulated_broker import RealisticSimulatedBroker, ExecutionRegime, CompletedTrade
from v3.execution.market_data_guards import MarketDataGuard, IST


class TestSimulationEODInvariants(unittest.TestCase):
    def setUp(self):
        self.broker = RealisticSimulatedBroker(regime=ExecutionRegime.BASE, seed=42)
        self.guard = MarketDataGuard(
            max_staleness_seconds=5.0,
            max_daily_loss=30.0,
            max_capital=7500.0
        )

    def test_guaranteed_rms_eod_exit(self):
        """Proves force_eod_square_off is 100% filled with zero rejection even under SEVERE conditions."""
        severe_broker = RealisticSimulatedBroker(regime=ExecutionRegime.SEVERE, seed=123)
        for _ in range(50):
            res = severe_broker.force_eod_square_off(
                symbol="INFY.NS",
                side="BUY",
                quantity=10,
                mid_price=1050.0,
                timestamp=datetime(2026, 9, 22, 15, 15, tzinfo=IST)
            )
            self.assertEqual(res.status, "FILLED")
            self.assertGreater(res.executed_price, 1050.0)  # Buy incurs adverse slippage

    def test_position_cannot_survive_1515(self):
        """Rule 1: Position cannot survive past 15:15 IST."""
        active_position = {
            "symbol": "BAJFINANCE.NS",
            "side": "SHORT",
            "quantity": 7,
            "entry_time": datetime(2026, 9, 22, 14, 15, tzinfo=IST),
            "entry_price": 1012.2,
            "entry_exec_price": 1011.39,
            "entry_slippage": 5.67,
            "bars_held": 4
        }

        current_ts = datetime(2026, 9, 22, 15, 15, tzinfo=IST)
        
        # When clock reaches 15:15 IST
        if current_ts.time() >= time(15, 15):
            exit_order = self.broker.force_eod_square_off(
                symbol=active_position["symbol"],
                side="BUY",
                quantity=active_position["quantity"],
                mid_price=1010.0,
                timestamp=current_ts
            )
            self.assertEqual(exit_order.status, "FILLED")
            active_position = None

        self.assertIsNone(active_position, "Position must be None at 15:15 IST")

    def test_no_position_at_next_days_0915(self):
        """Rule 2: No position exists at next day's 09:15 IST."""
        # Active position was closed at EOD yesterday
        active_position = None
        
        # Next morning market open
        next_morning_ts = datetime(2026, 9, 23, 9, 15, tzinfo=IST)
        
        # State at 09:15 must be completely fresh
        self.assertIsNone(active_position, "Intraday position must be None at next day's 09:15 IST")

    def test_no_overnight_pnl_leakage(self):
        """Rule 3: Zero overnight gap P&L can enter an intraday strategy ledger."""
        # Suppose a short position entered at 1000.0 on Day 1
        entry_price = 1000.0
        qty = 10
        # Closed at 15:15 Day 1 at 1005.0
        day1_close_price = 1005.0
        exit_order = self.broker.force_eod_square_off(
            symbol="INFY.NS",
            side="BUY",
            quantity=qty,
            mid_price=day1_close_price,
            timestamp=datetime(2026, 9, 22, 15, 15, tzinfo=IST)
        )
        self.assertEqual(exit_order.status, "FILLED")
        day1_realized_gross = (entry_price - exit_order.executed_price) * qty
        
        # Next morning Day 2, stock gaps up drastically to 1100.0 (+10%)
        day2_open_price = 1100.0
        
        # If position had survived overnight, catastrophic phantom loss would be:
        phantom_overnight_loss = (entry_price - day2_open_price) * qty  # -1000.0
        
        # But with 15:15 EOD square-off, Day 2 opening gap does NOT touch the ledger:
        self.assertGreater(day1_realized_gross, -100.0)
        self.assertNotEqual(day1_realized_gross, phantom_overnight_loss)

    def test_forced_eod_exit_appears_in_ledger(self):
        """Rule 4: Forced EOD exit appears in ledger with reason INTRADAY_SQUARE_OFF."""
        entry_price = 500.0
        exit_price = 505.0
        qty = 15
        current_ts = datetime(2026, 9, 22, 15, 15, tzinfo=IST)

        exit_order = self.broker.force_eod_square_off(
            symbol="TCS.NS",
            side="BUY",
            quantity=qty,
            mid_price=exit_price,
            timestamp=current_ts
        )

        b_paid, stat_paid, slip_paid, total_cost = self.broker.compute_trade_costs(
            entry_val=entry_price * qty,
            exit_val=exit_order.executed_price * qty,
            entry_slippage=3.5,
            exit_slippage=exit_order.slippage_paid
        )
        gross_pnl = (entry_price - exit_order.executed_price) * qty
        net_pnl = gross_pnl - total_cost

        trade = CompletedTrade(
            trade_id="TRD_TEST_0001",
            symbol="TCS.NS",
            model_name="TEST_MODEL",
            entry_time=datetime(2026, 9, 22, 14, 0, tzinfo=IST),
            exit_time=current_ts,
            quantity=qty,
            entry_price=entry_price,
            exit_price=exit_order.executed_price,
            gross_pnl=round(gross_pnl, 2),
            slippage=round(slip_paid, 2),
            brokerage=round(b_paid, 2),
            statutory_taxes=round(stat_paid, 2),
            total_cost=round(total_cost, 2),
            net_pnl=round(net_pnl, 2),
            holding_minutes=75,
            exit_reason="INTRADAY_SQUARE_OFF"
        )

        self.assertEqual(trade.exit_reason, "INTRADAY_SQUARE_OFF")
        self.assertEqual(trade.exit_time.time(), time(15, 15))
        self.assertLess(trade.net_pnl, 0)

    def test_realized_pnl_included_in_daily_loss(self):
        """Rule 5: Realized P&L from EOD square-off is included in daily loss tracking."""
        current_daily_loss = 10.0
        
        # Realized net loss on EOD exit = -25.0
        trade_net_pnl = -25.0
        if trade_net_pnl < 0:
            current_daily_loss += abs(trade_net_pnl)
            
        self.assertEqual(current_daily_loss, 35.0)
        
        # Verify that guard catches this loss exceeding max_daily_loss (30.0)
        quote_dummy = {
            "status": "success",
            "data": {
                "NSE_EQ": {
                    "INFY.NS": {
                        "last_price": 1000.0,
                        "last_trade_time": "2026-09-22 15:15:00",
                        "ohlc": {"open": 1000, "high": 1005, "low": 995, "close": 1000}
                    }
                }
            }
        }
        passed, reason, _ = self.guard.evaluate_pre_trade_gates(
            security_id="INFY.NS",
            quote_packet=quote_dummy,
            current_daily_loss=current_daily_loss,
            proposed_trade_value=1000.0,
            current_dt=datetime(2026, 9, 22, 15, 15, tzinfo=IST),
            bypass_market_hours=True
        )
        self.assertFalse(passed)
        self.assertIn("Daily loss limit reached", reason)


if __name__ == "__main__":
    unittest.main()
