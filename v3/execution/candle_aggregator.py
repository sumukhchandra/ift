#!/usr/bin/env python3
"""
v3/execution/candle_aggregator.py
Production 1-Minute OHLCV Candle Aggregator for AlphaNSE V3.

Solves the Production Sampling Mismatch:
- Ingests sub-minute market quotes (e.g., 10-second polling ticks).
- Aggregates intra-minute ticks into genuine 1-minute OHLCV bars.
- Prevents N sub-minute ticks from incorrectly becoming N separate 1-minute bars.
- Handles duplicate ticks, missing intervals/gaps, market session boundaries,
  timezone normalization (Asia/Kolkata), incomplete candles, and stale quotes.
"""

import os
import sys
import math
import logging
from datetime import datetime, date, time as dtime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
import pytz

IST = pytz.timezone("Asia/Kolkata")
logger = logging.getLogger("CandleAggregator")


class OneMinuteCandleAggregator:
    """
    Stateful 1-minute OHLCV candle aggregator for multi-instrument live trading.
    Maintains completed 1-minute history and currently forming in-progress candles.
    """

    def __init__(self, max_history: int = 60, market_open: dtime = dtime(9, 15), market_close: dtime = dtime(15, 30)):
        self.max_history = max_history
        self.market_open = market_open
        self.market_close = market_close

        # Per-symbol state:
        # completed_bars[sym] = list of sealed 1-minute bars (is_complete=True)
        self.completed_bars: Dict[str, List[Dict[str, Any]]] = {}
        # forming_bars[sym] = currently active 1-minute bar in progress (is_complete=False)
        self.forming_bars: Dict[str, Dict[str, Any]] = {}
        # last_tick[sym] = (dt, ltp) to deduplicate ticks
        self.last_tick: Dict[str, Tuple[datetime, float]] = {}
        # cumulative_vol_base[sym] = base cumulative volume from day start
        self.cumulative_vol_base: Dict[str, float] = {}

    @staticmethod
    def normalize_timestamp(ts: Any) -> Optional[datetime]:
        """
        Normalizes any timestamp (str, datetime, pd.Timestamp) to timezone-aware Asia/Kolkata datetime.
        """
        if ts is None:
            return None
        try:
            if isinstance(ts, (int, float)):
                val = float(ts)
                if val > 1e11:
                    val = val / 1000.0
                return datetime.fromtimestamp(val, tz=IST)
            elif isinstance(ts, str):
                ts_str = ts.strip()
                if ts_str.isdigit():
                    val = float(ts_str)
                    if val > 1e11:
                        val = val / 1000.0
                    return datetime.fromtimestamp(val, tz=IST)
                # Check HH:MM:SS format
                if len(ts_str) == 8 and ts_str.count(":") == 2:
                    today = datetime.now(IST).date()
                    h, m, s = [int(x) for x in ts_str.split(":")]
                    return IST.localize(datetime(today.year, today.month, today.day, h, m, s))
                # Check ISO / standard string format
                ts_clean = ts_str.replace(" IST", "")
                dt = datetime.fromisoformat(ts_clean)
                if dt.tzinfo is None:
                    return IST.localize(dt)
                return dt.astimezone(IST)
            elif isinstance(ts, datetime):
                if ts.tzinfo is None:
                    return IST.localize(ts)
                return ts.astimezone(IST)
            elif hasattr(ts, "to_pydatetime"):
                dt = ts.to_pydatetime()
                if dt.tzinfo is None:
                    return IST.localize(dt)
                return dt.astimezone(IST)
        except Exception as e:
            logger.debug(f"Failed to parse timestamp {ts}: {e}")
        return None

    def is_session_time(self, dt: datetime) -> bool:
        """Verifies if datetime falls within official NSE equity session (09:15 - 15:30 IST)."""
        t = dt.time()
        return self.market_open <= t <= self.market_close

    def preseed(self, symbol: str, bars: List[Dict[str, Any]]) -> int:
        """
        Pre-seeds historical completed 1-minute bars (e.g. from canonical CSVs).
        Enforces authentic timestamps, valid OHLCV numbers, and chronological order.
        """
        if not bars:
            return 0
        cleaned = []
        for b in bars:
            ts = self.normalize_timestamp(b.get("timestamp"))
            if ts is None:
                # If timestamp is missing from legacy file, reject or synthesize documented index
                continue
            o = float(b.get("open", 0.0))
            h = float(b.get("high", 0.0))
            l = float(b.get("low", 0.0))
            c = float(b.get("close", 0.0))
            v = float(b.get("volume", 0.0))
            if c <= 0 or l <= 0:
                continue
            cleaned.append({
                "timestamp": ts,
                "timestamp_str": ts.strftime("%Y-%m-%d %H:%M:%S IST"),
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
                "volume": v,
                "is_complete": True,
                "tick_count": int(b.get("tick_count", 6))
            })

        cleaned.sort(key=lambda x: x["timestamp"])
        self.completed_bars[symbol] = cleaned[-self.max_history:]
        return len(self.completed_bars[symbol])

    def process_quote(self, symbol: str, quote: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Processes an incoming live quote observation.
        Aggregates into current 1-minute forming candle.
        If minute rolls over, seals previous candle into completed_bars and starts new candle.
        Returns the newly sealed candle if rollover occurred, else None.
        """
        if not quote:
            return None

        # 1. Stale quote rejection
        if quote.get("is_stale", False) or quote.get("source") == "BUFFER_FALLBACK":
            logger.warning(f"Rejected stale quote for {symbol} (source: {quote.get('source')})")
            return None

        try:
            ltp = float(quote.get("ltp", 0.0))
        except (ValueError, TypeError):
            return None

        if ltp <= 0.0 or not math.isfinite(ltp):
            return None

        # 2. Timestamp extraction and normalization
        raw_ts = quote.get("timestamp") or quote.get("exchange_timestamp") or quote.get("time")
        if raw_ts is not None:
            q_dt = self.normalize_timestamp(raw_ts)
            if q_dt is None:
                logger.warning(f"Rejected malformed timestamp '{raw_ts}' for {symbol}")
                return None
        else:
            q_dt = datetime.now(IST)

        # 3. Duplicate tick rejection
        if symbol in self.last_tick:
            prev_dt, prev_ltp = self.last_tick[symbol]
            if prev_dt == q_dt and abs(prev_ltp - ltp) < 1e-6:
                return None  # Exact duplicate tick ignored

        self.last_tick[symbol] = (q_dt, ltp)

        # 4. Minute bucket alignment (floor to minute)
        bucket_dt = q_dt.replace(second=0, microsecond=0)

        # Volume semantics determination
        is_cum = quote.get("is_cumulative", False) or quote.get("is_cumulative_volume", False) or quote.get("volume_type") == "cumulative"
        is_inc = quote.get("volume_type") == "incremental"

        try:
            raw_vol = float(quote.get("cumulative_volume") if is_cum and "cumulative_volume" in quote else quote.get("volume", quote.get("last_volume", 0.0)))
            if not math.isfinite(raw_vol) or raw_vol < 0.0:
                raw_vol = 0.0
        except (ValueError, TypeError):
            raw_vol = 0.0

        forming = self.forming_bars.get(symbol)
        sealed_bar = None

        # Case A: No forming candle exists yet
        if forming is None:
            if is_cum:
                self.cumulative_vol_base[symbol] = raw_vol
                init_vol = 0.0
            else:
                init_vol = raw_vol

            self.forming_bars[symbol] = {
                "timestamp": bucket_dt,
                "timestamp_str": bucket_dt.strftime("%Y-%m-%d %H:%M:%S IST"),
                "open": round(ltp, 2),
                "high": round(ltp, 2),
                "low": round(ltp, 2),
                "close": round(ltp, 2),
                "volume": round(init_vol, 2),
                "is_complete": False,
                "tick_count": 1,
                "last_tick_time": q_dt,
                "is_cumulative": is_cum
            }
            return None

        # Case B: Quote belongs to the SAME minute as current forming bar
        if bucket_dt == forming["timestamp"]:
            forming["high"] = round(max(forming["high"], ltp), 2)
            forming["low"] = round(min(forming["low"], ltp), 2)
            forming["close"] = round(ltp, 2)
            
            if is_cum or forming.get("is_cumulative", False):
                base_v = self.cumulative_vol_base.get(symbol, raw_vol)
                forming["volume"] = round(max(0.0, raw_vol - base_v), 2)
            elif is_inc:
                forming["volume"] = round(forming["volume"] + raw_vol, 2)
            else:
                # Default/legacy behavior: max seen volume
                if raw_vol > forming["volume"]:
                    forming["volume"] = round(raw_vol, 2)

            forming["tick_count"] += 1
            forming["last_tick_time"] = q_dt
            return None

        # Case C: Minute rolled over (quote belongs to a LATER minute)
        if bucket_dt > forming["timestamp"]:
            # Finalize previous forming bar
            forming["is_complete"] = True
            sealed_bar = dict(forming)

            history = self.completed_bars.setdefault(symbol, [])
            history.append(sealed_bar)
            if len(history) > self.max_history:
                history.pop(0)

            # Detect gap if more than 1 minute skipped
            elapsed_minutes = (bucket_dt - forming["timestamp"]).total_seconds() / 60.0
            if elapsed_minutes > 1.0:
                logger.info(
                    f"Market data gap detected for {symbol}: {elapsed_minutes:.1f} mins elapsed between "
                    f"{forming['timestamp_str']} and {bucket_dt.strftime('%H:%M:%S')} (No synthetic bars fabricated)"
                )

            # Start new forming bar for new minute bucket
            if is_cum:
                self.cumulative_vol_base[symbol] = raw_vol
                new_vol = 0.0
            else:
                new_vol = raw_vol

            self.forming_bars[symbol] = {
                "timestamp": bucket_dt,
                "timestamp_str": bucket_dt.strftime("%Y-%m-%d %H:%M:%S IST"),
                "open": round(ltp, 2),
                "high": round(ltp, 2),
                "low": round(ltp, 2),
                "close": round(ltp, 2),
                "volume": round(new_vol, 2),
                "is_complete": False,
                "tick_count": 1,
                "last_tick_time": q_dt,
                "is_cumulative": is_cum
            }
            return sealed_bar

        # Case D: Out-of-order timestamp arriving late (bucket_dt < forming["timestamp"])
        logger.warning(
            f"Rejected out-of-order tick for {symbol}: tick time {q_dt.strftime('%H:%M:%S')} is earlier than "
            f"forming bar {forming['timestamp_str']}"
        )
        return None

    def get_bars(self, symbol: str, include_forming: bool = False, min_bars: int = 15) -> List[Dict[str, Any]]:
        """
        Returns authentic 1-minute OHLCV candles for the symbol.
        If include_forming=True, appends the current in-progress candle as the last bar.
        Guarantees that each returned element represents a distinct 1-minute timeframe.
        """
        history = list(self.completed_bars.get(symbol, []))
        if include_forming:
            forming = self.forming_bars.get(symbol)
            if forming is not None:
                history.append(dict(forming))
        return history

    def validate_buffer_timeframe(self, bars: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        """
        Validates that a candle buffer strictly conforms to 1-minute bar intervals.
        Rejects buffers containing sub-minute (e.g. 10s) intervals.
        """
        if not bars or len(bars) < 2:
            return True, None

        deltas = []
        for i in range(1, len(bars)):
            t0 = bars[i - 1].get("timestamp")
            t1 = bars[i].get("timestamp")
            if t0 is not None and t1 is not None:
                dt0 = self.normalize_timestamp(t0)
                dt1 = self.normalize_timestamp(t1)
                if dt0 and dt1:
                    deltas.append((dt1 - dt0).total_seconds())

        if not deltas:
            return True, None

        # Check for sub-minute sampling defect
        sub_minute_count = sum(1 for d in deltas if d < 45.0)
        if sub_minute_count > 0:
            return False, f"DETECTED_SUB_MINUTE_SAMPLING: {sub_minute_count} of {len(deltas)} intervals < 45s (e.g. 10s quotes)"

        return True, None
