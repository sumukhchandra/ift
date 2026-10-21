"""
Unit Tests for BrokerCostConfig & CostScenarioRegistry.
Verifies:
  1. Configurable broker commission models (PERCENT_WITH_CAP, FLAT, ZERO).
  2. Accurate roundtrip statutory fee decomposition.
  3. Standardized CostScenario registry outputs (STATUTORY_ONLY, BASE_AGGRESSIVE, PASSIVE).
"""

import unittest
from v2.risk.cost_scenarios import (
    BrokerCostConfig,
    BrokerageType,
    ScenarioType,
    CostScenario,
    CostScenarioRegistry
)


class TestBrokerCostConfig(unittest.TestCase):

    def setUp(self):
        self.zerodha = BrokerCostConfig(
            name="Zerodha_Test",
            brokerage_type=BrokerageType.PERCENT_WITH_CAP,
            brokerage_rate=0.0003,
            brokerage_max_per_order=20.0
        )
        self.flat_broker = BrokerCostConfig(
            name="Flat_Test",
            brokerage_type=BrokerageType.FLAT_PER_ORDER,
            brokerage_max_per_order=15.0
        )
        self.zero_broker = BrokerCostConfig(
            name="Zero_Test",
            brokerage_type=BrokerageType.ZERO_BROKERAGE
        )

    def test_brokerage_types(self):
        """Verify commission calculation across broker fee schedules."""
        # 5,000 notional: 0.03% = 1.50 Rs
        self.assertEqual(self.zerodha.calculate_brokerage(5000.0), 1.50)

        # 100,000 notional: 0.03% = 30 Rs -> capped at 20 Rs
        self.assertEqual(self.zerodha.calculate_brokerage(100000.0), 20.00)

        # Flat broker charges 15 Rs regardless of size
        self.assertEqual(self.flat_broker.calculate_brokerage(5000.0), 15.00)
        self.assertEqual(self.flat_broker.calculate_brokerage(100000.0), 15.00)

        # Zero broker charges 0
        self.assertEqual(self.zero_broker.calculate_brokerage(5000.0), 0.0)

    def test_statutory_breakdown_on_5k(self):
        """Verify the exact 10.63 bps statutory calculation on 5k notional."""
        breakdown = self.zerodha.calculate_statutory_charges(5000.0, 5000.0)

        self.assertEqual(breakdown["brokerage"], 3.00)   # 1.50 * 2
        self.assertEqual(breakdown["stt"], 1.25)         # 0.025% of 5000
        self.assertEqual(breakdown["exchange"], 0.307)   # 0.00307% of 10000
        self.assertEqual(breakdown["sebi"], 0.01)        # 0.0001% of 10000
        self.assertAlmostEqual(breakdown["gst"], 0.597, places=2)  # 18% of 3.317
        self.assertEqual(breakdown["stamp"], 0.15)       # 0.003% of 5000
        self.assertAlmostEqual(breakdown["total_rupees"], 5.314, places=2)
        self.assertAlmostEqual(breakdown["total_bps"], 10.63, delta=0.02)

    def test_cost_scenario_registry(self):
        """Verify registry scenarios produce expected decomposed friction."""
        stat_only = CostScenarioRegistry.get_scenario(ScenarioType.STATUTORY_ONLY, self.zerodha)
        base_aggr = CostScenarioRegistry.get_scenario(ScenarioType.BASE_AGGRESSIVE, self.zerodha)
        passive = CostScenarioRegistry.get_scenario(ScenarioType.PASSIVE, self.zerodha)

        c_stat = stat_only.compute_total_cost_bps(5000.0)
        self.assertEqual(c_stat["spread_bps"], 0.0)
        self.assertEqual(c_stat["slippage_bps"], 0.0)
        self.assertEqual(c_stat["total_cost_bps"], c_stat["statutory_bps"])

        c_aggr = base_aggr.compute_total_cost_bps(5000.0)
        self.assertGreater(c_aggr["total_cost_bps"], c_stat["total_cost_bps"])
        self.assertEqual(c_aggr["spread_bps"], 2.0)

        c_pass = passive.compute_total_cost_bps(5000.0)
        self.assertEqual(c_pass["fill_probability"], 0.65)
        self.assertEqual(c_pass["spread_component_bps"], 1.0)
        self.assertEqual(c_pass["adverse_selection_bps"], 1.0)
        self.assertGreater(c_pass["partial_fill_component_bps"], 0.0)

    def test_cost_scenario_additive_identity(self):
        """Verify sum(components) == total_expected_cost_bps across all 5 registry scenarios."""
        for scenario_type in ScenarioType:
            scenario = CostScenarioRegistry.get_scenario(scenario_type, self.zerodha)
            cost_dict = scenario.compute_total_cost_bps(notional=5000.0)

            component_sum = (
                cost_dict["statutory_bps"]
                + cost_dict["spread_component_bps"]
                + cost_dict["impact_bps"]
                + cost_dict["adverse_selection_bps"]
                + cost_dict["partial_fill_component_bps"]
            )
            self.assertAlmostEqual(
                component_sum,
                cost_dict["total_expected_cost_bps"],
                places=2,
                msg=f"Additive identity failed for {scenario_type}"
            )
            self.assertEqual(cost_dict["cost_per_completed_trade_bps"], cost_dict["total_expected_cost_bps"])
            self.assertAlmostEqual(
                cost_dict["cost_per_attempted_trade_bps"],
                cost_dict["total_expected_cost_bps"] * cost_dict["fill_probability"],
                places=2
            )

    def test_execution_tree_unfilled_policies(self):
        """Verify CANCEL vs MARKET_CROSS execution policies in execution tree."""
        cross_scenario = CostScenarioRegistry.get_scenario(ScenarioType.PASSIVE, self.zerodha)
        cancel_scenario = CostScenario(
            scenario_type=ScenarioType.PASSIVE,
            broker_config=self.zerodha,
            base_spread_bps=2.0,
            base_impact_bps=2.0,
            impact_coefficient_bps=5.0,
            fill_probability=0.65,
            partial_fill_rate=0.80,
            adverse_selection_bps=1.0,
            slippage_multiplier=1.0,
            unfilled_policy="CANCEL"
        )

        c_cross = cross_scenario.compute_total_cost_bps(5000.0)
        c_cancel = cancel_scenario.compute_total_cost_bps(5000.0)

        # Cancel policy avoids paying completion friction on unfilled balance
        self.assertEqual(c_cancel["partial_fill_component_bps"], 0.0)
        self.assertGreater(c_cross["partial_fill_component_bps"], 0.0)
        self.assertLess(c_cancel["total_expected_cost_bps"], c_cross["total_expected_cost_bps"])


if __name__ == "__main__":
    unittest.main()

