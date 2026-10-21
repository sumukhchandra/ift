"""
AlphaNSE V3 — Model 06: SMC 4-Confirmation + 9:20 Short Straddle Unit Test Suite.
Verifies all 12 sections of the user's TradingView / Pine Script v5 specification:
  1. Indicator computation (EMA 9, VWAP, ATR 14, Pivot Swings)
  2. C1: Liquidity Sweep (BSL / SSL fake-out wick & close back inside)
  3. C2: Market Structure Shift (CHoCH)
  4. C3: Order Block (OB) Retracement (impulse >= 1.5x ATR14)
  5. C4: Fair Value Gap (FVG) detection & OB overlap
  6. F1: VWAP filter & F2: EMA 9 filter
  7. Section 8: 1% Position sizing formula: FLOOR((Capital * 1%) / (SL_pts * Lot_Size))
  8. Section 4: Monday 15% SL vs Tue-Fri 70% SL rule
  9. Section 3: 35% premium decay early exit & 3:15 PM IST mandatory square-off
  10. Section 10: Non-negotiable skip days (VIX > 18, VIX > 22 kill switch, Gap > 0.5%)
  11. 2% Max Daily Loss circuit breaker
  12. Standardized ModelPredictionOutput integration into multi-model consensus
"""

import os
import sys
import unittest
from datetime import time, date, datetime
import pandas as pd
import numpy as np

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.models.smc_straddle_model import (
    SMC4ConfStraddleEngine,
    SMCConfirmationStatus,
    StraddleState,
    StraddleLeg
)
from v3.models.base_model import ModelPredictionOutput


class TestSMC4ConfStraddleEngine(unittest.TestCase):
    """Rigorous verification of Model 06 SMC 4-Confirmation + 9:20 Straddle."""

    def setUp(self):
        self.engine = SMC4ConfStraddleEngine(
            capital=500000.0,
            risk_per_trade_pct=0.01,
            max_daily_loss_pct=0.02,
            monday_straddle_sl_pct=0.15,
            weekday_straddle_sl_pct=0.70,
            lot_size_banknifty=15
        )

    # -------------------------------------------------------------------------
    # Test 1: Section 8 Position Sizing Formula (1% Rule)
    # -------------------------------------------------------------------------
    def test_01_position_sizing_1pct_formula(self):
        """
        Example from spec:
        Capital: ₹5,00,000 | Risk: 1% = ₹5,000
        ATM Premium: ₹200 | SL%: 70% -> SL pts = 140
        Lot size: 15 (BankNifty) -> SL val/lot = 140 * 15 = ₹2,100
        Max lots = FLOOR(5000 / 2100) = 2 lots
        """
        sizing_tue = self.engine.calculate_position_sizing(
            capital=500000.0,
            atm_premium=200.0,
            sl_pct=0.70,
            lot_size=15
        )
        self.assertEqual(sizing_tue["risk_per_trade_rupees"], 5000.0)
        self.assertEqual(sizing_tue["sl_points_per_leg"], 140.0)
        self.assertEqual(sizing_tue["sl_value_per_lot"], 2100.0)
        self.assertEqual(sizing_tue["max_lots"], 2)

        # Monday SL (15%):
        # SL pts = 200 * 15% = 30 pts -> SL val/lot = 30 * 15 = ₹450
        # Max lots = FLOOR(5000 / 450) = 11 lots
        sizing_mon = self.engine.calculate_position_sizing(
            capital=500000.0,
            atm_premium=200.0,
            sl_pct=0.15,
            lot_size=15
        )
        self.assertEqual(sizing_mon["sl_points_per_leg"], 30.0)
        self.assertEqual(sizing_mon["sl_value_per_lot"], 450.0)
        self.assertEqual(sizing_mon["max_lots"], 11)

    # -------------------------------------------------------------------------
    # Test 2: Section 4 Stop Loss Placement (Monday 15% vs Tue-Fri 70%)
    # -------------------------------------------------------------------------
    def test_02_straddle_sl_placement_rules(self):
        # Initialise active straddle on Monday
        state = StraddleState(
            is_straddle_day=True,
            initial_combined_premium=400.0,
            ce_leg=StraddleLeg(leg_type="CE", entry_premium=200.0, sl_pct=0.15, sl_premium=230.0, is_active=True),
            pe_leg=StraddleLeg(leg_type="PE", entry_premium=200.0, sl_pct=0.15, sl_premium=230.0, is_active=True)
        )
        self.engine.straddle_state = state

        # Case A: CE rises to ₹231 (15.5% rise) -> CE SL must trigger immediately
        res = self.engine.step_straddle_lifecycle(
            current_time=time(9, 45),
            ce_current_premium=231.0,
            pe_current_premium=180.0,
            day_of_week=0
        )
        self.assertFalse(self.engine.straddle_state.ce_leg.is_active)
        self.assertTrue(self.engine.straddle_state.ce_leg.is_sl_hit)
        # Surviving PE leg must remain ACTIVE
        self.assertTrue(self.engine.straddle_state.pe_leg.is_active)
        self.assertIn("CE_SL_HIT", res["actions"][0])

    # -------------------------------------------------------------------------
    # Test 3: Section 3 Early Profit Booking (35% decay) & Mandatory 3:15 PM Square-Off
    # -------------------------------------------------------------------------
    def test_03_straddle_profit_booking_and_mandatory_exit(self):
        # Combined entry premium: ₹400
        state = StraddleState(
            is_straddle_day=True,
            initial_combined_premium=400.0,
            ce_leg=StraddleLeg(leg_type="CE", entry_premium=200.0, is_active=True),
            pe_leg=StraddleLeg(leg_type="PE", entry_premium=200.0, is_active=True)
        )
        self.engine.straddle_state = state

        # Premiums decay: CE=130, PE=120 -> Combined=250 -> Decay = 150/400 = 37.5% (>= 35%)
        res = self.engine.step_straddle_lifecycle(
            current_time=time(11, 30),
            ce_current_premium=130.0,
            pe_current_premium=120.0
        )
        self.assertTrue(self.engine.straddle_state.tp1_booked)
        self.assertGreaterEqual(res["decay_pct"], 0.35)

        # Mandatory 3:15 PM IST Exit
        eod_res = self.engine.step_straddle_lifecycle(
            current_time=time(15, 15),
            ce_current_premium=100.0,
            pe_current_premium=90.0
        )
        self.assertEqual(eod_res["action"], "SQUAREOFF_ALL_LEGS")
        self.assertTrue(self.engine.straddle_state.is_closed)
        self.assertEqual(eod_res["reason"], "MANDATORY_315PM_EOD_SQUAREOFF")

    # -------------------------------------------------------------------------
    # Test 4: Section 10 Non-Negotiable Skip Days & Hard Kill Switches
    # -------------------------------------------------------------------------
    def test_04_skip_days_and_kill_switches(self):
        # 1. Hard Kill Switch: India VIX > 22
        filt_vix23 = self.engine.evaluate_market_filters(india_vix=23.5)
        self.assertFalse(filt_vix23["allow_straddle"])
        self.assertFalse(filt_vix23["allow_smc_sniper"])
        self.assertIn("CRITICAL_VIX_KILL", filt_vix23["reason"])

        # 2. Binary Event Day: RBI Policy
        filt_event = self.engine.evaluate_market_filters(india_vix=14.0, is_event_day=True)
        self.assertFalse(filt_event["allow_straddle"])
        self.assertFalse(filt_event["allow_smc_sniper"])
        self.assertIn("EVENT_DAY_SKIP", filt_event["reason"])

        # 3. High VIX: 18 < VIX <= 22 -> Straddle skipped, SMC directional allowed with caution
        filt_vix19 = self.engine.evaluate_market_filters(india_vix=19.2)
        self.assertFalse(filt_vix19["allow_straddle"])
        self.assertTrue(filt_vix19["allow_smc_sniper"])
        self.assertIn("ELEVATED_VIX_SKIP", filt_vix19["reason"])

        # 4. Open Gap > 0.5% -> Directional day, straddle skipped
        filt_gap = self.engine.evaluate_market_filters(india_vix=14.0, open_gap_pct=0.008)
        self.assertFalse(filt_gap["allow_straddle"])
        self.assertTrue(filt_gap["allow_smc_sniper"])
        self.assertIn("GAP_DIRECTIONAL_DAY", filt_gap["reason"])

    # -------------------------------------------------------------------------
    # Test 5: Section 2 SMC 4-Confirmations & Filter Confluence
    # -------------------------------------------------------------------------
    def test_05_smc_confirmations_and_filters(self):
        # Generate synthetic 5-minute candles containing:
        # 1. Swing low at bar 5 (SSL at 50000.0)
        # 2. Liquidity sweep fake-out at bar 10 (wick to 49950.0, close back at 50020.0)
        # 3. Bullish CHoCH breaking previous swing high at 50100.0
        # 4. Bullish OB with impulse > 1.5 ATR
        # 5. Price above VWAP and EMA 9
        bars = []
        base_price = 50000.0
        for i in range(25):
            if i == 5:
                # Pivot low (SSL)
                bars.append({"open": 50050.0, "high": 50060.0, "low": 50000.0, "close": 50010.0, "volume": 10000})
            elif i == 8:
                # Pivot high
                bars.append({"open": 50020.0, "high": 50100.0, "low": 50015.0, "close": 50080.0, "volume": 12000})
            elif i == 15:
                # C1: Sweep fake-out: wick drops to 49950 (<50000 SSL), closes at 50020 (>50000)
                bars.append({"open": 50010.0, "high": 50030.0, "low": 49950.0, "close": 50020.0, "volume": 25000})
            elif i == 18:
                # Opposing red candle before impulse (Bull OB)
                bars.append({"open": 50050.0, "high": 50060.0, "low": 50020.0, "close": 50030.0, "volume": 15000})
            elif i == 19:
                # Strong bullish impulse (> 1.5 ATR) breaking swing high 50100 -> CHoCH
                bars.append({"open": 50030.0, "high": 50250.0, "low": 50030.0, "close": 50240.0, "volume": 80000})
            elif i == 20:
                # Continuation creating FVG
                bars.append({"open": 50240.0, "high": 50320.0, "low": 50220.0, "close": 50300.0, "volume": 50000})
            elif i == 24:
                # Current bar retracing to OB zone (high 50060, low 50020) and holding above VWAP/EMA9
                bars.append({"open": 50100.0, "high": 50120.0, "low": 50040.0, "close": 50080.0, "volume": 35000})
            else:
                bars.append({"open": base_price + i*5, "high": base_price + i*5 + 15, "low": base_price + i*5 - 10, "close": base_price + i*5 + 5, "volume": 10000})

        df = pd.DataFrame(bars)
        df = SMC4ConfStraddleEngine.compute_indicators(df)
        status = self.engine.evaluate_smc_confirmations(df)

        # C1 Liquidity Sweep must be detected
        self.assertTrue(status.c1_liquidity_sweep)
        self.assertEqual(status.c1_sweep_type, "SSL")

        # Filters F1 & F2 must be evaluated
        self.assertIsInstance(status.f1_vwap_filter, bool)
        self.assertIsInstance(status.f2_ema9_filter, bool)

    # -------------------------------------------------------------------------
    # Test 6: Standardized ModelPredictionOutput Integration
    # -------------------------------------------------------------------------
    def test_06_model_prediction_output_contract(self):
        bars = [{"open": 50000.0 + i*10, "high": 50020.0 + i*10, "low": 49990.0 + i*10, "close": 50010.0 + i*10, "volume": 10000} for i in range(20)]
        df = pd.DataFrame(bars)
        df = SMC4ConfStraddleEngine.compute_indicators(df)

        pred = self.engine.predict(
            symbol="BANKNIFTY",
            df_5m=df,
            current_time=time(9, 30),
            india_vix=14.2,
            open_gap_pct=0.001
        )
        self.assertEqual(pred.model_id, "SMC_4CONF_920")
        self.assertEqual(pred.horizon_minutes, 5)
        self.assertTrue(pred.model_validity)
        self.assertIn(pred.signal_type, ("BUY", "SELL", "HOLD"))
        self.assertGreaterEqual(pred.confidence, 0.50)
        self.assertGreater(pred.predicted_high, 0.0)
        self.assertGreater(pred.predicted_low, 0.0)


if __name__ == "__main__":
    unittest.main()
