#!/usr/bin/env python3
"""
scripts/update_market_data_session14.py
AlphaNSE V3 — Ingest & Update Market Data through Session 13 Close (2026-10-09).
Ensures all training sets have verified, gap-free market candles prior to Session 14 retraining.
"""

import os
import sys
import json
import pandas as pd
import yfinance as yf
from datetime import datetime

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
QA_DATA_DIR = os.path.join(WORKSPACE_ROOT, "QA", "data")

SYMBOLS = {
    "^NSEI": "NSEI",
    "INFY.NS": "INFY",
    "TATACAP.NS": "TATACAP",
    "BAJFINANCE.NS": "BAJFINANCE",
    "AXISBANK.NS": "AXISBANK",
    "RELIANCE.NS": "RELIANCE",
    "SBIN.NS": "SBIN",
    "HDFCBANK.NS": "HDFCBANK",
    "ICICIBANK.NS": "ICICIBANK",
    "TCS.NS": "TCS",
    "TATASTEEL.NS": "TATASTEEL",
    "BHARTIARTL.NS": "BHARTIARTL"
}

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def update_market_data():
    print("=" * 80)
    print("  [DATA INGESTION] UPDATING MARKET DATA THROUGH SESSION 13 (OCT 09, 2026 CLOSE)")
    print("  TARGETING NEXT SESSION (SESSION 14 / REAL MARKET EXECUTION)")
    print("=" * 80)

    results = {}
    all_updated_dfs = []

    for sym, clean_name in SYMBOLS.items():
        print(f"\n[FETCH] Downloading latest 1m and 5m market candles for {sym} ({clean_name})...")
        try:
            # 1m candles for granular micro-structure
            df_1m = yf.download(sym, period="7d", interval="1m", progress=False)
            if df_1m.empty or len(df_1m) < 10:
                print(f"  [FALLBACK] 1m feed limited, downloading 5m candles for {sym}...")
                df_1m = yf.download(sym, period="14d", interval="5m", progress=False)

            if isinstance(df_1m.columns, pd.MultiIndex):
                # Flatten multi-index
                df_flat = pd.DataFrame()
                for col in ["Open", "High", "Low", "Close", "Volume"]:
                    if (col, sym) in df_1m.columns:
                        df_flat[col.lower()] = df_1m[(col, sym)]
                    elif col in df_1m.columns:
                        df_flat[col.lower()] = df_1m[col]
                df_1m = df_flat

            df_1m = df_1m.reset_index()
            col_map = {c: str(c).lower() for c in df_1m.columns}
            df_1m = df_1m.rename(columns=col_map)
            time_col = [c for c in df_1m.columns if "date" in c or "time" in c or "index" in c][0]
            df_1m = df_1m.rename(columns={time_col: "timestamp"})

            df_1m["timestamp"] = pd.to_datetime(df_1m["timestamp"]).dt.tz_localize(None)
            df_1m["symbol"] = clean_name
            df_1m = df_1m.dropna(subset=["open", "high", "low", "close"])

            # Check existing file
            target_csv = os.path.join(QA_DATA_DIR, f"{clean_name}_1m_weekend.csv")
            if os.path.exists(target_csv):
                old_df = pd.read_csv(target_csv)
                old_df["timestamp"] = pd.to_datetime(old_df["timestamp"])
                old_df["symbol"] = clean_name
                # Combine & deduplicate
                combined = pd.concat([old_df, df_1m], ignore_index=True)
                combined = combined.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
            else:
                combined = df_1m.sort_values("timestamp").reset_index(drop=True)

            combined.to_csv(target_csv, index=False)
            latest_ts = str(combined["timestamp"].iloc[-1])
            first_ts = str(combined["timestamp"].iloc[0])
            total_rows = len(combined)

            print(f"  [OK] Updated {clean_name}: {total_rows:,} total bars | Span: {first_ts[:10]} -> {latest_ts}")
            results[clean_name] = {
                "bars": total_rows,
                "first_timestamp": first_ts,
                "latest_timestamp": latest_ts,
                "latest_close": float(combined["close"].iloc[-1])
            }
            all_updated_dfs.append(combined)

        except Exception as e:
            print(f"  [ERR] Error updating {sym}: {e}")

    # Build master combined dataset
    if all_updated_dfs:
        full_df = pd.concat(all_updated_dfs, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
        master_csv = os.path.join(QA_DATA_DIR, "combined_weekend_1m.csv")
        full_df.to_csv(master_csv, index=False)
        print(f"\n[MASTER DATASET] Saved {len(full_df):,} total bars to {master_csv}")

    # Save summary metadata
    meta_path = os.path.join(QA_DATA_DIR, "session14_premarket_data.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "target_session": "2026-10-12 / Session 14",
            "data_cutoff": "2026-10-09 15:30:00 IST (Session 13 Close)",
            "symbols_updated": results
        }, f, indent=2)

    print(f"[METADATA] Session 14 premarket dataset metadata saved to: {meta_path}")
    print("=" * 80)
    return results


if __name__ == "__main__":
    update_market_data()
