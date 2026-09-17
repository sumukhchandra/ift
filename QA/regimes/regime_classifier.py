import pandas as pd
import numpy as np
from sklearn.mixture import GaussianMixture
import os

class RegimeClassifier:
    """
    Classifies market states using volatility, returns, and VPIN.
    """
    def __init__(self, n_regimes=4):
        self.n_regimes = n_regimes
        self.model = GaussianMixture(n_components=n_regimes, random_state=42)
        self.regime_map = {}

    def fit(self, df):
        """Fits GMM on volatility, returns, and funding rates."""
        features = pd.DataFrame()
        features['returns'] = df.groupby('symbol')['close'].pct_change().rolling(24).mean()
        features['volatility'] = df.groupby('symbol')['close'].pct_change().rolling(24).std()
        
        if 'last_funding_rate' in df.columns:
            features['funding'] = df['last_funding_rate'].rolling(24).mean()
        else:
            features['funding'] = 0
            
        if 'vpin' in df.columns:
            features['vpin'] = df['vpin'].rolling(24).mean()
            
        features = features.dropna()
        self.model.fit(features)
        
        labels = self.model.predict(features)
        temp_df = features.copy()
        temp_df['label'] = labels
        
        summary = temp_df.groupby('label').agg({'returns': 'mean', 'volatility': 'mean', 'funding': 'mean'})
        
        for i, row in summary.iterrows():
            if row['funding'] > 0.0001:
                self.regime_map[i] = 'overheated_bull'
            elif row['returns'] > 0.0005 and row['volatility'] < summary['volatility'].median():
                self.regime_map[i] = 'trending_bull'
            elif row['returns'] < -0.0005:
                self.regime_map[i] = 'trending_bear'
            elif row['volatility'] > summary['volatility'].quantile(0.75):
                self.regime_map[i] = 'high_volatility'
            else:
                self.regime_map[i] = 'sideways'

    def predict(self, df):
        features = pd.DataFrame()
        features['returns'] = df.groupby('symbol')['close'].pct_change().rolling(24).mean()
        features['volatility'] = df.groupby('symbol')['close'].pct_change().rolling(24).std()
        
        if 'last_funding_rate' in df.columns:
            features['funding'] = df['last_funding_rate'].rolling(24).mean()
        else:
            features['funding'] = 0
            
        if 'vpin' in df.columns:
            features['vpin'] = df['vpin'].rolling(24).mean()
            
        features_filled = features.bfill().fillna(0)
        labels = self.model.predict(features_filled)
        return [self.regime_map.get(l, 'unknown') for l in labels]


def classify_micro_regime(candles: pd.DataFrame) -> dict:
    """
    Fast, deterministic intraday regime detector for 1-minute stock candles.
    Classifies micro-state into TRENDING_BULL, TRENDING_BEAR, SIDEWAYS, or HIGH_VOLATILITY.
    Provides dynamic hurdle scaling to prevent whipsaws in sideways/bearish markets.
    """
    if candles is None or len(candles) < 15:
        return {
            "regime": "SIDEWAYS",
            "hurdle_multiplier": 1.0,
            "allows_long_scalp": True,
            "trend_slope_pct": 0.0,
            "vol_ratio": 1.0,
            "description": "Insufficient candles; defaulting to baseline sideways"
        }

    close = candles["close"].astype(float)
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)

    # 1. EMA 5 vs EMA 20 trend slope
    ema_5 = close.ewm(span=5, adjust=False).mean()
    ema_20 = close.ewm(span=20, adjust=False).mean()
    trend_slope = float((ema_5.iloc[-1] - ema_20.iloc[-1]) / (ema_20.iloc[-1] + 1e-9))

    # 2. Return momentum over last 5 and 15 candles
    ret_5 = float((close.iloc[-1] - close.iloc[-5]) / (close.iloc[-5] + 1e-9)) if len(close) >= 5 else 0.0
    ret_15 = float((close.iloc[-1] - close.iloc[-15]) / (close.iloc[-15] + 1e-9)) if len(close) >= 15 else 0.0

    # 3. Micro-ATR expansion ratio (14-period vs 30-period baseline)
    tr = np.maximum(high - low, np.maximum(np.abs(high - close.shift(1)), np.abs(low - close.shift(1))))
    atr_14 = float(tr.rolling(14, min_periods=5).mean().iloc[-1])
    atr_baseline = float(tr.rolling(30, min_periods=10).mean().iloc[-1]) if len(tr) >= 30 else atr_14
    vol_ratio = float(atr_14 / (atr_baseline + 1e-9)) if atr_baseline > 0 else 1.0

    # Classification logic
    if vol_ratio > 1.65:
        regime = "HIGH_VOLATILITY"
        hurdle_multiplier = 1.30
        allows_long = False  # Avoid whipsaws during sudden volatility explosions
        desc = "High volatility expansion; elevated risk of whipsaw"
    elif trend_slope > 0.0008 and ret_5 > 0.0005:
        regime = "TRENDING_BULL"
        hurdle_multiplier = 0.90  # Easier to hit profit targets in trend direction
        allows_long = True
        desc = "Bullish momentum expansion; favorable for long scalps"
    elif trend_slope < -0.0008 and ret_5 < -0.0005:
        regime = "TRENDING_BEAR"
        hurdle_multiplier = 1.50
        allows_long = False  # Counter-trend buying in 1-min bear trends is statistically negative
        desc = "Bearish micro-trend; long scalps suppressed to protect capital"
    else:
        regime = "SIDEWAYS"
        hurdle_multiplier = 1.15
        allows_long = True
        desc = "Rangebound chop; requires higher profit hurdle"

    return {
        "regime": regime,
        "hurdle_multiplier": round(hurdle_multiplier, 2),
        "allows_long_scalp": allows_long,
        "trend_slope_pct": round(trend_slope * 100, 3),
        "vol_ratio": round(vol_ratio, 2),
        "description": desc
    }


if __name__ == "__main__":
    data_path = 'data/processed/labeled_data.parquet'
    if os.path.exists(data_path):
        df = pd.read_parquet(data_path)
        classifier = RegimeClassifier()
        classifier.fit(df)
        df['regime'] = classifier.predict(df)
        print("Regime distribution:")
        print(df['regime'].value_counts(normalize=True))
    else:
        print("Data not found.")

