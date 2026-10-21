#!/usr/bin/env python3
"""
scripts/ingest_forward_oos_data.py
Fetches and archives strictly post-training out-of-sample 1-minute market data
(October 13, 2026 09:15:00 IST to October 14, 2026 15:29:00 IST).
Guarantees T_train_end (2026-10-12 10:47:48) strictly precedes T_eval_start (2026-10-13 09:15:00).
"""

import os
import sys
import pandas as pd
import yfinance as yf

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_FILE = os.path.join(WORKSPACE_ROOT, "QA", "data", "genuine_forward_oos_oct13_oct14.csv")

SYMBOLS = [
    "INFY.NS", "RELIANCE.NS", "TATASTEEL.NS", "BAJFINANCE.NS", "AXISBANK.NS",
    "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "BHARTIARTL.NS", "NIFTYBEES.NS"
]

def ingest_forward_oos():
    print("=" * 80)
    print("  [INGEST] INGESTING GENUINE OUT-OF-SAMPLE FORWARD MARKET DATA (OCT 13-14, 2026)")
    print("=" * 80)
    dfs = []
    for s in SYMBOLS:
        print(f"  * Fetching 1m candles for {s}...")
        df = yf.download(s, period="5d", interval="1m", progress=False)
        if df is None or df.empty:
            print(f"    [WARN] No data returned for {s}")
            continue

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        df = df.reset_index()
        for col in ["Datetime", "datetime", "Date", "date", "index"]:
            if col in df.columns:
                df = df.rename(columns={col: "timestamp"})
                break

        clean_sym = s.replace(".NS", "")
        df["symbol"] = clean_sym
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Filter strictly post-October 12 10:47:48 training timestamp
        cutoff = pd.Timestamp("2026-10-13 09:15:00+05:30")
        post = df[df["timestamp"] >= cutoff].copy()
        print(f"    [OK] Filtered {len(post)} post-training candles ({post['timestamp'].min()} to {post['timestamp'].max()})")
        dfs.append(post)

    if not dfs:
        print("[FAIL] Error: No forward data fetched.")
        return False

    combined = pd.concat(dfs, ignore_index=True).sort_values(["timestamp", "symbol"]).reset_index(drop=True)
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    combined.to_csv(OUT_FILE, index=False)
    print("=" * 80)
    print(f"  [OK] Saved {len(combined):,} genuine forward rows to: {OUT_FILE}")
    print(f"  * Instruments: {sorted(combined['symbol'].unique())}")
    print(f"  * Date Boundaries: {combined['timestamp'].min()} to {combined['timestamp'].max()}")
    print("=" * 80)
    return True

if __name__ == "__main__":
    ingest_forward_oos()
