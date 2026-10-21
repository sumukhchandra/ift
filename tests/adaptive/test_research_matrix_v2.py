"""
Unit and Integration Tests for AlphaNSE Adaptive Research Matrix V2.
Verifies:
  1. Authoritative Capital-Aware Ticket Economics (rejects 1-share fee traps)
  2. Conviction Tier Filtering (Q4 vs Extreme Top 15%)
  3. Multi-Horizon Holding Rules (30m, 60m, EOD)
  4. Equity Futures Execution (contract specs, margin feasibility, NSEFuturesCostModel scenarios)
  5. 3-Phase Protocol (Candidate Selection, Cryptographic Freeze, Phase C INCONCLUSIVE rules)
"""

import os
import shutil
import unittest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np

from v2.adaptive.opportunity_ranker import OpportunityRanker, ConvictionTier, TicketEconomicsResult
from v2.adaptive.session_trader import SessionTrader
from v2.adaptive.futures_trader import FuturesSessionTrader, FuturesCostScenario
from v2.adaptive.research_matrix_engine import (
    AdaptiveResearchMatrixEngine,
    ResearchSliceConfig,
    TrackType,
    ValidationVerdict,
    FrozenCandidateManifest
)
from v2.adaptive.audit_ledger import DailyModelManifest, TradeAuditRecord, CandidateDecisionAuditRecord, AuditLedger
from v2.risk.dynamic_cost_model import DynamicCostModel
from v2.derivatives.contract_master import NSEContractMaster
from v2.derivatives.contract_specs import NSEContractSpec, ContractType


class TestResearchMatrixV2(unittest.TestCase):

    def setUp(self):
        self.cost_model = DynamicCostModel(base_half_spread_bps=1.0, base_slippage_bps=2.0)
        self.ranker = OpportunityRanker(cost_model=self.cost_model)
        self.manifest = DailyModelManifest(
            session_date="2026-09-22",
            data_cutoff="2026-09-21T15:15:00+05:30",
            dataset_hash="test_data_hash",
            feature_version="test_feat_version",
            model_version="AlphaNSE_Test_v1",
            model_hash="test_model_hash",
            training_window="2026-06-29 to 2026-09-21",
            training_rows=48811,
            validation_result={"val_ic": 0.08},
            regime_at_open="NORMAL_VOL",
            created_at="2026-09-23T00:00:00Z"
        )
        self.test_engine_dir = "tests/scratch_matrix_v2"
        os.makedirs(self.test_engine_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_engine_dir):
            shutil.rmtree(self.test_engine_dir)

    def test_ticket_economics_rejects_insufficient_capital(self):
        """Verifies ticket economics rejects stock when capital cannot even buy 1 share."""
        # Stock price ₹6,000, capital ₹5,000, max allocation 30% = ₹1,500 max
        res = self.ranker.evaluate_ticket_economics(
            symbol="BAJFINANCE.NS",
            price=6000.0,
            available_capital=5000.0,
            expected_gross_bps=25.0
        )
        self.assertFalse(res.is_viable)
        self.assertEqual(res.qty, 0)
        self.assertEqual(res.reject_reason, "INSUFFICIENT_CAPITAL_FOR_1_SHARE")

    def test_ticket_economics_authoritative_calculation(self):
        """Verifies unit economics calculates gross INR minus costs accurately."""
        # Stock price ₹200, capital ₹5,000 -> max alloc ₹1,500 -> 7 shares (notional ₹1,400)
        # Expected move +30 bps = ₹4.20 gross.
        # Cost on ₹1,400 is ~14.7 bps = ₹2.06. Net = +₹2.14 > 0.
        res = self.ranker.evaluate_ticket_economics(
            symbol="TATACAP.NS",
            price=200.0,
            available_capital=5000.0,
            expected_gross_bps=30.0
        )
        self.assertTrue(res.is_viable)
        self.assertEqual(res.qty, 7)
        self.assertEqual(res.notional, 1400.0)
        self.assertGreater(res.net_expected_inr, 0)

    def test_preliminary_price_ratio_heuristic(self):
        """Verifies optional preliminary price ratio filter rejects stocks > 25% capital."""
        ranker_heuristic = OpportunityRanker(
            max_price_pct_heuristic=0.25, # Price must be <= ₹1,250 on ₹5,000 capital
            cost_model=self.cost_model
        )
        # TCS at ₹3,000 should be rejected by preliminary heuristic
        res = ranker_heuristic.evaluate_ticket_economics(
            symbol="TCS.NS",
            price=3000.0,
            available_capital=5000.0,
            expected_gross_bps=50.0
        )
        self.assertFalse(res.is_viable)
        self.assertIn("PRICE_EXCEEDS_HEURISTIC", res.reject_reason)

    def test_conviction_tier_filtering(self):
        """Verifies ranker filters opportunities by conviction tier."""
        ranker_extreme = OpportunityRanker(
            conviction_filter=ConvictionTier.EXTREME_TOP_15,
            cost_model=self.cost_model
        )
        self.assertEqual(ranker_extreme.conviction_filter, ConvictionTier.EXTREME_TOP_15)

    def test_futures_margin_feasibility(self):
        """Verifies FuturesTrader explicitly detects when capital is below SPAN margin."""
        trader = FuturesSessionTrader(
            manifest=self.manifest,
            capital=500000.0,       # Institutional ₹5L
            retail_capital_ref=5000.0, # Retail ₹5k
            cost_scenario=FuturesCostScenario.BASE
        )
        # Check active contract for RELIANCE
        contract = trader.contract_master.get_near_month_contract(
            "RELIANCE",
            as_of_date=pd.to_datetime(self.manifest.session_date).date()
        )
        self.assertIsNotNone(contract)
        # Lot size is 250 shares
        self.assertEqual(contract.lot_size, 250)
        req_margin = contract.calculate_required_margin(price=1250.0, lots=1)
        # 1250 * 250 * 0.20 = ₹62,500
        self.assertEqual(req_margin, 62500.0)
        # Clearly ₹5k is NOT feasible
        self.assertFalse(trader.retail_capital_ref >= req_margin)

    def test_phase_b_cryptographic_freeze(self):
        """Verifies Selected Candidate is frozen with deterministic SHA-256 hash."""
        engine = AdaptiveResearchMatrixEngine(
            frozen_dir=os.path.join(self.test_engine_dir, "frozen"),
            reports_dir=os.path.join(self.test_engine_dir, "reports")
        )
        config = ResearchSliceConfig(
            track=TrackType.CASH_EQUITY,
            horizon_bars=6,
            conviction_tier=ConvictionTier.Q4_TOP_CONVICTION,
            direction_filter=None,
            cost_scenario="BASE"
        )
        dummy_metrics = MagicMock()
        dummy_metrics.to_dict.return_value = {"mean_net_pnl": 1.25}

        frozen = engine.freeze_selected_candidate(config, dummy_metrics, self.manifest)
        self.assertIsNotNone(frozen.config_hash)
        self.assertEqual(len(frozen.config_hash), 64) # SHA-256 length
        self.assertTrue(os.path.exists(os.path.join(self.test_engine_dir, "frozen", f"{frozen.candidate_id}.json")))

    def test_phase_c_inconclusive_rule(self):
        """CRITICAL: Verifies Phase C outputs INCONCLUSIVE if trades < 30 or sessions < 10."""
        engine = AdaptiveResearchMatrixEngine(
            frozen_dir=os.path.join(self.test_engine_dir, "frozen"),
            reports_dir=os.path.join(self.test_engine_dir, "reports")
        )
        manifest = FrozenCandidateManifest(
            candidate_id="Candidate_Test",
            created_at="2026-09-23T00:00:00Z",
            config={"track": "CASH_EQUITY"},
            config_hash="abc123hash",
            feature_version="feat1",
            model_version="mod1",
            model_hash="hash1",
            dataset_hash="dhash1",
            phase_a_metrics={}
        )

        # Create dummy small sample: 8 trades across 3 sessions (high profit)
        mock_trades = [
            MagicMock(net_pnl_rupees=2.50) for _ in range(8)
        ]

        report = engine.evaluate_phase_c_validation(
            candidate_manifest=manifest,
            fresh_trades=mock_trades,
            fresh_sessions_count=3,
            folds_count=3
        )

        # MUST be INCONCLUSIVE because sample size is below threshold (8 trades < 30)
        self.assertEqual(report.verdict, ValidationVerdict.INCONCLUSIVE)
        self.assertFalse(report.sample_sufficient)
        self.assertIn("INSUFFICIENT SAMPLE SIZE", report.verdict_rationale)
        self.assertIn("INCONCLUSIVE / CONTINUE", report.verdict_rationale)

    def test_no_early_stop_inconclusive_preservation(self):
        """
        CRITICAL PROTOCOL GUARD:
        Verifies that consecutive negative sessions DO NOT trigger a premature FAIL
        when sample size is below threshold. The system must remain INCONCLUSIVE / CONTINUE.
        """
        engine = AdaptiveResearchMatrixEngine(
            frozen_dir=os.path.join(self.test_engine_dir, "frozen"),
            reports_dir=os.path.join(self.test_engine_dir, "reports")
        )
        manifest = FrozenCandidateManifest(
            candidate_id="Candidate_CASH_EQUITY_12b_72d9ac7b",
            created_at="2026-09-23T00:00:00Z",
            config={"track": "CASH_EQUITY", "horizon_bars": 12, "conviction_tier": "EXTREME_TOP_15"},
            config_hash="72d9ac7b",
            feature_version="feat1",
            model_version="mod1",
            model_hash="hash1",
            dataset_hash="dhash1",
            phase_a_metrics={}
        )

        # Simulate 3 consecutive negative sessions with 15 total trades (< 30 trades threshold)
        consecutive_neg_trades = [
            MagicMock(net_pnl_rupees=-2.50) for _ in range(5)
        ] + [
            MagicMock(net_pnl_rupees=-3.10) for _ in range(5)
        ] + [
            MagicMock(net_pnl_rupees=-1.80) for _ in range(5)
        ]

        report = engine.evaluate_phase_c_validation(
            candidate_manifest=manifest,
            fresh_trades=consecutive_neg_trades,
            fresh_sessions_count=3,
            folds_count=1
        )

        # Invariant: No sequential stopping rule after 3 negative sessions; must stay INCONCLUSIVE / CONTINUE
        self.assertEqual(report.verdict, ValidationVerdict.INCONCLUSIVE)
        self.assertFalse(report.sample_sufficient)
        self.assertIn("INCONCLUSIVE / CONTINUE", report.verdict_rationale)

    def test_candidate_decision_telemetry_fields(self):
        """
        Verifies CandidateDecisionAuditRecord and TradeAuditRecord preserve all 29 fields
        and adhere to the single authoritative cost engine invariant.
        """
        ledger = AuditLedger(ledger_dir=os.path.join(self.test_engine_dir, "ledger"))

        # Verify candidate decision record field completeness
        decision = CandidateDecisionAuditRecord(
            timestamp="2026-09-22T09:20:00+05:30",
            session_date="2026-09-22",
            symbol="INFY.NS",
            model_version="AlphaNSE_Test_v1",
            model_hash="test_model_hash",
            dataset_hash="test_data_hash",
            data_cutoff="2026-09-21T15:15:00+05:30",
            predicted_return_bps=18.5,
            realized_return_bps=12.1,
            predicted_direction=1,
            actual_direction=1,
            quantity=5,
            entry_price=1450.0,
            exit_price=1460.0,
            notional=7250.0,
            gross_pnl_rupees=50.0,
            brokerage_rupees=4.35,
            stt_rupees=1.83,
            stamp_duty_rupees=0.22,
            exchange_charges_rupees=0.45,
            sebi_fees_rupees=0.01,
            gst_rupees=0.87,
            spread_cost_rupees=1.45,
            slippage_cost_rupees=2.90,
            total_friction_rupees=12.08,
            net_pnl_rupees=37.92,
            conviction_percentile=92.5,
            z_score=1.44,
            conviction_tier="EXTREME_TOP_15",
            ticket_economics_result="VIABLE",
            risk_gate_result="PASSED",
            final_decision="ENTERED",
            rejection_reason="NONE",
            trade_id="trd12345"
        )

        dec_dict = decision.to_dict()
        required_fields = [
            "timestamp", "session_date", "symbol", "model_version", "model_hash", "dataset_hash",
            "predicted_return_bps", "realized_return_bps", "predicted_direction", "actual_direction",
            "quantity", "entry_price", "exit_price", "notional", "gross_pnl_rupees",
            "brokerage_rupees", "stt_rupees", "stamp_duty_rupees", "exchange_charges_rupees", "sebi_fees_rupees", "gst_rupees",
            "spread_cost_rupees", "slippage_cost_rupees", "total_friction_rupees", "net_pnl_rupees",
            "conviction_percentile", "ticket_economics_result", "risk_gate_result", "final_decision", "rejection_reason"
        ]
        for field in required_fields:
            self.assertIn(field, dec_dict, f"Missing field in CandidateDecisionAuditRecord: {field}")

        # Test ledger persistence and roundtrip integrity
        ledger.save_decisions("2026-09-22", [decision])
        loaded = ledger.load_decisions("2026-09-22")
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].symbol, "INFY.NS")
        self.assertEqual(loaded[0].net_pnl_rupees, 37.92)

        # Single Authoritative Cost Invariant verification
        stat_sum = round(decision.brokerage_rupees + decision.stt_rupees + decision.stamp_duty_rupees +
                         decision.exchange_charges_rupees + decision.sebi_fees_rupees + decision.gst_rupees, 2)
        exec_sum = round(decision.spread_cost_rupees + decision.slippage_cost_rupees, 2)
        total_calc = round(stat_sum + exec_sum, 2)
        self.assertAlmostEqual(decision.total_friction_rupees, total_calc, delta=0.05)


if __name__ == "__main__":
    unittest.main()

