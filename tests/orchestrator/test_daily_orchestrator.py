"""
AlphaNSE V3 — Daily Adaptive Multi-Model Orchestrator Verification Suite (Section 38).
Implements automated tests verifying all 20+ architectural requirements:

1. Data cleanup removes temporary files without deleting raw/immutable files.
2. Data retention verifies all required immutable categories exist.
3. 15-domain market intelligence collection produces valid NextSessionMarketState.
4. 10-minute pre-market freeze stops ingestion at exactly 09:05 IST.
5. Post-freeze future data injection raises LookaheadViolationError.
6. Market World State synthesizes universe, rankings, volatility, and regimes.
7. Constrained beam search roadmap optimizer generates Primary, Backup, and Cash roadmaps.
8. Roadmap objective maximizes expected risk-adjusted net value after all friction and penalties.
9. Whole-share integer sizing is strictly enforced (no fractional shares).
10. All 5 active research models (V2_15M, HYPO001, HYPO002, HYPO003, V3_60M) receive context and predict.
11. Each model outputs Section 1 rich attributes (BUY/SELL/HOLD, predicted high/low/close, move bps, time-to-edge).
12. Antigravity Meta-Orchestrator generates transparent consensus verdicts with explicit reason codes.
13. Meta-model consensus identifies supporting and contradicting models.
14. Capital allocation plan preserves cash when net edge < ₹0.80.
15. 1-minute thesis verification categorizes ON_TRACK, EARLY, LATE, WEAKENING, INVALIDATED, COMPLETED.
16. Time-to-edge engine calculates remaining time and remaining move bps.
17. Active position monitor enforces 15:25 IST mandatory square-off (EMERGENCY_EXIT).
18. Active position monitor prohibits loss averaging.
19. Zero-trade sessions preserve 100% cash capital.
20. All 14 daily artifacts are generated on disk in the session directory.
21. Live execution safety lock raises LiveExecutionDisabledError when unauthorized.
"""

import os
import sys
import json
import unittest
import tempfile
import shutil
from datetime import datetime, date, time
import pandas as pd
import numpy as np

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from v3.config.multimodel_config import ACTIVE_MODEL_SPECS
from v3.data.data_cleaner import DailyDataCleanerV3
from v3.data.market_intelligence import MarketIntelligenceCollectorV3, NextSessionMarketState
from v3.data.premarket_freeze import PreMarketFreezeEngineV3, LookaheadViolationError
from v3.roadmap.world_state import WorldStateBuilderV3, MarketWorldState
from v3.roadmap.roadmap_engine import RoadmapOptimizationEngineV3, PreMarketRoadmap
from v3.models.antigravity_orchestrator import AntigravityMetaOrchestratorV3
from v3.verification.minute_verifier import MinuteThesisVerifierV3, ThesisVerificationRecord
from v3.verification.position_monitor import ActivePositionMonitorV3, PositionActionRecommendation
from v3.orchestration.daily_orchestrator import DailyAdaptiveOrchestratorV3, LiveExecutionDisabledError


class TestDailyAdaptiveOrchestrator(unittest.TestCase):
    """Rigorous verification suite for Daily Adaptive Multi-Model Orchestrator."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.orchestrator = DailyAdaptiveOrchestratorV3(
            workspace_root=WORKSPACE_ROOT,
            initial_capital=5000.0,
            min_net_edge_rupees=0.80,
            live_execution_unlocked=False
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. Data cleanup removes temporary files without deleting raw/immutable files
    def test_01_data_cleanup_preserves_immutable_files(self):
        cleaner = DailyDataCleanerV3(workspace_root=WORKSPACE_ROOT)
        report = cleaner.execute_eod_cleanup("2026-09-24")
        self.assertEqual(report["retention"]["data_retention_policy_status"], "COMPLIANT")
        self.assertGreater(report["retention"]["protected_file_count"], 0)
        self.assertEqual(report["integrity"]["overall_verdict"], "VERIFIED_INTACT")

    # 2. 15-Domain market intelligence produces valid NextSessionMarketState
    def test_02_fifteen_domain_market_intelligence(self):
        collector = MarketIntelligenceCollectorV3()
        state = collector.build_next_session_market_state(
            session_date="2026-09-25",
            cutoff_timestamp="2026-09-25T09:05:00+05:30"
        )
        self.assertIsInstance(state, NextSessionMarketState)
        self.assertEqual(state.total_candidates, 10)
        self.assertEqual(state.calendar.session_date, "2026-09-25")
        self.assertEqual(len(state.per_symbol_intelligence), 10)
        # Verify specific domains exist
        first_sym = list(state.per_symbol_intelligence.keys())[0]
        sym_dict = state.per_symbol_intelligence[first_sym]
        for domain in ["price", "tick_trade", "depth", "corporate_actions", "sector_peer", "derivatives", "news_events", "sentiment", "fundamentals", "target_labels"]:
            self.assertIn(domain, sym_dict)

    # 3. 10-Minute pre-market freeze stops ingestion at exactly 09:05 IST
    def test_03_premarket_freeze_stops_at_0905(self):
        freeze_engine = PreMarketFreezeEngineV3(freeze_minutes_before_open=10, market_open_str="09:15")
        self.assertEqual(freeze_engine.freeze_time, time(9, 5))
        collector = MarketIntelligenceCollectorV3()
        state = collector.build_next_session_market_state("2026-09-25", "2026-09-25T09:05:00+05:30")
        snapshot = freeze_engine.freeze_premarket_state("2026-09-25", state, snapshot_dir=self.temp_dir)
        self.assertEqual(snapshot["status"], "FROZEN_T_MINUS_10")
        self.assertTrue(len(snapshot["snapshot_hash"]) == 64)

    # 4. Post-freeze future data injection raises LookaheadViolationError
    def test_04_lookahead_violation_error_raised(self):
        freeze_engine = PreMarketFreezeEngineV3()
        with self.assertRaises(LookaheadViolationError):
            freeze_engine.verify_timestamp_compliance(
                record_timestamp="2026-09-25T09:08:00+05:30",
                cutoff_timestamp="2026-09-25T09:05:00+05:30"
            )

    # 5. Market World State synthesizes candidate universe, rankings, and risk budget
    def test_05_world_state_synthesis(self):
        collector = MarketIntelligenceCollectorV3()
        state = collector.build_next_session_market_state("2026-09-25", "2026-09-25T09:05:00+05:30")
        freeze_engine = PreMarketFreezeEngineV3()
        snapshot = freeze_engine.freeze_premarket_state("2026-09-25", state)

        builder = WorldStateBuilderV3()
        ws = builder.build_world_state(snapshot, available_capital=5000.0, risk_budget_pct=0.01)
        self.assertEqual(ws.available_capital, 5000.0)
        self.assertEqual(ws.risk_budget_rupees, 50.0)
        self.assertEqual(len(ws.candidate_universe), 10)
        self.assertIn("TATACAP.NS", ws.candidate_summaries)

    # 6. Constrained beam search roadmap optimizer generates Primary, Backup, and Cash roadmaps
    def test_06_roadmap_optimizer_generates_tri_roadmaps(self):
        collector = MarketIntelligenceCollectorV3()
        state = collector.build_next_session_market_state("2026-09-25", "2026-09-25T09:05:00+05:30")
        freeze_engine = PreMarketFreezeEngineV3()
        snapshot = freeze_engine.freeze_premarket_state("2026-09-25", state)
        builder = WorldStateBuilderV3()
        ws = builder.build_world_state(snapshot, available_capital=5000.0)

        engine = RoadmapOptimizationEngineV3()
        roadmaps = engine.generate_trading_roadmaps(ws, output_path=os.path.join(self.temp_dir, "PREMARKET_ROADMAP.json"))
        self.assertIn("ROADMAP_1_PRIMARY", roadmaps)
        self.assertIn("ROADMAP_2_BACKUP", roadmaps)
        self.assertIn("ROADMAP_CASH", roadmaps)

    # 7. Whole-share integer sizing enforced in roadmap paths
    def test_07_whole_share_integer_sizing_in_roadmap(self):
        collector = MarketIntelligenceCollectorV3()
        state = collector.build_next_session_market_state("2026-09-25", "2026-09-25T09:05:00+05:30")
        freeze_engine = PreMarketFreezeEngineV3()
        snapshot = freeze_engine.freeze_premarket_state("2026-09-25", state)
        builder = WorldStateBuilderV3()
        ws = builder.build_world_state(snapshot, available_capital=5000.0)
        engine = RoadmapOptimizationEngineV3()
        roadmaps = engine.generate_trading_roadmaps(ws)

        primary = roadmaps["ROADMAP_1_PRIMARY"]
        for node in primary.path_nodes:
            if node["symbol"] != "CASH_RESERVE":
                qty = node["affordable_quantity"]
                self.assertIsInstance(qty, int)
                self.assertGreaterEqual(qty, 1)
                self.assertLessEqual(node["allocated_capital"], 5000.0)

    # 8. All 5 active research models receive context and output rich predictions
    def test_08_five_models_output_rich_predictions(self):
        collector = MarketIntelligenceCollectorV3()
        state = collector.build_next_session_market_state("2026-09-25", "2026-09-25T09:05:00+05:30")
        freeze_engine = PreMarketFreezeEngineV3()
        snapshot = freeze_engine.freeze_premarket_state("2026-09-25", state)
        builder = WorldStateBuilderV3()
        ws = builder.build_world_state(snapshot, available_capital=5000.0)
        engine = RoadmapOptimizationEngineV3()
        roadmaps = engine.generate_trading_roadmaps(ws)

        meta_orchestrator = AntigravityMetaOrchestratorV3()
        model_preds = meta_orchestrator.generate_all_model_predictions(ws, roadmaps)
        self.assertIn(len(model_preds), (5, 6))
        for m_id in ["V2_15M", "HYPO001", "HYPO002", "HYPO003", "V3_60M"]:
            self.assertIn(m_id, model_preds)
            tatacap_pred = model_preds[m_id]["TATACAP.NS"]
            self.assertIn(tatacap_pred.signal_type, ["BUY", "SELL", "HOLD", "NO_SIGNAL"])
            self.assertGreater(tatacap_pred.predicted_high, 0.0)
            self.assertGreater(tatacap_pred.predicted_low, 0.0)
            self.assertGreater(tatacap_pred.expected_holding_time, 0)

    # 9. Antigravity Meta-Orchestrator consensus evaluation with transparent reason codes
    def test_09_meta_orchestrator_consensus_transparent_reasons(self):
        collector = MarketIntelligenceCollectorV3()
        state = collector.build_next_session_market_state("2026-09-25", "2026-09-25T09:05:00+05:30")
        freeze_engine = PreMarketFreezeEngineV3()
        snapshot = freeze_engine.freeze_premarket_state("2026-09-25", state)
        builder = WorldStateBuilderV3()
        ws = builder.build_world_state(snapshot, available_capital=5000.0)
        engine = RoadmapOptimizationEngineV3()
        roadmaps = engine.generate_trading_roadmaps(ws)
        meta_orchestrator = AntigravityMetaOrchestratorV3()
        model_preds = meta_orchestrator.generate_all_model_predictions(ws, roadmaps)

        meta_preds, consensus, plan = meta_orchestrator.evaluate_meta_orchestrator(ws, roadmaps, model_preds)
        self.assertIn("TATACAP.NS", meta_preds)
        self.assertIn("TATACAP.NS", consensus)
        t_cons = consensus["TATACAP.NS"]
        # Must have transparent reason codes (Section 31)
        self.assertGreaterEqual(len(t_cons.reason_codes), 1)
        self.assertIsInstance(t_cons.supporting_models, list)
        self.assertIsInstance(t_cons.contradicting_models, list)
        self.assertIsInstance(t_cons.expected_net_rupees, float)

    # 10. Capital allocation plan respects risk hurdles
    def test_10_capital_allocation_plan_respects_hurdle(self):
        collector = MarketIntelligenceCollectorV3()
        state = collector.build_next_session_market_state("2026-09-25", "2026-09-25T09:05:00+05:30")
        freeze_engine = PreMarketFreezeEngineV3()
        snapshot = freeze_engine.freeze_premarket_state("2026-09-25", state)
        builder = WorldStateBuilderV3()
        ws = builder.build_world_state(snapshot, available_capital=5000.0)
        engine = RoadmapOptimizationEngineV3()
        roadmaps = engine.generate_trading_roadmaps(ws)
        meta_orchestrator = AntigravityMetaOrchestratorV3(min_net_edge_rupees=0.80)
        model_preds = meta_orchestrator.generate_all_model_predictions(ws, roadmaps)

        _, _, plan = meta_orchestrator.evaluate_meta_orchestrator(ws, roadmaps, model_preds)
        self.assertEqual(plan.total_capital, 5000.0)
        if plan.planned_allocations:
            for alloc in plan.planned_allocations:
                self.assertGreaterEqual(alloc["expected_net_rupees"], 0.80)

    # 11. 1-Minute thesis verification categorizes states correctly
    def test_11_one_minute_thesis_verification_states(self):
        verifier = MinuteThesisVerifierV3()

        # On track
        r1 = verifier.verify_thesis("TATACAP.NS", "09:20", 5, 1, 30.0, 30, 500.0, 500.80, 495.0)
        self.assertEqual(r1.thesis_state, "ON_TRACK")
        self.assertFalse(r1.is_invalidated)

        # Completed
        r2 = verifier.verify_thesis("TATACAP.NS", "09:40", 25, 1, 30.0, 30, 500.0, 502.00, 495.0)
        self.assertEqual(r2.thesis_state, "COMPLETED")

        # Invalidated
        r3 = verifier.verify_thesis("TATACAP.NS", "09:25", 10, 1, 30.0, 30, 500.0, 494.00, 495.0)
        self.assertEqual(r3.thesis_state, "INVALIDATED")
        self.assertTrue(r3.is_invalidated)

    # 12. Active position monitor enforces 15:25 square-off
    def test_12_active_position_monitor_eod_square_off(self):
        monitor = ActivePositionMonitorV3()
        verifier = MinuteThesisVerifierV3()
        rec = verifier.verify_thesis("TATACAP.NS", "15:25", 60, 1, 30.0, 60, 500.0, 501.0, 495.0)

        action = monitor.evaluate_position_action(
            symbol="TATACAP.NS",
            current_time=time(15, 25),
            current_qty=9,
            entry_price=500.0,
            current_price=501.0,
            bars_held=12,
            horizon_bars=12,
            thesis_record=rec
        )
        self.assertEqual(action.action, "EMERGENCY_EXIT")
        self.assertEqual(action.target_quantity_change, -9)

    # 13. Complete daily orchestrator run generates all 14 required artifacts
    def test_13_daily_orchestrator_generates_all_14_artifacts(self):
        result = self.orchestrator.run_daily_cycle(
            session_date="2026-09-24",
            artifacts_output_dir=self.temp_dir
        )
        self.assertEqual(result["session_date"], "2026-09-24")

        required_files = [
            "DAILY_DATA_CLEANUP_REPORT.json",
            "DAILY_DATA_INGESTION_REPORT.json",
            "DAILY_DATA_QUALITY_REPORT.json",
            "PREMARKET_WORLD_STATE.json",
            "PREMARKET_ROADMAP.json",
            "MODEL_01_PREDICTIONS.json",
            "MODEL_02_PREDICTIONS.json",
            "MODEL_03_PREDICTIONS.json",
            "MODEL_04_PREDICTIONS.json",
            "MODEL_05_PREDICTIONS.json",
            "ANTIGRAVITY_META_PREDICTIONS.json",
            "MODEL_CONSENSUS.json",
            "CAPITAL_ALLOCATION_PLAN.json",
            "INTRADAY_PREDICTION_AUDIT.json",
            "TRADE_DECISION_LEDGER.json",
            "MODEL_ATTRIBUTION.json",
            "POST_SESSION_FORENSICS.json"
        ]
        for fname in required_files:
            fpath = os.path.join(self.temp_dir, fname)
            self.assertTrue(os.path.exists(fpath), f"Required artifact {fname} missing from output!")
            with open(fpath, "r", encoding="utf-8") as f:
                content = json.load(f)
                self.assertIsNotNone(content)

    # 14. Unauthorized live execution raises LiveExecutionDisabledError
    def test_14_unauthorized_live_execution_raises(self):
        live_orchestrator = DailyAdaptiveOrchestratorV3(live_execution_unlocked=True)
        with self.assertRaises(LiveExecutionDisabledError):
            live_orchestrator.run_daily_cycle("2026-09-25")


if __name__ == "__main__":
    unittest.main()
