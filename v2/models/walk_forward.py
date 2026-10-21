"""
Purged & Embargoed Walk-Forward Cross-Validation Engine for AlphaNSE V2.
Enforces:
  1. Strict temporal chronological progression (Train -> Val -> Test).
  2. Exact label horizon purging (H bars purged before boundaries to prevent label leakage).
  3. Inter-session embargoing (1 full session post-training/validation to eliminate serial correlation).
  4. 'No Test Peeking' invariant: Model, scalers, calibration, and thresholds are fit on Train/Val
     and completely frozen before out-of-sample Test evaluation.
"""

import logging
from typing import List, Dict, Tuple, Iterator, NamedTuple, Optional
from dataclasses import dataclass
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FoldSplit(NamedTuple):
    fold_idx: int
    train_dates: List[object]
    val_dates: List[object]
    test_dates: List[object]
    train_indices: np.ndarray
    val_indices: np.ndarray
    test_indices: np.ndarray


@dataclass
class WalkForwardConfig:
    n_folds: int = 5
    min_train_sessions: int = 25
    val_sessions_per_fold: int = 7
    test_sessions_per_fold: int = 7
    embargo_sessions: int = 1


class PurgedWalkForwardCV:
    """
    Generates expanding purged and embargoed walk-forward splits across trading sessions.
    """

    def __init__(
        self,
        config: Optional[WalkForwardConfig] = None
    ):
        self.config = config or WalkForwardConfig()

    def generate_splits(
        self,
        df: pd.DataFrame,
        horizon_bars: int = 1
    ) -> List[FoldSplit]:
        """
        Constructs expanding walk-forward folds with exact H-bar purging and session embargoing.
        df must contain 'timestamp' and 'symbol'.
        """
        df = df.copy()
        df["date"] = pd.to_datetime(df["timestamp"]).dt.date
        unique_dates = sorted(df["date"].unique().tolist())
        n_sessions = len(unique_dates)

        if n_sessions < (self.config.min_train_sessions + self.config.val_sessions_per_fold + self.config.test_sessions_per_fold):
            raise ValueError(
                f"Insufficient sessions ({n_sessions}) for walk-forward splits with min_train={self.config.min_train_sessions}."
            )

        splits: List[FoldSplit] = []
        val_size = self.config.val_sessions_per_fold
        test_size = self.config.test_sessions_per_fold
        total_eval_sessions = val_size + test_size

        # Determine step size between folds
        available_steps = n_sessions - (self.config.min_train_sessions + total_eval_sessions)
        step = max(1, available_steps // (self.config.n_folds - 1)) if self.config.n_folds > 1 else 1

        for f in range(self.config.n_folds):
            train_end = self.config.min_train_sessions + (f * step)
            val_start = train_end + self.config.embargo_sessions  # embargo post-train
            val_end = val_start + val_size
            test_start = val_end + self.config.embargo_sessions  # embargo post-val
            test_end = min(n_sessions, test_start + test_size)

            if test_start >= n_sessions:
                break

            train_dates = unique_dates[:train_end]
            val_dates = unique_dates[val_start:val_end]
            test_dates = unique_dates[test_start:test_end]

            # Collect raw index masks
            train_mask = df["date"].isin(train_dates)
            val_mask = df["date"].isin(val_dates)
            test_mask = df["date"].isin(test_dates)

            # --- EXACT H-BAR PURGING ---
            # Purge the last H bars of each symbol in Train so their forward label window
            # does not peek into the validation period
            train_indices = []
            for sym, s_df in df[train_mask].groupby("symbol"):
                idx = s_df.index.values
                if len(idx) > horizon_bars:
                    train_indices.extend(idx[:-horizon_bars])
                else:
                    train_indices.extend(idx)

            val_indices = []
            for sym, s_df in df[val_mask].groupby("symbol"):
                idx = s_df.index.values
                if len(idx) > horizon_bars:
                    val_indices.extend(idx[:-horizon_bars])
                else:
                    val_indices.extend(idx)

            test_indices = df[test_mask].index.values

            splits.append(FoldSplit(
                fold_idx=f + 1,
                train_dates=train_dates,
                val_dates=val_dates,
                test_dates=test_dates,
                train_indices=np.array(sorted(train_indices)),
                val_indices=np.array(sorted(val_indices)),
                test_indices=test_indices
            ))

        logger.info(f"Generated {len(splits)} purged & embargoed walk-forward folds.")
        return splits
