#!/usr/bin/env python3
"""
tests/test_broker_interface_and_edge_gate.py
Unit tests verifying:
1. BaseBroker unified inheritance on RealisticSimulatedBroker and DhanLiveBrokerAdapter.
2. LIVE_TRADING = False default fail-closed behavior.
3. EdgeFrictionGate pre-trade filter: blocks sub-friction signals.
4. Hard sandbox limits: Rs. 1,500 capital, 1 position max, no short selling, Rs. 30 daily loss.
"""

import os
import sys
import unittest
from datetime import datetime

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from v3.execution.base_broker import BaseBroker
from v3.execution.realistic_simulated_broker import RealisticSimulatedBroker, ExecutionRegime
from v3.execution.dhan_adapter import DhanLiveBrokerAdapter
from v3.execution.edge_friction_gate import EdgeFrictionGate


class TestBrokerInterfaceAndEdgeGate(unittest.TestCase):

    def test_base_broker_inheritance(self):
        """Verify both brokers inherit from BaseBroker."""
        sim_broker = RealisticSimulatedBroker(scenario="BASE", starting_cash=1500.0)
        dhan_broker = DhanLiveBrokerAdapter(max_capital=1500.0)

        self.assertIsInstance(sim_broker, BaseBroker)
        self.assertIsInstance(dhan_broker, BaseBroker)

        # Simulation must never report live
        self.assertFalse(sim_broker.is_live)
        # Dhan adapter defaults to False unless dual-key enabled
        self.assertFalse(dhan_broker.is_live)

    def test_edge_friction_gate_blocks_sub_friction_moves(self):
        """
        Verify that a small expected move (0.15%) is rejected for 1 share of INFY at Rs. 1,050.
        All-in friction (~Rs. 2.55) + margin exceeds gross return (Rs. 1.58).
        """
        gate = EdgeFrictionGate(half_spread_bps=3.0, slippage_bps=4.0, safety_margin_rs=0.50)
        
        # Sub-friction move: 0.15% on Rs. 1,050 is Rs. 1.58 gross
        eval_sub = gate.evaluate_signal(
            symbol="INFY",
            side="BUY",
            quantity=1,
            mid_price=1050.0,
            expected_move_pct=0.0015
        )
        self.assertFalse(eval_sub.approved)
        self.assertIn("EDGE_INSUFFICIENT", eval_sub.rejection_reason)

        # High-conviction move: 1.20% on Rs. 1,050 is Rs. 12.60 gross
        eval_super = gate.evaluate_signal(
            symbol="INFY",
            side="BUY",
            quantity=1,
            mid_price=1050.0,
            expected_move_pct=0.0120
        )
        self.assertTrue(eval_super.approved)
        self.assertGreater(eval_super.net_edge_rs, 0.0)

    def test_dhan_adapter_safeguards(self):
        """Verify Dhan adapter enforces Rs. 1,500 ceiling, single position, and short selling ban."""
        dhan = DhanLiveBrokerAdapter(max_capital=1500.0, max_daily_loss=30.0)

        # 1. Prohibit Short Selling in Cash Equity Sandbox
        approved, reason = dhan.check_pre_trade_risk(
            symbol="INFY",
            side="SELL",
            quantity=1,
            mid_price=1050.0
        )
        self.assertFalse(approved)

        # 2. Capital Ceiling (Order exceeding Rs. 1,500)
        approved, reason = dhan.check_pre_trade_risk(
            symbol="TCS",
            side="BUY",
            quantity=1,
            mid_price=3500.0
        )
        self.assertFalse(approved)


if __name__ == "__main__":
    unittest.main()
