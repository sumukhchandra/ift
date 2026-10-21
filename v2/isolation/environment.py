"""
Environment Isolation and Broker Execution Guard for AlphaNSE V2.
Guarantees that under RESEARCH and PAPER modes, real broker orders cannot be created or sent.
Guarantees that LIVE execution is physically blocked with a runtime exception during Phase 1.
"""

from enum import Enum
from typing import Optional, Dict, Any
from ..execution.order import Order, OrderState
from ..execution.order_state_machine import OrderStateMachine


class EnvironmentMode(Enum):
    RESEARCH = "RESEARCH"
    PAPER = "PAPER"
    LIVE = "LIVE"


class LiveExecutionDisabledError(Exception):
    """Raised when any attempt is made to dispatch a real-money broker order in Phase 1."""
    pass


class ExecutionRouter:
    """
    Directs orders according to the active environment mode.
    Enforces absolute isolation between research, simulated paper, and live broker channels.
    """

    def __init__(self, mode: EnvironmentMode = EnvironmentMode.RESEARCH):
        self._mode = mode
        self._dispatched_paper_orders: list = []

    @property
    def mode(self) -> EnvironmentMode:
        return self._mode

    def dispatch_order(self, order: Order) -> Optional[Dict[str, Any]]:
        """
        Route an order according to the active environment mode.
        """
        # 1. RESEARCH MODE: Absolutely no order dispatch permitted
        if self._mode == EnvironmentMode.RESEARCH:
            return None

        # 2. PAPER MODE: Routed to internal simulated matching engine
        if self._mode == EnvironmentMode.PAPER:
            OrderStateMachine.transition(order, OrderState.SUBMITTED)
            OrderStateMachine.transition(order, OrderState.ACKNOWLEDGED)
            OrderStateMachine.transition(order, OrderState.FILLED)
            order.filled_qty = order.qty
            order.average_fill_price = order.price

            result = {
                "status": "FILLED_SIMULATED",
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "qty": order.qty,
                "fill_price": order.price,
                "mode": "PAPER"
            }
            self._dispatched_paper_orders.append(result)
            return result

        # 3. LIVE MODE: HARD PHYSICAL BLOCK
        if self._mode == EnvironmentMode.LIVE:
            raise LiveExecutionDisabledError(
                "CRITICAL SAFETY VIOLATION: Live broker execution is disabled in Phase 1. "
                "No live capital connection is authorized until Phase 4+ validation gates pass."
            )

        raise ValueError(f"Unknown environment mode: {self._mode}")
