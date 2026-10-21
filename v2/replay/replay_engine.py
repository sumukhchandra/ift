"""
Event-Driven Replay Engine.
Coordinates chronological bar stepping, clock updates, and strategy listener notification.
"""

from typing import List, Callable, Optional
from ..data.schema import Bar
from ..data.adapters.replay_adapter import HistoricalReplayAdapter
from .as_of_clock import AsOfClock


class ReplayEngine:
    """
    Simulates real-time market data arrival by playing back historical bars.
    Guarantees that at every step T, the AsOfClock is at T and all downstream components
    receive events strictly in chronological sequence.
    """

    def __init__(self, adapter: HistoricalReplayAdapter):
        self._adapter = adapter
        self._clock = AsOfClock()
        self._listeners: List[Callable[[Bar, AsOfClock], None]] = []

    @property
    def clock(self) -> AsOfClock:
        return self._clock

    def add_listener(self, callback: Callable[[Bar, AsOfClock], None]) -> None:
        self._listeners.append(callback)

    def step(self) -> Optional[Bar]:
        bar = self._adapter.step()
        if bar is not None:
            self._clock.set_time(bar.timestamp)
            for listener in self._listeners:
                listener(bar, self._clock)
        return bar

    def run_all(self) -> int:
        """Run through all available historical bars. Returns total steps executed."""
        count = 0
        while self._adapter.has_next():
            bar = self.step()
            if bar:
                count += 1
        return count
