"""
v3/ensemble/unified_risk_engine.py
Centralized Risk Engine for AlphaNSE Unified Ensemble.
Enforces whole-share integer sizing, ₹1,500 capital limit, ₹30 daily loss circuit breaker,
dynamic trailing stops, and stagnation timeout exit governors.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

from v3.ensemble.specialist_signal import SignalDirection
from v3.ensemble.unified_meta_decision_engine import MetaDecisionOutput


@dataclass
class PositionRiskState:
    """Active open position risk tracking state."""
    symbol: str
    direction: SignalDirection          # BUY (Long) or SELL (Short)
    quantity: int
    entry_price: float
    current_price: float
    highest_price: float
    lowest_price: float
    invested_capital: float
    entry_timestamp: datetime
    stop_loss_price: float
    take_profit_price: float
    trailing_stop_active: bool = False
    trailing_stop_price: float = 0.0
    stagnation_timeout_mins: int = 45   # Auto-exit if flat after 45 mins
    supporting_models: List[str] = field(default_factory=list)


class UnifiedRiskEngine:
    """
    Central risk governor enforcing fail-closed capital, position, and loss limits.
    """
    def __init__(
        self,
        max_capital: float = 1500.0,
        max_daily_loss: float = 30.0,
        max_concurrent_positions: int = 1,
        hard_stop_loss_pct: float = 0.006,       # 0.60% stop loss
        take_profit_target_pct: float = 0.030,   # 3.0% take profit
        trailing_stop_activation_pct: float = 0.012, # Trailing activates at +1.2%
        trailing_pullback_pct: float = 0.0035,   # Trailing ratchet 0.35% off peak
        stagnation_cutoff_mins: int = 45         # Max flat-hold window
    ):
        self.max_capital = max_capital
        self.max_daily_loss = max_daily_loss
        self.max_concurrent_positions = max_concurrent_positions
        self.hard_stop_loss_pct = hard_stop_loss_pct
        self.take_profit_target_pct = take_profit_target_pct
        self.trailing_stop_activation_pct = trailing_stop_activation_pct
        self.trailing_pullback_pct = trailing_pullback_pct
        self.stagnation_cutoff_mins = stagnation_cutoff_mins

        self.current_cash = max_capital
        self.realized_pnl_today = 0.0
        self.active_position: Optional[PositionRiskState] = None
        self.circuit_breaker_tripped = False

    def is_trading_allowed(self) -> Tuple[bool, str]:
        """Fail-closed safety check before evaluating any order."""
        if self.circuit_breaker_tripped:
            return False, f"CIRCUIT_BREAKER_TRIPPED: Daily loss limit (₹{self.max_daily_loss:.2f}) reached"
        if self.realized_pnl_today <= -self.max_daily_loss:
            self.circuit_breaker_tripped = True
            return False, f"DAILY_LOSS_LIMIT_REACHED: Realized P&L ₹{self.realized_pnl_today:.2f} <= -₹{self.max_daily_loss:.2f}"
        if self.active_position is not None:
            return False, f"MAX_POSITIONS_REACHED: Position already open in {self.active_position.symbol}"
        if self.current_cash < 100.0:
            return False, f"INSUFFICIENT_CASH: Available cash ₹{self.current_cash:.2f} < ₹100.00 buffer"
        return True, "ALLOWED"

    def calculate_order_sizing(
        self,
        decision: MetaDecisionOutput,
        current_price: float
    ) -> Tuple[int, float, str]:
        """
        Computes whole-share integer position sizing within the ₹1,500 budget.
        """
        allowed, reason = self.is_trading_allowed()
        if not allowed:
            return 0, 0.0, reason

        if current_price <= 0:
            return 0, 0.0, "INVALID_PRICE"

        # Deploy up to 95% of available cash for single concentrated runner
        deployable_cash = min(self.current_cash, self.max_capital) * 0.95
        shares = int(deployable_cash // current_price)

        if shares < 1:
            return 0, 0.0, f"PRICE_EXCEEDS_BUDGET: Share price ₹{current_price:.2f} > deployable cash ₹{deployable_cash:.2f}"

        capital_required = round(shares * current_price, 2)
        return shares, capital_required, "SIZED_SUCCESSFULLY"

    def open_position(
        self,
        decision: MetaDecisionOutput,
        current_price: float,
        timestamp: Optional[datetime] = None
    ) -> Tuple[Optional[PositionRiskState], str]:
        """Initializes and registers a new position."""
        shares, capital_req, reason = self.calculate_order_sizing(decision, current_price)
        if shares < 1:
            return None, reason

        now = timestamp or datetime.now()
        direction = decision.action

        if direction == SignalDirection.BUY:
            sl_price = round(current_price * (1.0 - self.hard_stop_loss_pct), 2)
            tp_price = round(current_price * (1.0 + self.take_profit_target_pct), 2)
        else:  # SELL / Short
            sl_price = round(current_price * (1.0 + self.hard_stop_loss_pct), 2)
            tp_price = round(current_price * (1.0 - self.take_profit_target_pct), 2)

        self.current_cash -= capital_req
        self.active_position = PositionRiskState(
            symbol=decision.target_symbol,
            direction=direction,
            quantity=shares,
            entry_price=current_price,
            current_price=current_price,
            highest_price=current_price,
            lowest_price=current_price,
            invested_capital=capital_req,
            entry_timestamp=now,
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
            stagnation_timeout_mins=self.stagnation_cutoff_mins,
            supporting_models=decision.supporting_models
        )

        return self.active_position, "POSITION_OPENED"

    def evaluate_position_exit(
        self,
        current_price: float,
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, str, float]:
        """
        Evaluates active position against Stop-Loss, Take-Profit, Trailing Stop,
        and Stagnation Timeout.
        Returns: (should_exit, exit_reason, price)
        """
        pos = self.active_position
        if pos is None:
            return False, "NO_OPEN_POSITION", 0.0

        now = current_time or datetime.now()
        pos.current_price = current_price

        # Update high / low watermarks
        if current_price > pos.highest_price:
            pos.highest_price = current_price
        if current_price < pos.lowest_price:
            pos.lowest_price = current_price

        entry_p = pos.entry_price
        mins_held = (now - pos.entry_timestamp).total_seconds() / 60.0

        # Long Position Evaluations
        if pos.direction == SignalDirection.BUY:
            gain_pct = (current_price - entry_p) / entry_p
            best_gain_pct = (pos.highest_price - entry_p) / entry_p
            pullback_from_peak = (pos.highest_price - current_price) / pos.highest_price

            # 1. Hard Stop-Loss
            if current_price <= pos.stop_loss_price:
                return True, "HARD_STOP_LOSS", current_price

            # 2. Take-Profit Target
            if current_price >= pos.take_profit_price:
                return True, "TAKE_PROFIT_TARGET", current_price

            # 3. Dynamic Trailing Stop Ratchet
            if best_gain_pct >= self.trailing_stop_activation_pct:
                pos.trailing_stop_active = True
                pos.trailing_stop_price = round(pos.highest_price * (1.0 - self.trailing_pullback_pct), 2)
                if current_price <= pos.trailing_stop_price:
                    return True, "TRAILING_STOP_RATCHET", current_price

            # 4. Stagnation / Time-Decay Exit (Prevents indefinite chop holding)
            if mins_held >= pos.stagnation_timeout_mins and abs(gain_pct) < 0.0025:
                return True, "STAGNATION_TIMEOUT_CHOP_EXIT", current_price

        # Short Position Evaluations
        else:
            gain_pct = (entry_p - current_price) / entry_p
            best_gain_pct = (entry_p - pos.lowest_price) / entry_p
            pullback_from_peak = (current_price - pos.lowest_price) / entry_p

            # 1. Hard Stop-Loss
            if current_price >= pos.stop_loss_price:
                return True, "HARD_STOP_LOSS", current_price

            # 2. Take-Profit Target
            if current_price <= pos.take_profit_price:
                return True, "TAKE_PROFIT_TARGET", current_price

            # 3. Dynamic Trailing Stop Ratchet
            if best_gain_pct >= self.trailing_stop_activation_pct:
                pos.trailing_stop_active = True
                pos.trailing_stop_price = round(pos.lowest_price * (1.0 + self.trailing_pullback_pct), 2)
                if current_price >= pos.trailing_stop_price:
                    return True, "TRAILING_STOP_RATCHET", current_price

            # 4. Stagnation / Time-Decay Exit
            if mins_held >= pos.stagnation_timeout_mins and abs(gain_pct) < 0.0025:
                return True, "STAGNATION_TIMEOUT_CHOP_EXIT", current_price

        return False, "HOLDING", 0.0

    def close_position(
        self,
        exit_price: float,
        statutory_friction: float = 0.0
    ) -> Tuple[float, float]:
        """Closes position, recovers cash, records P&L."""
        pos = self.active_position
        if pos is None:
            return 0.0, 0.0

        if pos.direction == SignalDirection.BUY:
            gross_pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            gross_pnl = (pos.entry_price - exit_price) * pos.quantity

        net_pnl = round(gross_pnl - statutory_friction, 2)
        recovered_capital = pos.invested_capital + gross_pnl - statutory_friction

        self.current_cash += max(0.0, recovered_capital)
        self.realized_pnl_today += net_pnl

        # Check circuit breaker
        if self.realized_pnl_today <= -self.max_daily_loss:
            self.circuit_breaker_tripped = True

        self.active_position = None
        return gross_pnl, net_pnl
