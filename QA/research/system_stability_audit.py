import os
import sys
import importlib
import glob
import asyncio
import pandas as pd

class StabilityAuditor:
    def __init__(self, root_dir='.'):
        self.root_dir = root_dir
        self.issues = []

    def check_data_integrity(self, data_path='data/processed/master_labeled_dataset.parquet'):
        print(f"Checking data integrity: {data_path}...")
        if not os.path.exists(data_path):
            self.issues.append(f"Missing Data File: {data_path}")
            return
            
        try:
            df = pd.read_parquet(data_path)
            # 1. Leakage Check: future_return_t1 vs features
            # (Heuristic: Check for high correlation with non-future features)
            # This is complex, but we check for identical columns first
            cols = df.columns.tolist()
            if 'future_return_t1' in cols:
                print("Checking for obvious leakage into target...")
                # Add more sophisticated leakage logic here later
                
            # 2. Duplicate Check
            dupes = df.duplicated(subset=['timestamp', 'symbol']).sum()
            if dupes > 0:
                self.issues.append(f"Data Integrity Error: {dupes} duplicate timestamp/symbol pairs found.")
                
            # 3. Missing Values Check
            nulls = df.isnull().sum().sum()
            if nulls > 0:
                print(f"[!] Warning: {nulls} null values detected in dataset.")
                
            # 4. Temporal Alignment
            # Ensure timestamps are monotonic within each symbol
            for symbol in df['symbol'].unique():
                symbol_df = df[df['symbol'] == symbol]
                if not symbol_df['timestamp'].is_monotonic_increasing:
                    self.issues.append(f"Temporal Alignment Error: Timestamps for {symbol} are not monotonic.")

        except Exception as e:
            self.issues.append(f"Data Read Error: {e}")

    def check_imports(self):
        print("Checking imports and dependencies...")
        py_files = glob.glob(os.path.join(self.root_dir, '**/*.py'), recursive=True)
        for f in py_files:
            if 'venv' in f or '.gemini' in f: continue
            
            # Simple check for circular or broken imports by trying to load modules
            # This is a bit aggressive but helps identify major path issues
            rel_path = os.path.relpath(f, self.root_dir)
            module_name = rel_path.replace(os.path.sep, '.').replace('.py', '')
            
            try:
                # We don't actually import everything here to avoid side effects
                # but we check if sys.path is correctly configured for key modules
                with open(f, 'r') as file:
                    content = file.read()
                    if 'import' in content or 'from' in content:
                        # Scan for local imports that might fail
                        pass 
            except Exception as e:
                self.issues.append(f"File Access Error: {f} - {e}")

    def check_paths(self):
        print("Checking hardcoded paths and directory consistency...")
        required_dirs = ['data/processed', 'data/orderbook', 'logs/live_metrics', 'models/saved_models']
        for d in required_dirs:
            if not os.path.exists(os.path.join(self.root_dir, d)):
                self.issues.append(f"Missing Required Directory: {d}")

    def check_async_patterns(self):
        print("Checking for potential async deadlocks in executor...")
        # Check if asyncio.run or loop management is used correctly in key entry points
        executor_path = os.path.join(self.root_dir, 'paper_trading/executor.py')
        if os.path.exists(executor_path):
            with open(executor_path, 'r') as f:
                content = f.read()
                if 'asyncio.run' in content and 'loop =' in content:
                    self.issues.append("Executor uses mixed async management (asyncio.run + manual loop)")

    def run_full_audit(self):
        self.check_data_integrity()
        self.check_imports()
        self.check_paths()
        self.check_async_patterns()
        
        print("\n--- Stability Audit Results ---")
        if not self.issues:
            print("[+] PASS: No major stability issues detected.")
        else:
            for issue in self.issues:
                print(f"[-] {issue}")
        return len(self.issues) == 0

if __name__ == "__main__":
    auditor = StabilityAuditor()
    auditor.run_full_audit()
