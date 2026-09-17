import pandas as pd
import numpy as np
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models.microprice_model import MicropriceModel

def validate_microprice(data_path='data/processed/orderbook_depth_dataset.parquet'):
    if not os.path.exists(data_path):
        print("Dataset not found.")
        return
        
    df = pd.read_parquet(data_path)
    model = MicropriceModel()
    
    print(f"Validating Microprice on {len(df)} samples...")
    
    # 1. Calculate Microprice Drift
    df['midprice'] = (df['best_bid'] + df['best_ask']) / 2.0
    df['micro_drift'] = df.apply(lambda r: model.calculate_microprice(r['best_bid'], r['best_bid_qty'], r['best_ask'], r['best_ask_qty']) - r['midprice'], axis=1)
    
    # 2. Calculate Future Returns at various horizons
    # Assuming 100ms frequency
    horizons = {
        '1s': 10,
        '5s': 50,
        '15s': 150,
        '60s': 600
    }
    
    results = []
    
    for label, periods in horizons.items():
        # Future midprice return
        df[f'f_ret_{label}'] = df['midprice'].shift(-periods) / df['midprice'] - 1
        
        # Drop rows with NaNs (end of dataset)
        valid_df = df.dropna(subset=[f'f_ret_{label}', 'micro_drift'])
        
        if valid_df.empty:
            continue
            
        # Correlation
        corr = valid_df['micro_drift'].corr(valid_df[f'f_ret_{label}'])
        
        # Directional Win Rate (Sign match)
        win_rate = (np.sign(valid_df['micro_drift']) == np.sign(valid_df[f'f_ret_{label}'])).mean()
        
        # Expected edge (Avg return * sign of drift)
        edge = (np.sign(valid_df['micro_drift']) * valid_df[f'f_ret_{label}']).mean() * 10000 # in bps
        
        results.append({
            'horizon': label,
            'correlation': corr,
            'win_rate': win_rate,
            'edge_bps': edge
        })
        
    results_df = pd.DataFrame(results)
    print("\n--- Microprice Validation Results ---")
    print(results_df.to_string(index=False))
    
    return results_df

if __name__ == "__main__":
    validate_microprice()
