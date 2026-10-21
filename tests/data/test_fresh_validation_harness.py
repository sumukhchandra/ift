"""
Unit Tests for Fresh Session Ingestion & Cumulative Evidence Gate.
Verifies data quality validation, per-symbol missing bar rules,
and accumulation evidence gate requirements.
"""

import os
import unittest
import tempfile
import json
from datetime import date
import pandas as pd
from scripts.ingest_fresh_sessions import FreshSessionIngestionHarness


class TestFreshSessionHarness(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, "test_state.json")
        self.harness = FreshSessionIngestionHarness(
            fresh_dir=self.temp_dir,
            state_file=self.state_file,
            universe=["BAJFINANCE.NS", "RELIANCE.NS"]
        )

    def test_mock_session_generation_valid(self):
        """Verify generated mock session conforms to required schema and geometry."""
        df = self.harness.generate_mock_unseen_session(date(2026, 9, 21))
        self.assertFalse(df.empty)
        self.assertIn("symbol", df.columns)
        self.assertIn("timestamp", df.columns)
        self.assertIn("open", df.columns)
        self.assertIn("close", df.columns)

        passed, report = self.harness.validate_session_data_quality(df)
        self.assertTrue(passed, f"Validation failed: {report['reasons']}")
        self.assertTrue(report["geometry_passed"])
        self.assertEqual(report["duplicates_count"], 0)

    def test_rejects_symbol_exceeding_missing_threshold(self):
        """Verify that a session where one symbol has > 5% missing bars is rejected."""
        df = self.harness.generate_mock_unseen_session(date(2026, 9, 21))
        # Drop half the bars of RELIANCE.NS (leaving only ~37 bars, missing > 50%)
        rel_indices = df[df["symbol"] == "RELIANCE.NS"].index[:40]
        df_corrupt = df.drop(rel_indices)

        passed, report = self.harness.validate_session_data_quality(df_corrupt)
        self.assertFalse(passed)
        self.assertFalse(report["symbols_evaluated"]["RELIANCE.NS"]["passed"])
        self.assertIn("exceeds 5.0% threshold", str(report["reasons"]))

    def test_cumulative_evidence_gate(self):
        """
        Evidence gate must report INCONCLUSIVE_ACCUMULATING until at least 10 sessions are accumulated.
        """
        res_initial = self.harness.check_evidence_sufficiency()
        self.assertEqual(res_initial["status"], "INCONCLUSIVE_ACCUMULATING")
        self.assertFalse(res_initial["is_sufficient"])

        # Manually simulate 10 accumulated sessions
        self.harness.state["accumulated_sessions"] = [f"202609{i:02d}" for i in range(21, 31)]
        self.harness._save_state()

        res_10 = self.harness.check_evidence_sufficiency()
        self.assertEqual(res_10["status"], "SUFFICIENT_FOR_TERMINAL_GATE")
        self.assertTrue(res_10["is_sufficient"])


if __name__ == "__main__":
    unittest.main()
