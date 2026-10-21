"""
Runtime Operational Safety State Machine.
Handles intraday fault tolerance, safe degradation, and automatic fault recovery.
"""

from enum import Enum, auto
from typing import Optional, List, Dict
from datetime import datetime


class RuntimeSafetyState(Enum):
    NORMAL = auto()
    SAFE_DATA_HALT = auto()
    SAFE_MODEL_HALT = auto()
    SAFE_EXECUTION_HALT = auto()


class RuntimeSafetyController:
    """
    Supervises runtime operational safety during active market hours.
    
    CRITICAL ARCHITECTURAL SEPARATION:
    Runtime safety handles transient operational events (stale feed, NaN inference, order timeout).
    When faults are resolved, the system auto-recovers to NORMAL.
    A runtime halt NEVER regresses the system to DATA_BLOCKED or resets research lifecycle progress.
    """

    def __init__(self):
        self._state = RuntimeSafetyState.NORMAL
        self._fault_reason: Optional[str] = None
        self._fault_timestamp: Optional[datetime] = None
        self._event_log: List[Dict[str, str]] = []

    @property
    def current_state(self) -> RuntimeSafetyState:
        return self._state

    @property
    def is_operational(self) -> bool:
        """Trading decisions and executions are only permitted when state is NORMAL."""
        return self._state == RuntimeSafetyState.NORMAL

    @property
    def fault_reason(self) -> Optional[str]:
        return self._fault_reason

    def trigger_data_halt(self, reason: str) -> None:
        """Triggered on stale market feed, missing tick stream, or corrupted tick format."""
        self._transition_to(RuntimeSafetyState.SAFE_DATA_HALT, reason)

    def trigger_model_halt(self, reason: str) -> None:
        """Triggered on NaN model output, unexpected dimension, or severe prediction drift."""
        self._transition_to(RuntimeSafetyState.SAFE_MODEL_HALT, reason)

    def trigger_execution_halt(self, reason: str) -> None:
        """Triggered on broker error, order rejection spike, or reconciliation mismatch."""
        self._transition_to(RuntimeSafetyState.SAFE_EXECUTION_HALT, reason)

    def auto_recover(self, health_verification_note: str) -> bool:
        """
        Attempt automatic recovery back to NORMAL when the underlying fault is verified resolved.
        """
        if self._state == RuntimeSafetyState.NORMAL:
            return True

        old_state = self._state
        self._state = RuntimeSafetyState.NORMAL
        self._fault_reason = None
        self._fault_timestamp = None
        self._log_event("AUTO_RECOVERY", f"Recovered from {old_state.name} to NORMAL: {health_verification_note}")
        return True

    def _transition_to(self, target_state: RuntimeSafetyState, reason: str) -> None:
        self._state = target_state
        self._fault_reason = reason
        self._fault_timestamp = datetime.now()
        self._log_event(target_state.name, reason)

    def _log_event(self, event_type: str, details: str) -> None:
        self._event_log.append({
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "details": details
        })
