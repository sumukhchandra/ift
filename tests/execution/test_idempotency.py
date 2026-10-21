"""
Unit tests for Order Idempotency and Duplicate Order Prevention.
"""

import unittest
from v2.execution import (
    IdempotentOrderStore,
    DuplicateOrderError,
    OrderState,
    OrderAction,
    OrderStateMachine
)
from v2.execution.order import create_order


class TestOrderIdempotency(unittest.TestCase):

    def setUp(self):
        self.store = IdempotentOrderStore()

    def test_unique_order_registration(self):
        order1 = create_order("TATACAP.NS", OrderAction.BUY, qty=10, price=348.0, idempotency_key="SIG-001")
        self.store.register(order1)

        self.assertIsNotNone(self.store.get_by_id(order1.client_order_id))
        self.assertIsNotNone(self.store.get_by_key("SIG-001"))

    def test_duplicate_idempotency_key_rejected(self):
        order1 = create_order("TATACAP.NS", OrderAction.BUY, qty=10, price=348.0, idempotency_key="SIG-002")
        self.store.register(order1)

        # Re-submitting with identical idempotency key must raise DuplicateOrderError
        order2 = create_order("TATACAP.NS", OrderAction.BUY, qty=10, price=348.0, idempotency_key="SIG-002")
        with self.assertRaises(DuplicateOrderError):
            self.store.register(order2)

    def test_in_flight_symbol_conflict_rejected(self):
        order1 = create_order("INFY.NS", OrderAction.BUY, qty=5, price=1040.0, idempotency_key="SIG-INFY-1")
        self.store.register(order1)

        # Attempting to place a second order on INFY while order1 is in CREATED state must fail
        order2 = create_order("INFY.NS", OrderAction.BUY, qty=5, price=1040.0, idempotency_key="SIG-INFY-2")
        with self.assertRaises(DuplicateOrderError):
            self.store.register(order2)

        # Transition order1 to terminal state FILLED
        OrderStateMachine.transition(order1, OrderState.SUBMITTED)
        OrderStateMachine.transition(order1, OrderState.ACKNOWLEDGED)
        OrderStateMachine.transition(order1, OrderState.FILLED)

        # Now placing a second order on INFY with a fresh key must succeed
        order3 = create_order("INFY.NS", OrderAction.SELL, qty=5, price=1045.0, idempotency_key="SIG-INFY-3")
        self.store.register(order3)
        self.assertEqual(len(self.store.get_all_orders()), 2)


if __name__ == "__main__":
    unittest.main()
