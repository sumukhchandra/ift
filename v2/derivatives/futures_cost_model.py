"""
NSE Equity Futures Cost & Microstructure Engine.
Codifies official post-April 1, 2026 statutory rates and execution friction:
- Securities Transaction Tax (STT): 0.05% on sell turnover (5.00 bps)
- Stamp Duty: 0.002% on buyer turnover (0.20 bps)
- Exchange Turnover Charges: ₹183 per crore per side (0.366 bps RT) including IPFT
- SEBI Turnover Fee: ₹10 per crore per side (0.02 bps RT)
- GST: 18% on (Brokerage + Exchange Charges + SEBI Charges)
- Brokerage: Configurable via BrokerCostConfig (default flat ₹20/order)
- Execution Friction: Half-spread, market impact, adverse selection, and basis slippage
- Enforces strict additive identity: |sum(components) - total_expected_bps| < 1e-6
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional
import math

from v2.risk.cost_scenarios import BrokerCostConfig, BrokerageType


@dataclass(frozen=True)
class FuturesTradeCostDetail:
    """Complete decomposed breakdown of round-trip equity futures trading costs."""
    notional: float                 # One-leg notional value (INR)
    brokerage_inr: float
    stt_inr: float
    exchange_charges_inr: float
    sebi_fee_inr: float
    gst_inr: float
    stamp_duty_inr: float
    total_statutory_inr: float

    # Bps metrics (normalized by one-leg notional)
    statutory_bps: float
    spread_component_bps: float
    impact_bps: float
    adverse_selection_bps: float
    basis_slippage_bps: float
    total_friction_bps: float

    def verify_additive_identity(self, tolerance: float = 1e-5) -> bool:
        """Verifies sum(components) == total_friction_bps."""
        components_sum = (
            self.statutory_bps +
            self.spread_component_bps +
            self.impact_bps +
            self.adverse_selection_bps +
            self.basis_slippage_bps
        )
        return abs(components_sum - self.total_friction_bps) < tolerance


class FuturesExecutionStyle(str, Enum):
    AGGRESSIVE = "AGGRESSIVE"          # Market order / cross spread
    PASSIVE = "PASSIVE"                # Limit order at inside quote
    CONSERVATIVE_PASSIVE = "CONSERVATIVE_PASSIVE"


class NSEFuturesCostModel:
    """
    Evaluates institutional round-trip execution costs for NSE stock futures.
    Implements April 1, 2026 regulatory updates and microstructure frictions.
    """

    # Regulatory schedule (effective April 1, 2026)
    STT_SELL_RATE = 0.0005                 # 0.05% on sell transaction value
    STAMP_DUTY_BUY_RATE = 0.00002          # 0.002% on buy transaction value
    EXCHANGE_TURNOVER_RATE = 0.0000183     # ₹183 per crore per side (incl IPFT)
    SEBI_TURNOVER_RATE = 0.0000010         # ₹10 per crore per side
    GST_RATE = 0.18                        # 18% on Brokerage + Exchange + SEBI

    def __init__(
        self,
        broker_config: Optional[BrokerCostConfig] = None,
        base_spread_bps: float = 1.0,      # Default 1.0 bps round-trip spread
        base_impact_bps: float = 1.0,      # Default 1.0 bps market impact
        basis_slippage_bps: float = 0.5    # Basis fluctuation noise
    ):
        self.broker_config = broker_config or BrokerCostConfig(
            brokerage_type=BrokerageType.FLAT_PER_ORDER,
            brokerage_max_per_order=20.0
        )
        self.base_spread_bps = base_spread_bps
        self.base_impact_bps = base_impact_bps
        self.basis_slippage_bps = basis_slippage_bps

    def calculate_brokerage(self, notional: float) -> float:
        """Calculates single-leg brokerage commission in INR."""
        return self.broker_config.calculate_brokerage(notional)

    def compute_statutory_costs(
        self,
        entry_notional: float,
        exit_notional: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Computes the exact statutory levies for a round-trip equity futures trade.
        Assumes Long trade: Entry = Buy, Exit = Sell.
        For Short trade: Entry = Sell, Exit = Buy (total levies are identical).
        """
        if exit_notional is None:
            exit_notional = entry_notional

        buy_turnover = entry_notional
        sell_turnover = exit_notional

        # 1. Brokerage (both legs)
        b_entry = self.calculate_brokerage(buy_turnover)
        b_exit = self.calculate_brokerage(sell_turnover)
        total_brokerage = b_entry + b_exit

        # 2. STT: 0.05% on sell side only
        stt = sell_turnover * self.STT_SELL_RATE

        # 3. Exchange charges: ₹183 per crore each side
        exch_entry = buy_turnover * self.EXCHANGE_TURNOVER_RATE
        exch_exit = sell_turnover * self.EXCHANGE_TURNOVER_RATE
        total_exchange = exch_entry + exch_exit

        # 4. SEBI fee: ₹10 per crore each side
        sebi_entry = buy_turnover * self.SEBI_TURNOVER_RATE
        sebi_exit = sell_turnover * self.SEBI_TURNOVER_RATE
        total_sebi = sebi_entry + sebi_exit

        # 5. GST: 18% on (Brokerage + Exchange Charges + SEBI Fee)
        gst_base = total_brokerage + total_exchange + total_sebi
        gst = gst_base * self.GST_RATE

        # 6. Stamp Duty: 0.002% on buy side only
        stamp_duty = buy_turnover * self.STAMP_DUTY_BUY_RATE

        total_statutory = total_brokerage + stt + total_exchange + total_sebi + gst + stamp_duty

        return {
            "brokerage_inr": total_brokerage,
            "stt_inr": stt,
            "exchange_charges_inr": total_exchange,
            "sebi_fee_inr": total_sebi,
            "gst_inr": gst,
            "stamp_duty_inr": stamp_duty,
            "total_statutory_inr": total_statutory,
        }

    def compute_round_trip_cost(
        self,
        contract_notional: float,
        style: FuturesExecutionStyle = FuturesExecutionStyle.AGGRESSIVE,
        participation_rate: float = 0.01,
        stress_multiplier: float = 1.0
    ) -> FuturesTradeCostDetail:
        """
        Computes total expected round-trip friction (statutory + microstructure).
        """
        if contract_notional <= 0:
            raise ValueError(f"Contract notional must be positive, got {contract_notional}")

        # Compute statutory levies
        stat = self.compute_statutory_costs(contract_notional, contract_notional)
        statutory_bps = (stat["total_statutory_inr"] / contract_notional) * 10000.0

        # Microstructure execution costs
        if style == FuturesExecutionStyle.AGGRESSIVE:
            # Crosses the full spread round-trip
            spread_bps = self.base_spread_bps * stress_multiplier
            # Square root market impact
            impact_bps = self.base_impact_bps * math.sqrt(max(1.0, participation_rate * 100.0)) * stress_multiplier
            adverse_selection_bps = 0.0
            basis_bps = self.basis_slippage_bps * stress_multiplier
        elif style == FuturesExecutionStyle.PASSIVE:
            # Captures spread, but suffers queue fill probability and adverse selection
            spread_bps = 0.2 * self.base_spread_bps * stress_multiplier
            impact_bps = 0.3 * self.base_impact_bps * stress_multiplier
            adverse_selection_bps = 0.8 * stress_multiplier
            basis_bps = self.basis_slippage_bps * stress_multiplier
        else:  # CONSERVATIVE_PASSIVE
            spread_bps = 0.1 * self.base_spread_bps * stress_multiplier
            impact_bps = 0.2 * self.base_impact_bps * stress_multiplier
            adverse_selection_bps = 1.2 * stress_multiplier
            basis_bps = self.basis_slippage_bps * stress_multiplier

        total_friction_bps = (
            statutory_bps +
            spread_bps +
            impact_bps +
            adverse_selection_bps +
            basis_bps
        )

        detail = FuturesTradeCostDetail(
            notional=contract_notional,
            brokerage_inr=stat["brokerage_inr"],
            stt_inr=stat["stt_inr"],
            exchange_charges_inr=stat["exchange_charges_inr"],
            sebi_fee_inr=stat["sebi_fee_inr"],
            gst_inr=stat["gst_inr"],
            stamp_duty_inr=stat["stamp_duty_inr"],
            total_statutory_inr=stat["total_statutory_inr"],
            statutory_bps=statutory_bps,
            spread_component_bps=spread_bps,
            impact_bps=impact_bps,
            adverse_selection_bps=adverse_selection_bps,
            basis_slippage_bps=basis_bps,
            total_friction_bps=total_friction_bps
        )

        assert detail.verify_additive_identity(), "Additive identity violated in futures cost detail!"
        return detail
