import os
import json
import datetime
import pandas as pd

class ExperimentLogger:
    def __init__(self, experiment_dir='../experiments'):
        self.experiment_dir = experiment_dir
        self.run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = os.path.join(self.experiment_dir, self.run_id)
        os.makedirs(self.run_dir, exist_ok=True)
        self.metadata = {
            'run_id': self.run_id,
            'timestamp': datetime.datetime.utcnow().isoformat(),
            'params': {},
            'metrics': {},
            'artifacts': []
        }
        
    def log_param(self, key, value):
        self.metadata['params'][key] = value
        
    def log_metric(self, key, value):
        self.metadata['metrics'][key] = value
        
    def save_feature_snapshot(self, feature_df, filename='feature_snapshot.parquet'):
        snapshot_path = os.path.join(self.run_dir, filename)
        feature_df.to_parquet(snapshot_path, engine='pyarrow')
        self.log_metric('feature_rows', len(feature_df))
        self.log_metric('feature_columns', len(feature_df.columns))
        self.metadata['artifacts'].append(filename)
        print(f"Saved feature snapshot to {snapshot_path}")
        
    def log_dataset_hash(self, df):
        import hashlib
        # Create a deterministic hash of the dataset columns and basic shape
        hash_str = f"{df.shape}_{list(df.columns)}"
        dataset_hash = hashlib.md5(hash_str.encode()).hexdigest()
        self.log_param('dataset_hash', dataset_hash)
        
    def save_plot(self, plt, filename):
        plot_path = os.path.join(self.run_dir, filename)
        plt.savefig(plot_path)
        self.metadata['artifacts'].append(filename)
        print(f"Saved plot artifact to {plot_path}")
        
    def save_metadata(self):
        meta_path = os.path.join(self.run_dir, 'metadata.json')
        with open(meta_path, 'w') as f:
            json.dump(self.metadata, f, indent=4)
        print(f"Saved experiment metadata to {meta_path}")

if __name__ == "__main__":
    # Example usage
    logger = ExperimentLogger()
    logger.log_param("model", "XGBoost")
    logger.log_param("walk_forward_folds", 5)
    logger.log_metric("avg_accuracy", 0.65)
    logger.save_metadata()
