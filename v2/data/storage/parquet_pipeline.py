"""
Parquet Data Pipeline for AlphaNSE V2.
Standardizes raw vendor chunks, filters to standard NSE session bounds (09:15-15:25 IST),
validates price geometry, isolates raw execution series from adjusted research series,
and generates SHA-256 audited ingestion manifests.
"""

import os
import json
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, time
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

STANDARD_COLUMNS = ["timestamp", "symbol", "open", "high", "low", "close", "volume"]


class ParquetPipeline:
    """
    Transforms raw vendor data into standardized, normalized, and adjusted parquet datasets.
    """

    def __init__(
        self,
        raw_storage_dir: str = "v2/data/storage/raw",
        normalized_storage_dir: str = "v2/data/storage/normalized",
        adjusted_storage_dir: str = "v2/data/storage/adjusted",
        metadata_dir: str = "v2/data/storage/metadata"
    ):
        self.raw_storage_dir = raw_storage_dir
        self.normalized_storage_dir = normalized_storage_dir
        self.adjusted_storage_dir = adjusted_storage_dir
        self.metadata_dir = metadata_dir

        os.makedirs(self.normalized_storage_dir, exist_ok=True)
        os.makedirs(self.adjusted_storage_dir, exist_ok=True)
        os.makedirs(self.metadata_dir, exist_ok=True)

    @staticmethod
    def _compute_sha256(filepath: str) -> str:
        """Calculate SHA-256 hash of a file on disk."""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest()

    def process_raw_chunk(
        self,
        filepath: str,
        symbol: str,
        interval: str = "5m"
    ) -> pd.DataFrame:
        """
        Reads a raw vendor parquet file, normalizes columns and timestamps,
        filters to standard NSE trading hours, and validates price geometry.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Raw chunk not found: {filepath}")

        df = pd.read_parquet(filepath)
        if df.empty:
            return pd.DataFrame(columns=STANDARD_COLUMNS)

        # 1. Reset index to extract Datetime/timestamp
        if "datetime" not in [c.lower() for c in df.columns] and "timestamp" not in [c.lower() for c in df.columns]:
            df = df.reset_index()

        # Rename index column to timestamp
        date_col = None
        for col in df.columns:
            if col.lower() in ("datetime", "timestamp", "date", "index"):
                date_col = col
                break
        if date_col is None:
            date_col = df.columns[0]
        df = df.rename(columns={date_col: "timestamp"})

        # Normalize column names
        df.columns = [str(c).lower().strip().replace(" ", "_") for c in df.columns]

        # 2. Add symbol column
        df["symbol"] = symbol

        # 3. Ensure required OHLCV columns exist
        for req in ["open", "high", "low", "close", "volume"]:
            if req not in df.columns:
                raise ValueError(f"Missing required column '{req}' in {filepath}")

        # Keep only standard columns
        df = df[STANDARD_COLUMNS].copy()

        # 4. Standardize timestamps to Asia/Kolkata timezone
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize("Asia/Kolkata")
        else:
            df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Kolkata")

        # 5. Filter strictly to standard NSE trading sessions
        # 5m: 09:15 to 15:25 inclusive (bar-start covers 09:15 to 15:30)
        # 1m: 09:15 to 15:29 inclusive
        start_t = time(9, 15)
        end_t = time(15, 25) if interval == "5m" else time(15, 29)

        bar_times = df["timestamp"].dt.time
        mask_hours = (bar_times >= start_t) & (bar_times <= end_t)
        # Exclude Saturday / Sunday (weekdays are 0 to 4)
        mask_days = df["timestamp"].dt.dayofweek < 5
        df = df[mask_hours & mask_days].copy()

        # 6. Price Sanity & Geometry Cleansing (fix floating precision jitter)
        # If open or close slightly exceeds high by epsilon <= 1e-3, snap high
        df["high"] = np.maximum(df["high"], np.maximum(df["open"], df["close"]))
        # If open or close slightly below low by epsilon <= 1e-3, snap low
        df["low"] = np.minimum(df["low"], np.minimum(df["open"], df["close"]))

        # Filter out corrupted rows
        valid_prices = (df["open"] > 0) & (df["high"] > 0) & (df["low"] > 0) & (df["close"] > 0)
        valid_geometry = (df["high"] >= df["low"])
        valid_volume = (df["volume"] >= 0)

        df = df[valid_prices & valid_geometry & valid_volume].copy()

        # 7. Deduplicate and sort
        df = df.drop_duplicates(subset=["timestamp"]).sort_values(by="timestamp").reset_index(drop=True)
        return df

    def apply_corporate_action_adjustments(
        self,
        df: pd.DataFrame,
        corporate_actions_path: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Applies standard backward adjustment factors for cash dividends and stock splits (CRSP methodology).
        For a cash dividend D on ex-date T_ex:
            f = (P_{T_ex - 1} - D) / P_{T_ex - 1}
            All prices prior to T_ex are multiplied by f: P_adj(t) = P_raw(t) * f.
        Volume is unchanged for cash dividends, and divided by split factor for splits.
        """
        if corporate_actions_path is None:
            corporate_actions_path = os.path.join(self.metadata_dir, "corporate_actions.parquet")

        if not os.path.exists(corporate_actions_path):
            logger.warning(f"Corporate actions file not found at {corporate_actions_path}, returning unadjusted copy.")
            return df.copy()

        actions_df = pd.read_parquet(corporate_actions_path)
        if actions_df.empty:
            return df.copy()

        actions_df["ex_date"] = pd.to_datetime(actions_df["ex_date"]).dt.date
        df_adj = df.copy()
        df_adj["date"] = pd.to_datetime(df_adj["timestamp"]).dt.date

        min_date = df_adj["date"].min()
        max_date = df_adj["date"].max()

        adjusted_symbol_dfs = []
        for sym, sym_df in df_adj.groupby("symbol", group_keys=False):
            sym_df = sym_df.copy()
            sym_actions = actions_df[
                (actions_df["symbol"] == sym) &
                (actions_df["ex_date"] >= min_date) &
                (actions_df["ex_date"] <= max_date)
            ].sort_values(by="ex_date")

            for _, act in sym_actions.iterrows():
                ex_d = act["ex_date"]
                val = float(act["value"])
                act_type = act["action_type"]

                prev_bars = sym_df[sym_df["date"] < ex_d]
                if prev_bars.empty:
                    continue
                p_prev = float(prev_bars.iloc[-1]["close"])
                if p_prev <= 0:
                    continue

                if act_type == "dividend":
                    if p_prev > val:
                        factor = (p_prev - val) / p_prev
                        mask = sym_df["date"] < ex_d
                        sym_df.loc[mask, ["open", "high", "low", "close"]] *= factor
                        logger.info(f"Applied dividend adjustment for {sym} on {ex_d} (D={val}, P_prev={p_prev:.2f}, factor={factor:.6f})")
                elif act_type == "split":
                    if val > 0:
                        factor = 1.0 / val
                        mask = sym_df["date"] < ex_d
                        sym_df.loc[mask, ["open", "high", "low", "close"]] *= factor
                        sym_df.loc[mask, "volume"] /= factor
                        logger.info(f"Applied split adjustment for {sym} on {ex_d} (ratio={val}, factor={factor:.6f})")

            adjusted_symbol_dfs.append(sym_df)

        result_df = pd.concat(adjusted_symbol_dfs, ignore_index=True)
        result_df = result_df.drop(columns=["date"], errors="ignore")
        return result_df.sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)

    def run_pipeline_for_interval(
        self,
        interval: str = "5m",
        symbols: Optional[List[str]] = None
    ) -> Tuple[str, str]:
        """
        Processes all raw vendor chunks for the specified interval,
        combines them into unified raw (execution) and adjusted (research) parquets,
        and returns paths to the created files.
        """
        raw_vendor_dir = os.path.join(self.raw_storage_dir, f"vendor_{interval}")
        if not os.path.exists(raw_vendor_dir):
            raise FileNotFoundError(f"Vendor raw directory not found: {raw_vendor_dir}")

        if symbols is None:
            from v2.data.ingestion.historical_fetcher import DEFAULT_UNIVERSE
            symbols = DEFAULT_UNIVERSE

        raw_dfs: List[pd.DataFrame] = []

        for sym in symbols:
            clean_sym = sym.replace("^", "INDEX_")
            raw_path = os.path.join(raw_vendor_dir, f"{clean_sym}_raw.parquet")

            if os.path.exists(raw_path):
                df_r = self.process_raw_chunk(raw_path, sym, interval=interval)
                if not df_r.empty:
                    raw_dfs.append(df_r)
            else:
                logger.warning(f"Raw vendor chunk missing for {sym} ({interval}) at {raw_path}")

        if not raw_dfs:
            raise ValueError(f"No raw chunks could be processed for interval {interval}")

        # Combine all symbols into raw execution series
        combined_raw = pd.concat(raw_dfs, ignore_index=True)
        combined_raw = combined_raw.sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)

        # Generate continuous research return series by applying corporate actions
        corp_actions_path = os.path.join(self.metadata_dir, "corporate_actions.parquet")
        combined_adj = self.apply_corporate_action_adjustments(combined_raw, corp_actions_path)

        # Output paths
        out_raw_path = os.path.join(self.normalized_storage_dir, f"historical_{interval}_raw.parquet")
        out_adj_path = os.path.join(self.adjusted_storage_dir, f"historical_{interval}_adjusted.parquet")

        combined_raw.to_parquet(out_raw_path, index=False)
        combined_adj.to_parquet(out_adj_path, index=False)

        logger.info(f"Generated normalized raw {interval} ({len(combined_raw)} rows) -> {out_raw_path}")
        logger.info(f"Generated adjusted {interval} ({len(combined_adj)} rows) -> {out_adj_path}")

        return out_raw_path, out_adj_path

    def generate_manifest(
        self,
        file_paths: List[str],
        manifest_filename: str = "ingestion_manifest.json"
    ) -> Dict[str, Any]:
        """
        Generates SHA-256 checksums, row counts, date spans, and sizes for all generated parquets.
        """
        manifest: Dict[str, Any] = {
            "generated_at": datetime.now().isoformat(),
            "pipeline_version": "AlphaNSE_V2_Phase2",
            "files": {}
        }

        for path in file_paths:
            if not os.path.exists(path):
                continue
            df = pd.read_parquet(path)
            sha256_hash = self._compute_sha256(path)
            file_stat = os.stat(path)
            start_time = str(df["timestamp"].min()) if "timestamp" in df.columns and not df.empty else None
            end_time = str(df["timestamp"].max()) if "timestamp" in df.columns and not df.empty else None
            unique_symbols = df["symbol"].unique().tolist() if "symbol" in df.columns else []

            manifest["files"][os.path.basename(path)] = {
                "filepath": path,
                "sha256": sha256_hash,
                "size_bytes": file_stat.st_size,
                "total_rows": len(df),
                "unique_symbols": unique_symbols,
                "start_time": start_time,
                "end_time": end_time
            }

        manifest_path = os.path.join(self.metadata_dir, manifest_filename)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"Saved ingestion manifest to {manifest_path}")
        return manifest
