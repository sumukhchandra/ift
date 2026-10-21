"""
Unit tests for Portfolio Circuit Breakers and Drawdown Halts.
"""

import unittest
from v2.risk import PortfolioCircuitBreaker
from v2.risk.circuit_breakers import CircuitBreakerTrippedError


class TestCircuitBreakers(unittest.TestCase):

    def test_circuit_breaker_trips_on_loss_limit(self):
        cb = PortfolioCircuitBreaker(starting_daily_capital=5000.0, max_daily_loss_pct=0.02)
        # Max loss = ₹100.0 (2.0%)
        self.assertFalse(cb.is_tripped)
        cb.assert_trading_permitted()

        # Record ₹50 loss (1.0%)
        cb.record_loss(50.0)
        self.assertFalse(cb.is_tripped)
        cb.assert_trading_permitted()

        # Record another ₹60 loss (total ₹110 > ₹100)
        cb.record_loss(60.0)
        self.assertTrue(cb.is_tripped)
        self.assertIsNotNone(cb.trip_reason)

        # Assert trading permitted must now raise CircuitBreakerTrippedError
        with self.assertRaises(CircuitBreakerTrippedError):
            cb.assert_trading_permitted()

    def test_circuit_breaker_resets_for_new_day(self):
        cb = PortfolioCircuitBreaker(starting_daily_capital=5000.0, max_daily_loss_pct=0.02)
        cb.record_loss(120.0)
        self.assertTrue(cb.is_tripped)

        # New morning session with capital ₹4,880
        cb.reset_for_new_session(4880.0)
        self.assertFalse(cb.is_tripped)
        cb.assert_trading_permitted()


if __name__ == "__main__":
    unittest.main()
