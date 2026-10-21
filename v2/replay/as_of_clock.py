"""
Point-in-Time As-Of Clock.
Enforces strict no-lookahead invariants: data_as_of <= current_time.
"""

from datetime import datetime
from typing import Optional


class LookaheadViolationError(Exception):
    """Raised when an attempt is made to access data from the future."""
    pass


class AsOfClock:
    """
    Deterministic clock for replay, backtesting, and live simulation.
    Ensures that features, models, and execution decisions cannot access future bars.
    """

    def __init__(self, start_time: Optional[datetime] = None):
        self._current_time: Optional[datetime] = start_time

    @property
    def current_time(self) -> Optional[datetime]:
        return self._current_time

    def set_time(self, t: datetime) -> None:
        if self._current_time is not None and t < self._current_time:
            raise ValueError(f"Clock cannot move backward: current={self._current_time}, target={t}")
        self._current_time = t

    def assert_accessible(self, data_timestamp: datetime) -> None:
        """
        Verify that data timestamp is accessible at the current simulated time.
        Raises LookaheadViolationError if data_timestamp > current_time.
        """
        if self._current_time is None:
            raise ValueError("AsOfClock current_time is not set.")
        if data_timestamp > self._current_time:
            raise LookaheadViolationError(
                f"Lookahead violation detected: data timestamp ({data_timestamp}) is in the future relative to current time ({self._current_time})"
            )
