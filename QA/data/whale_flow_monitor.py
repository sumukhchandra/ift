import requests
import numpy as np

class WhaleFlowMonitor:
    """
    Monitors large exchange flows and whale transactions.
    """
    def __init__(self):
        # In a real scenario, use Whale Alert API
        self.api_url = "https://api.whale-alert.io/v1/status" 

    def get_whale_sentiment(self):
        """
        Simulates whale flow sentiment based on net exchange movements.
        0.0 (Bearish/Heavy Inflow) to 1.0 (Bullish/Heavy Outflow)
        """
        # Net Flow Simulation: Outflows are bullish (supply decreasing)
        net_flow = np.random.normal(0.5, 0.15) 
        return np.clip(net_flow, 0, 1)

if __name__ == "__main__":
    monitor = WhaleFlowMonitor()
    print(f"Whale Sentiment: {monitor.get_whale_sentiment():.2f}")
