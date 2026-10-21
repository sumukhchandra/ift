import pandas as pd
import numpy as np
import os
import argparse

class BlockBootstrapGenerator:
    """
    Generates synthetic market data using block bootstrapping to preserve 
    local autocorrelation and volatility clustering.
    """
    def __init__(self, data_path='data/processed/features_latest.parquet'):
        self.data_path = data_path
        if not os.path.exists(data_path):
            raise FileNotFoundError(f"Source data not found at {data_path}")
        self.df = pd.read_parquet(data_path)
        self.df = self.df.sort_values(['symbol', 'timestamp']).reset_index(drop=True)

    def generate(self, symbol, n_samples, block_size=24):
        """
        Generates synthetic data for a specific symbol.
        block_size: Number of consecutive samples to take in one block (e.g., 24 for 2 hours if 5m data).
        """
        symbol_df = self.df[self.df['symbol'] == symbol].copy().reset_index(drop=True)
        if symbol_df.empty:
            print(f"No data for symbol {symbol}")
            return None

        n_original = len(symbol_df)
        n_blocks = int(np.ceil(n_samples / block_size))
        
        synthetic_blocks = []
        for _ in range(n_blocks):
            # Pick a random start index that allows for a full block
            start_idx = np.random.randint(0, n_original - block_size + 1)
            block = symbol_df.iloc[start_idx : start_idx + block_size].copy()
            synthetic_blocks.append(block)
        
        synthetic_df = pd.concat(synthetic_blocks, ignore_index=True)
        synthetic_df = synthetic_df.iloc[:n_samples] # Trim to exact size
        
        # Reset timestamps to be continuous (preserving the original interval)
        # We assume the original data has a consistent interval (e.g., 5m)
        start_time = symbol_df['timestamp'].min()
        freq = pd.infer_freq(symbol_df['timestamp'].iloc[:10]) 
        if freq is None:
            # Fallback to manual diff if freq inference fails
            diffs = symbol_df['timestamp'].diff().dropna()
            if not diffs.empty:
                freq = diffs.mode()[0]
            else:
                freq = pd.Timedelta(minutes=5)
                
        synthetic_df['timestamp'] = pd.date_range(start=start_time, periods=n_samples, freq=freq)
        
        # Re-calculate cumulative price/returns if needed, 
        # but bootstrapping blocks already preserves local price movements.
        # However, at block boundaries, there will be price jumps.
        # We should adjust the price levels at boundaries to make it continuous.
        
        self._smooth_block_boundaries(synthetic_df, block_size)
        
        return synthetic_df

    def _smooth_block_boundaries(self, df, block_size):
        """
        Adjusts OHLC prices at block boundaries to ensure continuity.
        """
        for i in range(block_size, len(df), block_size):
            if i >= len(df): break
            
            # Calculate the gap between the last close and current open
            prev_close = df.loc[i-1, 'close']
            curr_open = df.loc[i, 'open']
            gap = curr_open - prev_close
            
            # Shift all subsequent prices in the current block and beyond
            price_cols = ['open', 'high', 'low', 'close', 'vwap']
            df.loc[i:, price_cols] -= gap

    def save_synthetic(self, df, output_path='data/processed/synthetic_bootstrap.parquet'):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_parquet(output_path, engine='pyarrow')
        print(f"Synthetic data saved to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', type=str, default='BTCUSDT')
    parser.add_argument('--samples', type=int, default=5000)
    parser.add_argument('--block_size', type=int, default=48) # 4 hours if 5m
    args = parser.parse_args()
    
    try:
        generator = BlockBootstrapGenerator()
        synthetic_df = generator.generate(args.symbol, args.samples, args.block_size)
        if synthetic_df is not None:
            generator.save_synthetic(synthetic_df)
    except Exception as e:
        print(f"Error: {e}")
