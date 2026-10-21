"""
tests/test_unified_ensemble.py
Comprehensive test suite for AlphaNSE Unified Ensemble Architecture.
Covers signal aggregation, consensus scoring, risk limits, transaction-cost hurdles,
regime gating, stagnation exits, daily loss circuit breakers, and air-gap integrity.
"""

import unittest
from datetime import datetime, timedelta
import os
import sys

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.ensemble.specialist_signal import SpecialistSignal, SignalDirection, HorizonCategory
from v3.ensemble.specialist_registry import SpecialistRegistry
from v3.ensemble.unified_meta_decision_engine import UnifiedMetaDecisionEngine, MetaDecisionOutput
from v3.ensemble.unified_risk_engine import UnifiedRiskEngine, PositionRiskState
from v3.ensemble.unified_paper_executor import UnifiedPaperExecutor


class TestUnifiedEnsemble(unittest.TestCase):

    def setUp(self):
        self.registry = SpecialistRegistry()
        self.meta_engine = UnifiedMetaDecisionEngine(min_agreement_threshold=3, min_consensus_score=0.30)
        self.risk_engine = UnifiedRiskEngine(max_capital=1500.0, max_daily_loss=30.0)

    # 1. Specialist Signal Schema Validation
    def test_specialist_signal_schema(self):
        market_snapshot = {
            "^NSEI": {"price": 22497.15, "ema50": 23842.22},
            "INFY.NS": {"price": 1018.5, "ema5": 1022.0, "ema20": 1015.0, "rsi": 55.0, "vol_surge": 1.4},
            "TATACAP.NS": {"price": 319.35, "support_shelf": 316.5, "vol_surge": 1.9},
            "BAJFINANCE.NS": {"price": 981.2, "channel_low": 995.0, "channel_high": 1045.0},
            "AXISBANK.NS": {"price": 1222.5, "rsi": 28.0, "bb_pct_b": -0.02},
            "RELIANCE.NS": {"price": 1183.2, "vwap": 1195.0, "composite_factor_score": -0.35}
        }
        signals = self.registry.evaluate_all(market_snapshot)
        self.assertEqual(len(signals), 7, "All 7 specialist models must produce signals")

        for model_id, sig in signals.items():
            self.assertIsInstance(sig, SpecialistSignal)
            self.assertIn(sig.direction, [SignalDirection.BUY, SignalDirection.SELL, SignalDirection.HOLD])
            self.assertTrue(0.0 <= sig.confidence <= 1.0)
            self.assertIsInstance(sig.horizon, HorizonCategory)
            self.assertIsInstance(sig.to_dict(), dict)

    # 2. Consensus Scoring & Agreement Hurdle
    def test_consensus_agreement_thresholds(self):
        # Scenario A: Strong Bearish Consensus (4 models vote SELL)
        sell_signals = {
            "SMC_4CONF_920": SpecialistSignal("^NSEI", "SMC", "SMC", SignalDirection.SELL, HorizonCategory.INTRADAY_5M, 0.85, -0.50, 45),
            "HYPO002": SpecialistSignal("BAJFINANCE.NS", "HYPO002", "HYPO002", SignalDirection.SELL, HorizonCategory.INTRADAY_60M, 0.80, -0.60, 60),
            "V3_60M": SpecialistSignal("RELIANCE.NS", "V3_60M", "V3_60M", SignalDirection.SELL, HorizonCategory.INTRADAY_60M, 0.78, -0.45, 60),
            "V2_15M": SpecialistSignal("INFY.NS", "V2_15M", "V2_15M", SignalDirection.SELL, HorizonCategory.INTRADAY_15M, 0.75, -0.35, 45),
            "HYPO001": SpecialistSignal("TATACAP.NS", "HYPO001", "HYPO001", SignalDirection.HOLD, HorizonCategory.INTRADAY_30M, 0.40, 0.0, 0),
            "HYPO003": SpecialistSignal("AXISBANK.NS", "HYPO003", "HYPO003", SignalDirection.HOLD, HorizonCategory.INTRADAY_15M, 0.40, 0.0, 0),
            "SWING_REV_3D_MACRO": SpecialistSignal("UNIVERSE", "SWING", "SWING", SignalDirection.HOLD, HorizonCategory.MULTI_DAY_SWING, 0.50, 0.0, 0),
        }
        market_snapshot = {"^NSEI": {"price": 22400.0, "ema50": 23800.0}}
        decision = self.meta_engine.evaluate_opportunity("BAJFINANCE.NS", sell_signals, market_snapshot)
        self.assertEqual(decision.action, SignalDirection.SELL)
        self.assertEqual(decision.agreement_count, 4)
        self.assertTrue(decision.consensus_score <= -0.30)

        # Scenario B: Conflicting Signals (2 BUY vs 2 SELL vs 3 HOLD) -> Must resolve to HOLD
        conflicting_signals = {
            "M1": SpecialistSignal("A", "M1", "M1", SignalDirection.BUY, HorizonCategory.INTRADAY_15M, 0.70, 0.30, 45),
            "M2": SpecialistSignal("B", "M2", "M2", SignalDirection.BUY, HorizonCategory.INTRADAY_15M, 0.65, 0.25, 45),
            "M3": SpecialistSignal("C", "M3", "M3", SignalDirection.SELL, HorizonCategory.INTRADAY_15M, 0.70, -0.30, 45),
            "M4": SpecialistSignal("D", "M4", "M4", SignalDirection.SELL, HorizonCategory.INTRADAY_15M, 0.65, -0.25, 45),
            "M5": SpecialistSignal("E", "M5", "M5", SignalDirection.HOLD, HorizonCategory.INTRADAY_15M, 0.40, 0.0, 0),
            "M6": SpecialistSignal("F", "M6", "M6", SignalDirection.HOLD, HorizonCategory.INTRADAY_15M, 0.40, 0.0, 0),
            "M7": SpecialistSignal("G", "M7", "M7", SignalDirection.HOLD, HorizonCategory.INTRADAY_15M, 0.40, 0.0, 0),
        }
        conflict_decision = self.meta_engine.evaluate_opportunity("SYM", conflicting_signals, market_snapshot)
        self.assertEqual(conflict_decision.action, SignalDirection.HOLD, "Conflicting signals must resolve to HOLD")

    # 3. Transaction Cost Hurdle Filter
    def test_transaction_cost_hurdle(self):
        # Expected return (+0.08%) is smaller than 2.0x statutory friction (~0.30%) -> Must WAIT/HOLD
        low_edge_signals = {
            f"M{i}": SpecialistSignal(f"S{i}", f"M{i}", f"M{i}", SignalDirection.BUY, HorizonCategory.INTRADAY_15M, 0.80, 0.08, 30)
            for i in range(5)
        }
        market_snapshot = {"^NSEI": {"price": 24000.0, "ema50": 23000.0}, "INFY.NS": {"price": 1000.0, "regime": "TRENDING_BULL"}}
        decision = self.meta_engine.evaluate_opportunity("INFY.NS", low_edge_signals, market_snapshot)
        self.assertIn(decision.action, [SignalDirection.WAIT, SignalDirection.HOLD])
        self.assertFalse(decision.net_edge_cleared)

    # 4. Macro Regime Gate
    def test_macro_regime_filtering(self):
        # Bear Macro (NIFTY 22,000 < EMA50 23,800) must suppress multi-day long swing
        swing_signal = {
            f"M{i}": SpecialistSignal(f"S{i}", f"M{i}", f"M{i}", SignalDirection.BUY, HorizonCategory.MULTI_DAY_SWING, 0.85, 0.60, 1200)
            for i in range(5)
        }
        bear_snapshot = {"^NSEI": {"price": 22000.0, "ema50": 23800.0}}
        decision = self.meta_engine.evaluate_opportunity("UNIVERSE", swing_signal, bear_snapshot)
        self.assertEqual(decision.action, SignalDirection.HOLD, "Bear macro must suppress multi-day long swings")
        self.assertEqual(decision.macro_regime, "BEAR")

    # 5. Risk Engine: Whole-Share Integer Sizing & ₹1,500 Capital Limit
    def test_risk_engine_capital_and_position_limits(self):
        decision = MetaDecisionOutput(
            target_symbol="BAJFINANCE.NS",
            action=SignalDirection.BUY,
            consensus_score=0.65,
            agreement_count=5,
            total_specialists=7,
            agreement_ratio="5/7",
            supporting_models=["M1", "M2", "M3", "M4", "M5"],
            opposing_models=[],
            neutral_models=["M6", "M7"],
            expected_gross_pct=1.5,
            estimated_friction_pct=0.2,
            expected_net_pct=1.3,
            net_edge_cleared=True,
            macro_regime="BULL",
            micro_regime="TRENDING_BULL",
            recommended_horizon_mins=60,
            rationale="Approved"
        )
        # Price is ₹980. Deployable cash = 1500 * 0.95 = 1425. Sized shares = 1425 // 980 = 1 share
        shares, cap_req, reason = self.risk_engine.calculate_order_sizing(decision, 980.0)
        self.assertEqual(shares, 1, "Sizing must be whole integer share")
        self.assertEqual(cap_req, 980.0)
        self.assertTrue(cap_req <= 1500.0, "Capital deployed must be within ₹1,500.00")

        # Open position
        pos, status = self.risk_engine.open_position(decision, 980.0)
        self.assertIsNotNone(pos)
        self.assertEqual(self.risk_engine.active_position.quantity, 1)

        # Attempt to open second position -> Must be rejected (max 1 position)
        pos2, status2 = self.risk_engine.open_position(decision, 980.0)
        self.assertIsNone(pos2)
        self.assertIn("MAX_POSITIONS_REACHED", status2)

    # 6. Daily Loss Circuit Breaker (₹30.00 Limit)
    def test_daily_loss_circuit_breaker(self):
        # Simulate an open position that loses ₹32 net
        decision = MetaDecisionOutput(
            target_symbol="INFY.NS", action=SignalDirection.BUY, consensus_score=0.6,
            agreement_count=4, total_specialists=7, agreement_ratio="4/7",
            supporting_models=["M1"], opposing_models=[], neutral_models=[],
            expected_gross_pct=1.0, estimated_friction_pct=0.2, expected_net_pct=0.8,
            net_edge_cleared=True, macro_regime="BULL", micro_regime="TRENDING_BULL",
            recommended_horizon_mins=45, rationale="Approved"
        )
        pos, _ = self.risk_engine.open_position(decision, 1000.0)
        self.assertIsNotNone(pos)

        # Close position with ₹32.00 total net loss (e.g. ₹28 gross loss + ₹4 friction)
        gross_pnl, net_pnl = self.risk_engine.close_position(exit_price=972.0, statutory_friction=4.0)
        self.assertEqual(net_pnl, -32.0)
        self.assertTrue(self.risk_engine.circuit_breaker_tripped, "Circuit breaker must trip when daily loss >= ₹30.00")

        # Check trading is now blocked fail-closed
        allowed, reason = self.risk_engine.is_trading_allowed()
        self.assertFalse(allowed)
        self.assertIn("CIRCUIT_BREAKER_TRIPPED", reason)

    # 7. Stagnation / Time-Decay Timeout Exit (Fix for TCS Defect)
    def test_stagnation_timeout_chop_exit(self):
        decision = MetaDecisionOutput(
            target_symbol="TCS.NS", action=SignalDirection.SELL, consensus_score=-0.5,
            agreement_count=4, total_specialists=7, agreement_ratio="4/7",
            supporting_models=["M1"], opposing_models=[], neutral_models=[],
            expected_gross_pct=0.8, estimated_friction_pct=0.15, expected_net_pct=0.65,
            net_edge_cleared=True, macro_regime="BEAR", micro_regime="SIDEWAYS",
            recommended_horizon_mins=45, rationale="Approved"
        )
        t_entry = datetime(2026, 10, 5, 11, 9, 0)
        pos, _ = self.risk_engine.open_position(decision, 1000.0, timestamp=t_entry)
        self.assertIsNotNone(pos)

        # Price sits in flat chop at ₹1,000.50 (+0.05% change) for 50 minutes (past 45-min stagnation limit)
        t_current = t_entry + timedelta(minutes=50)
        should_exit, reason, exit_p = self.risk_engine.evaluate_position_exit(1000.50, current_time=t_current)
        self.assertTrue(should_exit, "Stagnation timeout must trigger exit when trade makes no progress after 45 minutes")
        self.assertEqual(reason, "STAGNATION_TIMEOUT_CHOP_EXIT")

    # 8. Dynamic Trailing Stop Ratchet
    def test_trailing_stop_ratchet(self):
        decision = MetaDecisionOutput(
            target_symbol="BAJFINANCE.NS", action=SignalDirection.SELL, consensus_score=-0.6,
            agreement_count=5, total_specialists=7, agreement_ratio="5/7",
            supporting_models=["M1"], opposing_models=[], neutral_models=[],
            expected_gross_pct=2.0, estimated_friction_pct=0.2, expected_net_pct=1.8,
            net_edge_cleared=True, macro_regime="BEAR", micro_regime="TRENDING_BEAR",
            recommended_horizon_mins=60, rationale="Approved"
        )
        pos, _ = self.risk_engine.open_position(decision, 1000.0)

        # Price drops favorably to 980.0 (+2.0% gain on short) -> Trailing stop activates
        self.risk_engine.evaluate_position_exit(980.0)
        self.assertTrue(self.risk_engine.active_position.trailing_stop_active)
        # Trailing stop set at 980 * (1 + 0.0035) = 983.43
        trailing_sl = self.risk_engine.active_position.trailing_stop_price
        self.assertTrue(trailing_sl < 1000.0, "Trailing stop must lock in profits below entry for short")

        # Price bounces back to 985.0 -> Trailing stop triggered
        should_exit, reason, _ = self.risk_engine.evaluate_position_exit(985.0)
        self.assertTrue(should_exit)
        self.assertEqual(reason, "TRAILING_STOP_RATCHET")

    # 9. Fail-Closed Air-Gap Security Verification
    def test_fail_closed_airgap_security(self):
        executor = UnifiedPaperExecutor(
            starting_capital=1500.0,
            max_daily_loss=30.0,
            ledger_path=os.path.join(WORKSPACE_ROOT, "v3", "reports", "test_ledger.jsonl"),
            state_path=os.path.join(WORKSPACE_ROOT, "v3", "reports", "test_state.json")
        )
        self.assertFalse(executor.LIVE_TRADING)
        self.assertFalse(executor.ALLOW_REAL_ORDERS)

        # Attempting to breach air gap must raise PermissionError
        executor.LIVE_TRADING = True
        with self.assertRaises(PermissionError):
            executor._enforce_airgap()


if __name__ == "__main__":
    unittest.main()
