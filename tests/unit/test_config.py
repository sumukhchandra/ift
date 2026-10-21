"""
Unit tests for AlphaNSE V2 Configuration System.
"""

import unittest
from datetime import time
from v2.config import load_config, AppConfig, MarketHoursConfig, RiskConfig


class TestConfig(unittest.TestCase):

    def test_default_config_loads_valid(self):
        cfg = load_config(environment="RESEARCH", starting_capital=5000.0)
        self.assertIsInstance(cfg, AppConfig)
        self.assertEqual(cfg.environment, "RESEARCH")
        self.assertEqual(cfg.starting_capital, 5000.0)
        self.assertIn(len(cfg.universe.symbols), (10, 11))

    def test_market_hours_validation(self):
        mkt = MarketHoursConfig()
        # 09:00 is pre-market
        self.assertFalse(mkt.is_market_open(time(9, 0)))
        # 09:15 is open
        self.assertTrue(mkt.is_market_open(time(9, 15)))
        # 12:00 is open
        self.assertTrue(mkt.is_market_open(time(12, 0)))
        # 15:30 is market close boundary
        self.assertTrue(mkt.is_market_open(time(15, 30)))
        # 15:31 is after market
        self.assertFalse(mkt.is_market_open(time(15, 31)))

        # Opening cooloff (first 5 mins: 09:15-09:20)
        self.assertTrue(mkt.is_opening_cooloff(time(9, 16)))
        self.assertFalse(mkt.is_opening_cooloff(time(9, 21)))

    def test_risk_config_bounds(self):
        risk = RiskConfig()
        self.assertEqual(risk.max_daily_loss_pct, 0.02)
        self.assertEqual(risk.max_risk_per_trade_pct, 0.01)
        self.assertEqual(risk.max_open_positions, 5)

    def test_invalid_config_raises(self):
        with self.assertRaises(ValueError):
            load_config(starting_capital=-100)


if __name__ == "__main__":
    unittest.main()
