"""
AlphaNSE V3 — Base Model Specifications & Standardized Decision Representations.
Provides common contracts for the 5 research models participating in Session 5:
  1. Standardized Model Output Normalization
  2. Cryptographic Frozen Model Metadata Schema
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class ModelPredictionOutput:
    """
    Normalized decision representation for any individual model participating in AlphaNSE.
    Converts heterogeneous horizons and targets into a standardized decision interface.
    Supports Section 1 rich output requirements: BUY, SELL, HOLD, NO_SIGNAL.
    """
    model_id: str
    direction: int                      # +1 for Long, -1 for Short, 0 for Neutral
    expected_gross_return_bps: float    # Expected gross return in bps
    confidence: float                   # Calibrated confidence score (0.0 to 1.0)
    horizon_minutes: int                # Intended holding horizon in minutes (15, 30, or 60)
    model_validity: bool                # True if model passed pre-market sanity gates
    raw_prediction_bps: float           # Raw uncalibrated model output
    model_hash: str                     # SHA-256 hash of model artifact

    # Section 1 Rich Model Output Specifications
    signal_type: str = "HOLD"           # "BUY", "SELL", "HOLD", "NO_SIGNAL"
    symbol: str = ""                    # e.g. "TATACAP.NS"
    predicted_high: float = 0.0         # Expected peak price during horizon
    predicted_low: float = 0.0          # Expected trough price during horizon
    predicted_close: float = 0.0        # Expected exit price
    expected_move_bps: float = 0.0      # Expected absolute move in bps
    expected_time_to_edge: int = 15     # Expected minutes until edge realizes
    expected_holding_time: int = 15     # Expected holding time in minutes
    risk_estimate: float = 0.0          # Volatility / risk estimate in bps
    model_regime: str = "NORMAL_VOL"    # Regime classification
    signal_strength: float = 0.0        # Signal conviction score (0.0 to 1.0)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FrozenModelMetadata:
    """
    Authoritative 16-field metadata specification for an independently validated,
    frozen Session 5 model.
    """
    model_id: str                       # e.g. "HYPO002"
    model_version: str                  # e.g. "AlphaNSE_HYPO002_20260925_v1"
    model_hash: str                     # SHA-256 hash of serialized model weights
    dataset_hash: str                   # SHA-256 hash of D-1 training dataset
    training_cutoff: str                # e.g. "2026-09-24T15:25:00+05:30"
    feature_schema_hash: str            # SHA-256 hash of the 26 feature column names
    target_definition: str              # e.g. "target_return_60m"
    target_horizon_minutes: int         # 15, 30, or 60
    training_sample_count: int          # Clean observations used in training
    validation_sample_count: int        # Observations used in in-sample validation
    validation_metrics: Dict[str, Any]  # MAE, IC, R2, etc.
    regime: str                         # "LOW_VOL", "NORMAL_VOL", "HIGH_VOL"
    direction: str                      # "LONG_AND_SHORT" or "SHORT_SPARSITY"
    expected_return_units: str          # "bps"
    confidence: float                   # Base model in-sample confidence (0.0 to 1.0)
    status: str                         # "FROZEN" or "INVALID_FOR_SESSION"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FrozenModelMetadata":
        return cls(**data)
