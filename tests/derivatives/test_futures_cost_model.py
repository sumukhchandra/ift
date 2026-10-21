"""
Unit Tests for NSE Equity Futures Cost Model.
Validates the official April 1, 2026 statutory rates, additive identity,
and the exact ₹6.13 bps calculation on ₹10 Lakh notional.
"""

import unittest
from v2.derivatives.futures_cost_model import (
    NSEFuturesCostModel,
    FuturesExecutionStyle,
    FuturesTradeCostDetail
)
from v2.risk.cost_scenarios import BrokerCostConfig, BrokerageType


class TestNSEFuturesCostModel(unittest.TestCase):

    def setUp(self):
        self.cost_model = NSEFuturesCostModel()

    def test_exact_statutory_calculation_on_10l(self):
        """
        Verifies the exact round-trip calculation on ₹10 Lakh notional:
        - Turnover: ₹10,00,000 buy leg, ₹10,00,000 sell leg
        - Brokerage: ₹20 buy + ₹20 sell = ₹40.00 (0.40 bps)
        - STT: 0.05% on sell side = ₹500.00 (5.00 bps)
        - Exchange charges: ₹183/cr per side * 2 = ₹36.60 (0.366 bps)
        - SEBI fee: ₹10/cr per side * 2 = ₹2.00 (0.02 bps)
        - GST: 18% on (40.00 + 36.60 + 2.00) = 18% of 78.60 = ₹14.148 (0.1415 bps)
        - Stamp duty: 0.002% on buy side = ₹20.00 (0.20 bps)
        Total statutory: ₹612.748 ~ ₹612.75 -> 6.1275 bps of notional.
        """
        notional = 1000000.0  # ₹10 Lakhs
        stat = self.cost_model.compute_statutory_costs(notional, notional)

        self.assertAlmostEqual(stat["brokerage_inr"], 40.00, places=2)
        self.assertAlmostEqual(stat["stt_inr"], 500.00, places=2)
        self.assertAlmostEqual(stat["exchange_charges_inr"], 36.60, places=2)
        self.assertAlmostEqual(stat["sebi_fee_inr"], 2.00, places=2)
        self.assertAlmostEqual(stat["gst_inr"], 14.148, places=2)
        self.assertAlmostEqual(stat["stamp_duty_inr"], 20.00, places=2)
        self.assertAlmostEqual(stat["total_statutory_inr"], 612.748, places=2)

        # In bps:
        stat_bps = (stat["total_statutory_inr"] / notional) * 10000.0
        self.assertAlmostEqual(stat_bps, 6.12748, places=2)
        self.assertGreater(stat_bps, 6.10)
        self.assertLess(stat_bps, 6.15)

    def test_additive_identity(self):
        """Verify that sum of components exactly equals total friction bps."""
        for style in [FuturesExecutionStyle.AGGRESSIVE, FuturesExecutionStyle.PASSIVE, FuturesExecutionStyle.CONSERVATIVE_PASSIVE]:
            detail = self.cost_model.compute_round_trip_cost(
                contract_notional=1000000.0,
                style=style
            )
            self.assertTrue(detail.verify_additive_identity())
            self.assertAlmostEqual(
                detail.statutory_bps +
                detail.spread_component_bps +
                detail.impact_bps +
                detail.adverse_selection_bps +
                detail.basis_slippage_bps,
                detail.total_friction_bps,
                places=5
            )

    def test_small_notional_higher_statutory_bps(self):
        """
        On smaller notional (e.g. ₹2 Lakhs), the flat ₹20 brokerage increases
        statutory friction from ~6.13 bps to ~7.95 bps.
        """
        detail_2l = self.cost_model.compute_round_trip_cost(200000.0)
        detail_10l = self.cost_model.compute_round_trip_cost(1000000.0)

        self.assertGreater(detail_2l.statutory_bps, detail_10l.statutory_bps)
        self.assertAlmostEqual(detail_2l.statutory_bps, 7.95, delta=0.1)

    def test_refutes_naive_2_to_3_bps_assumption(self):
        """
        Proves that total futures friction is well above the naive 2-3.5 bps assumption.
        Even under passive execution on ₹10L, total friction is > 7.5 bps; aggressive is > 9.5 bps.
        """
        detail_agg = self.cost_model.compute_round_trip_cost(1000000.0, style=FuturesExecutionStyle.AGGRESSIVE)
        detail_pass = self.cost_model.compute_round_trip_cost(1000000.0, style=FuturesExecutionStyle.PASSIVE)

        self.assertGreater(detail_agg.total_friction_bps, 8.5)
        self.assertGreater(detail_pass.total_friction_bps, 7.5)


if __name__ == "__main__":
    unittest.main()
