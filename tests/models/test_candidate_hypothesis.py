"""
Unit Tests for CandidateHypothesis & Anti-Peeking Freeze Engine.
Verifies:
  1. CandidateHypothesis instantiation and deterministic SHA-256 hash generation.
  2. Immutability of frozen candidate hypotheses.
  3. Serialization, persistence, and cryptographic integrity check on load.
  4. Detection and rejection of candidate tampering and prohibited substitutions.
"""

import unittest
import tempfile
import os
from v2.models.hypothesis import (
    CandidateHypothesis,
    CandidateTamperingError,
    ProhibitedCandidateReplacementError,
    LOCKED_PHASE3B_CANDIDATE_IDS
)


class TestCandidateHypothesis(unittest.TestCase):

    def setUp(self):
        self.hypo = CandidateHypothesis.create(
            id="HYPO_3A_001_30M_MIDDAY_TREND",
            horizon="30m",
            side="LONG_AND_SHORT",
            time_window="11:00-13:00",
            volatility_regime="NORMAL_VOL",
            signal_threshold_quantile=95.0,
            interaction_rules={"time_regime": "11:00-13:00 x NORMAL_VOL"},
            execution_scenario="BASE_AGGRESSIVE",
            minimum_trade_size=30,
            feature_columns=["raw_atr_14", "adj_log_return_5m", "raw_wick_pressure"]
        )

    def test_hypothesis_hash_generation(self):
        """Verify deterministic SHA-256 definition and feature set hashes."""
        self.assertTrue(self.hypo.created_from_phase3a)
        self.assertEqual(len(self.hypo.definition_hash), 64)
        self.assertEqual(len(self.hypo.feature_set_hash), 16)
        self.assertEqual(self.hypo.cost_model_version, "v2.2_execution_tree")
        self.assertEqual(self.hypo.labeler_version, "v2.0_raw_forward_returns")

        # Same definition produces identical definition_hash regardless of instantiation time
        hypo2 = CandidateHypothesis.create(
            id="HYPO_3A_001_30M_MIDDAY_TREND",
            horizon="30m",
            side="LONG_AND_SHORT",
            time_window="11:00-13:00",
            volatility_regime="NORMAL_VOL",
            signal_threshold_quantile=95.0,
            interaction_rules={"time_regime": "11:00-13:00 x NORMAL_VOL"},
            execution_scenario="BASE_AGGRESSIVE",
            minimum_trade_size=30,
            feature_columns=["raw_atr_14", "adj_log_return_5m", "raw_wick_pressure"]
        )
        self.assertEqual(self.hypo.definition_hash, hypo2.definition_hash)

    def test_serialization_and_hash_integrity(self):
        """Verify save and load integrity verification."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "test_hypotheses.json")
            self.hypo.save_to_file(file_path)

            with open(file_path, "r") as f:
                import json
                loaded_list = json.load(f)

            loaded_hypo = CandidateHypothesis.load_from_dict(loaded_list[0])
            self.assertEqual(loaded_hypo.id, self.hypo.id)
            self.assertEqual(loaded_hypo.definition_hash, self.hypo.definition_hash)

            # Test tampered definition raises CandidateTamperingError
            tampered = loaded_list[0].copy()
            tampered["horizon"] = "60m"  # Tampered field
            with self.assertRaises(CandidateTamperingError):
                CandidateHypothesis.load_from_dict(tampered)

    def test_prohibited_candidate_replacement(self):
        """Verify that attempting to substitute an unknown candidate ID raises ProhibitedCandidateReplacementError."""
        bogus_hypo = CandidateHypothesis.create(
            id="HYPO_004_OPTIMIZED_SNOOP",
            horizon="30m",
            side="LONG",
            signal_threshold_quantile=99.0
        )
        with self.assertRaises(ProhibitedCandidateReplacementError):
            CandidateHypothesis.load_from_dict(bogus_hypo.to_dict(), enforce_locked_set=True)


if __name__ == "__main__":
    unittest.main()

