"""
Universe Tracker for AlphaNSE V2.
Maintains point-in-time tracking of universe membership to prevent survivorship
bias and document explicit asset onboarding/offboarding dates.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import pandas as pd

logger = logging.getLogger(__name__)

INITIAL_UNIVERSE_METADATA: List[Dict[str, Any]] = [
    {
        "symbol": "RELIANCE.NS",
        "company_name": "Reliance Industries Limited",
        "sector": "Energy / Conglomerate",
        "asset_class": "EQUITY",
        "is_active": True,
        "entry_date": "2026-01-01",
        "exit_date": None,
        "notes": "Nifty 50 constituent; large-cap heavyweight."
    },
    {
        "symbol": "HDFCBANK.NS",
        "company_name": "HDFC Bank Limited",
        "sector": "Financial Services / Banking",
        "asset_class": "EQUITY",
        "is_active": True,
        "entry_date": "2026-01-01",
        "exit_date": None,
        "notes": "Nifty 50 constituent; largest private bank."
    },
    {
        "symbol": "BHARTIARTL.NS",
        "company_name": "Bharti Airtel Limited",
        "sector": "Telecommunications",
        "asset_class": "EQUITY",
        "is_active": True,
        "entry_date": "2026-01-01",
        "exit_date": None,
        "notes": "Nifty 50 constituent; top telecom provider."
    },
    {
        "symbol": "ICICIBANK.NS",
        "company_name": "ICICI Bank Limited",
        "sector": "Financial Services / Banking",
        "asset_class": "EQUITY",
        "is_active": True,
        "entry_date": "2026-01-01",
        "exit_date": None,
        "notes": "Nifty 50 constituent; major private bank."
    },
    {
        "symbol": "TATACAP.NS",
        "company_name": "Tata Capital Limited",
        "sector": "Financial Services / NBFC",
        "asset_class": "EQUITY",
        "is_active": True,
        "entry_date": "2026-01-01",
        "exit_date": None,
        "notes": "Financial services affiliate of Tata Group."
    },
    {
        "symbol": "INFY.NS",
        "company_name": "Infosys Limited",
        "sector": "Information Technology",
        "asset_class": "EQUITY",
        "is_active": True,
        "entry_date": "2026-01-01",
        "exit_date": None,
        "notes": "Nifty 50 constituent; global IT services."
    },
    {
        "symbol": "TCS.NS",
        "company_name": "Tata Consultancy Services Limited",
        "sector": "Information Technology",
        "asset_class": "EQUITY",
        "is_active": True,
        "entry_date": "2026-01-01",
        "exit_date": None,
        "notes": "Nifty 50 constituent; largest IT market cap."
    },
    {
        "symbol": "SBIN.NS",
        "company_name": "State Bank of India",
        "sector": "Financial Services / Public Bank",
        "asset_class": "EQUITY",
        "is_active": True,
        "entry_date": "2026-01-01",
        "exit_date": None,
        "notes": "Nifty 50 constituent; largest public sector bank."
    },
    {
        "symbol": "AXISBANK.NS",
        "company_name": "Axis Bank Limited",
        "sector": "Financial Services / Banking",
        "asset_class": "EQUITY",
        "is_active": True,
        "entry_date": "2026-01-01",
        "exit_date": None,
        "notes": "Nifty 50 constituent; major private bank."
    },
    {
        "symbol": "BAJFINANCE.NS",
        "company_name": "Bajaj Finance Limited",
        "sector": "Financial Services / NBFC",
        "asset_class": "EQUITY",
        "is_active": True,
        "entry_date": "2026-01-01",
        "exit_date": None,
        "notes": "Nifty 50 constituent; consumer lending powerhouse."
    },
    {
        "symbol": "^NSEI",
        "company_name": "Nifty 50 Index",
        "sector": "Broad Market Index",
        "asset_class": "INDEX_BENCHMARK",
        "is_active": True,
        "entry_date": "2026-01-01",
        "exit_date": None,
        "notes": "Benchmark market index for regime detection and beta calculation."
    }
]


class UniverseTracker:
    """
    Manages universe membership tracking and point-in-time asset lists.
    """

    def __init__(self, metadata_dir: str = "v2/data/storage/metadata"):
        self.metadata_dir = metadata_dir
        self.parquet_path = os.path.join(self.metadata_dir, "universe_membership.parquet")
        os.makedirs(self.metadata_dir, exist_ok=True)

    def initialize_default_universe(self) -> pd.DataFrame:
        """Create or initialize universe membership table."""
        df = pd.DataFrame(INITIAL_UNIVERSE_METADATA)
        df["entry_date"] = pd.to_datetime(df["entry_date"])
        df["exit_date"] = pd.to_datetime(df["exit_date"])
        df.to_parquet(self.parquet_path, index=False)
        logger.info(f"Initialized universe membership ({len(df)} assets) at {self.parquet_path}")
        return df

    def get_membership(self) -> pd.DataFrame:
        """Read universe membership table from disk, initializing if missing."""
        if not os.path.exists(self.parquet_path):
            return self.initialize_default_universe()
        return pd.read_parquet(self.parquet_path)

    def get_active_universe(self, as_of: Optional[str] = None) -> List[str]:
        """
        Return list of active symbols as of a specific date (or current date if None).
        Prevents lookahead/survivorship bias.
        """
        df = self.get_membership()
        if as_of is None:
            active_df = df[df["is_active"] == True]
        else:
            target_dt = pd.to_datetime(as_of)
            active_df = df[
                (df["entry_date"] <= target_dt) &
                (df["exit_date"].isna() | (df["exit_date"] >= target_dt))
            ]
        return active_df["symbol"].tolist()
