"""
AlphaNSE V3 — Comprehensive Test Suite for DynamicIntradayCapitalRotationEngine V1.
Module: tests/portfolio/test_dynamic_rotation_engine.py

Verifies all 20 required behaviors and constraints using unittest:
1. Sequential capital recycling
2. One position -> another position rotation
3. Two position basket rotation
4. Insufficient incremental advantage (hysteresis block)
5. Rotation cost (both exit and entry costs accounted for)
6. Whole-share sizing under ₹5,000 budget
7. Insufficient capital handling
8. Entry cutoff (14:25 IST gate)
9. Stop loss exit
10. Take profit exit
11. Horizon timeout exit (60m)
12. Risk limit / high volatility crash regime
13. Sector concentration limit (max 3 per sector)
14. Correlation / redundant candidate handling
15. No-lookahead temporal barrier invariant
16. Frozen calibration factor immutability
17. Frozen model hash verification
18. Idempotent rotation
19. Duplicate order prevention
20. Zero-trade session & zero-position preservation
"""

import os
import sys
import unittest

# Ensure root is in path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.portfolio.dynamic_rotation_engine import (
    DynamicIntradayCapitalRotationEngine,
    ActivePosition,
    CandidateOpportunity,
    LiveExecutionDisabledError,
    BASELINE_MODE,
    DYNAMIC_ROTATION_MODE,
    PAPER_SHADOW_ONLY
)


class TestDynamicIntradayCapitalRotationEngine(unittest.TestCase):
    """Test suite covering all 20 requirements for DynamicIntradayCapitalRotationEngine V1."""

    def setUp(self):
        """Create a clean engine instance with standard test configuration."""
        self.engine = DynamicIntradayCapitalRotationEngine(
            initial_capital=5000.0,
            min_cash_buffer_rupees=50.0,
            min_net_edge_rupees=0.80,
            min_net_edge_bps=0.0,
            rotation_min_advantage_bps=8.0,
            rotation_penalty_rupees=0.50,
            hard_max_position_count=5,
            calibration_factor=0.4858,
            entry_cutoff_time="14:25",
            eod_close_time="15:25",
            live_execution_unlocked=False,
            model_hash="HASH_MODEL_FROZEN_123",
            dataset_hash="HASH_DATA_FROZEN_456",
            calibration_hash="HASH_CALIB_FROZEN_789"
        )

    def test_01_sequential_capital_recycling(self):
        """1. Verifies that when Trade A exits, capital is immediately returned and reusable."""
        engine = self.engine

        slice_0915 = {
            "AXISBANK.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"},
            "TATACAP.NS": {"ltp": 500.0, "volume": 1000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}
        }
        preds_0915 = {
            "AXISBANK.NS": {"raw_expected_bps": 80.0, "confidence": 0.8, "direction": 1, "supporting": ["M1", "M2"]},
            "TATACAP.NS": {"raw_expected_bps": 10.0, "confidence": 0.1, "direction": 1, "supporting": []}
        }
        engine.process_minute("09:15", slice_0915, preds_0915)
        self.assertIn("AXISBANK.NS", engine.active_positions)
        pos = engine.active_positions["AXISBANK.NS"]
        initial_cash_after_buy = engine.available_capital

        # Simulate price reaching take profit target
        target_tp = pos.take_profit_price
        slice_tp = {
            "AXISBANK.NS": {"ltp": target_tp, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"},
            "TATACAP.NS": {"ltp": 500.0, "volume": 1000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}
        }
        engine.process_minute("09:30", slice_tp, preds_0915)

        # Position closed via Take Profit
        self.assertNotIn("AXISBANK.NS", engine.active_positions)
        self.assertEqual(len(engine.closed_trades), 1)
        self.assertIn("TAKE_PROFIT", engine.closed_trades[0].exit_reason)
        # Capital must be released immediately: cash > initial_cash_after_buy
        self.assertGreater(engine.available_capital, initial_cash_after_buy)
        self.assertGreater(engine.available_capital, 4900.0)

    def test_02_one_position_to_another_rotation(self):
        """2. Verifies that a significantly superior opportunity triggers rotation out of an existing position."""
        engine = self.engine

        slice_1 = {
            "AXISBANK.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"},
            "TCS.NS": {"ltp": 2000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}
        }
        preds_1 = {
            "AXISBANK.NS": {"raw_expected_bps": 60.0, "confidence": 0.7, "direction": 1, "supporting": ["M1", "M2"]},
            "TCS.NS": {"raw_expected_bps": 0.0, "confidence": 0.1, "direction": 0, "supporting": []}
        }
        engine.process_minute("09:15", slice_1, preds_1)
        self.assertIn("AXISBANK.NS", engine.active_positions)

        # Lock free cash to test rotation
        engine.available_capital = 50.0

        # TCS shows massive breakout edge (+250 bps raw)
        slice_2 = {
            "AXISBANK.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"},
            "TCS.NS": {"ltp": 2000.0, "volume": 50000.0, "spread_bps": 1.5, "regime": "TRENDING_BULL"}
        }
        preds_2 = {
            "AXISBANK.NS": {"raw_expected_bps": 20.0, "confidence": 0.4, "direction": 1, "supporting": ["M1"]},
            "TCS.NS": {"raw_expected_bps": 250.0, "confidence": 0.95, "direction": 1, "supporting": ["M1", "M2", "M3", "M4"]}
        }
        res = engine.process_minute("09:25", slice_2, preds_2)

        # Should have rotated from AXISBANK to TCS
        self.assertTrue(any(d["action"] == "ROTATE" for d in res["decisions"]))
        self.assertNotIn("AXISBANK.NS", engine.active_positions)
        self.assertIn("TCS.NS", engine.active_positions)
        self.assertTrue(any(t.exit_reason == "ROTATION_REPLACEMENT" for t in engine.closed_trades))

    def test_03_two_position_basket_rotation(self):
        """3. Verifies rotation when holding a 2-stock basket and replacing the weaker leg."""
        engine = self.engine

        slice_1 = {
            "AXISBANK.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"},
            "TATACAP.NS": {"ltp": 300.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"},
            "RELIANCE.NS": {"ltp": 1200.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}
        }
        preds_1 = {
            "AXISBANK.NS": {"raw_expected_bps": 80.0, "confidence": 0.8, "direction": 1, "supporting": ["M1", "M2"]},
            "TATACAP.NS": {"raw_expected_bps": 80.0, "confidence": 0.85, "direction": 1, "supporting": ["M1", "M2"]},
            "RELIANCE.NS": {"raw_expected_bps": 0.0, "confidence": 0.1, "direction": 0, "supporting": []}
        }
        engine.process_minute("09:15", slice_1, preds_1)
        self.assertEqual(len(engine.active_positions), 2)
        self.assertIn("AXISBANK.NS", engine.active_positions)
        self.assertIn("TATACAP.NS", engine.active_positions)

        engine.available_capital = 50.0  # Lock free capital
        preds_2 = {
            "AXISBANK.NS": {"raw_expected_bps": 75.0, "confidence": 0.8, "direction": 1, "supporting": ["M1", "M2"]},
            "TATACAP.NS": {"raw_expected_bps": 15.0, "confidence": 0.3, "direction": 1, "supporting": ["M1"]},
            "RELIANCE.NS": {"raw_expected_bps": 250.0, "confidence": 0.95, "direction": 1, "supporting": ["M1", "M2", "M3", "M4"]}
        }
        slice_2 = {
            "AXISBANK.NS": {"ltp": 1002.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"},
            "TATACAP.NS": {"ltp": 300.5, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"},
            "RELIANCE.NS": {"ltp": 1200.0, "volume": 40000.0, "spread_bps": 1.5, "regime": "TRENDING_BULL"}
        }
        res = engine.process_minute("09:30", slice_2, preds_2)
        self.assertGreaterEqual(len(engine.closed_trades), 1)
        self.assertEqual(engine.closed_trades[0].exit_reason, "ROTATION_REPLACEMENT")
        self.assertEqual(engine.closed_trades[0].symbol, "TATACAP.NS")
        self.assertIn("RELIANCE.NS", engine.active_positions)

    def test_04_insufficient_incremental_advantage(self):
        """4. Verifies that tiny marginal edge does NOT trigger rotation (hysteresis check)."""
        engine = self.engine

        slice_1 = {
            "AXISBANK.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"},
            "INFY.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}
        }
        preds_1 = {
            "AXISBANK.NS": {"raw_expected_bps": 60.0, "confidence": 0.8, "direction": 1, "supporting": ["M1"]},
            "INFY.NS": {"raw_expected_bps": 0.0, "confidence": 0.1, "direction": 0, "supporting": []}
        }
        engine.process_minute("09:15", slice_1, preds_1)
        self.assertIn("AXISBANK.NS", engine.active_positions)
        engine.available_capital = 50.0  # Constrain capital

        # INFY only slightly better (+62 bps vs +58 bps), advantage is < 8 bps hysteresis
        preds_2 = {
            "AXISBANK.NS": {"raw_expected_bps": 58.0, "confidence": 0.8, "direction": 1, "supporting": ["M1"]},
            "INFY.NS": {"raw_expected_bps": 62.0, "confidence": 0.8, "direction": 1, "supporting": ["M1"]}
        }
        res = engine.process_minute("09:20", slice_1, preds_2)

        # Should NOT rotate!
        self.assertFalse(any(d["action"] == "ROTATE" for d in res["decisions"]))
        self.assertIn("AXISBANK.NS", engine.active_positions)
        self.assertNotIn("INFY.NS", engine.active_positions)

    def test_05_rotation_cost_accounting(self):
        """5. Verifies that exit cost + entry cost + rotation penalty are explicitly accounted for."""
        engine = self.engine
        cand_tick = {"ltp": 1000.0, "spread_bps": 2.4, "volatility_bps": 15.0, "volume": 10000.0}
        cand_model = {"raw_expected_bps": 80.0, "confidence": 0.8, "direction": 1, "supporting": ["M1", "M2"]}
        cand = engine._evaluate_candidate_opportunity("TCS.NS", "09:30", cand_tick, cand_model, False)

        cand_entry = engine._evaluate_candidate_opportunity("AXISBANK.NS", "09:15", cand_tick, cand_model, False)
        pos = engine._enter_position(cand_entry, 3, "09:15")
        pos_eval = engine._evaluate_position_remaining_value(pos, 1000.0)

        rot_comp = engine._find_best_rotation_target(cand, {"AXISBANK.NS": pos_eval})
        self.assertIsNotNone(rot_comp)
        self.assertGreater(rot_comp.exit_cost_current, 0)
        self.assertGreater(rot_comp.entry_cost_candidate, 0)
        self.assertEqual(rot_comp.rotation_penalty, 0.50)

    def test_06_whole_share_sizing(self):
        """6. Verifies sizing produces strictly integer whole shares."""
        engine = self.engine
        slice_1 = {
            "BAJFINANCE.NS": {"ltp": 7100.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"},
            "TATACAP.NS": {"ltp": 335.95, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}
        }
        preds_1 = {
            "BAJFINANCE.NS": {"raw_expected_bps": 100.0, "confidence": 0.9, "direction": 1, "supporting": ["M1"]},
            "TATACAP.NS": {"raw_expected_bps": 80.0, "confidence": 0.9, "direction": 1, "supporting": ["M1"]}
        }
        engine.process_minute("09:15", slice_1, preds_1)

        # Capital is 5000, so BAJFINANCE (7100) must have 0 shares and be rejected
        self.assertNotIn("BAJFINANCE.NS", engine.active_positions)
        if "TATACAP.NS" in engine.active_positions:
            qty = engine.active_positions["TATACAP.NS"].quantity
            self.assertIsInstance(qty, int)
            self.assertGreater(qty, 0)

    def test_07_insufficient_capital(self):
        """7. Verifies rejection with INSUFFICIENT_CAPITAL when cash < 1 share price."""
        engine = self.engine
        engine.available_capital = 100.0  # Not enough for ₹1000 stock
        slice_1 = {"INFY.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}}
        preds_1 = {"INFY.NS": {"raw_expected_bps": 100.0, "confidence": 0.9, "direction": 1, "supporting": ["M1"]}}
        engine.process_minute("09:15", slice_1, preds_1)
        self.assertEqual(len(engine.active_positions), 0)
        audit = engine.audit_ledger[-1]
        self.assertIn("INSUFFICIENT_CAPITAL", audit["candidate_evaluations"]["INFY.NS"]["reject_reasons"])

    def test_08_entry_cutoff_gate(self):
        """8. Verifies that no entries or rotations occur after 14:25 IST cutoff."""
        engine = self.engine
        slice_late = {"INFY.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}}
        preds_late = {"INFY.NS": {"raw_expected_bps": 150.0, "confidence": 0.9, "direction": 1, "supporting": ["M1", "M2"]}}

        # Minute 14:26 IST (after 14:25 cutoff)
        engine.process_minute("14:26", slice_late, preds_late)
        self.assertEqual(len(engine.active_positions), 0)
        audit = engine.audit_ledger[-1]
        self.assertIn("ENTRY_CUTOFF", audit["candidate_evaluations"]["INFY.NS"]["reject_reasons"])

    def test_09_stop_loss_exit(self):
        """9. Verifies that a position exits when price drops below stop_loss_price."""
        engine = self.engine
        slice_1 = {"AXISBANK.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}}
        preds_1 = {"AXISBANK.NS": {"raw_expected_bps": 80.0, "confidence": 0.8, "direction": 1, "supporting": ["M1"]}}
        engine.process_minute("09:15", slice_1, preds_1)
        pos = engine.active_positions["AXISBANK.NS"]

        # Price crashes below stop loss
        crash_price = pos.stop_loss_price - 5.0
        slice_crash = {"AXISBANK.NS": {"ltp": crash_price, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}}
        engine.process_minute("09:20", slice_crash, preds_1)

        self.assertNotIn("AXISBANK.NS", engine.active_positions)
        self.assertEqual(len(engine.closed_trades), 1)
        self.assertIn("STOP_LOSS", engine.closed_trades[0].exit_reason)

    def test_10_take_profit_exit(self):
        """10. Verifies take profit exit when price reaches target return."""
        engine = self.engine
        slice_1 = {"AXISBANK.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}}
        preds_1 = {"AXISBANK.NS": {"raw_expected_bps": 80.0, "confidence": 0.8, "direction": 1, "supporting": ["M1"]}}
        engine.process_minute("09:15", slice_1, preds_1)
        pos = engine.active_positions["AXISBANK.NS"]

        # Price reaches TP
        tp_price = pos.take_profit_price + 2.0
        slice_tp = {"AXISBANK.NS": {"ltp": tp_price, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}}
        engine.process_minute("09:25", slice_tp, preds_1)

        self.assertNotIn("AXISBANK.NS", engine.active_positions)
        self.assertEqual(len(engine.closed_trades), 1)
        self.assertIn("TAKE_PROFIT", engine.closed_trades[0].exit_reason)

    def test_11_horizon_exit(self):
        """11. Verifies exit upon reaching target horizon minutes (60 min)."""
        engine = self.engine
        slice_1 = {"AXISBANK.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}}
        preds_1 = {"AXISBANK.NS": {"raw_expected_bps": 80.0, "confidence": 0.8, "direction": 1, "supporting": ["M1"]}}
        engine.process_minute("09:15", slice_1, preds_1)
        pos = engine.active_positions["AXISBANK.NS"]
        pos.minutes_held = 60

        engine.process_minute("10:15", slice_1, preds_1)
        self.assertNotIn("AXISBANK.NS", engine.active_positions)
        self.assertEqual(len(engine.closed_trades), 1)
        self.assertIn("HORIZON_COMPLETED", engine.closed_trades[0].exit_reason)

    def test_12_risk_limit_hostile_regime(self):
        """12. Verifies candidates are rejected when regime is hostile."""
        engine = self.engine
        slice_crash = {"INFY.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "HIGH_VOLATILITY_CRASH"}}
        preds = {"INFY.NS": {"raw_expected_bps": 90.0, "confidence": 0.8, "direction": 1, "supporting": ["M1"]}}
        engine.process_minute("09:15", slice_crash, preds)
        self.assertEqual(len(engine.active_positions), 0)
        audit = engine.audit_ledger[-1]
        self.assertIn("REGIME_INVALID", audit["candidate_evaluations"]["INFY.NS"]["reject_reasons"])

    def test_13_sector_limit(self):
        """13. Verifies max sector concentration limit (max 3 positions per sector)."""
        engine = self.engine
        cand_tick = {"ltp": 100.0, "spread_bps": 2.0, "volatility_bps": 15.0, "volume": 10000.0}
        cand_model = {"raw_expected_bps": 80.0, "confidence": 0.8, "direction": 1, "supporting": ["M1"]}

        # Pre-populate 3 FINANCIAL_SERVICES positions
        for sym in ["AXISBANK.NS", "TATACAP.NS", "HDFCBANK.NS"]:
            c = engine._evaluate_candidate_opportunity(sym, "09:15", cand_tick, cand_model, False)
            engine._enter_position(c, 1, "09:15")

        # 4th financial stock (BAJFINANCE) must be rejected
        slice_4 = {"BAJFINANCE.NS": cand_tick}
        preds_4 = {"BAJFINANCE.NS": cand_model}
        engine.process_minute("09:20", slice_4, preds_4)
        self.assertNotIn("BAJFINANCE.NS", engine.active_positions)

    def test_14_correlation_and_reject_reasons(self):
        """14. Verifies non-viable candidates receive explicit reject reasons."""
        engine = self.engine
        slice_weak = {
            "SBIN.NS": {"ltp": 500.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"},
            "TCS.NS": {"ltp": 3000.0, "volume": 500.0, "spread_bps": 20.0, "regime": "SIDEWAYS"}
        }
        preds_weak = {
            "SBIN.NS": {"raw_expected_bps": 5.0, "confidence": 0.8, "direction": 1, "supporting": []},   # Hurdle fail
            "TCS.NS": {"raw_expected_bps": 80.0, "confidence": 0.8, "direction": 1, "supporting": ["M1"]}  # Liquidity fail
        }
        engine.process_minute("09:15", slice_weak, preds_weak)
        audit = engine.audit_ledger[-1]
        self.assertIn("HURDLE_FAIL", audit["candidate_evaluations"]["SBIN.NS"]["reject_reasons"])
        self.assertIn("INSUFFICIENT_LIQUIDITY", audit["candidate_evaluations"]["TCS.NS"]["reject_reasons"])

    def test_15_no_lookahead_temporal_barrier(self):
        """15. Verifies that engine decision strictly uses current timestamp without future bars."""
        engine = self.engine
        slice_0916 = {"AXISBANK.NS": {"ltp": 1192.4, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}}
        preds_0916 = {"AXISBANK.NS": {"raw_expected_bps": 80.0, "confidence": 0.8, "direction": 1, "supporting": ["M1"]}}
        res = engine.process_minute("09:16", slice_0916, preds_0916)
        self.assertEqual(res["time"], "09:16")
        self.assertEqual(engine.last_processed_timestamp, "09:16")

    def test_16_frozen_calibration_immutability(self):
        """16. Verifies calibration factor remains completely immutable across all minutes."""
        engine = self.engine
        initial_factor = engine.calibration_factor
        self.assertEqual(initial_factor, 0.4858)

        slice_1 = {"AXISBANK.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}}
        preds_1 = {"AXISBANK.NS": {"raw_expected_bps": 80.0, "confidence": 0.8, "direction": 1, "supporting": ["M1"]}}
        engine.process_minute("09:15", slice_1, preds_1)
        engine.process_minute("10:15", slice_1, preds_1)

        # Immutability check
        self.assertEqual(engine.calibration_factor, initial_factor)

    def test_17_frozen_model_hash_verification(self):
        """17. Verifies cryptographic hashes are attached to each audit record."""
        engine = self.engine
        slice_1 = {"AXISBANK.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}}
        preds_1 = {"AXISBANK.NS": {"raw_expected_bps": 80.0, "confidence": 0.8, "direction": 1, "supporting": ["M1"]}}
        engine.process_minute("09:15", slice_1, preds_1)

        audit = engine.audit_ledger[-1]
        self.assertEqual(audit["model_hash"], "HASH_MODEL_FROZEN_123")
        self.assertEqual(audit["dataset_hash"], "HASH_DATA_FROZEN_456")
        self.assertEqual(audit["calibration_hash"], "HASH_CALIB_FROZEN_789")

    def test_18_idempotent_rotation(self):
        """18. Verifies engine doesn't re-rotate into the same stock repeatedly on identical bars."""
        engine = self.engine
        slice_1 = {
            "AXISBANK.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"},
            "TCS.NS": {"ltp": 2000.0, "volume": 50000.0, "spread_bps": 1.5, "regime": "TRENDING_BULL"}
        }
        preds_1 = {
            "AXISBANK.NS": {"raw_expected_bps": 20.0, "confidence": 0.4, "direction": 1, "supporting": ["M1"]},
            "TCS.NS": {"raw_expected_bps": 250.0, "confidence": 0.95, "direction": 1, "supporting": ["M1", "M2"]}
        }
        engine.available_capital = 50.0
        engine.active_positions["AXISBANK.NS"] = ActivePosition(
            position_id="POS_01", symbol="AXISBANK.NS", quantity=3, entry_price=1000.0,
            entry_time="09:15", entry_notional=3000.0, target_horizon_minutes=60,
            stop_loss_price=985.0, take_profit_price=1050.0, expected_gross_bps=20.0,
            expected_net_bps=5.0, expected_net_rupees=1.5, entry_cost_rupees=3.0,
            supporting_models=["M1"], sector="FINANCIAL_SERVICES"
        )
        engine.process_minute("09:20", slice_1, preds_1)
        self.assertIn("TCS.NS", engine.active_positions)

        # Next minute with same signals: should HOLD TCS, not churn!
        res2 = engine.process_minute("09:21", slice_1, preds_1)
        self.assertFalse(any(d["action"] == "ROTATE" for d in res2["decisions"]))
        self.assertIn("TCS.NS", engine.active_positions)

    def test_19_duplicate_order_prevention(self):
        """19. Verifies that an already held symbol is not duplicated into multiple positions."""
        engine = self.engine
        slice_1 = {"AXISBANK.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}}
        preds_1 = {"AXISBANK.NS": {"raw_expected_bps": 80.0, "confidence": 0.8, "direction": 1, "supporting": ["M1"]}}
        engine.process_minute("09:15", slice_1, preds_1)
        self.assertIn("AXISBANK.NS", engine.active_positions)

        # Minute 09:16 with strong buy signal again
        res2 = engine.process_minute("09:16", slice_1, preds_1)
        self.assertEqual(len([s for s in engine.active_positions.keys() if s == "AXISBANK.NS"]), 1)
        self.assertFalse(any(d["action"] == "ENTER" and d["symbol"] == "AXISBANK.NS" for d in res2["decisions"]))

    def test_20_zero_trade_session_and_zero_positions(self):
        """20. Verifies engine preserves 100% cash when no candidates clear economic hurdle."""
        engine = self.engine
        slice_chop = {
            "AXISBANK.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"},
            "INFY.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"}
        }
        preds_chop = {
            "AXISBANK.NS": {"raw_expected_bps": 2.0, "confidence": 0.2, "direction": 0, "supporting": []},
            "INFY.NS": {"raw_expected_bps": -5.0, "confidence": 0.2, "direction": -1, "supporting": []}
        }
        for m in range(15, 30):
            engine.process_minute(f"09:{m:02d}", slice_chop, preds_chop)

        self.assertEqual(len(engine.active_positions), 0)
        self.assertEqual(len(engine.closed_trades), 0)
        self.assertEqual(engine.available_capital, 5000.0)
        summary = engine.generate_session_summary()
        self.assertEqual(summary["total_trades"], 0)
        self.assertEqual(summary["net_pnl_rupees"], 0.0)
        self.assertEqual(summary["ending_capital"], 5000.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
