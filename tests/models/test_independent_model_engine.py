"""
Unit tests for IndependentModelTradingEngine (Multi-Agent Sub-Portfolios).
"""

import os
import unittest
import tempfile
import shutil

from v3.models.independent_model_engine import IndependentModelTradingEngine
from v3.config.multimodel_config import ACTIVE_MODEL_SPECS


class TestIndependentModelTradingEngine(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.engine = IndependentModelTradingEngine(
            capital_per_model=5000.0,
            min_net_edge_rupees=0.80,
            max_positions_per_model=2
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_independent_execution_all_models(self):
        # Synthetic mock predictions for all active models
        mock_preds = {}
        for m_id in ACTIVE_MODEL_SPECS:
            mock_preds[m_id] = {
                "INFY.NS": {
                    "direction": 1,
                    "predicted_return_bps": 35.0,
                    "confidence": 0.85
                },
                "TATACAP.NS": {
                    "direction": 1,
                    "predicted_return_bps": 30.0,
                    "confidence": 0.82
                },
                "^NSEI": {
                    "direction": 1,
                    "predicted_return_bps": 22.0,
                    "confidence": 0.80
                },
                "AXISBANK.NS": {
                    "direction": -1 if m_id == "HYPO003" else 0,
                    "predicted_return_bps": -25.0 if m_id == "HYPO003" else 0.0,
                    "confidence": 0.70
                }
            }

        res = self.engine.run_session_tournament(
            session_date="2026-09-28",
            predictions_by_model=mock_preds,
            artifacts_output_dir=self.temp_dir
        )

        self.assertIn("leaderboard", res)
        self.assertEqual(len(res["leaderboard"]), len(ACTIVE_MODEL_SPECS))

        # Check files created on disk
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "MODEL_INDEPENDENT_LEADERBOARD.json")))
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "MODEL_INDEPENDENT_LEADERBOARD.md")))

        for m_id in ACTIVE_MODEL_SPECS:
            m_path = os.path.join(self.temp_dir, f"INDIVIDUAL_TRADES_{m_id}.json")
            self.assertTrue(os.path.exists(m_path), f"Missing trade file for {m_id}")

        # Check rankings
        ranks = [m["rank"] for m in res["leaderboard"]]
        self.assertEqual(ranks, list(range(1, len(ACTIVE_MODEL_SPECS) + 1)))

    def test_economic_hurdle_blocks_sub_hurdle(self):
        # If expected return is negligible, model trades 0 and preserves cash
        mock_preds = {
            "V2_15M": {
                "INFY.NS": {
                    "direction": 1,
                    "predicted_return_bps": 1.0,  # ~1 bps return on ₹2,500 = ₹0.25 gross, below friction
                    "confidence": 0.50
                }
            }
        }
        res = self.engine.run_session_tournament(
            session_date="2026-09-28",
            predictions_by_model=mock_preds,
            artifacts_output_dir=self.temp_dir
        )
        v2_card = next(m for m in res["leaderboard"] if m["model_id"] == "V2_15M")
        self.assertEqual(v2_card["total_trades"], 0)
        self.assertEqual(v2_card["net_pnl_rupees"], 0.0)
        self.assertEqual(v2_card["ending_capital"], 5000.0)


if __name__ == "__main__":
    unittest.main()
