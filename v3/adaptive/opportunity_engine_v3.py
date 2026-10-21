"""
AlphaNSE V3 — Rupee Net-Edge Opportunity Engine.
Evaluates cross-sectional opportunities bar-by-bar using the capital-aware Rupee Net-Edge rule:

Predicted gross return (%)
        ↓
actual affordable quantity (whole shares with ₹5k capital)
        ↓
expected gross ₹ = notional * (predicted_return_bps / 10000)
        ↓
statutory costs + spread + slippage + impact = all-in costs ₹
        ↓
expected net ₹ = expected gross ₹ - all-in costs ₹
        ↓
minimum required edge ₹ (>= ₹0.80 net buffer)
        ↓
TRADE / HOLD CASH

STATUS: EXPERIMENT / VALIDATION
KEY PRINCIPLES:
  1. NO ATR INFLATION: Uses pure model predictions without artificial ATR multipliers.
  2. DYNAMIC UNIVERSE: Evaluates whatever symbols are present at the bar (no hardcoded whitelist/blacklist).
  3. CASH PRESERVATION: Holding cash (0 trades) is a valid, intentional decision when net edge is negative.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import pandas as pd

from v2.features.feature_pipeline import ALL_FEATURE_COLUMNS
from v2.models.estimators import RidgeReturnRegressor
from v2.risk.dynamic_cost_model import DynamicCostModel, ExecutionMode, TradeCostDetail
from v3.config.v3_config import (
    MIN_NET_EDGE_RUPEES,
    MIN_NET_EDGE_BPS,
    MIN_PREDICTED_RETURN_BPS,
    MIN_BAR_VOLUME,
    MAX_SPREAD_BPS,
    MAX_CAPITAL_PCT_PER_TRADE,
    ALLOW_CASH_HOLDING
)
from v3.ensemble.multimodel_ensemble_v3 import MultiModelEnsembleV3, EnsembleDecisionOutput
from v3.models.base_model import ModelPredictionOutput
from v3.adaptive.audit_ledger_v3 import CandidateDecisionAuditRecordV3

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RankedOpportunityV3:
    """
    Evaluated opportunity passing the full Rupee Net-Edge Gate.
    """
    symbol: str
    direction: int                      # +1 for Long, -1 for Short
    price: float
    quantity: int
    notional: float
    predicted_return_bps: float         # Raw model predicted return in bps
    expected_gross_rupees: float        # Expected gross return in INR
    expected_cost_rupees: float         # Dynamic all-in execution cost in INR
    expected_net_rupees: float          # Expected net rupee return after all friction
    expected_cost_bps: float            # Dynamic execution cost in bps
    expected_net_bps: float             # Expected net return in bps
    cost_detail: TradeCostDetail        # Complete itemized friction breakdown
    z_score: float
    bar_volume: float
    is_viable: bool
    reject_reason: Optional[str] = None


class OpportunityEngineV3:
    """
    Point-in-time cross-sectional opportunity evaluator and ranker for V3.
    """

    def __init__(
        self,
        min_net_edge_rupees: float = MIN_NET_EDGE_RUPEES,
        min_net_edge_bps: float = MIN_NET_EDGE_BPS,
        min_predicted_return_bps: float = MIN_PREDICTED_RETURN_BPS,
        min_bar_volume: float = MIN_BAR_VOLUME,
        max_spread_bps: float = MAX_SPREAD_BPS,
        max_capital_pct_per_trade: float = MAX_CAPITAL_PCT_PER_TRADE,
        cost_model: Optional[DynamicCostModel] = None,
        execution_mode: ExecutionMode = ExecutionMode.AGGRESSIVE,
        allow_short: bool = True,
        shrinkage_factor: Optional[float] = None
    ):
        self.min_net_edge_rupees = min_net_edge_rupees
        self.min_net_edge_bps = min_net_edge_bps
        self.min_predicted_return_bps = min_predicted_return_bps
        self.min_bar_volume = min_bar_volume
        self.max_spread_bps = max_spread_bps
        self.max_capital_pct_per_trade = max_capital_pct_per_trade
        self.cost_model = cost_model or DynamicCostModel(base_half_spread_bps=1.0, base_slippage_bps=2.0)
        self.execution_mode = execution_mode
        self.allow_short = allow_short
        self.shrinkage_factor = shrinkage_factor
        self.ensemble = MultiModelEnsembleV3(
            min_net_edge_rupees=self.min_net_edge_rupees,
            min_net_edge_bps=self.min_net_edge_bps,
            min_bar_volume=self.min_bar_volume,
            max_spread_bps=self.max_spread_bps,
            max_capital_pct_per_trade=self.max_capital_pct_per_trade,
            cost_model=self.cost_model,
            execution_mode=self.execution_mode,
            shrinkage_factor=self.shrinkage_factor
        )

    def evaluate_symbol_ticket(
        self,
        symbol: str,
        price: float,
        predicted_bps: float,
        available_capital: float,
        bar_volume: float,
        z_score: float = 0.0
    ) -> RankedOpportunityV3:
        """
        Executes the Rupee Net-Edge evaluation for a single instrument:
        Computes affordable whole shares, gross expected ₹, dynamic friction ₹,
        and tests against the minimum net edge hurdle.
        """
        # Direction from prediction sign
        direction = 1 if predicted_bps >= 0 else -1
        abs_pred_bps = abs(predicted_bps)

        if not self.allow_short and direction == -1:
            return RankedOpportunityV3(
                symbol=symbol, direction=direction, price=price, quantity=0, notional=0.0,
                predicted_return_bps=predicted_bps, expected_gross_rupees=0.0,
                expected_cost_rupees=0.0, expected_net_rupees=0.0, expected_cost_bps=0.0,
                expected_net_bps=0.0, cost_detail=None, z_score=z_score, bar_volume=bar_volume,
                is_viable=False, reject_reason="SHORTS_DISABLED"
            )

        if price <= 0 or available_capital <= 0:
            return RankedOpportunityV3(
                symbol=symbol, direction=direction, price=price, quantity=0, notional=0.0,
                predicted_return_bps=predicted_bps, expected_gross_rupees=0.0,
                expected_cost_rupees=0.0, expected_net_rupees=0.0, expected_cost_bps=0.0,
                expected_net_bps=0.0, cost_detail=None, z_score=z_score, bar_volume=bar_volume,
                is_viable=False, reject_reason="INVALID_PRICE_OR_CAPITAL"
            )

        # Liquidity check
        if bar_volume < self.min_bar_volume:
            return RankedOpportunityV3(
                symbol=symbol, direction=direction, price=price, quantity=0, notional=0.0,
                predicted_return_bps=predicted_bps, expected_gross_rupees=0.0,
                expected_cost_rupees=0.0, expected_net_rupees=0.0, expected_cost_bps=0.0,
                expected_net_bps=0.0, cost_detail=None, z_score=z_score, bar_volume=bar_volume,
                is_viable=False, reject_reason=f"LOW_VOLUME ({bar_volume:.0f} < {self.min_bar_volume:.0f})"
            )

        # Minimum signal floor check
        if abs_pred_bps < self.min_predicted_return_bps:
            return RankedOpportunityV3(
                symbol=symbol, direction=direction, price=price, quantity=0, notional=0.0,
                predicted_return_bps=predicted_bps, expected_gross_rupees=0.0,
                expected_cost_rupees=0.0, expected_net_rupees=0.0, expected_cost_bps=0.0,
                expected_net_bps=0.0, cost_detail=None, z_score=z_score, bar_volume=bar_volume,
                is_viable=False, reject_reason=f"SIGNAL_BELOW_NOISE_FLOOR ({abs_pred_bps:.2f} < {self.min_predicted_return_bps:.2f} bps)"
            )

        # Sizing: affordable whole shares within allocated capital
        allocatable_capital = available_capital * self.max_capital_pct_per_trade
        qty = int(allocatable_capital / price)

        if qty <= 0:
            return RankedOpportunityV3(
                symbol=symbol, direction=direction, price=price, quantity=0, notional=0.0,
                predicted_return_bps=predicted_bps, expected_gross_rupees=0.0,
                expected_cost_rupees=0.0, expected_net_rupees=0.0, expected_cost_bps=0.0,
                expected_net_bps=0.0, cost_detail=None, z_score=z_score, bar_volume=bar_volume,
                is_viable=False, reject_reason=f"INSUFFICIENT_CAPITAL_FOR_1_SHARE (Price ₹{price:.1f} > Alloc ₹{allocatable_capital:.1f})"
            )

        notional = price * qty
        expected_gross_rupees = notional * (abs_pred_bps / 10000.0)

        # Penny-for-penny dynamic friction model
        cost_detail = self.cost_model.compute_trade_cost(
            price=price,
            quantity=qty,
            bar_volume=bar_volume,
            execution_mode=self.execution_mode
        )
        expected_cost_rupees = cost_detail.total_cost_rupees
        expected_cost_bps = cost_detail.total_cost_bps
        spread_bps = cost_detail.spread_bps

        # Spread filter
        if spread_bps > self.max_spread_bps:
            return RankedOpportunityV3(
                symbol=symbol, direction=direction, price=price, quantity=qty, notional=notional,
                predicted_return_bps=predicted_bps, expected_gross_rupees=round(expected_gross_rupees, 2),
                expected_cost_rupees=round(expected_cost_rupees, 2), expected_net_rupees=0.0,
                expected_cost_bps=round(expected_cost_bps, 2), expected_net_bps=0.0,
                cost_detail=cost_detail, z_score=z_score, bar_volume=bar_volume,
                is_viable=False, reject_reason=f"SPREAD_EXCEEDS_MAX ({spread_bps:.1f} > {self.max_spread_bps:.1f} bps)"
            )

        # RUPEE NET-EDGE CALCULATION
        expected_net_rupees = expected_gross_rupees - expected_cost_rupees
        expected_net_bps = abs_pred_bps - expected_cost_bps

        # Gate check: must clear both rupee edge hurdle (>= ₹0.80) and bps hurdle (>= 5 bps)
        cleared_rupee_hurdle = expected_net_rupees >= self.min_net_edge_rupees
        cleared_bps_hurdle = expected_net_bps >= self.min_net_edge_bps

        is_viable = cleared_rupee_hurdle and cleared_bps_hurdle

        reject_reason = None
        if not is_viable:
            if not cleared_rupee_hurdle:
                reject_reason = (
                    f"INSUFFICIENT_NET_INR (Expected Net ₹{expected_net_rupees:.2f} < "
                    f"Hurdle ₹{self.min_net_edge_rupees:.2f} | Gross ₹{expected_gross_rupees:.2f} vs Cost ₹{expected_cost_rupees:.2f})"
                )
            else:
                reject_reason = (
                    f"INSUFFICIENT_NET_BPS (Expected Net {expected_net_bps:.1f} bps < "
                    f"Hurdle {self.min_net_edge_bps:.1f} bps)"
                )

        return RankedOpportunityV3(
            symbol=symbol,
            direction=direction,
            price=price,
            quantity=qty,
            notional=round(notional, 2),
            predicted_return_bps=round(predicted_bps, 2),
            expected_gross_rupees=round(expected_gross_rupees, 2),
            expected_cost_rupees=round(expected_cost_rupees, 2),
            expected_net_rupees=round(expected_net_rupees, 2),
            expected_cost_bps=round(expected_cost_bps, 2),
            expected_net_bps=round(expected_net_bps, 2),
            cost_detail=cost_detail,
            z_score=round(z_score, 2),
            bar_volume=bar_volume,
            is_viable=is_viable,
            reject_reason=reject_reason
        )

    def rank_universe_at_bar(
        self,
        bar_features_df: pd.DataFrame,
        model: RidgeReturnRegressor,
        timestamp: pd.Timestamp,
        available_capital: float
    ) -> List[RankedOpportunityV3]:
        """
        Cross-sectionally evaluates all available symbols at a single bar timestamp.
        Returns viable opportunities sorted by expected net rupee profit descending.
        If no candidate provides sufficient net rupee edge, returns an empty list (HOLD CASH).
        """
        if bar_features_df.empty:
            return []

        # Drop benchmark index and rows with missing features
        clean_df = bar_features_df.dropna(subset=ALL_FEATURE_COLUMNS).copy()
        clean_df = clean_df[clean_df["symbol"] != "^NSEI"].copy().reset_index(drop=True)
        if clean_df.empty:
            return []

        # Predict using point-in-time features (in bps)
        X = clean_df[ALL_FEATURE_COLUMNS].values
        raw_preds_bps = model.predict(X) * 10000.0

        # Cross-sectional standardization
        mu = np.mean(raw_preds_bps)
        std = np.std(raw_preds_bps)
        std = std if std > 1e-4 else 1.0
        z_scores = (raw_preds_bps - mu) / std

        all_opportunities: List[RankedOpportunityV3] = []

        for idx, row in clean_df.iterrows():
            sym = row["symbol"]
            pred_bps = float(raw_preds_bps[idx])
            z = float(z_scores[idx])
            price = float(row["raw_close"])
            vol = float(row.get("raw_volume", 10000.0))

            opp = self.evaluate_symbol_ticket(
                symbol=sym,
                price=price,
                predicted_bps=pred_bps,
                available_capital=available_capital,
                bar_volume=vol,
                z_score=z
            )
            all_opportunities.append(opp)

        # Filter strictly for viable opportunities
        viable = [opp for opp in all_opportunities if opp.is_viable]

        # Rank viable opportunities by expected net rupee return descending
        viable.sort(key=lambda x: x.expected_net_rupees, reverse=True)

        return viable

    def evaluate_multimodel_universe_at_bar(
        self,
        bar_features_df: pd.DataFrame,
        model_registry: Any,
        timestamp: pd.Timestamp,
        available_capital: float,
        dataset_hash: str = "",
        training_cutoff: str = ""
    ) -> Tuple[List[EnsembleDecisionOutput], List[CandidateDecisionAuditRecordV3]]:
        """
        Cross-sectionally evaluates all available symbols at a single bar timestamp
        using the active multi-model registry (V2_15M, HYPO001, HYPO002, HYPO003, V3_60M).
        Produces EnsembleDecisionOutput for sizing/trading and CandidateDecisionAuditRecordV3
        for complete forensic lineage reconstruction.
        """
        if bar_features_df.empty:
            return [], []

        clean_df = bar_features_df.dropna(subset=ALL_FEATURE_COLUMNS).copy()
        clean_df = clean_df[clean_df["symbol"] != "^NSEI"].copy().reset_index(drop=True)
        if clean_df.empty:
            return [], []

        # Retrieve valid models from registry
        if hasattr(model_registry, "get_valid_models"):
            valid_models = model_registry.get_valid_models()
            all_meta = model_registry.metadata
        elif isinstance(model_registry, dict):
            valid_models = model_registry
            all_meta = {}
        else:
            valid_models = {}
            all_meta = {}

        model_hashes = {
            m_id: meta.model_hash if hasattr(meta, "model_hash") else "hash"
            for m_id, meta in all_meta.items()
        }
        feature_schema_hash = all_meta[list(all_meta.keys())[0]].feature_schema_hash if all_meta else "schema_hash"

        viable_candidates: List[EnsembleDecisionOutput] = []
        candidate_audits: List[CandidateDecisionAuditRecordV3] = []

        for idx, row in clean_df.iterrows():
            sym = row["symbol"]
            price = float(row["raw_close"])
            vol = float(row.get("raw_volume", 10000.0))

            x_vec = row[ALL_FEATURE_COLUMNS].values.reshape(1, -1)

            # Generate independent predictions across all 5 model slots
            model_predictions: Dict[str, ModelPredictionOutput] = {}

            # Default prediction slots
            preds_dict = {
                "V2_15M": (0.0, 0.0),
                "HYPO001": (0.0, 0.0),
                "HYPO002": (0.0, 0.0),
                "HYPO003": (0.0, 0.0),
                "V3_60M": (0.0, 0.0)
            }

            for model_id in ["V2_15M", "HYPO001", "HYPO002", "HYPO003", "V3_60M"]:
                if model_id in valid_models:
                    model_obj, meta = valid_models[model_id]
                    raw_pred_bps = float(model_obj.predict(x_vec)[0] * 10000.0)
                    horizon_mins = meta.target_horizon_minutes

                    # Determine direction and calibrated confidence
                    signal_floor = 4.0 if horizon_mins == 15 else (5.0 if horizon_mins == 30 else 6.0)
                    if model_id == "HYPO003":
                        # Short sparsity model: specialized downside detection
                        direction = -1 if raw_pred_bps < -signal_floor else 0
                    else:
                        direction = 1 if raw_pred_bps >= signal_floor else (-1 if raw_pred_bps <= -signal_floor else 0)

                    # Dynamic confidence scaling (0.50 to 0.90 based on signal strength)
                    conf_scale = min(0.35, abs(raw_pred_bps) / 100.0)
                    confidence = round(float(np.clip(meta.confidence + conf_scale, 0.50, 0.90)), 2)

                    output = ModelPredictionOutput(
                        model_id=model_id,
                        direction=direction,
                        expected_gross_return_bps=round(raw_pred_bps, 2),
                        confidence=confidence,
                        horizon_minutes=horizon_mins,
                        model_validity=True,
                        raw_prediction_bps=round(raw_pred_bps, 2),
                        model_hash=meta.model_hash
                    )
                    model_predictions[model_id] = output
                    preds_dict[model_id] = (round(raw_pred_bps, 2), confidence)
                else:
                    # Model failed or invalid: register as invalid
                    failed_hash = model_hashes.get(model_id, "INVALID")
                    horizon_default = 15 if "15M" in model_id else (30 if "001" in model_id else 60)
                    output = ModelPredictionOutput(
                        model_id=model_id,
                        direction=0,
                        expected_gross_return_bps=0.0,
                        confidence=0.0,
                        horizon_minutes=horizon_default,
                        model_validity=False,
                        raw_prediction_bps=0.0,
                        model_hash=failed_hash
                    )
                    model_predictions[model_id] = output
                    preds_dict[model_id] = (0.0, 0.0)

            # Evaluate candidate through MultiModelEnsembleV3
            ensemble_out = self.ensemble.evaluate_candidate(
                symbol=sym,
                price=price,
                bar_volume=vol,
                available_capital=available_capital,
                model_predictions=model_predictions
            )

            if ensemble_out.is_viable:
                viable_candidates.append(ensemble_out)

            # Generate Section 13 Candidate Decision Audit Record
            audit_rec = CandidateDecisionAuditRecordV3(
                timestamp=str(timestamp),
                symbol=sym,
                V2_15M_prediction=preds_dict["V2_15M"][0],
                V2_15M_confidence=preds_dict["V2_15M"][1],
                HYPO001_prediction=preds_dict["HYPO001"][0],
                HYPO001_confidence=preds_dict["HYPO001"][1],
                HYPO002_prediction=preds_dict["HYPO002"][0],
                HYPO002_confidence=preds_dict["HYPO002"][1],
                HYPO003_prediction=preds_dict["HYPO003"][0],
                HYPO003_confidence=preds_dict["HYPO003"][1],
                V3_60M_prediction=preds_dict["V3_60M"][0],
                V3_60M_confidence=preds_dict["V3_60M"][1],
                model_agreement_count=ensemble_out.model_agreement_count,
                valid_model_count=ensemble_out.valid_model_count,
                agreement_ratio=ensemble_out.agreement_ratio,
                supporting_models=ensemble_out.supporting_models,
                contradicting_models=ensemble_out.contradicting_models,
                ensemble_direction=ensemble_out.ensemble_direction,
                ensemble_confidence=ensemble_out.ensemble_confidence,
                selected_horizon=ensemble_out.selected_horizon,
                ensemble_expected_gross_bps=ensemble_out.ensemble_expected_gross_bps,
                ensemble_expected_net_bps=ensemble_out.ensemble_expected_net_bps,
                ensemble_expected_net_rupees=ensemble_out.ensemble_expected_net_rupees,
                price=price,
                affordable_quantity=ensemble_out.affordable_quantity,
                capital_required=ensemble_out.capital_required,
                estimated_brokerage=ensemble_out.estimated_statutory_rupees * 0.5,
                estimated_statutory_cost=ensemble_out.estimated_statutory_rupees,
                estimated_spread=ensemble_out.estimated_execution_rupees * 0.5,
                estimated_slippage=ensemble_out.estimated_execution_rupees * 0.5,
                estimated_impact=0.0,
                total_cost=ensemble_out.estimated_total_cost_rupees,
                final_decision=ensemble_out.final_decision,
                decision_reason=ensemble_out.decision_reason,
                model_hashes=model_hashes,
                dataset_hash=dataset_hash,
                feature_schema_hash=feature_schema_hash,
                training_cutoff=training_cutoff
            )
            candidate_audits.append(audit_rec)

        # Sort viable candidates by expected net INR descending
        viable_candidates.sort(key=lambda x: x.ensemble_expected_net_rupees, reverse=True)
        return viable_candidates, candidate_audits
