#!/usr/bin/env python3
"""
tests/test_exit_validation.py
P4 Regression Tests: Target-based exit simulation, next-bar execution,
conservative stop/target priority, statutory costs, timeouts, and single-position invariants.
"""

import os
import sys
import unittest
from datetime import datetime, time, timedelta
import pandas as pd
import numpy as np

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.simulation.reproduce_target_exit_simulation import TargetExitSimulator, UNIVERSE


class TestExitValidation(unittest.TestCase):
    def setUp(self):
        self.simulator = TargetExitSimulator(bankroll=1500.0)

    def _create_synthetic_test_df(
        self,
        n_bars: int = 40,
        start_time_str: str = "2026-10-14 09:15:00",
        bar_generator=None
    ) -> pd.DataFrame:
        dates = pd.date_range(start_time_str, periods=n_bars, freq="1min")
        rows = []
        base_price = 1000.0
        for i, dt in enumerate(dates):
            if bar_generator:
                o, h, l, c = bar_generator(i, base_price)
            else:
                o, h, l, c = base_price, base_price + 1.0, base_price - 1.0, base_price
            rows.append({
                "timestamp": dt,
                "symbol": "INFY",
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 50000,
                "spec_pred": 0.0010 if i == 25 else 0.0, # Trigger signal at bar 25
                "tree_pred": 0.0010 if i == 25 else 0.0,
                "breakout_prob": 0.60 if i == 25 else 0.50,
                "micro_rsi": 50.0,
                "wick_pressure": 0.0
            })
        return pd.DataFrame(rows)

    def test_next_bar_execution_no_lookahead(self):
        """Verify that a signal at bar t enters at bar t+1 open with friction, never at bar t close."""
        def bar_gen(i, base):
            # Bar 25 has signal at close=1000.0; bar 26 has open=1005.0
            if i == 25:
                return base, base + 2.0, base - 1.0, 1000.0
            elif i == 26:
                return 1005.0, 1006.0, 1004.0, 1005.0
            return base, base + 1.0, base - 1.0, base

        df = self._create_synthetic_test_df(n_bars=35, bar_generator=bar_gen)
        res = self.simulator.run_simulation_for_horizon(df, timeout_minutes=15)
        trades = res["trades"]
        self.assertEqual(len(trades), 1, "Expected exactly 1 trade to execute")
        t = trades[0]

        # Entry time must be at bar 26 (09:41), not bar 25 (09:40)
        self.assertEqual(t["entry_time"], "2026-10-14 09:41:00")
        # Entry price must be based on bar 26 open (1005.0) + friction, not bar 25 close (1000.0)
        expected_entry = round(1005.0 * (1.0 + self.simulator.entry_friction_rate), 2)
        self.assertEqual(t["entry_price"], expected_entry)

    def test_conservative_stop_priority_on_intrabar_clash(self):
        """Verify that when both stop and target are breached in the same bar, stop takes precedence."""
        def bar_gen(i, base):
            if i == 25:
                return base, base + 1.0, base - 1.0, base # Signal bar
            elif i == 26:
                return base, base + 1.0, base - 1.0, base # Entry bar
            elif i == 27:
                # Huge bar: reaches +2.0% (target is +1.0%) and -2.0% (stop is -0.3%)
                return base, base * 1.025, base * 0.975, base
            return base, base + 1.0, base - 1.0, base

        df = self._create_synthetic_test_df(n_bars=35, bar_generator=bar_gen)
        res = self.simulator.run_simulation_for_horizon(df, timeout_minutes=15)
        trades = res["trades"]
        self.assertEqual(len(trades), 1)
        t = trades[0]
        self.assertEqual(t["exit_reason"], "CONSERVATIVE_STOP_PRIORITY_CLASH")
        self.assertLess(t["net_pnl"], 0.0, "Conservative clash resolution must realize a loss, not a win!")

    def test_holding_timeout_exit(self):
        """Verify that holding timeout liquidates position at exact horizon duration."""
        # Flat prices: neither target nor stop hit
        def bar_gen(i, base):
            return base, base + 0.1, base - 0.1, base

        df = self._create_synthetic_test_df(n_bars=50, bar_generator=bar_gen)
        res15 = self.simulator.run_simulation_for_horizon(df, timeout_minutes=15)
        trades15 = res15["trades"]
        self.assertEqual(len(trades15), 1)
        self.assertEqual(trades15[0]["exit_reason"], "HOLDING_TIMEOUT_15M")
        self.assertEqual(trades15[0]["holding_mins"], 15)

    def test_eod_square_off_at_1515(self):
        """Verify that any active position is forcibly liquidated at 15:15 IST."""
        def bar_gen(i, base):
            return base, base + 0.1, base - 0.1, base

        # Start at 14:15: signal at bar 25 (14:40), entry at bar 26 (14:41), 15:15 reaches before 60m timeout
        df = self._create_synthetic_test_df(n_bars=65, start_time_str="2026-10-14 14:15:00", bar_generator=bar_gen)
        # Put signal at 14:40 (index 25)
        df.loc[25, "spec_pred"] = 0.0010
        df.loc[25, "tree_pred"] = 0.0010
        df.loc[25, "breakout_prob"] = 0.60
        # Clean subsequent signals
        df.loc[26:, "spec_pred"] = 0.0

        res = self.simulator.run_simulation_for_horizon(df, timeout_minutes=60)
        trades = res["trades"]
        self.assertEqual(len(trades), 1, "Expected 1 trade to be squared off at EOD")
        self.assertEqual(trades[0]["exit_reason"], "15:15_EOD_SQUARE_OFF")
        self.assertEqual(trades[0]["exit_time"], "2026-10-14 15:15:00")


if __name__ == "__main__":
    unittest.main()
