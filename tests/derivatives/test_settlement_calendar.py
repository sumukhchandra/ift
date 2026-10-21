"""
Unit Tests for NSE Settlement Calendar & Expiry Rules.
Validates Tuesday expiry rule and previous-day holiday adjustments.
"""

import unittest
from datetime import date
from v2.derivatives.settlement_calendar import NSESettlementCalendar


class TestNSESettlementCalendar(unittest.TestCase):

    def setUp(self):
        self.cal = NSESettlementCalendar()

    def test_last_tuesday_calculation(self):
        """Test finding the last Tuesday of various months."""
        # September 2026: Tuesdays are 1, 8, 15, 22, 29. Last is Sept 29.
        tue_sep26 = self.cal.get_last_tuesday_of_month(2026, 9)
        self.assertEqual(tue_sep26, date(2026, 9, 29))
        self.assertEqual(tue_sep26.weekday(), 1)  # 1 = Tuesday

        # October 2026: Tuesdays are 6, 13, 20, 27. Last is Oct 27.
        tue_oct26 = self.cal.get_last_tuesday_of_month(2026, 10)
        self.assertEqual(tue_oct26, date(2026, 10, 27))
        self.assertEqual(tue_oct26.weekday(), 1)

    def test_monthly_expiry_regular(self):
        """When the last Tuesday is a trading day, it is the expiry day."""
        exp_sep26 = self.cal.get_monthly_expiry(2026, 9)
        self.assertEqual(exp_sep26, date(2026, 9, 29))
        self.assertTrue(self.cal.is_trading_day(exp_sep26))

    def test_monthly_expiry_holiday_adjustment(self):
        """
        When the last Tuesday is an exchange holiday, expiry moves to previous trading day.
        """
        # Create a mock calendar with a holiday on Tuesday Sep 29, 2026
        mock_holidays = {date(2026, 9, 29)}
        mock_cal = NSESettlementCalendar(holidays=mock_holidays)

        exp = mock_cal.get_monthly_expiry(2026, 9)
        # Previous trading day before Tuesday Sept 29 is Monday Sept 28
        self.assertEqual(exp, date(2026, 9, 28))
        self.assertEqual(exp.weekday(), 0)  # Monday

    def test_active_contract_expiries_cycle(self):
        """Test resolution of near, next, and far month contract expiries."""
        as_of = date(2026, 9, 15)
        expiries = self.cal.get_active_contract_expiries(as_of)
        
        self.assertIn("near_month", expiries)
        self.assertIn("next_month", expiries)
        self.assertIn("far_month", expiries)

        self.assertEqual(expiries["near_month"], date(2026, 9, 29))
        self.assertEqual(expiries["next_month"], date(2026, 10, 27))
        self.assertTrue(expiries["near_month"] < expiries["next_month"] < expiries["far_month"])

    def test_expiry_past_current_date(self):
        """When current date is past the month's expiry, near month shifts to next month."""
        as_of = date(2026, 9, 30)  # Day after Sept 29 expiry
        expiries = self.cal.get_active_contract_expiries(as_of)
        self.assertEqual(expiries["near_month"], date(2026, 10, 27))


if __name__ == "__main__":
    unittest.main()
