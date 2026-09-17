import pandas as pd
import numpy as np
import os
from datetime import datetime

class CrisisSimulator:
    """
    Simulates extreme market conditions to stress-test system survival.
    """
    def __init__(self, data_path='data/processed/master_labeled_dataset.parquet'):
        self.data_path = data_path

    def simulate_flash_crash(self, df, crash_magnitude=0.10, duration_bars=12):
        """
        Injects a synthetic flash crash into the provided dataframe.
        """
        crash_df = df.copy()
        start_idx = len(df) // 2
        
        # Linear drop
        for i in range(duration_bars):
            idx = start_idx + i
            drop = (crash_magnitude / duration_bars) * (i + 1)
            crash_df.iloc[idx, crash_df.columns.get_loc('close')] *= (1 - drop)
            crash_df.iloc[idx, crash_df.columns.get_loc('low')] *= (1 - drop * 1.2) # lower low
            
        return crash_df

    def simulate_liquidity_collapse(self, df, spread_multiplier=10.0):
        """
        Simulates extreme spread widening.
        """
        stress_df = df.copy()
        if 'spread' in stress_df.columns:
            stress_df['spread'] *= spread_multiplier
        return stress_df

    def run_war_game(self):
        if not os.path.exists(self.data_path): return
        df = pd.read_parquet(self.data_path).iloc[:1000] # Use subset
        
        print("\n--- Crisis War-Game Simulation ---")
        
        # 1. Flash Crash Test
        crash_df = self.simulate_flash_crash(df)
        print(f"Flash Crash Simulated: Max drop {crash_df['close'].min() / df['close'].iloc[0] - 1:.2%}")
        
        # 2. Liquidity Stress
        stress_df = self.simulate_liquidity_collapse(df)
        print(f"Liquidity Stress: Avg Spread {stress_df['spread'].mean():.4f} (Original: {df['spread'].mean():.4f})")

if __name__ == "__main__":
    sim = CrisisSimulator()
    sim.run_war_game()
