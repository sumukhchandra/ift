"""
Idempotent Order Store for AlphaNSE V2.
Prevents duplicate order submissions across process restarts and network retries.
"""

import threading
from typing import Dict, Optional, List
from .order import Order, OrderState


class DuplicateOrderError(Exception):
    """Raised when an order submission violates idempotency constraints."""
    pass


class IdempotentOrderStore:
    """
    Thread-safe, crash-reconciled order store.
    Guarantees that no duplicate orders can be created or dispatched.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._orders_by_id: Dict[str, Order] = {}
        self._orders_by_key: Dict[str, Order] = {}

    def register(self, order: Order) -> None:
        """
        Register a newly created order.
        Raises DuplicateOrderError if the idempotency_key has already been used,
        or if an active in-flight order already exists for the same symbol.
        """
        with self._lock:
            # 1. Idempotency key collision check
            if order.idempotency_key in self._orders_by_key:
                existing = self._orders_by_key[order.idempotency_key]
                raise DuplicateOrderError(
                    f"Duplicate order rejected: idempotency key '{order.idempotency_key}' "
                    f"already bound to order {existing.client_order_id} in state {existing.state.name}"
                )

            # 2. In-flight active order check for the same symbol
            in_flight_states = {
                OrderState.CREATED,
                OrderState.SUBMITTED,
                OrderState.ACKNOWLEDGED,
                OrderState.PARTIAL,
                OrderState.CANCEL_REQUESTED,
                OrderState.RECONCILING
            }
            for existing in self._orders_by_id.values():
                if existing.symbol == order.symbol and existing.state in in_flight_states:
                    raise DuplicateOrderError(
                        f"In-flight order conflict: symbol '{order.symbol}' already has active order "
                        f"{existing.client_order_id} in state {existing.state.name}"
                    )

            # Register
            self._orders_by_id[order.client_order_id] = order
            self._orders_by_key[order.idempotency_key] = order

    def get_by_id(self, client_order_id: str) -> Optional[Order]:
        with self._lock:
            return self._orders_by_id.get(client_order_id)

    def get_by_key(self, idempotency_key: str) -> Optional[Order]:
        with self._lock:
            return self._orders_by_key.get(idempotency_key)

    def get_all_orders(self) -> List[Order]:
        with self._lock:
            return list(self._orders_by_id.values())

    def get_active_orders(self) -> List[Order]:
        in_flight = {
            OrderState.CREATED,
            OrderState.SUBMITTED,
            OrderState.ACKNOWLEDGED,
            OrderState.PARTIAL,
            OrderState.CANCEL_REQUESTED,
            OrderState.RECONCILING
        }
        with self._lock:
            return [o for o in self._orders_by_id.values() if o.state in in_flight]
