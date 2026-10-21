"""
AlphaNSE V3 — Real-Time 1-Minute Thesis Verifier & Time-to-Edge Engine (Sections 26 & 27).
Monitors active candidate predictions continuously during the session, tracking:
  - Reality vs Model Predictions (Direction, Magnitude, Timing)
  - Prediction Error & Variance
  - Real-Time Thesis Progression:
      ON_TRACK    -> Market moving as expected within scheduled window
      EARLY       -> Move materialized faster than expected horizon
      LATE        -> Move delayed but structure intact
      WEAKENING   -> Momentum dissipating before reaching target
      INVALIDATED -> Price violated invalidation threshold or adverse excursion limit
      COMPLETED   -> Target return/price achieved
"""

from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional
from datetime import datetime, time
import numpy as np


@dataclass
class ThesisVerificationRecord:
    """State audit for an active trading thesis at an intraday checkpoint."""
    symbol: str
    checkpoint_time: str
    minutes_elapsed: int
    predicted_direction: int
    predicted_target_bps: float
    expected_time_to_edge_mins: int
    entry_price: float
    current_price: float
    realized_move_bps: float
    remaining_expected_move_bps: float
    prediction_error_bps: float
    thesis_state: str                   # "ON_TRACK", "EARLY", "LATE", "WEAKENING", "INVALIDATED", "COMPLETED"
    remaining_minutes: int
    is_invalidated: bool
    invalidation_reason: Optional[str] = None


class MinuteThesisVerifierV3:
    """
    Executes 1-minute real-time cross-verification of active predictions against live market prints.
    """

    def verify_thesis(
        self,
        symbol: str,
        checkpoint_time: str,
        minutes_elapsed: int,
        predicted_direction: int,
        expected_gross_bps: float,
        expected_time_to_edge_mins: int,
        entry_price: float,
        current_price: float,
        stop_loss_price: float
    ) -> ThesisVerificationRecord:
        """
        Computes prediction vs reality discrepancies and categorizes thesis state.
        """
        if entry_price <= 0:
            realized_bps = 0.0
        else:
            if predicted_direction >= 0:
                realized_bps = (current_price - entry_price) / entry_price * 10000.0
            else:
                realized_bps = (entry_price - current_price) / entry_price * 10000.0

        remaining_bps = expected_gross_bps - realized_bps
        pred_error = abs(realized_bps - expected_gross_bps)
        rem_mins = max(0, expected_time_to_edge_mins - minutes_elapsed)

        # Check for invalidation (Stop loss breached)
        is_invalidated = False
        inv_reason = None

        if predicted_direction >= 0 and current_price <= stop_loss_price:
            is_invalidated = True
            inv_reason = f"STOP_LOSS_BREACHED (Price ₹{current_price:.2f} <= Stop ₹{stop_loss_price:.2f})"
        elif predicted_direction < 0 and current_price >= stop_loss_price:
            is_invalidated = True
            inv_reason = f"STOP_LOSS_BREACHED (Price ₹{current_price:.2f} >= Stop ₹{stop_loss_price:.2f})"

        # Determine Thesis State
        if is_invalidated:
            state = "INVALIDATED"
        elif realized_bps >= expected_gross_bps:
            state = "COMPLETED"
        elif minutes_elapsed <= (expected_time_to_edge_mins * 0.5) and realized_bps >= (expected_gross_bps * 0.75):
            state = "EARLY"
        elif minutes_elapsed >= expected_time_to_edge_mins and realized_bps < (expected_gross_bps * 0.3):
            state = "LATE"
        elif realized_bps < 0 and minutes_elapsed >= 15:
            state = "WEAKENING"
        else:
            state = "ON_TRACK"

        return ThesisVerificationRecord(
            symbol=symbol,
            checkpoint_time=checkpoint_time,
            minutes_elapsed=minutes_elapsed,
            predicted_direction=predicted_direction,
            predicted_target_bps=round(expected_gross_bps, 2),
            expected_time_to_edge_mins=expected_time_to_edge_mins,
            entry_price=round(entry_price, 2),
            current_price=round(current_price, 2),
            realized_move_bps=round(realized_bps, 2),
            remaining_expected_move_bps=round(remaining_bps, 2),
            prediction_error_bps=round(pred_error, 2),
            thesis_state=state,
            remaining_minutes=rem_mins,
            is_invalidated=is_invalidated,
            invalidation_reason=inv_reason
        )
