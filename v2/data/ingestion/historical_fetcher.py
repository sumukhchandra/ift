"""
Historical Data Fetcher for AlphaNSE V2.
Acquires empirical market data from Yahoo Finance with resumable state,
per-symbol chunking, retry backoff, and robust error handling.
"""

import os
import json
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

DEFAULT_UNIVERSE: List[str] = [
    "RELIANCE.NS",
    "HDFCBANK.NS",
    "BHARTIARTL.NS",
    "ICICIBANK.NS",
    "TATACAP.NS",
    "INFY.NS",
    "TCS.NS",
    "SBIN.NS",
    "AXISBANK.NS",
    "BAJFINANCE.NS",
    "^NSEI"
]


class HistoricalFetcher:
    """
    Ingests empirical historical OHLCV data from Yahoo Finance for 5m and 1m intervals.
    Provides resumable state tracking, per-symbol parquet chunking, and retry logic.
    """

    def __init__(
        self,
        universe: Optional[List[str]] = None,
        raw_storage_dir: str = "v2/data/storage/raw",
        state_file: str = "v2/data/storage/raw/acquisition_state.json",
        max_retries: int = 3,
        retry_delay_seconds: float = 2.0
    ):
        self.universe = universe or DEFAULT_UNIVERSE
        self.raw_storage_dir = raw_storage_dir
        self.state_file = state_file
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

        # Ensure raw directories exist
        os.makedirs(os.path.join(self.raw_storage_dir, "vendor_5m"), exist_ok=True)
        os.makedirs(os.path.join(self.raw_storage_dir, "vendor_1m"), exist_ok=True)
        self.state: Dict[str, Any] = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        """Load acquisition state from disk if exists."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not read acquisition state ({e}), initializing empty.")
        return {"5m": {}, "1m": {}, "last_updated": None}

    def _save_state(self) -> None:
        """Persist acquisition state to disk."""
        self.state["last_updated"] = datetime.now().isoformat()
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def _download_symbol_with_retry(
        self,
        symbol: str,
        period: str,
        interval: str,
        auto_adjust: bool
    ) -> pd.DataFrame:
        """Download single symbol data with exponential backoff retries."""
        attempt = 0
        last_err: Optional[Exception] = None
        while attempt < self.max_retries:
            attempt += 1
            try:
                df = yf.download(
                    tickers=symbol,
                    period=period,
                    interval=interval,
                    auto_adjust=auto_adjust,
                    progress=False
                )
                if df is not None and not df.empty:
                    return df
                logger.warning(f"Attempt {attempt}/{self.max_retries} for {symbol} ({interval}) returned empty DataFrame.")
            except Exception as e:
                last_err = e
                logger.warning(f"Attempt {attempt}/{self.max_retries} for {symbol} ({interval}) failed: {e}")
            
            if attempt < self.max_retries:
                time.sleep(self.retry_delay_seconds * (2 ** (attempt - 1)))

        if last_err is not None:
            raise RuntimeError(f"Failed to fetch {symbol} ({interval}) after {self.max_retries} attempts: {last_err}")
        return pd.DataFrame()

    def fetch_symbol_5m(self, symbol: str, force_refresh: bool = False) -> Dict[str, str]:
        """
        Fetch ~60d 5m data (raw and adjusted) for a single symbol and save per-symbol chunks.
        Returns paths to saved raw and adjusted parquet files.
        """
        clean_sym = symbol.replace("^", "INDEX_")
        raw_path = os.path.join(self.raw_storage_dir, "vendor_5m", f"{clean_sym}_raw.parquet")
        adj_path = os.path.join(self.raw_storage_dir, "vendor_5m", f"{clean_sym}_adjusted.parquet")

        if not force_refresh and symbol in self.state.get("5m", {}) and os.path.exists(raw_path) and os.path.exists(adj_path):
            logger.info(f"Symbol {symbol} (5m) already acquired in state. Skipping.")
            return {"raw": raw_path, "adjusted": adj_path}

        logger.info(f"Fetching 5m data for {symbol} (period=60d)...")
        # 1. Fetch raw (auto_adjust=False)
        df_raw = self._download_symbol_with_retry(symbol, period="60d", interval="5m", auto_adjust=False)
        if df_raw.empty:
            raise ValueError(f"No 5m data returned for symbol {symbol}")
        
        # 2. Fetch adjusted (auto_adjust=True)
        df_adj = self._download_symbol_with_retry(symbol, period="60d", interval="5m", auto_adjust=True)
        if df_adj.empty:
            raise ValueError(f"No 5m adjusted data returned for symbol {symbol}")

        # Flatten multiindex columns if present
        df_raw = self._normalize_columns(df_raw)
        df_adj = self._normalize_columns(df_adj)

        # Save to parquet
        df_raw.to_parquet(raw_path, index=True)
        df_adj.to_parquet(adj_path, index=True)

        self.state.setdefault("5m", {})[symbol] = {
            "raw_path": raw_path,
            "adjusted_path": adj_path,
            "rows": len(df_raw),
            "start": str(df_raw.index[0]),
            "end": str(df_raw.index[-1]),
            "downloaded_at": datetime.now().isoformat()
        }
        self._save_state()
        logger.info(f"Successfully saved {symbol} 5m chunks ({len(df_raw)} bars).")
        return {"raw": raw_path, "adjusted": adj_path}

    def fetch_symbol_1m(self, symbol: str, force_refresh: bool = False) -> Dict[str, str]:
        """
        Fetch ~7d 1m calibration data (raw and adjusted) for a single symbol and save per-symbol chunks.
        Returns paths to saved raw and adjusted parquet files.
        """
        clean_sym = symbol.replace("^", "INDEX_")
        raw_path = os.path.join(self.raw_storage_dir, "vendor_1m", f"{clean_sym}_raw.parquet")
        adj_path = os.path.join(self.raw_storage_dir, "vendor_1m", f"{clean_sym}_adjusted.parquet")

        if not force_refresh and symbol in self.state.get("1m", {}) and os.path.exists(raw_path) and os.path.exists(adj_path):
            logger.info(f"Symbol {symbol} (1m) already acquired in state. Skipping.")
            return {"raw": raw_path, "adjusted": adj_path}

        logger.info(f"Fetching 1m data for {symbol} (period=7d)...")
        # 1. Fetch raw (auto_adjust=False)
        df_raw = self._download_symbol_with_retry(symbol, period="7d", interval="1m", auto_adjust=False)
        if df_raw.empty:
            raise ValueError(f"No 1m data returned for symbol {symbol}")
        
        # 2. Fetch adjusted (auto_adjust=True)
        df_adj = self._download_symbol_with_retry(symbol, period="7d", interval="1m", auto_adjust=True)
        if df_adj.empty:
            raise ValueError(f"No 1m adjusted data returned for symbol {symbol}")

        # Flatten multiindex columns if present
        df_raw = self._normalize_columns(df_raw)
        df_adj = self._normalize_columns(df_adj)

        # Save to parquet
        df_raw.to_parquet(raw_path, index=True)
        df_adj.to_parquet(adj_path, index=True)

        self.state.setdefault("1m", {})[symbol] = {
            "raw_path": raw_path,
            "adjusted_path": adj_path,
            "rows": len(df_raw),
            "start": str(df_raw.index[0]),
            "end": str(df_raw.index[-1]),
            "downloaded_at": datetime.now().isoformat()
        }
        self._save_state()
        logger.info(f"Successfully saved {symbol} 1m chunks ({len(df_raw)} bars).")
        return {"raw": raw_path, "adjusted": adj_path}

    def fetch_all(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch all universe symbols for both 5m and 1m intervals."""
        results: Dict[str, Any] = {"5m": {}, "1m": {}}
        for symbol in self.universe:
            try:
                results["5m"][symbol] = self.fetch_symbol_5m(symbol, force_refresh=force_refresh)
            except Exception as e:
                logger.error(f"Error fetching 5m data for {symbol}: {e}")
                results["5m"][symbol] = {"error": str(e)}

            try:
                results["1m"][symbol] = self.fetch_symbol_1m(symbol, force_refresh=force_refresh)
            except Exception as e:
                logger.error(f"Error fetching 1m data for {symbol}: {e}")
                results["1m"][symbol] = {"error": str(e)}

        return results

    @staticmethod
    def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Standardize column names to lowercase and drop multiindex levels."""
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex):
            # Take the price measure name (first level)
            df.columns = [str(c[0]).lower().strip().replace(" ", "_") for c in df.columns]
        else:
            df.columns = [str(c).lower().strip().replace(" ", "_") for c in df.columns]
        return df
