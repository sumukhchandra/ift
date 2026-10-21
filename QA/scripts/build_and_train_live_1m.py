"""
Phase 3: Comprehensive 1-Minute Retraining Engine.
Uses OneMinPredictor.train() so all model architecture changes (MAE loss, quantile
regressor, Platt-calibrated classifier, 30 features) are automatically picked up.
"""

import os
import sys
import time
import json
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from stocks_config import STOCK_SYMBOLS, STOCK_UNIVERSE
from models.one_min_predictor import OneMinPredictor

MODEL_DIR = os.path.join(PROJECT_ROOT, "models", "saved_models_1m")
os.makedirs(MODEL_DIR, exist_ok=True)

def build_and_retrain():
    print("=" * 80)
    print("PHASE 3: ADVANCED 1-MINUTE ENSEMBLE RETRAINING")
    print("  - MAE/SquaredError loss (no more Huber compression)")
    print("  - 30 features (7 new: time, session, rolling VWAP, EMA velocity, stock ID)")
    print("  - Platt-calibrated GBM classifier (replaces RandomForest)")
    print("  - Quantile regressor (P75 upper bound)")
    print("  - Breakout target lowered to 0.10%")
    print("=" * 80)
    start_time = time.time()

    # Force fresh model initialization (ignore old saved models with wrong architecture)
    predictor = OneMinPredictor()
    # Force re-initialization of fresh Phase 3 models
    predictor._load_or_init_models()
    # Ensure we use the full 30-feature set
    predictor.feature_cols = list(predictor.ALL_FEATURE_COLS)
    
    print(f"\nTarget Feature Set ({len(predictor.feature_cols)} features):")
    for i, col in enumerate(predictor.feature_cols, 1):
        print(f"  {i:02d}. {col}")

    # 1. Download 5 days of real 1m candles from NSE
    print("\n1. Downloading real 1-minute NSE candles (5-day window)...")
    raw_df = yf.download(STOCK_SYMBOLS, period="5d", interval="1m", progress=False, threads=True)
    
    real_dfs = []
    if raw_df is not None and not raw_df.empty:
        for symbol in STOCK_SYMBOLS:
            try:
                if isinstance(raw_df.columns, pd.MultiIndex):
                    if symbol in raw_df.columns.get_level_values(1):
                        sym_df = raw_df.xs(symbol, axis=1, level=1).copy()
                    elif symbol in raw_df.columns.get_level_values(0):
                        sym_df = raw_df.xs(symbol, axis=1, level=0).copy()
                    else:
                        continue
                else:
                    continue

                sym_df = sym_df.reset_index()
                sym_df.columns = [str(c).lower() for c in sym_df.columns]
                time_col = "datetime" if "datetime" in sym_df.columns else "date" if "date" in sym_df.columns else "index"
                if time_col not in sym_df.columns and "timestamp" not in sym_df.columns:
                    time_col = sym_df.columns[0]
                sym_df = sym_df.rename(columns={time_col: "timestamp"})
                sym_df["symbol"] = symbol
                sym_df = sym_df.dropna(subset=["open", "high", "low", "close"])
                if len(sym_df) >= 20:
                    real_dfs.append(sym_df)
                    print(f"  - {symbol}: {len(sym_df)} 1m candles")
            except Exception as e:
                print(f"  - Error processing {symbol}: {e}")

    # 2. Load historical master dataset
    master_path = os.path.join(PROJECT_ROOT, "data", "processed", "master_labeled_dataset.parquet")
    hist_dfs = []
    if os.path.exists(master_path):
        print("\n2. Loading historical master dataset...")
        m_df = pd.read_parquet(master_path)
        print(f"  Master dataset: {len(m_df):,} candles")
        for sym, grp in m_df.groupby("symbol"):
            hist_dfs.append(grp.copy())

    # 3. Normalize timestamps to canonical Asia/Kolkata (Indian Standard Time) convention
    def normalize_tz(df):
        if "timestamp" in df.columns:
            ts = pd.to_datetime(df["timestamp"])
            if hasattr(ts.dt, "tz"):
                if ts.dt.tz is None:
                    # Naive timestamps represent Indian market hours (09:15-15:30 IST)
                    df["timestamp"] = ts.dt.tz_localize("Asia/Kolkata")
                else:
                    df["timestamp"] = ts.dt.tz_convert("Asia/Kolkata")
        return df

    for d in real_dfs:
        normalize_tz(d)
    for d in hist_dfs:
        normalize_tz(d)

    # 4. Combine all raw data (features will be extracted by predictor.train())
    all_dfs = hist_dfs + real_dfs
    if not all_dfs:
        print("ERROR: No training data available!")
        return {"status": "error", "reason": "no_data"}

    full_df = pd.concat(all_dfs, ignore_index=True)
    full_df = full_df.dropna(subset=["open", "high", "low", "close"])
    full_df = full_df.sort_values("timestamp").reset_index(drop=True)

    print(f"\n3. Combined Dataset: {len(full_df):,} candles across {full_df['symbol'].nunique()} symbols")

    # 5. Train using the OneMinPredictor's train() method
    # This automatically uses Phase 3 architecture: MAE loss, quantile regressor,
    # Platt-calibrated classifier, all 30 features
    print("\n4. Training Phase 3 model ensemble...")
    metrics = predictor.train(full_df, eval_split=0.20)

    # 6. Save final metrics with timing
    elapsed = round(time.time() - start_time, 1)
    metrics["training_time_sec"] = elapsed
    metrics["dataset_summary"] = {
        "total_samples": len(full_df),
        "live_1m_candles": sum(len(d) for d in real_dfs),
        "historical_master_candles": sum(len(d) for d in hist_dfs),
        "symbols_count": full_df["symbol"].nunique()
    }
    metrics["retrained_at"] = datetime.now().isoformat()

    with open(os.path.join(MODEL_DIR, "model_metrics_1m.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"\n{'=' * 50}")
    print(f"PHASE 3 RETRAINING COMPLETE")
    print(f"  Features: {metrics.get('feature_count', '?')}")
    print(f"  Direction Accuracy: {metrics.get('test_direction_accuracy_pct', '?')}%")
    print(f"  MAE: {metrics.get('test_mae_pct', '?')}%")
    print(f"  Breakout F1: {metrics.get('test_breakout_f1_pct', '?')}%")
    print(f"  Time: {elapsed}s")
    print(f"{'=' * 50}")

    return metrics

if __name__ == "__main__":
    build_and_retrain()
