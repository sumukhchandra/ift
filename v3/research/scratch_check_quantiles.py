import sys
sys.path.insert(0, ".")
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.linear_model import Ridge
from v3.research.phase2_cost_aware_research import resample_discrete_bars, extract_multi_bar_features

raw1 = pd.read_csv('QA/data/combined_weekend_1m.csv')
raw2 = pd.read_csv('QA/data/genuine_forward_oos_oct13_oct14.csv')
df_raw = pd.concat([raw1, raw2], ignore_index=True)
df_raw["timestamp"] = df_raw["timestamp"].astype(str).str.replace("+05:30", "")

train_dates = ["2026-09-18", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-29", "2026-09-30"]
val_dates = ["2026-10-01", "2026-10-05"]
test_dates = ["2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-13", "2026-10-14"]
feature_cols = ["ret_1_bps", "ret_2_bps", "ret_3_bps", "accel_bps", "atr_bps", "pvol_bps", "bb_pct", "bb_bw", "wick_press", "ofi", "v_surge"]

for h in [5, 10, 15]:
    bars_df = resample_discrete_bars(df_raw, freq_min=h)
    feat_df = extract_multi_bar_features(bars_df)
    train_h = feat_df[feat_df["date"].isin(train_dates)].reset_index(drop=True)
    val_h = feat_df[feat_df["date"].isin(val_dates)].reset_index(drop=True)
    test_h = feat_df[feat_df["date"].isin(test_dates)].reset_index(drop=True)
    
    lgb = LGBMRegressor(n_estimators=80, learning_rate=0.03, max_depth=3, num_leaves=7, objective="huber", reg_lambda=20.0, random_state=42, verbose=-1)
    lgb.fit(train_h[feature_cols].values, train_h["target_ret_bps"].values)
    val_preds = lgb.predict(val_h[feature_cols].values)
    test_preds = lgb.predict(test_h[feature_cols].values)
    
    val_h["pred"] = val_preds
    test_h["pred"] = test_preds
    
    # Check top quintile or decile of predictions on validation data
    q90_val = np.percentile(val_preds, 90)
    top_val = val_h[val_h["pred"] >= q90_val]
    mean_val_move = top_val["target_ret_bps"].mean()
    
    # Check what happens if we apply that exact threshold to test data
    top_test = test_h[test_h["pred"] >= q90_val]
    mean_test_move = top_test["target_ret_bps"].mean()
    
    print(f"Horizon {h}m:")
    print(f"  Val Q90 threshold: {q90_val:.3f} bps")
    print(f"  Val Top Decile: N={len(top_val)}, Realized Mean Gross Move = {mean_val_move:.2f} bps")
    print(f"  Test with Val Q90: N={len(top_test)}, Realized Mean Gross Move = {mean_test_move:.2f} bps")
    print(f"  Friction realistic = 8.54 bps -> Net move = {mean_test_move - 8.54:.2f} bps")
