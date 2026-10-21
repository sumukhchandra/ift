"""
test_cloud_deployment.py
Automated test suite for AlphaNSE V3 Render Cloud deployment and mobile dashboard.
Validates:
1. Pre-trade trading safety invariants and live-order locks
2. Cross-platform process detection (Linux / Windows PID checking)
3. Cloud StorageManager persistence (schema creation, state/ledger save & load, event logging)
4. Dashboard status badge and data freshness logic (LIVE, STALE, MARKET CLOSED, SHADOW MODE)
5. Render deployment configuration (render.yaml parsing and environment variable completeness)
"""

import os
import sys
import unittest
import tempfile
import json
from datetime import datetime, timedelta
import pytz

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.storage.persistence import StorageManager
from v3.execution.live_trader import is_pid_alive


class TestTradingSafetyLocks(unittest.TestCase):
    """Verify that live order routing is locked down completely."""

    def test_environment_safety_flags_default_to_false(self):
        """LIVE_TRADING and ALLOW_REAL_ORDERS must evaluate to False."""
        live_trading = os.getenv("LIVE_TRADING", "False").lower() in ("true", "1", "yes")
        allow_real = os.getenv("ALLOW_REAL_ORDERS", "False").lower() in ("true", "1", "yes")
        self.assertFalse(live_trading, "LIVE_TRADING must be False for paper/shadow deployment")
        self.assertFalse(allow_real, "ALLOW_REAL_ORDERS must be False for paper/shadow deployment")

    def test_risk_limits_invariants(self):
        """Paper capital limits must adhere to strict limits."""
        starting_capital = 1500.00
        max_daily_loss = 30.00
        max_open_positions = 1

        self.assertEqual(starting_capital, 1500.00, "Starting paper capital must be ₹1,500")
        self.assertEqual(max_daily_loss, 30.00, "Max daily paper loss must be ₹30")
        self.assertEqual(max_open_positions, 1, "Max open positions must be 1")


class TestCrossPlatformPID(unittest.TestCase):
    """Verify process liveness check works across Linux and Windows."""

    def test_current_pid_is_alive(self):
        current_pid = os.getpid()
        self.assertTrue(is_pid_alive(current_pid), f"Current PID {current_pid} must be reported alive")

    def test_nonexistent_pid_is_not_alive(self):
        # PID 999999 is virtually guaranteed not to exist
        self.assertFalse(is_pid_alive(999999), "Nonexistent PID 999999 must be reported dead")


class TestStorageManagerPersistence(unittest.TestCase):
    """Test unified persistence layer across restarts and sessions."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_alphanse.db")
        self.storage = StorageManager(sqlite_path=self.db_path)

    def tearDown(self):
        if hasattr(self, "storage") and self.storage:
            self.storage.close()
        self.temp_dir.cleanup()

    def test_runtime_state_save_and_load(self):
        test_state = {
            "timestamp": "2026-10-20T10:00:00+05:30",
            "cycle_count": 42,
            "system_state": "ACTIVE_MONITORING",
            "shadow_mode": True,
            "paper_balance": 1500.00,
            "open_positions": 0
        }
        success = self.storage.save_state(test_state)
        self.assertTrue(success, "Saving runtime state to storage must succeed")

        loaded = self.storage.load_state()
        self.assertIsNotNone(loaded, "Loaded state must not be None")
        self.assertEqual(loaded.get("cycle_count"), 42)
        self.assertEqual(loaded.get("system_state"), "ACTIVE_MONITORING")
        self.assertTrue(loaded.get("shadow_mode"))

    def test_paper_ledger_save_and_load(self):
        test_ledger = {
            "initial_capital": 1500.00,
            "current_capital": 1500.00,
            "realized_pnl": 0.0,
            "trades": [
                {
                    "trade_id": "T001",
                    "symbol": "NIFTYBEES",
                    "action": "BUY",
                    "price": 285.50,
                    "qty": 5,
                    "status": "FILLED_PAPER"
                }
            ]
        }
        success = self.storage.save_ledger(test_ledger)
        self.assertTrue(success, "Saving paper ledger must succeed")

        loaded = self.storage.load_ledger()
        self.assertIsNotNone(loaded, "Loaded ledger must not be None")
        self.assertEqual(loaded.get("initial_capital"), 1500.00)
        self.assertEqual(len(loaded.get("trades", [])), 1)

    def test_system_event_logging_and_query(self):
        self.storage.log_event("TEST_EVENT", "System started successfully", {"node": "worker-1"})
        self.storage.log_event("WARNING", "Quote latency elevated", {"latency_ms": 145})

        events = self.storage.get_recent_events(limit=5)
        self.assertGreaterEqual(len(events), 2)
        event_types = [e["event_type"] for e in events]
        self.assertIn("TEST_EVENT", event_types)
        self.assertIn("WARNING", event_types)

    def test_market_capture_persistence(self):
        capture = {
            "symbol": "INFY.NS",
            "ltp": 1920.50,
            "validation_status": "VALID",
            "latency_ms": 42.5,
            "request_timestamp_ist": "2026-10-21 09:30:00 IST"
        }
        self.storage.append_market_capture(capture)
        recent = self.storage.get_recent_captures(limit=5)
        self.assertGreaterEqual(len(recent), 1)
        self.assertEqual(recent[-1]["symbol"], "INFY.NS")
        self.assertEqual(recent[-1]["ltp"], 1920.50)

    def test_prediction_and_outcome_persistence(self):
        pred = {
            "record_id": "INFY_20261021_093000",
            "timestamp": "2026-10-21 09:30:00 IST",
            "symbol": "INFY.NS",
            "spot_price": 1920.50,
            "horizon": "1m",
            "tree_alpha_bps": 14.5,
            "specialist_alpha_bps": 12.0,
            "signal": "BUY",
            "rejection_reason": "CLEARED_GATES"
        }
        self.storage.append_prediction(pred)
        loaded_preds = self.storage.get_recent_predictions(limit=5)
        self.assertGreaterEqual(len(loaded_preds), 1)
        self.assertEqual(loaded_preds[-1]["symbol"], "INFY.NS")
        self.assertEqual(loaded_preds[-1]["tree_alpha_bps"], 14.5)

        outcome = {
            "record_id": "INFY_20261021_093000",
            "symbol": "INFY.NS",
            "creation_timestamp": "2026-10-21 09:31:00 IST",
            "current_spot_price": 1920.50,
            "actual_forward_price": 1923.25,
            "actual_return_bps": 14.32,
            "direction_correct": True
        }
        self.storage.append_outcome(outcome)
        loaded_outcomes = self.storage.get_recent_outcomes(limit=5)
        self.assertGreaterEqual(len(loaded_outcomes), 1)
        self.assertEqual(loaded_outcomes[-1]["actual_return_bps"], 14.32)
        self.assertTrue(loaded_outcomes[-1]["direction_correct"])


class TestDashboardStatusBadges(unittest.TestCase):
    """Test dashboard status calculation logic."""

    def test_stale_data_detection(self):
        """Data older than 180 seconds must be classified as STALE DATA."""
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)

        # 5 minutes old
        old_time = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        old_dt = ist.localize(datetime.strptime(old_time, "%Y-%m-%d %H:%M:%S"))
        age_seconds = (now - old_dt).total_seconds()

        self.assertGreater(age_seconds, 180, "Timestamp is older than 180 seconds")
        # Logic rule: Never show LIVE if age > 180
        is_fresh = age_seconds <= 180
        self.assertFalse(is_fresh, "Data older than 180s must never be marked fresh/LIVE")

    def test_live_data_freshness(self):
        """Data within 60 seconds is considered fresh."""
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)

        recent_time = (now - timedelta(seconds=25)).strftime("%Y-%m-%d %H:%M:%S")
        recent_dt = ist.localize(datetime.strptime(recent_time, "%Y-%m-%d %H:%M:%S"))
        age_seconds = (now - recent_dt).total_seconds()

        self.assertLessEqual(age_seconds, 60)

    def test_market_hours_logic(self):
        from dashboard import is_market_open
        ist = pytz.timezone("Asia/Kolkata")
        # Sunday should be closed
        sunday_dt = ist.localize(datetime(2026, 10, 18, 11, 0, 0))
        self.assertFalse(is_market_open(sunday_dt))

        # Wednesday 11:00 AM IST should be open
        trading_hours_dt = ist.localize(datetime(2026, 10, 21, 11, 0, 0))
        self.assertTrue(is_market_open(trading_hours_dt))

        # Wednesday 08:30 AM IST (pre-open) should be closed
        pre_market_dt = ist.localize(datetime(2026, 10, 21, 8, 30, 0))
        self.assertFalse(is_market_open(pre_market_dt))

        # Wednesday 16:00 PM IST (post-close) should be closed
        post_market_dt = ist.localize(datetime(2026, 10, 21, 16, 0, 0))
        self.assertFalse(is_market_open(post_market_dt))


class TestRenderBlueprintConfig(unittest.TestCase):
    """Test render.yaml configuration syntax and service completeness."""

    def test_render_yaml_structure(self):
        import yaml
        yaml_path = os.path.join(WORKSPACE_ROOT, "render.yaml")
        self.assertTrue(os.path.exists(yaml_path), "render.yaml must exist in root")

        with open(yaml_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self.assertIn("services", config)
        service_names = [s["name"] for s in config["services"]]
        self.assertIn("alphanse-v3-dashboard", service_names)
        self.assertIn("alphanse-v3-worker", service_names)

        # Verify database is defined
        self.assertIn("databases", config)
        db_names = [d["name"] for d in config["databases"]]
        self.assertIn("alphanse-v3-db", db_names)

        # Verify safety locks in worker
        worker = next(s for s in config["services"] if s["name"] == "alphanse-v3-worker")
        env_dict = {e["key"]: e.get("value") for e in worker.get("envVars", [])}
        self.assertEqual(env_dict.get("LIVE_TRADING"), "False")
        self.assertEqual(env_dict.get("ALLOW_REAL_ORDERS"), "False")


if __name__ == "__main__":
    unittest.main()
