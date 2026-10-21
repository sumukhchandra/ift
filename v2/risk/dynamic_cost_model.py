"""
Dynamic Execution Cost & Friction Stress Model for AlphaNSE V2.
Models total round-trip trade friction dynamically:
  Total Cost = Statutory Taxes & Charges (IndiaCostEngine)
             + Trade Notional
             + Bid-Ask Spread
             + Size-Dependent Market Impact Slippage
             + Adverse Selection (for passive orders)
Evaluates friction across stress multipliers (1.0x, 1.25x, 1.50x, 2.00x)
and across execution modes (AGGRESSIVE, PASSIVE, CONSERVATIVE_PASSIVE).
"""

import logging
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass
import numpy as np
from .cost_engine import IndiaCostEngine, CostBreakdown

logger = logging.getLogger(__name__)


class ExecutionMode(str, Enum):
    AGGRESSIVE = "AGGRESSIVE"                      # Marketable order: pays full spread + impact slippage
    PASSIVE = "PASSIVE"                            # Limit order: captures half spread, P_fill=0.65, +1.0 bps adverse selection
    CONSERVATIVE_PASSIVE = "CONSERVATIVE_PASSIVE"  # Limit order: lower fill P_fill=0.45, +2.0 bps adverse selection


@dataclass(frozen=True)
class TradeCostDetail:
    statutory_cost_rupees: float
    statutory_bps: float
    spread_bps: float
    slippage_bps: float
    adverse_selection_bps: float
    execution_friction_bps: float
    total_cost_bps: float
    stress_multiplier: float
    total_cost_rupees: float
    fill_probability: float
    execution_mode: str
    partial_fill_component_bps: float = 0.0
    cost_per_attempted_trade_bps: float = 0.0
    cost_per_completed_trade_bps: float = 0.0
    spread_component_bps: float = 0.0


class DynamicCostModel:
    """
    Computes trade-level execution costs combining statutory taxes, bid-ask spread,
    and market-impact slippage, with stress multipliers for robust edge evaluation.
    """

    def __init__(
        self,
        base_half_spread_bps: float = 1.0,
        base_impact_bps: Optional[float] = None,
        impact_coefficient_bps: Optional[float] = None,
        base_slippage_bps: Optional[float] = None,
        impact_coefficient: Optional[float] = None
    ):
        self.cost_engine = IndiaCostEngine()
        self.base_half_spread_bps = base_half_spread_bps
        self.base_impact_bps = base_impact_bps if base_impact_bps is not None else (base_slippage_bps if base_slippage_bps is not None else 2.0)
        if impact_coefficient_bps is not None:
            self.impact_coefficient_bps = impact_coefficient_bps
        elif impact_coefficient is not None:
            self.impact_coefficient_bps = impact_coefficient * 100.0 if impact_coefficient < 1.0 else impact_coefficient
        else:
            self.impact_coefficient_bps = 5.0

    def compute_trade_cost(
        self,
        price: float,
        quantity: int,
        bar_volume: float = 50000.0,
        stress_multiplier: float = 1.0,
        execution_mode: ExecutionMode = ExecutionMode.AGGRESSIVE,
        participation_rate_fraction: Optional[float] = None
    ) -> TradeCostDetail:
        """
        Calculates dynamic round-trip transaction costs for a specific trade.
        Formula:
          impact_bps = base_impact_bps + impact_coefficient_bps * sqrt(participation_rate_fraction)
        """
        if price <= 0 or quantity <= 0:
            return TradeCostDetail(
                statutory_cost_rupees=0.0,
                statutory_bps=0.0,
                spread_bps=0.0,
                slippage_bps=0.0,
                adverse_selection_bps=0.0,
                execution_friction_bps=0.0,
                total_cost_bps=0.0,
                stress_multiplier=stress_multiplier,
                total_cost_rupees=0.0,
                fill_probability=1.0,
                execution_mode=str(execution_mode)
            )

        notional = price * quantity
        bar_notional = max(price * bar_volume, notional * 2.0)

        # 1. Statutory taxes and brokerage via IndiaCostEngine (excluding slippage)
        stat_breakdown = self.cost_engine.calculate_roundtrip_cost(
            capital=notional,
            gross_return=0.0,
            slippage_bps=0.0
        )
        statutory_rupees = stat_breakdown.fixed_or_capped_cost + stat_breakdown.proportional_statutory_cost
        statutory_bps = (statutory_rupees / notional) * 10000.0

        # 2. Participation Rate Fraction (explicit or calculated)
        if participation_rate_fraction is None:
            participation = min(1.0, notional / bar_notional)
        else:
            participation = min(1.0, max(0.0, participation_rate_fraction))

        # 3. Market Impact Slippage: base + coefficient * sqrt(participation)
        impact_bps = self.base_impact_bps + (self.impact_coefficient_bps * np.sqrt(participation))

        # 4. Spread, Impact, Adverse Selection, and Partial Fill depending on Execution Mode
        if execution_mode == ExecutionMode.AGGRESSIVE:
            spread_bps = self.base_half_spread_bps * 2.0  # Pay 2 * half-spread roundtrip
            adverse_selection_bps = 0.0
            fill_probability = 1.0
            slippage_bps = impact_bps
            partial_fill_penalty = 0.0
        elif execution_mode == ExecutionMode.PASSIVE:
            # Earn half-spread on entry, pay half-spread on exit -> net spread = 1 * half-spread
            spread_bps = self.base_half_spread_bps * 1.0
            adverse_selection_bps = 1.0  # Limit orders suffer adverse selection when filled
            fill_probability = 0.65      # Empirical fill rate for passive resting orders
            slippage_bps = impact_bps * 0.5
            partial_fill_penalty = 0.20 * (self.base_half_spread_bps * 1.0 + impact_bps * 0.5)
        elif execution_mode == ExecutionMode.CONSERVATIVE_PASSIVE:
            spread_bps = self.base_half_spread_bps * 1.0
            adverse_selection_bps = 2.0  # Higher adverse selection penalty
            fill_probability = 0.45      # Lower queue fill probability
            slippage_bps = impact_bps * 0.5
            partial_fill_penalty = 0.40 * (self.base_half_spread_bps * 1.0 + impact_bps * 0.5)
        else:
            raise ValueError(f"Unknown execution mode: {execution_mode}")

        # 5. Uncertain execution friction stressed by multiplier
        nominal_execution_friction_bps = spread_bps + slippage_bps + adverse_selection_bps + partial_fill_penalty
        stressed_execution_friction_bps = nominal_execution_friction_bps * stress_multiplier

        # Display components rounded consistently under stress_multiplier
        stat_rounded = round(statutory_bps, 2)
        spread_rounded = round(spread_bps * stress_multiplier, 2)
        slip_rounded = round(slippage_bps * stress_multiplier, 2)
        adverse_rounded = round(adverse_selection_bps * stress_multiplier, 2)
        partial_rounded = round(partial_fill_penalty * stress_multiplier, 2)
        exec_rounded = round(stressed_execution_friction_bps, 2)

        total_cost_bps = round(stat_rounded + exec_rounded, 2)
        total_cost_rupees = (total_cost_bps / 10000.0) * notional
        cost_per_attempted = round(total_cost_bps * fill_probability, 2)

        return TradeCostDetail(
            statutory_cost_rupees=round(statutory_rupees, 4),
            statutory_bps=stat_rounded,
            spread_bps=spread_rounded,
            slippage_bps=slip_rounded,
            adverse_selection_bps=adverse_rounded,
            execution_friction_bps=exec_rounded,
            total_cost_bps=total_cost_bps,
            stress_multiplier=stress_multiplier,
            total_cost_rupees=round(total_cost_rupees, 4),
            fill_probability=fill_probability,
            execution_mode=str(execution_mode),
            partial_fill_component_bps=partial_rounded,
            cost_per_attempted_trade_bps=cost_per_attempted,
            cost_per_completed_trade_bps=total_cost_bps,
            spread_component_bps=spread_rounded
        )
