"""
Dataset Updater & Quality Gate for AlphaNSE V2 Adaptive Daily Pipeline.
Merges historical baseline data with completed chronological fresh sessions strictly <= D-1.
Enforces zero lookahead, timestamp monotonicity, geometry validity, and cryptographic SHA-256 hashing.
"""

import os
import glob
import json
import hashlib
import logging
from datetime import datetime, date, time
from typing import Tuple, Dict, Any, List, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

STANDARD_COLUMNS = ["timestamp", "symbol", "open", "high", "low", "close", "volume"]


class DatasetUpdater:
    """
    Manages the pre-market research dataset update before Day D market open.
    """

    def __init__(
        self,
        base_raw_path: str = "v2/data/storage/normalized/historical_5m_raw.parquet",
        base_adj_path: str = "v2/data/storage/adjusted/historical_5m_adjusted.parquet",
        fresh_dir: str = "v2/data/storage/fresh",
        output_dir: str = "v2/data/storage/adaptive"
    ):
        self.base_raw_path = base_raw_path
        self.base_adj_path = base_adj_path
        self.fresh_dir = fresh_dir
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def prepare_dataset_for_day(
        self,
        target_day: date
    ) -> Dict[str, Any]:
        """
        Gathers all market data strictly prior to target_day (i.e. <= target_day - 1),
        validates data quality, calculates cryptographic SHA-256 hash, and saves training parquets.

        Returns metadata dictionary containing:
          - raw_path: path to point-in-time raw parquet
          - adj_path: path to point-in-time adjusted parquet
          - dataset_hash: SHA-256 of training dataset
          - data_cutoff: ISO string of cutoff timestamp
          - training_rows: number of observations
          - start_date: earliest date string
          - end_date: latest date string
        """
        logger.info(f"Preparing adaptive training dataset strictly prior to {target_day}...")

        # 1. Load historical baseline
        if not os.path.exists(self.base_raw_path) or not os.path.exists(self.base_adj_path):
            raise FileNotFoundError(f"Baseline parquets not found: {self.base_raw_path}, {self.base_adj_path}")

        df_raw_base = pd.read_parquet(self.base_raw_path)
        df_adj_base = pd.read_parquet(self.base_adj_path)

        df_raw_base["timestamp"] = pd.to_datetime(df_raw_base["timestamp"])
        df_adj_base["timestamp"] = pd.to_datetime(df_adj_base["timestamp"])

        # 2. Gather fresh sessions strictly < target_day
        fresh_pattern = os.path.join(self.fresh_dir, "session_*_5m.parquet")
        fresh_files = sorted(glob.glob(fresh_pattern))
        eligible_fresh_dfs = []

        for fpath in fresh_files:
            fname = os.path.basename(fpath)
            # format: session_YYYYMMDD_5m.parquet
            parts = fname.replace("session_", "").replace("_5m.parquet", "")
            try:
                session_dt = datetime.strptime(parts, "%Y%m%d").date()
                if session_dt < target_day:
                    df_fresh = pd.read_parquet(fpath)
                    df_fresh["timestamp"] = pd.to_datetime(df_fresh["timestamp"])
                    eligible_fresh_dfs.append(df_fresh)
                    logger.info(f"  Included completed prior session: {session_dt} ({len(df_fresh)} bars)")
                else:
                    logger.info(f"  Excluded future session from training: {session_dt} (>= {target_day})")
            except ValueError:
                continue

        # 3. Combine raw and adjusted datasets
        if eligible_fresh_dfs:
            combined_fresh = pd.concat(eligible_fresh_dfs, ignore_index=True)
            df_raw_all = pd.concat([df_raw_base, combined_fresh], ignore_index=True)
            df_adj_all = pd.concat([df_adj_base, combined_fresh], ignore_index=True)
        else:
            df_raw_all = df_raw_base.copy()
            df_adj_all = df_adj_base.copy()

        # Filter strictly < target_day (extra safety against any timestamp leakage)
        df_raw_all = df_raw_all[df_raw_all["timestamp"].dt.date < target_day].copy()
        df_adj_all = df_adj_all[df_adj_all["timestamp"].dt.date < target_day].copy()

        # Deduplicate and sort
        df_raw_all = df_raw_all.drop_duplicates(subset=["symbol", "timestamp"]).sort_values(
            by=["symbol", "timestamp"]
        ).reset_index(drop=True)
        df_adj_all = df_adj_all.drop_duplicates(subset=["symbol", "timestamp"]).sort_values(
            by=["symbol", "timestamp"]
        ).reset_index(drop=True)

        if df_raw_all.empty:
            raise ValueError(f"Training dataset is empty prior to {target_day}!")

        # 4. Strict Data Quality & Geometry Validation
        geom_violations = (
            (df_raw_all["high"] < df_raw_all["low"]) |
            (df_raw_all["high"] < df_raw_all["open"]) |
            (df_raw_all["high"] < df_raw_all["close"]) |
            (df_raw_all["low"] > df_raw_all["open"]) |
            (df_raw_all["low"] > df_raw_all["close"]) |
            (df_raw_all["open"] <= 0) |
            (df_raw_all["close"] <= 0)
        ).sum()
        if geom_violations > 0:
            raise ValueError(f"Dataset contains {geom_violations} OHLC price geometry violations!")

        # 5. Determine Cutoff and Hashes
        max_ts = df_raw_all["timestamp"].max()
        min_ts = df_raw_all["timestamp"].min()
        data_cutoff_iso = max_ts.isoformat()

        # Deterministic SHA-256 hash of raw training data bytes
        raw_bytes = df_raw_all.to_parquet(index=False)
        dataset_hash = hashlib.sha256(raw_bytes).hexdigest()

        # 6. Save point-in-time parquets
        target_str = target_day.strftime("%Y%m%d")
        raw_out_path = os.path.join(self.output_dir, f"train_raw_D{target_str}.parquet")
        adj_out_path = os.path.join(self.output_dir, f"train_adj_D{target_str}.parquet")

        df_raw_all.to_parquet(raw_out_path, index=False)
        df_adj_all.to_parquet(adj_out_path, index=False)

        logger.info(
            f"Dataset updated for {target_day}: {len(df_raw_all)} rows, cutoff: {data_cutoff_iso}, "
            f"hash: {dataset_hash[:16]}..."
        )

        return {
            "raw_path": raw_out_path,
            "adj_path": adj_out_path,
            "dataset_hash": dataset_hash,
            "data_cutoff": data_cutoff_iso,
            "training_rows": len(df_raw_all),
            "start_date": min_ts.strftime("%Y-%m-%d"),
            "end_date": max_ts.strftime("%Y-%m-%d"),
            "max_timestamp": max_ts
        }
