import pandas as pd
import numpy as np
import os
import seaborn as sns
import matplotlib.pyplot as plt
from sklearn.feature_selection import mutual_info_classif

def feature_redundancy_analysis(data_path='../data/processed/labeled_data.parquet', output_dir='../experiments/feature_analysis'):
    if not os.path.exists(data_path):
        print(f"Data file not found: {data_path}")
        return
        
    os.makedirs(output_dir, exist_ok=True)
    df = pd.read_parquet(data_path)
    
    exclude_cols = ['timestamp', 'symbol', 'target', 'future_price', 'future_return', 'type', 'data_version', 'downloaded_at', 'source']
    feature_cols = [c for c in df.columns if c not in exclude_cols]
    
    df = df.dropna(subset=feature_cols + ['target'])
    
    if len(df) == 0:
        print("No valid data for analysis.")
        return
        
    X = df[feature_cols]
    y = df['target']
    
    print("Calculating Correlation Matrix...")
    corr_matrix = X.corr(method='spearman') # Spearman is better for non-linear relationships
    
    plt.figure(figsize=(12, 10))
    sns.heatmap(corr_matrix, annot=False, cmap='coolwarm', vmin=-1, vmax=1)
    plt.title('Feature Spearman Correlation Heatmap')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'correlation_heatmap.png'))
    plt.close()
    
    # Flag highly correlated pairs
    threshold = 0.85
    high_corr = np.where(np.abs(corr_matrix) > threshold)
    high_corr_pairs = [(corr_matrix.index[x], corr_matrix.columns[y], corr_matrix.iloc[x, y]) for x, y in zip(*high_corr) if x != y and x < y]
    
    print("\nHighly Correlated Pairs (|corr| > 0.85):")
    for feat1, feat2, corr in high_corr_pairs:
        print(f"{feat1} <-> {feat2}: {corr:.3f}")
        
    print("\nCalculating Mutual Information...")
    # Sample data for MI if too large
    if len(X) > 50000:
        sample_idx = np.random.choice(len(X), 50000, replace=False)
        X_sample = X.iloc[sample_idx]
        y_sample = y.iloc[sample_idx]
    else:
        X_sample = X
        y_sample = y
        
    mi_scores = mutual_info_classif(X_sample.fillna(0), y_sample, random_state=42)
    mi_df = pd.DataFrame({'feature': feature_cols, 'mi_score': mi_scores})
    mi_df = mi_df.sort_values('mi_score', ascending=False)
    
    mi_df.to_csv(os.path.join(output_dir, 'mutual_information.csv'), index=False)
    
    plt.figure(figsize=(10, 6))
    sns.barplot(x='mi_score', y='feature', data=mi_df.head(15))
    plt.title('Top 15 Features by Mutual Information')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'mutual_information.png'))
    plt.close()
    
    print(f"\nAnalysis saved to {output_dir}")

if __name__ == "__main__":
    feature_redundancy_analysis()
