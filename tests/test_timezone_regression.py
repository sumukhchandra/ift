#!/usr/bin/env python3
"""
tests/test_timezone_regression.py
Regression tests for Timezone Consistency (Task 1):
1. IST timestamps (aware and naive) map accurately to session minutes.
2. UTC timestamps convert to IST without shifting or distortion.
3. Daylight-independent conversion: Asia/Kolkata is strictly UTC+05:30 year-round.
4. Session boundaries: Pre-market (08:45-09:14), market open (09:15), phases (0,1,2,3), market close (15:30), post-market (15:31+).
5. Existing datasets on disk are not silently shifted, clipped, or relabeled.
"""

import os
import sys
import unittest
import numpy as np
import pandas as pd

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from QA.models.one_min_predictor import OneMinPredictor


class TestTimezoneConsistency(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.predictor = OneMinPredictor()

    def _build_test_df(self, timestamps):
        n = len(timestamps)
        return pd.DataFrame({
            "timestamp": timestamps,
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.0] * n,
            "volume": [1000] * n,
            "symbol": "INFY"
        })

    def test_01_ist_aware_and_naive_timestamps(self):
        """Verifies IST timestamps (both timezone-aware and naive) produce exact identical time features."""
        # 09:15 IST, 12:00 IST, 15:30 IST
        ist_naive = pd.Series(["2026-10-15 09:15:00", "2026-10-15 12:00:00", "2026-10-15 15:30:00"])
        ist_aware = pd.Series(["2026-10-15 09:15:00+05:30", "2026-10-15 12:00:00+05:30", "2026-10-15 15:30:00+05:30"])

        df_naive = self._build_test_df(ist_naive)
        df_aware = self._build_test_df(ist_aware)

        feats_naive = self.predictor.extract_features_1m(df_naive)
        feats_aware = self.predictor.extract_features_1m(df_aware)

        # Minutes from open should be 0, 165, 375
        expected_sin = np.sin(2 * np.pi * np.array([0, 165, 375]) / 375.0)
        expected_cos = np.cos(2 * np.pi * np.array([0, 165, 375]) / 375.0)

        np.testing.assert_allclose(feats_naive["time_sin"].values, expected_sin, atol=1e-5)
        np.testing.assert_allclose(feats_naive["time_cos"].values, expected_cos, atol=1e-5)
        np.testing.assert_allclose(feats_aware["time_sin"].values, expected_sin, atol=1e-5)
        np.testing.assert_allclose(feats_aware["time_cos"].values, expected_cos, atol=1e-5)

        # Session phases: 0 (open rush), 2 (midday), 3 (close rush)
        self.assertEqual(list(feats_naive["session_phase"].values), [0.0, 2.0, 3.0])
        self.assertEqual(list(feats_aware["session_phase"].values), [0.0, 2.0, 3.0])

    def test_02_utc_timestamps_convert_identically_to_ist(self):
        """Verifies UTC timestamps convert to canonical IST without being clipped to 0 or shifted."""
        # 03:45 UTC = 09:15 IST (open)
        # 06:30 UTC = 12:00 IST (midday)
        # 10:00 UTC = 15:30 IST (close)
        utc_series = pd.Series(["2026-10-15 03:45:00+00:00", "2026-10-15 06:30:00+00:00", "2026-10-15 10:00:00+00:00"])
        ist_series = pd.Series(["2026-10-15 09:15:00+05:30", "2026-10-15 12:00:00+05:30", "2026-10-15 15:30:00+05:30"])

        df_utc = self._build_test_df(utc_series)
        df_ist = self._build_test_df(ist_series)

        feats_utc = self.predictor.extract_features_1m(df_utc)
        feats_ist = self.predictor.extract_features_1m(df_ist)

        np.testing.assert_allclose(feats_utc["time_sin"].values, feats_ist["time_sin"].values, atol=1e-6)
        np.testing.assert_allclose(feats_utc["time_cos"].values, feats_ist["time_cos"].values, atol=1e-6)
        self.assertEqual(list(feats_utc["session_phase"].values), list(feats_ist["session_phase"].values))

    def test_03_daylight_independent_conversion(self):
        """Verifies Asia/Kolkata maintains strict UTC+05:30 offset across summer and winter dates."""
        # Summer date (July 15) vs Winter date (January 15)
        summer_utc = pd.Series(["2026-07-15 03:45:00+00:00", "2026-07-15 10:00:00+00:00"])
        winter_utc = pd.Series(["2026-01-15 03:45:00+00:00", "2026-01-15 10:00:00+00:00"])

        df_summer = self._build_test_df(summer_utc)
        df_winter = self._build_test_df(winter_utc)

        feats_summer = self.predictor.extract_features_1m(df_summer)
        feats_winter = self.predictor.extract_features_1m(df_winter)

        # Both summer and winter 03:45 UTC must map to minute 0 (09:15 IST) and 10:00 UTC to minute 375 (15:30 IST)
        np.testing.assert_allclose(feats_summer["time_sin"].values, [0.0, 0.0], atol=1e-5)
        np.testing.assert_allclose(feats_winter["time_sin"].values, [0.0, 0.0], atol=1e-5)
        np.testing.assert_allclose(feats_summer["time_cos"].values, [1.0, 1.0], atol=1e-5)
        np.testing.assert_allclose(feats_winter["time_cos"].values, [1.0, 1.0], atol=1e-5)

    def test_04_session_boundaries_and_phases(self):
        """Verifies session boundaries: pre-market, open rush, morning, midday, close rush, post-market."""
        test_times = pd.Series([
            "2026-10-15 08:45:00+05:30",  # Pre-market (clipped to 0, phase 0)
            "2026-10-15 09:14:00+05:30",  # 1 min before open (clipped to 0, phase 0)
            "2026-10-15 09:15:00+05:30",  # Market open (min 0, phase 0)
            "2026-10-15 09:45:00+05:30",  # Open rush end (min 30, phase 0)
            "2026-10-15 09:46:00+05:30",  # Morning start (min 31, phase 1)
            "2026-10-15 11:15:00+05:30",  # Morning end (min 120, phase 1)
            "2026-10-15 11:16:00+05:30",  # Midday start (min 121, phase 2)
            "2026-10-15 13:15:00+05:30",  # Midday end (min 240, phase 2)
            "2026-10-15 13:16:00+05:30",  # Close rush start (min 241, phase 3)
            "2026-10-15 15:30:00+05:30",  # Market close (min 375, phase 3)
            "2026-10-15 15:45:00+05:30",  # Post-market (clipped to 375, phase 3)
        ])

        df = self._build_test_df(test_times)
        feats = self.predictor.extract_features_1m(df)

        expected_phases = [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 3.0]
        self.assertEqual(list(feats["session_phase"].values), expected_phases)

        # Pre-market must equal exact open (min 0)
        self.assertAlmostEqual(feats.loc[0, "time_sin"], feats.loc[2, "time_sin"], places=5)
        self.assertAlmostEqual(feats.loc[0, "time_cos"], feats.loc[2, "time_cos"], places=5)

        # Post-market must equal exact close (min 375)
        self.assertAlmostEqual(feats.loc[9, "time_sin"], feats.loc[10, "time_sin"], places=5)
        self.assertAlmostEqual(feats.loc[9, "time_cos"], feats.loc[10, "time_cos"], places=5)

    def test_05_existing_datasets_not_silently_shifted(self):
        """Verifies existing datasets on disk retain canonical 09:15 market open without corruption."""
        sample_path = os.path.join(WORKSPACE_ROOT, "QA", "data", "genuine_forward_oos_oct13_oct14.csv")
        self.assertTrue(os.path.exists(sample_path), f"Missing dataset: {sample_path}")

        df_raw = pd.read_csv(sample_path, nrows=50)
        self.assertIn("timestamp", df_raw.columns)

        # First candle must be 09:15:00 IST
        first_ts = df_raw["timestamp"].iloc[0]
        self.assertIn("09:15:00", str(first_ts))

        # Extract features and verify minutes_from_open starts at 0, NOT -330
        feats = self.predictor.extract_features_1m(df_raw)
        self.assertAlmostEqual(feats["time_sin"].iloc[0], 0.0, places=4)
        self.assertAlmostEqual(feats["time_cos"].iloc[0], 1.0, places=4)
        self.assertEqual(feats["session_phase"].iloc[0], 0.0)


if __name__ == "__main__":
    unittest.main()
