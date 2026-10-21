"""
Unit tests for Environment Isolation and Live Broker Execution Lockout.
"""

import unittest
from v2.isolation import (
    EnvironmentMode,
    LiveExecutionDisabledError,
    ExecutionRouter
)
from v2.execution.order import create_order, OrderAction, OrderState


class TestPaperIsolation(unittest.TestCase):

    def test_research_mode_blocks_all_orders(self):
        router = ExecutionRouter(mode=EnvironmentMode.RESEARCH)
        order = create_order("TATACAP.NS", OrderAction.BUY, qty=10, price=350.0, idempotency_key="TEST-1")

        result = router.dispatch_order(order)
        self.assertIsNone(result)
        self.assertEqual(order.state, OrderState.CREATED)

    def test_paper_mode_simulates_fill(self):
        router = ExecutionRouter(mode=EnvironmentMode.PAPER)
        order = create_order("TATACAP.NS", OrderAction.BUY, qty=10, price=350.0, idempotency_key="TEST-2")

        result = router.dispatch_order(order)
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "FILLED_SIMULATED")
        self.assertEqual(order.state, OrderState.FILLED)
        self.assertEqual(order.filled_qty, 10)

    def test_live_mode_raises_physical_error(self):
        router = ExecutionRouter(mode=EnvironmentMode.LIVE)
        order = create_order("TATACAP.NS", OrderAction.BUY, qty=10, price=350.0, idempotency_key="TEST-3")

        with self.assertRaises(LiveExecutionDisabledError):
            router.dispatch_order(order)


if __name__ == "__main__":
    unittest.main()
