#!/usr/bin/env python3
"""
tests/test_live_trader_logging.py
P1 Regression Tests: Verify logging architecture, import safety, and production runner log output.
"""

import os
import sys
import json
import subprocess
import unittest

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

LOG_FILE = os.path.join(WORKSPACE_ROOT, "logs", "live_trader.log")


class TestLiveTraderLogging(unittest.TestCase):
    def test_import_does_not_redirect_stdout(self):
        """Verify that importing live_trader does not hijack sys.stdout."""
        orig_stdout = sys.stdout
        import v3.execution.live_trader as lt
        self.assertIs(sys.stdout, orig_stdout, "sys.stdout was globally redirected during module import!")

    def test_production_runner_appends_logs_without_erasure(self):
        """
        Verify that invoking run_live_trader.py --test-conn appends a new log line
        and preserves pre-existing logs.
        """
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        # Write a canary line to ensure it is not erased
        canary = f"[CANARY_TEST_LINE_{os.getpid()}] Pre-existing log entry that must not be deleted.\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(canary)

        # Count lines before
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines_before = f.readlines()

        # Run production runner via subprocess
        runner_path = os.path.join(WORKSPACE_ROOT, "run_live_trader.py")
        cmd = [sys.executable, runner_path, "--test-conn"]
        res = subprocess.run(cmd, cwd=WORKSPACE_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(res.returncode, 0, f"run_live_trader.py failed: {res.stderr}")

        # Count lines after
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines_after = f.readlines()

        self.assertGreater(len(lines_after), len(lines_before), "Runner did not append new log entries to LOG_FILE!")

        # Verify canary is still present (no erasure)
        canary_found = any(canary.strip() in line for line in lines_after)
        self.assertTrue(canary_found, "Pre-existing log entries were erased by production runner!")

        # Verify structured log content contains STARTUP and CONNECTION_TEST
        new_lines = lines_after[len(lines_before):]
        new_text = "".join(new_lines)
        self.assertIn("[STARTUP]", new_text)
        self.assertIn("[CONNECTION_TEST]", new_text)

    def test_log_structured_emits_valid_json_payload(self):
        """Verify log_structured outputs parseable JSON metadata."""
        from v3.execution.live_trader import AlphaNSELiveTrader
        trader = AlphaNSELiveTrader()
        test_event = "TEST_AUDIT_EVENT"
        test_data = {"test_key": 42, "status": "OK", "model": "V3_60M"}

        lines_before = 0
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                lines_before = len(f.readlines())

        trader.log_structured(test_event, test_data, "Test structured message")

        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines_after = f.readlines()

        last_line = lines_after[-1]
        self.assertIn(f"[{test_event}]", last_line)
        self.assertIn("Test structured message", last_line)
        json_part = last_line.split("|")[-1].strip()
        parsed = json.loads(json_part)
        self.assertEqual(parsed["test_key"], 42)
        self.assertEqual(parsed["status"], "OK")


if __name__ == "__main__":
    unittest.main()
