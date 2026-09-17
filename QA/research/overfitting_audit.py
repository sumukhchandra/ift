import pandas as pd
import numpy as np
import os
import joblib
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class OverfittingAuditor:
    def __init__(self, data_path='data/processed/master_labeled_dataset.parquet'):
        self.data_path = data_path

    def audit_probability_distribution(self, model_path):
        """Checks for overconfidence (probabilities bunched at 0 or 1)."""
        if not os.path.exists(model_path): return
        model = joblib.load(model_path)
        df = pd.read_parquet(self.data_path).iloc[-2000:] # Audit recent data
        
        # This is generic, might need feature_cols
        # For simplicity, we assume model is an ensemble model from our system
        try:
            feature_cols = joblib.load('models/saved_models/ensemble/feature_cols.joblib')
            X = df[feature_cols].fillna(0)
            probas = model.predict_proba(X)[:, 1]
            
            std = np.std(probas)
            mean = np.mean(probas)
            
            print(f"\n--- Probability Audit: {os.path.basename(model_path)} ---")
            print(f"Mean Prob: {mean:.4f}, Std Dev: {std:.4f}")
            
            if std > 0.4:
                print("[!] WARNING: Overconfidence detected (high variance in probabilities).")
            elif std < 0.05:
                print("[!] WARNING: Probability collapse detected (model is too conservative/stuck).")
            else:
                print("[+] PASS: Probability distribution is healthy.")
        except Exception as e:
            print(f"Error auditing probabilities: {e}")

    def audit_feature_stability(self):
        """Placeholder for checking if feature importance shifts wildly across regimes."""
        print("\nChecking feature importance stability (TODO)...")
        pass

if __name__ == "__main__":
    auditor = OverfittingAuditor()
    auditor.audit_probability_distribution('models/saved_models/ensemble/xgboost_calibrated.joblib')
