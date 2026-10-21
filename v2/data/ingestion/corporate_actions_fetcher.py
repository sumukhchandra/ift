"""
Corporate Actions Fetcher for AlphaNSE V2.
Captures stock splits and dividend distributions for all universe symbols,
storing an explicit audit log in parquet format for dynamic backtest adjustments.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class CorporateActionsFetcher:
    """
    Fetches corporate actions (splits and dividends) from Yahoo Finance
    and stores them in a normalized metadata table.
    """

    def __init__(
        self,
        universe: Optional[List[str]] = None,
        output_dir: str = "v2/data/storage/metadata"
    ):
        from .historical_fetcher import DEFAULT_UNIVERSE
        self.universe = universe or DEFAULT_UNIVERSE
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_actions(self) -> pd.DataFrame:
        """
        Query splits and dividends for all universe symbols and return consolidated DataFrame.
        """
        records: List[Dict[str, Any]] = []

        for symbol in self.universe:
            logger.info(f"Querying corporate actions for {symbol}...")
            try:
                ticker = yf.Ticker(symbol)
                
                # 1. Fetch splits
                splits = ticker.splits
                if splits is not None and not splits.empty:
                    for date_idx, ratio in splits.items():
                        # ratio > 0
                        records.append({
                            "symbol": symbol,
                            "action_type": "split",
                            "ex_date": pd.to_datetime(date_idx).strftime("%Y-%m-%d"),
                            "value": float(ratio),
                            "recorded_at": datetime.now().isoformat()
                        })

                # 2. Fetch dividends
                divs = ticker.dividends
                if divs is not None and not divs.empty:
                    for date_idx, amount in divs.items():
                        records.append({
                            "symbol": symbol,
                            "action_type": "dividend",
                            "ex_date": pd.to_datetime(date_idx).strftime("%Y-%m-%d"),
                            "value": float(amount),
                            "recorded_at": datetime.now().isoformat()
                        })

            except Exception as e:
                logger.warning(f"Failed to fetch corporate actions for {symbol}: {e}")

        if not records:
            # Create empty structured dataframe
            df = pd.DataFrame(columns=["symbol", "action_type", "ex_date", "value", "recorded_at"])
        else:
            df = pd.DataFrame(records)
            df["ex_date"] = pd.to_datetime(df["ex_date"])
            df = df.sort_values(by=["symbol", "ex_date", "action_type"]).reset_index(drop=True)

        parquet_path = os.path.join(self.output_dir, "corporate_actions.parquet")
        df.to_parquet(parquet_path, index=False)
        logger.info(f"Saved {len(df)} corporate actions to {parquet_path}")
        return df
