"""
Abstract Market Data Provider Base Class.
Decouples data ingestion from specific transport mechanisms (REST, WebSocket, Replay, Mock).
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Callable
from .schema import Bar


class MarketDataProvider(ABC):
    """Abstract interface for all market data ingestion sources."""

    @abstractmethod
    def get_latest_bar(self, symbol: str) -> Optional[Bar]:
        """Return the most recently finalized candle bar for the given symbol."""
        pass

    @abstractmethod
    def get_history(self, symbol: str, count: int) -> List[Bar]:
        """Return the recent N closed candle bars for the given symbol."""
        pass

    @abstractmethod
    def subscribe_bars(self, callback: Callable[[Bar], None]) -> None:
        """Register a callback to receive newly closed bars in real-time or replay."""
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """Return True if the data connection is alive and data is fresh."""
        pass
