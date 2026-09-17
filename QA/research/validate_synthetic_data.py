import pandas as pd
import numpy as np
import os
from scipy.stats import kurtosis, skew, ks_2samp
import matplotlib.pyplot as plt

class SyntheticDataValidator:
    def __init__(self, real_path='data/processed/features_latest.parquet', 
                 synth_path='data/processed/synthetic_bootstrap.parquet'):
        self.real_df = pd.read_parquet(real_path)
        self.synth_df = pd.read_parquet(synth_path)
        
        # Ensure we have returns
        self.real_df['returns'] = self.real_df.groupby('symbol')['close'].pct_change()
        self.synth_df['returns'] = self.synth_df.groupby('symbol')['close'].pct_change()
        
        self.real_df = self.real_df.dropna()
        self.synth_df = self.synth_df.dropna()

    def compare_distributions(self, column='returns'):
        """Compares kurtosis, skewness, and KS test for a given column."""
        real_data = self.real_df[column]
        synth_data = self.synth_df[column]
        
        metrics = {
            'real_kurtosis': kurtosis(real_data),
            'synth_kurtosis': kurtosis(synth_data),
            'real_skew': skew(real_data),
            'synth_skew': skew(synth_data),
            'ks_stat': ks_2samp(real_data, synth_data).statistic,
            'ks_pvalue': ks_2samp(real_data, synth_data).pvalue
        }
        return metrics

    def compare_autocorrelation(self, column='returns', lags=10):
        """Compares autocorrelation for a given column."""
        real_data = self.real_df[column]
        synth_data = self.synth_df[column]
        
        real_ac = [real_data.autocorr(lag=i) for i in range(1, lags + 1)]
        synth_ac = [synth_data.autocorr(lag=i) for i in range(1, lags + 1)]
        
        return pd.DataFrame({
            'lag': range(1, lags + 1),
            'real_ac': real_ac,
            'synth_ac': synth_ac
        })

    def run_full_validation(self):
        print("--- Synthetic Data Validation Report ---")
        
        # 1. Returns Distribution
        ret_metrics = self.compare_distributions('returns')
        print("\n[Return Distribution]")
        for k, v in ret_metrics.items():
            print(f"{k}: {v:.6f}")
            
        # 2. Volatility Clustering (Absolute Returns AC)
        self.real_df['abs_returns'] = self.real_df['returns'].abs()
        self.synth_df['abs_returns'] = self.synth_df['returns'].abs()
        vol_ac = self.compare_autocorrelation('abs_returns', lags=5)
        print("\n[Volatility Clustering (Autocorr of Abs Returns)]")
        print(vol_ac)
        
        # 3. Microstructure Features
        features = ['vpin', 'mean_imbalance', 'mean_spread']
        print("\n[Microstructure Feature KS Tests]")
        for feat in features:
            if feat in self.real_df.columns and feat in self.synth_df.columns:
                ks = ks_2samp(self.real_df[feat], self.synth_df[feat])
                print(f"{feat}: stat={ks.statistic:.4f}, p-value={ks.pvalue:.4f}")

    def plot_comparison(self, column='returns', output_dir='research/plots'):
        os.makedirs(output_dir, exist_ok=True)
        plt.figure(figsize=(12, 6))
        
        plt.subplot(1, 2, 1)
        self.real_df[column].hist(bins=50, alpha=0.5, label='Real', density=True)
        self.synth_df[column].hist(bins=50, alpha=0.5, label='Synthetic', density=True)
        plt.title(f'{column} Distribution')
        plt.legend()
        
        plt.subplot(1, 2, 2)
        real_ac = [self.real_df[column].autocorr(lag=i) for i in range(1, 20)]
        synth_ac = [self.synth_df[column].autocorr(lag=i) for i in range(1, 20)]
        plt.plot(real_ac, label='Real AC')
        plt.plot(synth_ac, label='Synthetic AC')
        plt.title(f'{column} Autocorrelation')
        plt.legend()
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/synthetic_comparison_{column}.png")
        print(f"Plot saved to {output_dir}/synthetic_comparison_{column}.png")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--synth_path', type=str, default='data/processed/synthetic_bootstrap.parquet')
    args = parser.parse_args()
    
    if os.path.exists(args.synth_path):
        validator = SyntheticDataValidator(synth_path=args.synth_path)
        validator.run_full_validation()
        # validator.plot_comparison('returns')
    else:
        print(f"Synthetic data not found at {args.synth_path}")
