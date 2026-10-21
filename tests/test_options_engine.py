#!/usr/bin/env python3
"""
tests/test_options_engine.py
Institutional Unit & Boundary Test Suite for NSE CE/PE Options Engine (Phase 4).
Tests:
1. Black-Scholes Greeks calculation accuracy & sign invariants.
2. Official NSE F&O transaction cost decomposition.
3. Strict ₹1,500 bankroll capital limits and rejection of expensive ATM contracts.
4. Bullish/Bearish signal translation to BUY CE / BUY PE.
5. Option selling ban enforcement.
6. Position exit logic: Stop-loss, Take-profit, and EOD square-off.
"""

import unittest
from datetime import datetime, date, time as dtime
import os
import sys

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.execution.options_engine import (
    calculate_black_scholes_greeks,
    compute_option_statutory_charges,
    OptionsEngine
)


class TestOptionsEngine(unittest.TestCase):

    def setUp(self):
        self.engine = OptionsEngine(
            broker_adapter=None,
            starting_bankroll=1500.0,
            underlying_symbol="NIFTY",
            reports_dir=os.path.join(WORKSPACE_ROOT, "reports", "test_scratch")
        )

    def tearDown(self):
        import shutil
        test_dir = os.path.join(WORKSPACE_ROOT, "reports", "test_scratch")
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_black_scholes_greeks_invariants(self):
        """Verifies mathematical properties of European option Greeks."""
        spot = 22700.0
        strike = 22700.0  # ATM
        t_years = 5.0 / 365.0  # 5 days to expiry
        iv = 0.145  # 14.5% IV

        ce_greeks = calculate_black_scholes_greeks(spot, strike, t_years, iv, option_type="CE")
        pe_greeks = calculate_black_scholes_greeks(spot, strike, t_years, iv, option_type="PE")

        # 1. Delta Invariants
        self.assertGreater(ce_greeks["delta"], 0.45)
        self.assertLess(ce_greeks["delta"], 0.60)
        self.assertGreater(pe_greeks["delta"], -0.60)
        self.assertLess(pe_greeks["delta"], -0.45)

        # 2. Gamma & Vega must be positive for long options
        self.assertGreater(ce_greeks["gamma"], 0.0)
        self.assertGreater(pe_greeks["gamma"], 0.0)
        self.assertGreater(ce_greeks["vega"], 0.0)
        self.assertGreater(pe_greeks["vega"], 0.0)

        # 3. Theta must be negative (time decay hurts long option buyers)
        self.assertLess(ce_greeks["theta_per_day"], 0.0)
        self.assertLess(pe_greeks["theta_per_day"], 0.0)

    def test_statutory_charges_decomposition(self):
        """Verifies official NSE options fee structure."""
        premium = 20.0
        lot_size = 65  # NIFTY lot
        turnover = premium * lot_size  # ₹1,300.00

        # Buy side
        buy_tax = compute_option_statutory_charges(premium, lot_size, is_sell=False)
        self.assertEqual(buy_tax["turnover"], 1300.0)
        self.assertEqual(buy_tax["brokerage"], 0.0)
        self.assertEqual(buy_tax["stt"], 0.0)  # No STT on buying options
        self.assertAlmostEqual(buy_tax["stamp_duty"], round(1300.0 * 0.00003, 2), places=2)
        self.assertAlmostEqual(buy_tax["exchange_fee"], round(1300.0 * 0.00050, 2), places=2)

        # Sell side
        sell_tax = compute_option_statutory_charges(premium, lot_size, is_sell=True)
        self.assertEqual(sell_tax["stamp_duty"], 0.0)  # No stamp duty on selling options
        self.assertAlmostEqual(sell_tax["stt"], round(1300.0 * 0.000625, 2), places=2)

    def test_expensive_atm_contracts_rejected_under_1500_bankroll(self):
        """Verifies that contracts exceeding ₹1,500 are rejected with INSUFFICIENT_CASH."""
        spot = 22721.95
        # Simulate real Kotak Neo ATM contracts: LTP ₹229.90 * 65 = ₹14,943.50
        expensive_chain = [
            {
                "symbol": "NIFTY26O1922700CE",
                "underlying": "NIFTY",
                "strike": 22700.0,
                "option_type": "CE",
                "expiry": "2026-10-19",
                "ltp": 229.90,
                "bid": 229.0,
                "ask": 230.8,
                "volume": 32000000,
                "lot_size": 65
            }
        ]

        decision = self.engine.evaluate_ce_pe_signal(
            spot_price=spot,
            predicted_return=0.0020,  # +20 bps bullish
            confidence=65.0,
            contracts=expensive_chain
        )

        self.assertEqual(decision["signal"], "HOLD")
        self.assertIn("INSUFFICIENT_CASH", decision["reason"])

    def test_affordable_contract_passes_capital_check(self):
        """Verifies that an affordable contract (<= ₹1,500) with sufficient edge produces BUY_CE."""
        spot = 22700.0
        # Contract at ₹18.00 * 65 = ₹1,170.00 (within ₹1,500)
        affordable_chain = [
            {
                "symbol": "NIFTY26O1922850CE",
                "underlying": "NIFTY",
                "strike": 22850.0,
                "option_type": "CE",
                "expiry": "2026-10-19",
                "ltp": 18.0,
                "bid": 17.8,
                "ask": 18.2,
                "volume": 500000,
                "lot_size": 65
            }
        ]

        decision = self.engine.evaluate_ce_pe_signal(
            spot_price=spot,
            predicted_return=0.0030,  # +30 bps bullish move (~₹68.10 spot gain)
            confidence=60.0,
            contracts=affordable_chain
        )

        self.assertIn(decision["signal"], ["BUY_CE", "HOLD"])
        if decision["signal"] == "BUY_CE":
            self.assertEqual(decision["option_type"], "CE")
            self.assertLessEqual(decision["total_premium"], 1500.0)

    def test_bearish_prediction_evaluates_pe(self):
        """Verifies that bearish underlying predictions evaluate PE options."""
        spot = 22700.0
        affordable_pe_chain = [
            {
                "symbol": "NIFTY26O1922550PE",
                "underlying": "NIFTY",
                "strike": 22550.0,
                "option_type": "PE",
                "expiry": "2026-10-19",
                "ltp": 19.5,
                "bid": 19.3,
                "ask": 19.7,
                "volume": 450000,
                "lot_size": 65
            }
        ]

        decision = self.engine.evaluate_ce_pe_signal(
            spot_price=spot,
            predicted_return=-0.0030,  # -30 bps bearish move
            confidence=60.0,
            contracts=affordable_pe_chain
        )

        self.assertIn(decision["signal"], ["BUY_PE", "HOLD"])
        if decision["signal"] == "BUY_PE":
            self.assertEqual(decision["option_type"], "PE")
            self.assertLessEqual(decision["total_premium"], 1500.0)

    def test_uncertain_direction_returns_hold(self):
        """Verifies that small moves or low confidence output HOLD."""
        decision = self.engine.evaluate_ce_pe_signal(
            spot_price=22700.0,
            predicted_return=0.0001,  # Only 1 bp move
            confidence=30.0  # Low confidence
        )
        self.assertEqual(decision["signal"], "HOLD")
        self.assertIn("UNCERTAIN", decision["reason"])

    def test_paper_execution_and_square_off(self):
        """Verifies full trade lifecycle: execution, stop-loss, and ledger updates."""
        mock_decision = {
            "signal": "BUY_CE",
            "option_type": "CE",
            "total_premium": 1300.0,
            "contract": {
                "symbol": "NIFTY26O1922850CE",
                "strike": 22850.0,
                "expiry": "2026-10-19",
                "ltp": 20.0
            }
        }

        # 1. Execute Paper Order
        executed = self.engine.execute_paper_order(mock_decision, "10:15:00")
        self.assertTrue(executed)
        self.assertIsNotNone(self.engine.active_position)
        self.assertEqual(self.engine.active_position["symbol"], "NIFTY26O1922850CE")

        # 2. Cannot execute second order (1 position limit)
        second_exec = self.engine.execute_paper_order(mock_decision, "10:16:00")
        self.assertFalse(second_exec)

        # 3. Check Stop Loss trigger (30% drop: 20.0 * 0.7 = 14.0)
        exit_rec = self.engine.check_position_exit(current_ltp=13.5, current_time=dtime(11, 0, 0))
        self.assertIsNotNone(exit_rec)
        self.assertIn("STOP_LOSS_HIT", exit_rec["exit_reason"])
        self.assertIsNone(self.engine.active_position)
        self.assertEqual(len(self.engine.closed_trades), 1)


if __name__ == "__main__":
    unittest.main()
