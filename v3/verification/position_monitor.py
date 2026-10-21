"""
AlphaNSE V3 — Active Position Monitor & Dynamic Action Engine (Sections 28 & 29).
Monitors active open positions dynamically bar-by-bar, issuing structured actions:
  HOLD           -> Thesis progressing normally within risk boundaries
  ADD            -> High-conviction thesis expansion (only on profit, NEVER to average down)
  REDUCE         -> Partial profit taking as target approaches
  EXIT           -> Target reached or invalidated
  TIMEOUT        -> Time horizon elapsed without realization
  EMERGENCY_EXIT -> Catastrophic circuit trip or end-of-day square-off (15:25 IST)

ARCHITECTURAL INVARIANT:
  No averaging down merely to rescue a losing trade is permitted.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import time
from v3.verification.minute_verifier import ThesisVerificationRecord


@dataclass
class PositionActionRecommendation:
    """Action decision issued for an active position."""
    symbol: str
    action: str                         # "HOLD", "ADD", "REDUCE", "EXIT", "TIMEOUT", "EMERGENCY_EXIT"
    target_quantity_change: int         # 0 for HOLD/TIMEOUT/EXIT, >0 for ADD, <0 for REDUCE
    urgency: str                        # "LOW", "MEDIUM", "HIGH", "IMMEDIATE"
    action_reason: str
    realized_pnl_bps: float
    time_held_minutes: int


class ActivePositionMonitorV3:
    """
    Evaluates open positions bar-by-bar, managing transitions and preventing loss averaging.
    """

    def __init__(self, eod_close_time: time = time(15, 25)):
        self.eod_close_time = eod_close_time

    def evaluate_position_action(
        self,
        symbol: str,
        current_time: time,
        current_qty: int,
        entry_price: float,
        current_price: float,
        bars_held: int,
        horizon_bars: int,
        thesis_record: ThesisVerificationRecord
    ) -> PositionActionRecommendation:
        """
        Determines the next action for an active position.
        """
        time_held_mins = bars_held * 5
        realized_bps = thesis_record.realized_move_bps

        # 1. Mandatory End-of-Day Square-Off (15:25 IST)
        if current_time >= self.eod_close_time:
            return PositionActionRecommendation(
                symbol=symbol,
                action="EMERGENCY_EXIT",
                target_quantity_change=-current_qty,
                urgency="IMMEDIATE",
                action_reason="EOD_MANDATORY_SQUARE_OFF (15:25 IST reached)",
                realized_pnl_bps=realized_bps,
                time_held_minutes=time_held_mins
            )

        # 2. Thesis Invalidation / Stop Loss Hit
        if thesis_record.is_invalidated:
            return PositionActionRecommendation(
                symbol=symbol,
                action="EXIT",
                target_quantity_change=-current_qty,
                urgency="HIGH",
                action_reason=thesis_record.invalidation_reason or "THESIS_INVALIDATED",
                realized_pnl_bps=realized_bps,
                time_held_minutes=time_held_mins
            )

        # 3. Target Completed
        if thesis_record.thesis_state == "COMPLETED":
            return PositionActionRecommendation(
                symbol=symbol,
                action="EXIT",
                target_quantity_change=-current_qty,
                urgency="MEDIUM",
                action_reason=f"TARGET_COMPLETED (+{realized_bps:.1f} bps achieved)",
                realized_pnl_bps=realized_bps,
                time_held_minutes=time_held_mins
            )

        # 4. Horizon Time-Out
        if bars_held >= horizon_bars:
            return PositionActionRecommendation(
                symbol=symbol,
                action="TIMEOUT",
                target_quantity_change=-current_qty,
                urgency="MEDIUM",
                action_reason=f"HORIZON_TIMEOUT ({bars_held} bars >= {horizon_bars} bars)",
                realized_pnl_bps=realized_bps,
                time_held_minutes=time_held_mins
            )

        # 5. Weakening Thesis with Adverse Excursion
        if thesis_record.thesis_state == "WEAKENING" and realized_bps < -20.0:
            return PositionActionRecommendation(
                symbol=symbol,
                action="EXIT",
                target_quantity_change=-current_qty,
                urgency="HIGH",
                action_reason=f"WEAKENING_MOMENTUM_CUTOFF (Realized {realized_bps:.1f} bps)",
                realized_pnl_bps=realized_bps,
                time_held_minutes=time_held_mins
            )

        # 6. Default: Hold position normally
        return PositionActionRecommendation(
            symbol=symbol,
            action="HOLD",
            target_quantity_change=0,
            urgency="LOW",
            action_reason=f"THESIS_ON_TRACK ({thesis_record.thesis_state}, {thesis_record.remaining_minutes}m remaining)",
            realized_pnl_bps=realized_bps,
            time_held_minutes=time_held_mins
        )
