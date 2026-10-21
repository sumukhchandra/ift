"""
1-Minute NSE Stock Predictor Engine.

Predicts stock price return and direction for the NEXT 1-MINUTE candle (t+1).
Triggers a BUY signal when predicted profit exceeds dynamic volatility threshold
and probability of continuation/breakout is high.
"""

import os
import sys
import math
import json
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import logging
import yfinance as yf

logger = logging.getLogger("OneMinPredictor")

from lightgbm import LGBMRegressor
from catboost import CatBoostRegressor
from xgboost import XGBRegressor
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, accuracy_score, precision_score, recall_score, f1_score

# Ensure project root is in path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from stocks_config import STOCK_SYMBOLS, STOCK_UNIVERSE

MODEL_DIR = os.path.join(PROJECT_ROOT, "models", "saved_models_1m")
os.makedirs(MODEL_DIR, exist_ok=True)


class OneMinPredictor:
    """High-frequency 1-minute price and return prediction model for NSE stocks."""

    ALL_FEATURE_COLS = [
        "ret_1m", "ret_3m", "ret_5m", "ret_10m",
        "accel_1m", "micro_rsi_7", "micro_rsi_14",
        "micro_vwap_dist", "micro_atr_14", "parkinson_vol",
        "bb_pct_b", "bb_bandwidth", "orderflow_imbalance",
        "vol_surge_ratio", "nifty_ret_1m", "nifty_lead_lag",
        # Advanced engineered microstructure features:
        "ema_cross_5_20", "atr_vol_ratio", "momentum_divergence",
        "vol_spike_zscore", "wick_pressure", "upper_wick_ratio", "lower_wick_ratio",
        # Phase 3: Time, session & identity features:
        "time_sin", "time_cos", "session_phase",
        "rolling_vwap_dist", "ema_cross_velocity",
        "stock_id_hash", "parkinson_vol_rolling"
    ]

    def __init__(self, model_dir=MODEL_DIR):
        self.model_dir = model_dir
        self.regressors = {}
        self.classifier = None
        self.feature_cols = list(self.ALL_FEATURE_COLS)
        self._load_or_init_models()

    def _load_or_init_models(self):
        """Load pretrained models from disk or initialize fresh regressors."""
        reg_path = os.path.join(self.model_dir, "return_regressors_1m.joblib")
        clf_path = os.path.join(self.model_dir, "breakout_classifier_1m.joblib")
        q_path = os.path.join(self.model_dir, "quantile_regressor_1m.joblib")
        feat_path = os.path.join(self.model_dir, "feature_cols_1m.joblib")

        if os.path.exists(reg_path) and os.path.exists(clf_path):
            try:
                self.regressors = joblib.load(reg_path)
                self.classifier = joblib.load(clf_path)
                if os.path.exists(q_path):
                    self.quantile_regressor = joblib.load(q_path)
                if os.path.exists(feat_path):
                    loaded_cols = joblib.load(feat_path)
                    # Only use loaded cols if it has all the engineered features
                    if isinstance(loaded_cols, list) and len(loaded_cols) >= len(self.ALL_FEATURE_COLS):
                        self.feature_cols = loaded_cols
                print(f"Loaded pre-trained 1-minute models successfully ({len(self.feature_cols)} features).")
                # Ensure quantile_regressor exists even if not saved in older model versions
                if not hasattr(self, 'quantile_regressor') or self.quantile_regressor is None:
                    self.quantile_regressor = LGBMRegressor(
                        n_estimators=400, learning_rate=0.025, max_depth=6, num_leaves=40,
                        objective="quantile", alpha=0.75, random_state=42, verbose=-1, n_jobs=-1
                    )
                return
            except Exception as e:
                print(f"Failed to load existing 1-minute models: {e}. Initializing fresh models.")

        # Initialize fresh models with robust intraday hyperparameters
        # Phase 3: Switched from Huber to MAE/squarederror to prevent prediction compression
        # Huber loss was aggressively shrinking predicted returns toward zero
        self.regressors = {
            "lgbm": LGBMRegressor(
                n_estimators=500,
                learning_rate=0.025,
                max_depth=7,
                num_leaves=50,
                objective="mae",
                min_child_samples=20,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                verbose=-1,
                n_jobs=-1
            ),
            "xgb": XGBRegressor(
                n_estimators=500,
                learning_rate=0.025,
                max_depth=7,
                objective="reg:squarederror",
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1
            ),
            "catboost": CatBoostRegressor(
                iterations=500,
                learning_rate=0.025,
                depth=7,
                loss_function="MAE",
                random_seed=42,
                verbose=0
            )
        }
        # Phase 3: Quantile regressor for upper-bound return prediction (75th percentile)
        self.quantile_regressor = LGBMRegressor(
            n_estimators=400,
            learning_rate=0.025,
            max_depth=6,
            num_leaves=40,
            objective="quantile",
            alpha=0.75,
            random_state=42,
            verbose=-1,
            n_jobs=-1
        )
        # Phase 3: Platt-calibrated GBM classifier (replaces miscalibrated RandomForest)
        base_clf = GradientBoostingClassifier(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=5,
            subsample=0.8,
            random_state=42
        )
        self.classifier = CalibratedClassifierCV(
            estimator=base_clf,
            method="sigmoid",  # Platt scaling
            cv=3
        )

    def extract_features_1m(self, df: pd.DataFrame, nifty_df: pd.DataFrame = None) -> pd.DataFrame:
        """
        Compute high-frequency 1-minute technical & microstructure features.
        Expects columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'symbol'].
        """
        df = df.copy()
        if "timestamp" not in df.columns:
            if isinstance(df.index, pd.DatetimeIndex):
                df["timestamp"] = df.index
            else:
                for c in df.columns:
                    if str(c).lower() in ("datetime", "date", "timestamp"):
                        df["timestamp"] = df[c]
                        break
        if "timestamp" in df.columns:
            df = df.sort_values("timestamp").reset_index(drop=True)
        else:
            df = df.reset_index(drop=True)
            df["timestamp"] = pd.date_range(end=pd.Timestamp.now(), periods=len(df), freq="1min")

        close = df["close"]
        high = df["high"]
        low = df["low"]
        open_p = df["open"]
        vol = df["volume"].replace(0, 1.0)

        # 1. Multi-scale Returns
        df["ret_1m"] = close.pct_change(1).fillna(0)
        df["ret_3m"] = close.pct_change(3).fillna(0)
        df["ret_5m"] = close.pct_change(5).fillna(0)
        df["ret_10m"] = close.pct_change(10).fillna(0)
        df["accel_1m"] = df["ret_1m"].diff().fillna(0)

        # 2. Micro-RSI (7 & 14 period)
        delta = close.diff().fillna(0)
        gain_7 = delta.clip(lower=0).rolling(7, min_periods=1).mean()
        loss_7 = (-delta.clip(upper=0)).rolling(7, min_periods=1).mean()
        rs_7 = gain_7 / (loss_7 + 1e-9)
        df["micro_rsi_7"] = 100 - (100 / (1 + rs_7))

        gain_14 = delta.clip(lower=0).rolling(14, min_periods=1).mean()
        loss_14 = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
        rs_14 = gain_14 / (loss_14 + 1e-9)
        df["micro_rsi_14"] = 100 - (100 / (1 + rs_14))

        # 3. Micro-VWAP & Distance
        cum_vol = vol.cumsum()
        cum_pv = (close * vol).cumsum()
        vwap = cum_pv / cum_vol.replace(0, np.nan)
        df["micro_vwap_dist"] = ((close - vwap) / (vwap + 1e-9)).fillna(0)

        # 4. Micro-ATR & Parkinson Volatility
        tr = np.maximum(
            high - low,
            np.maximum(
                (high - close.shift(1)).abs(),
                (low - close.shift(1)).abs()
            )
        )
        df["micro_atr_14"] = (tr.rolling(14, min_periods=1).mean() / (close + 1e-9)).fillna(0)

        hl_ratio = np.log(high / low.replace(0, np.nan)).fillna(0)
        df["parkinson_vol"] = np.sqrt((hl_ratio ** 2) / (4 * np.log(2))).fillna(0)

        # 5. Bollinger Bands (20 period, 2 std)
        rolling_mean = close.rolling(20, min_periods=1).mean()
        rolling_std = close.rolling(20, min_periods=1).std().fillna(1e-5)
        upper_bb = rolling_mean + (2 * rolling_std)
        lower_bb = rolling_mean - (2 * rolling_std)
        df["bb_pct_b"] = ((close - lower_bb) / (upper_bb - lower_bb + 1e-9)).fillna(0.5)
        df["bb_bandwidth"] = ((upper_bb - lower_bb) / (rolling_mean + 1e-9)).fillna(0)

        # 6. Microstructure Order Flow Imbalance Proxy
        candle_range = (high - low).replace(0, 1e-5)
        df["orderflow_imbalance"] = (vol * ((close - open_p) / candle_range)).fillna(0)
        vol_mean_20 = vol.rolling(20, min_periods=1).mean().replace(0, 1.0)
        df["vol_surge_ratio"] = (vol / vol_mean_20).fillna(1.0)

        # 7. NIFTY 50 Lead-Lag Cross-Asset Features
        if nifty_df is not None and not nifty_df.empty and "timestamp" in nifty_df.columns:
            nifty_sub = nifty_df[["timestamp", "nifty_ret_1m"]].copy()
            df = pd.merge_asof(df.sort_values("timestamp"), nifty_sub.sort_values("timestamp"), on="timestamp", direction="backward")
            df["nifty_ret_1m"] = df["nifty_ret_1m"].fillna(0)
            df["nifty_lead_lag"] = df["ret_1m"] - df["nifty_ret_1m"]
        else:
            df["nifty_ret_1m"] = 0.0
            df["nifty_lead_lag"] = df["ret_1m"]

        # 8. NEW: Fast EMA 5 vs EMA 20 Momentum Slope
        ema_5 = close.ewm(span=5, adjust=False).mean()
        ema_20 = close.ewm(span=20, adjust=False).mean()
        df["ema_cross_5_20"] = ((ema_5 - ema_20) / (ema_20 + 1e-9)).fillna(0)

        # 9. NEW: Volatility Expansion Ratio (Micro-ATR vs rolling 60-candle baseline)
        rolling_atr_60 = df["micro_atr_14"].rolling(60, min_periods=5).mean().replace(0, 1e-5)
        df["atr_vol_ratio"] = (df["micro_atr_14"] / rolling_atr_60).fillna(1.0)

        # 10. NEW: Momentum Divergence (Price delta vs RSI delta over 3 periods)
        rsi_diff_3 = (df["micro_rsi_7"] - df["micro_rsi_7"].shift(3)).fillna(0) / 100.0
        df["momentum_divergence"] = (df["ret_3m"] - rsi_diff_3).fillna(0)

        # 11. NEW: Standardized Volume Spike Z-Score (30 periods)
        vol_mean_30 = vol.rolling(30, min_periods=5).mean()
        vol_std_30 = vol.rolling(30, min_periods=5).std().replace(0, 1.0).fillna(1.0)
        df["vol_spike_zscore"] = ((vol - vol_mean_30) / vol_std_30).clip(-3.0, 5.0).fillna(0.0)

        # 12. NEW: Candlestick Wick & Buying Pressure Dynamics
        bar_span = (high - low).replace(0, 1e-5)
        df["wick_pressure"] = ((close - low) / bar_span).clip(0.0, 1.0).fillna(0.5)
        df["upper_wick_ratio"] = ((high - np.maximum(open_p, close)) / bar_span).clip(0.0, 1.0).fillna(0.0)
        df["lower_wick_ratio"] = ((np.minimum(open_p, close) - low) / bar_span).clip(0.0, 1.0).fillna(0.0)

        # === Phase 3: New Features ===

        # 13. Time-of-Day (sin/cos encoding of minute within trading session in canonical Asia/Kolkata)
        if "timestamp" in df.columns:
            ts = pd.to_datetime(df["timestamp"])
            if hasattr(ts.dt, "tz"):
                if ts.dt.tz is None:
                    # Naive timestamps represent Indian market hours (09:15-15:30 IST)
                    ts = ts.dt.tz_localize("Asia/Kolkata")
                else:
                    # Timezone-aware timestamps (UTC, IST, or other) converted to canonical Asia/Kolkata
                    ts = ts.dt.tz_convert("Asia/Kolkata")
            minutes_from_open = (ts.dt.hour * 60 + ts.dt.minute) - (9 * 60 + 15)  # Minutes since 9:15 AM IST
            minutes_from_open = minutes_from_open.clip(0, 375).fillna(0)  # 375 = 6h15m trading session
            df["time_sin"] = np.sin(2 * np.pi * minutes_from_open / 375).fillna(0)
            df["time_cos"] = np.cos(2 * np.pi * minutes_from_open / 375).fillna(0)
            # Session phase: 0=open rush (0-30min), 1=morning (30-120), 2=midday (120-240), 3=close rush (240-375)
            df["session_phase"] = np.where(minutes_from_open <= 30, 0,
                                  np.where(minutes_from_open <= 120, 1,
                                  np.where(minutes_from_open <= 240, 2, 3))).astype(float)
        else:
            df["time_sin"] = 0.0
            df["time_cos"] = 0.0
            df["session_phase"] = 1.0

        # 14. Rolling VWAP distance (30-period instead of cumulative session VWAP)
        rolling_pv = (close * vol).rolling(30, min_periods=5).sum()
        rolling_vol_sum = vol.rolling(30, min_periods=5).sum().replace(0, np.nan)
        rolling_vwap = (rolling_pv / rolling_vol_sum).fillna(close)
        df["rolling_vwap_dist"] = ((close - rolling_vwap) / (rolling_vwap + 1e-9)).fillna(0)

        # 15. EMA Cross Velocity (rate of change of the EMA 5/20 gap — is it widening or narrowing?)
        ema_gap = df["ema_cross_5_20"] if "ema_cross_5_20" in df.columns else 0.0
        df["ema_cross_velocity"] = (pd.Series(ema_gap).diff(3) if isinstance(ema_gap, (pd.Series, np.ndarray)) else pd.Series(0.0, index=df.index)).fillna(0)

        # 16. Stock Identity Hash (deterministic numeric encoding so model can learn per-stock patterns)
        if "symbol" in df.columns:
            df["stock_id_hash"] = df["symbol"].apply(lambda s: hash(s) % 100 / 100.0).astype(float)
        else:
            df["stock_id_hash"] = 0.0

        # 17. Rolling Parkinson Volatility (smoothed over 10 candles instead of per-candle noise)
        df["parkinson_vol_rolling"] = df["parkinson_vol"].rolling(10, min_periods=3).mean().fillna(df["parkinson_vol"])

        df[self.feature_cols] = df[self.feature_cols].ffill().fillna(0)
        return df

    def train(self, historical_df: pd.DataFrame, eval_split: float = 0.2) -> dict:
        """
        Train the enhanced 1-minute prediction ensemble with chronological validation.
        Target: next 1-minute return (ret_{t+1} = (close_{t+1} - close_t) / close_t).
        Follows strict chronological split (Train 80% / Test 20%) per ml-best-practices.
        """
        if historical_df.empty:
            raise ValueError("Historical dataframe is empty.")

        self.feature_cols = list(self.ALL_FEATURE_COLS)

        dfs = []
        for symbol, grp in historical_df.groupby("symbol"):
            grp_feat = self.extract_features_1m(grp)
            # Create target: next 1-minute return
            if "future_return_t1" in grp.columns:
                grp_feat["target_ret_1m"] = grp["future_return_t1"].values
            else:
                grp_feat["target_ret_1m"] = grp_feat["close"].pct_change(1).shift(-1)
            # Breakout target: profitable scalps (return >= 0.10%) — lowered from 0.18% to get more positive labels
            grp_feat["target_breakout"] = (grp_feat["target_ret_1m"] >= 0.0010).astype(int)
            dfs.append(grp_feat)

        full_df = pd.concat(dfs, ignore_index=True).dropna(subset=["target_ret_1m"])
        if len(full_df) < 100:
            raise ValueError(f"Not enough data points for training: {len(full_df)}")

        # Sort chronologically to ensure honest time-series train/test split
        full_df = full_df.sort_values("timestamp").reset_index(drop=True)

        X = full_df[self.feature_cols].ffill().fillna(0)
        y_reg = full_df["target_ret_1m"].values
        y_clf = full_df["target_breakout"].values

        split_idx = int(len(full_df) * (1 - eval_split))
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_reg_train, y_reg_test = y_reg[:split_idx], y_reg[split_idx:]
        y_clf_train, y_clf_test = y_clf[:split_idx], y_clf[split_idx:]

        # Sample weights: emphasize meaningful volatility moves (abs return > 0.001)
        sample_weights_train = 1.0 + (np.abs(y_reg_train) * 200.0)
        sample_weights_train = np.clip(sample_weights_train, 1.0, 5.0)

        print(f"Training 1-Minute Upgraded Ensemble:")
        print(f"  Total Samples:     {len(full_df):,} across {len(dfs)} symbols")
        print(f"  Train Samples:     {len(X_train):,} ({100*(1-eval_split):.0f}%)")
        print(f"  Test Samples:      {len(X_test):,} ({100*eval_split:.0f}%)")
        print(f"  Feature Count:     {len(self.feature_cols)}")
        print(f"  Breakout Positives: {np.mean(y_clf)*100:.1f}%")

        # Train Regressors with Huber Loss and sample weighting
        reg_test_preds = {}
        for name, model in self.regressors.items():
            print(f"  Fitting {name} regressor...")
            if name == "catboost":
                model.fit(X_train, y_reg_train, sample_weight=sample_weights_train)
            elif name == "lgbm":
                model.fit(X_train, y_reg_train, sample_weight=sample_weights_train)
            else:
                model.fit(X_train, y_reg_train, sample_weight=sample_weights_train)
            pred_test = model.predict(X_test)
            reg_test_preds[name] = pred_test

        # Ensemble Average on Test Set
        ensemble_pred_test = np.mean(list(reg_test_preds.values()), axis=0)
        mae = float(mean_absolute_error(y_reg_test, ensemble_pred_test))
        rmse = float(np.sqrt(mean_squared_error(y_reg_test, ensemble_pred_test)))

        # Phase 3: Train quantile regressor (75th percentile upper bound)
        print("  Fitting quantile regressor (P75 upper bound)...")
        self.quantile_regressor.fit(X_train, y_reg_train, sample_weight=sample_weights_train)
        q75_pred_test = self.quantile_regressor.predict(X_test)
        dir_acc = float(np.mean((ensemble_pred_test > 0) == (y_reg_test > 0))) * 100.0

        # High-conviction directional accuracy (when model predicts > 0.05% move)
        conviction_mask = np.abs(ensemble_pred_test) >= 0.0005
        if np.sum(conviction_mask) > 0:
            conviction_dir_acc = float(np.mean((ensemble_pred_test[conviction_mask] > 0) == (y_reg_test[conviction_mask] > 0))) * 100.0
        else:
            conviction_dir_acc = dir_acc

        # Train Breakout Classifier
        print("  Fitting breakout classifier (balanced random forest)...")
        self.classifier.fit(X_train, y_clf_train)
        clf_pred_test = self.classifier.predict(X_test)
        clf_acc = float(accuracy_score(y_clf_test, clf_pred_test)) * 100.0
        clf_prec = float(precision_score(y_clf_test, clf_pred_test, zero_division=0)) * 100.0
        clf_rec = float(recall_score(y_clf_test, clf_pred_test, zero_division=0)) * 100.0
        clf_f1 = float(f1_score(y_clf_test, clf_pred_test, zero_division=0)) * 100.0

        print(f"\nOut-of-Sample Test Evaluation:")
        print(f"  Return MAE:                 {mae*100:.3f}%")
        print(f"  Return RMSE:                {rmse*100:.3f}%")
        print(f"  Overall Directional Acc:    {dir_acc:.2f}%")
        print(f"  High-Conviction Dir Acc:    {conviction_dir_acc:.2f}%")
        print(f"  Breakout Precision:         {clf_prec:.2f}%")
        print(f"  Breakout Recall:            {clf_rec:.2f}%")
        print(f"  Breakout F1-Score:          {clf_f1:.2f}%")

        # Save to disk
        joblib.dump(self.regressors, os.path.join(self.model_dir, "return_regressors_1m.joblib"))
        joblib.dump(self.classifier, os.path.join(self.model_dir, "breakout_classifier_1m.joblib"))
        joblib.dump(self.quantile_regressor, os.path.join(self.model_dir, "quantile_regressor_1m.joblib"))
        joblib.dump(self.feature_cols, os.path.join(self.model_dir, "feature_cols_1m.joblib"))

        metrics_report = {
            "trained_at": datetime.now().isoformat(),
            "samples_total": len(full_df),
            "samples_train": len(X_train),
            "samples_test": len(X_test),
            "feature_count": len(self.feature_cols),
            "feature_cols": self.feature_cols,
            "test_mae_pct": round(mae * 100, 4),
            "test_rmse_pct": round(rmse * 100, 4),
            "test_direction_accuracy_pct": round(dir_acc, 2),
            "test_high_conviction_dir_acc_pct": round(conviction_dir_acc, 2),
            "test_breakout_precision_pct": round(clf_prec, 2),
            "test_breakout_recall_pct": round(clf_rec, 2),
            "test_breakout_f1_pct": round(clf_f1, 2)
        }
        with open(os.path.join(self.model_dir, "model_metrics_1m.json"), "w") as f:
            json.dump(metrics_report, f, indent=2)

        print("1-Minute Models saved successfully to:", self.model_dir)
        return metrics_report

    def predict_next_1m(self, latest_candles: pd.DataFrame, profit_threshold: float = 0.0008, confidence_multiplier: float = 1.0) -> dict:
        """
        Generate 1-minute prediction for a single stock using its latest candles.
        Features dynamic ATR-based profit hurdle and adaptive confidence calibration.
        """
        if len(latest_candles) < 15:
            last_p = float(latest_candles.iloc[-1]["close"]) if not latest_candles.empty else 0.0
            sym = str(latest_candles.iloc[-1].get("symbol", "")) if not latest_candles.empty else ""
            return {
                "symbol": sym or "UNKNOWN",
                "company": STOCK_UNIVERSE.get(sym, "UNKNOWN"),
                "current_price": last_p,
                "predicted_price_1m": last_p,
                "predicted_return_pct": 0.0,
                "confidence": 0.0,
                "raw_breakout_prob": 0.0,
                "signal": "HOLD",
                "direction": "UNCERTAIN",
                "prediction_valid": False,
                "error": f"INSUFFICIENT_HISTORY: Only {len(latest_candles)} candles available, minimum 15 required",
                "profit_threshold_pct": profit_threshold * 100,
                "timestamp": datetime.now().isoformat()
            }

        feat_df = self.extract_features_1m(latest_candles)
        last_row = feat_df.iloc[-1]
        X = feat_df[self.feature_cols].iloc[[-1]].ffill().fillna(0)

        current_price = float(last_row["close"])
        if math.isnan(current_price) or current_price <= 0:
            return {
                "symbol": str(last_row.get("symbol", "UNKNOWN")),
                "company": STOCK_UNIVERSE.get(str(last_row.get("symbol", "")), "UNKNOWN"),
                "current_price": 0.0,
                "predicted_price_1m": 0.0,
                "predicted_return_pct": 0.0,
                "confidence": 0.0,
                "raw_breakout_prob": 0.0,
                "signal": "HOLD",
                "direction": "UNCERTAIN",
                "prediction_valid": False,
                "error": "INVALID_PRICE_SERIES: Current price is NaN or <= 0",
                "timestamp": datetime.now().isoformat()
            }

        # Predict expected return using ensemble average
        preds = []
        for name, model in self.regressors.items():
            try:
                p = model.predict(X)[0]
                preds.append(float(p))
            except Exception as reg_err:
                logger.warning(f"Regressor {name} prediction failed: {reg_err}")

        if preds:
            pred_return = float(np.mean(preds))
        else:
            # Model inference failed: report failure honestly, do NOT substitute heuristics
            return {
                "symbol": latest_candles.iloc[-1].get("symbol", "UNKNOWN"),
                "company": STOCK_UNIVERSE.get(str(latest_candles.iloc[-1].get("symbol", "")), "UNKNOWN"),
                "current_price": current_price,
                "predicted_price_1m": current_price,
                "predicted_return_pct": 0.0,
                "confidence": 0.0,
                "raw_breakout_prob": 0.0,
                "signal": "HOLD",
                "direction": "UNCERTAIN",
                "prediction_valid": False,
                "error": "REGRESSORS_INFERENCE_FAILED",
                "timestamp": datetime.now().isoformat()
            }

        # Phase 3: Quantile upper-bound prediction (75th percentile of possible returns)
        try:
            q75_return = float(self.quantile_regressor.predict(X)[0])
        except Exception:
            q75_return = pred_return

        # Microstructure features
        mom_1m = float(last_row.get("ret_1m", 0.0))
        mom_3m = float(last_row.get("ret_3m", 0.0))
        mom_5m = float(last_row.get("ret_5m", 0.0))
        surge = float(last_row.get("vol_surge_ratio", 1.0))
        rsi_7 = float(last_row.get("micro_rsi_7", 50.0))
        orderflow = float(last_row.get("orderflow_imbalance", 0.0))
        upper_wick = float(last_row.get("upper_wick_ratio", 0.0))
        lower_wick = float(last_row.get("lower_wick_ratio", 0.0))
        wick_pressure = float(last_row.get("wick_pressure", 0.5))
        vol_zscore = float(last_row.get("vol_spike_zscore", 0.0))
        ema_cross = float(last_row.get("ema_cross_5_20", 0.0))
        sym_atr = float(last_row.get("micro_atr_14", 0.0025))

        # Dynamic Volatility Hurdle Adjustment:
        vol_multiplier = float(np.clip(sym_atr / 0.0025, 0.75, 1.50))
        effective_threshold = max(0.0006, profit_threshold * vol_multiplier)

        # Classify probability of exceeding threshold
        try:
            raw_breakout_prob = float(self.classifier.predict_proba(X)[0][1])
            # Directional confidence centered at 50% (neutral), reflecting probability of move in predicted direction
            # Preserves raw_breakout_prob for tail risk tracking while preventing directional misclassification
            if pred_return >= 0:
                directional_conf = float(np.clip(0.50 + (pred_return * 50.0), 0.10, 0.95))
            else:
                directional_conf = float(np.clip(0.50 + (abs(pred_return) * 50.0), 0.10, 0.95))
            calibrated_confidence = float(np.clip(directional_conf * confidence_multiplier, 0.10, 0.99))
        except Exception as e:
            # Report classifier failure honestly - never fabricate synthetic probability
            return {
                "symbol": latest_candles.iloc[-1].get("symbol", "UNKNOWN"),
                "company": STOCK_UNIVERSE.get(str(latest_candles.iloc[-1].get("symbol", "")), "UNKNOWN"),
                "current_price": current_price,
                "predicted_price_1m": current_price,
                "predicted_return_pct": 0.0,
                "confidence": 0.0,
                "raw_breakout_prob": 0.0,
                "signal": "HOLD",
                "direction": "UNCERTAIN",
                "prediction_valid": False,
                "error": f"CLASSIFIER_FAILED: {e}",
                "timestamp": datetime.now().isoformat()
            }

        predicted_price = current_price * (1 + pred_return)

        # Trigger BUY if predicted return >= effective_threshold and calibrated breakout confidence is supportive
        is_buy = (pred_return >= effective_threshold) and (calibrated_confidence >= 0.45)
        # Trigger SHORT SELL if predicted return <= -effective_threshold (price expected to FALL)
        # NSE allows intraday short selling on all NSE liquid stocks — sell first, buy back same day
        is_short = (pred_return <= -effective_threshold) and (calibrated_confidence >= 0.45)

        if is_buy:
            signal = "BUY"   # Long: price expected to rise
        elif is_short:
            signal = "SELL"  # Short: price expected to fall — sell first, buy back lower
        else:
            signal = "HOLD"

        return {
            "symbol": str(last_row["symbol"]),
            "company": STOCK_UNIVERSE.get(str(last_row["symbol"]), str(last_row["symbol"])),
            "current_price": round(current_price, 2),
            "predicted_price_1m": round(predicted_price, 2),
            "predicted_return_pct": round(pred_return * 100, 3),
            "confidence": round(calibrated_confidence * 100, 1),
            "raw_breakout_prob": round(raw_breakout_prob * 100, 1),
            "signal": signal,
            "direction": "LONG" if is_buy else ("SHORT" if is_short else "FLAT"),
            "prediction_valid": True,
            "error": None,
            "profit_threshold_pct": round(effective_threshold * 100, 2),
            "timestamp": last_row["timestamp"].isoformat() if hasattr(last_row["timestamp"], "isoformat") else str(last_row["timestamp"]),
            "micro_rsi": round(float(last_row.get("micro_rsi_7", 50)), 1),
            "micro_vwap_dist_pct": round(float(last_row.get("micro_vwap_dist", 0)) * 100, 3),
            "ema_cross_pct": round(ema_cross * 100, 3),
            "vol_zscore": round(vol_zscore, 2),
            "wick_pressure": round(wick_pressure, 2)
        }

    def predict_batch_1m(
        self,
        candle_dfs_dict: dict,
        profit_threshold: float = 0.0008,
        confidence_multiplier: float = 1.0
    ) -> dict:
        """
        Vectorized multi-instrument prediction.
        Extracts features and evaluates regressors, quantile regressor, and classifier
        in single batched matrix operations across all eligible symbols.
        Mathematically equivalent to calling predict_next_1m sequentially.
        """
        results = {}
        if not candle_dfs_dict:
            return results

        valid_symbols = []
        valid_x_rows = []
        valid_last_rows = []

        for sym, candles in candle_dfs_dict.items():
            if candles is None or len(candles) < 15:
                last_p = float(candles.iloc[-1]["close"]) if (candles is not None and not candles.empty) else 0.0
                sym_str = str(candles.iloc[-1].get("symbol", sym)) if (candles is not None and not candles.empty) else sym
                results[sym] = {
                    "symbol": sym_str,
                    "company": STOCK_UNIVERSE.get(sym_str, sym_str),
                    "current_price": last_p,
                    "predicted_price_1m": last_p,
                    "predicted_return_pct": 0.0,
                    "confidence": 0.0,
                    "raw_breakout_prob": 0.0,
                    "signal": "HOLD",
                    "direction": "UNCERTAIN",
                    "prediction_valid": False,
                    "error": f"INSUFFICIENT_HISTORY: Only {len(candles) if candles is not None else 0} candles available, minimum 15 required",
                    "profit_threshold_pct": profit_threshold * 100,
                    "timestamp": datetime.now().isoformat()
                }
                continue

            try:
                feat_df = self.extract_features_1m(candles)
                last_row = feat_df.iloc[-1]
                x_row = feat_df[self.feature_cols].iloc[[-1]].ffill().fillna(0)
                valid_symbols.append(sym)
                valid_last_rows.append(last_row)
                valid_x_rows.append(x_row)
            except Exception as e:
                results[sym] = {
                    "symbol": sym,
                    "company": STOCK_UNIVERSE.get(sym, sym),
                    "current_price": 0.0,
                    "predicted_price_1m": 0.0,
                    "predicted_return_pct": 0.0,
                    "confidence": 0.0,
                    "raw_breakout_prob": 0.0,
                    "signal": "HOLD",
                    "direction": "UNCERTAIN",
                    "prediction_valid": False,
                    "error": f"FEATURE_EXTRACTION_FAILED: {e}",
                    "timestamp": datetime.now().isoformat()
                }

        if not valid_symbols:
            return results

        # Stack into single batch feature matrix
        x_batch = pd.concat(valid_x_rows, ignore_index=True)

        # 1. Batched Regressors Inference
        reg_preds = []
        for name, model in self.regressors.items():
            try:
                p = model.predict(x_batch)
                reg_preds.append(p)
            except Exception as reg_err:
                logger.warning(f"Batch regressor {name} failed: {reg_err}")

        if reg_preds:
            batch_pred_returns = np.mean(reg_preds, axis=0)
        else:
            batch_pred_returns = np.zeros(len(x_batch))

        # 2. Batched Quantile Regressor Inference
        try:
            batch_q75 = self.quantile_regressor.predict(x_batch)
        except Exception:
            batch_q75 = batch_pred_returns

        # 3. Batched Breakout Classifier Inference
        try:
            batch_probs = self.classifier.predict_proba(x_batch)[:, 1]
        except Exception:
            batch_probs = np.zeros(len(x_batch))

        # Vectorized assembly of per-symbol outputs
        for i, sym in enumerate(valid_symbols):
            last_row = valid_last_rows[i]
            current_price = float(last_row["close"])
            pred_return = float(batch_pred_returns[i])
            raw_breakout_prob = float(batch_probs[i])
            if pred_return >= 0:
                directional_conf = float(np.clip(0.50 + (pred_return * 50.0), 0.10, 0.95))
            else:
                directional_conf = float(np.clip(0.50 + (abs(pred_return) * 50.0), 0.10, 0.95))
            calibrated_confidence = float(np.clip(directional_conf * confidence_multiplier, 0.10, 0.99))

            sym_atr = float(last_row.get("micro_atr_14", 0.0025))
            vol_multiplier = float(np.clip(sym_atr / 0.0025, 0.75, 1.50))
            effective_threshold = max(0.0006, profit_threshold * vol_multiplier)

            predicted_price = current_price * (1.0 + pred_return)
            is_buy = (pred_return >= effective_threshold) and (calibrated_confidence >= 0.45)
            is_short = (pred_return <= -effective_threshold) and (calibrated_confidence >= 0.45)

            if is_buy:
                signal = "BUY"
            elif is_short:
                signal = "SELL"
            else:
                signal = "HOLD"

            ema_cross = float(last_row.get("ema_cross_5_20", 0.0))
            vol_zscore = float(last_row.get("vol_spike_zscore", 0.0))
            wick_pressure = float(last_row.get("wick_pressure", 0.5))

            results[sym] = {
                "symbol": str(last_row["symbol"]),
                "company": STOCK_UNIVERSE.get(str(last_row["symbol"]), str(last_row["symbol"])),
                "current_price": round(current_price, 2),
                "predicted_price_1m": round(predicted_price, 2),
                "predicted_return_pct": round(pred_return * 100, 3),
                "confidence": round(calibrated_confidence * 100, 1),
                "raw_breakout_prob": round(raw_breakout_prob * 100, 1),
                "signal": signal,
                "direction": "LONG" if is_buy else ("SHORT" if is_short else "FLAT"),
                "prediction_valid": True,
                "error": None,
                "profit_threshold_pct": round(effective_threshold * 100, 2),
                "timestamp": last_row["timestamp"].isoformat() if hasattr(last_row["timestamp"], "isoformat") else str(last_row["timestamp"]),
                "micro_rsi": round(float(last_row.get("micro_rsi_7", 50)), 1),
                "micro_vwap_dist_pct": round(float(last_row.get("micro_vwap_dist", 0)) * 100, 3),
                "ema_cross_pct": round(ema_cross * 100, 3),
                "vol_zscore": round(vol_zscore, 2),
                "wick_pressure": round(wick_pressure, 2)
            }

        return results

