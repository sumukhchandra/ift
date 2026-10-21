"""
Historical Replay Adapter.
Feeds recorded historical bars into the MarketDataProvider interface chronologically.
"""

from typing import List, Optional, Callable, Dict
from datetime import datetime
from ..schema import Bar
from ..provider_base import MarketDataProvider


class HistoricalReplayAdapter(MarketDataProvider):
    """
    Adapter that replays stored historical bars.
    Maintains chronological ordering and supports event subscription.
    """

    def __init__(self, bars: List[Bar]):
        # Sort bars chronologically
        self._bars = sorted(bars, key=lambda b: b.timestamp)
        self._cursor = 0
        self._symbol_history: Dict[str, List[Bar]] = {}
        self._latest_bars: Dict[str, Bar] = {}
        self._subscribers: List[Callable[[Bar], None]] = []

    def get_latest_bar(self, symbol: str) -> Optional[Bar]:
        return self._latest_bars.get(symbol)

    def get_history(self, symbol: str, count: int) -> List[Bar]:
        hist = self._symbol_history.get(symbol, [])
        return hist[-count:] if count > 0 else []

    def subscribe_bars(self, callback: Callable[[Bar], None]) -> None:
        self._subscribers.append(callback)

    def is_healthy(self) -> bool:
        return True

    def has_next(self) -> bool:
        return self._cursor < len(self._bars)

    def step(self) -> Optional[Bar]:
        """Advance one bar forward in the historical dataset."""
        if not self.has_next():
            return None

        bar = self._bars[self._cursor]
        self._cursor += 1

        self._latest_bars[bar.symbol] = bar
        if bar.symbol not in self._symbol_history:
            self._symbol_history[bar.symbol] = []
        self._symbol_history[bar.symbol].append(bar)

        for sub in self._subscribers:
            sub(bar)

        return bar

    def reset(self) -> None:
        self._cursor = 0
        self._symbol_history.clear()
        self._latest_bars.clear()

    @classmethod
    def from_parquet(cls, filepath: str, symbols: Optional[List[str]] = None) -> "HistoricalReplayAdapter":
        """Load bars from a standardized parquet file."""
        import pandas as pd
        df = pd.read_parquet(filepath)
        if symbols is not None:
            df = df[df["symbol"].isin(symbols)]
        
        bars = []
        for row in df.itertuples(index=False):
            ts = row.timestamp
            if hasattr(ts, "to_pydatetime"):
                ts = ts.to_pydatetime()
            bars.append(Bar(
                timestamp=ts,
                symbol=str(row.symbol),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume)
            ))
        return cls(bars=bars)

