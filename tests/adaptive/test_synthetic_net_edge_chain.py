"""
AlphaNSE V3 — Synthetic Rupee Net-Edge Chain Verification Test.
Verifies the end-to-end economic gating chain:
  Model prediction
        ↓
  predicted 60m return
        ↓
  affordable whole-share quantity
        ↓
  gross expected ₹
        ↓
  brokerage + STT + exchange + GST + stamp + SEBI
        ↓
  spread + slippage + impact
        ↓
  expected net ₹
        ↓
  ₹0.80 hurdle
        ↓
  TRADE / HOLD

Also tests exact boundary conditions:
  expected net = ₹0.79 → HOLD
  expected net = ₹0.80 → TRADE (>= rule)
  expected net = ₹0.81 → TRADE
"""

import sys
import os
import unittest
import pandas as pd
import numpy as np

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from v3.adaptive.opportunity_engine_v3 import OpportunityEngineV3, RankedOpportunityV3
from v2.risk.dynamic_cost_model import DynamicCostModel, ExecutionMode
from v2.risk.cost_engine import IndiaCostEngine


class TestSyntheticNetEdgeChain(unittest.TestCase):
    """Verifies the exact Rupee Net-Edge evaluation chain and ₹0.80 hurdle boundary."""

    def setUp(self):
        self.cost_model = DynamicCostModel(base_half_spread_bps=1.0, base_slippage_bps=2.0)
        self.engine = OpportunityEngineV3(
            min_net_edge_rupees=0.80,
            min_net_edge_bps=0.0,
            min_predicted_return_bps=6.0,
            min_bar_volume=1000.0,
            max_capital_pct_per_trade=0.95,
            cost_model=self.cost_model
        )
        self.capital = 5000.0
        self.price = 500.0
        self.bar_volume = 50000.0

    def test_single_profitable_opportunity_full_chain(self):
        """
        Traces every link of the economic calculation chain for a high-conviction
        synthetic opportunity:
        Price = ₹500, Predicted 60m return = +25.0 bps, Capital = ₹5,000.
        """
        predicted_bps = 25.0  # +25.0 bps prediction

        # 1. Sizing: affordable whole-share quantity
        allocatable_capital = self.capital * 0.95  # ₹4,750
        expected_qty = int(allocatable_capital / self.price)  # 9 shares
        expected_notional = expected_qty * self.price  # ₹4,500

        self.assertEqual(expected_qty, 9)
        self.assertEqual(expected_notional, 4500.0)

        # 2. Gross expected ₹
        expected_gross_rupees = expected_notional * (predicted_bps / 10000.0)  # ₹11.25
        self.assertAlmostEqual(expected_gross_rupees, 11.25, places=2)

        # 3. Dynamic friction breakdown
        cost_detail = self.cost_model.compute_trade_cost(
            price=self.price,
            quantity=expected_qty,
            bar_volume=self.bar_volume,
            execution_mode=ExecutionMode.AGGRESSIVE
        )

        statutory_rupees = cost_detail.statutory_cost_rupees
        spread_bps = cost_detail.spread_bps
        slippage_bps = cost_detail.slippage_bps
        total_cost_rupees = cost_detail.total_cost_rupees
        total_cost_bps = cost_detail.total_cost_bps

        # Statutory detail check via IndiaCostEngine
        stat_breakdown = self.cost_model.cost_engine.calculate_roundtrip_cost(
            capital=expected_notional,
            gross_return=predicted_bps / 10000.0
        )

        # 4. Expected Net ₹
        expected_net_rupees = expected_gross_rupees - total_cost_rupees
        expected_net_bps = predicted_bps - total_cost_bps

        # 5. Opportunity Engine evaluation
        opp = self.engine.evaluate_symbol_ticket(
            symbol="SYNTH_PROFITABLE.NS",
            price=self.price,
            predicted_bps=predicted_bps,
            available_capital=self.capital,
            bar_volume=self.bar_volume
        )

        stat_total = stat_breakdown.fixed_or_capped_cost + stat_breakdown.proportional_statutory_cost

        # Print full telemetry trace
        print("\n" + "=" * 70)
        print("  SYNTHETIC PROFITABLE OPPORTUNITY — ECONOMIC CHAIN VERIFICATION")
        print("=" * 70)
        print(f"  Model Prediction (60m):             +{predicted_bps:.2f} bps")
        print(f"  Price per Share:                    ₹{self.price:.2f}")
        print(f"  Available Capital:                  ₹{self.capital:.2f}")
        print(f"  Max Allocation (95%):               ₹{allocatable_capital:.2f}")
        print(f"  Affordable Whole Shares:            {opp.quantity} shares")
        print(f"  Traded Notional:                    ₹{opp.notional:.2f}")
        print(f"  Gross Expected Return (₹):          ₹{opp.expected_gross_rupees:.2f}")
        print("-" * 70)
        print(f"  Brokerage (Zerodha):                ₹{stat_breakdown.brokerage:.2f}")
        print(f"  STT (0.025% sell side):             ₹{stat_breakdown.stt:.2f}")
        print(f"  Exchange Turnover (NSE):            ₹{stat_breakdown.exchange_charges:.2f}")
        print(f"  SEBI Charges:                       ₹{stat_breakdown.sebi_fees:.4f}")
        print(f"  Stamp Duty (0.003% buy side):       ₹{stat_breakdown.stamp_duty:.2f}")
        print(f"  GST (18% on fees):                  ₹{stat_breakdown.gst:.2f}")
        print(f"  Total Statutory Fees:               ₹{stat_total:.2f}")
        print(f"  Spread + Slippage Friction:         ₹{total_cost_rupees - stat_total:.2f}")
        print(f"  Total Roundtrip Friction:           ₹{opp.expected_cost_rupees:.2f} ({opp.expected_cost_bps:.1f} bps)")
        print("-" * 70)
        print(f"  Expected Net Return (₹):            ₹{opp.expected_net_rupees:.2f} ({opp.expected_net_bps:.1f} bps)")
        print(f"  Hurdle Requirement:                 ≥ ₹{self.engine.min_net_edge_rupees:.2f} (and > 0 bps)")
        print(f"  Decision Verdict:                   {'TRADE (VIABLE)' if opp.is_viable else 'HOLD CASH'}")
        print("=" * 70)

        # Assertions
        self.assertTrue(opp.is_viable, "Synthetic profitable opportunity MUST clear the gate")
        self.assertEqual(opp.quantity, 9)
        self.assertEqual(opp.notional, 4500.0)
        self.assertAlmostEqual(opp.expected_gross_rupees, round(expected_gross_rupees, 2), places=2)
        self.assertAlmostEqual(opp.expected_cost_rupees, round(total_cost_rupees, 2), places=2)
        self.assertAlmostEqual(opp.expected_net_rupees, round(expected_net_rupees, 2), places=2)
        self.assertGreaterEqual(opp.expected_net_rupees, 0.80)
        self.assertIsNone(opp.reject_reason)

    def test_hurdle_boundary_conditions_079_080_081(self):
        """
        Tests the exact boundary around the ₹0.80 hurdle:
          expected net = ₹0.79 → HOLD CASH (is_viable=False)
          expected net = ₹0.80 → TRADE (is_viable=True)
          expected net = ₹0.81 → TRADE (is_viable=True)
        """
        qty = 9
        notional = 4500.0

        cost_detail = self.cost_model.compute_trade_cost(
            price=self.price,
            quantity=qty,
            bar_volume=self.bar_volume,
            execution_mode=ExecutionMode.AGGRESSIVE
        )
        total_cost_rupees = cost_detail.total_cost_rupees  # exact friction in ₹

        # Case A: expected net = ₹0.79
        # expected_gross = total_cost + 0.79
        gross_079 = total_cost_rupees + 0.79
        pred_bps_079 = (gross_079 / notional) * 10000.0

        opp_079 = self.engine.evaluate_symbol_ticket(
            symbol="SYNTH_079.NS",
            price=self.price,
            predicted_bps=pred_bps_079,
            available_capital=self.capital,
            bar_volume=self.bar_volume
        )

        # Case B: expected net = ₹0.80
        gross_080 = total_cost_rupees + 0.80
        pred_bps_080 = (gross_080 / notional) * 10000.0

        opp_080 = self.engine.evaluate_symbol_ticket(
            symbol="SYNTH_080.NS",
            price=self.price,
            predicted_bps=pred_bps_080,
            available_capital=self.capital,
            bar_volume=self.bar_volume
        )

        # Case C: expected net = ₹0.81
        gross_081 = total_cost_rupees + 0.81
        pred_bps_081 = (gross_081 / notional) * 10000.0

        opp_081 = self.engine.evaluate_symbol_ticket(
            symbol="SYNTH_081.NS",
            price=self.price,
            predicted_bps=pred_bps_081,
            available_capital=self.capital,
            bar_volume=self.bar_volume
        )

        print("\n" + "=" * 70)
        print("  HURDLE BOUNDARY TEST RESULTS (₹0.79 vs ₹0.80 vs ₹0.81)")
        print("=" * 70)
        print(f"  Target: ₹0.79 | Calculated Net: ₹{opp_079.expected_net_rupees:.2f} | Decision: {'TRADE' if opp_079.is_viable else 'HOLD'} | Reason: {opp_079.reject_reason}")
        print(f"  Target: ₹0.80 | Calculated Net: ₹{opp_080.expected_net_rupees:.2f} | Decision: {'TRADE' if opp_080.is_viable else 'HOLD'} | Reason: {opp_080.reject_reason}")
        print(f"  Target: ₹0.81 | Calculated Net: ₹{opp_081.expected_net_rupees:.2f} | Decision: {'TRADE' if opp_081.is_viable else 'HOLD'} | Reason: {opp_081.reject_reason}")
        print("=" * 70)

        # Verification:
        # At ₹0.79: MUST be HOLD CASH (cleared_rupee_hurdle is False)
        self.assertFalse(opp_079.is_viable, "₹0.79 expected net must produce HOLD")
        self.assertIn("INSUFFICIENT_NET_INR", opp_079.reject_reason)

        # At ₹0.80: MUST be TRADE (0.80 >= 0.80 is True, net_bps clears 5 bps hurdle)
        self.assertTrue(opp_080.is_viable, "₹0.80 expected net must produce TRADE under >= rule")
        self.assertIsNone(opp_080.reject_reason)

        # At ₹0.81: MUST be TRADE (0.81 >= 0.80 is True, net_bps clears 5 bps hurdle)
        self.assertTrue(opp_081.is_viable, "₹0.81 expected net must produce TRADE")
        self.assertIsNone(opp_081.reject_reason)


if __name__ == "__main__":
    unittest.main()
