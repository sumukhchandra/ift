"""
AlphaNSE V3 — Multi-Model Ensemble Decision Engine.
Combines independent evidence from all valid Session 5 research models:
  V2_15M, HYPO001 (30m), HYPO002 (60m), HYPO003 (15m), V3_60M (60m).

STATUS: EXPERIMENT / VALIDATION
CORE ENSEMBLE PRINCIPLES:
  1. NO BLIND AVERAGING: Does not average raw predictions across different horizons.
  2. HORIZON PRESERVATION: Separates short-term (15m), medium-term (30m), and long-term (60m) signals.
  3. EXPLICIT ATTRIBUTION: Records supporting_models, contradicting_models, and agreement count (0/5 to 5/5).
  4. RUPEE NET-EDGE: Only approves trades when expected net return clears friction AND exceeds the ₹0.80 hurdle.
  5. WHOLE-SHARE INTEGER SIZING: Sized strictly within available capital (₹5,000 constraint).
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import numpy as np

from v2.risk.dynamic_cost_model import DynamicCostModel, ExecutionMode, TradeCostDetail
from v3.config.v3_config import (
    MIN_NET_EDGE_RUPEES,
    MIN_NET_EDGE_BPS,
    MAX_CAPITAL_PCT_PER_TRADE,
    MAX_SPREAD_BPS,
    MIN_BAR_VOLUME,
    PREDICTION_SHRINKAGE_FACTOR,
)
from v3.models.base_model import ModelPredictionOutput

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnsembleDecisionOutput:
    """
    Complete consolidated output of the MultiModelEnsembleV3 for a single asset at a bar.
    """
    symbol: str
    price: float
    affordable_quantity: int
    capital_required: float

    # Model Predictions & Agreement Telemetry
    individual_predictions: Dict[str, ModelPredictionOutput]
    valid_model_count: int
    model_agreement_count: int          # Models voting in ensemble direction
    agreement_ratio: str                # e.g. "4/5", "3/4"
    supporting_models: List[str]
    contradicting_models: List[str]
    neutral_models: List[str]

    # Consolidated Ensemble Signal
    ensemble_direction: int             # +1 for Long, -1 for Short, 0 for Neutral
    ensemble_confidence: float          # 0.0 to 1.0 confidence score
    selected_horizon: int               # Primary horizon in minutes (15, 30, or 60)
    horizon_breakdown: Dict[int, float] # {15: bps, 30: bps, 60: bps}

    # Rupee Ticket Economics
    ensemble_expected_gross_bps: float
    expected_gross_rupees: float
    estimated_statutory_rupees: float
    estimated_execution_rupees: float
    estimated_total_cost_rupees: float
    estimated_cost_bps: float
    ensemble_expected_net_bps: float
    ensemble_expected_net_rupees: float

    # Final Decision
    final_decision: str                 # "TRADE" or "HOLD_CASH"
    decision_reason: str
    is_viable: bool

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["individual_predictions"] = {
            k: v.to_dict() for k, v in self.individual_predictions.items()
        }
        return d


class MultiModelEnsembleV3:
    """
    Synthesizes independent multi-horizon signals into economically validated decisions.
    """

    def __init__(
        self,
        min_net_edge_rupees: float = MIN_NET_EDGE_RUPEES,
        min_net_edge_bps: float = MIN_NET_EDGE_BPS,
        min_bar_volume: float = MIN_BAR_VOLUME,
        max_spread_bps: float = MAX_SPREAD_BPS,
        max_capital_pct_per_trade: float = MAX_CAPITAL_PCT_PER_TRADE,
        cost_model: Optional[DynamicCostModel] = None,
        execution_mode: ExecutionMode = ExecutionMode.AGGRESSIVE,
        shrinkage_factor: Optional[float] = None
    ):
        self.min_net_edge_rupees = min_net_edge_rupees
        self.min_net_edge_bps = min_net_edge_bps
        self.min_bar_volume = min_bar_volume
        self.max_spread_bps = max_spread_bps
        self.max_capital_pct_per_trade = max_capital_pct_per_trade
        self.cost_model = cost_model or DynamicCostModel(base_half_spread_bps=1.0, base_slippage_bps=2.0)
        self.execution_mode = execution_mode
        self.shrinkage_factor = shrinkage_factor if shrinkage_factor is not None else PREDICTION_SHRINKAGE_FACTOR

    def evaluate_candidate(
        self,
        symbol: str,
        price: float,
        bar_volume: float,
        available_capital: float,
        model_predictions: Dict[str, ModelPredictionOutput]
    ) -> EnsembleDecisionOutput:
        """
        Evaluates a single instrument using multi-model predictions and Rupee Net-Edge calculations.
        """
        # Filter strictly for valid models
        valid_models = {k: v for k, v in model_predictions.items() if v.model_validity}
        valid_count = len(valid_models)

        if valid_count == 0 or price <= 0 or available_capital <= 0:
            return self._create_hold_decision(
                symbol=symbol, price=price, available_capital=available_capital,
                model_predictions=model_predictions, valid_count=valid_count,
                reason="NO_VALID_MODELS_OR_INVALID_PRICE_CAPITAL"
            )

        # Check Liquidity
        if bar_volume < self.min_bar_volume:
            return self._create_hold_decision(
                symbol=symbol, price=price, available_capital=available_capital,
                model_predictions=model_predictions, valid_count=valid_count,
                reason=f"LOW_VOLUME ({bar_volume:.0f} < {self.min_bar_volume:.0f})"
            )

        # Sizing: affordable whole shares within allocated capital
        allocatable_capital = available_capital * self.max_capital_pct_per_trade
        qty = int(allocatable_capital / price)
        if qty <= 0:
            return self._create_hold_decision(
                symbol=symbol, price=price, available_capital=available_capital,
                model_predictions=model_predictions, valid_count=valid_count,
                reason=f"INSUFFICIENT_CAPITAL_FOR_1_SHARE (Price ₹{price:.1f} > Alloc ₹{allocatable_capital:.1f})"
            )
        notional = qty * price

        # 1. Horizon & Direction Disaggregation
        horizon_breakdown: Dict[int, List[float]] = {15: [], 30: [], 60: []}
        direction_votes = {1: 0, -1: 0, 0: 0}

        for m_id, pred in valid_models.items():
            if pred.horizon_minutes in horizon_breakdown:
                horizon_breakdown[pred.horizon_minutes].append(pred.expected_gross_return_bps)
            direction_votes[pred.direction] += 1

        # Calculate average prediction per horizon (preserving multi-horizon structure)
        horizon_means = {
            h: float(np.mean(vals)) if vals else 0.0
            for h, vals in horizon_breakdown.items()
        }

        # 2. Ensemble Direction & Model Agreement
        # Determine dominant direction
        long_count = direction_votes[1]
        short_count = direction_votes[-1]

        if long_count > short_count and long_count >= 1:
            ensemble_dir = 1
        elif short_count > long_count and short_count >= 1:
            ensemble_dir = -1
        else:
            ensemble_dir = 0

        # Classify supporting, contradicting, and neutral models
        supporting_models = [m_id for m_id, p in valid_models.items() if p.direction == ensemble_dir and ensemble_dir != 0]
        contradicting_models = [m_id for m_id, p in valid_models.items() if p.direction == -ensemble_dir and ensemble_dir != 0]
        neutral_models = [m_id for m_id, p in valid_models.items() if p.direction == 0 or ensemble_dir == 0]

        agreement_count = len(supporting_models)
        agreement_ratio = f"{agreement_count}/{valid_count}"

        if ensemble_dir == 0:
            return self._create_hold_decision(
                symbol=symbol, price=price, available_capital=available_capital,
                model_predictions=model_predictions, valid_count=valid_count,
                reason="ZERO_DIRECTIONAL_CONSENSUS",
                qty=qty, notional=notional, horizon_breakdown=horizon_means,
                supporting=supporting_models, contradicting=contradicting_models,
                agreement_count=0
            )

        # 3. Horizon-Aware Expected Gross Return Calculation
        # Select primary horizon from supporting models (favor longer horizon if present)
        supporting_horizons = [valid_models[m].horizon_minutes for m in supporting_models]
        selected_horizon = max(supporting_horizons) if supporting_horizons else 15

        # Weighted gross return from supporting models (weighted by confidence)
        supp_weights = [valid_models[m].confidence for m in supporting_models]
        supp_returns = [valid_models[m].expected_gross_return_bps for m in supporting_models]

        total_weight = sum(supp_weights) if sum(supp_weights) > 0 else 1.0
        raw_expected_gross_bps = sum(r * w for r, w in zip(supp_returns, supp_weights)) / total_weight

        # ── CALIBRATION SHRINKAGE ─────────────────────────────────────────────
        # Session 5 forensics showed all 5 models over-predict gross move
        # amplitude by ~2×.  Mean realized/predicted ratio across 10 stocks =
        # 0.504.  Shrink raw prediction to a realistic expectation BEFORE any
        # economics calculation so that the net-edge gate evaluates real ₹.
        # Uses self.shrinkage_factor (frozen OOS factor or config default 1.0).
        expected_gross_bps = raw_expected_gross_bps * self.shrinkage_factor
        logger.debug(
            "[%s] Gross bps: raw=%.2f  shrunk=%.2f  (factor=%.4f)",
            symbol, raw_expected_gross_bps, expected_gross_bps, self.shrinkage_factor
        )
        # ─────────────────────────────────────────────────────────────────────

        # Ensemble confidence: average confidence scaled by agreement ratio
        avg_conf = float(np.mean(supp_weights)) if supp_weights else 0.50
        agreement_factor = agreement_count / valid_count
        ensemble_confidence = round(float(avg_conf * (0.5 + 0.5 * agreement_factor)), 2)

        # Penalty if strong contradiction exists (e.g. 15m short vs 60m long)
        if len(contradicting_models) > 0:
            contra_returns = [abs(valid_models[m].expected_gross_return_bps) for m in contradicting_models]
            contra_penalty = min(0.30, 0.10 * len(contradicting_models))
            ensemble_confidence = round(float(ensemble_confidence * (1.0 - contra_penalty)), 2)

        # 4. Penny-for-Penny Cost Computation
        expected_gross_rupees = notional * (abs(expected_gross_bps) / 10000.0)

        cost_detail = self.cost_model.compute_trade_cost(
            price=price,
            quantity=qty,
            bar_volume=bar_volume,
            execution_mode=self.execution_mode
        )

        statutory_costs = self.cost_model.cost_engine.calculate_roundtrip_cost(
            capital=notional,
            gross_return=abs(expected_gross_bps) / 10000.0
        )

        statutory_rupees = statutory_costs.fixed_or_capped_cost + statutory_costs.proportional_statutory_cost
        execution_rupees = cost_detail.total_cost_rupees - statutory_rupees
        total_cost_rupees = cost_detail.total_cost_rupees
        total_cost_bps = cost_detail.total_cost_bps
        spread_bps = cost_detail.spread_bps

        # Spread filter
        if spread_bps > self.max_spread_bps:
            return self._create_hold_decision(
                symbol=symbol, price=price, available_capital=available_capital,
                model_predictions=model_predictions, valid_count=valid_count,
                reason=f"SPREAD_EXCEEDS_MAX ({spread_bps:.1f} > {self.max_spread_bps:.1f} bps)",
                qty=qty, notional=notional, horizon_breakdown=horizon_means,
                supporting=supporting_models, contradicting=contradicting_models,
                agreement_count=agreement_count
            )

        # 5. RUPEE NET-EDGE GATE
        expected_net_rupees = expected_gross_rupees - total_cost_rupees
        expected_net_bps = abs(expected_gross_bps) - total_cost_bps

        cleared_rupee_hurdle = expected_net_rupees >= self.min_net_edge_rupees
        cleared_bps_hurdle = expected_net_bps > self.min_net_edge_bps

        is_viable = cleared_rupee_hurdle and cleared_bps_hurdle

        if is_viable:
            final_decision = "TRADE"
            decision_reason = (
                f"CLEARED_GATE: Exp Net ₹{expected_net_rupees:.2f} >= ₹{self.min_net_edge_rupees:.2f} | "
                f"Gross ₹{expected_gross_rupees:.2f} vs Cost ₹{total_cost_rupees:.2f} | "
                f"Agreement: {agreement_ratio} ({selected_horizon}m horizon)"
            )
        else:
            final_decision = "HOLD_CASH"
            if not cleared_rupee_hurdle:
                decision_reason = (
                    f"INSUFFICIENT_NET_INR (Exp Net ₹{expected_net_rupees:.2f} < "
                    f"Hurdle ₹{self.min_net_edge_rupees:.2f} | Gross ₹{expected_gross_rupees:.2f} vs Cost ₹{total_cost_rupees:.2f})"
                )
            else:
                decision_reason = (
                    f"INSUFFICIENT_NET_BPS (Exp Net {expected_net_bps:.1f} bps <= "
                    f"Hurdle {self.min_net_edge_bps:.1f} bps)"
                )

        return EnsembleDecisionOutput(
            symbol=symbol,
            price=price,
            affordable_quantity=qty,
            capital_required=round(notional, 2),
            individual_predictions=model_predictions,
            valid_model_count=valid_count,
            model_agreement_count=agreement_count,
            agreement_ratio=agreement_ratio,
            supporting_models=supporting_models,
            contradicting_models=contradicting_models,
            neutral_models=neutral_models,
            ensemble_direction=ensemble_dir,
            ensemble_confidence=ensemble_confidence,
            selected_horizon=selected_horizon,
            horizon_breakdown=horizon_means,
            ensemble_expected_gross_bps=round(expected_gross_bps, 2),
            expected_gross_rupees=round(expected_gross_rupees, 2),
            estimated_statutory_rupees=round(statutory_rupees, 2),
            estimated_execution_rupees=round(execution_rupees, 2),
            estimated_total_cost_rupees=round(total_cost_rupees, 2),
            estimated_cost_bps=round(total_cost_bps, 2),
            ensemble_expected_net_bps=round(expected_net_bps, 2),
            ensemble_expected_net_rupees=round(expected_net_rupees, 2),
            final_decision=final_decision,
            decision_reason=decision_reason,
            is_viable=is_viable
        )

    def _create_hold_decision(
        self,
        symbol: str,
        price: float,
        available_capital: float,
        model_predictions: Dict[str, ModelPredictionOutput],
        valid_count: int,
        reason: str,
        qty: int = 0,
        notional: float = 0.0,
        horizon_breakdown: Optional[Dict[int, float]] = None,
        supporting: Optional[List[str]] = None,
        contradicting: Optional[List[str]] = None,
        agreement_count: int = 0
    ) -> EnsembleDecisionOutput:
        """Helper to create a normalized HOLD_CASH decision record."""
        return EnsembleDecisionOutput(
            symbol=symbol,
            price=price,
            affordable_quantity=qty,
            capital_required=round(notional, 2),
            individual_predictions=model_predictions,
            valid_model_count=valid_count,
            model_agreement_count=agreement_count,
            agreement_ratio=f"{agreement_count}/{valid_count}",
            supporting_models=supporting or [],
            contradicting_models=contradicting or [],
            neutral_models=[k for k in model_predictions if k not in (supporting or []) and k not in (contradicting or [])],
            ensemble_direction=0,
            ensemble_confidence=0.0,
            selected_horizon=15,
            horizon_breakdown=horizon_breakdown or {15: 0.0, 30: 0.0, 60: 0.0},
            ensemble_expected_gross_bps=0.0,
            expected_gross_rupees=0.0,
            estimated_statutory_rupees=0.0,
            estimated_execution_rupees=0.0,
            estimated_total_cost_rupees=0.0,
            estimated_cost_bps=0.0,
            ensemble_expected_net_bps=0.0,
            ensemble_expected_net_rupees=0.0,
            final_decision="HOLD_CASH",
            decision_reason=reason,
            is_viable=False
        )
