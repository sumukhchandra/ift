"""
Raw Execution Price Forward Labeling for AlphaNSE V2.
Constructs multi-horizon forward return labels strictly from raw tradable prices:
  R_{t+H} = ln(P_{raw, t+H} / P_{raw, t}) for H in {1, 2, 3} bars (5m, 10m, 15m).
Enforces intraday boundary constraints (no overnight forward leakage).
"""

import logging
from typing import List, Dict, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

HORIZONS = [1, 2, 3, 6, 12]  # 5m (1 bar), 10m (2 bars), 15m (3 bars), 30m (6 bars), 60m (12 bars)


class IntradayLabeler:
    """
    Constructs raw executable forward return targets and directional conviction labels.
    """

    def __init__(
        self,
        horizons: Optional[List[int]] = None,
        cost_hurdle_bps: float = 15.0
    ):
        self.horizons = horizons or HORIZONS
        self.cost_hurdle = cost_hurdle_bps * 1e-4  # convert bps to decimal

    def construct_forward_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes forward raw execution returns for each horizon H.
        Masks out cross-day observations to strictly enforce intraday square-off.
        """
        df = df.copy().sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)
        df["date"] = pd.to_datetime(df["timestamp"]).dt.date

        labeled_symbols = []
        for sym, sym_df in df.groupby("symbol", group_keys=False):
            sym_df = sym_df.copy().sort_values(by="timestamp").reset_index(drop=True)

            for h in self.horizons:
                h_name = f"{h * 5}m"  # 1 -> 5m, 2 -> 10m, 3 -> 15m
                future_raw_close = sym_df["raw_close"].shift(-h)
                future_date = sym_df["date"].shift(-h)

                # Intraday constraint: future bar must be in the exact same trading session
                is_same_session = sym_df["date"] == future_date

                # Raw Forward Log Return
                forward_ret = np.where(
                    is_same_session & (sym_df["raw_close"] > 0) & (future_raw_close > 0),
                    np.log(future_raw_close / sym_df["raw_close"]),
                    np.nan
                )
                sym_df[f"target_return_{h_name}"] = forward_ret

                # Directional Hurdle Target (-1, 0, +1)
                # +1 if forward return exceeds cost hurdle, -1 if below negative hurdle, else 0
                sym_df[f"target_direction_{h_name}"] = np.where(
                    np.isnan(forward_ret),
                    np.nan,
                    np.where(
                        forward_ret > self.cost_hurdle,
                        1,
                        np.where(forward_ret < -self.cost_hurdle, -1, 0)
                    )
                )

            labeled_symbols.append(sym_df)

        result_df = pd.concat(labeled_symbols, ignore_index=True)
        result_df = result_df.drop(columns=["date"], errors="ignore")
        return result_df.sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)
