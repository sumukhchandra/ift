import pandas as pd
import numpy as np

def get_cusum_events(close, threshold):
    """
    Symmetric CUSUM Filter.
    Returns timestamps where the cumulative sum of absolute returns exceeds threshold.
    """
    t_events = []
    s_pos, s_neg = 0, 0
    diff = close.diff()
    
    for i in range(1, len(diff)):
        s_pos = max(0, s_pos + diff.iloc[i])
        s_neg = min(0, s_neg + diff.iloc[i])
        
        if s_pos > threshold:
            s_pos = 0
            t_events.append(diff.index[i])
        elif s_neg < -threshold:
            s_neg = 0
            t_events.append(diff.index[i])
            
    return pd.DatetimeIndex(t_events)

def apply_event_sampling(df, threshold_mult=0.5):
    """
    Applies CUSUM sampling to the dataframe.
    threshold is set as a multiplier of the average daily volatility (if available) 
    or a fraction of average price.
    """
    if df.empty:
        return df
        
    df = df.copy()
    if 'timestamp' in df.columns:
        df = df.set_index('timestamp')
        
    # Set threshold based on recent volatility or fixed pct of price
    # Example: 0.1% of current price
    avg_price = df['close'].mean()
    threshold = avg_price * 0.001 * threshold_mult
    
    event_timestamps = get_cusum_events(df['close'], threshold)
    
    print(f"CUSUM Sampling: Sampled {len(event_timestamps)} events from {len(df)} original rows.")
    
    sampled_df = df.loc[event_timestamps].reset_index()
    return sampled_df

if __name__ == "__main__":
    import os
    data_path = 'data/processed/labeled_data.parquet'
    if os.path.exists(data_path):
        df = pd.read_parquet(data_path)
        sampled_df = apply_event_sampling(df)
        # sampled_df.to_parquet('data/processed/sampled_data.parquet')
    else:
        print("Data not found.")
