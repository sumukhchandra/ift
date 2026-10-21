"""
Unit tests for IndiaCostEngine.
Verifies exact penny-for-penny statutory tax and brokerage decomposition.
"""

import unittest
from v2.risk import IndiaCostEngine, CostBreakdown


class TestCostEngine(unittest.TestCase):

    def setUp(self):
        self.engine = IndiaCostEngine(profit_tax_pct=0.25)

    def test_brokerage_cap(self):
        # Trade value ₹1,000 -> 0.03% = ₹0.30 (below ₹20 cap)
        self.assertAlmostEqual(self.engine.brokerage_per_side(1000.0), 0.30, places=2)

        # Trade value ₹1,00,000 -> 0.03% = ₹30.0 -> Capped at ₹20.0
        self.assertEqual(self.engine.brokerage_per_side(100000.0), 20.0)

    def test_roundtrip_cost_decomposition(self):
        # 1% gross gain on ₹5,000 capital
        breakdown = self.engine.calculate_roundtrip_cost(capital=5000.0, gross_return=0.01, slippage_bps=2.5)

        self.assertIsInstance(breakdown, CostBreakdown)
        self.assertEqual(breakdown.capital, 5000.0)
        self.assertEqual(breakdown.buy_value, 5000.0)
        self.assertEqual(breakdown.sell_value, 5050.0)

        # Brokerage = ₹1.50 (buy) + ₹1.515 (sell) = ₹3.015 -> ₹3.01 (banker's rounding)
        self.assertEqual(breakdown.brokerage, 3.01)

        # STT = 0.025% of 5050 = ₹1.26
        self.assertEqual(breakdown.stt, 1.26)

        # Total cost must match sum within 1-2 paisa rounding tolerance
        calculated_sum = round(breakdown.fixed_or_capped_cost + breakdown.proportional_statutory_cost + breakdown.slippage, 2)
        self.assertAlmostEqual(breakdown.total_cost, calculated_sum, delta=0.02)

        # Gross profit = ₹50.0
        self.assertEqual(breakdown.gross_profit, 50.0)
        self.assertTrue(breakdown.net_profit > 0)

    def test_viability_gate(self):
        # A tiny 0.02% gross move on ₹1,000 capital is NOT viable due to fees
        self.assertFalse(self.engine.is_trade_viable(capital=1000.0, predicted_gross_return=0.0002))

        # A 0.5% gross move on ₹50,000 is viable
        self.assertTrue(self.engine.is_trade_viable(capital=50000.0, predicted_gross_return=0.005))


if __name__ == "__main__":
    unittest.main()
