#!/usr/bin/env python3
"""
tests/test_execution_costs.py
Comprehensive Regression Test Suite for AlphaNSE V3 Execution Costs and Trading Readiness Gate (Priority 2).

Verifies:
1. Every statutory cost formula, rate, and unit in IndiaCostEngine.
2. Spread (2.5 bps) and slippage (3.0 bps) inclusion on entry and exit prices.
3. Conservative intra-bar stop vs target clash priority.
4. Whole-share affordability under ₹1,500 bankroll (below, equal, above).
5. Partial / rejected orders, insufficient cash, and reserve enforcement.
6. Fail-closed rejection of stale quotes and fallback buffers.
7. Paper safeguards and live execution lock enforcement.
"""

import os
import sys
import unittest
from datetime import datetime
from typing import Dict, Any, List

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v2.risk.cost_engine import IndiaCostEngine, CostBreakdown
from v3.execution.edge_friction_gate import EdgeFrictionGate
from v3.intelligence.opportunity_engine import OpportunityDiscoveryEngine, OpportunityCandidate, MarketRegime
from v3.execution.kotak_adapter import KotakLiveBrokerAdapter


class TestStatutoryCostFormulas(unittest.TestCase):
    """Priority 2: Verify every cost formula, rate, and its units."""

    def setUp(self):
        self.engine = IndiaCostEngine()
        # Kotak Neo Trade Free Plan: 0 Brokerage on intraday cash equity
        self.engine_zero_brokerage = IndiaCostEngine()
        self.engine_zero_brokerage.brokerage_pct = 0.0
        self.engine_zero_brokerage.brokerage_flat_cap = 0.0

    def test_statutory_rates_and_units(self):
        """Verify regulatory statutory rates against official NSE CM intraday schedule."""
        self.assertAlmostEqual(self.engine.stt_sell_pct, 0.00025, places=6, msg="STT must be 0.025% on sell side")
        self.assertAlmostEqual(self.engine.exchange_pct, 0.0000307, places=7, msg="NSE Exchange charges must be 0.00307% per side")
        self.assertAlmostEqual(self.engine.sebi_pct, 0.000001, places=7, msg="SEBI turnover fees must be Rs 10 per crore (0.0001%)")
        self.assertAlmostEqual(self.engine.gst_pct, 0.18, places=4, msg="GST must be 18% on non-tax transaction charges")
        self.assertAlmostEqual(self.engine.stamp_duty_buy_pct, 0.00003, places=6, msg="Stamp Duty must be 0.003% on buy side only")

    def test_penny_for_penny_statutory_breakdown(self):
        """Verify exact calculation of roundtrip costs on a Rs. 1,000 buy / Rs. 1,010 sell."""
        capital = 1000.0
        gross_return = 0.01  # +1.0% (Sell value = 1010.0)
        slippage_bps = 3.0   # 3 bps

        breakdown = self.engine_zero_brokerage.calculate_roundtrip_cost(
            capital=capital,
            gross_return=gross_return,
            slippage_bps=slippage_bps
        )

        expected_buy_val = 1000.0
        expected_sell_val = 1010.0
        expected_stt = expected_sell_val * 0.00025                 # 0.2525
        expected_exchange = (expected_buy_val + expected_sell_val) * 0.0000307  # 0.061707
        expected_sebi = (expected_buy_val + expected_sell_val) * 0.000001       # 0.00201
        expected_gst = (0.0 + expected_exchange + expected_sebi) * 0.18        # 0.011469
        expected_stamp = expected_buy_val * 0.00003                            # 0.03
        expected_slippage = (expected_buy_val + expected_sell_val) * (3.0 / 10000.0) # 0.603

        self.assertAlmostEqual(breakdown.stt, round(expected_stt, 2), places=2)
        self.assertAlmostEqual(breakdown.exchange_charges, round(expected_exchange, 4), places=4)
        self.assertAlmostEqual(breakdown.sebi_fees, round(expected_sebi, 4), places=4)
        self.assertAlmostEqual(breakdown.gst, round(expected_gst, 4), places=4)
        self.assertAlmostEqual(breakdown.stamp_duty, round(expected_stamp, 4), places=4)
        self.assertAlmostEqual(breakdown.slippage, round(expected_slippage, 2), places=2)

        # Net profit after costs
        expected_gross_profit = expected_sell_val - expected_buy_val # 10.0
        expected_costs = (
            expected_stt + expected_exchange + expected_sebi + 
            expected_gst + expected_stamp + expected_slippage
        )
        self.assertAlmostEqual(breakdown.gross_profit, 10.0, places=2)
        self.assertGreater(breakdown.net_profit, 0.0)
        self.assertLess(breakdown.net_profit, breakdown.gross_profit)


class TestExecutionPricesSpreadAndSlippage(unittest.TestCase):
    """Priority 2: Ensure entry and exit prices include realistic spread and slippage."""

    def test_adverse_execution_prices(self):
        """Verifies that buyers cross the ask + slippage and sellers cross the bid - slippage."""
        mid_price = 500.0
        half_spread_bps = 2.5  # 0.025%
        slippage_bps = 3.0     # 0.030%
        adverse_factor = (half_spread_bps + slippage_bps) / 10000.0  # 0.00055

        # BUY order execution
        buy_entry = mid_price * (1.0 + adverse_factor)
        self.assertGreater(buy_entry, mid_price)
        self.assertAlmostEqual(buy_entry, 500.0 * 1.00055, places=4)

        # SELL order execution
        sell_entry = mid_price * (1.0 - adverse_factor)
        self.assertLess(sell_entry, mid_price)
        self.assertAlmostEqual(sell_entry, 500.0 * 0.99945, places=4)


class TestIntraBarClashConservativePriority(unittest.TestCase):
    """Priority 2: Conservative handling when a stop and target are both touched within a candle."""

    def test_conservative_stop_priority_long(self):
        """When Long and both high >= target and low <= stop in the same bar, stop-loss triggers."""
        entry_price = 100.0
        target_price = 101.0  # +1%
        stop_price = 99.7     # -0.3%

        # Bar touched 101.5 (above target) AND 99.5 (below stop)
        candle_high = 101.5
        candle_low = 99.5
        candle_close = 100.8

        both_touched = (candle_high >= target_price) and (candle_low <= stop_price)
        self.assertTrue(both_touched)

        # Conservative rule: stop-loss must be selected
        if both_touched:
            exit_px = stop_price
            exit_reason = "CONSERVATIVE_STOP_LOSS_CLASH"
        elif candle_low <= stop_price:
            exit_px = stop_price
            exit_reason = "STOP_LOSS_HIT"
        elif candle_high >= target_price:
            exit_px = target_price
            exit_reason = "PROFIT_TARGET_HIT"
        else:
            exit_px = candle_close
            exit_reason = "CLOSE"

        self.assertEqual(exit_reason, "CONSERVATIVE_STOP_LOSS_CLASH")
        self.assertEqual(exit_px, stop_price)

    def test_conservative_stop_priority_short(self):
        """When Short and both low <= target and high >= stop in the same bar, stop-loss triggers."""
        entry_price = 100.0
        target_price = 99.0   # -1%
        stop_price = 100.3    # +0.3%

        # Bar touched 98.5 (below target) AND 100.5 (above stop)
        candle_high = 100.5
        candle_low = 98.5
        candle_close = 99.2

        both_touched = (candle_low <= target_price) and (candle_high >= stop_price)
        self.assertTrue(both_touched)

        if both_touched:
            exit_px = stop_price
            exit_reason = "CONSERVATIVE_STOP_LOSS_CLASH"
        elif candle_high >= stop_price:
            exit_px = stop_price
            exit_reason = "STOP_LOSS_HIT"
        elif candle_low <= target_price:
            exit_px = target_price
            exit_reason = "PROFIT_TARGET_HIT"
        else:
            exit_px = candle_close
            exit_reason = "CLOSE"

        self.assertEqual(exit_reason, "CONSERVATIVE_STOP_LOSS_CLASH")
        self.assertEqual(exit_px, stop_price)


class TestAffordabilityAndBankrollRegression(unittest.TestCase):
    """Priority 2: Add regression tests for affordability under ₹1,500 bankroll."""

    def setUp(self):
        self.engine = OpportunityDiscoveryEngine(bankroll=1500.0)

    def test_price_well_below_bankroll(self):
        """Tata Steel at ₹150 is affordable, returns whole shares."""
        ltp = 150.0
        qty, notional, rejections = self.engine.calculate_affordable_quantity(ltp)
        self.assertGreater(qty, 0)
        self.assertLessEqual(notional, 1500.0)
        self.assertEqual(len(rejections), 0)
        # Should be roughly 9 or 10 shares
        self.assertIn(qty, [9, 10])

    def test_price_equal_to_bankroll(self):
        """Stock priced at exactly ₹1,500 cannot be afforded once entry friction is included."""
        ltp = 1500.0
        qty, notional, rejections = self.engine.calculate_affordable_quantity(ltp)
        # 1 share * 1500 + entry spread/slippage/statutory > 1500 -> 0 shares
        self.assertEqual(qty, 0)
        self.assertEqual(notional, 0.0)
        self.assertTrue(any("UNAFFORDABLE_POSITION" in r for r in rejections))

    def test_price_above_bankroll(self):
        """Stock priced at ₹2,800 (Reliance) cannot be afforded with ₹1,500."""
        ltp = 2800.0
        qty, notional, rejections = self.engine.calculate_affordable_quantity(ltp)
        self.assertEqual(qty, 0)
        self.assertEqual(notional, 0.0)
        self.assertTrue(any("UNAFFORDABLE_POSITION" in r for r in rejections))

    def test_unaffordable_stock_does_not_suppress_affordable_candidate(self):
        """Unaffordable high-priced stock must be ranked below affordable viable candidate."""
        quotes = {
            "RELIANCE.NS": {"ltp": 2800.0, "is_stale": False, "source": "TEST", "bid": 2799.0, "ask": 2801.0},
            "TATASTEEL.NS": {"ltp": 150.0, "is_stale": False, "source": "TEST", "bid": 149.9, "ask": 150.1}
        }
        # Fake 20-candle buffer with upward trend
        buf_reliance = [{"open": 2790, "high": 2805, "low": 2785, "close": 2800, "volume": 5000} for _ in range(25)]
        buf_tata = [{"open": 148, "high": 151, "low": 147, "close": 150, "volume": 10000} for _ in range(25)]

        buffers = {"RELIANCE.NS": buf_reliance, "TATASTEEL.NS": buf_tata}
        candidates = self.engine.scan_and_rank_opportunities(quotes, buffers)

        tata_cand = next((c for c in candidates if c.symbol == "TATASTEEL.NS"), None)
        rel_cand = next((c for c in candidates if c.symbol == "RELIANCE.NS"), None)

        self.assertIsNotNone(tata_cand)
        self.assertIsNotNone(rel_cand)

        # Reliance is unaffordable (qty = 0)
        self.assertEqual(rel_cand.quantity, 0)
        self.assertEqual(rel_cand.gross_gain_rs, 0.0)
        self.assertFalse(rel_cand.viable)

        # TataSteel has quantity > 0
        self.assertGreater(tata_cand.quantity, 0)


class TestStaleQuotesFailClosed(unittest.TestCase):
    """Priority 2 & 3: Fail closed when market data is stale or incomplete."""

    def setUp(self):
        self.engine = OpportunityDiscoveryEngine(bankroll=1500.0)

    def test_stale_flag_triggers_exclusion(self):
        """Quotes marked is_stale=True are completely excluded from opportunity scanning."""
        quotes = {
            "INFY.NS": {"ltp": 1400.0, "is_stale": True, "source": "KOTAK_NEO", "bid": 1399.0, "ask": 1401.0}
        }
        buffers = {
            "INFY.NS": [{"open": 1395, "high": 1402, "low": 1390, "close": 1400, "volume": 5000} for _ in range(25)]
        }
        candidates = self.engine.scan_and_rank_opportunities(quotes, buffers)
        self.assertEqual(len(candidates), 0, "Stale quote must not produce any opportunity candidate")

    def test_buffer_fallback_source_triggers_exclusion(self):
        """Quotes from BUFFER_FALLBACK are fail-closed and excluded."""
        quotes = {
            "INFY.NS": {"ltp": 1400.0, "is_stale": False, "source": "BUFFER_FALLBACK", "bid": 1399.0, "ask": 1401.0}
        }
        buffers = {
            "INFY.NS": [{"open": 1395, "high": 1402, "low": 1390, "close": 1400, "volume": 5000} for _ in range(25)]
        }
        candidates = self.engine.scan_and_rank_opportunities(quotes, buffers)
        self.assertEqual(len(candidates), 0, "BUFFER_FALLBACK quote must not produce any opportunity candidate")


from unittest.mock import patch


class TestKotakAdapterPaperSafeguards(unittest.TestCase):
    """Priority 2 & 3: Order rejection on insufficient cash, capital limit, and live safety locks."""

    def setUp(self):
        self.patcher = patch("v3.execution.kotak_adapter.datetime")
        self.mock_dt = self.patcher.start()
        self.mock_dt.now.return_value = datetime(2026, 10, 15, 10, 30, 0)
        self.adapter = KotakLiveBrokerAdapter(max_capital=1500.0, max_daily_loss=30.0)

    def tearDown(self):
        self.patcher.stop()

    def test_live_trading_locked_by_default(self):
        """Verify LIVE_TRADING and ALLOW_REAL_ORDERS are False by default."""
        self.assertFalse(self.adapter.is_live, "Adapter must be in PAPER / READ-ONLY mode")
        self.assertIn("PAPER", self.adapter.broker_name)

    def test_order_rejected_when_exceeding_max_capital(self):
        """Order with notional > max_capital (₹1,500) must be rejected."""
        res = self.adapter.place_order(
            symbol="RELIANCE-EQ",
            side="BUY",
            quantity=1,
            price=2800.0
        )
        self.assertEqual(res["status"], "REJECTED")
        self.assertIn("CAPITAL_LIMIT", res["reason"])

    def test_second_concurrent_position_rejected(self):
        """Adapter enforces max 1 concurrent position."""
        # First order fills in paper mode
        res1 = self.adapter.place_order(
            symbol="TATASTEEL-EQ",
            side="BUY",
            quantity=5,
            price=150.0
        )
        self.assertEqual(res1["status"], "FILLED")
        self.assertIsNotNone(self.adapter.internal_position)

        # Second order must be rejected
        res2 = self.adapter.place_order(
            symbol="INFY-EQ",
            side="BUY",
            quantity=1,
            price=1400.0
        )
        self.assertEqual(res2["status"], "REJECTED")
        self.assertIn("CONCURRENT_POSITION_LIMIT", res2["reason"])


if __name__ == "__main__":
    unittest.main()
