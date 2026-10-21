#!/usr/bin/env python3
"""
v3/strategy/v2_1_relative_strength_trend.py
AlphaNSE Strategy V2.1: Multi-Timeframe Trend + Relative Strength Leader Selection.

Upgrades in V2.1:
1. Strict Entry Cutoff Window (09:30 – 12:45 IST):
   - Entries only permitted between 09:30 and 12:45 IST.
   - Eliminates late-session trades that lack the 2.5-hour duration required
     for a 1.50% move to develop before the 15:15 mandatory exit.
2. Relative Strength (RS) Ranking vs Market/Day Open:
   - Measures intraday momentum: RS = (Current Price - Session Open) / Session Open.
   - Discards lagging or negative-intraday stocks (RS <= 0).
   - In cross-asset selection, ranks qualifying candidates and picks the single strongest leader.
3. 15-Minute Trend Filter:
   - 15m EMA 10 > 15m EMA 30 AND 15m Close > 15m EMA 10.
4. 5-Minute Momentum Confirmation:
   - 5m EMA 5 > 5m EMA 15.
5. 1-Minute Trigger & Volume Confirmation:
   - 1m Close crosses above 1m EMA 20 with Volume >= 1.25x 15-bar Volume SMA.
6. Target / Stop Geometry:
   - Target: +1.50% (Tested headroom over ~0.25% friction).
   - Stop Loss: -0.75% (2.0:1 Reward:Risk).
   - Trailing Breakeven: Moves stop to +0.25% if gain reaches +0.80%.
   - EOD Square-Off: 15:15 IST.
"""

from datetime import datetime, time
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from v3.strategy.v2_multitimeframe_trend import SyntheticBarAggregator


class StrategyV2_1RelativeStrength:
    def __init__(
        self,
        target_profit_pct: float = 0.0150,     # +1.50% target
        stop_loss_pct: float = 0.0075,          # -0.75% stop loss (2:1 R:R)
        trail_breakeven_pct: float = 0.0080,    # +0.80% triggers breakeven floor
        volume_mult: float = 1.25,
        entry_start: time = time(9, 30),
        entry_cutoff: time = time(12, 45),      # Hard 12:45 IST cutoff
    ):
        self.target_profit_pct = target_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.trail_breakeven_pct = trail_breakeven_pct
        self.volume_mult = volume_mult
        self.entry_start = entry_start
        self.entry_cutoff = entry_cutoff

        self.agg_5m = SyntheticBarAggregator(5)
        self.agg_15m = SyntheticBarAggregator(15)
        self.session_open_price: Optional[float] = None
        self.current_session_date = None

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
        Processes a sequential 1-minute bar and returns evaluation dictionary.
        Strictly zero lookahead: only closed historical bars are used.
        """
        self.agg_5m.update(bar_1m)
        self.agg_15m.update(bar_1m)

        dt: datetime = bar_1m["timestamp"]
        bar_date = dt.date()
        mid_price = bar_1m["close"]

        # Track session open price
        if self.current_session_date != bar_date:
            self.current_session_date = bar_date
            self.session_open_price = bar_1m["open"]

        # 1. Check Intraday Mandatory Square-Off (15:15 IST)
        if dt.time() >= time(15, 15):
            if position:
                return {"action": "SELL", "reason": "EOD_MANDATORY_SQUARE_OFF"}
            return {"action": "HOLD", "reason": "MARKET_CLOSED_EOD"}

        # 2. Position Management if Holding
        if position:
            entry_px = position.entry_price
            price_move = (mid_price - entry_px) / entry_px

            # Take Profit Target (+1.50%)
            if price_move >= self.target_profit_pct:
                return {"action": "SELL", "reason": f"TAKE_PROFIT_TARGET_HIT (+{price_move*100:.2f}%)"}

            # Stop Loss (-0.75%)
            if price_move <= -self.stop_loss_pct:
                return {"action": "SELL", "reason": f"STOP_LOSS_HIT ({price_move*100:.2f}%)"}

            # Trailing Breakeven Protection (Locks in +0.25% after peak >= +0.80%)
            if hasattr(position, "peak_move") and position.peak_move >= self.trail_breakeven_pct:
                if price_move <= 0.0025:
                    return {"action": "SELL", "reason": "TRAILING_BREAKEVEN_PROTECTION"}

            # Update peak move
            if not hasattr(position, "peak_move"):
                position.peak_move = price_move
            else:
                position.peak_move = max(position.peak_move, price_move)

            return {"action": "HOLD", "reason": "IN_POSITION"}

        # 3. Strict Entry Window Gate (09:30 - 12:45 IST)
        if dt.time() < self.entry_start:
            return {"action": "HOLD", "reason": "EARLY_SESSION_WARMUP"}
        if dt.time() > self.entry_cutoff:
            return {"action": "HOLD", "reason": "LATE_ENTRY_CUTOFF_EXCEEDED"}

        # Require minimum completed higher-timeframe bars
        if len(self.agg_15m.completed_bars) < 6 or len(self.agg_5m.completed_bars) < 10:
            return {"action": "HOLD", "reason": "WARMING_UP_HIGHER_TIMEFRAMES"}

        # 4. Relative Strength vs Session Open
        rs_score = 0.0
        if self.session_open_price and self.session_open_price > 0:
            rs_score = (mid_price - self.session_open_price) / self.session_open_price

        # Leader Criterion: Stock must be trading higher than its daily open
        if rs_score <= 0.0005:  # Must be positive intraday
            return {"action": "HOLD", "reason": "RELATIVE_STRENGTH_NEGATIVE_OR_FLAT"}

        # 5. Higher Timeframe 15m Trend Alignment
        closes_15m = [b["close"] for b in self.agg_15m.completed_bars]
        ema10_15m = self._calc_ema(closes_15m[-15:], 10)
        ema30_15m = self._calc_ema(closes_15m[-30:], 30)
        last_15m_close = closes_15m[-1]

        is_15m_bullish = (ema10_15m > ema30_15m) and (last_15m_close > ema10_15m)
        if not is_15m_bullish:
            return {"action": "HOLD", "reason": "15M_TREND_NOT_ALIGNED"}

        # 6. Medium Timeframe 5m Momentum Confirmation
        closes_5m = [b["close"] for b in self.agg_5m.completed_bars]
        ema5_5m = self._calc_ema(closes_5m[-15:], 5)
        ema15_5m = self._calc_ema(closes_5m[-25:], 15)

        is_5m_bullish = ema5_5m > ema15_5m
        if not is_5m_bullish:
            return {"action": "HOLD", "reason": "5M_MOMENTUM_NOT_CONFIRMED"}

        # 7. 1-Minute Trigger & Volume Surge
        if len(recent_1m_bars) < 20:
            return {"action": "HOLD", "reason": "INSUFFICIENT_1M_HISTORY"}

        closes_1m = [b["close"] for b in recent_1m_bars]
        vols_1m = [b["volume"] for b in recent_1m_bars]
        ema20_1m = self._calc_ema(closes_1m[-20:], 20)

        avg_vol = float(np.mean(vols_1m[-15:])) if vols_1m else 1.0
        cur_vol = bar_1m["volume"]
        vol_surge = (cur_vol / avg_vol) >= self.volume_mult if avg_vol > 0 else False

        price_cross_ema = (closes_1m[-2] <= ema20_1m) and (mid_price > ema20_1m)

        if price_cross_ema and vol_surge:
            return {
                "action": "BUY",
                "reason": "V2_1_QUALIFIED_LEADER_SIGNAL",
                "expected_move_pct": self.target_profit_pct,
                "mid_price": mid_price,
                "rs_score": rs_score,
            }

        return {"action": "HOLD", "reason": "WAITING_FOR_1M_TRIGGER"}
