import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta

def generate_hf_synthetic(symbol='BTCUSDT', n_samples=10000, freq_ms=100):
    """
    Generates synthetic 100ms L2 data for microstructure research.
    """
    start_time = datetime.now()
    timestamps = [start_time + timedelta(milliseconds=i*freq_ms) for i in range(n_samples)]
    
    # Stochastic midprice
    returns = np.random.normal(0, 0.00001, n_samples)
    midprice = 60000 * np.exp(np.cumsum(returns))
    
    # Spread (avg 1.0)
    spread = np.abs(np.random.normal(1.0, 0.5, n_samples)) + 0.5
    
    best_bid = midprice - spread/2
    best_ask = midprice + spread/2
    
    # Quantities (mean 1.0)
    # Introduce some correlation between qty and future price
    # e.g. more bid qty -> price goes up
    bid_qty = np.random.lognormal(0, 0.5, n_samples)
    ask_qty = np.random.lognormal(0, 0.5, n_samples)
    
    # Induce alpha in the synthetic data
    for i in range(n_samples - 100):
        # If bid_qty > ask_qty, push next returns slightly positive
        if bid_qty[i] > ask_qty[i] * 1.5:
            returns[i+1:i+11] += 0.0001
        # If ask_qty > bid_qty, push next returns slightly negative
        elif ask_qty[i] > bid_qty[i] * 1.5:
            returns[i+1:i+11] -= 0.0001
            
    # Re-calc midprice with alpha
    midprice = 60000 * np.exp(np.cumsum(returns))
    best_bid = midprice - spread/2
    best_ask = midprice + spread/2

    df = pd.DataFrame({
        'timestamp': timestamps,
        'symbol': symbol,
        'type': 'depth',
        'best_bid': best_bid,
        'best_bid_qty': bid_qty,
        'best_ask': best_ask,
        'best_ask_qty': ask_qty,
        'spread': spread,
        'imbalance': (bid_qty - ask_qty) / (bid_qty + ask_qty)
    })
    
    output_dir = 'data/orderbook'
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f'raw_data_synthetic_hf.parquet')
    df.to_parquet(path)
    print(f"Generated {n_samples} HF synthetic records at {path}")

if __name__ == "__main__":
    generate_hf_synthetic()
