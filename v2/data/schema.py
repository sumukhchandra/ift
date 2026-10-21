"""
Standard Data Schemas for AlphaNSE V2.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Bar:
    """Standardized OHLCV candle bar."""
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self):
        if self.high < self.low:
            raise ValueError(f"Bar high ({self.high}) cannot be less than low ({self.low})")
        if self.volume < 0:
            raise ValueError(f"Volume cannot be negative: {self.volume}")
        if self.close <= 0 or self.open <= 0:
            raise ValueError(f"Prices must be positive. Open: {self.open}, Close: {self.close}")

    @property
    def typical_price(self) -> float:
        return (self.high + self.low + self.close) / 3.0

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def return_pct(self) -> float:
        return (self.close - self.open) / self.open if self.open > 0 else 0.0


@dataclass(frozen=True)
class Tick:
    """Real-time market tick."""
    timestamp: datetime
    symbol: str
    price: float
    volume: float
    bid: Optional[float] = None
    ask: Optional[float] = None


@dataclass
class DataQualityReport:
    symbol: str
    total_bars: int
    missing_bars: int = 0
    duplicate_bars: int = 0
    out_of_order_bars: int = 0
    zero_volume_bars: int = 0
    is_acceptable: bool = True
