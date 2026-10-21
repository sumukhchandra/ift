"""
v3/ensemble/specialist_signal.py
Standardized signal schema for all AlphaNSE specialist models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List


class SignalDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WAIT = "WAIT"

    @property
    def numeric_value(self) -> int:
        if self == SignalDirection.BUY:
            return 1
        elif self == SignalDirection.SELL:
            return -1
        return 0


class HorizonCategory(str, Enum):
    INTRADAY_5M = "5m"
    INTRADAY_15M = "15m"
    INTRADAY_30M = "30m"
    INTRADAY_60M = "60m"
    MULTI_DAY_SWING = "3D"


@dataclass
class SpecialistSignal:
    """
    Standardized atomic signal produced by an independent specialist model.
    """
    symbol: str
    model_id: str
    model_name: str
    direction: SignalDirection
    horizon: HorizonCategory
    confidence: float                  # Normalized 0.0 to 1.0
    predicted_return_pct: float        # Expected price return percentage
    expected_holding_mins: int         # Recommended holding window in minutes
    timestamp: datetime = field(default_factory=datetime.now)
    rationale: str = ""
    features: Dict[str, float] = field(default_factory=dict)
    raw_metrics: Dict[str, Any] = field(default_factory=dict)

    def is_directional(self) -> bool:
        return self.direction in (SignalDirection.BUY, SignalDirection.SELL)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "direction": self.direction.value,
            "horizon": self.horizon.value,
            "confidence": round(self.confidence, 4),
            "predicted_return_pct": round(self.predicted_return_pct, 4),
            "expected_holding_mins": self.expected_holding_mins,
            "timestamp": self.timestamp.isoformat(),
            "rationale": self.rationale,
            "features": self.features,
            "raw_metrics": self.raw_metrics
        }
