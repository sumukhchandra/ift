"""
Script to retrain the enhanced 1-minute ML ensemble on master_labeled_dataset.parquet.
Evaluates out-of-sample performance and saves upgraded artifacts to QA/models/saved_models_1m.
"""

import os
import sys
import time
import json
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from models.one_min_predictor import OneMinPredictor

def main():
    print("=" * 80)
    print("STARTING 1-MINUTE ML ENSEMBLE RETRAINING & CALIBRATION")
    print("=" * 80)
    start_time = time.time()

    data_path = os.path.join(PROJECT_ROOT, "data", "processed", "master_labeled_dataset.parquet")
    if not os.path.exists(data_path):
        print(f"Error: Dataset not found at {data_path}")
        return

    print(f"Loading master dataset from: {data_path}")
    df = pd.read_parquet(data_path)
    print(f"Loaded {len(df):,} candles across symbols: {df['symbol'].unique().tolist()}")

    # Initialize predictor
    predictor = OneMinPredictor()
    print(f"Feature set ({len(predictor.feature_cols)} features):")
    for i, f in enumerate(predictor.feature_cols, 1):
        print(f"  {i:02d}. {f}")

    print("\nExecuting chronological 80/20 train/validation and fitting ensemble...")
    metrics = predictor.train(df, eval_split=0.20)

    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"RETRAINING COMPLETE IN {elapsed:.1f} SECONDS")
    print("=" * 80)
    print(json.dumps(metrics, indent=2))

if __name__ == "__main__":
    main()
