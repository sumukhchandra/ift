"""
Model Registry & Prediction Configuration for AlphaNSE V2.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    """
    Configuration for ML modeling and inference.
    
    IMPORTANT NOTE:
    The 5-minute prediction horizon is a PRIMARY RESEARCH EXPERIMENT.
    Expected return distributions and empirical net edges must be measured
    statistically on real multi-month historical data before promotion.
    It is NOT treated as a proven fact or design guarantee.
    """
    target_horizon: str = "5m"                 # 5-minute candle prediction target
    is_experimental_horizon: bool = True       # Enforces research status until validated
    min_confidence_threshold: float = 0.45     # Hurdle for calibrated breakout probability
    base_features_count: int = 30              # Expected dimensionality of feature vector
    min_historical_sessions_required: int = 120 # Minimum sessions needed to exit DATA_BLOCKED
    purged_cv_folds: int = 5                   # Purged K-fold splits
    embargo_pct: float = 0.01                  # Embargo window after test sets (1%)
