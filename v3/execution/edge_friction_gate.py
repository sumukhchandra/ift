#!/usr/bin/env python3
"""
v3/execution/edge_friction_gate.py
Friction-Aware Pre-Trade Signal Gate for AlphaNSE.

Core Principle:
Never execute a trade (even paper) unless the model's expected statistical move
strictly exceeds the complete roundtrip all-in market friction + safety margin.

Formula:
Expected Gross Edge > Spread + Estimated Slippage + Brokerage + Statutory Taxes + Safety Margin
"""

from dataclasses import dataclass
from typing import Dict, Any, Tuple
from v2.risk.cost_engine import IndiaCostEngine


@dataclass
class EdgeFrictionEvaluation:
    approved: bool
    symbol: str
    quantity: int
    mid_price: float
    expected_move_pct: float
    expected_gross_profit_rs: float
    estimated_roundtrip_friction_rs: float
    estimated_spread_rs: float
    estimated_slippage_rs: float
    estimated_brokerage_rs: float
    estimated_taxes_rs: float
    safety_margin_rs: float
    net_edge_rs: float
    breakeven_move_pct: float
    rejection_reason: str = ""


class EdgeFrictionGate:
    """
    Evaluates whether a prospective quantitative signal carries enough expected alpha
    to overcome the institutional friction hurdle rate on NSE cash equities.
    """

    def __init__(
        self,
        half_spread_bps: float = 3.0,
        slippage_bps: float = 4.0,
        safety_margin_rs: float = 0.50,
        min_net_expectancy_rs: float = 0.25,
    ):
        self.half_spread_bps = half_spread_bps
        self.slippage_bps = slippage_bps
        self.safety_margin_rs = safety_margin_rs
        self.min_net_expectancy_rs = min_net_expectancy_rs
        self.cost_engine = IndiaCostEngine()

    def evaluate_signal(
        self,
        symbol: str,
        side: str,
        quantity: int,
        mid_price: float,
        expected_move_pct: float,
    ) -> EdgeFrictionEvaluation:
        """
        Validates signal viability against all-in execution friction.
        """
        position_value = mid_price * quantity
        expected_gross_profit = position_value * abs(expected_move_pct)

        # 1. Roundtrip Spread (Crossing ask on entry, bid on exit)
        roundtrip_spread_bps = self.half_spread_bps * 2.0
        est_spread_rs = position_value * (roundtrip_spread_bps / 10000.0)

        # 2. Roundtrip Adverse Slippage (Entry + Exit)
        roundtrip_slippage_bps = self.slippage_bps * 2.0
        est_slippage_rs = position_value * (roundtrip_slippage_bps / 10000.0)

        # 3. Roundtrip Brokerage
        b_entry = min(self.cost_engine.brokerage_flat_cap, position_value * self.cost_engine.brokerage_pct)
        est_exit_val = position_value * (1.0 + expected_move_pct)
        b_exit = min(self.cost_engine.brokerage_flat_cap, est_exit_val * self.cost_engine.brokerage_pct)
        est_brokerage_rs = b_entry + b_exit

        # 4. Roundtrip Statutory Taxes (STT on sell, GST, SEBI, Exchange, Stamp on buy)
        stt = est_exit_val * self.cost_engine.stt_sell_pct
        exchange = (position_value + est_exit_val) * self.cost_engine.exchange_pct
        sebi = (position_value + est_exit_val) * self.cost_engine.sebi_pct
        gst = (est_brokerage_rs + exchange + sebi) * self.cost_engine.gst_pct
        stamp = position_value * self.cost_engine.stamp_duty_buy_pct
        est_taxes_rs = stt + exchange + sebi + gst + stamp

        # Total All-in Friction
        total_friction_rs = est_spread_rs + est_slippage_rs + est_brokerage_rs + est_taxes_rs
        net_edge = expected_gross_profit - total_friction_rs - self.safety_margin_rs

        # Required move to achieve breakeven
        breakeven_move_pct = (total_friction_rs + self.safety_margin_rs) / position_value if position_value > 0 else 0.0

        approved = net_edge >= self.min_net_expectancy_rs
        rejection_reason = ""
        if not approved:
            rejection_reason = (
                f"EDGE_INSUFFICIENT: Expected gross gain ₹{expected_gross_profit:.2f} ({expected_move_pct*100:.2f}%) "
                f"< All-in friction ₹{total_friction_rs:.2f} + margin ₹{self.safety_margin_rs:.2f}. "
                f"Net edge is ₹{net_edge:.2f}. Breakeven required: >={breakeven_move_pct*100:.2f}%"
            )

        return EdgeFrictionEvaluation(
            approved=approved,
            symbol=symbol,
            quantity=quantity,
            mid_price=mid_price,
            expected_move_pct=expected_move_pct,
            expected_gross_profit_rs=round(expected_gross_profit, 2),
            estimated_roundtrip_friction_rs=round(total_friction_rs, 2),
            estimated_spread_rs=round(est_spread_rs, 2),
            estimated_slippage_rs=round(est_slippage_rs, 2),
            estimated_brokerage_rs=round(est_brokerage_rs, 2),
            estimated_taxes_rs=round(est_taxes_rs, 2),
            safety_margin_rs=self.safety_margin_rs,
            net_edge_rs=round(net_edge, 2),
            breakeven_move_pct=round(breakeven_move_pct * 100.0, 3),
            rejection_reason=rejection_reason,
        )
