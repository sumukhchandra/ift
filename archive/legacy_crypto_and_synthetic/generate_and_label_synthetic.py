import pandas as pd
import numpy as np
import os
import argparse
import sys

# Add project root to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from labels.triple_barrier import apply_triple_barrier_labels
from synthetic.bootstrap_generator import BlockBootstrapGenerator
from synthetic.monte_carlo_regime_simulator import MonteCarloRegimeSimulator

def main():
    parser = argparse.ArgumentParser(description="Generate and label synthetic market data.")
    parser.add_argument('--method', type=str, choices=['bootstrap', 'monte_carlo'], default='bootstrap')
    parser.add_argument('--symbol', type=str, default='BTCUSDT')
    parser.add_argument('--samples', type=int, default=10000)
    parser.add_argument('--output', type=str, default='data/processed/synthetic_labeled.parquet')
    args = parser.parse_args()

    print(f"Generating synthetic data using {args.method}...")
    
    if args.method == 'bootstrap':
        try:
            generator = BlockBootstrapGenerator()
            synthetic_df = generator.generate(args.symbol, args.samples, block_size=48)
        except Exception as e:
            print(f"Bootstrap error: {e}")
            return
    else:
        simulator = MonteCarloRegimeSimulator()
        synthetic_df = simulator.generate_stress_test_set()
        # Monte Carlo simulator already handles multiple regimes and labeling might need care
    
    if synthetic_df is None or synthetic_df.empty:
        print("Failed to generate synthetic data.")
        return

    print("Labeling synthetic data...")
    # Using same parameters as in labels/triple_barrier.py
    labeled_df = apply_triple_barrier_labels(synthetic_df, pt_sl=[1.5, 1.0], t1=5, min_ret=0.001)
    
    print(f"Class distribution in synthetic data:")
    print(labeled_df['target'].value_counts(normalize=True))
    
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    labeled_df.to_parquet(args.output, engine='pyarrow')
    print(f"Saved labeled synthetic data to {args.output}")

    # Advice on mixing
    print("\n[Recommendation]")
    print("To use this data, concatenate it with your real labeled data:")
    print("real_df = pd.read_parquet('data/processed/labeled_data.parquet')")
    print("synth_df = pd.read_parquet('data/processed/synthetic_labeled.parquet')")
    print("combined_df = pd.concat([real_df, synth_df], ignore_index=True)")
    print("combined_df.to_parquet('data/processed/mixed_train_data.parquet')")

if __name__ == "__main__":
    main()
