"""
Tests for ParquetPipeline in AlphaNSE V2.
Validates raw chunk processing, column standardizations, session boundaries,
price geometry corrections, and manifest generation.
"""

import os
import shutil
import tempfile
import unittest
import pandas as pd
import numpy as np
from datetime import datetime
from v2.data.storage.parquet_pipeline import ParquetPipeline, STANDARD_COLUMNS


class TestDataPipeline(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.raw_dir = os.path.join(self.temp_dir, "raw")
        self.norm_dir = os.path.join(self.temp_dir, "normalized")
        self.adj_dir = os.path.join(self.temp_dir, "adjusted")
        self.meta_dir = os.path.join(self.temp_dir, "metadata")
        for d in [self.raw_dir, self.norm_dir, self.adj_dir, self.meta_dir]:
            os.makedirs(d, exist_ok=True)

        self.pipeline = ParquetPipeline(
            raw_storage_dir=self.raw_dir,
            normalized_storage_dir=self.norm_dir,
            adjusted_storage_dir=self.adj_dir,
            metadata_dir=self.meta_dir
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_process_raw_chunk_columns_and_filtering(self):
        # Create dummy raw chunk with extra columns and out-of-bounds timestamps
        data = {
            "Datetime": [
                pd.Timestamp("2026-09-18 09:10:00+05:30"),  # Pre-market: should be filtered
                pd.Timestamp("2026-09-18 09:15:00+05:30"),  # In-session (first 5m bar): kept
                pd.Timestamp("2026-09-18 12:00:00+05:30"),  # In-session: kept
                pd.Timestamp("2026-09-18 15:25:00+05:30"),  # In-session (last 5m bar): kept
                pd.Timestamp("2026-09-18 15:30:00+05:30"),  # Post-market: should be filtered for 5m
                pd.Timestamp("2026-09-19 10:00:00+05:30"),  # Saturday: should be filtered
            ],
            "Open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            "High": [101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
            "Low": [99.0, 100.0, 101.0, 102.0, 103.0, 104.0],
            "Close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5],
            "Volume": [1000, 2000, 3000, 4000, 5000, 6000],
            "Extra_Col": [1, 2, 3, 4, 5, 6]
        }
        raw_df = pd.DataFrame(data)
        chunk_path = os.path.join(self.raw_dir, "sample_chunk.parquet")
        raw_df.to_parquet(chunk_path, index=False)

        clean_df = self.pipeline.process_raw_chunk(chunk_path, symbol="TEST.NS", interval="5m")

        # Verify standard columns
        self.assertEqual(list(clean_df.columns), STANDARD_COLUMNS)
        self.assertTrue((clean_df["symbol"] == "TEST.NS").all())

        # Verify filtering (only the 3 in-session bars on Friday survive)
        self.assertEqual(len(clean_df), 3)
        expected_times = [
            pd.Timestamp("2026-09-18 09:15:00+05:30"),
            pd.Timestamp("2026-09-18 12:00:00+05:30"),
            pd.Timestamp("2026-09-18 15:25:00+05:30"),
        ]
        for actual_t, exp_t in zip(clean_df["timestamp"], expected_times):
            self.assertEqual(actual_t, exp_t)

    def test_process_raw_chunk_price_geometry_snapping(self):
        # Ingest float precision mismatch (e.g. open slightly higher than high)
        data = {
            "Datetime": [
                pd.Timestamp("2026-09-18 09:15:00+05:30"),
                pd.Timestamp("2026-09-18 09:20:00+05:30"),
            ],
            "Open": [100.0001, 102.0],
            "High": [100.0000, 103.0],  # high is slightly below open
            "Low": [99.0, 102.0001],    # low is slightly above close
            "Close": [99.5, 102.0],
            "Volume": [1000, 2000]
        }
        raw_df = pd.DataFrame(data)
        chunk_path = os.path.join(self.raw_dir, "geometry_chunk.parquet")
        raw_df.to_parquet(chunk_path, index=False)

        clean_df = self.pipeline.process_raw_chunk(chunk_path, symbol="GEOM.NS", interval="5m")

        self.assertEqual(len(clean_df), 2)
        # Check that high was snapped to at least open
        row0 = clean_df.iloc[0]
        self.assertGreaterEqual(row0["high"], row0["open"])
        # Check that low was snapped to at most close
        row1 = clean_df.iloc[1]
        self.assertLessEqual(row1["low"], row1["close"])

    def test_manifest_generation(self):
        sample_df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2026-09-18 09:15:00+05:30"), pd.Timestamp("2026-09-18 09:20:00+05:30")],
            "symbol": ["TEST.NS", "TEST.NS"],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [100.0, 200.0]
        })
        target_path = os.path.join(self.norm_dir, "test_output.parquet")
        sample_df.to_parquet(target_path, index=False)

        manifest = self.pipeline.generate_manifest([target_path])

        self.assertIn("files", manifest)
        self.assertIn("test_output.parquet", manifest["files"])
        file_info = manifest["files"]["test_output.parquet"]
        self.assertEqual(file_info["total_rows"], 2)
        self.assertIn("sha256", file_info)
        self.assertEqual(len(file_info["sha256"]), 64)
        self.assertEqual(file_info["unique_symbols"], ["TEST.NS"])

    def test_historical_replay_adapter_from_parquet(self):
        from v2.data.adapters.replay_adapter import HistoricalReplayAdapter
        sample_df = pd.DataFrame({
            "timestamp": [
                pd.Timestamp("2026-09-18 09:15:00+05:30"),
                pd.Timestamp("2026-09-18 09:20:00+05:30"),
                pd.Timestamp("2026-09-18 09:25:00+05:30")
            ],
            "symbol": ["RELIANCE.NS", "RELIANCE.NS", "RELIANCE.NS"],
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [1000.0, 1500.0, 2000.0]
        })
        target_path = os.path.join(self.norm_dir, "sample_bars.parquet")
        sample_df.to_parquet(target_path, index=False)

        adapter = HistoricalReplayAdapter.from_parquet(target_path, symbols=["RELIANCE.NS"])
        self.assertTrue(adapter.has_next())
        bar1 = adapter.step()
        self.assertIsNotNone(bar1)
        self.assertEqual(bar1.symbol, "RELIANCE.NS")
        self.assertEqual(bar1.open, 100.0)
        self.assertEqual(bar1.close, 100.5)

        bar2 = adapter.step()
        self.assertEqual(bar2.close, 101.5)
        self.assertEqual(len(adapter.get_history("RELIANCE.NS", count=5)), 2)

    def test_corporate_action_adjustments_math(self):
        # Create dummy corporate actions
        actions_df = pd.DataFrame([
            {
                "symbol": "TESTDIV.NS",
                "action_type": "dividend",
                "ex_date": "2026-09-18",
                "value": 10.0,
                "recorded_at": "2026-09-19"
            }
        ])
        actions_path = os.path.join(self.meta_dir, "corporate_actions.parquet")
        actions_df.to_parquet(actions_path, index=False)

        # Create raw price series spanning 2 days
        raw_df = pd.DataFrame({
            "timestamp": [
                pd.Timestamp("2026-09-17 15:25:00+05:30"),  # Day before ex-date, close = 100.0
                pd.Timestamp("2026-09-18 09:15:00+05:30"),  # Ex-date, open = 90.0
            ],
            "symbol": ["TESTDIV.NS", "TESTDIV.NS"],
            "open": [100.0, 90.0],
            "high": [105.0, 95.0],
            "low": [95.0, 85.0],
            "close": [100.0, 92.0],
            "volume": [1000.0, 1200.0]
        })

        adj_df = self.pipeline.apply_corporate_action_adjustments(raw_df, actions_path)

        # Expected factor: (100.0 - 10.0) / 100.0 = 0.90
        # Row 0 (before ex-date) must be scaled by 0.90
        self.assertAlmostEqual(adj_df.iloc[0]["close"], 90.0, places=4)
        self.assertAlmostEqual(adj_df.iloc[0]["open"], 90.0, places=4)
        self.assertAlmostEqual(adj_df.iloc[0]["high"], 94.5, places=4)
        self.assertAlmostEqual(adj_df.iloc[0]["low"], 85.5, places=4)

        # Row 1 (on ex-date) remains unchanged
        self.assertEqual(adj_df.iloc[1]["close"], 92.0)
        self.assertEqual(adj_df.iloc[1]["open"], 90.0)

        # Raw != Adjusted on Day 1
        self.assertNotEqual(raw_df.iloc[0]["close"], adj_df.iloc[0]["close"])


if __name__ == "__main__":
    unittest.main()
