"""
Order State Machine for AlphaNSE V2.
Enforces valid lifecycle transitions and terminal state immutability.
"""

from datetime import datetime
from .order import Order, OrderState


class InvalidOrderStateTransitionError(Exception):
    """Raised when an illegal order lifecycle transition is attempted."""
    pass


class OrderStateMachine:
    """Manages order state transitions."""

    LEGAL_TRANSITIONS = {
        OrderState.CREATED: {OrderState.SUBMITTED, OrderState.REJECTED},
        OrderState.SUBMITTED: {OrderState.ACKNOWLEDGED, OrderState.REJECTED, OrderState.EXPIRED, OrderState.UNKNOWN},
        OrderState.ACKNOWLEDGED: {OrderState.PARTIAL, OrderState.FILLED, OrderState.CANCEL_REQUESTED, OrderState.REJECTED},
        OrderState.PARTIAL: {OrderState.PARTIAL, OrderState.FILLED, OrderState.CANCEL_REQUESTED},
        OrderState.CANCEL_REQUESTED: {OrderState.CANCELLED, OrderState.FILLED},
        OrderState.UNKNOWN: {OrderState.RECONCILING},
        OrderState.RECONCILING: {OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED},
        # Terminal states have no legal outgoing transitions
        OrderState.FILLED: set(),
        OrderState.CANCELLED: set(),
        OrderState.REJECTED: set(),
        OrderState.EXPIRED: set(),
    }

    @classmethod
    def transition(cls, order: Order, new_state: OrderState, reason: str = "") -> None:
        """
        Transition an order to new_state.
        Raises InvalidOrderStateTransitionError if transition is illegal.
        """
        allowed = cls.LEGAL_TRANSITIONS.get(order.state, set())
        if new_state not in allowed:
            raise InvalidOrderStateTransitionError(
                f"Illegal order transition from {order.state.name} to {new_state.name} for {order.client_order_id}. "
                f"Allowed: {[s.name for s in allowed]}"
            )

        order.state = new_state
        order.updated_at = datetime.now()
        if reason:
            order.rejection_reason = reason
