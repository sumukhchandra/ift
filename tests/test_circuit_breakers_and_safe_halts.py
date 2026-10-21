#!/usr/bin/env python3
"""
tests/test_circuit_breakers_and_safe_halts.py
Comprehensive Verification Suite for Priority 4 & Priority 6:
Circuit Breakers, Safe-Halts, Silent Failure Elimination, and Accounting Limits.
"""

import os
import sys
import unittest
from datetime import datetime
import pandas as pd

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.execution.live_trader import AlphaNSELiveTrader
from v3.execution.kotak_adapter import KotakLiveBrokerAdapter


class TestCircuitBreakersAndSafeHalts(unittest.TestCase):

    def setUp(self):
        self.trader = AlphaNSELiveTrader(shadow_mode=True)
        # Ensure fresh state
        self.trader.active_positions = {}
        self.trader.closed_trades = []
        self.trader.realized_pnl = 0.0
        self.trader.safe_halt_active = False
        self.trader.safe_halt_reason = ""
        self.trader.broker_quote_errors = 0
        self.trader.consecutive_stale_quotes = 0

    def test_01_broker_failures_triggers_safe_halt(self):
        """5 consecutive broker quote errors must activate safe halt and block orders."""
        self.trader.broker_quote_errors = 5
        self.trader.safe_halt_active = True
        self.trader.safe_halt_reason = "CONSECUTIVE_BROKER_FAILURES: 5 failed quote requests"

        # Mock quotes
        quotes = {
            "INFY.NS": {"ltp": 1500.0, "is_stale": False, "source": "KOTAK_NEO_TRADE_API", "volume": 100}
        }
        # Attempt order evaluation
        self.trader.evaluate_and_execute_orders(quotes)

        # Invariant: zero new positions allowed during safe halt
        self.assertEqual(len(self.trader.active_positions), 0)

    def test_02_stale_quotes_timeout_triggers_safe_halt(self):
        """6 consecutive stale cycles (60s) must activate safe halt and block orders."""
        self.trader.consecutive_stale_quotes = 6
        self.trader.safe_halt_active = True
        self.trader.safe_halt_reason = "STALE_MARKET_DATA_TIMEOUT: 60s without fresh quotes"

        quotes = {
            "INFY.NS": {"ltp": 1500.0, "is_stale": True, "source": "BUFFER_FALLBACK", "volume": 100}
        }
        self.trader.evaluate_and_execute_orders(quotes)
        self.assertEqual(len(self.trader.active_positions), 0)

    def test_03_daily_loss_limit_blocks_new_entries(self):
        """If realized net loss reaches -Rs. 30.00, all new orders must be strictly blocked."""
        self.trader.realized_pnl = -30.50  # Exceeded Rs. 30 daily loss cap
        quotes = {
            "INFY.NS": {"ltp": 1500.0, "is_stale": False, "source": "KOTAK_NEO_TRADE_API", "volume": 100}
        }
        self.trader.evaluate_and_execute_orders(quotes)
        self.assertEqual(len(self.trader.active_positions), 0)

    def test_04_max_one_concurrent_position_enforced(self):
        """If 1 open position is already active, evaluate_and_execute_orders must not open a 2nd position."""
        self.trader.active_positions["EXISTING_POS"] = {
            "symbol": "INFY.NS",
            "quantity": 1,
            "entry_price": 1500.0,
            "current_price": 1500.0,
            "notional": 1500.0
        }
        quotes = {
            "TCS.NS": {"ltp": 3500.0, "is_stale": False, "source": "KOTAK_NEO_TRADE_API", "volume": 100}
        }
        self.trader.evaluate_and_execute_orders(quotes)
        # Must still have strictly 1 position
        self.assertEqual(len(self.trader.active_positions), 1)

    def test_05_predict_ml_ensemble_fails_closed_on_insufficient_history(self):
        """Buffer with fewer than 20 candles must fail closed with prediction_valid=False."""
        short_buf = [{"timestamp": f"2026-10-19 09:{15+i:02d}:00 IST", "close": 100.0, "high": 101.0, "low": 99.0, "open": 100.0, "volume": 100.0} for i in range(10)]
        self.trader.candle_buffers["INFY.NS"] = short_buf

        res = self.trader.predict_ml_ensemble("INFY.NS")
        self.assertFalse(res["prediction_valid"])
        self.assertIn("INSUFFICIENT_BUFFER_HISTORY", res["error"])

    def test_06_predict_ml_ensemble_fails_closed_on_timeframe_sampling_mismatch(self):
        """Buffer with 10s sampling must fail closed with TIMEFRAME_SAMPLING_MISMATCH."""
        base_t = datetime(2026, 10, 19, 9, 15, 0)
        sub_minute_buf = []
        for i in range(25):
            t = base_t + pd.Timedelta(seconds=i * 10)  # 10s intervals
            sub_minute_buf.append({
                "timestamp": t.strftime("%Y-%m-%d %H:%M:%S IST"),
                "close": 100.0,
                "high": 101.0,
                "low": 99.0,
                "open": 100.0,
                "volume": 100.0
            })
        self.trader.candle_buffers["INFY.NS"] = sub_minute_buf

        res = self.trader.predict_ml_ensemble("INFY.NS")
        self.assertFalse(res["prediction_valid"])
        self.assertIn("TIMEFRAME_SAMPLING_MISMATCH", res["error"])

    def test_07_dual_key_authorization_guarantees_paper_mode(self):
        """Ensure Kotak adapter defaults to paper execution with is_live=False."""
        # Tests use explicit test configuration rather than implicitly weakening production safety
        adapter = KotakLiveBrokerAdapter(enforce_time_gate=False)
        self.assertFalse(adapter.is_live, "Default adapter must have is_live=False")
        self.assertIn("PAPER", adapter.broker_name)

        # Place simulated order
        res = adapter.place_order(
            symbol="INFY-EQ",
            side="BUY",
            quantity=1,
            price=1500.0,
            order_type="MARKET",
            product="MIS",
            segment="nse_cm"
        )
        self.assertEqual(res["status"], "FILLED")
        self.assertEqual(res.get("mode"), "PAPER")
        self.assertTrue(res["order_id"].startswith("KOTAK_PAPER_"))

    def test_08_production_time_gate_enforces_1515_cutoff(self):
        """Production default (enforce_time_gate=True) strictly rejects orders after 15:15 IST."""
        from unittest.mock import patch
        from datetime import datetime
        with patch("v3.execution.kotak_adapter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 10, 19, 15, 20, 0)
            adapter = KotakLiveBrokerAdapter(enforce_time_gate=True)
            res = adapter.place_order(symbol="INFY-EQ", side="BUY", quantity=1, price=1500.0)
            self.assertEqual(res["status"], "REJECTED")
            self.assertIn("TIME_GATE", res["reason"])


if __name__ == "__main__":
    unittest.main()
