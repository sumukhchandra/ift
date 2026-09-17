import pandas as pd
import numpy as np
import glob
import os
import hashlib

def get_content_hash(df):
    """Generate a deterministic hash based on actual dataframe content."""
    hashed_values = pd.util.hash_pandas_object(df, index=True).values
    return hashlib.md5(hashed_values.tobytes()).hexdigest()

def validate_schema(df, expected_schema):
    """Validate columns and dtypes."""
    errors = []
    for col, dtype in expected_schema.items():
        if col not in df.columns:
            errors.append(f"Missing column: {col}")
        elif not pd.api.types.is_dtype_equal(df[col].dtype, dtype):
            errors.append(f"Dtype mismatch for {col}: Expected {dtype}, got {df[col].dtype}")
    return len(errors) == 0, errors

def validate_klines(klines_dir):
    print("\n" + "="*40)
    print("=== Klines Data Validation ===")
    print("="*40)
    
    kline_files = sorted(glob.glob(os.path.join(klines_dir, "*.parquet")))
    if not kline_files:
        print("No kline files found.")
        return None
        
    expected_schema = {
        'open': 'float32', 'high': 'float32', 'low': 'float32', 'close': 'float32', 
        'volume': 'float32', 'timestamp': 'datetime64[ns, UTC]'
    }
    
    df_list = []
    prev_last_timestamp = None
    continuity_errors = 0
    
    for f in kline_files:
        df_chunk = pd.read_parquet(f)
        
        # Enforce UTC
        df_chunk['timestamp'] = pd.to_datetime(df_chunk['timestamp'], utc=True)
        
        # Cross-file continuity
        if prev_last_timestamp is not None:
            first_timestamp = df_chunk['timestamp'].iloc[0]
            if first_timestamp <= prev_last_timestamp:
                print(f"[FAIL] Continuity Error: Overlap between files at {first_timestamp}")
                continuity_errors += 1
                
        prev_last_timestamp = df_chunk['timestamp'].iloc[-1]
        df_list.append(df_chunk)
        
    df = pd.concat(df_list, ignore_index=True).sort_values('timestamp').reset_index(drop=True)
    print(f"[Check] Cross-File Continuity: {continuity_errors} errors")
    
    # Schema validation
    schema_ok, schema_errors = validate_schema(df, expected_schema)
    print(f"[Check] Schema Validation: " + ("(PASS)" if schema_ok else f"(FAIL) - {schema_errors}"))
    
    # 8. Memory Usage
    mem_usage = df.memory_usage(deep=True).sum() / (1024**2)
    print(f"[Memory] Klines DataFrame Size: {mem_usage:.2f} MB")
    
    # 1. Content Fingerprinting
    print(f"[Fingerprint] Klines Full Content Hash: {get_content_hash(df)}")
    print(f"[Info] Total Rows: {len(df):,}")
    print(f"[Info] Time Range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    # 2. Duplicate & Monotonic
    duplicates = df['timestamp'].duplicated().sum()
    print(f"[Check] Duplicate Timestamps: {duplicates} " + ("(PASS)" if duplicates == 0 else "(FAIL)"))
    is_monotonic = df['timestamp'].is_monotonic_increasing
    print(f"[Check] Timestamps Monotonic Increasing: {is_monotonic} " + ("(PASS)" if is_monotonic else "(FAIL)"))
    
    # 3. NaN/Inf
    numeric_cols = ['open', 'high', 'low', 'close', 'volume']
    nans = df[numeric_cols].isna().sum().sum()
    infs = np.isinf(df[numeric_cols]).sum().sum()
    print(f"[Check] NaNs/Infs in OHLCV: {nans}/{infs} " + ("(PASS)" if nans == 0 and infs == 0 else "(FAIL)"))
    
    # 5. OHLC Integrity
    ohlc_integrity = ((df['low'] <= df['open']) & (df['low'] <= df['close']) & (df['high'] >= df['open']) & (df['high'] >= df['close'])).all()
    print(f"[Check] OHLC Integrity (Low <= Open/Close <= High): {ohlc_integrity} " + ("(PASS)" if ohlc_integrity else "(FAIL)"))
    
    negative_prices = (df[['open', 'high', 'low', 'close', 'volume']] < 0).any().any()
    print(f"[Check] Negative Prices/Volume: {negative_prices} " + ("(FAIL)" if negative_prices else "(PASS)"))
    
    # 7. Exact Gap Reporting
    diffs = df['timestamp'].diff()
    expected_diff = pd.Timedelta(minutes=5)
    gaps = diffs[diffs > expected_diff]
    print(f"[Check] Missing Candles (> 5m gaps): {len(gaps)} " + ("(PASS)" if len(gaps) == 0 else "(FAIL)"))
    
    # Volume Spike Diagnostics
    if 'volume' in df.columns and len(df) > 50:
        roll_median = df['volume'].rolling(50).median()
        roll_mad = abs(df['volume'] - roll_median).rolling(50).median()
        vol_z = (df['volume'] - roll_median) / (roll_mad + 1e-8)
        vol_spikes = (vol_z > 10).sum()
        print(f"[Check] Abnormal Volume Spikes (Robust Z > 10): {vol_spikes}")
        
    return df

def validate_trades_streaming(trades_dir):
    print("\n" + "="*40)
    print("=== AggTrades Data Validation (Streaming) ===")
    print("="*40)
    
    trade_files = sorted(glob.glob(os.path.join(trades_dir, "*.parquet")))
    if not trade_files:
        print("No trade files found.")
        return
        
    total_rows = 0
    total_duplicates = 0
    total_nans = 0
    total_infs = 0
    missing_ids_total = 0
    large_gaps_total = 0
    continuity_errors = 0
    
    prev_last_timestamp = None
    prev_last_id = None
    hashes = []
    
    print(f"Streaming through {len(trade_files)} files...")
    
    for f in trade_files:
        df_chunk = pd.read_parquet(f, columns=['agg_trade_id', 'price', 'quantity', 'timestamp'])
        
        # Enforce UTC
        df_chunk['timestamp'] = pd.to_datetime(df_chunk['timestamp'], utc=True)
        
        total_rows += len(df_chunk)
        hashes.append(get_content_hash(df_chunk))
        
        # Cross-file continuity
        if prev_last_timestamp is not None:
            if df_chunk['timestamp'].iloc[0] < prev_last_timestamp:
                continuity_errors += 1
        prev_last_timestamp = df_chunk['timestamp'].iloc[-1]
        
        # Duplicate Checks
        if 'agg_trade_id' in df_chunk.columns:
            total_duplicates += df_chunk.duplicated(subset=['agg_trade_id']).sum()
            
            # Cross-file ID continuity
            if prev_last_id is not None:
                if df_chunk['agg_trade_id'].iloc[0] - prev_last_id > 1:
                    missing_ids_total += 1
            
            id_diffs = df_chunk['agg_trade_id'].diff().dropna()
            missing_ids_total += (id_diffs > 1).sum()
            prev_last_id = df_chunk['agg_trade_id'].iloc[-1]
            
        # NaNs / Infs
        numeric_cols = ['price', 'quantity']
        total_nans += df_chunk[numeric_cols].isna().sum().sum()
        total_infs += np.isinf(df_chunk[numeric_cols]).sum().sum()
        
        # Timestamp gaps
        time_diffs = df_chunk['timestamp'].diff().dropna()
        large_gaps_total += (time_diffs > pd.Timedelta(hours=1)).sum()
        
    print(f"[Memory-Safe Validation Complete]")
    final_hash = hashlib.md5("".join(hashes).encode()).hexdigest()
    print(f"[Fingerprint] Streaming Trades Content Hash: {final_hash}")
    
    print(f"[Info] Total Rows: {total_rows:,}")
    print(f"[Check] Cross-File Time Continuity Errors: {continuity_errors} " + ("(PASS)" if continuity_errors == 0 else "(FAIL)"))
    print(f"[Check] Duplicate Trade IDs: {total_duplicates} " + ("(PASS)" if total_duplicates == 0 else "(FAIL)"))
    print(f"[Check] Missing sequential agg_trade_ids: {missing_ids_total} " + ("(PASS)" if missing_ids_total == 0 else "(FAIL)"))
    print(f"[Check] NaNs/Infs in Price/Volume: {total_nans}/{total_infs} " + ("(PASS)" if total_nans == 0 and total_infs == 0 else "(FAIL)"))
    print(f"[Check] Inactivity Gaps > 1h: {large_gaps_total} " + ("(PASS)" if large_gaps_total == 0 else "(FAIL)"))

def leakage_sentinel_tests(df):
    print("\n" + "="*40)
    print("=== Leakage Sentinel Tests ===")
    print("="*40)
    
    if df is None or 'timestamp' not in df.columns:
        return
        
    # Check for future timestamps
    future_leak = (df['timestamp'] > pd.Timestamp.utcnow()).sum()
    print(f"[Sentinel] Future Timestamps: {future_leak} " + ("(PASS)" if future_leak == 0 else "(FAIL)"))
    
    if 'future_return' in df.columns:
        # Check alignment mismatch (if future return is calculated backwards)
        # Assuming horizon=1 for future_return (5m)
        df = df.sort_values('timestamp')
        actual_future = (df['close'].shift(-1) - df['close']) / df['close']
        mismatches = np.isclose(df['future_return'].dropna(), actual_future.dropna(), atol=1e-5) == False
        print(f"[Sentinel] Target Alignment Mismatches: {mismatches.sum()} " + ("(PASS)" if mismatches.sum() == 0 else "(FAIL)"))

def validate_raw_data(raw_dir='data/raw'):
    klines_dir = os.path.join(raw_dir, 'klines')
    trades_dir = os.path.join(raw_dir, 'trades')
    
    klines_df = validate_klines(klines_dir)
    validate_trades_streaming(trades_dir)
    leakage_sentinel_tests(klines_df)

if __name__ == "__main__":
    validate_raw_data()
