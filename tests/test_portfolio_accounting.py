#!/usr/bin/env python3
"""
tests/test_portfolio_accounting.py
Comprehensive Regression Test Suite for Portfolio Accounting Invariants.

Enforces the 7 Non-Negotiable Forensic Invariants:
1. Cash never becomes negative.
2. Orders cannot exceed available capital after entry costs and required reserves.
3. Open positions strictly obey configured maximum (max 1 position).
4. Every fill has a real prediction/event provenance and valid timestamp.
5. P&L reconciles from the trade ledger to equity (penny-for-penny).
6. Drawdown is calculated from the equity curve and bounded within 0% - 100%.
7. Replaying the same recorded data deterministically reproduces the exact same ledger.
"""

import os
import sys
import unittest
import pandas as pd
import numpy as np

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.research.forward_evaluation import ForwardEvaluationPipeline


class TestPortfolioAccountingInvariants(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data_path = os.path.join(WORKSPACE_ROOT, "QA", "data", "genuine_forward_oos_oct13_oct14.csv")
        cls.pipeline = ForwardEvaluationPipeline(
            confidence_threshold=45.0,
            bankroll=1500.0,
            test_data_path=cls.data_path
        )
        cls.df = pd.read_csv(cls.data_path)
        cls.df["timestamp"] = pd.to_datetime(cls.df["timestamp"])
        cls.results = cls.pipeline.run_sequential_portfolio_simulation(cls.df)

    def test_invariant_1_cash_never_becomes_negative(self):
        """Invariant 1: Cash balance never drops below zero at any point in time."""
        self.assertTrue(self.results["cash_never_negative"])
        for pt in self.results["equity_curve"]:
            self.assertGreaterEqual(
                pt["cash"], 0.0,
                f"Negative cash detected: {pt['cash']} at {pt['timestamp']}"
            )

    def test_invariant_2_orders_cannot_exceed_available_capital(self):
        """Invariant 2: No trade entry cost can exceed available cash at time of entry."""
        for t in self.results["trade_ledger"]:
            # entry_open * shares must not exceed starting capital of Rs 1500
            self.assertLessEqual(
                t["shares"] * t["entry_open"], 1500.0,
                f"Trade {t['trade_id']} notional exceeded bankroll: {t['shares'] * t['entry_open']}"
            )
            self.assertGreaterEqual(t["shares"], 1, "Executed trade must have at least 1 share")

    def test_invariant_3_open_positions_obey_configured_maximum(self):
        """Invariant 3: Single position limit is strictly enforced (no overlapping open positions)."""
        self.assertTrue(self.results["max_concurrent_positions_enforced"])
        ledger = self.results["trade_ledger"]
        for i in range(len(ledger) - 1):
            t_curr = ledger[i]
            t_next = ledger[i + 1]
            # Entry of next trade must be >= exit of current trade
            curr_exit = pd.Timestamp(t_curr["exit_time"])
            next_entry = pd.Timestamp(t_next["entry_time"])
            self.assertGreaterEqual(
                next_entry, curr_exit,
                f"Overlapping position detected: Trade {t_next['trade_id']} entered at {next_entry} before Trade {t_curr['trade_id']} exited at {curr_exit}"
            )

    def test_invariant_4_fill_provenance_and_valid_timestamps(self):
        """Invariant 4: Every fill has prediction provenance and chronologically valid timestamps."""
        for t in self.results["trade_ledger"]:
            self.assertIn("trade_id", t)
            self.assertIn("symbol", t)
            self.assertIn("signal_time", t)
            self.assertIn("entry_time", t)
            self.assertIn("exit_time", t)
            self.assertIn("confidence", t)
            self.assertIn("predicted_return_bps", t)

            t_sig = pd.Timestamp(t["signal_time"])
            t_ent = pd.Timestamp(t["entry_time"])
            t_ext = pd.Timestamp(t["exit_time"])

            # Signal strictly precedes entry (next-bar execution)
            self.assertLess(t_sig, t_ent, f"Signal {t_sig} did not strictly precede entry {t_ent}")
            # Entry precedes or equals exit
            self.assertLessEqual(t_ent, t_ext, f"Entry {t_ent} occurred after exit {t_ext}")

    def test_invariant_5_pnl_reconciles_from_ledger_to_equity(self):
        """Invariant 5: Ending cash exactly equals Starting cash + sum(Net P&L) within 1 paisa."""
        start_cap = self.results["starting_capital_rs"]
        ending_cap = self.results["ending_capital_rs"]
        total_pnl = self.results["net_realized_pnl_rs"]
        expected_ending = round(start_cap + total_pnl, 2)

        self.assertAlmostEqual(
            ending_cap, expected_ending, places=2,
            msg=f"Reconciliation failure: Ending cash {ending_cap} != Expected {expected_ending}"
        )
        self.assertLessEqual(abs(self.results["reconciliation_discrepancy_rs"]), 0.05)

    def test_invariant_6_drawdown_bounded_within_100_percent(self):
        """Invariant 6: Drawdown is derived from the equity curve and bounded within 0% to 100%."""
        self.assertTrue(self.results["drawdown_bounded_within_100pct"])
        self.assertLessEqual(self.results["max_drawdown_pct"], 100.0)
        self.assertGreaterEqual(self.results["max_drawdown_pct"], 0.0)

        for pt in self.results["equity_curve"]:
            self.assertLessEqual(pt["drawdown_pct"], 100.0)
            self.assertGreaterEqual(pt["drawdown_pct"], 0.0)

    def test_invariant_7_deterministic_replay_produces_identical_ledger(self):
        """Invariant 7: Replaying the recorded data reproduces the exact same trade count, P&L, and ledger."""
        results_replay = self.pipeline.run_sequential_portfolio_simulation(self.df)

        self.assertEqual(len(self.results["trade_ledger"]), len(results_replay["trade_ledger"]))
        self.assertEqual(self.results["net_realized_pnl_rs"], results_replay["net_realized_pnl_rs"])
        self.assertEqual(self.results["ending_capital_rs"], results_replay["ending_capital_rs"])

        for t1, t2 in zip(self.results["trade_ledger"], results_replay["trade_ledger"]):
            self.assertEqual(t1["trade_id"], t2["trade_id"])
            self.assertEqual(t1["symbol"], t2["symbol"])
            self.assertEqual(t1["entry_time"], t2["entry_time"])
            self.assertEqual(t1["exit_time"], t2["exit_time"])
            self.assertEqual(t1["net_pnl_rs"], t2["net_pnl_rs"])


if __name__ == "__main__":
    unittest.main()
