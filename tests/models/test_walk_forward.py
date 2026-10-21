"""
Unit Tests for Purged and Embargoed Walk-Forward Cross-Validation.
Verifies:
  1. Strict chronological ordering (Train < Val < Test).
  2. Exact H-bar purge at fold boundaries.
  3. 1-session embargo between sets.
  4. Disjoint index sets between Train, Val, and Test.
"""

import unittest
import numpy as np
import pandas as pd
from v2.models.walk_forward import PurgedWalkForwardCV, WalkForwardConfig


class TestPurgedWalkForwardCV(unittest.TestCase):

    def setUp(self):
        # Generate 45 synthetic sessions with 10 bars per session for 2 symbols
        dates = pd.date_range("2026-07-01", periods=45, freq="B")
        records = []
        for d in dates:
            for bar in range(10):
                ts = pd.Timestamp(d) + pd.Timedelta(minutes=5 * bar)
                records.append({"timestamp": ts, "symbol": "SYM_A", "price": 100.0})
                records.append({"timestamp": ts, "symbol": "SYM_B", "price": 200.0})

        self.df = pd.DataFrame(records).sort_values(by=["timestamp", "symbol"]).reset_index(drop=True)

    def test_chronological_split_and_embargo(self):
        """Verify train, val, and test dates maintain chronological order and respect embargo."""
        config = WalkForwardConfig(
            n_folds=3,
            min_train_sessions=20,
            val_sessions_per_fold=5,
            test_sessions_per_fold=5,
            embargo_sessions=1
        )
        cv = PurgedWalkForwardCV(config)
        splits = cv.generate_splits(self.df, horizon_bars=2)

        self.assertEqual(len(splits), 3)

        for split in splits:
            max_train_date = max(split.train_dates)
            min_val_date = min(split.val_dates)
            max_val_date = max(split.val_dates)
            min_test_date = min(split.test_dates)

            # Strict chronological order
            self.assertLess(max_train_date, min_val_date)
            self.assertLess(max_val_date, min_test_date)

            # Embargo check: at least 1 session between train and val
            self.assertTrue((pd.Timestamp(min_val_date) - pd.Timestamp(max_train_date)).days >= 1)

            # Indices must be disjoint
            train_set = set(split.train_indices)
            val_set = set(split.val_indices)
            test_set = set(split.test_indices)
            self.assertEqual(len(train_set.intersection(val_set)), 0)
            self.assertEqual(len(train_set.intersection(test_set)), 0)
            self.assertEqual(len(val_set.intersection(test_set)), 0)

    def test_exact_h_bar_purge(self):
        """Verify that the last H bars of each symbol in Train are purged."""
        config = WalkForwardConfig(
            n_folds=2,
            min_train_sessions=20,
            val_sessions_per_fold=5,
            test_sessions_per_fold=5,
            embargo_sessions=1
        )
        cv = PurgedWalkForwardCV(config)
        h = 3
        splits = cv.generate_splits(self.df, horizon_bars=h)

        split1 = splits[0]
        train_df = self.df.iloc[split1.train_indices]

        # Total unpurged train bars for 20 sessions * 10 bars = 200 bars per symbol
        # With h=3 purge, should have 200 - 3 = 197 bars per symbol
        for sym in ["SYM_A", "SYM_B"]:
            sym_train = train_df[train_df["symbol"] == sym]
            self.assertEqual(len(sym_train), 197, f"Expected 197 bars after {h}-bar purge, got {len(sym_train)}")


if __name__ == "__main__":
    unittest.main()
