"""
Unit and Integration Tests for AlphaNSE V3 Multi-Stock Portfolio Basket Optimization Engine.
Verifies all 10 core architectural and portfolio optimization requirements:

1. 1-stock basket can be selected when genuinely superior after costs.
2. 2-stock basket can be selected when multi-stock diversification / sizing is superior.
3. 3+ stock basket can be selected when multiple stocks clear the economic hurdle.
4. Infeasible baskets are strictly rejected (cannot afford 1 share, exceeds budget).
5. Capital constraint & minimum cash buffer are strictly respected.
6. Whole-share integer sizing constraint is strictly respected (no fractional shares).
7. Economic cost hurdle (>= ₹0.80 net and > 0 bps) is strictly enforced per position.
8. Risk limits, correlation, and sector concentration penalties are applied.
9. Zero-trade / Cash baseline outcome remains valid when no basket clears the hurdle.
10. No future data is used (decision timestamp isolation).
"""

import os
import sys
import unittest

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.portfolio.basket_optimizer import (
    PortfolioBasketOptimizerV3,
    PortfolioBasket,
    PositionAllocation,
    HARD_MAX_POSITION_COUNT
)


class TestPortfolioBasketOptimizer(unittest.TestCase):
    """Test suite verifying dynamic multi-stock portfolio optimization."""

    def setUp(self):
        self.optimizer = PortfolioBasketOptimizerV3(
            initial_capital=5000.0,
            min_cash_buffer_rupees=50.0,
            min_net_edge_rupees=0.80,
            min_net_edge_bps=0.0,
            hard_max_position_count=5
        )

    # 1. 2-Stock basket selected when multi-stock allocation is superior
    def test_01_two_stock_basket_selected_when_superior(self):
        candidate_summaries = {
            "AXISBANK.NS": {"last_price": 1192.40, "atr_14": 12.0, "sector": "BANKING", "bar_volume": 50000.0},
            "TATACAP.NS": {"last_price": 346.75, "atr_14": 4.5, "sector": "FINANCE", "bar_volume": 40000.0},
            "SBIN.NS": {"last_price": 785.00, "atr_14": 9.0, "sector": "BANKING", "bar_volume": 60000.0}
        }
        consensus_decisions = {
            "AXISBANK.NS": {"expected_gross_bps": 100.0, "confidence": 0.9, "supporting_models": ["M1", "M2"], "contradicting_models": []},
            "TATACAP.NS": {"expected_gross_bps": 80.0, "confidence": 0.85, "supporting_models": ["M1", "M3"], "contradicting_models": []},
            "SBIN.NS": {"expected_gross_bps": 5.0, "confidence": 0.3, "supporting_models": [], "contradicting_models": ["M4"]}
        }

        result = self.optimizer.optimize_portfolio_baskets(
            candidate_summaries=candidate_summaries,
            consensus_decisions=consensus_decisions,
            available_capital=5000.0
        )

        primary = result["primary_basket"]
        self.assertIsInstance(primary, PortfolioBasket)
        self.assertEqual(primary.position_count, 2)
        self.assertIn("AXISBANK.NS", primary.selected_symbols)
        self.assertIn("TATACAP.NS", primary.selected_symbols)
        self.assertGreater(primary.total_expected_net_rupees, 25.0)
        self.assertGreaterEqual(primary.risk_adjusted_net_value, 0.80)

    # 2. 1-Stock basket selected when genuinely superior after costs
    def test_02_single_stock_basket_selected_when_superior(self):
        candidate_summaries = {
            "SOLO_STAR.NS": {"last_price": 1200.00, "atr_14": 10.0, "sector": "AUTO", "bar_volume": 50000.0},
            "WEAK_A.NS": {"last_price": 500.00, "atr_14": 8.0, "sector": "IT", "bar_volume": 30000.0},
            "WEAK_B.NS": {"last_price": 400.00, "atr_14": 7.0, "sector": "ENERGY", "bar_volume": 20000.0}
        }
        # Only SOLO_STAR has high edge; others have tiny gross return insufficient to clear ₹0.80 net hurdle
        consensus_decisions = {
            "SOLO_STAR.NS": {"expected_gross_bps": 120.0, "confidence": 0.95, "supporting_models": ["M1", "M2", "M3"], "contradicting_models": []},
            "WEAK_A.NS": {"expected_gross_bps": 12.0, "confidence": 0.4, "supporting_models": ["M1"], "contradicting_models": ["M3"]},
            "WEAK_B.NS": {"expected_gross_bps": 8.0, "confidence": 0.3, "supporting_models": [], "contradicting_models": ["M2"]}
        }

        result = self.optimizer.optimize_portfolio_baskets(
            candidate_summaries=candidate_summaries,
            consensus_decisions=consensus_decisions,
            available_capital=5000.0
        )

        primary = result["primary_basket"]
        self.assertEqual(primary.position_count, 1)
        self.assertEqual(primary.selected_symbols, ["SOLO_STAR.NS"])
        self.assertGreaterEqual(primary.total_expected_net_rupees, 0.80)

    # 3. 3+ Stock basket selected when multiple low-price stocks clear the hurdle
    def test_03_three_plus_stock_basket_selected(self):
        candidate_summaries = {
            "STOCK_A.NS": {"last_price": 300.00, "atr_14": 3.0, "sector": "FINANCE", "bar_volume": 40000.0},
            "STOCK_B.NS": {"last_price": 400.00, "atr_14": 4.0, "sector": "PHARMA", "bar_volume": 40000.0},
            "STOCK_C.NS": {"last_price": 500.00, "atr_14": 5.0, "sector": "IT", "bar_volume": 40000.0}
        }
        # All three have strong positive expected return and low correlation across different sectors
        consensus_decisions = {
            "STOCK_A.NS": {"expected_gross_bps": 85.0, "confidence": 0.9, "supporting_models": ["M1", "M2"], "contradicting_models": []},
            "STOCK_B.NS": {"expected_gross_bps": 80.0, "confidence": 0.9, "supporting_models": ["M1", "M2"], "contradicting_models": []},
            "STOCK_C.NS": {"expected_gross_bps": 75.0, "confidence": 0.9, "supporting_models": ["M1", "M2"], "contradicting_models": []}
        }

        result = self.optimizer.optimize_portfolio_baskets(
            candidate_summaries=candidate_summaries,
            consensus_decisions=consensus_decisions,
            available_capital=5000.0
        )

        primary = result["primary_basket"]
        self.assertGreaterEqual(primary.position_count, 3)
        self.assertSetEqual(set(primary.selected_symbols), {"STOCK_A.NS", "STOCK_B.NS", "STOCK_C.NS"})

    # 4. Infeasible baskets are strictly rejected
    def test_04_infeasible_baskets_rejected(self):
        candidate_summaries = {
            "EXPENSIVE.NS": {"last_price": 6000.00, "atr_14": 50.0, "sector": "NBFC", "bar_volume": 20000.0},
            "CHEAP_A.NS": {"last_price": 3000.00, "atr_14": 30.0, "sector": "IT", "bar_volume": 30000.0},
            "CHEAP_B.NS": {"last_price": 2500.00, "atr_14": 25.0, "sector": "AUTO", "bar_volume": 30000.0}
        }
        consensus_decisions = {
            "EXPENSIVE.NS": {"expected_gross_bps": 100.0, "confidence": 0.9, "supporting_models": ["M1"], "contradicting_models": []},
            "CHEAP_A.NS": {"expected_gross_bps": 80.0, "confidence": 0.8, "supporting_models": ["M1"], "contradicting_models": []},
            "CHEAP_B.NS": {"expected_gross_bps": 80.0, "confidence": 0.8, "supporting_models": ["M1"], "contradicting_models": []}
        }

        result = self.optimizer.optimize_portfolio_baskets(
            candidate_summaries=candidate_summaries,
            consensus_decisions=consensus_decisions,
            available_capital=5000.0
        )

        # Pair CHEAP_A + CHEAP_B costs ₹3000 + ₹2500 = ₹5500 > ₹5000 max deployable -> infeasible
        # EXPENSIVE costs ₹6000 > ₹5000 -> infeasible
        for b in result["all_evaluated_baskets"]:
            if "EXPENSIVE.NS" in b.selected_symbols or set(b.selected_symbols) == {"CHEAP_A.NS", "CHEAP_B.NS"}:
                self.assertFalse(b.is_feasible)
                self.assertGreater(len(b.invalidation_reasons), 0)

    # 5. Capital constraint and minimum cash buffer respected
    def test_05_capital_and_cash_buffer_constraints_strictly_respected(self):
        candidate_summaries = {
            "STOCK_1.NS": {"last_price": 1000.00, "atr_14": 10.0, "sector": "AUTO", "bar_volume": 50000.0},
            "STOCK_2.NS": {"last_price": 500.00, "atr_14": 5.0, "sector": "IT", "bar_volume": 50000.0}
        }
        consensus_decisions = {
            "STOCK_1.NS": {"expected_gross_bps": 60.0, "confidence": 0.9, "supporting_models": ["M1"], "contradicting_models": []},
            "STOCK_2.NS": {"expected_gross_bps": 60.0, "confidence": 0.9, "supporting_models": ["M1"], "contradicting_models": []}
        }

        result = self.optimizer.optimize_portfolio_baskets(
            candidate_summaries=candidate_summaries,
            consensus_decisions=consensus_decisions,
            available_capital=5000.0
        )

        for b in result["all_evaluated_baskets"]:
            if b.is_feasible:
                # Must leave at least min_cash_buffer_rupees (₹50)
                self.assertLessEqual(b.total_capital_deployed, 5000.0 - 50.0)
                self.assertGreaterEqual(b.reserved_cash, 50.0)
                self.assertAlmostEqual(b.total_capital_deployed + b.reserved_cash, 5000.0, places=2)

    # 6. Whole-share integer sizing strictly enforced
    def test_06_whole_share_integer_sizing_strictly_enforced(self):
        candidate_summaries = {
            "STOCK_X.NS": {"last_price": 1192.40, "atr_14": 15.0, "sector": "BANKING", "bar_volume": 50000.0},
            "STOCK_Y.NS": {"last_price": 346.75, "atr_14": 4.0, "sector": "FINANCE", "bar_volume": 50000.0}
        }
        consensus_decisions = {
            "STOCK_X.NS": {"expected_gross_bps": 90.0, "confidence": 0.9, "supporting_models": ["M1"], "contradicting_models": []},
            "STOCK_Y.NS": {"expected_gross_bps": 70.0, "confidence": 0.8, "supporting_models": ["M1"], "contradicting_models": []}
        }

        result = self.optimizer.optimize_portfolio_baskets(
            candidate_summaries=candidate_summaries,
            consensus_decisions=consensus_decisions,
            available_capital=5000.0
        )

        primary = result["primary_basket"]
        for pos in primary.positions:
            self.assertIsInstance(pos.quantity, int)
            self.assertGreaterEqual(pos.quantity, 1)
            self.assertAlmostEqual(pos.notional, pos.quantity * pos.price, places=2)

    # 7. Economic cost hurdle respected per position
    def test_07_economic_cost_hurdle_respected(self):
        candidate_summaries = {
            "HIGH_EDGE.NS": {"last_price": 1000.00, "atr_14": 10.0, "sector": "IT", "bar_volume": 50000.0},
            "SUB_HURDLE.NS": {"last_price": 500.00, "atr_14": 5.0, "sector": "ENERGY", "bar_volume": 50000.0}
        }
        # SUB_HURDLE has expected return lower than roundtrip friction (14 bps < 17 bps friction) -> net < 0
        consensus_decisions = {
            "HIGH_EDGE.NS": {"expected_gross_bps": 80.0, "confidence": 0.9, "supporting_models": ["M1"], "contradicting_models": []},
            "SUB_HURDLE.NS": {"expected_gross_bps": 12.0, "confidence": 0.5, "supporting_models": ["M1"], "contradicting_models": []}
        }

        result = self.optimizer.optimize_portfolio_baskets(
            candidate_summaries=candidate_summaries,
            consensus_decisions=consensus_decisions,
            available_capital=5000.0
        )

        primary = result["primary_basket"]
        for pos in primary.positions:
            self.assertGreaterEqual(pos.expected_net_rupees, 0.80)
            self.assertGreater(pos.expected_net_bps, 0.0)

        # Any basket containing SUB_HURDLE must be rejected
        for b in result["all_evaluated_baskets"]:
            if "SUB_HURDLE.NS" in b.selected_symbols:
                self.assertFalse(b.is_feasible)

    # 8. Risk limits, correlation, and sector concentration penalties applied
    def test_08_risk_and_sector_penalties_applied(self):
        candidate_summaries = {
            "BANK_1.NS": {"last_price": 1000.00, "atr_14": 15.0, "sector": "BANKING", "bar_volume": 50000.0},
            "BANK_2.NS": {"last_price": 1000.00, "atr_14": 15.0, "sector": "BANKING", "bar_volume": 50000.0},
            "TECH_1.NS": {"last_price": 1000.00, "atr_14": 15.0, "sector": "IT", "bar_volume": 50000.0}
        }
        consensus_decisions = {
            "BANK_1.NS": {"expected_gross_bps": 70.0, "confidence": 0.9, "supporting_models": ["M1"], "contradicting_models": []},
            "BANK_2.NS": {"expected_gross_bps": 70.0, "confidence": 0.9, "supporting_models": ["M1"], "contradicting_models": []},
            "TECH_1.NS": {"expected_gross_bps": 70.0, "confidence": 0.9, "supporting_models": ["M1"], "contradicting_models": []}
        }
        correlation_matrix = {
            "BANK_1.NS": {"BANK_2.NS": 0.85, "TECH_1.NS": 0.15},
            "BANK_2.NS": {"BANK_1.NS": 0.85, "TECH_1.NS": 0.20},
            "TECH_1.NS": {"BANK_1.NS": 0.15, "BANK_2.NS": 0.20}
        }

        result = self.optimizer.optimize_portfolio_baskets(
            candidate_summaries=candidate_summaries,
            consensus_decisions=consensus_decisions,
            correlation_matrix=correlation_matrix,
            available_capital=5000.0
        )

        baskets_by_id = {b.basket_id: b for b in result["all_evaluated_baskets"] if b.is_feasible}
        b_same_sector = baskets_by_id.get("BASKET_BANK_1_BANK_2")
        b_diff_sector = baskets_by_id.get("BASKET_BANK_1_TECH_1")

        self.assertIsNotNone(b_same_sector)
        self.assertIsNotNone(b_diff_sector)

        # Cross-sector diversified basket must have lower risk and higher RANV than same-sector basket
        self.assertLess(b_diff_sector.portfolio_risk_bps, b_same_sector.portfolio_risk_bps)
        self.assertGreater(b_diff_sector.risk_adjusted_net_value, b_same_sector.risk_adjusted_net_value)

    # 9. Zero-trade / Cash outcome remains valid when all fail
    def test_09_zero_trade_cash_baseline_valid_when_all_fail(self):
        candidate_summaries = {
            "LOSER_1.NS": {"last_price": 1000.00, "atr_14": 10.0, "sector": "AUTO", "bar_volume": 50000.0},
            "LOSER_2.NS": {"last_price": 800.00, "atr_14": 8.0, "sector": "IT", "bar_volume": 50000.0}
        }
        # In a bad market regime, all signals are negative or tiny
        consensus_decisions = {
            "LOSER_1.NS": {"expected_gross_bps": 5.0, "confidence": 0.3, "supporting_models": [], "contradicting_models": ["M1", "M2"]},
            "LOSER_2.NS": {"expected_gross_bps": 2.0, "confidence": 0.2, "supporting_models": [], "contradicting_models": ["M1"]}
        }

        result = self.optimizer.optimize_portfolio_baskets(
            candidate_summaries=candidate_summaries,
            consensus_decisions=consensus_decisions,
            available_capital=5000.0
        )

        primary = result["primary_basket"]
        self.assertEqual(primary.basket_type, "PRIMARY")
        self.assertEqual(primary.position_count, 0)
        self.assertEqual(primary.total_capital_deployed, 0.0)
        self.assertEqual(primary.reserved_cash, 5000.0)
        self.assertIn("Preserved 100% Cash", primary.reason_for_selection)

    # 10. No future data is used in optimization
    def test_10_no_future_data_used(self):
        # Optimizer inputs accept ONLY candidate summaries and pre-market consensus decisions
        candidate_summaries = {
            "STOCK_A.NS": {"last_price": 1000.00, "atr_14": 10.0, "sector": "AUTO", "bar_volume": 50000.0}
        }
        consensus_decisions = {
            "STOCK_A.NS": {"expected_gross_bps": 50.0, "confidence": 0.8, "supporting_models": ["M1"], "contradicting_models": []}
        }

        result = self.optimizer.optimize_portfolio_baskets(
            candidate_summaries=candidate_summaries,
            consensus_decisions=consensus_decisions,
            available_capital=5000.0
        )
        self.assertNotIn("realized_return", result["primary_basket"].to_dict())
        self.assertNotIn("realized_pnl", result["primary_basket"].to_dict())


if __name__ == "__main__":
    unittest.main()
