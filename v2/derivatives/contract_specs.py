"""
NSE Contract Specifications Module.
Defines formal contract data structures, validation rules, and enums for individual stock futures.
"""

from dataclasses import dataclass
from enum import Enum
from datetime import date
from typing import Optional


class ContractType(str, Enum):
    FUTSTK = "FUTSTK"  # Individual Stock Futures
    FUTIDX = "FUTIDX"  # Index Futures (e.g. NIFTY, BANKNIFTY)


@dataclass(frozen=True)
class NSEContractSpec:
    """
    Formal representation of an NSE individual stock futures contract specification.
    """
    symbol: str                     # Contract symbol, e.g. "BAJFINANCE26SEPFUT"
    underlying_symbol: str          # Underlying NSE symbol, e.g. "BAJFINANCE"
    contract_type: ContractType     # FUTSTK or FUTIDX
    expiry_date: date               # Tuesday of expiry period (holiday adjusted)
    lot_size: int                   # Contract lot size (integer number of underlying shares)
    tick_size: float                # Applicable tick size (follows underlying, standard 0.05)
    quantity_freeze: int            # NSE quantity freeze limit per order
    margin_rate: float = 0.20       # Minimum SPAN + Exposure margin rate (e.g. 20% - 25%)
    contract_status: str = "ACTIVE" # ACTIVE, SUSPENDED, EXPIRED
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None

    def __post_init__(self):
        if self.lot_size <= 0:
            raise ValueError(f"Lot size must be positive, got {self.lot_size}")
        if self.tick_size <= 0:
            raise ValueError(f"Tick size must be positive, got {self.tick_size}")
        if self.quantity_freeze <= 0:
            raise ValueError(f"Quantity freeze must be positive, got {self.quantity_freeze}")
        if not (0.05 <= self.margin_rate <= 1.0):
            raise ValueError(f"Margin rate must be between 0.05 and 1.0, got {self.margin_rate}")

    @property
    def is_active(self) -> bool:
        return self.contract_status == "ACTIVE"

    def calculate_contract_value(self, price: float, lots: int = 1) -> float:
        """Calculates total notional value: price * lot_size * lots."""
        return price * self.lot_size * lots

    def calculate_required_margin(self, price: float, lots: int = 1) -> float:
        """Calculates required margin capital to hold the position."""
        return self.calculate_contract_value(price, lots) * self.margin_rate
