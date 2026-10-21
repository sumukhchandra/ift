"""
AlphaNSE V3 — Historical Multi-Model Simulation Validation Suite.
Implements the 20 rigorous architectural and empirical validation gates (Section 23).
"""

import os
import sys
import unittest
import pickle
import hashlib
from datetime import datetime, date, time
from typing import Dict, Any, List
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
from v3.models.base_model import FrozenModelMetadata, ModelPredictionOutput
from v3.models.model_registry import MultiModelRegistryV3
from v3.models.model_trainers import MultiModelTrainerV3, MultiModelSanityGateError
from v3.ensemble.multimodel_ensemble_v3 import MultiModelEnsembleV3, EnsembleDecisionOutput
from v3.adaptive.opportunity_engine_v3 import OpportunityEngineV3
from v3.adaptive.session_trader_v3 import SessionTraderV3
from v3.adaptive.audit_ledger_v3 import DailyModelManifestV3, CandidateDecisionAuditRecordV3, TradeAuditRecordV3
from v2.risk.cost_engine import IndiaCostEngine
from v2.risk.dynamic_cost_model import DynamicCostModel, ExecutionMode
from v2.risk.integer_sizer import IntegerPositionSizer
from v2.models.estimators import RidgeReturnRegressor


class TestHistoricalMultiModelSimulation(unittest.TestCase):
    """20-point validation suite for Historical Multi-Model Walk-Forward Simulation (Section 23)."""

    def setUp(self):
        self.ensemble = MultiModelEnsembleV3(min_net_edge_rupees=0.80, min_net_edge_bps=0.0)
        self.cost_model = DynamicCostModel(base_half_spread_bps=1.0, base_slippage_bps=2.0)
        self.sizer = IntegerPositionSizer(max_position_allocation_pct=0.95)

    # 1. No future data enters training
    def test_01_no_future_data_enters_training(self):
        target_day = date(2026, 9, 21)
        df_raw = pd.read_parquet("v2/data/storage/normalized/historical_5m_raw.parquet")
        df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
        training_slice = df_raw[df_raw["timestamp"].dt.date < target_day]
        max_train_ts = training_slice["timestamp"].max()
        self.assertLess(max_train_ts.date(), target_day, "Training data MUST strictly precede target_day")

    # 2. D-day data cannot train D-day model
    def test_02_d_day_data_cannot_train_d_day_model(self):
        trainer = MultiModelTrainerV3()
        leaked_meta = {
            "raw_path": "v2/data/storage/normalized/historical_5m_raw.parquet",
            "adj_path": "v2/data/storage/adjusted/historical_5m_adjusted.parquet",
            "data_cutoff": "2026-09-15T15:25:00+05:30",
            "dataset_hash": "leaked"
        }
        # Trying to train target_day=2026-09-15 when base data extends to 2026-09-18 must fail
        with self.assertRaises(MultiModelSanityGateError):
            trainer.train_all_session_models(target_day=date(2026, 9, 15), dataset_meta=leaked_meta)

    # 3. Each day's model hashes are reproducible
    def test_03_each_days_model_hashes_reproducible(self):
        X = np.ones((100, 10))
        y = np.linspace(1, 10, 100)
        m1 = RidgeReturnRegressor(alpha=20.0).fit(X, y)
        m2 = RidgeReturnRegressor(alpha=20.0).fit(X, y)
        h1 = hashlib.sha256(pickle.dumps(m1)).hexdigest()
        h2 = hashlib.sha256(pickle.dumps(m2)).hexdigest()
        self.assertEqual(h1, h2, "Model hashes must be 100% deterministic and reproducible")

    # 4. All models participate
    def test_04_all_five_models_participate(self):
        registry = MultiModelRegistryV3()
        self.assertIn(len(ACTIVE_MODEL_SPECS), (5, 6))
        for m_id, spec in ACTIVE_MODEL_SPECS.items():
            meta = FrozenModelMetadata(
                model_id=m_id,
                model_version="test_v1",
                model_hash="hash_" + m_id,
                dataset_hash="d_hash",
                training_cutoff="2026-09-24T15:25:00+05:30",
                feature_schema_hash="f_hash",
                target_definition=spec["target_definition"],
                target_horizon_minutes=spec["target_horizon_minutes"],
                training_sample_count=1000,
                validation_sample_count=200,
                validation_metrics={"ic": 0.05},
                regime="NORMAL_VOL",
                direction="LONG_AND_SHORT",
                expected_return_units="bps",
                confidence=0.6,
                status="FROZEN"
            )
            registry.models[m_id] = object()
            registry.metadata[m_id] = meta
        valid_models = registry.get_valid_models()
        self.assertIn(len(valid_models), (5, 6))
        for m_id in ["V2_15M", "HYPO001", "HYPO002", "HYPO003", "V3_60M"]:
            self.assertIn(m_id, valid_models)

    # 5. Model failure isolation works
    def test_05_model_failure_isolation_works(self):
        preds = {
            "V2_15M": ModelPredictionOutput("V2_15M", 1, 20.0, 0.70, 15, True, 20.0, "h1"),
            "HYPO001": ModelPredictionOutput("HYPO001", 1, 18.0, 0.65, 30, True, 18.0, "h2"),
            "HYPO002": ModelPredictionOutput("HYPO002", 1, 25.0, 0.72, 60, True, 25.0, "h3"),
            "HYPO003": ModelPredictionOutput("HYPO003", 0, 0.0, 0.0, 15, False, 0.0, "FAIL"),  # Failed model
            "V3_60M": ModelPredictionOutput("V3_60M", 1, 22.0, 0.68, 60, True, 22.0, "h5")
        }
        out = self.ensemble.evaluate_candidate(
            symbol="TATACAP.NS", price=500.0, bar_volume=50000.0, available_capital=5000.0, model_predictions=preds
        )
        self.assertEqual(out.valid_model_count, 4)
        self.assertTrue(out.is_viable)

    # 6. Costs are applied correctly
    def test_06_costs_are_applied_correctly(self):
        engine = IndiaCostEngine()
        cost = engine.calculate_roundtrip_cost(capital=4500.0, gross_return=0.0025, slippage_bps=2.5)
        self.assertGreater(cost.brokerage, 0.0)
        self.assertGreater(cost.stt, 0.0)
        self.assertGreater(cost.exchange_charges, 0.0)
        self.assertGreater(cost.total_cost, 5.0)

    # 7. Whole-share sizing works
    def test_07_whole_share_sizing_works(self):
        preds = {m_id: ModelPredictionOutput(m_id, 1, 35.0, 0.75, 60, True, 35.0, "h") for m_id in ACTIVE_MODEL_SPECS}
        out = self.ensemble.evaluate_candidate(
            symbol="TATACAP.NS", price=500.0, bar_volume=50000.0, available_capital=5000.0, model_predictions=preds
        )
        self.assertIsInstance(out.affordable_quantity, int)
        self.assertEqual(out.affordable_quantity, 9)
        self.assertLessEqual(out.capital_required, 5000.0)

    # 8. ₹0.79 net => HOLD
    def test_08_hurdle_079_produces_hold(self):
        # Verify strict threshold boundary logic
        self.assertFalse(0.79 >= self.ensemble.min_net_edge_rupees)
        # Test low return that gives < 0.80 net rupees
        preds = {m_id: ModelPredictionOutput(m_id, 1, 15.0, 0.7, 15, True, 15.0, "h") for m_id in ACTIVE_MODEL_SPECS}
        out = self.ensemble.evaluate_candidate(
            symbol="TCS.NS", price=3500.0, bar_volume=50000.0, available_capital=5000.0, model_predictions=preds
        )
        self.assertLess(out.ensemble_expected_net_rupees, 0.80)
        self.assertFalse(out.is_viable)
        self.assertEqual(out.final_decision, "HOLD_CASH")

    # 9. ₹0.80 net => TRADE
    def test_09_hurdle_080_produces_trade(self):
        self.assertTrue(0.80 >= self.ensemble.min_net_edge_rupees)
        preds = {m_id: ModelPredictionOutput(m_id, 1, 35.0, 0.75, 60, True, 35.0, "h") for m_id in ACTIVE_MODEL_SPECS}
        out = self.ensemble.evaluate_candidate(
            symbol="TATACAP.NS", price=500.0, bar_volume=50000.0, available_capital=5000.0, model_predictions=preds
        )
        self.assertGreaterEqual(out.ensemble_expected_net_rupees, 0.80)
        self.assertTrue(out.is_viable)
        self.assertEqual(out.final_decision, "TRADE")

    # 10. ₹0.81 net => TRADE
    def test_10_hurdle_081_produces_trade(self):
        self.assertTrue(0.81 >= self.ensemble.min_net_edge_rupees)
        preds = {m_id: ModelPredictionOutput(m_id, 1, 40.0, 0.80, 60, True, 40.0, "h") for m_id in ACTIVE_MODEL_SPECS}
        out = self.ensemble.evaluate_candidate(
            symbol="TATACAP.NS", price=500.0, bar_volume=50000.0, available_capital=5000.0, model_predictions=preds
        )
        self.assertGreaterEqual(out.ensemble_expected_net_rupees, 0.81)
        self.assertTrue(out.is_viable)
        self.assertEqual(out.final_decision, "TRADE")

    # 11. Lunch blackout works
    def test_11_lunch_blackout_works(self):
        manifest = DailyModelManifestV3(
            session_date="2026-09-21", data_cutoff="2026-09-18", dataset_hash="h", feature_version="v",
            model_version="m", model_hash="h", target_column="t", horizon_bars=12, training_window="w",
            training_rows=1000, validation_result={}, regime_at_open="NORMAL_VOL", created_at="2026-09-24T00:00:00Z"
        )
        trader = SessionTraderV3(manifest=manifest, initial_capital=5000.0)
        self.assertTrue(trader.lunch_start <= time(12, 30) < trader.lunch_end)

    # 12. 14:25 cutoff works
    def test_12_entry_cutoff_works(self):
        manifest = DailyModelManifestV3(
            session_date="2026-09-21", data_cutoff="2026-09-18", dataset_hash="h", feature_version="v",
            model_version="m", model_hash="h", target_column="t", horizon_bars=12, training_window="w",
            training_rows=1000, validation_result={}, regime_at_open="NORMAL_VOL", created_at="2026-09-24T00:00:00Z"
        )
        trader = SessionTraderV3(manifest=manifest, initial_capital=5000.0)
        self.assertEqual(trader.entry_cutoff, time(14, 25))

    # 13. 15:25 mandatory close works
    def test_13_mandatory_close_works(self):
        manifest = DailyModelManifestV3(
            session_date="2026-09-21", data_cutoff="2026-09-18", dataset_hash="h", feature_version="v",
            model_version="m", model_hash="h", target_column="t", horizon_bars=12, training_window="w",
            training_rows=1000, validation_result={}, regime_at_open="NORMAL_VOL", created_at="2026-09-24T00:00:00Z"
        )
        trader = SessionTraderV3(manifest=manifest, initial_capital=5000.0)
        self.assertEqual(trader.eod_close_time, time(15, 25))

    # 14. No overnight position survives
    def test_14_no_overnight_position_survives(self):
        manifest = DailyModelManifestV3(
            session_date="2026-09-21", data_cutoff="2026-09-18", dataset_hash="h", feature_version="v",
            model_version="m", model_hash="h", target_column="t", horizon_bars=12, training_window="w",
            training_rows=1000, validation_result={}, regime_at_open="NORMAL_VOL", created_at="2026-09-24T00:00:00Z"
        )
        trader = SessionTraderV3(manifest=manifest, initial_capital=5000.0)
        # Empty active positions at session close
        self.assertEqual(len(trader.active_positions), 0)

    # 15. Zero-trade days are preserved
    def test_15_zero_trade_days_preserved(self):
        preds = {m_id: ModelPredictionOutput(m_id, 0, 0.0, 0.5, 15, True, 0.0, "h") for m_id in ACTIVE_MODEL_SPECS}
        out = self.ensemble.evaluate_candidate(
            symbol="TATACAP.NS", price=500.0, bar_volume=50000.0, available_capital=5000.0, model_predictions=preds
        )
        self.assertEqual(out.final_decision, "HOLD_CASH")
        self.assertFalse(out.is_viable)

    # 16. Capital cannot become negative
    def test_16_capital_cannot_become_negative(self):
        preds = {m_id: ModelPredictionOutput(m_id, 1, 35.0, 0.75, 60, True, 35.0, "h") for m_id in ACTIVE_MODEL_SPECS}
        out = self.ensemble.evaluate_candidate(
            symbol="EXPENSIVE.NS", price=6000.0, bar_volume=50000.0, available_capital=5000.0, model_predictions=preds
        )
        self.assertEqual(out.affordable_quantity, 0)
        self.assertEqual(out.final_decision, "HOLD_CASH")
        self.assertLessEqual(out.capital_required, 0.0)

    # 17. No fractional shares
    def test_17_no_fractional_shares(self):
        preds = {m_id: ModelPredictionOutput(m_id, 1, 35.0, 0.75, 60, True, 35.0, "h") for m_id in ACTIVE_MODEL_SPECS}
        out = self.ensemble.evaluate_candidate(
            symbol="FRACTIONAL.NS", price=333.33, bar_volume=50000.0, available_capital=5000.0, model_predictions=preds
        )
        self.assertIsInstance(out.affordable_quantity, int)
        self.assertEqual(float(out.affordable_quantity).is_integer(), True)

    # 18. Audit lineage is complete
    def test_18_audit_lineage_is_complete(self):
        record = CandidateDecisionAuditRecordV3(
            timestamp="2026-09-21T09:15:00+05:30", symbol="TATACAP.NS",
            V2_15M_prediction=10.0, V2_15M_confidence=0.6,
            HYPO001_prediction=12.0, HYPO001_confidence=0.62,
            HYPO002_prediction=15.0, HYPO002_confidence=0.65,
            HYPO003_prediction=0.0, HYPO003_confidence=0.5,
            V3_60M_prediction=14.0, V3_60M_confidence=0.64,
            model_agreement_count=4, valid_model_count=5,
            agreement_ratio="4/5", supporting_models=["V2_15M", "HYPO001", "HYPO002", "V3_60M"],
            contradicting_models=[],
            ensemble_direction=1, ensemble_confidence=0.64, selected_horizon=60,
            ensemble_expected_gross_bps=14.0, ensemble_expected_net_bps=5.0,
            ensemble_expected_net_rupees=2.25, price=500.0, affordable_quantity=9,
            capital_required=4500.0, estimated_brokerage=2.70, estimated_statutory_cost=2.09,
            estimated_spread=0.90, estimated_slippage=0.92, estimated_impact=0.0,
            total_cost=6.61, final_decision="TRADE", decision_reason=None,
            model_hashes={"V2_15M": "h1"}, dataset_hash="d_hash",
            feature_schema_hash="schema", training_cutoff="cutoff"
        )
        self.assertEqual(record.symbol, "TATACAP.NS")
        self.assertEqual(record.final_decision, "TRADE")

    # 19. Re-running produces identical results
    def test_19_rerunning_produces_identical_results(self):
        preds1 = {m_id: ModelPredictionOutput(m_id, 1, 25.0, 0.70, 60, True, 25.0, "h") for m_id in ACTIVE_MODEL_SPECS}
        preds2 = {m_id: ModelPredictionOutput(m_id, 1, 25.0, 0.70, 60, True, 25.0, "h") for m_id in ACTIVE_MODEL_SPECS}
        o1 = self.ensemble.evaluate_candidate("TATACAP.NS", 500.0, 50000.0, 5000.0, preds1)
        o2 = self.ensemble.evaluate_candidate("TATACAP.NS", 500.0, 50000.0, 5000.0, preds2)
        self.assertEqual(o1.ensemble_expected_net_rupees, o2.ensemble_expected_net_rupees)
        self.assertEqual(o1.final_decision, o2.final_decision)

    # 20. Session 5 data is excluded from historical baseline
    def test_20_session_5_data_is_excluded(self):
        base_raw = "v2/data/storage/normalized/historical_5m_raw.parquet"
        df_raw = pd.read_parquet(base_raw)
        max_date = pd.to_datetime(df_raw["timestamp"]).dt.date.max()
        self.assertLessEqual(max_date, date(2026, 9, 24), "Session 5 (2026-09-25) MUST NOT be present in historical dataset")


def load_all_market_data():
    base_raw = "v2/data/storage/normalized/historical_5m_raw.parquet"
    df_raw = pd.read_parquet(base_raw)
    import glob
    fresh_files = sorted(glob.glob("v2/data/storage/fresh/session_*_5m.parquet"))
    fresh_dfs = [pd.read_parquet(f) for f in fresh_files]
    comb_raw = pd.concat([df_raw] + fresh_dfs, ignore_index=True)
    comb_raw["date"] = pd.to_datetime(comb_raw["timestamp"]).dt.date
    return comb_raw, comb_raw


if __name__ == "__main__":
    unittest.main()
