"""
Configurable Broker Economics & Cost Scenario Registry for AlphaNSE V2.
Decouples broker fee structures from Indian statutory levies:
  1. BrokerCostConfig: Configurable brokerage rates, caps, and exchange/statutory levies.
  2. CostScenario: Structured representation of statutory vs execution friction.
  3. CostScenarioRegistry: Named scenarios (STATUTORY_ONLY, BASE_AGGRESSIVE, STRESSED_AGGRESSIVE,
     PASSIVE, CONSERVATIVE_PASSIVE) across broker templates.
"""

from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import hashlib
import json


class BrokerageType(str, Enum):
    PERCENT_WITH_CAP = "PERCENT_WITH_CAP"  # min(rate * notional, max_per_order)
    FLAT_PER_ORDER = "FLAT_PER_ORDER"      # flat fee per executed order
    PURE_PERCENT = "PURE_PERCENT"          # rate * notional without cap
    ZERO_BROKERAGE = "ZERO_BROKERAGE"      # zero commission models


@dataclass(frozen=True)
class BrokerCostConfig:
    name: str = "Zerodha_Default"
    brokerage_type: BrokerageType = BrokerageType.PERCENT_WITH_CAP
    brokerage_rate: float = 0.0003          # 0.03%
    brokerage_max_per_order: float = 20.0   # Rs. 20 per order
    minimum_brokerage: float = 0.0
    exchange_rate: float = 0.0000307        # NSE Cash: 0.00307% per side
    sebi_rate: float = 0.000001             # Rs. 10 per crore (0.0001%)
    stt_rate_sell: float = 0.00025          # 0.025% on sell side (non-delivery)
    stamp_rate_buy: float = 0.00003         # 0.003% on buy side (non-delivery)
    gst_rate: float = 0.18                  # 18% GST on (Brokerage + Exchange + SEBI)

    def calculate_brokerage(self, notional: float) -> float:
        """Calculates broker commission per order side."""
        if self.brokerage_type == BrokerageType.PERCENT_WITH_CAP:
            val = max(self.minimum_brokerage, min(notional * self.brokerage_rate, self.brokerage_max_per_order))
        elif self.brokerage_type == BrokerageType.FLAT_PER_ORDER:
            val = self.brokerage_max_per_order
        elif self.brokerage_type == BrokerageType.PURE_PERCENT:
            val = notional * self.brokerage_rate
        elif self.brokerage_type == BrokerageType.ZERO_BROKERAGE:
            val = 0.0
        else:
            val = min(notional * self.brokerage_rate, self.brokerage_max_per_order)
        return round(val, 4)

    def calculate_statutory_charges(self, buy_notional: float, sell_notional: float) -> Dict[str, float]:
        """
        Calculates all statutory fees and taxes for a complete roundtrip.
        """
        buy_brokerage = self.calculate_brokerage(buy_notional)
        sell_brokerage = self.calculate_brokerage(sell_notional)
        total_brokerage = buy_brokerage + sell_brokerage

        stt = sell_notional * self.stt_rate_sell
        exchange = (buy_notional + sell_notional) * self.exchange_rate
        sebi = (buy_notional + sell_notional) * self.sebi_rate
        gst = (total_brokerage + exchange + sebi) * self.gst_rate
        stamp = buy_notional * self.stamp_rate_buy

        statutory_total = total_brokerage + stt + exchange + sebi + gst + stamp
        notional_base = max(1.0, buy_notional)
        statutory_bps = (statutory_total / notional_base) * 10000.0

        return {
            "brokerage": round(total_brokerage, 4),
            "stt": round(stt, 4),
            "exchange": round(exchange, 4),
            "sebi": round(sebi, 4),
            "gst": round(gst, 4),
            "stamp": round(stamp, 4),
            "total_rupees": round(statutory_total, 4),
            "total_bps": round(statutory_bps, 2)
        }


class ScenarioType(str, Enum):
    STATUTORY_ONLY = "STATUTORY_ONLY"
    BASE_AGGRESSIVE = "BASE_AGGRESSIVE"
    STRESSED_AGGRESSIVE = "STRESSED_AGGRESSIVE"
    PASSIVE = "PASSIVE"
    CONSERVATIVE_PASSIVE = "CONSERVATIVE_PASSIVE"


@dataclass(frozen=True)
class CostScenario:
    scenario_type: ScenarioType
    broker_config: BrokerCostConfig
    base_spread_bps: float
    base_impact_bps: float
    impact_coefficient_bps: float
    fill_probability: float
    partial_fill_rate: float
    adverse_selection_bps: float
    slippage_multiplier: float
    unfilled_policy: str = "MARKET_CROSS"  # "MARKET_CROSS" or "CANCEL"
    cost_model_version: str = "v2.2_execution_tree"

    def compute_total_cost_bps(self, notional: float = 5000.0, participation_fraction: float = 0.0002) -> Dict[str, float]:
        """
        Decomposes total roundtrip friction via an explicit probability-weighted Execution Tree:
          Gross Return -> Statutory Friction -> Execution Friction -> Net Return
        Guarantees:
          total_expected_cost_bps == statutory + spread + impact + adverse_selection + partial_fill
        """
        stat_dict = self.broker_config.calculate_statutory_charges(notional, notional)
        stat_bps = stat_dict["total_bps"]

        if self.scenario_type == ScenarioType.STATUTORY_ONLY:
            return {
                "statutory_bps": stat_bps,
                "spread_component_bps": 0.0,
                "spread_bps": 0.0,
                "impact_bps": 0.0,
                "slippage_bps": 0.0,
                "adverse_selection_bps": 0.0,
                "partial_fill_component_bps": 0.0,
                "fill_probability": 1.0,
                "cost_per_completed_trade_bps": stat_bps,
                "cost_per_attempted_trade_bps": stat_bps,
                "execution_friction_bps": 0.0,
                "total_cost_bps": stat_bps,
                "total_expected_cost_bps": stat_bps,
                "cost_model_version": self.cost_model_version
            }

        # Market impact calculation
        raw_impact_bps = (self.base_impact_bps + (self.impact_coefficient_bps * (participation_fraction ** 0.5))) * self.slippage_multiplier

        if self.scenario_type in [ScenarioType.BASE_AGGRESSIVE, ScenarioType.STRESSED_AGGRESSIVE]:
            spread_bps = self.base_spread_bps * self.slippage_multiplier
            impact_bps = raw_impact_bps
            adverse_bps = 0.0
            partial_fill_bps = 0.0
            fill_prob = 1.0
        elif self.scenario_type in [ScenarioType.PASSIVE, ScenarioType.CONSERVATIVE_PASSIVE]:
            # Passive resting orders earn half-spread on entry and avoid immediate market impact
            spread_bps = self.base_spread_bps * 0.5
            impact_bps = raw_impact_bps * 0.5
            adverse_bps = self.adverse_selection_bps
            fill_prob = self.fill_probability

            # Unfilled fraction completion via execution tree
            if self.unfilled_policy == "MARKET_CROSS":
                spread_diff = (self.base_spread_bps * self.slippage_multiplier) - spread_bps
                impact_diff = raw_impact_bps - impact_bps
                unfilled_fraction = max(0.0, 1.0 - self.partial_fill_rate)
                partial_fill_bps = unfilled_fraction * (spread_diff + impact_diff)
            else:
                partial_fill_bps = 0.0
        else:
            spread_bps = self.base_spread_bps
            impact_bps = raw_impact_bps
            adverse_bps = 0.0
            partial_fill_bps = 0.0
            fill_prob = 1.0

        exec_friction_bps = spread_bps + impact_bps + adverse_bps + partial_fill_bps
        stat_rounded = round(stat_bps, 2)
        spread_rounded = round(spread_bps, 2)
        impact_rounded = round(impact_bps, 2)
        adverse_rounded = round(adverse_bps, 2)
        partial_rounded = round(partial_fill_bps, 2)

        # Ensure total identically equals the sum of its displayed components
        total_rounded = round(stat_rounded + spread_rounded + impact_rounded + adverse_rounded + partial_rounded, 2)
        cost_per_attempted = round(total_rounded * fill_prob, 2)
        exec_friction_rounded = round(spread_rounded + impact_rounded + adverse_rounded + partial_rounded, 2)

        return {
            "statutory_bps": stat_rounded,
            "spread_component_bps": spread_rounded,
            "spread_bps": spread_rounded,
            "impact_bps": impact_rounded,
            "slippage_bps": impact_rounded,
            "adverse_selection_bps": adverse_rounded,
            "partial_fill_component_bps": partial_rounded,
            "fill_probability": fill_prob,
            "cost_per_completed_trade_bps": total_rounded,
            "cost_per_attempted_trade_bps": cost_per_attempted,
            "execution_friction_bps": exec_friction_rounded,
            "total_cost_bps": total_rounded,
            "total_expected_cost_bps": total_rounded,
            "cost_model_version": self.cost_model_version
        }


class CostScenarioRegistry:
    """
    Standardized registry of cost scenarios for reproducible research and backtesting.
    """

    @classmethod
    def get_scenario(
        cls,
        scenario_type: ScenarioType,
        broker_config: Optional[BrokerCostConfig] = None
    ) -> CostScenario:
        broker = broker_config or BrokerCostConfig()

        if scenario_type == ScenarioType.STATUTORY_ONLY:
            return CostScenario(
                scenario_type=scenario_type,
                broker_config=broker,
                base_spread_bps=0.0,
                base_impact_bps=0.0,
                impact_coefficient_bps=0.0,
                fill_probability=1.0,
                partial_fill_rate=1.0,
                adverse_selection_bps=0.0,
                slippage_multiplier=1.0
            )
        elif scenario_type == ScenarioType.BASE_AGGRESSIVE:
            return CostScenario(
                scenario_type=scenario_type,
                broker_config=broker,
                base_spread_bps=2.0,
                base_impact_bps=2.0,
                impact_coefficient_bps=5.0,
                fill_probability=1.0,
                partial_fill_rate=1.0,
                adverse_selection_bps=0.0,
                slippage_multiplier=1.0
            )
        elif scenario_type == ScenarioType.STRESSED_AGGRESSIVE:
            return CostScenario(
                scenario_type=scenario_type,
                broker_config=broker,
                base_spread_bps=2.0,
                base_impact_bps=2.0,
                impact_coefficient_bps=5.0,
                fill_probability=1.0,
                partial_fill_rate=1.0,
                adverse_selection_bps=0.0,
                slippage_multiplier=1.5
            )
        elif scenario_type == ScenarioType.PASSIVE:
            return CostScenario(
                scenario_type=scenario_type,
                broker_config=broker,
                base_spread_bps=2.0,
                base_impact_bps=2.0,
                impact_coefficient_bps=5.0,
                fill_probability=0.65,
                partial_fill_rate=0.80,
                adverse_selection_bps=1.0,
                slippage_multiplier=1.0
            )
        elif scenario_type == ScenarioType.CONSERVATIVE_PASSIVE:
            return CostScenario(
                scenario_type=scenario_type,
                broker_config=broker,
                base_spread_bps=2.0,
                base_impact_bps=2.0,
                impact_coefficient_bps=5.0,
                fill_probability=0.45,
                partial_fill_rate=0.60,
                adverse_selection_bps=2.0,
                slippage_multiplier=1.0
            )
        else:
            raise ValueError(f"Unknown scenario_type: {scenario_type}")
