import pandas as pd
import numpy as np
import os
import glob
from tqdm import tqdm

def process_raw_orderbook(raw_dir='data/orderbook', output_path='data/processed/orderbook_depth_dataset.parquet'):
    """
    Processes raw 100ms depth and trade updates into a structured L2 dataset.
    """
    files = glob.glob(os.path.join(raw_dir, 'raw_data_*.parquet'))
    if not files:
        print(f"No raw data found in {raw_dir}")
        return
        
    all_data = []
    print(f"Processing {len(files)} raw data files for Layer 2 research...")
    
    for f in tqdm(files):
        df = pd.read_parquet(f)
        # Separate depth and trade events
        depth_df = df[df['type'] == 'depth'].copy()
        
        if depth_df.empty:
            continue
            
        # 1. Microprice: (P_ask * Q_bid + P_bid * Q_ask) / (Q_bid + Q_ask)
        depth_df['microprice'] = (depth_df['best_ask'] * depth_df['best_bid_qty'] + 
                                  depth_df['best_bid'] * depth_df['best_ask_qty']) / \
                                 (depth_df['best_bid_qty'] + depth_df['best_ask_qty'] + 1e-9)
        
        # 2. Spread Dynamics
        depth_df['spread_velocity'] = depth_df['spread'].diff().fillna(0)
        
        # 3. Book Slope & Curvature (Proxy: Spread / Imbalance magnitude)
        depth_df['book_slope'] = depth_df['spread'] / (np.abs(depth_df['imbalance']) + 1e-6)
        depth_df['slope_curvature'] = depth_df['book_slope'].diff().fillna(0)
        
        # 4. Multi-level Imbalance (Placeholder for when L2 data is available)
        # If 'bids' and 'asks' columns existed as lists of [price, qty]
        if 'bids' in depth_df.columns and 'asks' in depth_df.columns:
            def calc_level_imbalance(row, n_levels=5):
                bids = row['bids'][:n_levels]
                asks = row['asks'][:n_levels]
                bid_vol = sum([b[1] for b in bids])
                ask_vol = sum([a[1] for a in asks])
                return (bid_vol - ask_vol) / (bid_vol + ask_vol + 1e-9)
            
            depth_df['imbalance_l5'] = depth_df.apply(lambda r: calc_level_imbalance(r, 5), axis=1)
            
        # 5. Wall Detection (Quantity > Mean * Multiplier)
        mean_qty = depth_df['best_bid_qty'].rolling(100).mean()
        depth_df['is_bid_wall'] = (depth_df['best_bid_qty'] > mean_qty * 3.0).astype(int)
        depth_df['is_ask_wall'] = (depth_df['best_ask_qty'] > mean_qty * 3.0).astype(int)
        
        # 6. Imbalance Momentum
        depth_df['imbalance_momentum'] = depth_df['imbalance'].diff(5).fillna(0)
        
        all_data.append(depth_df)
        
    if not all_data:
        print("No depth data processed.")
        return
        
    final_l2_df = pd.concat(all_data, ignore_index=True)
    final_l2_df = final_l2_df.sort_values(['symbol', 'timestamp']).reset_index(drop=True)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final_l2_df.to_parquet(output_path, engine='pyarrow')
    print(f"Layer 2 Research Dataset built: {len(final_l2_df)} rows at {output_path}")

if __name__ == "__main__":
    process_raw_orderbook()
