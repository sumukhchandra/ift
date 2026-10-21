import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.linear_model import Ridge
import os

raw1 = pd.read_csv('QA/data/combined_weekend_1m.csv')
raw2 = pd.read_csv('QA/data/genuine_forward_oos_oct13_oct14.csv')
df_raw = pd.concat([raw1, raw2], ignore_index=True)
df_raw["timestamp"] = df_raw["timestamp"].astype(str).str.replace("+05:30", "")

import sys
sys.path.insert(0, ".")
from v3.research.phase2_cost_aware_research import resample_discrete_bars, extract_multi_bar_features

train_dates = ["2026-09-18", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-29", "2026-09-30"]
val_dates = ["2026-10-01", "2026-10-05"]
test_dates = ["2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-13", "2026-10-14"]
feature_cols = ["ret_1_bps", "ret_2_bps", "ret_3_bps", "accel_bps", "atr_bps", "pvol_bps", "bb_pct", "bb_bw", "wick_press", "ofi", "v_surge"]

for h in [5, 10, 15]:
    bars_df = resample_discrete_bars(df_raw, freq_min=h)
    feat_df = extract_multi_bar_features(bars_df)
    train_h = feat_df[feat_df["date"].isin(train_dates)].reset_index(drop=True)
    test_h = feat_df[feat_df["date"].isin(test_dates)].reset_index(drop=True)
    
    lgb = LGBMRegressor(n_estimators=80, learning_rate=0.03, max_depth=3, num_leaves=7, objective="huber", reg_lambda=20.0, random_state=42, verbose=-1)
    lgb.fit(train_h[feature_cols].values, train_h["target_ret_bps"].values)
    preds = lgb.predict(test_h[feature_cols].values)
    
    ridge = Ridge(alpha=200.0, fit_intercept=True)
    ridge.fit(train_h[feature_cols].values, train_h["target_ret_bps"].values)
    r_preds = ridge.predict(test_h[feature_cols].values)
    
    print(f"Horizon {h}m Test Predictions Distribution:")
    print(f"  LGB: min={preds.min():.2f}, p50={np.median(preds):.2f}, p90={np.percentile(preds, 90):.2f}, p99={np.percentile(preds, 99):.2f}, max={preds.max():.2f}")
    print(f"  Ridge: min={r_preds.min():.2f}, p50={np.median(r_preds):.2f}, p90={np.percentile(r_preds, 90):.2f}, p99={np.percentile(r_preds, 99):.2f}, max={r_preds.max():.2f}")
    print(f"  Actual target_ret_bps: min={test_h['target_ret_bps'].min():.2f}, p90={np.percentile(np.abs(test_h['target_ret_bps']), 90):.2f}, max={test_h['target_ret_bps'].max():.2f}")
