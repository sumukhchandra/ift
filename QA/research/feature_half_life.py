import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import os

class FeatureHalfLifeAnalysis:
    """
    Measures the predictive half-life of features.
    """
    def __init__(self, df):
        self.df = df.sort_values('timestamp').reset_index(drop=True)

    def calculate_half_life(self, feature, target_ret_col='future_return_t1', max_lags=20):
        """
        Calculates correlation decay of a feature with future returns over multiple lags.
        """
        corrs = []
        for lag in range(max_lags):
            # Correlation between feature at t and return at t+lag
            c = self.df[feature].corr(self.df[target_ret_col].shift(-lag))
            corrs.append(abs(c))
            
        # Fit exponential decay: corr = a * e^(-k * lag)
        # ln(corr) = ln(a) - k * lag
        lags = np.arange(max_lags)
        log_corrs = np.log(np.array(corrs) + 1e-9)
        
        model = LinearRegression()
        model.fit(lags.reshape(-1, 1), log_corrs)
        k = -model.coef_[0]
        
        # half-life = ln(2) / k
        if k > 0:
            half_life = np.log(2) / k
        else:
            half_life = np.inf
            
        return half_life, corrs

    def run_analysis(self, features):
        results = []
        for feat in features:
            if feat in self.df.columns:
                hl, corrs = self.calculate_half_life(feat)
                results.append({
                    'feature': feat,
                    'half_life_lags': hl,
                    'initial_corr': corrs[0]
                })
        return pd.DataFrame(results)

if __name__ == "__main__":
    data_path = 'data/processed/labeled_data.parquet'
    if os.path.exists(data_path):
        df = pd.read_parquet(data_path)
        analysis = FeatureHalfLifeAnalysis(df)
        features = ['vpin', 'mean_imbalance', 'mean_spread', 'ofi', 'rsi_14']
        report = analysis.run_analysis(features)
        print("--- Feature Half-Life Analysis ---")
        print(report)
    else:
        print("Data not found.")
