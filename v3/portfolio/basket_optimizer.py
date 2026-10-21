"""
AlphaNSE V3 — Multi-Stock Portfolio Basket Optimization Engine.
Evaluates the complete candidate stock universe across all 6 models, explores the full
feasible multi-stock portfolio space (baskets of size 0, 1, 2, 3, ... up to HARD_MAX_POSITION_COUNT),
and dynamically allocates capital to maximize expected risk-adjusted net value.

KEY PRINCIPLES:
1. FULL UNIVERSE ANALYSIS: All 6 models evaluate every candidate stock in the universe.
2. DYNAMIC BASKET SIZING: Position count (0, 1, 2, 3, ...) is an OUTPUT of the portfolio
   optimizer, not a hardcoded forcing constraint.
3. CONSTRAINED FEASIBILITY: Evaluates whole-share affordability, capital budget, minimum
   cash buffer, statutory taxes, spread, slippage, and market impact.
4. RISK-ADJUSTED NET VALUE OBJECTIVE:
   Objective = Expected Gross ₹ - Statutory Fees - Spread - Slippage - Impact
             - Portfolio Volatility Penalty - Sector Concentration Penalty - Model Disagreement Penalty
5. MULTI-BASKET OUTPUT:
   - PRIMARY BASKET (Optimal feasible path)
   - BACKUP BASKET (Contingent alternate path)
   - CASH BASELINE (Zero-trade capital preservation)
6. NO HINDSIGHT: Optimization uses strictly pre-market decision-timestamp information.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple
import itertools
import math
import numpy as np

from v2.risk.cost_engine import IndiaCostEngine, CostBreakdown
from v3.config.v3_config import (
    INITIAL_CAPITAL,
    MIN_CASH_BUFFER_RUPEES,
    MIN_NET_EDGE_RUPEES,
    MIN_NET_EDGE_BPS
)


HARD_MAX_POSITION_COUNT: int = 5  # Configurable safety ceiling


@dataclass
class PositionAllocation:
    """Individual stock allocation within a candidate portfolio basket."""
    symbol: str
    quantity: int
    price: float
    notional: float
    expected_gross_bps: float
    expected_gross_rupees: float
    brokerage_rupees: float
    stt_rupees: float
    exchange_charges_rupees: float
    sebi_charges_rupees: float
    stamp_duty_rupees: float
    gst_rupees: float
    statutory_cost_rupees: float
    spread_bps: float
    spread_rupees: float
    slippage_bps: float
    slippage_rupees: float
    impact_bps: float
    impact_rupees: float
    total_friction_rupees: float
    expected_net_rupees: float
    expected_net_bps: float
    expected_holding_time_minutes: int
    model_consensus_strength: str
    supporting_models: List[str]
    contradicting_models: List[str]
    sector: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PortfolioBasket:
    """Complete candidate portfolio basket specification."""
    basket_id: str                      # e.g. "BASKET_AXISBANK_TATACAP", "BASKET_CASH"
    basket_type: str                    # "PRIMARY", "BACKUP", "CASH_BASELINE", "CANDIDATE"
    position_count: int                 # 0, 1, 2, 3, ...
    selected_symbols: List[str]
    positions: List[PositionAllocation]
    total_capital_deployed: float
    reserved_cash: float
    total_expected_gross_rupees: float
    total_statutory_cost_rupees: float
    total_spread_rupees: float
    total_slippage_rupees: float
    total_impact_rupees: float
    total_expected_cost_rupees: float
    total_expected_net_rupees: float
    expected_net_bps: float
    portfolio_risk_bps: float
    expected_holding_time_minutes: int
    sector_concentration_penalty: float
    disagreement_penalty: float
    volatility_risk_penalty: float
    total_penalties_rupees: float
    risk_adjusted_net_value: float
    reason_for_selection: str
    is_feasible: bool = True
    invalidation_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["positions"] = [p.to_dict() if isinstance(p, PositionAllocation) else p for p in self.positions]
        return d


class PortfolioBasketOptimizerV3:
    """
    Evaluates the full feasible multi-stock basket space to find the optimal capital allocation.
    """

    def __init__(
        self,
        initial_capital: float = INITIAL_CAPITAL,
        min_cash_buffer_rupees: float = MIN_CASH_BUFFER_RUPEES,
        min_net_edge_rupees: float = MIN_NET_EDGE_RUPEES,
        min_net_edge_bps: float = MIN_NET_EDGE_BPS,
        hard_max_position_count: int = HARD_MAX_POSITION_COUNT
    ):
        self.initial_capital = initial_capital
        self.min_cash_buffer_rupees = min_cash_buffer_rupees
        self.max_deployable_capital = initial_capital - min_cash_buffer_rupees
        self.min_net_edge_rupees = min_net_edge_rupees
        self.min_net_edge_bps = min_net_edge_bps
        self.hard_max_position_count = hard_max_position_count
        self.cost_engine = IndiaCostEngine()

    def optimize_portfolio_baskets(
        self,
        candidate_summaries: Dict[str, Any],
        consensus_decisions: Dict[str, Any],
        correlation_matrix: Optional[Dict[str, Dict[str, float]]] = None,
        available_capital: Optional[float] = None,
        hard_max_positions: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Explores all feasible combinations of size 0, 1, 2, ..., hard_max_positions.
        Selects PRIMARY BASKET, BACKUP BASKET, and CASH BASELINE.
        """
        capital = available_capital or self.initial_capital
        max_deployable = capital - self.min_cash_buffer_rupees
        max_k = hard_max_positions or self.hard_max_position_count

        # 1. Create CASH BASELINE basket (size 0)
        cash_basket = PortfolioBasket(
            basket_id="BASKET_CASH_BASELINE",
            basket_type="CASH_BASELINE",
            position_count=0,
            selected_symbols=[],
            positions=[],
            total_capital_deployed=0.0,
            reserved_cash=round(capital, 2),
            total_expected_gross_rupees=0.0,
            total_statutory_cost_rupees=0.0,
            total_spread_rupees=0.0,
            total_slippage_rupees=0.0,
            total_impact_rupees=0.0,
            total_expected_cost_rupees=0.0,
            total_expected_net_rupees=0.0,
            expected_net_bps=0.0,
            portfolio_risk_bps=0.0,
            expected_holding_time_minutes=0,
            sector_concentration_penalty=0.0,
            disagreement_penalty=0.0,
            volatility_risk_penalty=0.0,
            total_penalties_rupees=0.0,
            risk_adjusted_net_value=0.0,
            reason_for_selection="Capital protection baseline: 100% cash preserved.",
            is_feasible=True,
            invalidation_reasons=[]
        )

        # 2. Filter candidate universe for basic eligibility
        eligible_candidates = []
        for sym, c_dec in consensus_decisions.items():
            info = candidate_summaries.get(sym, {})
            price = info.get("last_price", 0.0)
            if price <= 0:
                continue

            # Must afford at least 1 whole share within max deployable cash
            if price > max_deployable:
                continue

            # Must have non-negative gross expected move
            exp_gross_bps = getattr(c_dec, "expected_gross_bps", c_dec.get("expected_gross_bps", 0.0) if isinstance(c_dec, dict) else 0.0)
            if exp_gross_bps <= 0:
                continue

            eligible_candidates.append(sym)

        # 3. Explore candidate combinations across basket sizes k = 1 to max_k
        evaluated_baskets: List[PortfolioBasket] = [cash_basket]
        max_search_k = min(len(eligible_candidates), max_k)

        for k in range(1, max_search_k + 1):
            for combo in itertools.combinations(eligible_candidates, k):
                basket = self._evaluate_single_basket(
                    symbols=list(combo),
                    candidate_summaries=candidate_summaries,
                    consensus_decisions=consensus_decisions,
                    correlation_matrix=correlation_matrix,
                    max_deployable=max_deployable,
                    total_capital=capital
                )
                evaluated_baskets.append(basket)

        # 4. Filter feasible vs infeasible baskets
        feasible_baskets = [b for b in evaluated_baskets if b.is_feasible and b.position_count > 0]

        # 5. Rank feasible baskets by risk-adjusted net value (RANV)
        feasible_baskets.sort(key=lambda b: b.risk_adjusted_net_value, reverse=True)

        # 6. Determine Primary and Backup Baskets
        if feasible_baskets and feasible_baskets[0].risk_adjusted_net_value >= self.min_net_edge_rupees:
            primary_basket = feasible_baskets[0]
            primary_basket.basket_type = "PRIMARY"
            primary_basket.reason_for_selection = (
                f"Selected as PRIMARY: Maximizes risk-adjusted net value (+₹{primary_basket.risk_adjusted_net_value:.2f}) "
                f"across {primary_basket.position_count} positions ({', '.join(primary_basket.selected_symbols)})."
            )

            # Find best distinct backup basket (non-identical symbol set)
            backup_basket = None
            primary_sym_set = set(primary_basket.selected_symbols)
            for b in feasible_baskets[1:]:
                if set(b.selected_symbols) != primary_sym_set:
                    backup_basket = b
                    break

            if backup_basket is None:
                # If no alternative distinct basket, fallback to cash
                backup_basket = cash_basket

            backup_basket.basket_type = "BACKUP"
            backup_basket.reason_for_selection = (
                f"Selected as BACKUP: Contingent alternative path (+₹{backup_basket.risk_adjusted_net_value:.2f} RANV)."
            )
        else:
            # If no feasible basket clears the net economic hurdle, Cash is Primary!
            import copy
            primary_basket = copy.deepcopy(cash_basket)
            primary_basket.basket_type = "PRIMARY"
            primary_basket.reason_for_selection = (
                "Preserved 100% Cash: No feasible multi-stock or single-stock basket cleared the ₹0.80 net-edge hurdle."
            )
            backup_basket = copy.deepcopy(feasible_baskets[0]) if feasible_baskets else copy.deepcopy(cash_basket)
            backup_basket.basket_type = "BACKUP"

        return {
            "primary_basket": primary_basket,
            "backup_basket": backup_basket,
            "cash_baseline": cash_basket,
            "total_baskets_evaluated": len(evaluated_baskets),
            "feasible_baskets_count": len(feasible_baskets),
            "all_evaluated_baskets": evaluated_baskets
        }

    def _evaluate_single_basket(
        self,
        symbols: List[str],
        candidate_summaries: Dict[str, Any],
        consensus_decisions: Dict[str, Any],
        correlation_matrix: Optional[Dict[str, Dict[str, float]]],
        max_deployable: float,
        total_capital: float
    ) -> PortfolioBasket:
        """Evaluates whole-share sizing, decomposed costs, risk, and penalties for one combination."""
        k = len(symbols)
        basket_id = f"BASKET_{'_'.join([s.split('.')[0] for s in symbols])}"

        # Step A: Check basic budget feasibility (must afford at least 1 share of each)
        min_cost_sum = sum(candidate_summaries.get(s, {}).get("last_price", 0.0) for s in symbols)
        if min_cost_sum > max_deployable:
            return PortfolioBasket(
                basket_id=basket_id,
                basket_type="CANDIDATE",
                position_count=k,
                selected_symbols=symbols,
                positions=[],
                total_capital_deployed=0.0,
                reserved_cash=total_capital,
                total_expected_gross_rupees=0.0,
                total_statutory_cost_rupees=0.0,
                total_spread_rupees=0.0,
                total_slippage_rupees=0.0,
                total_impact_rupees=0.0,
                total_expected_cost_rupees=0.0,
                total_expected_net_rupees=0.0,
                expected_net_bps=0.0,
                portfolio_risk_bps=0.0,
                expected_holding_time_minutes=0,
                sector_concentration_penalty=0.0,
                disagreement_penalty=0.0,
                volatility_risk_penalty=0.0,
                total_penalties_rupees=0.0,
                risk_adjusted_net_value=-999.0,
                reason_for_selection="Infeasible: Minimum 1-share cost exceeds deployable capital.",
                is_feasible=False,
                invalidation_reasons=[f"Minimum 1-share cost ₹{min_cost_sum:.2f} > Max Deployable ₹{max_deployable:.2f}"]
            )

        # Step B: Optimize Whole-Share Allocation (Conviction / Volatility Weighted)
        prices = {s: candidate_summaries[s]["last_price"] for s in symbols}
        gross_bps = {}
        confidences = {}
        atrs = {}
        sectors = {}
        supporting = {}
        contradicting = {}
        consensus_strengths = {}

        for s in symbols:
            c_dec = consensus_decisions[s]
            info = candidate_summaries[s]
            gross_bps[s] = getattr(c_dec, "expected_gross_bps", c_dec.get("expected_gross_bps", 0.0) if isinstance(c_dec, dict) else 0.0)
            confidences[s] = getattr(c_dec, "confidence", c_dec.get("confidence", 0.5) if isinstance(c_dec, dict) else 0.5)
            atrs[s] = info.get("atr_14", max(1.0, prices[s] * 0.015))
            sectors[s] = info.get("sector", "GENERAL")
            supporting[s] = getattr(c_dec, "supporting_models", c_dec.get("supporting_models", []) if isinstance(c_dec, dict) else [])
            contradicting[s] = getattr(c_dec, "contradicting_models", c_dec.get("contradicting_models", []) if isinstance(c_dec, dict) else [])
            consensus_strengths[s] = getattr(c_dec, "consensus_strength", c_dec.get("consensus_strength", "3/5") if isinstance(c_dec, dict) else "3/5")

        # Conviction weight: proportional to expected return * confidence / volatility
        weights = {}
        for s in symbols:
            vol_bps = (atrs[s] / prices[s]) * 10000.0
            conviction = max(1.0, gross_bps[s] * confidences[s])
            weights[s] = conviction / max(10.0, vol_bps)

        tot_w = sum(weights.values())
        norm_weights = {s: weights[s] / tot_w for s in symbols}

        # Sizing: Start with 1 share each, then greedily distribute remaining capital
        quantities = {s: 1 for s in symbols}
        current_deployed = sum(prices[s] * quantities[s] for s in symbols)

        # Cap any single position at 75% for multi-stock baskets
        max_pct = 0.95 if k == 1 else 0.75
        max_single_cap = max_deployable * max_pct

        # Greedily allocate remaining capital to highest weight stock that can afford whole shares
        sorted_by_pref = sorted(symbols, key=lambda s: norm_weights[s], reverse=True)
        improved = True
        while improved:
            improved = False
            for s in sorted_by_pref:
                p = prices[s]
                new_notional = (quantities[s] + 1) * p
                if (current_deployed + p <= max_deployable) and (new_notional <= max_single_cap):
                    quantities[s] += 1
                    current_deployed += p
                    improved = True
                    break

        # Step C: Compute Penny-for-Penny Decomposed Costs for each position
        positions: List[PositionAllocation] = []
        tot_gross_inr = 0.0
        tot_stat_inr = 0.0
        tot_spread_inr = 0.0
        tot_slip_inr = 0.0
        tot_impact_inr = 0.0
        tot_friction_inr = 0.0
        tot_net_inr = 0.0
        invalidation_reasons = []

        for s in symbols:
            q = quantities[s]
            p = prices[s]
            notional = round(q * p, 2)
            g_bps = gross_bps[s]
            g_inr = round(notional * (g_bps / 10000.0), 2)

            # Exact statutory fees via IndiaCostEngine
            cb: CostBreakdown = self.cost_engine.calculate_roundtrip_cost(
                capital=notional, gross_return=g_bps / 10000.0, slippage_bps=0.0
            )
            # Individual statutory breakdown
            brokerage = round(cb.brokerage, 2)
            stt = round(cb.stt, 2)
            exchange = round(cb.exchange_charges, 2)
            sebi = round(cb.sebi_fees, 2)
            stamp = round(cb.stamp_duty, 2)
            gst = round(cb.gst, 2)
            statutory_cost = round(brokerage + stt + exchange + sebi + stamp + gst, 2)

            # Execution friction: Spread + Slippage + Impact
            info = candidate_summaries[s]
            spr_bps = info.get("expected_spread_bps", 2.40)
            slip_bps = info.get("expected_slippage_bps", 2.00)
            # Size-dependent impact: sqrt(notional / bar_notional)
            bar_vol = info.get("bar_volume", 50000.0)
            bar_notional = max(p * bar_vol, notional * 2.0)
            part_rate = min(1.0, notional / bar_notional)
            impact_bps = round(2.0 + 5.0 * math.sqrt(part_rate), 2)

            spr_inr = round(notional * (spr_bps / 10000.0), 2)
            slip_inr = round(notional * (slip_bps / 10000.0), 2)
            impact_inr = round(notional * (impact_bps / 10000.0), 2)

            total_fric = round(statutory_cost + spr_inr + slip_inr + impact_inr, 2)
            net_inr = round(g_inr - total_fric, 2)
            net_bps = round((net_inr / notional) * 10000.0, 2) if notional > 0 else 0.0

            # Economic hurdle check for each stock in the basket
            if net_inr < self.min_net_edge_rupees:
                invalidation_reasons.append(
                    f"{s} fails hurdle: Expected Net ₹{net_inr:.2f} < Min ₹{self.min_net_edge_rupees:.2f}"
                )
            if net_bps <= self.min_net_edge_bps:
                invalidation_reasons.append(
                    f"{s} fails bps hurdle: Expected Net {net_bps:.1f} bps <= {self.min_net_edge_bps:.1f} bps"
                )

            pos = PositionAllocation(
                symbol=s,
                quantity=q,
                price=p,
                notional=notional,
                expected_gross_bps=round(g_bps, 2),
                expected_gross_rupees=g_inr,
                brokerage_rupees=brokerage,
                stt_rupees=stt,
                exchange_charges_rupees=exchange,
                sebi_charges_rupees=sebi,
                stamp_duty_rupees=stamp,
                gst_rupees=gst,
                statutory_cost_rupees=statutory_cost,
                spread_bps=spr_bps,
                spread_rupees=spr_inr,
                slippage_bps=slip_bps,
                slippage_rupees=slip_inr,
                impact_bps=impact_bps,
                impact_rupees=impact_inr,
                total_friction_rupees=total_fric,
                expected_net_rupees=net_inr,
                expected_net_bps=net_bps,
                expected_holding_time_minutes=60,
                model_consensus_strength=consensus_strengths[s],
                supporting_models=supporting[s],
                contradicting_models=contradicting[s],
                sector=sectors[s]
            )
            positions.append(pos)

            tot_gross_inr += g_inr
            tot_stat_inr += statutory_cost
            tot_spread_inr += spr_inr
            tot_slip_inr += slip_inr
            tot_impact_inr += impact_inr
            tot_friction_inr += total_fric
            tot_net_inr += net_inr

        tot_deployed = round(sum(p.notional for p in positions), 2)
        reserved_cash = round(total_capital - tot_deployed, 2)
        net_bps_basket = round((tot_net_inr / tot_deployed) * 10000.0, 2) if tot_deployed > 0 else 0.0

        # Step D: Portfolio Risk & Penalty Calculations
        # 1. Portfolio Volatility Risk (bps)
        if tot_deployed > 0:
            var_sum = 0.0
            for i, s1 in enumerate(symbols):
                w1 = positions[i].notional / tot_deployed
                vol1 = (atrs[s1] / prices[s1]) * 10000.0
                for j, s2 in enumerate(symbols):
                    w2 = positions[j].notional / tot_deployed
                    vol2 = (atrs[s2] / prices[s2]) * 10000.0
                    if i == j:
                        rho = 1.0
                    else:
                        # Pairwise correlation
                        if correlation_matrix and s1 in correlation_matrix and s2 in correlation_matrix[s1]:
                            rho = correlation_matrix[s1][s2]
                        else:
                            # Sector-based heuristic
                            rho = 0.65 if sectors[s1] == sectors[s2] else 0.25
                    var_sum += w1 * w2 * vol1 * vol2 * rho
            portfolio_risk_bps = round(math.sqrt(max(0.0, var_sum)), 2)
        else:
            portfolio_risk_bps = 0.0

        # 2. Volatility Risk Penalty in ₹: 3% of portfolio volatility notional
        vol_penalty = round((portfolio_risk_bps / 10000.0) * tot_deployed * 0.03, 2)

        # 3. Sector Concentration Penalty: penalize if > 60% in a single sector
        sector_weights = {}
        for pos in positions:
            sec = pos.sector
            sector_weights[sec] = sector_weights.get(sec, 0.0) + (pos.notional / tot_deployed)
        sector_penalty = 0.0
        for sec, sw in sector_weights.items():
            if sw > 0.60 and k > 1:
                sector_penalty += round((sw - 0.60) * 4.0, 2)

        # 4. Disagreement Penalty: penalize if any model contradicts candidate
        disagree_penalty = 0.0
        for pos in positions:
            if pos.contradicting_models:
                disagree_penalty += round(len(pos.contradicting_models) * 1.5, 2)

        tot_penalties = round(vol_penalty + sector_penalty + disagree_penalty, 2)
        ranv = round(tot_net_inr - tot_penalties, 2)

        # Check basket-level feasibility
        is_feasible = (len(invalidation_reasons) == 0) and (tot_deployed <= max_deployable)

        return PortfolioBasket(
            basket_id=basket_id,
            basket_type="CANDIDATE",
            position_count=k,
            selected_symbols=symbols,
            positions=positions,
            total_capital_deployed=tot_deployed,
            reserved_cash=reserved_cash,
            total_expected_gross_rupees=round(tot_gross_inr, 2),
            total_statutory_cost_rupees=round(tot_stat_inr, 2),
            total_spread_rupees=round(tot_spread_inr, 2),
            total_slippage_rupees=round(tot_slip_inr, 2),
            total_impact_rupees=round(tot_impact_inr, 2),
            total_expected_cost_rupees=round(tot_friction_inr, 2),
            total_expected_net_rupees=round(tot_net_inr, 2),
            expected_net_bps=net_bps_basket,
            portfolio_risk_bps=portfolio_risk_bps,
            expected_holding_time_minutes=60,
            sector_concentration_penalty=round(sector_penalty, 2),
            disagreement_penalty=round(disagree_penalty, 2),
            volatility_risk_penalty=vol_penalty,
            total_penalties_rupees=tot_penalties,
            risk_adjusted_net_value=ranv,
            reason_for_selection=f"Evaluated {k}-stock basket with RANV = ₹{ranv:.2f}",
            is_feasible=is_feasible,
            invalidation_reasons=invalidation_reasons
        )
