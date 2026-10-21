"""
Unit tests for Order State Machine and Lifecycle Transitions.
"""

import unittest
from v2.execution import (
    Order,
    OrderState,
    OrderAction,
    OrderStateMachine,
    InvalidOrderStateTransitionError
)
from v2.execution.order import create_order


class TestOrderStateMachine(unittest.TestCase):

    def test_legal_full_fill_flow(self):
        order = create_order("TATACAP.NS", OrderAction.BUY, qty=10, price=348.0, idempotency_key="KEY-1")
        self.assertEqual(order.state, OrderState.CREATED)

        OrderStateMachine.transition(order, OrderState.SUBMITTED)
        self.assertEqual(order.state, OrderState.SUBMITTED)

        OrderStateMachine.transition(order, OrderState.ACKNOWLEDGED)
        self.assertEqual(order.state, OrderState.ACKNOWLEDGED)

        OrderStateMachine.transition(order, OrderState.FILLED)
        self.assertEqual(order.state, OrderState.FILLED)

    def test_legal_cancellation_flow(self):
        order = create_order("INFY.NS", OrderAction.BUY, qty=5, price=1040.0, idempotency_key="KEY-2")
        OrderStateMachine.transition(order, OrderState.SUBMITTED)
        OrderStateMachine.transition(order, OrderState.ACKNOWLEDGED)
        OrderStateMachine.transition(order, OrderState.CANCEL_REQUESTED)
        OrderStateMachine.transition(order, OrderState.CANCELLED)
        self.assertEqual(order.state, OrderState.CANCELLED)

    def test_illegal_transition_out_of_filled_raises(self):
        order = create_order("TCS.NS", OrderAction.BUY, qty=1, price=2118.0, idempotency_key="KEY-3")
        OrderStateMachine.transition(order, OrderState.SUBMITTED)
        OrderStateMachine.transition(order, OrderState.ACKNOWLEDGED)
        OrderStateMachine.transition(order, OrderState.FILLED)

        # Attempting to transition from terminal state FILLED to SUBMITTED must fail
        with self.assertRaises(InvalidOrderStateTransitionError):
            OrderStateMachine.transition(order, OrderState.SUBMITTED)

    def test_illegal_direct_skip_raises(self):
        order = create_order("RELIANCE.NS", OrderAction.BUY, qty=2, price=1244.0, idempotency_key="KEY-4")
        # Direct jump from CREATED to FILLED is illegal
        with self.assertRaises(InvalidOrderStateTransitionError):
            OrderStateMachine.transition(order, OrderState.FILLED)


if __name__ == "__main__":
    unittest.main()
