import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

def analyze_confidence_buckets(data_path='../data/processed/labeled_data.parquet', output_dir='../experiments/confidence_analysis'):
    if not os.path.exists(data_path):
        print(f"Data file not found: {data_path}")
        return
        
    os.makedirs(output_dir, exist_ok=True)
    df = pd.read_parquet(data_path)
    
    if 'pred_prob' not in df.columns:
        print("pred_prob not found in data. Generating predictions now...")
        import joblib
        import xgboost as xgb
        model_path = '../models/saved_models/calibrated_xgb_model.joblib'
        if not os.path.exists(model_path):
            print("Model not found. Train model first.")
            return
            
        model = joblib.load(model_path)
        feature_cols_path = '../models/saved_models/feature_cols.joblib'
        if os.path.exists(feature_cols_path):
            feature_cols = joblib.load(feature_cols_path)
        else:
            exclude_cols = ['timestamp', 'symbol', 'target', 'future_price', 'future_return', 'type', 'data_version', 'downloaded_at', 'source']
            feature_cols = [c for c in df.columns if c not in exclude_cols]
            
        df = df.dropna(subset=feature_cols)
        X = df[feature_cols]
        df['pred_prob'] = model.predict_proba(X)[:, 1]
        
    bins = np.arange(0, 1.1, 0.1)
    labels = [f"{int(b*100)}-{int((b+0.1)*100)}%" for b in bins[:-1]]
    
    df['confidence_bucket'] = pd.cut(df['pred_prob'], bins=bins, labels=labels, right=False)
    
    bucket_stats = df.groupby('confidence_bucket').agg(
        total_predictions=('target', 'count'),
        actual_win_rate=('target', 'mean')
    ).reset_index()
    
    bucket_stats = bucket_stats[bucket_stats['total_predictions'] > 0]
    
    print("\nConfidence Bucket Analysis:")
    print(bucket_stats.to_string(index=False))
    
    bucket_stats.to_csv(os.path.join(output_dir, 'confidence_buckets.csv'), index=False)
    
    plt.figure(figsize=(10, 6))
    bars = plt.bar(bucket_stats['confidence_bucket'], bucket_stats['actual_win_rate'] * 100)
    plt.axhline(50, color='red', linestyle='--', label='50% Break-Even')
    
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2, yval + 1, f'{yval:.1f}%', ha='center', va='bottom')
        
    plt.title('Actual Win Rate by Prediction Confidence Bucket')
    plt.xlabel('Confidence Bucket')
    plt.ylabel('Actual Win Rate (%)')
    plt.ylim(0, 100)
    plt.xticks(rotation=45)
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'confidence_win_rates.png'))
    plt.close()
    
    print(f"Analysis saved to {output_dir}")

if __name__ == "__main__":
    analyze_confidence_buckets()
