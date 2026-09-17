import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class CrossAssetEngine:
    """
    Fetches global macro data (DXY, SPY) to provide correlation features.
    """
    def __init__(self):
        self.symbols = {'DXY': 'DX-Y.NYB', 'SPY': 'SPY'}

    def fetch_macro_signals(self):
        signals = {}
        for name, ticker in self.symbols.items():
            try:
                data = yf.download(ticker, period='5d', interval='1h', progress=False)
                if data.empty:
                    signals[f'{name}_ret'] = 0.0
                    continue
                
                # Handle potential multi-index from recent yfinance versions
                if isinstance(data.columns, pd.MultiIndex):
                    close_data = data['Close'][ticker]
                else:
                    close_data = data['Close']
                
                # Calculate 24h return
                recent = float(close_data.iloc[-1])
                prev = float(close_data.iloc[0])
                signals[f'{name}_ret'] = (recent - prev) / (prev + 1e-8)
            except Exception as e:
                # print(f"Error fetching {name}: {e}")
                signals[f'{name}_ret'] = 0.0
                
        # Aggregate Risk Score
        spy_ret = signals.get('SPY_ret', 0.0)
        dxy_ret = signals.get('DXY_ret', 0.0)
        
        # Risk Score: Positive if SPY > DXY (Bullish for Crypto)
        risk_score = float(spy_ret) - float(dxy_ret)
        signals['macro_risk_score'] = 0.0 if np.isnan(risk_score) else risk_score
        return signals

if __name__ == "__main__":
    engine = CrossAssetEngine()
    print(engine.fetch_macro_signals())
