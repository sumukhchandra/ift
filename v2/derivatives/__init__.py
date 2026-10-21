"""
AlphaNSE V2 — Derivatives Microstructure & Research Branch.
Provides institutional-grade modeling for NSE equity futures:
- Dynamic contract master & settlement calendar (Tuesday expiry)
- Exact statutory post-April 1, 2026 cost schedules (0.05% sell STT, etc.)
- Discrete contract lot constraints and margin requirements
- Cost-of-carry and basis modeling
- Cash-to-futures signal translation and dual-output validation
"""

from .contract_specs import NSEContractSpec, ContractType
from .settlement_calendar import NSESettlementCalendar
from .contract_master import NSEContractMaster, NSEContractRecord
from .futures_cost_model import NSEFuturesCostModel, FuturesTradeCostDetail
from .futures_execution_model import NSEFuturesExecutionModel, FuturesOrderFill
from .basis_model import FuturesBasisModel
from .signal_mapper import CashToFuturesSignalMapper, IneligibleForDerivativesError
from .futures_validator import FuturesValidator, FuturesValidationResult

__all__ = [
    "NSEContractSpec",
    "ContractType",
    "NSESettlementCalendar",
    "NSEContractMaster",
    "NSEContractRecord",
    "NSEFuturesCostModel",
    "FuturesTradeCostDetail",
    "NSEFuturesExecutionModel",
    "FuturesOrderFill",
    "FuturesBasisModel",
    "CashToFuturesSignalMapper",
    "IneligibleForDerivativesError",
    "FuturesValidator",
    "FuturesValidationResult",
]
