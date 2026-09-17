import pandas as pd
import numpy as np
import joblib
import shap
import matplotlib.pyplot as plt
import os

def run_shap_analysis(model_path='models/saved_models/calibrated_xgb_model.joblib', 
                      data_path='data/processed/labeled_data.parquet',
                      output_dir='research/plots'):
    
    if not os.path.exists(model_path):
        print(f"Model not found at {model_path}")
        return
        
    if not os.path.exists(data_path):
        print(f"Data not found at {data_path}")
        return
        
    os.makedirs(output_dir, exist_ok=True)
    
    # Load model and data
    calibrated_model = joblib.load(model_path)
    df = pd.read_parquet(data_path)
    
    # Get feature columns
    feature_cols = joblib.load('models/saved_models/feature_cols.joblib')
    X = df[feature_cols]
    
    # CalibratedClassifierCV doesn't have a direct SHAP-compatible tree explainer 
    # for the whole ensemble easily. We'll use the base estimator of the first 
    # calibrated classifier or sample the ensemble.
    # Usually, we want to explain the underlying XGBoost model.
    
    # Extract the first base estimator (XGBoost)
    base_model = calibrated_model.calibrated_classifiers_[0].estimator
    
    print("Calculating SHAP values (this may take a while)...")
    explainer = shap.TreeExplainer(base_model)
    
    # Use a sample for SHAP calculation if data is too large
    sample_size = min(1000, len(X))
    X_sample = X.sample(sample_size, random_state=42)
    shap_values = explainer.shap_values(X_sample)
    
    # Summary Plot
    print("Generating SHAP Summary Plot...")
    plt.figure(figsize=(10, 8))
    shap.summary_plot(shap_values, X_sample, show=False)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'shap_summary_plot.png'))
    plt.close()
    
    # SHAP Bar Plot
    print("Generating SHAP Bar Plot...")
    plt.figure(figsize=(10, 8))
    shap.summary_plot(shap_values, X_sample, plot_type="bar", show=False)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'shap_bar_plot.png'))
    plt.close()
    
    print(f"SHAP analysis complete. Plots saved to {output_dir}")

if __name__ == "__main__":
    run_shap_analysis()
