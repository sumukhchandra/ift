#!/usr/bin/env python3
"""
scripts/train_30m_forward_models.py
Trains 30-Minute Forward Price Prediction Models for all 6 AlphaNSE instruments.

Target:
  target_30m = (P_{t + 30} - P_t) / P_t
  Predicts the exact 30-minute forward fractional return.
  At any minute T (e.g. 10:50, 11:00, 11:01...), forecast price at T + 30m:
    P_{t + 30}^{pred} = P_t * (1 + pred_ret_30m)
"""

import os
import sys
import math
import csv
import json
from datetime import datetime
from typing import Dict, Any, List

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from scripts.benchmark_model_prediction_accuracy import compute_features

QA_DATA_DIR = os.path.join(WORKSPACE_ROOT, "QA", "data")
OUTPUT_WEIGHTS_PATH = os.path.join(WORKSPACE_ROOT, "v3", "models", "multimodel", "session12_30m_forward_weights.json")

SYMBOLS_MAP = {
    "^NSEI": "NSEI",
    "INFY.NS": "INFY",
    "TATACAP.NS": "TATACAP",
    "BAJFINANCE.NS": "BAJFINANCE",
    "AXISBANK.NS": "AXISBANK",
    "RELIANCE.NS": "RELIANCE"
}


def train_ridge(X: List[List[float]], y: List[float], alpha: float = 15.0, epochs: int = 30, lr: float = 0.003):
    num_samples = len(X)
    num_features = len(X[0])
    weights = [0.0] * num_features
    bias = 0.0

    for epoch in range(epochs):
        grad_w = [0.0] * num_features
        grad_b = 0.0

        for xi, yi in zip(X, y):
            pred = sum(w * x for w, x in zip(weights, xi)) + bias
            err = pred - yi
            for j in range(num_features):
                grad_w[j] += err * xi[j]
            grad_b += err

        for j in range(num_features):
            weights[j] -= lr * ((grad_w[j] / num_samples) + (alpha * weights[j] / num_samples))
        bias -= lr * (grad_b / num_samples)

    return weights, bias


def main():
    print("=" * 88)
    print("  🚀 TRAINING DEDICATED 30-MINUTE FORWARD PRICE PREDICTION MODELS")
    print("  HORIZON: Exactly 30 Minutes Forward (T ➔ T + 30m)")
    print("=" * 88)

    models_30m = {}

    for sym, file_key in SYMBOLS_MAP.items():
        fname = f"{file_key}_1m_weekend.csv"
        fpath = os.path.join(QA_DATA_DIR, fname)
        if not os.path.exists(fpath):
            print(f"[WARN] File not found: {fpath}")
            continue

        candles = []
        with open(fpath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                try:
                    o = float(r["open"])
                    h = float(r["high"])
                    l = float(r["low"])
                    c = float(r["close"])
                    v = float(r["volume"])
                    ts = r.get("timestamp", "")
                    if o > 0 and h > 0 and l > 0 and c > 0:
                        candles.append({"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v})
                except Exception:
                    pass

        candles.sort(key=lambda x: x["timestamp"])
        n = len(candles)
        print(f"\nProcessing {sym} ({len(candles):,} candles)...")

        dataset_X = []
        dataset_y = []

        # Target is 30 bars forward (i + 30)
        for i in range(25, n - 30):
            feats = compute_features(candles, i)
            if not feats:
                continue

            c_now = candles[i]["close"]
            c_30m = candles[i + 30]["close"]
            target_30m = (c_30m - c_now) / (c_now or 1e-6)

            dataset_X.append(feats)
            dataset_y.append(target_30m)

        if not dataset_X:
            continue

        # Split 80/20 train/test
        split_idx = int(len(dataset_X) * 0.80)
        X_train_raw = dataset_X[:split_idx]
        y_train = dataset_y[:split_idx]
        X_test_raw = dataset_X[split_idx:]
        y_test = dataset_y[split_idx:]

        # Normalization
        num_feats = len(dataset_X[0])
        means = [sum(row[j] for row in X_train_raw) / len(X_train_raw) for j in range(num_feats)]
        stds = [math.sqrt(sum((row[j] - means[j]) ** 2 for row in X_train_raw) / len(X_train_raw)) or 1.0 for j in range(num_feats)]

        X_train = [[(r[j] - means[j]) / stds[j] for j in range(num_feats)] for r in X_train_raw]
        X_test = [[(r[j] - means[j]) / stds[j] for j in range(num_feats)] for r in X_test_raw]

        weights, bias = train_ridge(X_train, y_train, alpha=15.0, epochs=30, lr=0.003)

        # Evaluation on test set
        preds = [sum(w * x for w, x in zip(weights, xi)) + bias for xi in X_test]
        hits = sum(1 for p, a in zip(preds, y_test) if (p > 0 and a > 0) or (p < 0 and a < 0))
        acc = (hits / len(preds) * 100.0) if preds else 0.0
        mae_bps = sum(abs(p - a) for p, a in zip(preds, y_test)) / len(preds) * 10000

        print(f"  • {sym:<14}: Train={len(X_train):,} | Test={len(X_test):,} | 30m Dir Acc={acc:.1f}% | MAE={mae_bps:.1f} bps")

        models_30m[sym] = {
            "weights": weights,
            "bias": bias,
            "means": means,
            "stds": stds,
            "test_accuracy_pct": round(acc, 2),
            "test_mae_bps": round(mae_bps, 2)
        }

    os.makedirs(os.path.dirname(OUTPUT_WEIGHTS_PATH), exist_ok=True)
    with open(OUTPUT_WEIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(models_30m, f, indent=2)

    print(f"\n[DONE] Saved 30-minute forward weights to: {OUTPUT_WEIGHTS_PATH}")


if __name__ == "__main__":
    main()
