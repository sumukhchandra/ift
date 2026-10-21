"""
Unit tests for Risk-Based Integer Position Sizing.
Verifies integer whole share quantities and elimination of arbitrary single-share price caps.
"""

import unittest
from v2.risk import IntegerPositionSizer, SizingResult


class TestIntegerPositionSizing(unittest.TestCase):

    def setUp(self):
        self.sizer = IntegerPositionSizer(
            max_risk_per_trade_pct=0.01,       # 1.0% portfolio risk
            max_position_allocation_pct=0.25,  # 25% allocation cap
            atr_stop_multiplier=1.5,
            min_stop_loss_pct=0.003
        )

    def test_whole_shares_on_tatacap(self):
        # ₹5,000 capital, price ₹350, ATR ₹1.50
        # Stop distance = max(1.5 * 1.5, 350 * 0.003) = max(2.25, 1.05) = 2.25
        # Risk budget = 5000 * 0.01 = ₹50.0
        # Q_risk = floor(50 / 2.25) = 22 shares
        # Allocation budget = 5000 * 0.25 = ₹1250
        # Q_alloc = floor(1250 / 350) = 3 shares
        # Final Q = min(22, 3) = 3 shares
        res = self.sizer.calculate_size(
            total_capital=5000.0,
            available_capital=5000.0,
            current_price=350.0,
            atr=1.50
        )
        self.assertTrue(res.is_viable)
        self.assertIsInstance(res.qty, int)
        self.assertEqual(res.qty, 3)
        self.assertAlmostEqual(res.total_cost, 1050.0)
        self.assertTrue(res.total_cost <= 1250.0)

    def test_elimination_of_arbitrary_price_cap_on_tcs(self):
        """
        V1 hard-blocked TCS (₹2,118) on ₹5k capital because price > ₹1,250.
        V2 evaluates economic feasibility: 
        If available capital is ₹5,000 and stop distance risk <= risk budget, 1 share is permitted.
        """
        # ₹10,000 capital, available ₹10,000, price ₹2,118, tight ATR ₹10.0
        # Stop distance = 15.0. Risk budget = ₹100.
        # 1 share risk = ₹15.0 <= ₹100. Price ₹2,118 <= ₹10,000.
        res = self.sizer.calculate_size(
            total_capital=10000.0,
            available_capital=10000.0,
            current_price=2118.0,
            atr=10.0
        )
        self.assertTrue(res.is_viable)
        self.assertEqual(res.qty, 1)
        self.assertEqual(res.total_cost, 2118.0)

    def test_economic_rejection_when_cash_insufficient(self):
        # Available capital is only ₹1,000, stock price is ₹2,118
        res = self.sizer.calculate_size(
            total_capital=5000.0,
            available_capital=1000.0,
            current_price=2118.0,
            atr=10.0
        )
        self.assertFalse(res.is_viable)
        self.assertEqual(res.qty, 0)
        self.assertIn("insufficient", res.reason.lower())


if __name__ == "__main__":
    unittest.main()
