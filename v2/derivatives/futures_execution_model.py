"""
NSE Equity Futures Execution Model.
Simulates order routing, lot-size integer quantization, margin requirements,
quantity freeze limits, and order fills for stock futures contracts.
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import math

from .contract_specs import NSEContractSpec
from .futures_cost_model import (
    NSEFuturesCostModel,
    FuturesExecutionStyle,
    FuturesTradeCostDetail
)


class InsufficientMarginError(Exception):
    """Raised when available capital is insufficient for minimum integer lot size."""
    pass


class QuantityFreezeExceededError(Exception):
    """Raised when order size exceeds NSE exchange quantity freeze limit."""
    pass


@dataclass(frozen=True)
class FuturesOrderFill:
    """Outcome of an executed futures order."""
    symbol: str
    underlying: str
    order_type: str                 # "BUY" or "SELL"
    execution_style: FuturesExecutionStyle
    requested_lots: int
    filled_lots: int
    lot_size: int
    filled_shares: int
    execution_price: float
    notional_value: float
    required_margin: float
    cost_detail: FuturesTradeCostDetail
    is_fully_filled: bool
    rejection_reason: Optional[str] = None


class NSEFuturesExecutionModel:
    """
    Executes futures orders under exchange constraints:
    - Discrete lot-size quantization
    - Margin requirement validation
    - Quantity freeze slicing validation
    - Execution style friction application
    """

    def __init__(self, cost_model: Optional[NSEFuturesCostModel] = None):
        self.cost_model = cost_model or NSEFuturesCostModel()

    def calculate_max_lots(
        self,
        contract: NSEContractSpec,
        price: float,
        available_capital: float
    ) -> int:
        """
        Calculates maximum integer lots that can be purchased with available capital.
        Lots = floor( Capital / (LotSize * Price * MarginRate) )
        """
        if available_capital <= 0 or price <= 0:
            return 0
        margin_per_lot = contract.calculate_required_margin(price, lots=1)
        return int(available_capital // margin_per_lot)

    def execute_order(
        self,
        contract: NSEContractSpec,
        order_type: str,            # "BUY" or "SELL"
        price: float,
        capital_allocated: float,
        execution_style: FuturesExecutionStyle = FuturesExecutionStyle.AGGRESSIVE,
        stress_multiplier: float = 1.0,
        enforce_freeze: bool = True
    ) -> FuturesOrderFill:
        """
        Attempts to execute a futures order with integer lot sizing and margin checks.
        """
        if not contract.is_active:
            raise ValueError(f"Cannot execute order on inactive contract {contract.symbol}")

        # 1. Determine integer lot allocation
        margin_per_lot = contract.calculate_required_margin(price, lots=1)
        lots = int(capital_allocated // margin_per_lot)

        if lots == 0:
            # Capital is insufficient for 1 minimum lot
            cost_zero = self.cost_model.compute_round_trip_cost(contract_notional=1.0)
            return FuturesOrderFill(
                symbol=contract.symbol,
                underlying=contract.underlying_symbol,
                order_type=order_type,
                execution_style=execution_style,
                requested_lots=1,
                filled_lots=0,
                lot_size=contract.lot_size,
                filled_shares=0,
                execution_price=price,
                notional_value=0.0,
                required_margin=0.0,
                cost_detail=cost_zero,
                is_fully_filled=False,
                rejection_reason=f"Insufficient capital (₹{capital_allocated:,.2f}) for 1 lot (Req margin: ₹{margin_per_lot:,.2f})"
            )

        total_shares = lots * contract.lot_size

        # 2. Check quantity freeze limit
        if enforce_freeze and total_shares > contract.quantity_freeze:
            raise QuantityFreezeExceededError(
                f"Order of {total_shares} shares exceeds NSE quantity freeze of {contract.quantity_freeze} for {contract.symbol}"
            )

        # 3. Calculate notional value and margin
        notional_value = contract.calculate_contract_value(price, lots=lots)
        required_margin = notional_value * contract.margin_rate

        # 4. Compute cost detail
        cost_detail = self.cost_model.compute_round_trip_cost(
            contract_notional=notional_value,
            style=execution_style,
            stress_multiplier=stress_multiplier
        )

        return FuturesOrderFill(
            symbol=contract.symbol,
            underlying=contract.underlying_symbol,
            order_type=order_type,
            execution_style=execution_style,
            requested_lots=lots,
            filled_lots=lots,
            lot_size=contract.lot_size,
            filled_shares=total_shares,
            execution_price=price,
            notional_value=notional_value,
            required_margin=required_margin,
            cost_detail=cost_detail,
            is_fully_filled=True
        )
