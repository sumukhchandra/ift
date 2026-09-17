import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt

class TaxBleedSimulator:
    """
    Simulates the compounding effect of Indian TDS and taxes on capital over time.
    """
    def __init__(self, initial_capital=800000):
        self.initial_capital = initial_capital
        self.tds_pct = 0.01
        self.profit_tax_pct = 0.30

    def run_simulation(self, n_trades=100, win_rate=0.55, avg_win_pct=0.03, avg_loss_pct=0.015):
        """
        Simulates capital growth vs tax bleed.
        """
        capital = self.initial_capital
        liquid_capital = self.initial_capital
        total_tds = 0.0
        history = []
        
        for i in range(n_trades):
            # Trade outcome
            is_win = np.random.random() < win_rate
            ret_pct = avg_win_pct if is_win else -avg_loss_pct
            
            trade_size = liquid_capital * 0.1 # 10% sizing
            profit_usd = trade_size * ret_pct
            
            # TDS Impact (1% on exit volume)
            # Volume = trade_size + profit
            exit_vol = trade_size + profit_usd
            tds = exit_vol * self.tds_pct
            total_tds += tds
            
            # Profit Tax (30% on gains)
            tax = max(0, profit_usd * self.profit_tax_pct)
            
            # Capital Updates
            liquid_capital += (profit_usd - tds) # TDS is immediate liquidity drain
            # We assume tax is paid later, but we track it
            
            history.append({
                'trade': i,
                'liquid_capital': liquid_capital,
                'total_tds': total_tds,
                'net_pnl': liquid_capital - self.initial_capital
            })
            
            if liquid_capital <= 0:
                print(f"Simulation Terminated: Capital Exhausted at trade {i}")
                break
                
        return pd.DataFrame(history)

if __name__ == "__main__":
    sim = TaxBleedSimulator()
    print("\n--- Tax Bleed Simulation (100 High-Frequency Trades) ---")
    results = sim.run_simulation(n_trades=100, win_rate=0.52, avg_win_pct=0.01, avg_loss_pct=0.008)
    print(results.tail(5))
    
    print("\nNote: High frequency with small edges leads to rapid capital drain via TDS in India.")
