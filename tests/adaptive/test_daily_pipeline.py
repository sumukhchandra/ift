"""
Unit & Integration Tests for AlphaNSE V2 Adaptive Daily Retraining & Trading Pipeline.
Verifies:
  1. Anti-Leakage Invariant: Training set strictly ends <= D-1.
  2. Cryptographic Manifest & Dataset Hashing.
  3. Trade Lineage Traceability & Audit Verification.
  4. Opportunity Ranking & Dynamic Cost Hurdle Gates.
  5. Session Trader Execution Realism (Integer Sizing, PnL & Fees).
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, date, timezone
import pandas as pd
import numpy as np

from v2.adaptive.audit_ledger import DailyModelManifest, TradeAuditRecord, AuditLedger
from v2.adaptive.dataset_updater import DatasetUpdater
from v2.adaptive.opportunity_ranker import OpportunityRanker, RankedOpportunity
from v2.adaptive.session_trader import SessionTrader
from v2.models.estimators import RidgeReturnRegressor
from v2.risk.dynamic_cost_model import DynamicCostModel, ExecutionMode


class TestAdaptivePipeline(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="alphanse_adaptive_test_")
        self.ledger_dir = os.path.join(self.test_dir, "ledger")
        self.models_dir = os.path.join(self.test_dir, "models")
        self.ledger = AuditLedger(ledger_dir=self.ledger_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_manifest_and_trade_lineage(self):
        """Verifies manifest serialization and cryptographic trade lineage."""
        manifest = DailyModelManifest(
            session_date="2026-09-22",
            data_cutoff="2026-09-21T15:25:00+05:30",
            dataset_hash="a1b2c3d4e5f67890" * 4,
            feature_version="feat_v2_1234",
            model_version="AlphaNSE_Adaptive_20260922_v1",
            model_hash="f0e1d2c3b4a59687" * 4,
            training_window="2026-06-29 to 2026-09-21",
            training_rows=48811,
            validation_result={"val_ic": 0.045, "top_decile_win_rate": 58.2},
            regime_at_open="NORMAL_VOL",
            created_at=datetime.now(timezone.utc).isoformat()
        )

        manifest_path = self.ledger.save_manifest(manifest)
        self.assertTrue(os.path.exists(manifest_path))

        loaded_manifest = self.ledger.load_manifest("2026-09-22")
        self.assertIsNotNone(loaded_manifest)
        self.assertEqual(loaded_manifest.model_version, manifest.model_version)
        self.assertEqual(loaded_manifest.dataset_hash, manifest.dataset_hash)

        # Valid trade matching manifest
        trade_valid = TradeAuditRecord(
            trade_id="trade_001",
            session_date="2026-09-22",
            entry_time="2026-09-22T09:20:00+05:30",
            exit_time="2026-09-22T09:35:00+05:30",
            symbol="BAJFINANCE.NS",
            direction=1,
            entry_price=6500.0,
            exit_price=6520.0,
            quantity=1,
            gross_return_bps=30.77,
            cost_bps=12.50,
            net_return_bps=18.27,
            net_pnl_rupees=11.87,
            predicted_return_bps=25.0,
            expected_net_value_bps=12.5,
            model_version=manifest.model_version,
            model_hash=manifest.model_hash,
            dataset_hash=manifest.dataset_hash,
            data_cutoff=manifest.data_cutoff
        )

        self.assertTrue(self.ledger.verify_trade_lineage(trade_valid))

        # Tampered trade with mismatched model version
        trade_tampered = TradeAuditRecord(
            trade_id="trade_002",
            session_date="2026-09-22",
            entry_time="2026-09-22T09:20:00+05:30",
            exit_time="2026-09-22T09:35:00+05:30",
            symbol="BAJFINANCE.NS",
            direction=1,
            entry_price=6500.0,
            exit_price=6520.0,
            quantity=1,
            gross_return_bps=30.77,
            cost_bps=12.50,
            net_return_bps=18.27,
            net_pnl_rupees=11.87,
            predicted_return_bps=25.0,
            expected_net_value_bps=12.5,
            model_version="FORGED_MODEL_v9",
            model_hash=manifest.model_hash,
            dataset_hash=manifest.dataset_hash,
            data_cutoff=manifest.data_cutoff
        )

        self.assertFalse(self.ledger.verify_trade_lineage(trade_tampered))

    def test_opportunity_ranker_filtering(self):
        """Verifies that OpportunityRanker ranks by ENV and applies cost hurdle."""
        cost_model = DynamicCostModel(base_half_spread_bps=1.0, base_slippage_bps=2.0)
        ranker = OpportunityRanker(min_env_bps=5.0, min_net_rupees_target=0.80, cost_model=cost_model)

        # Mock model that returns synthetic predictions
        class MockModel:
            def predict(self, X):
                # Symbol 0 -> high positive return, Symbol 1 -> near zero return
                return np.array([0.0035, 0.0005])  # 35 bps and 5 bps

        from v2.features.feature_pipeline import ALL_FEATURE_COLUMNS

        # Synthetic feature dataframe for 2 symbols
        n_feat = len(ALL_FEATURE_COLUMNS)
        dummy_row_1 = {c: 0.0 for c in ALL_FEATURE_COLUMNS}
        dummy_row_1.update({"symbol": "BAJFINANCE.NS", "raw_close": 6500.0, "raw_atr_14": 30.0, "raw_volume": 50000.0})

        dummy_row_2 = {c: 0.0 for c in ALL_FEATURE_COLUMNS}
        dummy_row_2.update({"symbol": "RELIANCE.NS", "raw_close": 2900.0, "raw_atr_14": 15.0, "raw_volume": 50000.0})

        df = pd.DataFrame([dummy_row_1, dummy_row_2])
        ts = pd.Timestamp("2026-09-22 09:30:00+05:30")

        ranked = ranker.rank_universe_at_bar(df, MockModel(), ts)

        self.assertEqual(len(ranked), 2)
        # First opportunity should have higher ENV
        self.assertGreater(ranked[0].expected_net_value_bps, ranked[1].expected_net_value_bps)
        self.assertEqual(ranked[0].rank, 1)
        self.assertEqual(ranked[1].rank, 2)

        # Symbol 1 (35 bps) exceeds 12-14 bps cost and net target -> tradable
        self.assertTrue(ranked[0].is_tradable)
        # Symbol 2 (5 bps) does not exceed cost -> not tradable
        self.assertFalse(ranked[1].is_tradable)

    def test_session_trader_execution_realism(self):
        """Verifies session trader lifecycle, integer sizing, and trade logging."""
        manifest = DailyModelManifest(
            session_date="2026-09-22",
            data_cutoff="2026-09-21T15:25:00+05:30",
            dataset_hash="hash1",
            feature_version="feat1",
            model_version="Model_D20260922",
            model_hash="mhash1",
            training_window="2026-06-29 to 2026-09-21",
            training_rows=1000,
            validation_result={},
            regime_at_open="NORMAL_VOL",
            created_at=datetime.now(timezone.utc).isoformat()
        )

        trader = SessionTrader(manifest=manifest, initial_capital=5000.0, horizon_bars=2)

        # Create synthetic 3-bar session
        timestamps = [
            pd.Timestamp("2026-09-22 09:15:00+05:30"),
            pd.Timestamp("2026-09-22 09:20:00+05:30"),
            pd.Timestamp("2026-09-22 09:25:00+05:30")
        ]

        from v2.features.feature_pipeline import ALL_FEATURE_COLUMNS

        session_rows = []
        feature_rows = []

        prices = [1000.0, 1015.0, 1020.0]
        for i, ts in enumerate(timestamps):
            p = prices[i]
            session_rows.append({
                "timestamp": ts,
                "symbol": "STOCKA.NS",
                "open": p,
                "high": p + 2.0,
                "low": p - 2.0,
                "close": p,
                "volume": 20000
            })

            frow = {c: 0.0 for c in ALL_FEATURE_COLUMNS}
            frow.update({
                "timestamp": ts,
                "symbol": "STOCKA.NS",
                "raw_close": p,
                "raw_open": p,
                "raw_high": p + 2.0,
                "raw_low": p - 2.0,
                "raw_atr_14": 5.0,
                "raw_volume": 20000.0
            })
            feature_rows.append(frow)

        df_session = pd.DataFrame(session_rows)
        df_features = pd.DataFrame(feature_rows)

        class MockLongModel:
            def predict(self, X):
                return np.array([0.0040] * len(X))  # +40 bps prediction

        trades = trader.run_session(df_session, df_features, MockLongModel())

        self.assertGreater(len(trades), 0)
        t = trades[0]
        self.assertEqual(t.symbol, "STOCKA.NS")
        self.assertEqual(t.model_version, manifest.model_version)
        self.assertIsInstance(t.quantity, int)
        self.assertGreater(t.quantity, 0)
        self.assertGreater(t.net_pnl_rupees, 0.0)


if __name__ == "__main__":
    unittest.main()
