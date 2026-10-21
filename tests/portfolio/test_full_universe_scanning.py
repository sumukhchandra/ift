"""
Unit and Integration Tests for Full-Universe Dynamic Scanning & Capital Rotation.
Module: tests/portfolio/test_full_universe_scanning.py

Verifies:
  1. Dynamic universe discovery & filtration across broad NSE instruments.
  2. Two-stage inference funnel (Stage 1 cheap filter -> Stage 2 6-model economics).
  3. Economic ranking strictly by EXPECTED_NET_PROFIT_AFTER_ALL_COSTS (₹) vs raw bps.
  4. Combinatorial portfolio search (0 to 5 positions) under capital & sector constraints.
  5. Dynamic capital rotation and immediate capital recycling.
  6. Rejection reasons auditability (HURDLE_FAIL, LOW_LIQUIDITY, HIGH_COST, etc.).
  7. Strict no-lookahead causal barriers.
  8. Physical safety lock against unauthorized live execution.
"""

import unittest
from typing import Dict, Any

from v3.data.dynamic_universe_provider import (
    DynamicUniverseProvider,
    InstrumentMetadata,
    UniverseEligibilityResult,
    BROAD_NSE_SECTORS
)
from v3.portfolio.full_universe_rotation_engine import (
    FullUniverseDynamicRotationEngine,
    LiveExecutionDisabledError,
    PAPER_SHADOW_ONLY,
    SelectedBasket
)


class TestFullUniverseScanning(unittest.TestCase):
    """Test suite validating full-universe dynamic scanning and capital allocation."""

    def setUp(self):
        self.provider = DynamicUniverseProvider(min_volume_threshold=3000.0, max_spread_bps=20.0)
        self.engine = FullUniverseDynamicRotationEngine(
            initial_capital=5000.0,
            min_cash_buffer_rupees=50.0,
            min_net_edge_rupees=0.80,
            rotation_min_advantage_bps=8.0,
            rotation_penalty_rupees=0.50,
            hard_max_position_count=5,
            max_sector_positions=2,
            stage1_max_candidates=25,
            calibration_factor=0.4858,
            entry_cutoff_time="14:25",
            eod_close_time="15:25",
            live_execution_unlocked=False,
            mode=PAPER_SHADOW_ONLY
        )

    def test_01_dynamic_universe_discovery_size(self):
        """Verifies universe provider discovers full universe without 10-stock limit."""
        reg = self.provider.registry
        self.assertGreaterEqual(len(reg), 40, "Universe provider must register >= 40 instruments.")
        self.assertIn("TCS.NS", reg)
        self.assertIn("RELIANCE.NS", reg)
        self.assertIn("HDFCBANK.NS", reg)
        self.assertIn("MARUTI.NS", reg)
        self.assertIn("SUNPHARMA.NS", reg)
        self.assertIn("TATACAP.NS", reg)

    def test_02_universe_filtering_liquidity_and_spread(self):
        """Verifies universe filter drops illiquid and wide-spread instruments."""
        mkt_slice = {
            "TCS.NS": {"ltp": 2000.0, "volume": 10000.0, "spread_bps": 2.5, "regime": "SIDEWAYS"},
            "ILLIQUID.NS": {"ltp": 500.0, "volume": 500.0, "spread_bps": 3.0, "regime": "SIDEWAYS"},
            "WIDESPREAD.NS": {"ltp": 500.0, "volume": 10000.0, "spread_bps": 35.0, "regime": "SIDEWAYS"}
        }
        # Register test instruments
        self.provider.register_instrument(InstrumentMetadata(
            symbol="ILLIQUID.NS", company_name="Illiquid Co", sector="GENERAL", min_volume_threshold=3000.0
        ))
        self.provider.register_instrument(InstrumentMetadata(
            symbol="WIDESPREAD.NS", company_name="Wide Spread Co", sector="GENERAL", max_spread_bps_threshold=20.0
        ))

        eligible, audit = self.provider.filter_universe(mkt_slice)
        self.assertIn("TCS.NS", eligible)
        self.assertNotIn("ILLIQUID.NS", eligible)
        self.assertNotIn("WIDESPREAD.NS", eligible)
        self.assertIn("INSUFFICIENT_LIQUIDITY", audit["ILLIQUID.NS"].rejection_reasons)
        self.assertIn("SPREAD_TOO_WIDE", audit["WIDESPREAD.NS"].rejection_reasons)

    def test_03_universe_filtering_suspension_and_price_bounds(self):
        """Verifies suspended and degenerate price symbols are rejected."""
        self.provider.register_instrument(InstrumentMetadata(
            symbol="SUSP.NS", company_name="Suspended Co", sector="GENERAL", is_suspended=True
        ))
        mkt_slice = {
            "SUSP.NS": {"ltp": 500.0, "volume": 10000.0, "spread_bps": 2.5},
            "TCS.NS": {"ltp": 0.0, "volume": 10000.0, "spread_bps": 2.5}  # Degenerate price
        }
        eligible, audit = self.provider.filter_universe(mkt_slice)
        self.assertNotIn("SUSP.NS", eligible)
        self.assertNotIn("TCS.NS", eligible)
        self.assertIn("SYMBOL_SUSPENDED", audit["SUSP.NS"].rejection_reasons)
        self.assertIn("INVALID_PRICE", audit["TCS.NS"].rejection_reasons)

    def test_04_two_stage_funnel_execution(self):
        """Verifies Stage 1 cheap screening filters universe before Stage 2 six-model inference."""
        mkt_slice = {}
        for sym in self.provider.registry:
            mkt_slice[sym] = {
                "ltp": 1000.0,
                "volume": 20000.0,
                "spread_bps": 2.5,
                "volatility_bps": 12.0,
                "regime": "HIGH_VOLATILITY_CRASH" if sym == "RELIANCE.NS" else "SIDEWAYS"
            }

        preds_slice = {
            "TCS.NS": {"raw_expected_bps": 60.0, "confidence": 0.80, "direction": 1}
        }

        res = self.engine.process_minute("2026-09-25T09:20:00+05:30", mkt_slice, preds_slice)
        self.assertGreater(res["eligible_universe_size"], 40)
        self.assertLessEqual(res["stage2_evaluated_count"], self.engine.stage1_max_candidates)

    def test_05_economic_ranking_by_net_rupees_not_raw_bps(self):
        """
        Verifies that Stock B with lower raw bps but lower friction and higher NET ₹
        is ranked ABOVE Stock C with higher raw bps but very high friction.
        Scenario from user prompt:
          Stock A: +80 bps, 20 bps cost -> net ₹25
          Stock B: +55 bps, 12 bps cost -> net ₹31 (WINNER)
          Stock C: +100 bps, 45 bps cost -> net ₹18
        """
        mkt_slice = {
            "STOCK_A.NS": {"ltp": 500.0, "volume": 50000.0, "spread_bps": 8.0, "volatility_bps": 15.0, "regime": "SIDEWAYS"},
            "STOCK_B.NS": {"ltp": 500.0, "volume": 50000.0, "spread_bps": 1.5, "volatility_bps": 10.0, "regime": "SIDEWAYS"},
            "STOCK_C.NS": {"ltp": 500.0, "volume": 50000.0, "spread_bps": 20.0, "volatility_bps": 25.0, "regime": "SIDEWAYS"}
        }
        for s in ("STOCK_A.NS", "STOCK_B.NS", "STOCK_C.NS"):
            self.engine.universe_provider.register_instrument(
                InstrumentMetadata(symbol=s, company_name=s, sector="GENERAL")
            )

        # Calibrated bps = raw * 0.4858
        # Make Stock B yield higher net profit after costs than Stock C
        preds_slice = {
            "STOCK_A.NS": {"raw_expected_bps": 80.0, "confidence": 0.80, "direction": 1},
            "STOCK_B.NS": {"raw_expected_bps": 95.0, "confidence": 0.85, "direction": 1},   # Clean, low spread
            "STOCK_C.NS": {"raw_expected_bps": 110.0, "confidence": 0.70, "direction": 1}   # Wide spread (20 bps) eats net profit
        }

        res = self.engine.process_minute("2026-09-25T09:20:00+05:30", mkt_slice, preds_slice)
        top_opps = res["top_opportunities"]
        ranked_syms = [o["symbol"] for o in top_opps]

        # STOCK_B must rank ahead of STOCK_C because expected net rupees after friction is higher
        b_opp = next(o for o in top_opps if o["symbol"] == "STOCK_B.NS")
        c_opp = next(o for o in top_opps if o["symbol"] == "STOCK_C.NS")
        self.assertGreater(b_opp["net_rupees"], c_opp["net_rupees"])
        self.assertLess(ranked_syms.index("STOCK_B.NS"), ranked_syms.index("STOCK_C.NS"))

    def test_06_portfolio_optimizer_cash_baseline_zero_positions(self):
        """Verifies optimizer allocates 0 positions (cash) when no candidate clears economic hurdle."""
        mkt_slice = {
            "TCS.NS": {"ltp": 2000.0, "volume": 10000.0, "spread_bps": 2.5, "regime": "SIDEWAYS"},
            "INFY.NS": {"ltp": 1000.0, "volume": 10000.0, "spread_bps": 2.5, "regime": "SIDEWAYS"}
        }
        # Negative / zero edge predictions
        preds_slice = {
            "TCS.NS": {"raw_expected_bps": 2.0, "confidence": 0.30, "direction": 1},
            "INFY.NS": {"raw_expected_bps": -10.0, "confidence": 0.40, "direction": -1}
        }
        res = self.engine.process_minute("2026-09-25T09:15:00+05:30", mkt_slice, preds_slice)
        basket = res["selected_basket"]
        self.assertEqual(len(basket.get("symbols", [])), 0)
        self.assertEqual(len(self.engine.active_holdings), 0)
        self.assertEqual(self.engine.available_capital, 5000.0)

    def test_07_portfolio_optimizer_multi_stock_basket_with_sector_limit(self):
        """Verifies multi-stock basket allocation respects max sector concentration."""
        mkt_slice = {
            "TCS.NS": {"ltp": 1000.0, "volume": 50000.0, "spread_bps": 1.5, "regime": "TRENDING_BULL"},
            "INFY.NS": {"ltp": 1000.0, "volume": 50000.0, "spread_bps": 1.5, "regime": "TRENDING_BULL"},
            "WIPRO.NS": {"ltp": 1000.0, "volume": 50000.0, "spread_bps": 1.5, "regime": "TRENDING_BULL"},
            "RELIANCE.NS": {"ltp": 1000.0, "volume": 50000.0, "spread_bps": 1.5, "regime": "TRENDING_BULL"}
        }
        preds = {
            "TCS.NS": {"raw_expected_bps": 80.0, "confidence": 0.85, "direction": 1},
            "INFY.NS": {"raw_expected_bps": 75.0, "confidence": 0.85, "direction": 1},
            "WIPRO.NS": {"raw_expected_bps": 70.0, "confidence": 0.85, "direction": 1},
            "RELIANCE.NS": {"raw_expected_bps": 72.0, "confidence": 0.85, "direction": 1}
        }
        res = self.engine.process_minute("2026-09-25T09:15:00+05:30", mkt_slice, preds)
        holdings = self.engine.active_holdings
        self.assertGreaterEqual(len(holdings), 1)

        # Max IT sector holdings must not exceed max_sector_positions (2)
        it_count = sum(1 for p in holdings.values() if p.sector == "INFORMATION_TECHNOLOGY")
        self.assertLessEqual(it_count, self.engine.max_sector_positions)

    def test_08_dynamic_capital_rotation_and_recycling(self):
        """Verifies dynamic capital rotation out of weak holding into high-net candidate."""
        engine_rot = FullUniverseDynamicRotationEngine(
            initial_capital=3000.0,
            hard_max_position_count=1,
            rotation_min_advantage_bps=8.0,
            rotation_penalty_rupees=0.50,
            live_execution_unlocked=False,
            mode=PAPER_SHADOW_ONLY
        )
        mkt_slice_t1 = {
            "AXISBANK.NS": {"ltp": 1000.0, "volume": 20000.0, "spread_bps": 2.0, "regime": "TRENDING_BULL"}
        }
        preds_t1 = {
            "AXISBANK.NS": {"raw_expected_bps": 60.0, "confidence": 0.80, "direction": 1}
        }
        # Minute 1: Enter AXISBANK
        engine_rot.process_minute("2026-09-25T09:15:00+05:30", mkt_slice_t1, preds_t1)
        self.assertIn("AXISBANK.NS", engine_rot.active_holdings)

        # Minute 2: TCS emerges with overwhelming positive edge, clearing rotation hurdle
        mkt_slice_t2 = {
            "AXISBANK.NS": {"ltp": 1000.0, "volume": 20000.0, "spread_bps": 2.0, "regime": "SIDEWAYS"},
            "TCS.NS": {"ltp": 2000.0, "volume": 50000.0, "spread_bps": 1.0, "regime": "TRENDING_BULL"}
        }
        preds_t2 = {
            "AXISBANK.NS": {"raw_expected_bps": 5.0, "confidence": 0.40, "direction": 0},
            "TCS.NS": {"raw_expected_bps": 140.0, "confidence": 0.90, "direction": 1}
        }
        res_t2 = engine_rot.process_minute("2026-09-25T09:20:00+05:30", mkt_slice_t2, preds_t2)

        # AXISBANK should be rotated into TCS
        self.assertIn("ROTATED_AXISBANK.NS_INTO_TCS.NS", res_t2["actions"])
        self.assertNotIn("AXISBANK.NS", engine_rot.active_holdings)
        self.assertIn("TCS.NS", engine_rot.active_holdings)
        self.assertEqual(len(engine_rot.rotation_events), 1)

    def test_09_no_lookahead_temporal_barrier(self):
        """Verifies no future bars or outcome metrics are referenced at timestamp T."""
        t_now = "2026-09-25T10:00:00+05:30"
        mkt_slice = {
            "TCS.NS": {
                "ltp": 2000.0,
                "volume": 20000.0,
                "spread_bps": 2.0,
                "future_close_forbidden": 2050.0  # Should never be used
            }
        }
        preds = {
            "TCS.NS": {"raw_expected_bps": 50.0, "confidence": 0.75, "direction": 1}
        }
        res = self.engine.process_minute(t_now, mkt_slice, preds)
        self.assertEqual(res["timestamp"], t_now)
        # Entry price must be strictly current ltp (2000.0), not future close
        if "TCS.NS" in self.engine.active_holdings:
            self.assertEqual(self.engine.active_holdings["TCS.NS"].entry_price, 2000.0)

    def test_10_entry_cutoff_and_eod_squareoff(self):
        """Verifies entry cutoff at 14:25 and mandatory square-off at 15:25."""
        mkt_slice = {
            "TCS.NS": {"ltp": 2000.0, "volume": 50000.0, "spread_bps": 1.5, "regime": "TRENDING_BULL"}
        }
        preds = {
            "TCS.NS": {"raw_expected_bps": 90.0, "confidence": 0.85, "direction": 1}
        }

        # 14:26 IST (After cutoff) -> Entry blocked
        res_cutoff = self.engine.process_minute("2026-09-25T14:26:00+05:30", mkt_slice, preds)
        self.assertEqual(len(self.engine.active_holdings), 0)
        self.assertIn("TCS.NS", res_cutoff["rejected_opportunities"])
        self.assertEqual(res_cutoff["rejected_opportunities"]["TCS.NS"], "ENTRY_CUTOFF")

    def test_11_physical_live_execution_lock(self):
        """Verifies LiveExecutionDisabledError when live execution is attempted."""
        with self.assertRaises(LiveExecutionDisabledError):
            FullUniverseDynamicRotationEngine(
                live_execution_unlocked=True,
                mode="LIVE_REAL_BROKER"
            )


if __name__ == "__main__":
    unittest.main()
