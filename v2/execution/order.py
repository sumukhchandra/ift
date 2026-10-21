"""
Order entity and lifecycle state definitions for AlphaNSE V2.
"""

from dataclasses import dataclass
from enum import Enum, auto
from datetime import datetime
import uuid


class OrderAction(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderState(Enum):
    CREATED = auto()
    SUBMITTED = auto()
    ACKNOWLEDGED = auto()
    PARTIAL = auto()
    FILLED = auto()
    CANCEL_REQUESTED = auto()
    CANCELLED = auto()
    REJECTED = auto()
    EXPIRED = auto()
    UNKNOWN = auto()
    RECONCILING = auto()


@dataclass
class Order:
    client_order_id: str
    idempotency_key: str
    symbol: str
    action: OrderAction
    qty: int
    price: float
    state: OrderState = OrderState.CREATED
    filled_qty: int = 0
    average_fill_price: float = 0.0
    created_at: datetime = None
    updated_at: datetime = None
    rejection_reason: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now()
        if not self.updated_at:
            self.updated_at = self.created_at
        if self.qty < 1:
            raise ValueError(f"Order quantity must be >= 1 whole share, got: {self.qty}")
        if self.price <= 0:
            raise ValueError(f"Order price must be positive, got: {self.price}")


def create_order(
    symbol: str,
    action: OrderAction,
    qty: int,
    price: float,
    idempotency_key: str
) -> Order:
    """Factory helper generating an immutable UUIDv4 client order ID."""
    today_str = datetime.now().strftime("%Y%m%d")
    clean_sym = symbol.replace(".NS", "").replace("^", "")
    short_uuid = uuid.uuid4().hex[:8]
    client_id = f"NSE-V2-{today_str}-{clean_sym}-{short_uuid}"

    return Order(
        client_order_id=client_id,
        idempotency_key=idempotency_key,
        symbol=symbol,
        action=action,
        qty=qty,
        price=price,
        state=OrderState.CREATED
    )
