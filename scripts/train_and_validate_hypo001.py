#!/usr/bin/env python3
"""
scripts/train_and_validate_hypo001.py
Reproducible training, out-of-sample chronological validation,
and weights export for HYPO001 specialist Ridge model on TATASTEEL.NS.
"""

import os
import sys
import math
import json
import pickle
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(WORKSPACE_ROOT, "QA", "data", "TATASTEEL_1m_weekend.csv")
WEIGHTS_PATH = os.path.join(WORKSPACE_ROOT, "v3", "models", "multimodel", "active_model_weights.json")
SAVED_MODELS_DIR = os.path.join(WORKSPACE_ROOT, "v3", "models", "saved_models")
LOG_PATH = os.path.join(WORKSPACE_ROOT, "reports", "HYPO001_TATASTEEL_VALIDATION.log")

os.makedirs(SAVED_MODELS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

def compute_exact_19_features(df: pd.DataFrame):
    """Computes the authoritative 19-feature vector for every 1m bar."""
    c = df["close"].values
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    v = df["volume"].values
    n = len(df)

    rows = []
    targets = []
    timestamps = []

    # Requires at least 25 bars for indicator warm-up
    for i in range(25, n - 1):
        c0, o0, h0, l0, v0 = c[i], o[i], h[i], l[i], v[i]
        if c0 <= 0 or l0 <= 0 or o0 <= 0 or h0 <= 0:
            continue

        # 1. Returns & Momentum
        r1 = (c0 - c[i - 1]) / c[i - 1]
        r3 = (c0 - c[i - 3]) / c[i - 3]
        r5 = (c0 - c[i - 5]) / c[i - 5]
        r10 = (c0 - c[i - 10]) / c[i - 10]
        accel1 = r1 - ((c[i - 1] - c[i - 2]) / c[i - 2])

        # 2. RSI 7 & 14
        diffs14 = [c[k] - c[k - 1] for k in range(i - 13, i + 1)]
        gains14 = [max(0.0, d) for d in diffs14]
        losses14 = [abs(min(0.0, d)) for d in diffs14]
        avg_g14 = sum(gains14) / 14.0
        avg_l14 = (sum(losses14) / 14.0) or 1e-9
        rs14 = avg_g14 / avg_l14
        rsi14 = 100.0 - (100.0 / (1.0 + rs14))

        diffs7 = diffs14[-7:]
        gains7 = [max(0.0, d) for d in diffs7]
        losses7 = [abs(min(0.0, d)) for d in diffs7]
        avg_g7 = sum(gains7) / 7.0
        avg_l7 = (sum(losses7) / 7.0) or 1e-9
        rs7 = avg_g7 / avg_l7
        rsi7 = 100.0 - (100.0 / (1.0 + rs7))

        # 3. Micro-VWAP (20 bars)
        cum_vol = sum(v[k] for k in range(max(0, i - 20), i + 1))
        cum_vp = sum(c[k] * v[k] for k in range(max(0, i - 20), i + 1))
        vwap = (cum_vp / cum_vol) if cum_vol > 0 else c0
        vwap_dist = (c0 - vwap) / vwap

        # 4. Bollinger Bands 20
        window_c = [c[k] for k in range(max(0, i - 19), i + 1)]
        sma20 = sum(window_c) / len(window_c)
        var20 = sum((x - sma20) ** 2 for x in window_c) / len(window_c)
        std20 = math.sqrt(var20) or 1e-6
        bb_bandwidth = (4.0 * std20) / sma20
        bb_pct_b = (c0 - (sma20 - 2.0 * std20)) / (4.0 * std20)

        # 5. ATR 14 & Parkinson Volatility
        trs = [max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(max(1, i - 13), i + 1)]
        atr14 = sum(trs) / len(trs)
        micro_atr14 = atr14 / c0

        ln_hl = [math.log(h[k] / (l[k] or 1e-6)) for k in range(max(0, i - 9), i + 1)]
        parkinson_vol = math.sqrt(sum(x ** 2 for x in ln_hl) / (4.0 * math.log(2.0) * len(ln_hl)))

        # 6. Wick Pressures
        total_range = max(1e-6, h0 - l0)
        upper_wick = (h0 - max(o0, c0)) / total_range
        lower_wick = (min(o0, c0) - l0) / total_range
        wick_pressure = lower_wick - upper_wick

        # 7. Volume surge ratio
        past_vol = [v[k] for k in range(max(0, i - 9), i)]
        avg_vol_10 = (sum(past_vol) / len(past_vol)) if past_vol else 1.0
        vol_surge = v0 / (avg_vol_10 or 1.0)

        feats = [
            r1, r3, r5, r10, accel1,
            rsi7 / 100.0, rsi14 / 100.0,
            vwap_dist, bb_pct_b, bb_bandwidth,
            micro_atr14, parkinson_vol,
            wick_pressure, upper_wick, lower_wick,
            vol_surge,
            r1 * vol_surge,
            vwap_dist * rsi14 / 100.0,
            accel1 * bb_bandwidth
        ]

        target_return = math.log(c[i + 1] / c0)
        rows.append(feats)
        targets.append(target_return)
        timestamps.append(df.iloc[i].get("timestamp", i))

    return np.array(rows), np.array(targets), timestamps

def main():
    print(f"Loading data from {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH)
    print(f"Loaded {len(df)} total bars.")

    X, y, timestamps = compute_exact_19_features(df)
    n_samples = len(X)
    print(f"Extracted {n_samples} valid feature rows with 19 quantitative features.")

    # Chronological 80/20 train/test split (strict no look-ahead)
    split_idx = int(0.80 * n_samples)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    print(f"Chronological Train samples: {len(X_train)} (80%)")
    print(f"Chronological Test samples:  {len(X_test)} (20% Out-of-Sample)")

    # Standardize features (fitted strictly on training set)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train Ridge model with L2 regularization
    alpha = 100.0
    model = Ridge(alpha=alpha)
    model.fit(X_train_scaled, y_train)

    # Evaluate on Train Set
    y_train_pred = model.predict(X_train_scaled)
    train_mae_bps = mean_absolute_error(y_train, y_train_pred) * 10000
    train_rmse_bps = math.sqrt(mean_squared_error(y_train, y_train_pred)) * 10000
    train_dir_acc = np.mean(np.sign(y_train_pred) == np.sign(y_train)) * 100
    train_r2 = r2_score(y_train, y_train_pred)

    # Evaluate on Out-of-Sample Test Set
    y_test_pred = model.predict(X_test_scaled)
    test_mae_bps = mean_absolute_error(y_test, y_test_pred) * 10000
    test_rmse_bps = math.sqrt(mean_squared_error(y_test, y_test_pred)) * 10000
    test_dir_acc = np.mean(np.sign(y_test_pred) == np.sign(y_test)) * 100
    test_r2 = r2_score(y_test, y_test_pred)

    # Baselines
    zero_mae_bps = mean_absolute_error(y_test, np.zeros_like(y_test)) * 10000

    report = f"""================================================================================
  HYPO001 (TATASTEEL.NS) SPECIALIST RIDGE MODEL VALIDATION REPORT
================================================================================
  Target Instrument:        TATASTEEL.NS (Tata Steel Ltd. - NIFTY 50 Constituent)
  Feature Schema:           Exact 19 Quantitative Microstructure & Momentum Features
  Training Dataset:         {DATA_PATH}
  Total Samples:            {n_samples} 1-minute bars
  Chronological Split:      80% Train ({len(X_train)} bars) / 20% Test ({len(X_test)} bars)
  Regularization (L2 alpha): {alpha}
--------------------------------------------------------------------------------
  IN-SAMPLE TRAINING METRICS (80%):
    • MAE:                  {train_mae_bps:.2f} bps
    • RMSE:                 {train_rmse_bps:.2f} bps
    • Directional Accuracy: {train_dir_acc:.2f}%
    • R^2 Score:            {train_r2:.6f}
--------------------------------------------------------------------------------
  OUT-OF-SAMPLE TEST METRICS (20% Untouched):
    • Out-of-Sample MAE:    {test_mae_bps:.2f} bps  (vs Zero Baseline: {zero_mae_bps:.2f} bps)
    • Out-of-Sample RMSE:   {test_rmse_bps:.2f} bps
    • Directional Accuracy: {test_dir_acc:.2f}%
    • R^2 Score:            {test_r2:.6f}
================================================================================
"""
    print(report)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(report)

    # Save pickle artifact
    pkl_path = os.path.join(SAVED_MODELS_DIR, "HYPO001_TATASTEEL.pkl")
    with open(pkl_path, "wb") as f:
        pickle.dump({"model": model, "scaler": scaler, "alpha": alpha}, f)
    print(f"Saved model artifact to {pkl_path}")

    # Export weights to active_model_weights.json
    weights_entry = {
        "weights": [float(w) for w in model.coef_],
        "bias": float(model.intercept_),
        "means": [float(m) for m in scaler.mean_],
        "stds": [float(s) for s in scaler.scale_]
    }

    if os.path.exists(WEIGHTS_PATH):
        with open(WEIGHTS_PATH, "r", encoding="utf-8") as f:
            all_weights = json.load(f)
    else:
        all_weights = {}

    all_weights["HYPO001"] = weights_entry
    with open(WEIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_weights, f, indent=2)
    print(f"Exported verified HYPO001 weights to {WEIGHTS_PATH}")

if __name__ == "__main__":
    main()
