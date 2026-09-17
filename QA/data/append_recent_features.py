import pandas as pd
import os
import sys

# Add QA/features to path
sys.path.append('QA/features')
from technical import calculate_rsi, calculate_vwap, calculate_atr

def append_recent_to_features():
    features_path = 'QA/data/processed/features_latest.parquet'
    recent_path = 'QA/data/raw/klines/recent_institutional_1.parquet'
    
    if not os.path.exists(features_path):
        print("features_latest.parquet not found.")
        return
    
    if not os.path.exists(recent_path):
        print("recent_institutional_1.parquet not found.")
        return
        
    old_df = pd.read_parquet(features_path)
    new_klines = pd.read_parquet(recent_path)
    
    # Process new klines to match features_latest schema
    dfs = []
    for symbol, group in new_klines.groupby('symbol'):
        group = group.copy().sort_values('timestamp')
        group['rsi_14'] = calculate_rsi(group, period=14, price_col='close')
        group['vwap'] = calculate_vwap(group, volume_col='volume', price_col='close')
        group['vwap_dist'] = (group['close'] - group['vwap']) / group['vwap']
        group['atr_14'] = calculate_atr(group, period=14)
        
        # Placeholders for microstructure
        group['imbalance'] = 0.5
        group['spread'] = 0.0
        group['vpin'] = 0.0
        group['volume_delta'] = 0.0
        group['trade_intensity'] = 0.0
        group['type'] = 'klines'
        
        dfs.append(group)
    
    new_df = pd.concat(dfs, ignore_index=True)
    
    # Combine
    combined = pd.concat([old_df, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=['symbol', 'timestamp'], keep='last')
    combined = combined.sort_values(['symbol', 'timestamp'])
    
    combined.to_parquet(features_path, engine='pyarrow')
    print(f"Updated {features_path} with recent data. Total rows: {len(combined)}")

if __name__ == "__main__":
    append_recent_to_features()
