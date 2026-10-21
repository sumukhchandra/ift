"""
Cash-to-Futures Signal Translation & Symbol Mapping Layer.
Implements the disciplined mapping pipeline:
cash_symbol -> NSE futures underlying -> contract master -> specific expiry contract

Strict Safeguard:
Prohibits silent substitution of tickers (e.g. TATACAP.NS cannot be mapped to TATACONSUM).
If an underlying has no active NSE F&O contract, it raises IneligibleForDerivativesError.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, Tuple
import logging

from .contract_specs import NSEContractSpec
from .contract_master import NSEContractMaster

logger = logging.getLogger(__name__)


class IneligibleForDerivativesError(Exception):
    """Raised when an equity security does not have an active F&O derivatives contract on NSE."""
    pass


@dataclass(frozen=True)
class MappedFuturesTradeIntent:
    """Represents a validated futures trading intent mapped from a cash equity signal."""
    cash_symbol: str
    underlying_symbol: str
    contract: NSEContractSpec
    cash_predicted_return_bps: float
    target_direction: int           # +1 for Long, -1 for Short
    capital_allocated: float
    feasible_lots: int
    feasible_notional: float
    required_margin: float
    is_tradable: bool
    rejection_reason: Optional[str] = None


class CashToFuturesSignalMapper:
    """
    Translates cash equity model signals into valid NSE futures contracts.
    Enforces strict underlying identity matching with contract master verification.
    """

    def __init__(self, contract_master: Optional[NSEContractMaster] = None):
        self.master = contract_master or NSEContractMaster()

    @staticmethod
    def resolve_underlying_symbol(cash_symbol: str) -> str:
        """
        Extracts canonical NSE underlying symbol from cash symbol string.
        e.g. 'BAJFINANCE.NS' -> 'BAJFINANCE', '^NSEI' -> 'NIFTY'
        """
        sym = cash_symbol.upper().strip()
        if sym in ("^NSEI", "NIFTY.NS", "NIFTY 50"):
            return "NIFTY"
        return sym.replace(".NS", "").replace("^", "")

    def map_signal_to_contract(
        self,
        cash_symbol: str,
        predicted_return_bps: float,
        capital_allocated: float,
        as_of_date: date,
        current_spot_price: float,
        min_hurdle_bps: float = 8.5
    ) -> MappedFuturesTradeIntent:
        """
        Maps cash signal to specific near-month contract.
        Rejects ineligible symbols or trades failing lot-size capital requirements.
        """
        underlying = self.resolve_underlying_symbol(cash_symbol)

        # 1. Verify existence in NSE F&O Contract Master
        if not self.master.has_fo_contract(underlying):
            raise IneligibleForDerivativesError(
                f"Security '{cash_symbol}' (underlying '{underlying}') has NO active F&O contract on NSE! "
                f"Silent substitution is strictly prohibited."
            )

        # 2. Select near-month active contract
        contract = self.master.get_near_month_contract(underlying, as_of_date)
        if contract is None:
            raise IneligibleForDerivativesError(
                f"No active unexpired contract found for underlying '{underlying}' as of {as_of_date}"
            )

        # 3. Determine directional intent
        direction = 1 if predicted_return_bps > 0 else -1

        # 4. Check whether capital meets 1 integer lot size requirement
        margin_per_lot = contract.calculate_required_margin(current_spot_price, lots=1)
        feasible_lots = int(capital_allocated // margin_per_lot)

        if feasible_lots == 0:
            return MappedFuturesTradeIntent(
                cash_symbol=cash_symbol,
                underlying_symbol=underlying,
                contract=contract,
                cash_predicted_return_bps=predicted_return_bps,
                target_direction=direction,
                capital_allocated=capital_allocated,
                feasible_lots=0,
                feasible_notional=0.0,
                required_margin=0.0,
                is_tradable=False,
                rejection_reason=f"Capital ₹{capital_allocated:,.2f} insufficient for 1 lot (Margin required: ₹{margin_per_lot:,.2f})"
            )

        feasible_notional = contract.calculate_contract_value(current_spot_price, lots=feasible_lots)
        required_margin = feasible_notional * contract.margin_rate

        # 5. Check if predicted return overcomes minimum futures friction hurdle
        if abs(predicted_return_bps) < min_hurdle_bps:
            return MappedFuturesTradeIntent(
                cash_symbol=cash_symbol,
                underlying_symbol=underlying,
                contract=contract,
                cash_predicted_return_bps=predicted_return_bps,
                target_direction=direction,
                capital_allocated=capital_allocated,
                feasible_lots=feasible_lots,
                feasible_notional=feasible_notional,
                required_margin=required_margin,
                is_tradable=False,
                rejection_reason=f"Predicted signal ({predicted_return_bps:+.2f} bps) does not clear futures hurdle ({min_hurdle_bps:.2f} bps)"
            )

        return MappedFuturesTradeIntent(
            cash_symbol=cash_symbol,
            underlying_symbol=underlying,
            contract=contract,
            cash_predicted_return_bps=predicted_return_bps,
            target_direction=direction,
            capital_allocated=capital_allocated,
            feasible_lots=feasible_lots,
            feasible_notional=feasible_notional,
            required_margin=required_margin,
            is_tradable=True,
            rejection_reason=None
        )
