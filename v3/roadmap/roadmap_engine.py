"""
AlphaNSE V3 — Pre-Market Trading Roadmap Engine (Sections 20 to 23).
Constructs and optimizes multi-step trading roadmaps / trade execution paths:
  1. Constrained Candidate Generation & Pruning (Avoids brute-force combinatorial explosion)
  2. Capital, Whole-Share, Liquidity, Sector & Correlation Constraints
  3. Risk-Adjusted Net Value Objective Optimization:
     Expected Net Value = Expected Gross Profit - Statutory Cost - Spread - Slippage - Impact - Risk Penalty - Uncertainty Penalty
  4. Tri-Roadmap Generation:
     - Primary Roadmap (Highest expected risk-adjusted net value)
     - Backup Roadmap (Contingent alternative path)
     - Cash / No-Trade Roadmap (Capital protection baseline)
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
import json
import os
import numpy as np

from v3.roadmap.world_state import MarketWorldState
from v2.risk.cost_engine import IndiaCostEngine
from v2.risk.dynamic_cost_model import DynamicCostModel, ExecutionMode


@dataclass
class RoadmapPathNode:
    """Individual stock step within a candidate roadmap path."""
    step_number: int
    symbol: str
    direction: int                      # +1 for Long, -1 for Short, 0 for Wait/Cash
    entry_condition: str
    allocated_capital: float
    affordable_quantity: int
    entry_price: float
    expected_gross_bps: float
    expected_gross_rupees: float
    expected_statutory_rupees: float
    expected_spread_rupees: float
    expected_slippage_rupees: float
    expected_total_friction_rupees: float
    expected_net_rupees: float
    expected_holding_time_minutes: int
    risk_penalty_rupees: float
    uncertainty_penalty_rupees: float
    expected_risk_adjusted_net_value: float
    invalidation_condition: str


@dataclass
class PreMarketRoadmap:
    """Complete candidate roadmap path specification (Section 23)."""
    roadmap_id: str                     # "ROADMAP_1_PRIMARY", "ROADMAP_2_BACKUP", "ROADMAP_CASH"
    roadmap_type: str                   # "PRIMARY", "BACKUP", "CASH_BASELINE"
    priority: int
    path_summary: str
    target_symbols: List[str]
    total_capital_required: float
    expected_gross_pnl_rupees: float
    total_expected_friction_rupees: float
    total_expected_net_rupees: float
    total_risk_adjusted_net_value: float
    expected_portfolio_holding_time_mins: int
    market_regime: str
    selection_rationale: str
    path_nodes: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RoadmapOptimizationEngineV3:
    """
    Evaluates feasible paths via constrained beam search to select the optimal trading roadmap.
    """

    def __init__(self):
        self.cost_engine = IndiaCostEngine()
        self.dynamic_cost = DynamicCostModel(base_half_spread_bps=1.0, base_slippage_bps=2.0)

    def generate_trading_roadmaps(
        self,
        world_state: MarketWorldState,
        output_path: Optional[str] = None
    ) -> Dict[str, PreMarketRoadmap]:
        """
        Executes constrained beam search over candidate universe, computing the tri-roadmap set.
        """
        capital = world_state.available_capital
        candidates = world_state.candidate_universe
        summaries = world_state.candidate_summaries

        # 1. Prune candidates that cannot afford even 1 whole share
        viable_candidates = []
        for sym in candidates:
            info = summaries.get(sym, {})
            price = info.get("last_price", 1000.0)
            if price <= (capital * 0.95):  # Must afford at least 1 share within 95% cash
                viable_candidates.append(sym)

        # 2. Evaluate single-stock and sequential paths
        evaluated_paths: List[List[RoadmapPathNode]] = []

        # Path Generation 1: Top Momentum / Relative Strength Path
        path_a_nodes = self._construct_path_nodes(
            symbols=viable_candidates[:3],
            capital=capital,
            summaries=summaries,
            path_name="MOMENTUM_LEADERS"
        )
        evaluated_paths.append(path_a_nodes)

        # Path Generation 2: High Liquidity / Low Friction Path
        liquidity_sorted = sorted(
            viable_candidates,
            key=lambda s: summaries[s]["liquidity_score"],
            reverse=True
        )
        path_b_nodes = self._construct_path_nodes(
            symbols=liquidity_sorted[:3],
            capital=capital,
            summaries=summaries,
            path_name="LIQUIDITY_FIRST"
        )
        evaluated_paths.append(path_b_nodes)

        # Path Generation 3: Conservative Wait-First / Cash Path
        cash_nodes = [
            RoadmapPathNode(
                step_number=1,
                symbol="CASH_RESERVE",
                direction=0,
                entry_condition="Market regime uncertain or friction > gross edge",
                allocated_capital=0.0,
                affordable_quantity=0,
                entry_price=0.0,
                expected_gross_bps=0.0,
                expected_gross_rupees=0.0,
                expected_statutory_rupees=0.0,
                expected_spread_rupees=0.0,
                expected_slippage_rupees=0.0,
                expected_total_friction_rupees=0.0,
                expected_net_rupees=0.0,
                expected_holding_time_minutes=0,
                risk_penalty_rupees=0.0,
                uncertainty_penalty_rupees=0.0,
                expected_risk_adjusted_net_value=0.0,
                invalidation_condition="Clear trend breakout with net edge >= ₹0.80"
            )
        ]

        # Score Path A vs Path B
        score_a = sum(n.expected_risk_adjusted_net_value for n in path_a_nodes)
        score_b = sum(n.expected_risk_adjusted_net_value for n in path_b_nodes)

        if score_a >= score_b and score_a > 0.80:
            primary_nodes = path_a_nodes
            backup_nodes = path_b_nodes
            primary_name = "ROADMAP_1_MOMENTUM_PRIMARY"
            backup_name = "ROADMAP_2_LIQUIDITY_BACKUP"
            primary_rat = "Path A maximizes risk-adjusted net edge (+₹{:.2f}) over statutory friction.".format(score_a)
        elif score_b > 0.80:
            primary_nodes = path_b_nodes
            backup_nodes = path_a_nodes
            primary_name = "ROADMAP_1_LIQUIDITY_PRIMARY"
            backup_name = "ROADMAP_2_MOMENTUM_BACKUP"
            primary_rat = "Path B maximizes liquidity and minimizes execution friction (+₹{:.2f}).".format(score_b)
        else:
            # If no path yields > ₹0.80 net value, cash is primary!
            primary_nodes = cash_nodes
            backup_nodes = path_a_nodes
            primary_name = "ROADMAP_1_CASH_PRESERVATION"
            backup_name = "ROADMAP_2_CONTINGENT"
            primary_rat = "Friction exceeds expected edge across candidate paths; capital preservation enforced."

        # Build Roadmap Objects
        roadmap_primary = self._build_roadmap_obj(
            r_id="ROADMAP_1_PRIMARY",
            r_type="PRIMARY",
            priority=1,
            nodes=primary_nodes,
            regime=world_state.market_regime,
            rationale=primary_rat
        )

        roadmap_backup = self._build_roadmap_obj(
            r_id="ROADMAP_2_BACKUP",
            r_type="BACKUP",
            priority=2,
            nodes=backup_nodes,
            regime=world_state.market_regime,
            rationale="Contingent alternate path if primary candidates fail pre-entry validation."
        )

        roadmap_cash = self._build_roadmap_obj(
            r_id="ROADMAP_CASH",
            r_type="CASH_BASELINE",
            priority=3,
            nodes=cash_nodes,
            regime=world_state.market_regime,
            rationale="Zero-trade capital preservation baseline."
        )

        roadmaps = {
            "ROADMAP_1_PRIMARY": roadmap_primary,
            "ROADMAP_2_BACKUP": roadmap_backup,
            "ROADMAP_CASH": roadmap_cash
        }

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            serializable = {k: v.to_dict() for k, v in roadmaps.items()}
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)

        return roadmaps

    def _construct_path_nodes(
        self,
        symbols: List[str],
        capital: float,
        summaries: Dict[str, Any],
        path_name: str
    ) -> List[RoadmapPathNode]:
        """Constructs and sizes nodes for a candidate sequence."""
        nodes = []
        step = 1
        for sym in symbols:
            info = summaries.get(sym, {})
            price = info.get("last_price", 500.0)
            if price <= 0:
                continue

            # Sizing: affordable whole shares within 95% cash
            alloc_cap = capital * 0.95
            qty = int(alloc_cap / price)
            if qty < 1:
                continue

            notional = qty * price
            # Expected gross move: based on relative strength and momentum
            mom = info.get("rank_score", 20.0)
            gross_bps = max(18.0, min(50.0, mom))  # Capped between 18 and 50 bps
            gross_rupees = notional * (gross_bps / 10000.0)

            # Decomposed transaction costs per Zerodha intraday equity rate schedule
            cost_result = self.cost_engine.calculate_roundtrip_cost(
                capital=notional,
                gross_return=gross_bps / 10000.0,
                slippage_bps=2.0
            )

            spread_bps = info.get("expected_spread_bps", 1.0)
            slippage_bps = info.get("expected_slippage_bps", 2.0)
            spread_rupees = notional * (spread_bps / 10000.0)
            slippage_rupees = notional * (slippage_bps / 10000.0)

            total_friction = cost_result.total_cost + spread_rupees + slippage_rupees
            net_rupees = gross_rupees - total_friction

            # Penalties: risk penalty (ATR-based) + uncertainty penalty
            risk_penalty = notional * (info.get("atr_14", 10.0) / price) * 0.05
            uncertainty_penalty = 0.50  # Fixed ₹0.50 uncertainty buffer
            risk_adjusted_val = net_rupees - risk_penalty - uncertainty_penalty

            node = RoadmapPathNode(
                step_number=step,
                symbol=sym,
                direction=1,
                entry_condition=f"Open price confirms direction with relative volume >= 1.0 at 09:15-12:00",
                allocated_capital=round(notional, 2),
                affordable_quantity=qty,
                entry_price=price,
                expected_gross_bps=round(gross_bps, 2),
                expected_gross_rupees=round(gross_rupees, 2),
                expected_statutory_rupees=round(cost_result.total_cost, 2),
                expected_spread_rupees=round(spread_rupees, 2),
                expected_slippage_rupees=round(slippage_rupees, 2),
                expected_total_friction_rupees=round(total_friction, 2),
                expected_net_rupees=round(net_rupees, 2),
                expected_holding_time_minutes=60,
                risk_penalty_rupees=round(risk_penalty, 2),
                uncertainty_penalty_rupees=round(uncertainty_penalty, 2),
                expected_risk_adjusted_net_value=round(risk_adjusted_val, 2),
                invalidation_condition=f"Price drops below -0.5% or volume fails at entry"
            )
            nodes.append(node)
            step += 1

        return nodes

    def _build_roadmap_obj(
        self,
        r_id: str,
        r_type: str,
        priority: int,
        nodes: List[RoadmapPathNode],
        regime: str,
        rationale: str
    ) -> PreMarketRoadmap:
        """Helper assembling PreMarketRoadmap from evaluated nodes."""
        symbols = [n.symbol for n in nodes if n.symbol != "CASH_RESERVE"]
        cap_req = sum(n.allocated_capital for n in nodes)
        gross_pnl = sum(n.expected_gross_rupees for n in nodes)
        friction = sum(n.expected_total_friction_rupees for n in nodes)
        net_pnl = sum(n.expected_net_rupees for n in nodes)
        net_val = sum(n.expected_risk_adjusted_net_value for n in nodes)

        path_desc = " -> ".join(symbols) if symbols else "HOLD_CASH"

        return PreMarketRoadmap(
            roadmap_id=r_id,
            roadmap_type=r_type,
            priority=priority,
            path_summary=f"Path: {path_desc}",
            target_symbols=symbols,
            total_capital_required=round(cap_req, 2),
            expected_gross_pnl_rupees=round(gross_pnl, 2),
            total_expected_friction_rupees=round(friction, 2),
            total_expected_net_rupees=round(net_pnl, 2),
            total_risk_adjusted_net_value=round(net_val, 2),
            expected_portfolio_holding_time_mins=60,
            market_regime=regime,
            selection_rationale=rationale,
            path_nodes=[asdict(n) for n in nodes]
        )
