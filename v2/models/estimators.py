"""
Candidate Quantitative Estimators for AlphaNSE V2.
Implements:
  1. RidgeReturnRegressor: L2-regularized linear baseline.
  2. LightGBMReturnRegressor: Constrained gradient boosted tree regressor.
  3. CalibratedDirectionClassifier: Directional classifier with isotonic calibration.
Enforces the 'Frozen Model' invariant: once calibrated on Validation,
the estimator is frozen and cannot be updated on Test data.
"""

import logging
from typing import Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import RobustScaler
from sklearn.isotonic import IsotonicRegression
import lightgbm as lgb

logger = logging.getLogger(__name__)


class ModelFrozenError(Exception):
    """Raised when an illegal modification is attempted on a frozen model."""
    pass


class RidgeReturnRegressor:
    """
    L2-regularized linear baseline regressor.
    """

    def __init__(self, alpha: float = 10.0):
        self.alpha = alpha
        self.scaler = RobustScaler()
        self.model = Ridge(alpha=self.alpha)
        self.is_frozen = False
        self.val_ic: float = 0.0

    def fit(self, X_train: np.ndarray, y_train: np.ndarray) -> "RidgeReturnRegressor":
        if self.is_frozen:
            raise ModelFrozenError("Cannot fit a frozen model.")
        X_scaled = self.scaler.fit_transform(X_train)
        self.model.fit(X_scaled, y_train)
        return self

    def tune_and_calibrate(self, X_val: np.ndarray, y_val: np.ndarray) -> None:
        """Evaluate validation IC to verify signal direction."""
        if self.is_frozen:
            raise ModelFrozenError("Cannot calibrate a frozen model.")
        preds = self.predict(X_val)
        valid = ~np.isnan(preds) & ~np.isnan(y_val)
        if valid.sum() > 10:
            corr = np.corrcoef(preds[valid], y_val[valid])[0, 1]
            self.val_ic = float(corr) if not np.isnan(corr) else 0.0

    def freeze(self) -> None:
        """Freeze model state prior to out-of-sample test evaluation."""
        self.is_frozen = True

    def predict(self, X: np.ndarray) -> np.ndarray:
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)


class LightGBMReturnRegressor:
    """
    Gradient boosted decision trees constrained against overfitting:
    shallow trees (depth 4), large min_child_samples (50), L2 regularizer.
    """

    def __init__(
        self,
        n_estimators: int = 80,
        learning_rate: float = 0.03,
        max_depth: int = 4,
        num_leaves: int = 15,
        min_child_samples: int = 50,
        reg_lambda: float = 2.0
    ):
        self.params = {
            "n_estimators": n_estimators,
            "learning_rate": learning_rate,
            "max_depth": max_depth,
            "num_leaves": num_leaves,
            "min_child_samples": min_child_samples,
            "reg_lambda": reg_lambda,
            "random_state": 42,
            "verbose": -1,
            "n_jobs": -1
        }
        self.model = lgb.LGBMRegressor(**self.params)
        self.is_frozen = False
        self.val_ic: float = 0.0

    def fit(self, X_train: np.ndarray, y_train: np.ndarray) -> "LightGBMReturnRegressor":
        if self.is_frozen:
            raise ModelFrozenError("Cannot fit a frozen model.")
        self.model.fit(X_train, y_train)
        return self

    def tune_and_calibrate(self, X_val: np.ndarray, y_val: np.ndarray) -> None:
        if self.is_frozen:
            raise ModelFrozenError("Cannot calibrate a frozen model.")
        preds = self.predict(X_val)
        valid = ~np.isnan(preds) & ~np.isnan(y_val)
        if valid.sum() > 10:
            corr = np.corrcoef(preds[valid], y_val[valid])[0, 1]
            self.val_ic = float(corr) if not np.isnan(corr) else 0.0

    def freeze(self) -> None:
        self.is_frozen = True

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict(X)


class CalibratedDirectionClassifier:
    """
    LightGBM classifier predicting P(R > +CostHurdle) with Isotonic Probability Calibration.
    """

    def __init__(
        self,
        n_estimators: int = 80,
        learning_rate: float = 0.03,
        max_depth: int = 4,
        num_leaves: int = 15,
        min_child_samples: int = 50,
        reg_lambda: float = 2.0
    ):
        self.params = {
            "n_estimators": n_estimators,
            "learning_rate": learning_rate,
            "max_depth": max_depth,
            "num_leaves": num_leaves,
            "min_child_samples": min_child_samples,
            "reg_lambda": reg_lambda,
            "random_state": 42,
            "verbose": -1,
            "n_jobs": -1
        }
        self.base_model = lgb.LGBMClassifier(**self.params)
        self.calibrator = IsotonicRegression(out_of_bounds="clip")
        self.is_frozen = False
        self.val_accuracy: float = 0.0

    def fit(self, X_train: np.ndarray, y_train: np.ndarray) -> "CalibratedDirectionClassifier":
        if self.is_frozen:
            raise ModelFrozenError("Cannot fit a frozen model.")
        # Binary target: 1 if return > 0, 0 otherwise
        binary_y = (y_train > 0).astype(int)
        self.base_model.fit(X_train, binary_y)
        return self

    def tune_and_calibrate(self, X_val: np.ndarray, y_val: np.ndarray) -> None:
        if self.is_frozen:
            raise ModelFrozenError("Cannot calibrate a frozen model.")
        # Uncalibrated raw probabilities
        raw_probs = self.base_model.predict_proba(X_val)[:, 1]
        val_binary = (y_val > 0).astype(int)
        # Fit isotonic calibrator strictly on validation set
        self.calibrator.fit(raw_probs, val_binary)
        cal_preds = self.calibrator.predict(raw_probs)
        self.val_accuracy = float(np.mean((cal_preds > 0.5) == val_binary))

    def freeze(self) -> None:
        self.is_frozen = True

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        raw_probs = self.base_model.predict_proba(X)[:, 1]
        return self.calibrator.predict(raw_probs)

    def predict(self, X: np.ndarray) -> np.ndarray:
        probs = self.predict_proba(X)
        return (probs > 0.5).astype(int)
