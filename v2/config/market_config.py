"""
Market and Session Configuration for NSE Cash Equities.
"""

from dataclasses import dataclass, field
from datetime import time
from typing import Dict, List


@dataclass(frozen=True)
class StockMetadata:
    symbol: str
    company_name: str
    sector: str
    lot_size: int = 1
    tick_size: float = 0.05


@dataclass(frozen=True)
class MarketHoursConfig:
    market_open_time: time = time(9, 15)
    market_close_time: time = time(15, 30)
    opening_cooloff_minutes: int = 5       # 09:15-09:20 cooloff to avoid open whipsaw
    closing_sentinel_minutes: int = 30     # 15:00-15:30 closing surveillance
    timezone: str = "Asia/Kolkata"

    def is_market_open(self, t: time) -> bool:
        return self.market_open_time <= t <= self.market_close_time

    def is_opening_cooloff(self, t: time) -> bool:
        if not self.is_market_open(t):
            return False
        total_mins = (t.hour * 60 + t.minute) - (self.market_open_time.hour * 60 + self.market_open_time.minute)
        return total_mins < self.opening_cooloff_minutes


@dataclass(frozen=True)
class UniverseConfig:
    stocks: Dict[str, StockMetadata] = field(default_factory=lambda: {
        "RELIANCE.NS": StockMetadata("RELIANCE.NS", "Reliance Industries", "Energy/Retail"),
        "HDFCBANK.NS": StockMetadata("HDFCBANK.NS", "HDFC Bank", "Banking"),
        "BHARTIARTL.NS": StockMetadata("BHARTIARTL.NS", "Bharti Airtel", "Telecom"),
        "ICICIBANK.NS": StockMetadata("ICICIBANK.NS", "ICICI Bank", "Banking"),
        "TATACAP.NS": StockMetadata("TATACAP.NS", "Tata Capital", "Financial Services"),
        "INFY.NS": StockMetadata("INFY.NS", "Infosys", "Information Technology"),
        "TCS.NS": StockMetadata("TCS.NS", "TCS", "Information Technology"),
        "SBIN.NS": StockMetadata("SBIN.NS", "State Bank of India", "Banking"),
        "AXISBANK.NS": StockMetadata("AXISBANK.NS", "Axis Bank", "Banking"),
        "BAJFINANCE.NS": StockMetadata("BAJFINANCE.NS", "Bajaj Finance", "Financial Services"),
        "^NSEI": StockMetadata("^NSEI", "NIFTY 50 Index", "Index Benchmark", lot_size=1, tick_size=0.05),
    })

    @property
    def symbols(self) -> List[str]:
        return list(self.stocks.keys())
