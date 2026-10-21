"""
Unit Tests for Phase 3B Candidate Hypothesis Falsification Engine.
Verifies:
  1. Protocol Replay mode strictly prohibits emitting terminal PASS status.
  2. Candidate tampering detection raises CandidateTamperingError.
  3. Candidate replacement / substitution raises ProhibitedCandidateReplacementError.
  4. Restored 11-point Edge Gate correctly flags a 'less negative' result as FAIL.
  5. Catastrophic single fold loss strictly trips FAIL.
"""

import unittest
import numpy as np
import pandas as pd
from v2.models.hypothesis import (
    CandidateHypothesis,
    CandidateTamperingError,
    ProhibitedCandidateReplacementError,
    LOCKED_PHASE3B_CANDIDATE_IDS
)
from v2.models.phase3b_evaluator import (
    Phase3BEvaluator,
    ValidationMode,
    CandidateEvaluationMetrics
)


class TestPhase3BEvaluator(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        self.candidate = CandidateHypothesis.create(
            id="HYPO_3A_001_30M_MIDDAY_TREND",
            horizon="30m",
            side="LONG_AND_SHORT",
            time_window="11:00-13:00",
            volatility_regime="NORMAL_VOL",
            signal_threshold_quantile=95.0,
            interaction_rules={"time_regime": "11:00-13:00 x NORMAL_VOL"},
            execution_scenario="BASE_AGGRESSIVE",
            minimum_trade_size=30
        )

        # Generate synthetic evaluation dataset (1000 rows -> 50 trades at P95 >= 30 min_trades)
        n_rows = 1000
        dates = pd.date_range("2026-08-01", periods=20, freq="B").date
        records = []
        for i in range(n_rows):
            d = dates[i % len(dates)]
            fold = (i % 5) + 1
            records.append({
                "timestamp": pd.Timestamp(d) + pd.Timedelta(hours=11, minutes=(i % 12) * 5),
                "date": d,
                "symbol": "BAJFINANCE.NS",
                "horizon": "30m",
                "time_window": "11:00-13:00",
                "volatility_regime": "NORMAL_VOL",
                "pred_ridge": 0.0020 + (i * 1e-6) if i % 2 == 0 else -0.0020 - (i * 1e-6),
                "target_return": 0.0002 + (np.sin(i) * 1e-5),  # ~+2.0 bps gross with variance
                "fold": fold
            })
        self.df = pd.DataFrame(records)

    def test_protocol_replay_cannot_emit_pass(self):
        """Invariant: In PROTOCOL_REPLAY mode, terminal PASS is physically blocked."""
        evaluator = Phase3BEvaluator(mode=ValidationMode.PROTOCOL_REPLAY, bootstrap_iterations=50)
        res = evaluator.evaluate_candidate(self.candidate, self.df)

        # Even if all criteria passed, status can NEVER be 'PASS' in replay mode
        self.assertNotEqual(res.status, "PASS")
        self.assertIn(res.status, ["REPLAY_FAIL", "REPLAY_SURVIVED_FOR_UNSEEN_TEST"])

    def test_tampered_candidate_raises_error(self):
        """Invariant: Modifying any frozen field without hash match raises CandidateTamperingError."""
        d = self.candidate.to_dict()
        d["horizon"] = "60m"  # Tampered field
        with self.assertRaises(CandidateTamperingError):
            CandidateHypothesis.load_from_dict(d)

    def test_prohibited_candidate_substitution(self):
        """Invariant: Substituting an unauthorized hypothesis raises ProhibitedCandidateReplacementError."""
        bogus = CandidateHypothesis.create(
            id="HYPO_3A_004_CHERRY_PICKED",
            horizon="30m",
            side="LONG",
            signal_threshold_quantile=99.0
        )
        evaluator = Phase3BEvaluator(mode=ValidationMode.PROTOCOL_REPLAY, bootstrap_iterations=50)
        with self.assertRaises(ProhibitedCandidateReplacementError):
            evaluator.evaluate_candidate(bogus, self.df)

    def test_less_negative_is_still_fail(self):
        """Rule: A candidate with net return of -3.0 bps (improved from -14 bps) is strictly FAIL."""
        # Setup df where both long and short trades achieve +11.70 bps gross against 14.70 bps cost -> net = -3.00 bps
        df_sub = self.df.copy()
        # Directional alignment: longs predict positive returns, shorts predict negative returns
        df_sub["target_return"] = np.where(
            df_sub["pred_ridge"] > 0,
            0.00117 + (np.sin(np.arange(len(df_sub))) * 1e-6),
            -0.00117 - (np.sin(np.arange(len(df_sub))) * 1e-6)
        )

        evaluator = Phase3BEvaluator(mode=ValidationMode.FRESH_VALIDATION, bootstrap_iterations=50)
        res = evaluator.evaluate_candidate(self.candidate, df_sub)

        self.assertAlmostEqual(res.base_net_expectancy_bps, -3.00, delta=0.5)
        self.assertEqual(res.status, "FAIL")
        self.assertEqual(res.gate_verdict, "FAIL")
        self.assertFalse(res.criteria_evaluations["1. Mean Baseline Net Expectancy > 0"][0])

    def test_catastrophic_fold_failure(self):
        """Rule: A candidate with a fold losing worse than -scenario_cost fails criterion 5."""
        df_catastrophic = self.df.copy()
        # Set Fold 5 to suffer -30 bps loss
        df_catastrophic.loc[df_catastrophic["fold"] == 5, "target_return"] = -0.0020  # -20 bps gross -> -34.7 bps net

        evaluator = Phase3BEvaluator(mode=ValidationMode.FRESH_VALIDATION, bootstrap_iterations=50)
        res = evaluator.evaluate_candidate(self.candidate, df_catastrophic)

        self.assertEqual(res.status, "FAIL")
        self.assertFalse(res.criteria_evaluations["5. No Catastrophic Fold (Worst Fold >= -Cost)"][0])


if __name__ == "__main__":
    unittest.main()
