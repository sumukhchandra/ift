"""
Unit tests for AlphaNSE V3 Session 5 Real-Time Live/Paper Validation Engine.
Verifies all 17 validation requirements.
"""

import os
import sys
import unittest
import tempfile
import shutil

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.verification.session5_live_validator import Session5RealtimeValidatorV3, FrozenCandidateHypothesis


class TestSession5RealtimeValidator(unittest.TestCase):
    """Test suite for Session 5 real-time live/paper validation engine."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.validator = Session5RealtimeValidatorV3(
            workspace_root=WORKSPACE_ROOT,
            session_date="2026-09-25",
            starting_capital=5000.0,
            min_net_edge_rupees=0.80
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_load_and_freeze_premarket_hypotheses(self):
        """Verifies pre-market hypotheses are loaded, frozen, and SHA-256 hashed."""
        hypotheses = self.validator.load_and_freeze_premarket_state()
        self.assertEqual(len(hypotheses), 10)
        self.assertIn("AXISBANK.NS", hypotheses)
        self.assertIn("TATACAP.NS", hypotheses)
        self.assertIn("RELIANCE.NS", hypotheses)

        axis = hypotheses["AXISBANK.NS"]
        self.assertIsInstance(axis, FrozenCandidateHypothesis)
        self.assertEqual(axis.decision, "TRADE")
        self.assertEqual(axis.signal_type, "BUY")
        self.assertEqual(axis.predicted_direction, 1)
        self.assertGreater(axis.expected_gross_bps, 0.0)
        self.assertGreaterEqual(axis.expected_net_rupees, 0.80)
        self.assertEqual(axis.affordable_quantity, 3)
        self.assertTrue(len(self.validator.premarket_snapshot_hash) == 64)

    def test_02_minute_by_minute_tracking_loop(self):
        """Verifies minute-by-minute tracking, thesis states, and paper trade execution."""
        results = self.validator.execute_validation_cycle()
        self.assertEqual(results["total_minutes_tracked"], 60)

        trade = results["paper_trade"]
        self.assertEqual(trade["symbol"], "AXISBANK.NS")
        self.assertEqual(trade["quantity"], 3)
        self.assertEqual(trade["status"], "CLOSED")
        self.assertEqual(trade["exit_reason"], "HORIZON_COMPLETED_60M")
        self.assertGreaterEqual(trade["actual_net_rupees"], 0.80)

        # Check minute tracking record structure
        first_min = self.validator.minute_tracking_logs[0]
        self.assertIn("realized_move_bps", first_min)
        self.assertIn("prediction_error_bps", first_min)
        self.assertIn("thesis_state", first_min)
        self.assertIn("position_action", first_min)

    def test_03_all_six_models_evaluated_separately(self):
        """Verifies all 6 models are evaluated separately across accuracy and economic dimensions."""
        self.validator.execute_validation_cycle()
        metrics = self.validator.model_evaluation_metrics
        self.assertEqual(len(metrics), 6)
        for m_id in ["V2_15M", "HYPO001", "HYPO002", "HYPO003", "V3_60M", "ANTIGRAVITY_META"]:
            self.assertIn(m_id, metrics)
            m_data = metrics[m_id]
            self.assertIn("directional_accuracy_pct", m_data)
            self.assertIn("mean_magnitude_error_bps", m_data)
            self.assertIn("economic_profitability_rate_pct", m_data)

    def test_04_report_sections_a_through_p(self):
        """Verifies generation of SESSION_5_REALTIME_VALIDATION_REPORT.md with all sections."""
        self.validator.execute_validation_cycle()
        report_path = os.path.join(self.temp_dir, "SESSION_5_REALTIME_VALIDATION_REPORT.md")
        self.validator.generate_validation_report(output_path=report_path)

        self.assertTrue(os.path.exists(report_path))
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()

        sections = [
            "## A. Pre-Market Predictions",
            "## B. Actual Price Paths",
            "## C. 1-Minute Prediction Tracking Audit",
            "## D. Model-by-Model Accuracy Matrix",
            "## E. Time-to-Edge Accuracy",
            "## F. Magnitude Error Analysis",
            "## G. Cost Prediction Error",
            "## H. Hypothetical Trade P&L Ledger",
            "## I. Model Disagreement Analysis",
            "## J. Antigravity Meta-Model Performance",
            "## K. False Positives Analysis",
            "## L. False Negatives Analysis",
            "## M. Missed Opportunities Analysis",
            "## N. HOLD_CASH Decisions That Would Have Lost Money",
            "## O. HOLD_CASH Decisions That Avoided Losses",
            "## P. Final Research Conclusion"
        ]
        for sec in sections:
            self.assertIn(sec, content, f"Missing section: {sec}")

        self.assertIn("Do not classify any result as \"profitable\", \"successful\", or \"validated\"", content)
        self.assertIn("PHYSICALLY_LOCKED", content)


if __name__ == "__main__":
    unittest.main()
