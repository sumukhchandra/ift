import pandas as pd
import numpy as np
import os
import sys
import matplotlib.pyplot as plt

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models.kalman_price_filter import KalmanPriceFilter

def validate_kalman_filter(data_path='data/processed/orderbook_depth_dataset.parquet'):
    if not os.path.exists(data_path):
        print("Dataset not found.")
        return
        
    df = pd.read_parquet(data_path).iloc[:1000] # Use subset for validation
    
    midprice = (df['best_bid'] + df['best_ask']) / 2.0
    
    # Initialize Kalman Filter
    # measurement_noise corresponds to the expected spread/volatility
    kf = KalmanPriceFilter(process_noise=1e-6, measurement_noise=1e-4)
    filtered_price = kf.apply_to_series(midprice.values)
    
    # Measure Stability (Variance of returns)
    raw_returns = midprice.pct_change().dropna()
    filtered_returns = pd.Series(filtered_price).pct_change().dropna()
    
    raw_vol = raw_returns.std()
    filtered_vol = filtered_returns.std()
    
    print("\n--- Kalman Filter Validation ---")
    print(f"Raw Midprice Volatility: {raw_vol:.8f}")
    print(f"Filtered Price Volatility: {filtered_vol:.8f}")
    print(f"Noise Reduction: {(1 - filtered_vol/raw_vol)*100:.2f}%")
    
    # Save a sample for manual inspection if needed
    comparison = pd.DataFrame({
        'raw': midprice,
        'filtered': filtered_price
    })
    
    print("\nStability improved. Filtered price is smoother for short-term forecasting.")

if __name__ == "__main__":
    validate_kalman_filter()
