"""
Risk-Based Integer Position Sizer for AlphaNSE V2.
Replaces arbitrary single-share price caps with economically grounded risk & cash constraints.
"""

from dataclasses import dataclass
import math
from typing import Optional


@dataclass(frozen=True)
class SizingResult:
    is_viable: bool
    qty: int
    entry_price: float
    total_cost: float
    risk_amount: float
    stop_loss_price: float
    reason: str


class IntegerPositionSizer:
    """
    Sizes equity intraday positions into whole integer shares (Q >= 1, Q in Z).
    
    IMPORTANT ARCHITECTURAL PRINCIPLE:
    Arbitrary single-share price caps (e.g. ₹1,250 on ₹5k capital) are eliminated.
    Sizing is governed strictly by explicit unit-audited physical dimensions:
    - entry_price:          ₹ / share
    - stop_distance:        ₹ / share  (max(atr_multiplier * atr_rupees, min_stop_pct * entry_price))
    - risk_per_share:       ₹ / share  (= stop_distance)
    - risk_budget:          ₹          (= total_capital * max_risk_per_trade_pct)
    - capital_allocation:   ₹          (= available_capital * max_allocation_pct)
    - quantity (Q):         shares     (= floor(min(risk_budget / risk_per_share, capital_allocation / entry_price)))
    """

    def __init__(
        self,
        max_risk_per_trade_pct: float = 0.01,       # 1.0% portfolio risk per trade
        max_position_allocation_pct: float = 0.25,  # 25% max allocation of available cash
        atr_stop_multiplier: float = 1.5,           # 1.5 * ATR stop loss
        min_stop_loss_pct: float = 0.003            # 0.3% minimum stop loss distance
    ):
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_position_allocation_pct = max_position_allocation_pct
        self.atr_stop_multiplier = atr_stop_multiplier
        self.min_stop_loss_pct = min_stop_loss_pct

    def calculate_size(
        self,
        total_capital: float,
        available_capital: float,
        current_price: float,
        atr: float
    ) -> SizingResult:
        """
        Calculate whole integer share allocation for an entry.
        """
        if current_price <= 0:
            return SizingResult(False, 0, 0.0, 0.0, 0.0, 0.0, "Invalid price <= 0")

        if available_capital < current_price:
            return SizingResult(
                False, 0, current_price, 0.0, 0.0, 0.0,
                f"Available cash (₹{available_capital:.2f}) insufficient for single share at ₹{current_price:.2f}"
            )

        # 1. Stop loss distance based on ATR
        atr_distance = atr * self.atr_stop_multiplier
        min_distance = current_price * self.min_stop_loss_pct
        stop_distance = max(atr_distance, min_distance)
        stop_loss_price = round(current_price - stop_distance, 2)

        # 2. Risk-based quantity
        risk_budget = total_capital * self.max_risk_per_trade_pct
        qty_risk = math.floor(risk_budget / stop_distance) if stop_distance > 0 else 0

        # 3. Capital allocation-based quantity
        alloc_budget = available_capital * self.max_position_allocation_pct
        # Allow at least 1 share if cash permits and within total available capital
        qty_alloc = math.floor(alloc_budget / current_price)

        # Target quantity is constrained by both risk and allocation
        # If allocation budget gives 0 but total available cash allows 1 share and risk permits:
        if qty_alloc < 1 and available_capital >= current_price:
            # Check if 1 share violates total risk budget
            if stop_distance <= risk_budget:
                qty_target = 1
            else:
                qty_target = 0
        else:
            qty_target = min(qty_risk, qty_alloc)

        # Must not exceed available capital
        if (qty_target * current_price) > available_capital:
            qty_target = math.floor(available_capital / current_price)

        if qty_target < 1:
            return SizingResult(
                False, 0, current_price, 0.0, 0.0, stop_loss_price,
                f"Risk or allocation budget permits 0 shares at stop distance ₹{stop_distance:.2f}"
            )

        total_invested = qty_target * current_price
        actual_risk = qty_target * stop_distance

        return SizingResult(
            is_viable=True,
            qty=qty_target,
            entry_price=round(current_price, 2),
            total_cost=round(total_invested, 2),
            risk_amount=round(actual_risk, 2),
            stop_loss_price=stop_loss_price,
            reason="Approved"
        )
