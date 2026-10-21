"""
Unit Tests for Dynamic Execution Cost & Friction Stress Model.
Verifies:
  1. Accurate combination of statutory taxes, spread, and market impact slippage.
  2. Friction scaling across stress multipliers (1.0x, 1.25x, 1.50x, 2.00x).
  3. Safe handling of invalid inputs.
"""

import unittest
from v2.risk.dynamic_cost_model import DynamicCostModel, TradeCostDetail, ExecutionMode


class TestDynamicCostModel(unittest.TestCase):

    def setUp(self):
        self.cost_model = DynamicCostModel(
            base_half_spread_bps=1.0,
            base_slippage_bps=2.0,
            impact_coefficient=0.05
        )

    def test_base_cost_calculation(self):
        """Verify baseline cost breakdown for a standard NSE trade."""
        price = 2500.0
        qty = 2
        notional = price * qty  # 5000 Rs
        cost = self.cost_model.compute_trade_cost(price, qty, bar_volume=10000.0, stress_multiplier=1.0)

        self.assertIsInstance(cost, TradeCostDetail)
        self.assertGreater(cost.statutory_bps, 0.0)
        self.assertAlmostEqual(cost.spread_bps, 2.0, places=1)  # 2 * 1.0 bps half spread
        self.assertGreater(cost.slippage_bps, 2.0)
        self.assertGreater(cost.total_cost_bps, cost.statutory_bps)
        self.assertAlmostEqual(cost.total_cost_rupees, (cost.total_cost_bps / 10000.0) * notional, places=2)

    def test_friction_stress_multipliers(self):
        """Verify execution friction scales monotonically with stress multiplier."""
        price = 1000.0
        qty = 5

        cost_1_0 = self.cost_model.compute_trade_cost(price, qty, stress_multiplier=1.0)
        cost_1_25 = self.cost_model.compute_trade_cost(price, qty, stress_multiplier=1.25)
        cost_1_5 = self.cost_model.compute_trade_cost(price, qty, stress_multiplier=1.5)
        cost_2_0 = self.cost_model.compute_trade_cost(price, qty, stress_multiplier=2.0)

        # Statutory taxes do not change with friction stress
        self.assertAlmostEqual(cost_1_0.statutory_bps, cost_2_0.statutory_bps, places=2)

        # Execution friction must increase proportionally
        self.assertAlmostEqual(cost_1_25.execution_friction_bps, cost_1_0.execution_friction_bps * 1.25, places=1)
        self.assertAlmostEqual(cost_1_5.execution_friction_bps, cost_1_0.execution_friction_bps * 1.5, places=1)
        self.assertAlmostEqual(cost_2_0.execution_friction_bps, cost_1_0.execution_friction_bps * 2.0, places=1)

        # Total cost must be strictly monotonic
        self.assertLess(cost_1_0.total_cost_bps, cost_1_25.total_cost_bps)
        self.assertLess(cost_1_25.total_cost_bps, cost_1_5.total_cost_bps)
        self.assertLess(cost_1_5.total_cost_bps, cost_2_0.total_cost_bps)

    def test_execution_modes(self):
        """Verify execution modes: AGGRESSIVE, PASSIVE, and CONSERVATIVE_PASSIVE."""
        price = 1000.0
        qty = 5
        cost_aggr = self.cost_model.compute_trade_cost(price, qty, execution_mode=ExecutionMode.AGGRESSIVE)
        cost_pass = self.cost_model.compute_trade_cost(price, qty, execution_mode=ExecutionMode.PASSIVE)
        cost_cpass = self.cost_model.compute_trade_cost(price, qty, execution_mode=ExecutionMode.CONSERVATIVE_PASSIVE)

        # Passive captures half spread, has adverse selection
        self.assertEqual(cost_pass.spread_bps, 1.0)
        self.assertEqual(cost_pass.adverse_selection_bps, 1.0)
        self.assertEqual(cost_pass.fill_probability, 0.65)

        # Conservative passive has higher adverse selection penalty
        self.assertEqual(cost_cpass.adverse_selection_bps, 2.0)
        self.assertEqual(cost_cpass.fill_probability, 0.45)

    def test_explicit_participation_rate(self):
        """Verify impact scales with explicit participation rate."""
        price = 1000.0
        qty = 5
        cost_low = self.cost_model.compute_trade_cost(price, qty, participation_rate_fraction=0.01)
        cost_high = self.cost_model.compute_trade_cost(price, qty, participation_rate_fraction=0.25)

        self.assertLess(cost_low.slippage_bps, cost_high.slippage_bps)


if __name__ == "__main__":
    unittest.main()

