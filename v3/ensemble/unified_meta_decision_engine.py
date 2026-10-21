"""
v3/ensemble/unified_meta_decision_engine.py
AlphaNSE Unified Ensemble Meta-Decision Engine.
Combines independent evidence from specialist models, evaluates consensus,
validates net edge against statutory friction, and applies macro/micro-regime gates.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional

from v3.ensemble.specialist_signal import SpecialistSignal, SignalDirection, HorizonCategory
from v2.risk.cost_engine import IndiaCostEngine


@dataclass
class MetaDecisionOutput:
    """Consolidated institutional decision emitted by the Unified Meta-Decision Engine."""
    target_symbol: str
    action: SignalDirection               # BUY, SELL, HOLD, or WAIT
    consensus_score: float                # Normalized -1.0 to +1.0
    agreement_count: int                  # Number of specialist models agreeing with action
    total_specialists: int                # Total specialist models evaluated
    agreement_ratio: str                  # e.g. "4/7", "5/7"
    supporting_models: List[str]          # Models voting in direction
    opposing_models: List[str]            # Models voting opposite
    neutral_models: List[str]             # Models voting HOLD
    expected_gross_pct: float
    estimated_friction_pct: float
    expected_net_pct: float
    net_edge_cleared: bool
    macro_regime: str                     # "BULL" or "BEAR"
    micro_regime: str                     # "TRENDING_BULL", "TRENDING_BEAR", "SIDEWAYS"
    recommended_horizon_mins: int
    rationale: str
    decision_timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_symbol": self.target_symbol,
            "action": self.action.value,
            "consensus_score": round(self.consensus_score, 4),
            "agreement_count": self.agreement_count,
            "total_specialists": self.total_specialists,
            "agreement_ratio": self.agreement_ratio,
            "supporting_models": self.supporting_models,
            "opposing_models": self.opposing_models,
            "neutral_models": self.neutral_models,
            "expected_gross_pct": round(self.expected_gross_pct, 4),
            "estimated_friction_pct": round(self.estimated_friction_pct, 4),
            "expected_net_pct": round(self.expected_net_pct, 4),
            "net_edge_cleared": self.net_edge_cleared,
            "macro_regime": self.macro_regime,
            "micro_regime": self.micro_regime,
            "recommended_horizon_mins": self.recommended_horizon_mins,
            "rationale": self.rationale,
            "decision_timestamp": self.decision_timestamp.isoformat()
        }


class UnifiedMetaDecisionEngine:
    """
    Intelligent decision layer that consumes specialist signals and produces
    one high-conviction decision per opportunity.
    """
    def __init__(
        self,
        min_agreement_threshold: int = 3,       # At least 3 specialist votes required
        min_consensus_score: float = 0.35,      # Net score hurdle (weighted confidence)
        min_net_edge_multiple: float = 2.0,     # Expected return must be >= 2.0x friction
        cost_engine: Optional[IndiaCostEngine] = None
    ):
        self.min_agreement_threshold = min_agreement_threshold
        self.min_consensus_score = min_consensus_score
        self.min_net_edge_multiple = min_net_edge_multiple
        self.cost_engine = cost_engine or IndiaCostEngine()

    def evaluate_opportunity(
        self,
        target_symbol: str,
        specialist_signals: Dict[str, SpecialistSignal],
        market_snapshot: Dict[str, Any]
    ) -> MetaDecisionOutput:
        """
        Evaluates an asset across all specialist signals, market regime, and transaction costs.
        """
        total_specialists = len(specialist_signals)
        if total_specialists == 0:
            return MetaDecisionOutput(
                target_symbol=target_symbol,
                action=SignalDirection.HOLD,
                consensus_score=0.0,
                agreement_count=0,
                total_specialists=0,
                agreement_ratio="0/0",
                supporting_models=[],
                opposing_models=[],
                neutral_models=[],
                expected_gross_pct=0.0,
                estimated_friction_pct=0.0,
                expected_net_pct=0.0,
                net_edge_cleared=False,
                macro_regime="UNKNOWN",
                micro_regime="UNKNOWN",
                recommended_horizon_mins=0,
                rationale="Zero specialist signals available"
            )

        # 1. Macro Regime Gate
        nifty_data = market_snapshot.get("^NSEI", {})
        nifty_px = float(nifty_data.get("price", nifty_data.get("current_price", 22497.15)))
        nifty_ema50 = float(nifty_data.get("ema50", 23842.22))
        macro_regime = "BEAR" if nifty_px < nifty_ema50 else "BULL"

        # Micro-regime
        sym_data = market_snapshot.get(target_symbol, {})
        micro_regime = sym_data.get("regime", "SIDEWAYS")
        current_px = float(sym_data.get("price", sym_data.get("current_price", 1000.0)))

        # 2. Vote Tallying & Consensus Scoring
        buy_votes = []
        sell_votes = []
        neutral_votes = []

        buy_confidence_sum = 0.0
        sell_confidence_sum = 0.0
        gross_return_acc = []
        horizons_acc = []

        for model_id, sig in specialist_signals.items():
            # Filter relevance: evaluate general index/macro signals or asset-specific signals
            if sig.direction == SignalDirection.BUY:
                buy_votes.append(model_id)
                buy_confidence_sum += sig.confidence
                gross_return_acc.append(sig.predicted_return_pct)
                horizons_acc.append(sig.expected_holding_mins)
            elif sig.direction == SignalDirection.SELL:
                sell_votes.append(model_id)
                sell_confidence_sum += sig.confidence
                gross_return_acc.append(abs(sig.predicted_return_pct))
                horizons_acc.append(sig.expected_holding_mins)
            else:
                neutral_votes.append(model_id)

        # Consensus score normalized between -1.0 and +1.0
        consensus_score = (buy_confidence_sum - sell_confidence_sum) / float(total_specialists)

        # Determine prevailing raw direction
        if len(buy_votes) > len(sell_votes) and consensus_score >= self.min_consensus_score:
            raw_action = SignalDirection.BUY
            agreement_count = len(buy_votes)
            supporting_models = buy_votes
            opposing_models = sell_votes
            direction_multiplier = 1.0
        elif len(sell_votes) > len(buy_votes) and consensus_score <= -self.min_consensus_score:
            raw_action = SignalDirection.SELL
            agreement_count = len(sell_votes)
            supporting_models = sell_votes
            opposing_models = buy_votes
            direction_multiplier = -1.0
        else:
            raw_action = SignalDirection.HOLD
            agreement_count = len(neutral_votes)
            supporting_models = []
            opposing_models = []
            direction_multiplier = 0.0

        agreement_ratio = f"{agreement_count}/{total_specialists}"

        # 3. Transaction Cost & Net Edge Estimation
        avg_gross_pct = (sum(gross_return_acc) / len(gross_return_acc)) if gross_return_acc else 0.0
        rec_horizon = int(sum(horizons_acc) / len(horizons_acc)) if horizons_acc else 60

        # Estimate statutory friction in % terms (approx 0.15% to 0.25% intraday)
        simulated_notional = 1500.0
        cost_breakdown = self.cost_engine.calculate_roundtrip_cost(
            capital=simulated_notional,
            gross_return=(avg_gross_pct / 100.0)
        )
        estimated_friction_pct = (cost_breakdown.total_cost / simulated_notional) * 100.0
        expected_net_pct = avg_gross_pct - estimated_friction_pct
        net_edge_cleared = (avg_gross_pct >= (estimated_friction_pct * self.min_net_edge_multiple))

        # 4. Gating & Decision Synthesis
        final_action = SignalDirection.HOLD
        rationale_parts = []

        if raw_action == SignalDirection.HOLD:
            final_action = SignalDirection.HOLD
            rationale_parts.append(f"Insufficient directional consensus ({agreement_ratio} agreeing; score {consensus_score:+.2f})")
        elif not net_edge_cleared:
            final_action = SignalDirection.WAIT
            rationale_parts.append(
                f"Net edge hurdle failed: Expected return {avg_gross_pct:.2f}% < {self.min_net_edge_multiple:.1f}x friction ({estimated_friction_pct:.2f}%)"
            )
        elif raw_action == SignalDirection.BUY and macro_regime == "BEAR" and rec_horizon > 60:
            final_action = SignalDirection.HOLD
            rationale_parts.append("Macro BEAR regime suppresses multi-day long equity swings; 100% Cash Preservation active")
        elif micro_regime == "SIDEWAYS" and agreement_count < (self.min_agreement_threshold + 1):
            final_action = SignalDirection.WAIT
            rationale_parts.append("Sideways micro-regime requires elevated consensus to filter chop noise")
        else:
            final_action = raw_action
            rationale_parts.append(
                f"Approved {final_action.value}: Consensus {agreement_ratio} (Score: {consensus_score:+.2f}), "
                f"Net edge cleared (+{expected_net_pct:.2f}% net vs {estimated_friction_pct:.2f}% friction)"
            )

        return MetaDecisionOutput(
            target_symbol=target_symbol,
            action=final_action,
            consensus_score=consensus_score,
            agreement_count=agreement_count,
            total_specialists=total_specialists,
            agreement_ratio=agreement_ratio,
            supporting_models=supporting_models,
            opposing_models=opposing_models,
            neutral_models=neutral_votes,
            expected_gross_pct=avg_gross_pct,
            estimated_friction_pct=estimated_friction_pct,
            expected_net_pct=expected_net_pct,
            net_edge_cleared=net_edge_cleared,
            macro_regime=macro_regime,
            micro_regime=micro_regime,
            recommended_horizon_mins=rec_horizon,
            rationale=" | ".join(rationale_parts)
        )
