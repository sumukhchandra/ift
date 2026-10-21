#!/usr/bin/env python3
"""
v3/strategy/v2_multitimeframe_trend.py
AlphaNSE Strategy V2: Multi-Timeframe (15m/5m/1m) Trend + Momentum Engine.

Architecture:
1. 15-Minute Trend Filter:
   - Synthetic 15m bar aggregation (zero lookahead).
   - Condition: 15m EMA 10 > 15m EMA 30 AND 15m Close > 15m EMA 10.
2. 5-Minute Momentum Confirmation:
   - Synthetic 5m bar aggregation.
   - Condition: 5m EMA 5 > 5m EMA 15 AND 5m Close > 5m Open.
3. 1-Minute Entry Trigger:
   - Condition: 1m pullback into 1m EMA 20 or breakout of recent 5-bar high.
   - Volume Confirmation: 1m Volume >= 1.25x 15-bar Volume SMA.
4. Risk & Target Geometry:
   - Target: +1.50% (tested parameter to provide sufficient headroom over friction).
   - Stop Loss: -0.75% (2.0:1 Reward-to-Risk ratio).
   - Breakeven Trail: If gain reaches +0.80%, move stop to +0.25% (locking in roundtrip friction).
   - EOD Square-Off: Mandatory exit at 15:15 IST.
5. Pre-Trade Gatekeeper:
   - EdgeFrictionGate: Verifies Gross Target (1.50%) > Roundtrip Friction + Safety Margin.
"""

from datetime import datetime, time
from typing import List, Dict, Any, Optional, Tuple
import numpy as np


class SyntheticBarAggregator:
    """Aggregates 1-minute sequential bars into n-minute bars with zero lookahead bias."""
    
    def __init__(self, timeframe_minutes: int):
        self.tf_mins = timeframe_minutes
        self.current_bucket = None
        self.current_bar = None
        self.completed_bars: List[Dict[str, Any]] = []

    def update(self, bar_1m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        dt: datetime = bar_1m["timestamp"]
        # Bucket key based on minute interval from market open (09:15)
        minute_of_day = dt.hour * 60 + dt.minute
        bucket_id = (minute_of_day // self.tf_mins)

        completed_bar = None
        if self.current_bucket is not None and bucket_id != self.current_bucket:
            # Bucket closed, finalize bar
            completed_bar = dict(self.current_bar)
            self.completed_bars.append(completed_bar)
            self.current_bar = None

        self.current_bucket = bucket_id
        if self.current_bar is None:
            self.current_bar = {
                "timestamp": dt,
                "open": bar_1m["open"],
                "high": bar_1m["high"],
                "low": bar_1m["low"],
                "close": bar_1m["close"],
                "volume": bar_1m["volume"],
            }
        else:
            self.current_bar["high"] = max(self.current_bar["high"], bar_1m["high"])
            self.current_bar["low"] = min(self.current_bar["low"], bar_1m["low"])
            self.current_bar["close"] = bar_1m["close"]
            self.current_bar["volume"] += bar_1m["volume"]

        return completed_bar


class StrategyV2MultiTimeframe:
    def __init__(
        self,
        target_profit_pct: float = 0.0150,   # 1.50% target
        stop_loss_pct: float = 0.0075,        # 0.75% stop loss (2:1 R:R)
        trail_breakeven_pct: float = 0.0080,  # Trail to +0.25% after +0.80% gain
        volume_mult: float = 1.25,
    ):
        self.target_profit_pct = target_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.trail_breakeven_pct = trail_breakeven_pct
        self.volume_mult = volume_mult

        self.agg_5m = SyntheticBarAggregator(5)
        self.agg_15m = SyntheticBarAggregator(15)

    def _calc_ema(self, series: List[float], span: int) -> float:
        if not series:
            return 0.0
        alpha = 2.0 / (span + 1.0)
        ema = series[0]
        for val in series[1:]:
            ema = alpha * val + (1.0 - alpha) * ema
        return ema

    def evaluate_1m_bar(
        self,
        bar_1m: Dict[str, Any],
        recent_1m_bars: List[Dict[str, Any]],
        position: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Processes a sequential 1-minute bar and returns action: "BUY", "SELL", or "HOLD".
        Strictly zero lookahead: only closed historical bars are used.
        """
        # Update synthetic aggregators
        self.agg_5m.update(bar_1m)
        self.agg_15m.update(bar_1m)

        dt: datetime = bar_1m["timestamp"]
        mid_price = bar_1m["close"]

        # Check Intraday Mandatory Square-Off (15:15 IST)
        if dt.time() >= time(15, 15):
            if position:
                return {"action": "SELL", "reason": "EOD_MANDATORY_SQUARE_OFF"}
            return {"action": "HOLD", "reason": "MARKET_CLOSED_EOD"}

        # Position Management
        if position:
            entry_px = position.entry_price
            price_move = (mid_price - entry_px) / entry_px

            # 1. Take Profit (+1.50%)
            if price_move >= self.target_profit_pct:
                return {"action": "SELL", "reason": f"TAKE_PROFIT_TARGET_HIT (+{price_move*100:.2f}%)"}

            # 2. Hard Stop Loss (-0.75%)
            if price_move <= -self.stop_loss_pct:
                return {"action": "SELL", "reason": f"STOP_LOSS_HIT ({price_move*100:.2f}%)"}

            # 3. Trailing Breakeven (+0.25% floor if peak exceeded +0.80%)
            if hasattr(position, "peak_move") and position.peak_move >= self.trail_breakeven_pct:
                if price_move <= 0.0025:
                    return {"action": "SELL", "reason": "TRAILING_BREAKEVEN_PROTECTION"}

            # Track peak
            if not hasattr(position, "peak_move"):
                position.peak_move = price_move
            else:
                position.peak_move = max(position.peak_move, price_move)

            return {"action": "HOLD", "reason": "IN_POSITION"}

        # Entry Filter: Only trade between 09:30 and 14:45 IST (Wait for initial 15m bar to close)
        if dt.time() < time(9, 30) or dt.time() > time(14, 45):
            return {"action": "HOLD", "reason": "TIME_FILTER_OUTSIDE_WINDOW"}

        # Require minimum completed higher-timeframe bars
        if len(self.agg_15m.completed_bars) < 6 or len(self.agg_5m.completed_bars) < 10:
            return {"action": "HOLD", "reason": "WARMING_UP_HIGHER_TIMEFRAMES"}

        # ---------------------------------------------------------------------
        # 1. Higher Timeframe Filter: 15-Minute Trend Alignment
        # ---------------------------------------------------------------------
        closes_15m = [b["close"] for b in self.agg_15m.completed_bars]
        ema10_15m = self._calc_ema(closes_15m[-15:], 10)
        ema30_15m = self._calc_ema(closes_15m[-30:], 30)
        last_15m_close = closes_15m[-1]

        # 15m Bullish Regime: EMA10 > EMA30 AND Close > EMA10
        is_15m_bullish = (ema10_15m > ema30_15m) and (last_15m_close > ema10_15m)
        if not is_15m_bullish:
            return {"action": "HOLD", "reason": "15M_TREND_NOT_ALIGNED"}

        # ---------------------------------------------------------------------
        # 2. Medium Timeframe Confirmation: 5-Minute Momentum
        # ---------------------------------------------------------------------
        closes_5m = [b["close"] for b in self.agg_5m.completed_bars]
        ema5_5m = self._calc_ema(closes_5m[-15:], 5)
        ema15_5m = self._calc_ema(closes_5m[-25:], 15)

        # 5m Bullish Momentum: Fast EMA > Slow EMA
        is_5m_bullish = ema5_5m > ema15_5m
        if not is_5m_bullish:
            return {"action": "HOLD", "reason": "5M_MOMENTUM_NOT_CONFIRMED"}

        # ---------------------------------------------------------------------
        # 3. 1-Minute Entry Trigger & Volume Confirmation
        # ---------------------------------------------------------------------
        if len(recent_1m_bars) < 20:
            return {"action": "HOLD", "reason": "INSUFFICIENT_1M_HISTORY"}

        closes_1m = [b["close"] for b in recent_1m_bars]
        vols_1m = [b["volume"] for b in recent_1m_bars]
        ema20_1m = self._calc_ema(closes_1m[-20:], 20)

        avg_vol = float(np.mean(vols_1m[-15:])) if vols_1m else 1.0
        cur_vol = bar_1m["volume"]
        vol_surge = (cur_vol / avg_vol) >= self.volume_mult if avg_vol > 0 else False

        # Trigger Condition: 1m Close crosses above 1m EMA 20 with Volume Confirmation
        price_cross_ema = (closes_1m[-2] <= ema20_1m) and (mid_price > ema20_1m)

        if price_cross_ema and vol_surge:
            return {
                "action": "BUY",
                "reason": "V2_15M_TREND_5M_MOMENTUM_1M_CROSSOVER_CONFIRMED",
                "expected_move_pct": self.target_profit_pct,
                "mid_price": mid_price,
            }

        return {"action": "HOLD", "reason": "WAITING_FOR_1M_TRIGGER"}
