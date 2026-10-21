"""
AlphaNSE V3 — Daily Model Retraining & Sanity Gating Engine.
Retrains an adaptive ridge return regressor specifically for the 60-minute (12-bar) horizon.

STATUS: EXPERIMENT / VALIDATION
Maintains strict pre-market sanity gates:
  1. Zero Lookahead (Training data strictly < Day D open)
  2. Feature Matrix Integrity (All 26 features, zero NaNs, zero Infs)
  3. Target Validity (Valid 60m return distribution)
  4. Market Regime Classification at Open
  5. Cryptographic Weight Freezing & SHA-256 Hashing
"""

import os
import pickle
import hashlib
import logging
from datetime import date, datetime, timezone
from typing import Dict, Any, Tuple, Optional
import numpy as np
import pandas as pd

from v2.features.feature_pipeline import FeaturePipeline, ALL_FEATURE_COLUMNS
from v2.features.labeling import IntradayLabeler
from v2.models.estimators import RidgeReturnRegressor
from v3.config.v3_config import (
    HORIZON_BARS,
    TARGET_RETURN_COLUMN,
    ALPHA_RIDGE,
    COST_HURDLE_BPS,
    V3_MODELS_DIR,
    EXPERIMENT_MODE,
    PROFITABILITY_CLAIM,
    REPLAY_DISCLAIMER
)
from v3.adaptive.audit_ledger_v3 import DailyModelManifestV3

logger = logging.getLogger(__name__)


class ModelSanityGateError(Exception):
    """Raised when pre-market model validation fails."""
    pass


class ModelUpdaterV3:
    """
    Orchestrates daily 60m model retraining, validation, and freezing.
    """

    def __init__(
        self,
        models_dir: str = V3_MODELS_DIR,
        horizon_bars: int = HORIZON_BARS,
        alpha_ridge: float = ALPHA_RIDGE,
        target_col: str = TARGET_RETURN_COLUMN
    ):
        self.models_dir = models_dir
        self.horizon_bars = horizon_bars
        self.alpha_ridge = alpha_ridge
        self.target_col = target_col
        os.makedirs(self.models_dir, exist_ok=True)

    def train_and_freeze_for_day(
        self,
        target_day: date,
        dataset_meta: Dict[str, Any],
        is_forward_validation: bool = False
    ) -> Tuple[RidgeReturnRegressor, DailyModelManifestV3]:
        """
        Executes pre-market feature engineering, retraining, sanity gating, and freezing for Day D.
        Strictly requires all training observations to be < target_day.
        """
        logger.info(f"[V3] Retraining adaptive 60m model for session: {target_day}...")

        raw_path = dataset_meta["raw_path"]
        adj_path = dataset_meta["adj_path"]
        data_cutoff = dataset_meta["data_cutoff"]
        dataset_hash = dataset_meta["dataset_hash"]
        training_rows = dataset_meta["training_rows"]

        # 1. Feature Engineering
        pipeline = FeaturePipeline(raw_parquet_path=raw_path, adj_parquet_path=adj_path)
        feature_df = pipeline.compute_all_features()

        # 2. Labeling specifically for 60m (12 bars * 5m)
        labeler = IntradayLabeler(horizons=[self.horizon_bars], cost_hurdle_bps=COST_HURDLE_BPS)
        labeled_df = labeler.construct_forward_labels(feature_df)

        # Tradable universe (exclude ^NSEI index benchmark)
        tradable_df = labeled_df[labeled_df["symbol"] != "^NSEI"].copy().reset_index(drop=True)
        tradable_df["date"] = pd.to_datetime(tradable_df["timestamp"]).dt.date

        # --- PRE-MARKET SANITY GATE 1: ZERO LEAKAGE CHECK ---
        max_train_ts = pd.to_datetime(tradable_df["timestamp"]).max()
        if max_train_ts.date() >= target_day:
            raise ModelSanityGateError(
                f"[V3 LEAKAGE VIOLATION] Training set contains timestamp {max_train_ts} >= {target_day}!"
            )

        # --- PRE-MARKET SANITY GATE 2: FEATURE INTEGRITY CHECK ---
        missing_features = [col for col in ALL_FEATURE_COLUMNS if col not in tradable_df.columns]
        if missing_features:
            raise ModelSanityGateError(f"[V3 FEATURE INTEGRITY ERROR] Missing columns: {missing_features}")

        if self.target_col not in tradable_df.columns:
            raise ModelSanityGateError(f"[V3 TARGET ERROR] Target column {self.target_col} missing from labeled dataset!")

        clean_df = tradable_df.dropna(subset=[self.target_col] + ALL_FEATURE_COLUMNS).copy()
        if clean_df.empty:
            raise ModelSanityGateError("[V3 FEATURE INTEGRITY ERROR] Clean training dataframe is empty after dropping NaNs!")

        X = clean_df[ALL_FEATURE_COLUMNS].values
        y = clean_df[self.target_col].values

        if np.isinf(X).any():
            raise ModelSanityGateError("[V3 FEATURE INTEGRITY ERROR] Feature matrix contains infinite values!")
        if np.isnan(y).any() or np.isinf(y).any():
            raise ModelSanityGateError("[V3 TARGET ERROR] Target vector contains NaN or Inf values!")

        # --- PRE-MARKET SANITY GATE 3: SAMPLE COUNT & VARIANCE CHECK ---
        if len(clean_df) < 500:
            raise ModelSanityGateError(f"[V3 SAMPLE CHECK FAILED] Insufficient training rows: {len(clean_df)} < 500")

        target_std = np.std(y)
        if target_std < 1e-6:
            raise ModelSanityGateError(f"[V3 TARGET DEGENERATE] Target standard deviation is zero: {target_std}")

        # --- PRE-MARKET SANITY GATE 4: REGIME CLASSIFICATION AT OPEN ---
        unique_dates = sorted(clean_df["date"].unique())
        recent_dates = unique_dates[-10:] if len(unique_dates) >= 10 else unique_dates
        recent_subset = clean_df[clean_df["date"].isin(recent_dates)]
        daily_vol = recent_subset.groupby("date")["adj_log_return_5m"].std() * np.sqrt(75 * 252) * 100.0
        avg_recent_vol = float(daily_vol.mean())

        if avg_recent_vol < 15.0:
            regime_at_open = "LOW_VOL"
        elif avg_recent_vol <= 20.0:
            regime_at_open = "NORMAL_VOL"
        else:
            regime_at_open = "HIGH_VOL"

        # --- STEP 4: MODEL RETRAINING ---
        model = RidgeReturnRegressor(alpha=self.alpha_ridge)
        model.fit(X, y)

        # In-sample validation metrics
        preds = model.predict(X)
        mae = float(np.mean(np.abs(preds - y)))
        corr = float(np.corrcoef(preds, y)[0, 1]) if np.std(preds) > 1e-6 else 0.0

        validation_result = {
            "in_sample_rows": len(clean_df),
            "mae_bps": round(mae * 10000.0, 2),
            "ic_in_sample": round(corr, 4),
            "regime_vol_annualized": round(avg_recent_vol, 2),
            "alpha": self.alpha_ridge,
            "target_horizon": f"{self.horizon_bars * 5}m",
            "passed_sanity_gates": True
        }

        # --- STEP 6: MODEL FREEZING & CRYPTOGRAPHIC HASHING ---
        target_str = target_day.strftime("%Y%m%d")
        model_bytes = pickle.dumps(model)
        model_hash = hashlib.sha256(model_bytes).hexdigest()
        model_version = f"AlphaNSE_V3_60m_{target_str}_v1"

        model_file = os.path.join(self.models_dir, f"model_v3_{target_str}.pkl")
        with open(model_file, "wb") as f:
            f.write(model_bytes)

        # Compute feature pipeline version hash
        feature_version = hashlib.sha256("".join(ALL_FEATURE_COLUMNS).encode()).hexdigest()[:16]

        min_train_date = clean_df["date"].min().strftime("%Y-%m-%d")
        max_train_date = clean_df["date"].max().strftime("%Y-%m-%d")
        training_window = f"{min_train_date} to {max_train_date}"

        disclaimer = "FRESH FORWARD VALIDATION" if is_forward_validation else REPLAY_DISCLAIMER

        manifest = DailyModelManifestV3(
            session_date=target_day.strftime("%Y-%m-%d"),
            data_cutoff=data_cutoff,
            dataset_hash=dataset_hash,
            feature_version=feature_version,
            model_version=model_version,
            model_hash=model_hash,
            target_column=self.target_col,
            horizon_bars=self.horizon_bars,
            training_window=training_window,
            training_rows=len(clean_df),
            validation_result=validation_result,
            regime_at_open=regime_at_open,
            created_at=datetime.now(timezone.utc).isoformat(),
            experiment_mode=EXPERIMENT_MODE,
            profitability_claim=PROFITABILITY_CLAIM,
            disclaimer=disclaimer
        )

        logger.info(
            f"[V3] Model {model_version} frozen. SHA-256: {model_hash[:16]}... "
            f"Regime: {regime_at_open}, Rows: {len(clean_df)}, IC: {corr:.4f}"
        )
        return model, manifest
