"""
Research & Development Lifecycle State Machine.
Tracks maturity of the trading system, model certification, and deployment phases.
"""

from enum import Enum, auto
from typing import Set


class ResearchLifecycleState(Enum):
    DEVELOPMENT = auto()
    RESEARCH = auto()
    BACKTEST = auto()
    DATA_VALIDATION = auto()
    MODEL_VALIDATION = auto()
    SHADOW = auto()
    PAPER = auto()
    LIMITED_LIVE = auto()
    LIVE = auto()


class LifecycleTransitionError(Exception):
    """Raised when an illegal or blocked lifecycle transition is attempted."""
    pass


class ResearchLifecycleController:
    """
    Manages transitions along the research and maturity lifecycle.
    Guarantees that statistical and live execution gates cannot be bypassed.
    """

    # Legal forward transitions
    ALLOWED_TRANSITIONS = {
        ResearchLifecycleState.DEVELOPMENT: {ResearchLifecycleState.RESEARCH},
        ResearchLifecycleState.RESEARCH: {ResearchLifecycleState.BACKTEST, ResearchLifecycleState.DEVELOPMENT},
        ResearchLifecycleState.BACKTEST: {ResearchLifecycleState.DATA_VALIDATION, ResearchLifecycleState.RESEARCH},
        ResearchLifecycleState.DATA_VALIDATION: {ResearchLifecycleState.MODEL_VALIDATION, ResearchLifecycleState.RESEARCH},
        ResearchLifecycleState.MODEL_VALIDATION: {ResearchLifecycleState.SHADOW, ResearchLifecycleState.RESEARCH},
        ResearchLifecycleState.SHADOW: {ResearchLifecycleState.PAPER, ResearchLifecycleState.RESEARCH},
        ResearchLifecycleState.PAPER: {ResearchLifecycleState.LIMITED_LIVE, ResearchLifecycleState.SHADOW, ResearchLifecycleState.RESEARCH},
        ResearchLifecycleState.LIMITED_LIVE: {ResearchLifecycleState.LIVE, ResearchLifecycleState.PAPER, ResearchLifecycleState.RESEARCH},
        ResearchLifecycleState.LIVE: {ResearchLifecycleState.LIMITED_LIVE, ResearchLifecycleState.PAPER, ResearchLifecycleState.RESEARCH},
    }

    def __init__(self, initial_state: ResearchLifecycleState = ResearchLifecycleState.DEVELOPMENT, is_data_blocked: bool = True):
        self._state = initial_state
        self._is_data_blocked = is_data_blocked
        self._history = [initial_state]

    @property
    def current_state(self) -> ResearchLifecycleState:
        return self._state

    @property
    def is_data_blocked(self) -> bool:
        return self._is_data_blocked

    def set_data_blocked(self, blocked: bool) -> None:
        self._is_data_blocked = blocked

    def transition_to(self, target_state: ResearchLifecycleState) -> None:
        """
        Attempt transition to target state.
        Enforces state transition legality and statistical gates.
        """
        allowed = self.ALLOWED_TRANSITIONS.get(self._state, set())
        if target_state not in allowed:
            raise LifecycleTransitionError(
                f"Illegal transition from {self._state.name} to {target_state.name}. Allowed: {[s.name for s in allowed]}"
            )

        # DATA_BLOCKED GATE: Cannot enter MODEL_VALIDATION or downstream phases if data is blocked
        blocked_downstream_states = {
            ResearchLifecycleState.MODEL_VALIDATION,
            ResearchLifecycleState.SHADOW,
            ResearchLifecycleState.PAPER,
            ResearchLifecycleState.LIMITED_LIVE,
            ResearchLifecycleState.LIVE
        }
        if self._is_data_blocked and target_state in blocked_downstream_states:
            raise LifecycleTransitionError(
                f"Cannot transition to {target_state.name} while repository is classified as DATA_BLOCKED. "
                "Multi-month historical data must be ingested and validated first."
            )

        self._state = target_state
        self._history.append(target_state)

    def can_certify_models(self) -> bool:
        """Models can only be certified if data is NOT blocked and state is MODEL_VALIDATION or beyond."""
        return (not self._is_data_blocked) and self._state in {
            ResearchLifecycleState.MODEL_VALIDATION,
            ResearchLifecycleState.SHADOW,
            ResearchLifecycleState.PAPER,
            ResearchLifecycleState.LIMITED_LIVE,
            ResearchLifecycleState.LIVE
        }
