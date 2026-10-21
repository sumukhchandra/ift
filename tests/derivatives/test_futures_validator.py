"""
Unit Tests for Futures Validator — Dual-Output Framework.
Validates Output A (sensitivity) vs Output B (signal transfer).
"""

import unittest
import pandas as pd
import numpy as np
from v2.derivatives.futures_validator import FuturesValidator
from v2.derivatives.futures_cost_model import FuturesExecutionStyle


class TestFuturesValidator(unittest.TestCase):

    def setUp(self):
        self.validator = FuturesValidator()

    def test_output_a_economic_sensitivity(self):
        """
        Tests Output A: Sensitivity of hypothetical +12.76 bps gross return
        across contract notionals (₹2.5L to ₹25L) and execution styles.
        """
        rows = self.validator.run_economic_sensitivity_analysis(
            hypothetical_gross_bps=12.76,
            notional_brackets=[250000.0, 1000000.0]
        )
        self.assertEqual(len(rows), 6)  # 2 brackets * 3 styles

        # Find 10L Aggressive
        r_10l_agg = next(r for r in rows if r.notional_inr == 1000000.0 and r.execution_style == "AGGRESSIVE")
        self.assertAlmostEqual(r_10l_agg.statutory_cost_bps, 6.13, places=1)
        self.assertGreater(r_10l_agg.total_friction_bps, 8.5)
        # Net return is +12.76 - 8.63 ~ +4.13 bps (much lower than naive +9.5 bps!)
        self.assertLess(r_10l_agg.theoretical_net_bps, 5.0)
        self.assertGreater(r_10l_agg.theoretical_net_bps, 3.5)

    def test_output_b_tatacap_rejection(self):
        """
        Tests Output B: Attempting signal transfer on TATACAP returns REJECTED_INELIGIBLE
        because TATACAP has no active F&O contract.
        """
        df_dummy = pd.DataFrame({
            "close": [800.0, 805.0],
            "pred": [0.0020, 0.0025],
            "target": [0.0015, 0.0020]
        })
        res = self.validator.run_signal_transfer_simulation(
            underlying="TATACAP",
            df_bars=df_dummy,
            cash_predictions_col="pred",
            cash_forward_returns_col="target"
        )
        self.assertEqual(res.gate_verdict, "REJECTED_INELIGIBLE")
        self.assertIn("NO active F&O contract", res.summary_disclaimer)


if __name__ == "__main__":
    unittest.main()
