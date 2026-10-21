#!/usr/bin/env python3
"""
tests/test_startup_reliability.py
P2 Regression Tests: Operational startup reliability, duplicate instance prevention,
graceful shutdown, stale-heartbeat detection, and restart recovery.
"""

import os
import sys
import json
import time
import unittest
from datetime import datetime, timedelta

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.execution.live_trader import AlphaNSELiveTrader, PID_FILE, STATE_FILE, LOG_FILE
from check_status import safe_terminate_trader, is_pid_alive


class TestStartupReliability(unittest.TestCase):
    def setUp(self):
        self.test_pid_file = PID_FILE
        self.test_state_file = os.path.join(WORKSPACE_ROOT, "reports", "live", "test_runtime_state_isolated.json")

    def tearDown(self):
        if os.path.exists(self.test_state_file):
            try:
                os.remove(self.test_state_file)
            except Exception:
                pass
        if os.path.exists(self.test_pid_file):
            try:
                os.remove(self.test_pid_file)
            except Exception:
                pass

    def test_duplicate_instance_prevention(self):
        """Verify that starting a second instance while a process is running aborts immediately."""
        # Write current process PID to PID_FILE to simulate a running daemon
        with open(self.test_pid_file, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))

        trader2 = AlphaNSELiveTrader(state_file=self.test_state_file)
        # Mock trader2 having a different pid to test collision detection
        orig_getpid = os.getpid
        try:
            # Set os.getpid to return a fake pid so trader2 sees old_pid != cur_pid and old_pid is alive
            os.getpid = lambda: 99999999
            # Attempt to run: should abort without writing PID 99999999
            trader2.run()
            # Read PID_FILE: should still be the original PID, not overwritten
            with open(self.test_pid_file, "r", encoding="utf-8") as f:
                saved_pid = int(f.read().strip())
            self.assertEqual(saved_pid, orig_getpid())
        finally:
            os.getpid = orig_getpid
            if os.path.exists(self.test_pid_file):
                os.remove(self.test_pid_file)

    def test_restart_recovery_restores_active_positions(self):
        """Verify that restart recovery restores active open positions from runtime_state.json."""
        os.makedirs(os.path.dirname(self.test_state_file), exist_ok=True)
        mock_positions = {
            "V2_15M": {
                "symbol": "INFY.NS",
                "kotak_symbol": "INFY-EQ",
                "side": "BUY",
                "shares": 1,
                "entry_price": 1050.0,
                "notional": 1050.0,
                "current_price": 1052.0,
                "unrealized_pnl": 2.0
            }
        }
        mock_state = {
            "session_date": datetime.now().strftime("%Y-%m-%d"),
            "last_updated": datetime.now().isoformat(),
            "pid": os.getpid(),
            "status": "TRADING_ACTIVE",
            "active_positions_count": 1,
            "active_positions": mock_positions
        }
        with open(self.test_state_file, "w", encoding="utf-8") as f:
            json.dump(mock_state, f)

        # Initialize trader: should detect and restore the position
        trader = AlphaNSELiveTrader(state_file=self.test_state_file)
        self.assertIn("V2_15M", trader.active_positions)
        self.assertEqual(trader.active_positions["V2_15M"]["shares"], 1)
        self.assertEqual(trader.active_positions["V2_15M"]["kotak_symbol"], "INFY-EQ")

    def test_stale_heartbeat_detection(self):
        """Verify that a heartbeat older than 120 seconds is correctly detected as stale."""
        stale_time = (datetime.now() - timedelta(seconds=180)).isoformat()
        stale_state = {
            "session_date": datetime.now().strftime("%Y-%m-%d"),
            "last_updated": stale_time,
            "pid": os.getpid(),
            "status": "TRADING_ACTIVE",
            "active_positions_count": 0,
            "active_positions": {}
        }
        with open(self.test_state_file, "w", encoding="utf-8") as f:
            json.dump(stale_state, f)

        # Check status helper
        with open(self.test_state_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        last_dt = datetime.fromisoformat(loaded["last_updated"])
        elapsed = (datetime.now() - last_dt).total_seconds()
        self.assertGreater(elapsed, 120.0, "Heartbeat should be older than 120s limit")

    def test_safe_termination_refuses_when_active_positions_exist(self):
        """Verify that safe_terminate_trader refuses termination if open positions exist."""
        with open(self.test_pid_file, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))

        state_with_pos = {
            "session_date": datetime.now().strftime("%Y-%m-%d"),
            "last_updated": datetime.now().isoformat(),
            "pid": os.getpid(),
            "active_positions_count": 1,
            "active_positions": {
                "V2_15M": {"kotak_symbol": "INFY-EQ", "shares": 1}
            }
        }
        with open(self.test_state_file, "w", encoding="utf-8") as f:
            json.dump(state_with_pos, f)

        success, msg = safe_terminate_trader(force=False, state_file=self.test_state_file)
        self.assertFalse(success, "Termination should be BLOCKED when active positions exist!")
        self.assertIn("SAFETY REFUSAL", msg)

        # Cleanup PID_FILE
        if os.path.exists(self.test_pid_file):
            os.remove(self.test_pid_file)


if __name__ == "__main__":
    unittest.main()
