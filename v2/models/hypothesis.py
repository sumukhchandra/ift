"""
Candidate Hypothesis Definition & Anti-Peeking Freeze Engine for AlphaNSE V2.
Enforces the Phase 3A -> Phase 3B scientific handoff:
  1. Captures candidate strategies discovered during Phase 3A forensic exploration.
  2. Generates deterministic SHA-256 definition_hash and feature_set_hash.
  3. Freezes the hypothesis immutably before handoff to Phase 3B fresh walk-forward validation.
  4. Guarantees that Phase 3B evaluates strictly the frozen definition without data-peeking.
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict


class CandidateTamperingError(Exception):
    """Raised when candidate hypothesis definition has been tampered with or modified post-freeze."""
    pass


class ProhibitedCandidateReplacementError(Exception):
    """Raised when attempting to substitute or introduce new candidates during Phase 3B."""
    pass


# Strict Phase 3B Candidate Lock: No candidate replacement permitted
LOCKED_PHASE3B_CANDIDATE_IDS = frozenset([
    "HYPO_3A_001_30M_MIDDAY_TREND",
    "HYPO_3A_002_60M_HIGH_BETA",
    "HYPO_3A_003_15M_SHORT_SPARSITY"
])


@dataclass(frozen=True)
class CandidateHypothesis:
    id: str
    horizon: str                               # e.g., "5m", "15m", "30m", "60m"
    side: str                                  # "LONG", "SHORT", "LONG_AND_SHORT"
    time_window: Optional[str]                 # e.g., "09:15-10:00", "11:00-13:00", None
    volatility_regime: Optional[str]           # e.g., "HIGH_VOL", "NORMAL_VOL", None
    signal_threshold_quantile: float           # e.g., 90.0, 95.0, 99.0
    interaction_rules: Dict[str, Any]          # e.g., {"time_vol": "09:15-10:00 x HIGH_VOL"}
    execution_scenario: str                    # "BASE_AGGRESSIVE", "PASSIVE", "CONSERVATIVE_PASSIVE"
    execution_scenario_id: str                 # Explicit scenario identifier
    cost_model_version: str                    # e.g., "v2.2_execution_tree"
    labeler_version: str                       # e.g., "v2.0_raw_forward_returns"
    minimum_trade_size: int                    # e.g., 30
    created_from_phase3a: bool
    frozen_at: str
    feature_set_hash: str
    definition_hash: str

    @classmethod
    def create(
        cls,
        id: str,
        horizon: str,
        side: str,
        signal_threshold_quantile: float,
        execution_scenario: str = "BASE_AGGRESSIVE",
        execution_scenario_id: Optional[str] = None,
        cost_model_version: str = "v2.2_execution_tree",
        labeler_version: str = "v2.0_raw_forward_returns",
        time_window: Optional[str] = None,
        volatility_regime: Optional[str] = None,
        interaction_rules: Optional[Dict[str, Any]] = None,
        minimum_trade_size: int = 30,
        feature_columns: Optional[List[str]] = None
    ) -> "CandidateHypothesis":
        """
        Constructs a frozen, deterministic candidate hypothesis with cryptographically verifiable hashes.
        """
        scenario_id = execution_scenario_id or execution_scenario
        interaction_dict = interaction_rules or {}
        features = sorted(feature_columns) if feature_columns else ["ALL_PHASE3_FEATURES"]
        feat_str = json.dumps(features, sort_keys=True)
        feat_hash = hashlib.sha256(feat_str.encode("utf-8")).hexdigest()[:16]

        frozen_timestamp = datetime.now(timezone.utc).isoformat()

        core_def = {
            "id": id,
            "horizon": horizon,
            "side": side,
            "time_window": time_window,
            "volatility_regime": volatility_regime,
            "signal_threshold_quantile": signal_threshold_quantile,
            "interaction_rules": interaction_dict,
            "execution_scenario": execution_scenario,
            "execution_scenario_id": scenario_id,
            "cost_model_version": cost_model_version,
            "labeler_version": labeler_version,
            "minimum_trade_size": minimum_trade_size,
            "feature_set_hash": feat_hash
        }
        def_str = json.dumps(core_def, sort_keys=True)
        def_hash = hashlib.sha256(def_str.encode("utf-8")).hexdigest()

        return cls(
            id=id,
            horizon=horizon,
            side=side,
            time_window=time_window,
            volatility_regime=volatility_regime,
            signal_threshold_quantile=signal_threshold_quantile,
            interaction_rules=interaction_dict,
            execution_scenario=execution_scenario,
            execution_scenario_id=scenario_id,
            cost_model_version=cost_model_version,
            labeler_version=labeler_version,
            minimum_trade_size=minimum_trade_size,
            created_from_phase3a=True,
            frozen_at=frozen_timestamp,
            feature_set_hash=feat_hash,
            definition_hash=def_hash
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def verify_integrity(self) -> bool:
        """Verifies definition hash against core parameters."""
        core_def = {
            "id": self.id,
            "horizon": self.horizon,
            "side": self.side,
            "time_window": self.time_window,
            "volatility_regime": self.volatility_regime,
            "signal_threshold_quantile": self.signal_threshold_quantile,
            "interaction_rules": self.interaction_rules,
            "execution_scenario": self.execution_scenario,
            "execution_scenario_id": self.execution_scenario_id,
            "cost_model_version": self.cost_model_version,
            "labeler_version": self.labeler_version,
            "minimum_trade_size": self.minimum_trade_size,
            "feature_set_hash": self.feature_set_hash
        }
        recomputed_hash = hashlib.sha256(json.dumps(core_def, sort_keys=True).encode("utf-8")).hexdigest()
        if recomputed_hash != self.definition_hash:
            raise CandidateTamperingError(
                f"Cryptographic tampering detected in candidate {self.id}: "
                f"recomputed {recomputed_hash} != frozen {self.definition_hash}"
            )
        return True

    def save_to_file(self, file_path: str) -> None:
        """Saves hypothesis to a designated JSON artifact."""
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        data = []
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    existing = json.load(f)
                    data = existing if isinstance(existing, list) else [existing]
            except Exception:
                data = []

        # Replace existing with same ID or append
        data = [d for d in data if d.get("id") != self.id]
        data.append(self.to_dict())

        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_from_dict(cls, d: Dict[str, Any], enforce_locked_set: bool = True) -> "CandidateHypothesis":
        """Loads, validates against locked set, and verifies definition hash integrity."""
        # Backward compatibility for dictionaries without new version fields
        d_copy = dict(d)
        if "execution_scenario_id" not in d_copy:
            d_copy["execution_scenario_id"] = d_copy.get("execution_scenario", "BASE_AGGRESSIVE")
        if "cost_model_version" not in d_copy:
            d_copy["cost_model_version"] = "v2.2_execution_tree"
        if "labeler_version" not in d_copy:
            d_copy["labeler_version"] = "v2.0_raw_forward_returns"

        hypo = cls(**d_copy)

        if enforce_locked_set and hypo.id not in LOCKED_PHASE3B_CANDIDATE_IDS:
            raise ProhibitedCandidateReplacementError(
                f"Candidate {hypo.id} is not in the locked Phase 3B candidate set: {sorted(list(LOCKED_PHASE3B_CANDIDATE_IDS))}. "
                "Candidate substitution during Phase 3B is strictly prohibited."
            )

        hypo.verify_integrity()
        return hypo
