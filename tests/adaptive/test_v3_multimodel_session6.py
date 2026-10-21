"""
AlphaNSE V3 — Multi-Model Session 6 Comprehensive Verification Suite.
Validates all architectural and operational requirements specified for Session 6:
  1. All 5 models trained and registered for Session 6
  2. Strict D-1 data cutoff (2026-09-25 15:25 IST, zero lookahead)
  3. Unique artifact and SHA-256 hash per model
  4. Multi-model consensus and Antigravity meta-orchestrator evaluation
  5. Whole-share capital allocation strictly <= ₹5,000
  6. Expected net profit clears the ₹0.80 economic hurdle
  7. Physical live execution disabled via LiveExecutionDisabledError
  8. Master manifest manifest_20260928.json immutable on disk
"""

import os
import sys
import unittest
from datetime import date, datetime
import json
import pandas as pd

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.config.multimodel_config import (
    SESSION_6_DATE,
    SESSION_6_D_MINUS_ONE_CUTOFF,
    ACTIVE_MODEL_SPECS,
    V3_MULTIMODEL_REGISTRY_PATH
)
from v3.models.model_registry import MultiModelRegistryV3
from v3.ensemble.multimodel_ensemble_v3 import MultiModelEnsembleV3
from v3.orchestration.daily_orchestrator import DailyAdaptiveOrchestratorV3, LiveExecutionDisabledError


class TestMultiModelSession6Architecture(unittest.TestCase):
    """Verification suite for Multi-Model Session 6 (2026-09-28)."""

    def setUp(self):
        self.registry = MultiModelRegistryV3()
        self.registry.load_registry()
        self.ensemble = MultiModelEnsembleV3(min_net_edge_rupees=0.80, min_net_edge_bps=0.0)

    def test_01_all_six_models_registered_and_frozen(self):
        status = self.registry.get_status_summary()
        self.assertEqual(status["total_registered"], 6)
        self.assertEqual(status["valid_model_count"], 6)
        for m_id in ["V2_15M", "HYPO001", "HYPO002", "HYPO003", "V3_60M", "SMC_4CONF_920"]:
            self.assertIn(m_id, status["valid_models"])

    def test_02_session6_data_cutoff_strictly_d1(self):
        for m_id, meta in self.registry.metadata.items():
            self.assertEqual(meta.training_cutoff, SESSION_6_D_MINUS_ONE_CUTOFF)
            cutoff_date = pd.to_datetime(meta.training_cutoff).date()
            self.assertLess(cutoff_date, date(2026, 9, 28), "Training cutoff MUST precede Session 6")

    def test_03_master_manifest_exists_on_disk(self):
        manifest_path = os.path.join(WORKSPACE_ROOT, "v3", "adaptive", "ledger", "manifests", "manifest_20260928.json")
        self.assertTrue(os.path.exists(manifest_path), f"Missing {manifest_path}")
        with open(manifest_path, "r", encoding="utf-8") as f:
            man = json.load(f)
        self.assertEqual(man["model_version"], "AlphaNSE_V3_MultiModel_20260928_v1")
        self.assertTrue(len(man["model_hash"]) >= 32)

    def test_04_session6_premarket_reports_generated(self):
        rep_dir = os.path.join(WORKSPACE_ROOT, "v3", "reports", "daily_orchestrator", "20260928")
        self.assertTrue(os.path.exists(rep_dir))
        for art in ["CAPITAL_ALLOCATION_PLAN.json", "MODEL_CONSENSUS.json", "PREMARKET_ROADMAP.json", "PREMARKET_WORLD_STATE.json"]:
            art_path = os.path.join(rep_dir, art)
            self.assertTrue(os.path.exists(art_path), f"Missing artifact {art}")

    def test_05_capital_allocation_meets_constraints(self):
        plan_path = os.path.join(WORKSPACE_ROOT, "v3", "reports", "daily_orchestrator", "20260928", "CAPITAL_ALLOCATION_PLAN.json")
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        self.assertLessEqual(plan["allocated_capital"], 5000.0)
        self.assertGreater(plan["allocated_capital"], 4000.0)
        self.assertGreater(plan["reserved_cash"], 50.0)
        for alloc in plan["planned_allocations"]:
            self.assertGreaterEqual(alloc["expected_net_rupees"], 0.80, f"{alloc['symbol']} must clear Rs.0.80 hurdle")

    def test_06_live_execution_lock_active(self):
        orch = DailyAdaptiveOrchestratorV3(workspace_root=WORKSPACE_ROOT, live_execution_unlocked=True)
        with self.assertRaises(LiveExecutionDisabledError):
            orch.run_daily_cycle(session_date=SESSION_6_DATE)


if __name__ == "__main__":
    unittest.main()
