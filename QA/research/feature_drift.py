import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
from scipy.stats import entropy

def calculate_psi(expected, actual, buckets=10):
    """Calculate the Population Stability Index (PSI) between two distributions."""
    if len(expected) == 0 or len(actual) == 0:
        return np.nan
        
    expected_min, expected_max = np.min(expected), np.max(expected)
    if expected_min == expected_max:
        return 0.0
        
    breakpoints = np.linspace(expected_min, expected_max, buckets + 1)
    
    expected_percents, _ = np.histogram(expected, bins=breakpoints)
    actual_percents, _ = np.histogram(actual, bins=breakpoints)
    
    expected_percents = expected_percents / len(expected)
    actual_percents = actual_percents / len(actual)
    
    expected_percents = np.where(expected_percents == 0, 0.0001, expected_percents)
    actual_percents = np.where(actual_percents == 0, 0.0001, actual_percents)
    
    psi_value = np.sum((expected_percents - actual_percents) * np.log(expected_percents / actual_percents))
    return psi_value

def calculate_kl_divergence(p, q, buckets=10):
    """Calculate KL Divergence between two distributions."""
    if len(p) == 0 or len(q) == 0:
        return np.nan
        
    min_val = min(np.min(p), np.min(q))
    max_val = max(np.max(p), np.max(q))
    
    if min_val == max_val:
        return 0.0
        
    bins = np.linspace(min_val, max_val, buckets + 1)
    
    p_hist, _ = np.histogram(p, bins=bins)
    q_hist, _ = np.histogram(q, bins=bins)
    
    p_hist = p_hist / len(p)
    q_hist = q_hist / len(q)
    
    p_hist = p_hist + 1e-10
    q_hist = q_hist + 1e-10
    
    return entropy(p_hist, q_hist)

def feature_drift_analysis(data_path='../data/processed/labeled_data.parquet', output_dir='../experiments/feature_drift', window_days=7):
    if not os.path.exists(data_path):
        print(f"Data file not found: {data_path}")
        return
        
    os.makedirs(output_dir, exist_ok=True)
    df = pd.read_parquet(data_path)
    
    if 'timestamp' not in df.columns:
        print("Timestamp column required for drift analysis.")
        return
        
    df = df.sort_values('timestamp').reset_index(drop=True)
    df['date'] = df['timestamp'].dt.date
    dates = df['date'].unique()
    
    if len(dates) < window_days * 2:
        print("Not enough days of data for drift analysis.")
        return
        
    exclude_cols = ['timestamp', 'symbol', 'target', 'future_price', 'future_return', 'type', 'data_version', 'downloaded_at', 'source', 'date']
    feature_cols = [c for c in df.columns if c not in exclude_cols]
    
    # Use first window_days as baseline
    baseline_dates = dates[:window_days]
    baseline_df = df[df['date'].isin(baseline_dates)].copy()
    
    drift_results = []
    
    # Iterate through remaining days
    for date in dates[window_days:]:
        current_df = df[df['date'] == date].copy()
        if len(current_df) < 100:
            continue
            
        for feature in feature_cols:
            baseline_vals = baseline_df[feature].dropna().values
            current_vals = current_df[feature].dropna().values
            
            if len(baseline_vals) > 0 and len(current_vals) > 0:
                psi = calculate_psi(baseline_vals, current_vals)
                kl = calculate_kl_divergence(baseline_vals, current_vals)
                mean_drift = np.mean(current_vals) - np.mean(baseline_vals)
                std_drift = np.std(current_vals) - np.std(baseline_vals)
                
                drift_results.append({
                    'date': date,
                    'feature': feature,
                    'psi': psi,
                    'kl_divergence': kl,
                    'mean_drift': mean_drift,
                    'std_drift': std_drift
                })
                
    if not drift_results:
        print("No drift results calculated.")
        return
        
    drift_df = pd.DataFrame(drift_results)
    drift_df.to_csv(os.path.join(output_dir, 'feature_drift_daily.csv'), index=False)
    
    # Plot PSI over time for top features
    mean_psi = drift_df.groupby('feature')['psi'].mean().sort_values(ascending=False)
    top_drifting = mean_psi.head(5).index.tolist()
    
    plt.figure(figsize=(12, 6))
    for feature in top_drifting:
        feature_data = drift_df[drift_df['feature'] == feature]
        plt.plot(pd.to_datetime(feature_data['date']), feature_data['psi'], label=feature, marker='o')
        
    plt.axhline(0.1, color='orange', linestyle='--', label='Warning Threshold (0.1)')
    plt.axhline(0.2, color='red', linestyle='--', label='Critical Threshold (0.2)')
    plt.title('Top 5 Drifting Features (PSI over Time)')
    plt.xlabel('Date')
    plt.ylabel('Population Stability Index (PSI)')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'top_drifting_features_psi.png'))
    plt.close()
    
    print(f"Drift analysis saved to {output_dir}")

if __name__ == "__main__":
    feature_drift_analysis()
