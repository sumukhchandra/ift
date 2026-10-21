"""
NSE Settlement Calendar & Expiry Calculation Module.
Implements the current NSE equity derivatives contract specification:
- Expiry Day: Tuesday of the expiry period (last Tuesday of the expiry month).
- Holiday Adjustment: When the Tuesday is a trading holiday, the previous trading day is used.
- Cycle: 3-month contract cycle (Near Month, Next Month, Far Month).
"""

from datetime import date, timedelta
from typing import List, Set, Optional, Dict
import calendar


# Standard NSE Trading Holidays for 2026 (Exchange Communication & Gazette)
NSE_HOLIDAYS_2026: Set[date] = {
    date(2026, 1, 26),   # Republic Day
    date(2026, 2, 17),   # Mahashivratri
    date(2026, 3, 3),    # Holi
    date(2026, 3, 20),   # Id-ul-Fitr (subject to moon)
    date(2026, 3, 27),   # Ram Navami
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 5, 27),   # Bakri Id
    date(2026, 6, 26),   # Muharram
    date(2026, 8, 15),   # Independence Day (Saturday)
    date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    date(2026, 10, 20),  # Dussehra
    date(2026, 11, 8),   # Diwali Laxmi Pujan (Sunday - Muhurat Trading)
    date(2026, 11, 10),  # Diwali Balipratipada
    date(2026, 11, 24),  # Gurunanak Jayanti
    date(2026, 12, 25),  # Christmas
}


class NSESettlementCalendar:
    """
    Calculates settlement dates and expiry milestones for NSE stock futures.
    Follows NSE rules: Last Tuesday of the month, shifted to previous trading day if holiday.
    """

    def __init__(self, holidays: Optional[Set[date]] = None):
        self.holidays: Set[date] = set(holidays) if holidays is not None else set(NSE_HOLIDAYS_2026)

    def is_trading_day(self, d: date) -> bool:
        """A trading day is Monday-Friday and not an exchange holiday."""
        if d.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
        return d not in self.holidays

    def get_previous_trading_day(self, d: date) -> date:
        """Returns the immediately preceding open NSE trading day."""
        curr = d - timedelta(days=1)
        while not self.is_trading_day(curr):
            curr -= timedelta(days=1)
        return curr

    def get_last_tuesday_of_month(self, year: int, month: int) -> date:
        """Finds the last calendar Tuesday in the given year and month."""
        # Get the number of days in the month
        _, last_day = calendar.monthrange(year, month)
        d = date(year, month, last_day)
        # Tuesday is weekday 1 (Monday is 0, Sunday is 6)
        while d.weekday() != 1:
            d -= timedelta(days=1)
        return d

    def get_monthly_expiry(self, year: int, month: int) -> date:
        """
        Computes the final settlement expiry date for stock futures for a given month.
        Rule: Last Tuesday of the month; if that day is an exchange holiday,
        the expiry is advanced to the previous trading day.
        """
        last_tuesday = self.get_last_tuesday_of_month(year, month)
        if self.is_trading_day(last_tuesday):
            return last_tuesday
        # Advance to previous trading day
        return self.get_previous_trading_day(last_tuesday)

    def get_active_contract_expiries(self, as_of_date: date) -> Dict[str, date]:
        """
        Returns near-month, next-month, and far-month expiry dates as of a given date.
        If the near-month expiry has already passed as of the date, advances the cycle.
        """
        near_expiry = self.get_monthly_expiry(as_of_date.year, as_of_date.month)
        if as_of_date > near_expiry:
            # Shift forward by 1 month for near
            month1 = as_of_date.month + 1
            year1 = as_of_date.year
            if month1 > 12:
                month1 = 1
                year1 += 1
            near_expiry = self.get_monthly_expiry(year1, month1)
            
            month2 = month1 + 1
            year2 = year1
            if month2 > 12:
                month2 = 1
                year2 += 1
            next_expiry = self.get_monthly_expiry(year2, month2)
            
            month3 = month2 + 1
            year3 = year2
            if month3 > 12:
                month3 = 1
                year3 += 1
            far_expiry = self.get_monthly_expiry(year3, month3)
        else:
            # Current month is near month
            month2 = as_of_date.month + 1
            year2 = as_of_date.year
            if month2 > 12:
                month2 = 1
                year2 += 1
            next_expiry = self.get_monthly_expiry(year2, month2)

            month3 = month2 + 1
            year3 = year2
            if month3 > 12:
                month3 = 1
                year3 += 1
            far_expiry = self.get_monthly_expiry(year3, month3)

        return {
            "near_month": near_expiry,
            "next_month": next_expiry,
            "far_month": far_expiry,
        }

    def calendar_days_to_expiry(self, current_date: date, expiry_date: date) -> int:
        """Returns calendar days remaining until expiry."""
        return max(0, (expiry_date - current_date).days)

    def trading_days_to_expiry(self, current_date: date, expiry_date: date) -> int:
        """Returns the count of trading sessions remaining between current_date and expiry_date."""
        if current_date >= expiry_date:
            return 0
        count = 0
        curr = current_date + timedelta(days=1)
        while curr <= expiry_date:
            if self.is_trading_day(curr):
                count += 1
            curr += timedelta(days=1)
        return count
