"""
Feature Engineering Pipeline for AlphaNSE V2.
Explicitly enforces the architectural boundary:
  • RAW: Executable market state (tradable prices, sizing ATR, VWAP, spreads, wick structure).
  • ADJUSTED: Continuous statistical state (returns, momentum, RSI, rolling volatility).
  • MARKET: Benchmark index context (^NSEI).
Guarantees strict point-in-time calculation with zero lookahead.
"""

import os
import logging
from typing import List, Dict, Tuple, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

RAW_FEATURE_COLUMNS = [
    "raw_close",
    "raw_open",
    "raw_high",
    "raw_low",
    "raw_volume",
    "raw_vwap",
    "raw_atr_14",
    "raw_wick_pressure",
    "raw_upper_wick",
    "raw_lower_wick",
    "raw_bar_range_pct",
    "raw_dist_vwap_bps"
]

ADJ_FEATURE_COLUMNS = [
    "adj_log_return_5m",
    "adj_log_return_15m",
    "adj_log_return_30m",
    "adj_rsi_14",
    "adj_parkinson_vol",
    "adj_bollinger_b",
    "adj_volume_zscore",
    "adj_macd_diff"
]

BENCHMARK_FEATURE_COLUMNS = [
    "market_adj_return_5m",
    "relative_strength_to_nsei"
]

ALL_FEATURE_COLUMNS = RAW_FEATURE_COLUMNS + ADJ_FEATURE_COLUMNS + BENCHMARK_FEATURE_COLUMNS


class FeaturePipeline:
    """
    Constructs point-in-time microstructure and continuity features from raw and adjusted Parquet series.
    """

    def __init__(
        self,
        raw_parquet_path: str = "v2/data/storage/normalized/historical_5m_raw.parquet",
        adj_parquet_path: str = "v2/data/storage/adjusted/historical_5m_adjusted.parquet"
    ):
        self.raw_parquet_path = raw_parquet_path
        self.adj_parquet_path = adj_parquet_path

    def load_and_merge_series(self) -> pd.DataFrame:
        """
        Loads raw and adjusted datasets and merges on [timestamp, symbol] with explicit prefixes.
        """
        if not os.path.exists(self.raw_parquet_path):
            raise FileNotFoundError(f"Raw parquet not found: {self.raw_parquet_path}")
        if not os.path.exists(self.adj_parquet_path):
            raise FileNotFoundError(f"Adjusted parquet not found: {self.adj_parquet_path}")

        df_raw = pd.read_parquet(self.raw_parquet_path)
        df_adj = pd.read_parquet(self.adj_parquet_path)

        # Ensure datetime indexing
        df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
        df_adj["timestamp"] = pd.to_datetime(df_adj["timestamp"])

        # Rename raw columns
        raw_cols = {c: f"raw_{c}" for c in ["open", "high", "low", "close", "volume"]}
        df_raw = df_raw.rename(columns=raw_cols)

        # Rename adj columns
        adj_cols = {c: f"adj_{c}" for c in ["open", "high", "low", "close", "volume"]}
        df_adj = df_adj.rename(columns=adj_cols)

        # Merge on timestamp and symbol
        merged = pd.merge(df_raw, df_adj, on=["timestamp", "symbol"], how="inner")
        merged = merged.sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)
        return merged

    @staticmethod
    def _compute_symbol_features(sym_df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes features for a single symbol strictly point-in-time.
        """
        df = sym_df.copy().sort_values(by="timestamp").reset_index(drop=True)
        df["date"] = df["timestamp"].dt.date

        # --- 1. RAW EXECUTABLE FEATURES ---
        # Intraday VWAP resetting each session
        df["raw_pv"] = df["raw_close"] * df["raw_volume"]
        df["cum_pv"] = df.groupby("date")["raw_pv"].cumsum()
        df["cum_vol"] = df.groupby("date")["raw_volume"].cumsum()
        df["raw_vwap"] = np.where(df["cum_vol"] > 0, df["cum_pv"] / df["cum_vol"], df["raw_close"])
        df = df.drop(columns=["raw_pv", "cum_pv", "cum_vol"])

        # Distance to VWAP in basis points
        df["raw_dist_vwap_bps"] = np.where(
            df["raw_vwap"] > 0,
            (df["raw_close"] - df["raw_vwap"]) / df["raw_vwap"] * 10000.0,
            0.0
        )

        # Raw True Range & ATR(14)
        prev_close = df["raw_close"].shift(1)
        # Avoid gap from previous day in intraday ATR
        is_first_bar = df["date"] != df["date"].shift(1)
        tr1 = df["raw_high"] - df["raw_low"]
        tr2 = (df["raw_high"] - prev_close).abs()
        tr3 = (df["raw_low"] - prev_close).abs()
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        # For first bar of day, use high - low
        tr = np.where(is_first_bar, tr1, tr)
        df["raw_atr_14"] = pd.Series(tr, index=df.index).rolling(window=14, min_periods=1).mean()

        # Wick Pressures and Ratios
        bar_span = np.maximum(df["raw_high"] - df["raw_low"], 1e-4)
        df["raw_wick_pressure"] = np.clip((df["raw_close"] - df["raw_low"]) / bar_span, 0.0, 1.0)
        df["raw_upper_wick"] = np.clip((df["raw_high"] - np.maximum(df["raw_open"], df["raw_close"])) / bar_span, 0.0, 1.0)
        df["raw_lower_wick"] = np.clip((np.minimum(df["raw_open"], df["raw_close"]) - df["raw_low"]) / bar_span, 0.0, 1.0)
        df["raw_bar_range_pct"] = (df["raw_high"] - df["raw_low"]) / df["raw_close"]

        # --- 2. ADJUSTED CONTINUITY FEATURES ---
        # Log returns (zero out overnight gap between sessions to avoid non-tradable opening jump)
        adj_p = df["adj_close"]
        adj_ret = np.log(adj_p / adj_p.shift(1))
        adj_ret = np.where(is_first_bar, 0.0, adj_ret)
        df["adj_log_return_5m"] = pd.Series(adj_ret, index=df.index).fillna(0.0)

        # Multi-bar returns
        df["adj_log_return_15m"] = df["adj_log_return_5m"].rolling(window=3, min_periods=1).sum()
        df["adj_log_return_30m"] = df["adj_log_return_5m"].rolling(window=6, min_periods=1).sum()

        # RSI 14 on adjusted close
        delta = df["adj_close"].diff()
        delta = np.where(is_first_bar, 0.0, delta)
        gain = np.where(delta > 0, delta, 0.0)
        loss = np.where(delta < 0, -delta, 0.0)
        avg_gain = pd.Series(gain, index=df.index).rolling(window=14, min_periods=1).mean()
        avg_loss = pd.Series(loss, index=df.index).rolling(window=14, min_periods=1).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        df["adj_rsi_14"] = 100.0 - (100.0 / (1.0 + rs))

        # Parkinson Volatility (12 bars)
        hl_ratio = np.log(np.maximum(df["adj_high"], 1e-4) / np.maximum(df["adj_low"], 1e-4))
        pv_bar = (hl_ratio ** 2) / (4.0 * np.log(2.0))
        df["adj_parkinson_vol"] = np.sqrt(pd.Series(pv_bar, index=df.index).rolling(window=12, min_periods=1).mean())

        # Bollinger %B (20 bars, 2 std)
        roll_mean = df["adj_close"].rolling(window=20, min_periods=1).mean()
        roll_std = df["adj_close"].rolling(window=20, min_periods=1).std().fillna(1e-4)
        upper_band = roll_mean + 2.0 * roll_std
        lower_band = roll_mean - 2.0 * roll_std
        band_width = np.maximum(upper_band - lower_band, 1e-4)
        df["adj_bollinger_b"] = (df["adj_close"] - lower_band) / band_width

        # Volume Z-Score (20 bars)
        vol_mean = df["adj_volume"].rolling(window=20, min_periods=1).mean()
        vol_std = df["adj_volume"].rolling(window=20, min_periods=1).std().fillna(1.0)
        df["adj_volume_zscore"] = (df["adj_volume"] - vol_mean) / np.maximum(vol_std, 1.0)

        # MACD (12, 26, 9)
        ema12 = df["adj_close"].ewm(span=12, adjust=False).mean()
        ema26 = df["adj_close"].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        df["adj_macd_diff"] = macd_line - signal_line

        df = df.drop(columns=["date"], errors="ignore")
        return df

    def compute_all_features(self) -> pd.DataFrame:
        """
        Executes feature computation across all universe symbols, adding market benchmark context.
        """
        merged = self.load_and_merge_series()
        logger.info(f"Loaded {len(merged)} combined rows across {merged['symbol'].nunique()} symbols.")

        # Compute per-symbol features
        symbol_dfs = []
        for sym, sym_data in merged.groupby("symbol"):
            sym_feat = self._compute_symbol_features(sym_data)
            symbol_dfs.append(sym_feat)

        full_df = pd.concat(symbol_dfs, ignore_index=True)

        # --- 3. BENCHMARK CONTEXT (^NSEI) ---
        nsei_df = full_df[full_df["symbol"] == "^NSEI"][["timestamp", "adj_log_return_5m"]].copy()
        nsei_df = nsei_df.rename(columns={"adj_log_return_5m": "market_adj_return_5m"})
        full_df = pd.merge(full_df, nsei_df, on="timestamp", how="left")
        full_df["market_adj_return_5m"] = full_df["market_adj_return_5m"].fillna(0.0)

        # Relative strength to Nifty (stock 15m return - index 15m return)
        nsei_15m = full_df[full_df["symbol"] == "^NSEI"][["timestamp", "adj_log_return_15m"]].copy()
        nsei_15m = nsei_15m.rename(columns={"adj_log_return_15m": "market_adj_return_15m"})
        full_df = pd.merge(full_df, nsei_15m, on="timestamp", how="left")
        full_df["market_adj_return_15m"] = full_df["market_adj_return_15m"].fillna(0.0)
        full_df["relative_strength_to_nsei"] = full_df["adj_log_return_15m"] - full_df["market_adj_return_15m"]
        full_df = full_df.drop(columns=["market_adj_return_15m"], errors="ignore")

        # Sort and clean
        full_df = full_df.sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)
        # Fill any initial warmup NaNs with forward/zero fill
        full_df[ALL_FEATURE_COLUMNS] = full_df[ALL_FEATURE_COLUMNS].fillna(0.0)

        logger.info(f"Engineered {len(ALL_FEATURE_COLUMNS)} features across {len(full_df)} total observations.")
        return full_df
