import pandas as pd
import numpy as np
import os
import argparse

class MonteCarloRegimeSimulator:
    """
    Simulates various market regimes and stress events using stochastic processes.
    """
    def __init__(self, base_price=50000.0, interval_mins=5):
        self.base_price = base_price
        self.interval_mins = interval_mins
        self.dt = 1.0 / (252 * 24 * (60 / interval_mins)) # dt in years

    def simulate_regime(self, n_samples, mu, sigma, regime_name='generic'):
        """
        Simulates a price path using Geometric Brownian Motion.
        mu: annualized expected return
        sigma: annualized volatility
        """
        returns = np.random.normal(
            (mu - 0.5 * sigma**2) * self.dt,
            sigma * np.sqrt(self.dt),
            n_samples
        )
        price_path = self.base_price * np.exp(np.cumsum(returns))
        
        df = pd.DataFrame({
            'timestamp': pd.date_range(start=pd.Timestamp.now(), periods=n_samples, freq=f'{self.interval_mins}min'),
            'close': price_path,
            'regime': regime_name
        })
        
        # Simple OHLC generation
        df['open'] = df['close'].shift(1).fillna(self.base_price)
        df['high'] = df[['open', 'close']].max(axis=1) * (1 + np.abs(np.random.normal(0, 0.001, n_samples)))
        df['low'] = df[['open', 'close']].min(axis=1) * (1 - np.abs(np.random.normal(0, 0.001, n_samples)))
        
        # Add synthetic microstructure noise
        df['volume'] = np.random.lognormal(10, 1, n_samples)
        df['vpin'] = 0.2 + 0.6 * (np.abs(returns) / np.max(np.abs(returns))) + np.random.normal(0, 0.05, n_samples)
        df['mean_imbalance'] = np.random.normal(0, 0.2, n_samples)
        df['mean_spread'] = 0.0001 + 0.0005 * (np.abs(returns) / np.max(np.abs(returns)))
        
        return df

    def simulate_flash_crash(self, n_samples, crash_idx, depth=0.1):
        """
        Simulates a normal path with a sharp flash crash and partial recovery.
        """
        df = self.simulate_regime(n_samples, mu=0.05, sigma=0.2, regime_name='flash_crash')
        
        # Apply crash
        crash_len = 10 # 50 mins if 5m
        recovery_len = 20 # 100 mins
        
        for i in range(crash_len):
            idx = crash_idx + i
            if idx < n_samples:
                df.loc[idx, 'close'] *= (1 - (depth / crash_len) * (i + 1))
                df.loc[idx, 'low'] = df.loc[idx, 'close'] * 0.99
                df.loc[idx, 'vpin'] = 0.8 + np.random.normal(0, 0.05)
                df.loc[idx, 'mean_spread'] *= 5
        
        # Partial recovery
        recovery_start = crash_idx + crash_len
        last_crash_price = df.loc[recovery_start - 1, 'close']
        for i in range(recovery_len):
            idx = recovery_start + i
            if idx < n_samples:
                df.loc[idx, 'close'] *= (1 + (depth * 0.5 / recovery_len) * (i + 1))
                
        return df

    def generate_stress_test_set(self):
        """
        Generates a combined dataset of various stress regimes.
        """
        regimes = [
            self.simulate_regime(1000, mu=0.5, sigma=0.3, regime_name='strong_bull'),
            self.simulate_regime(1000, mu=-0.5, sigma=0.4, regime_name='strong_bear'),
            self.simulate_regime(1000, mu=0.0, sigma=0.1, regime_name='sideways_chop'),
            self.simulate_regime(1000, mu=0.0, sigma=0.8, regime_name='high_volatility'),
            self.simulate_flash_crash(1000, crash_idx=500, depth=0.15)
        ]
        
        final_df = pd.concat(regimes, ignore_index=True)
        final_df['symbol'] = 'SYNTH_BTC'
        return final_df

    def save_synthetic(self, df, output_path='data/processed/synthetic_monte_carlo.parquet'):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_parquet(output_path, engine='pyarrow')
        print(f"Monte Carlo synthetic data saved to {output_path}")

if __name__ == "__main__":
    simulator = MonteCarloRegimeSimulator()
    stress_df = simulator.generate_stress_test_set()
    simulator.save_synthetic(stress_df)
