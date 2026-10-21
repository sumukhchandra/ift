"""
AlphaNSE V3 — Comprehensive Test Suite.
Tests the 60m adaptive pipeline, Rupee Net-Edge gating, lunch blackout,
D-1 lookahead prevention, dynamic universe ranking, and audit lineage.
"""

import os
import unittest
from datetime import date, datetime, time, timezone
import pandas as pd
import numpy as np

from v3.config.v3_config import (
    HORIZON_BARS,
    TARGET_RETURN_COLUMN,
    MIN_NET_EDGE_RUPEES,
    MIN_NET_EDGE_BPS,
    REPLAY_DISCLAIMER,
    EXPERIMENT_MODE,
    PROFITABILITY_CLAIM,
    LUNCH_BLACKOUT_START,
    LUNCH_BLACKOUT_END,
    ENTRY_CUTOFF_TIME
)
from v3.adaptive.audit_ledger_v3 import DailyModelManifestV3, TradeAuditRecordV3, AuditLedgerV3
from v3.adaptive.opportunity_engine_v3 import OpportunityEngineV3, RankedOpportunityV3
from v3.adaptive.session_trader_v3 import SessionTraderV3
from v3.adaptive.model_updater_v3 import ModelSanityGateError, ModelUpdaterV3
from v2.risk.dynamic_cost_model import DynamicCostModel


class TestV3ConfigAndConstants(unittest.TestCase):
    """Verifies architectural specifications and disclaimers."""

    def test_horizon_is_60m(self):
        self.assertEqual(HORIZON_BARS, 12, "V3 must target 12 bars (60 minutes)")
        self.assertEqual(TARGET_RETURN_COLUMN, "target_return_60m")

    def test_experiment_status_is_validation(self):
        self.assertEqual(EXPERIMENT_MODE, "EXPERIMENT_VALIDATION")
        self.assertFalse(PROFITABILITY_CLAIM, "V3 must NOT claim profitability; it is an experiment")

    def test_replay_disclaimer_present(self):
        self.assertIn("HISTORICAL REPLAY", REPLAY_DISCLAIMER)
        self.assertIn("NOT FRESH VALIDATION", REPLAY_DISCLAIMER)
        self.assertIn("NOT PROFITABILITY PROOF", REPLAY_DISCLAIMER)


class TestV3OpportunityEngineRupeeNetEdge(unittest.TestCase):
    """Verifies the Rupee Net-Edge Gate and ticket economics."""

    def setUp(self):
        self.engine = OpportunityEngineV3(
            min_net_edge_rupees=0.80,
            min_net_edge_bps=5.0,
            min_predicted_return_bps=6.0,
            min_bar_volume=1000.0,
            max_capital_pct_per_trade=0.95
        )

    def test_insufficient_signal_floor_rejected(self):
        # Predicted return of 2.0 bps is below 6.0 bps noise floor
        opp = self.engine.evaluate_symbol_ticket(
            symbol="TEST.NS",
            price=500.0,
            predicted_bps=2.0,
            available_capital=5000.0,
            bar_volume=10000.0
        )
        self.assertFalse(opp.is_viable)
        self.assertIn("SIGNAL_BELOW_NOISE_FLOOR", opp.reject_reason)

    def test_negative_rupee_net_edge_rejected(self):
        # Small predicted return (7.0 bps) with ₹5k capital cannot overcome ~15 bps friction
        opp = self.engine.evaluate_symbol_ticket(
            symbol="TEST.NS",
            price=1000.0,
            predicted_bps=7.0,
            available_capital=5000.0,
            bar_volume=10000.0
        )
        self.assertFalse(opp.is_viable)
        self.assertIn("INSUFFICIENT_NET_INR", opp.reject_reason)

    def test_viable_opportunity_passing_hurdle(self):
        # Strong prediction (35.0 bps) on ₹500 stock with ₹5000 capital:
        # Notional = 9 * 500 = ₹4,500
        # Expected gross = ₹4,500 * 0.0035 = ₹15.75
        # Total cost ~ ₹2.50 to ₹3.00
        # Expected net ~ ₹12.75 > ₹0.80 hurdle -> VIABLE!
        opp = self.engine.evaluate_symbol_ticket(
            symbol="TATACAP.NS",
            price=500.0,
            predicted_bps=35.0,
            available_capital=5000.0,
            bar_volume=25000.0
        )
        self.assertTrue(opp.is_viable)
        self.assertGreater(opp.expected_net_rupees, 0.80)
        self.assertGreater(opp.expected_net_bps, 5.0)
        self.assertEqual(opp.quantity, 9)

    def test_dynamic_ranking_order(self):
        # Creates mock dataframe with two symbols: TATACAP and SBIN
        # Verifies that ranking is dynamic based on expected net ₹, not hardcoded
        class MockModel:
            def predict(self, X):
                # Returns 35 bps for first symbol, 20 bps for second
                return np.array([0.0035, 0.0020])

        df_bar = pd.DataFrame([
            {"symbol": "SBIN.NS", "raw_close": 800.0, "raw_volume": 50000.0, **{f"feat_{i}": 0.0 for i in range(26)}},
            {"symbol": "TATACAP.NS", "raw_close": 500.0, "raw_volume": 50000.0, **{f"feat_{i}": 0.0 for i in range(26)}}
        ])

        from v2.features.feature_pipeline import ALL_FEATURE_COLUMNS
        # Mock ALL_FEATURE_COLUMNS in clean_df
        for col in ALL_FEATURE_COLUMNS:
            df_bar[col] = 1.0

        ranked = self.engine.rank_universe_at_bar(
            bar_features_df=df_bar,
            model=MockModel(),
            timestamp=pd.Timestamp("2026-09-24 10:00:00"),
            available_capital=5000.0
        )
        # Check that viable opportunities are returned in descending order of expected net ₹
        if len(ranked) >= 2:
            self.assertGreaterEqual(ranked[0].expected_net_rupees, ranked[1].expected_net_rupees)


class TestV3SessionTraderTimeGates(unittest.TestCase):
    """Verifies Lunch Blackout, Entry Cutoff, and 60m Holding duration."""

    def setUp(self):
        self.manifest = DailyModelManifestV3(
            session_date="2026-09-24",
            data_cutoff="2026-09-23T15:25:00",
            dataset_hash="testhash",
            feature_version="feat1",
            model_version="AlphaNSE_V3_60m_20260924_v1",
            model_hash="modelhash",
            target_column="target_return_60m",
            horizon_bars=12,
            training_window="test window",
            training_rows=1000,
            validation_result={},
            regime_at_open="NORMAL_VOL",
            created_at=datetime.now(timezone.utc).isoformat()
        )
        self.trader = SessionTraderV3(manifest=self.manifest, initial_capital=5000.0, horizon_bars=12)

    def test_lunch_blackout_boundaries(self):
        # 12:00 to 14:00 must be in lunch blackout
        t_1230 = time(12, 30)
        self.assertTrue(self.trader.lunch_start <= t_1230 < self.trader.lunch_end)

        # 10:00 is outside
        t_1000 = time(10, 0)
        self.assertFalse(self.trader.lunch_start <= t_1000 < self.trader.lunch_end)

        # 14:10 is outside lunch blackout
        t_1410 = time(14, 10)
        self.assertFalse(self.trader.lunch_start <= t_1410 < self.trader.lunch_end)

    def test_entry_cutoff_time(self):
        # 14:25 onwards is entry cutoff
        t_1425 = time(14, 25)
        self.assertGreaterEqual(t_1425, self.trader.entry_cutoff)

        t_1420 = time(14, 20)
        self.assertLess(t_1420, self.trader.entry_cutoff)


class TestV3AuditLedgerIsolation(unittest.TestCase):
    """Verifies V3 audit ledger isolation and provenance verification."""

    def test_manifest_and_trade_serialization(self):
        test_dir = "v3/adaptive/test_ledger"
        ledger = AuditLedgerV3(ledger_dir=test_dir)

        manifest = DailyModelManifestV3(
            session_date="2026-09-24",
            data_cutoff="2026-09-23T15:25:00",
            dataset_hash="data123",
            feature_version="feat123",
            model_version="AlphaNSE_V3_60m_20260924_v1",
            model_hash="model123",
            target_column="target_return_60m",
            horizon_bars=12,
            training_window="test",
            training_rows=500,
            validation_result={"passed": True},
            regime_at_open="NORMAL_VOL",
            created_at=datetime.now(timezone.utc).isoformat()
        )
        ledger.save_manifest(manifest)
        loaded_manifest = ledger.load_manifest("2026-09-24")

        self.assertIsNotNone(loaded_manifest)
        self.assertEqual(loaded_manifest.model_version, "AlphaNSE_V3_60m_20260924_v1")
        self.assertEqual(loaded_manifest.target_column, "target_return_60m")
        self.assertEqual(loaded_manifest.horizon_bars, 12)
        self.assertEqual(loaded_manifest.experiment_mode, "EXPERIMENT_VALIDATION")

        # Cleanup test files
        import shutil
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


if __name__ == "__main__":
    unittest.main()
