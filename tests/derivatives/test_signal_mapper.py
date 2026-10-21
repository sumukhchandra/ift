"""
Unit Tests for Cash-to-Futures Signal Translation & Symbol Mapping.
Verifies strict symbol resolution, rejection of ineligible underlyings, and lot size constraints.
"""

import unittest
from datetime import date
from v2.derivatives.signal_mapper import (
    CashToFuturesSignalMapper,
    IneligibleForDerivativesError
)


class TestSignalMapper(unittest.TestCase):

    def setUp(self):
        self.mapper = CashToFuturesSignalMapper()

    def test_bajfinance_mapping(self):
        """Test mapping cash BAJFINANCE.NS to near-month futures contract."""
        intent = self.mapper.map_signal_to_contract(
            cash_symbol="BAJFINANCE.NS",
            predicted_return_bps=15.0,
            capital_allocated=1000000.0,  # ₹10 Lakhs capital
            as_of_date=date(2026, 9, 20),
            current_spot_price=6500.0,
            min_hurdle_bps=8.0
        )
        self.assertEqual(intent.underlying_symbol, "BAJFINANCE")
        self.assertEqual(intent.contract.symbol, "BAJFINANCE26SEPFUT")
        self.assertEqual(intent.contract.lot_size, 125)
        self.assertTrue(intent.is_tradable)
        self.assertGreaterEqual(intent.feasible_lots, 1)

    def test_tatacap_raises_ineligible_error(self):
        """
        TATACAP.NS has no F&O contract.
        Verify that mapping raises IneligibleForDerivativesError and does NOT map to TATACONSUM.
        """
        with self.assertRaises(IneligibleForDerivativesError) as ctx:
            self.mapper.map_signal_to_contract(
                cash_symbol="TATACAP.NS",
                predicted_return_bps=12.76,
                capital_allocated=1000000.0,
                as_of_date=date(2026, 9, 20),
                current_spot_price=800.0
            )
        self.assertIn("NO active F&O contract on NSE", str(ctx.exception))
        self.assertIn("TATACAP", str(ctx.exception))

    def test_rejection_when_capital_insufficient_for_lot(self):
        """
        BAJFINANCE at ₹6500 with lot size 125 requires notional ₹8,12,500.
        At 20% margin, required capital is ₹1,62,500.
        With only ₹50,000 capital, feasible_lots is 0 and trade is not tradable.
        """
        intent = self.mapper.map_signal_to_contract(
            cash_symbol="BAJFINANCE.NS",
            predicted_return_bps=20.0,
            capital_allocated=50000.0,  # ₹50k capital
            as_of_date=date(2026, 9, 20),
            current_spot_price=6500.0
        )
        self.assertFalse(intent.is_tradable)
        self.assertEqual(intent.feasible_lots, 0)
        self.assertIn("insufficient for 1 lot", intent.rejection_reason)


if __name__ == "__main__":
    unittest.main()
