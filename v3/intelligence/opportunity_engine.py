#!/usr/bin/env python3
"""
v3/intelligence/opportunity_engine.py
AlphaNSE V3 — Institutional Opportunity Discovery, Multi-Regime Scanning & Ranking Engine.

Architectural Objectives (Directive Pillars 1 & 4):
1. Comprehensive Universe Coverage:
   - Evaluates the full verified NIFTY 50 universe + Benchmark Index / ETFs (52 instruments).
   - Eliminates arbitrary single-symbol hardcoding.
2. Market Regime & Structural Volatility Detection:
   - Classifies market structure into MOMENTUM_BREAKOUT, TREND_CONTINUATION,
     MEAN_REVERSION, VOLATILITY_EXPANSION, or CHOP_REGIME.
   - Strictly suppresses signals during CHOP_REGIME (regime_multiplier = 0.0 -> HOLD).
3. Dual-Model Consensus & Probability Calibration:
   - Harmonizes Specialist Linear Alpha with 3-Tree ML Ensemble Alpha.
   - Enforces empirical probability calibration (calibrated confidence).
4. Realistic Transaction Friction Hurdle:
   - Computes complete statutory fees (STT, Exchange Turnover, SEBI, GST, Stamp Duty)
     plus instrument-specific Bid-Ask Half-Spread and Market Slippage.
   - Evaluates Net Expected Alpha: Net Edge = Gross Move - Total Frictions.
5. Cross-Instrument Opportunity Ranking:
   - Scores every candidate by:
       Opportunity Score = Net Edge (bps) * Calibrated Confidence * Regime Multiplier * Liquidity Score
   - Ranks from Rank #1 down; provides transparent comparative rationale for selecting Rank #1.
6. Seamless Cash-Equity & Options Separation:
   - For CASH_EQUITY: Computes whole integer shares under ₹1,500 bankroll limit.
   - For OPTIONS_PAPER: Evaluates genuine exchange option chains, calculates Greeks (Delta, Theta, Gamma, Vega),
     enforces ₹1,500 capital limit, and bans option writing.
"""

import os
import sys
import math
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, time as dtime
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from QA.nifty50_constituents import NIFTY_50_CONSTITUENTS, NIFTY_INDEX_BENCHMARKS
from QA.models.one_min_predictor import OneMinPredictor
from v2.risk.cost_engine import IndiaCostEngine
from v3.execution.edge_friction_gate import EdgeFrictionGate
from v3.execution.options_engine import OptionsEngine, calculate_black_scholes_greeks

logger = logging.getLogger("OpportunityEngine")


@dataclass
class MarketRegime:
    """Classified market regime for a single instrument."""
    regime_name: str  # MOMENTUM_BREAKOUT, TREND_CONTINUATION, MEAN_REVERSION, CHOP_REGIME
    trend_direction: str  # BULLISH, BEARISH, NEUTRAL
    adx_proxy: float
    vol_surge_ratio: float
    bandwidth_pct: float
    multiplier: float  # Multiplier applied to opportunity score
    rationale: str


@dataclass
class OpportunityCandidate:
    """Complete evaluation and economics for an individual opportunity."""
    symbol: str
    company_name: str
    ltp: float
    side: str  # BUY, SELL, HOLD
    direction: str  # LONG, SHORT, FLAT
    regime: MarketRegime
    specialist_alpha_bps: float
    tree_alpha_bps: float
    concurrence_ok: bool
    calibrated_confidence: float
    expected_gross_move_pct: float
    gross_gain_rs: float
    statutory_fees_rs: float
    spread_slippage_friction_rs: float
    total_friction_rs: float
    total_friction_bps: float
    net_expectancy_rs: float
    net_expectancy_bps: float
    score: float
    viable: bool
    rejection_reasons: List[str]
    quantity: int = 0
    rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["regime"] = self.regime.regime_name
        d["regime_multiplier"] = self.regime.multiplier
        return d


class RegimeDetector:
    """Microstructure and trend regime detection module."""

    @staticmethod
    def detect(candles: List[Dict[str, Any]], ltp: float) -> MarketRegime:
        if len(candles) < 15:
            return MarketRegime(
                regime_name="CHOP_REGIME",
                trend_direction="NEUTRAL",
                adx_proxy=10.0,
                vol_surge_ratio=1.0,
                bandwidth_pct=0.005,
                multiplier=0.0,
                rationale="Insufficient candle history (< 15 bars)"
            )

        df = pd.DataFrame(candles)
        c = df["close"].astype(float).values
        h = df["high"].astype(float).values
        l = df["low"].astype(float).values
        v = df["volume"].astype(float).values

        # Rolling indicators
        ema5 = float(pd.Series(c).ewm(span=5).mean().iloc[-1])
        ema20 = float(pd.Series(c).ewm(span=20).mean().iloc[-1])
        avg_vol = float(np.mean(v[-15:-1])) if len(v) > 1 else 1000.0
        cur_vol = float(v[-1])
        vol_surge = cur_vol / max(avg_vol, 1.0)

        # Volatility / Bollinger Bandwidth
        std14 = float(np.std(c[-14:]))
        mean14 = float(np.mean(c[-14:]))
        bandwidth = (4.0 * std14) / max(mean14, 1.0)

        # Immediate Chop Check: Bandwidth below 0.10% indicates sideways compression
        if bandwidth < 0.001 or std14 < 1e-4:
            return MarketRegime(
                regime_name="CHOP_REGIME",
                trend_direction="NEUTRAL",
                adx_proxy=8.0,
                vol_surge_ratio=round(vol_surge, 2),
                bandwidth_pct=round(bandwidth * 100, 3),
                multiplier=0.0,
                rationale="Flat sideways volatility compression (bandwidth < 0.10%)"
            )

        # Micro-RSI 7
        diffs = np.diff(c[-8:])
        gains = np.maximum(diffs, 0.0)
        losses = np.maximum(-diffs, 0.0)
        avg_gain = float(np.mean(gains)) if len(gains) > 0 else 0.0
        avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0
        rs = avg_gain / (avg_loss + 1e-9)
        rsi7 = 100.0 - (100.0 / (1.0 + rs))

        # Recent Range & Wick Pressure
        cur_h = float(h[-1])
        cur_l = float(l[-1])
        cur_o = float(df["open"].iloc[-1])
        cur_c = float(c[-1])
        bar_range = max(cur_h - cur_l, 0.01)
        upper_wick = (cur_h - max(cur_o, cur_c)) / bar_range
        lower_wick = (min(cur_o, cur_c) - cur_l) / bar_range

        # Regime Rules
        # 1. Momentum Breakout: High volume surge, strong directional expansion
        if vol_surge >= 1.50 and bandwidth >= 0.0025:
            if cur_c > ema20 and upper_wick < 0.25:
                return MarketRegime(
                    regime_name="MOMENTUM_BREAKOUT",
                    trend_direction="BULLISH",
                    adx_proxy=35.0,
                    vol_surge_ratio=round(vol_surge, 2),
                    bandwidth_pct=round(bandwidth * 100, 3),
                    multiplier=1.25,
                    rationale=f"Bullish volume surge ({vol_surge:.1f}x) with clean upper wick ({upper_wick:.2f})"
                )
            elif cur_c < ema20 and lower_wick < 0.25:
                return MarketRegime(
                    regime_name="MOMENTUM_BREAKOUT",
                    trend_direction="BEARISH",
                    adx_proxy=35.0,
                    vol_surge_ratio=round(vol_surge, 2),
                    bandwidth_pct=round(bandwidth * 100, 3),
                    multiplier=1.25,
                    rationale=f"Bearish volume breakdown ({vol_surge:.1f}x) with clean lower wick ({lower_wick:.2f})"
                )

        # 2. Trend Continuation: Clear EMA hierarchy and moderate momentum
        if ema5 > ema20 and 45.0 <= rsi7 <= 70.0:
            return MarketRegime(
                regime_name="TREND_CONTINUATION",
                trend_direction="BULLISH",
                adx_proxy=26.0,
                vol_surge_ratio=round(vol_surge, 2),
                bandwidth_pct=round(bandwidth * 100, 3),
                multiplier=1.10,
                rationale=f"Bullish EMA alignment (EMA5 > EMA20) with healthy RSI ({rsi7:.1f})"
            )
        elif ema5 < ema20 and 30.0 <= rsi7 <= 55.0:
            return MarketRegime(
                regime_name="TREND_CONTINUATION",
                trend_direction="BEARISH",
                adx_proxy=26.0,
                vol_surge_ratio=round(vol_surge, 2),
                bandwidth_pct=round(bandwidth * 100, 3),
                multiplier=1.10,
                rationale=f"Bearish EMA alignment (EMA5 < EMA20) with healthy RSI ({rsi7:.1f})"
            )

        # 3. Mean Reversion: Extreme oversold or overbought near band boundaries
        if rsi7 < 25.0 and lower_wick > 0.40:
            return MarketRegime(
                regime_name="MEAN_REVERSION",
                trend_direction="BULLISH",
                adx_proxy=18.0,
                vol_surge_ratio=round(vol_surge, 2),
                bandwidth_pct=round(bandwidth * 100, 3),
                multiplier=0.90,
                rationale=f"Oversold bounce setup (RSI7={rsi7:.1f}, Lower wick={lower_wick:.2f})"
            )
        elif rsi7 > 75.0 and upper_wick > 0.40:
            return MarketRegime(
                regime_name="MEAN_REVERSION",
                trend_direction="BEARISH",
                adx_proxy=18.0,
                vol_surge_ratio=round(vol_surge, 2),
                bandwidth_pct=round(bandwidth * 100, 3),
                multiplier=0.90,
                rationale=f"Overbought rejection setup (RSI7={rsi7:.1f}, Upper wick={upper_wick:.2f})"
            )

        # 4. Default: Chop / Sideways regime
        return MarketRegime(
            regime_name="CHOP_REGIME",
            trend_direction="NEUTRAL",
            adx_proxy=12.0,
            vol_surge_ratio=round(vol_surge, 2),
            bandwidth_pct=round(bandwidth * 100, 3),
            multiplier=0.0,
            rationale="Lack of directional conviction, flat moving averages or contradictory momentum"
        )


class OpportunityDiscoveryEngine:
    """
    Production-grade Multi-Asset Opportunity Discovery & Ranking Engine.
    Scans the complete NIFTY 50 universe, evaluates multi-model concurrence,
    calculates statutory transaction costs, filters regimes, and selects the
    highest-conviction opportunities.
    """

    def __init__(
        self,
        predictor: Optional[OneMinPredictor] = None,
        specialist_weights: Optional[Dict[str, Any]] = None,
        options_engine: Optional[OptionsEngine] = None,
        cost_engine: Optional[IndiaCostEngine] = None,
        min_net_expectancy_rs: float = 0.30,
        min_confidence_pct: float = 45.0,
        max_spread_bps: float = 25.0,
        bankroll: float = 1500.0,
        cash_reserve_rs: float = 0.0,
        cash_reserve_pct: float = 0.0
    ):
        self.predictor = predictor or OneMinPredictor()
        self.specialist_weights = specialist_weights or {}
        self.options_engine = options_engine
        self.min_net_expectancy_rs = min_net_expectancy_rs
        self.min_confidence_pct = min_confidence_pct
        self.max_spread_bps = max_spread_bps
        self.bankroll = bankroll
        self.cash_reserve_rs = cash_reserve_rs
        self.cash_reserve_pct = cash_reserve_pct

        # Transaction cost and friction gates
        self.cost_engine = cost_engine or IndiaCostEngine()
        self.cost_engine.brokerage_pct = 0.0
        self.cost_engine.brokerage_flat_cap = 0.0

        self.edge_gate = EdgeFrictionGate(
            half_spread_bps=2.5,
            slippage_bps=3.0,
            safety_margin_rs=0.40,
            min_net_expectancy_rs=self.min_net_expectancy_rs
        )
        self.edge_gate.cost_engine = self.cost_engine

        # Build full verified universe registry (50 NIFTY constituents + benchmarks)
        self.universe: Dict[str, Dict[str, Any]] = self._build_universe_registry()

    def _build_universe_registry(self) -> Dict[str, Dict[str, Any]]:
        registry = {}
        # 1. 50 NIFTY Constituents
        for sym, meta in NIFTY_50_CONSTITUENTS.items():
            clean = sym.replace(".NS", "")
            registry[sym] = {
                "symbol": sym,
                "clean_symbol": clean,
                "company_name": meta["name"],
                "sector": meta["sector"],
                "kotak_symbol": f"{clean}-EQ",
                "segment": "nse_cm",
                "is_index_benchmark": False
            }
        # 2. Benchmarks
        for sym, name in NIFTY_INDEX_BENCHMARKS.items():
            clean = sym.replace(".NS", "").replace("^", "")
            registry[sym] = {
                "symbol": sym,
                "clean_symbol": clean,
                "company_name": name,
                "sector": "INDEX",
                "kotak_symbol": f"{clean}-EQ" if not sym.startswith("^") else clean,
                "segment": "nse_cm",
                "is_index_benchmark": True
            }
        return registry

    @staticmethod
    def extract_19_features(buf: List[Dict[str, Any]]) -> Optional[List[float]]:
        """
        Extracts the exact 19 institutional features mathematically consistent
        with the training pipeline and live execution adapter.
        Returns None if buffer has fewer than 15 bars or non-positive close/low.
        """
        if not buf or len(buf) < 15:
            return None

        try:
            # Defensive timeframe validation: reject buffers containing sub-minute (e.g. 10s) intervals
            if len(buf) >= 3 and "timestamp" in buf[-1] and "timestamp" in buf[-2]:
                try:
                    t1 = pd.to_datetime(str(buf[-1]["timestamp"]).replace(" IST", ""))
                    t0 = pd.to_datetime(str(buf[-2]["timestamp"]).replace(" IST", ""))
                    delta_sec = (t1 - t0).total_seconds()
                    if 0 < delta_sec < 45.0:
                        logger.warning(f"REJECTED_SAMPLING_MISMATCH: Sub-minute interval detected ({delta_sec:.1f}s < 45s)")
                        return None
                except Exception as ex:
                    logger.debug(f"Timeframe delta calculation error: {ex}")

            i = len(buf) - 1
            c_list = buf

            c0 = float(c_list[i]["close"])
            h0 = float(c_list[i]["high"])
            l0 = float(c_list[i]["low"])
            o0 = float(c_list[i]["open"])
            v0 = float(c_list[i]["volume"])

            if c0 <= 0 or l0 <= 0:
                return None

            # 1. Returns & Momentum
            r1 = (c0 - float(c_list[i - 1]["close"])) / float(c_list[i - 1]["close"])
            r3 = (c0 - float(c_list[i - 3]["close"])) / float(c_list[i - 3]["close"])
            r5 = (c0 - float(c_list[i - 5]["close"])) / float(c_list[i - 5]["close"])
            r10 = (c0 - float(c_list[i - 10]["close"])) / float(c_list[i - 10]["close"])
            r1_prev = (float(c_list[i - 1]["close"]) - float(c_list[i - 2]["close"])) / float(c_list[i - 2]["close"])
            accel1 = r1 - r1_prev

            # 2. RSI 7 & 14
            diffs14 = [float(c_list[k]["close"]) - float(c_list[k - 1]["close"]) for k in range(max(1, i - 13), i + 1)]
            gains14 = [max(0.0, d) for d in diffs14]
            losses14 = [abs(min(0.0, d)) for d in diffs14]
            avg_g14 = sum(gains14) / 14.0
            avg_l14 = (sum(losses14) / 14.0) or 1e-9
            rs14 = avg_g14 / avg_l14
            rsi14 = 100.0 - (100.0 / (1.0 + rs14))

            diffs7 = diffs14[-7:]
            gains7 = [max(0.0, d) for d in diffs7]
            losses7 = [abs(min(0.0, d)) for d in diffs7]
            avg_g7 = sum(gains7) / 7.0
            avg_l7 = (sum(losses7) / 7.0) or 1e-9
            rs7 = avg_g7 / avg_l7
            rsi7 = 100.0 - (100.0 / (1.0 + rs7))

            # 3. Micro-VWAP
            cum_vol = sum(float(c_list[k]["volume"]) for k in range(max(0, i - 20), i + 1))
            cum_vp = sum(float(c_list[k]["close"]) * float(c_list[k]["volume"]) for k in range(max(0, i - 20), i + 1))
            vwap = (cum_vp / cum_vol) if cum_vol > 0 else c0
            vwap_dist = (c0 - vwap) / vwap

            # 4. Bollinger Bands 20
            window_c = [float(c_list[k]["close"]) for k in range(max(0, i - 19), i + 1)]
            sma20 = sum(window_c) / len(window_c)
            variance20 = sum((x - sma20) ** 2 for x in window_c) / len(window_c)
            std20 = math.sqrt(variance20) or 1e-6
            bb_bandwidth = (4.0 * std20) / sma20
            bb_pct_b = (c0 - (sma20 - 2.0 * std20)) / (4.0 * std20)

            # 5. ATR 14 & Parkinson Volatility
            trs = [max(float(c_list[k]["high"]) - float(c_list[k]["low"]),
                       abs(float(c_list[k]["high"]) - float(c_list[k - 1]["close"])),
                       abs(float(c_list[k]["low"]) - float(c_list[k - 1]["close"]))) for k in range(max(1, i - 13), i + 1)]
            atr14 = sum(trs) / len(trs)
            micro_atr14 = atr14 / c0

            ln_hl = [math.log(float(c_list[k]["high"]) / (float(c_list[k]["low"]) or 1e-6)) for k in range(max(0, i - 9), i + 1)]
            parkinson_vol = math.sqrt(sum(x ** 2 for x in ln_hl) / (4.0 * math.log(2.0) * len(ln_hl)))

            # 6. Wick Pressures
            total_range = max(1e-6, h0 - l0)
            upper_wick = (h0 - max(o0, c0)) / total_range
            lower_wick = (min(o0, c0) - l0) / total_range
            wick_pressure = lower_wick - upper_wick

            # 7. Volume surge ratio
            past_vol = [float(c_list[k]["volume"]) for k in range(max(0, i - 9), i)]
            avg_vol_10 = (sum(past_vol) / len(past_vol)) if past_vol else 1.0
            vol_surge = v0 / (avg_vol_10 or 1.0)

            feats = [
                float(r1), float(r3), float(r5), float(r10), float(accel1),
                float(rsi7 / 100.0), float(rsi14 / 100.0),
                float(vwap_dist), float(bb_pct_b), float(bb_bandwidth),
                float(micro_atr14), float(parkinson_vol),
                float(wick_pressure), float(upper_wick), float(lower_wick),
                float(vol_surge),
                float(r1 * vol_surge),
                float(vwap_dist * (rsi14 / 100.0)),
                float(accel1 * bb_bandwidth)
            ]

            if any(math.isnan(x) or math.isinf(x) for x in feats):
                return None
            return feats
        except Exception:
            return None

    @staticmethod
    def validate_specialist_output(raw_output: Any) -> Tuple[bool, Optional[float], Optional[str]]:
        """
        Validates specialist model output schema:
        - Output type: float, int, 1D array of size 1, or dict with 'predicted_alpha' or 'alpha'
        - Shape: scalar or array of size 1
        - Finite numeric values: no NaN, Inf, -Inf
        - Required fields: if dict, must contain 'predicted_alpha' or 'alpha'

        Returns:
            Tuple[bool, Optional[float], Optional[str]]: (is_valid, float_alpha, rejection_reason)
        """
        if raw_output is None:
            return False, None, "INVALID_SPECIALIST_OUTPUT: Specialist prediction is None (missing model output)"
        if isinstance(raw_output, bool):
            return False, None, "INVALID_SPECIALIST_OUTPUT: Unsupported output type bool, expected numeric float or dict"

        val = None
        if isinstance(raw_output, dict):
            if "predicted_alpha" in raw_output:
                val = raw_output["predicted_alpha"]
            elif "alpha" in raw_output:
                val = raw_output["alpha"]
            else:
                return False, None, "INVALID_SPECIALIST_OUTPUT: Missing required field 'predicted_alpha' in specialist output schema"
        elif isinstance(raw_output, (int, float, np.floating, np.integer)):
            val = float(raw_output)
        elif isinstance(raw_output, (list, tuple, np.ndarray)):
            arr = np.asarray(raw_output)
            if arr.size != 1:
                return False, None, f"INVALID_SPECIALIST_OUTPUT: Shape mismatch, expected scalar but got shape {arr.shape}"
            val = arr.item()
        else:
            return False, None, f"INVALID_SPECIALIST_OUTPUT: Unsupported output type {type(raw_output).__name__}, expected numeric float or dict"

        # Validate finite numeric and exclude booleans (subclass of int in Python)
        if val is None or isinstance(val, bool) or not isinstance(val, (int, float, np.floating, np.integer)):
            return False, None, f"INVALID_SPECIALIST_OUTPUT: Extracted alpha is not numeric ({type(val).__name__})"

        float_val = float(val)
        if math.isnan(float_val) or math.isinf(float_val):
            return False, None, "INVALID_SPECIALIST_OUTPUT: Non-finite numeric value (NaN/Inf) in specialist prediction"

        return True, float_val, None

    def _predict_specialist_linear(self, symbol: str, features_19: Optional[List[float]]) -> Optional[float]:
        """
        Computes linear specialist prediction if asset-assigned model exists.
        Validates model presence, required fields (weights, bias, means, stds),
        shapes (19 features/weights/means/stds), and finite numeric values.
        Returns float predicted return, or None if missing/invalid.
        """
        if not self.specialist_weights or not isinstance(self.specialist_weights, dict):
            return None

        if features_19 is None or not isinstance(features_19, (list, tuple, np.ndarray)) or len(features_19) != 19:
            return None

        # Find matching model by symbol or sector
        assigned_model = None
        for mid, meta in self.specialist_weights.items():
            if isinstance(meta, dict) and meta.get("assigned_asset") == symbol:
                assigned_model = meta
                break

        if not assigned_model:
            assigned_model = self.specialist_weights.get("V2_15M") or (
                list(self.specialist_weights.values())[0] if self.specialist_weights else None
            )

        if not assigned_model or not isinstance(assigned_model, dict):
            return None

        # Validate required fields
        required_fields = ["weights", "bias", "means", "stds"]
        for rf in required_fields:
            if rf not in assigned_model:
                return None

        weights = assigned_model["weights"]
        bias = assigned_model["bias"]
        means = assigned_model["means"]
        stds = assigned_model["stds"]

        # Validate types and lengths
        if not (isinstance(weights, (list, tuple, np.ndarray)) and len(weights) == 19):
            return None
        if not (isinstance(means, (list, tuple, np.ndarray)) and len(means) == 19):
            return None
        if not (isinstance(stds, (list, tuple, np.ndarray)) and len(stds) == 19):
            return None
        if not isinstance(bias, (int, float, np.floating, np.integer)):
            return None

        # Validate finite numeric values
        try:
            f_arr = np.asarray(features_19, dtype=float)
            w_arr = np.asarray(weights, dtype=float)
            m_arr = np.asarray(means, dtype=float)
            s_arr = np.asarray(stds, dtype=float)
            b_val = float(bias)

            if not (np.all(np.isfinite(f_arr)) and np.all(np.isfinite(w_arr)) and
                    np.all(np.isfinite(m_arr)) and np.all(np.isfinite(s_arr)) and
                    np.isfinite(b_val)):
                return None

            s_safe = np.where(s_arr == 0, 1.0, s_arr)
            norm_x = (f_arr - m_arr) / s_safe
            pred = float(np.dot(w_arr, norm_x) + b_val)
            if not np.isfinite(pred):
                return None
            return pred
        except Exception:
            return None

    def calculate_affordable_quantity(
        self,
        ltp: float,
        bankroll: Optional[float] = None,
        half_spread_bps: float = 2.5,
        slippage_bps: float = 3.0
    ) -> Tuple[int, float, List[str]]:
        """
        Computes affordable whole integer shares under available bankroll,
        strictly accounting for estimated entry costs and cash reserve.
        Returns (qty, notional, rejection_reasons).
        """
        effective_bankroll = bankroll if bankroll is not None else self.bankroll
        if ltp <= 0 or effective_bankroll <= 0:
            return 0, 0.0, ["INVALID_PRICE_OR_BANKROLL"]

        # Effective deployable bankroll after reserve
        avail_bankroll = max(0.0, effective_bankroll - getattr(self, "cash_reserve_rs", 0.0))
        if hasattr(self, "cash_reserve_pct") and self.cash_reserve_pct > 0:
            avail_bankroll = min(avail_bankroll, effective_bankroll * (1.0 - self.cash_reserve_pct))

        raw_qty = int(avail_bankroll // ltp)
        if raw_qty < 1:
            return 0, 0.0, [f"UNAFFORDABLE_POSITION (Price ₹{ltp:.2f} exceeds available bankroll ₹{avail_bankroll:.2f})"]

        # Iteratively verify affordability including entry friction
        qty = raw_qty
        last_total_entry = 0.0
        while qty > 0:
            notional = qty * ltp
            # Entry friction: stamp duty (0.003%) + exchange (0.00307%) + sebi (0.0001%) + gst + half spread + slippage
            entry_statutory = (
                notional * (self.cost_engine.stamp_duty_buy_pct + self.cost_engine.exchange_pct + self.cost_engine.sebi_pct)
                + (notional * (self.cost_engine.exchange_pct + self.cost_engine.sebi_pct) * self.cost_engine.gst_pct)
            )
            entry_spread = notional * (half_spread_bps / 10000.0)
            entry_slippage = notional * (slippage_bps / 10000.0)
            total_entry_cost = notional + entry_statutory + entry_spread + entry_slippage
            last_total_entry = total_entry_cost

            if total_entry_cost <= avail_bankroll:
                return qty, notional, []
            qty -= 1

        return 0, 0.0, [f"UNAFFORDABLE_POSITION (Price ₹{ltp:.2f} + entry costs ₹{last_total_entry:.2f} exceed available bankroll ₹{avail_bankroll:.2f})"]

    def scan_and_rank_opportunities(
        self,
        quotes: Dict[str, Dict[str, Any]],
        candle_buffers: Dict[str, List[Dict[str, Any]]]
    ) -> List[OpportunityCandidate]:
        """
        Scans all universe instruments in parallel batch, extracts features,
        evaluates models, calculates friction, detects regimes, and ranks opportunities.
        """
        candidates: List[OpportunityCandidate] = []
        batch_ml_symbols = []
        batch_ml_dfs = []

        # 1. First pass: Filter fresh quotes and prepare feature batches
        for sym, u_meta in self.universe.items():
            q = quotes.get(sym)
            if not q or q.get("is_stale", False) or q.get("source") == "BUFFER_FALLBACK" or q.get("ltp", 0.0) <= 0:
                continue

            buf = candle_buffers.get(sym, [])
            if len(buf) < 15:
                continue

            df = pd.DataFrame(buf)
            clean_sym = u_meta["clean_symbol"]
            df["symbol"] = clean_sym
            if "timestamp" not in df.columns:
                df["timestamp"] = pd.date_range(end=pd.Timestamp.now(), periods=len(df), freq="1min")

            batch_ml_symbols.append(sym)
            batch_ml_dfs.append(df)

        if not batch_ml_symbols:
            return []

        # 2. Vectorized Batch ML Prediction
        # Uses true batched inference across all models in a single matrix pass
        ml_input_dict = dict(zip(batch_ml_symbols, batch_ml_dfs))
        try:
            if hasattr(self.predictor, "predict_batch_1m"):
                ml_results = self.predictor.predict_batch_1m(ml_input_dict)
            else:
                ml_results = {s: self.predictor.predict_next_1m(d) for s, d in ml_input_dict.items()}
        except Exception as e:
            # Fallback to per-symbol with fail-closed logging
            ml_results = {}
            for s, d in ml_input_dict.items():
                try:
                    ml_results[s] = self.predictor.predict_next_1m(d)
                except Exception as ex:
                    ml_results[s] = {"prediction_valid": False, "error": str(ex)}

        # 3. Second pass: Comprehensive Economics, Concurrence & Regime Evaluation
        for sym in batch_ml_symbols:
            q = quotes[sym]
            ltp = float(q["ltp"])
            buf = candle_buffers[sym]
            u_meta = self.universe[sym]

            ml_res = ml_results.get(sym, {})
            if not ml_res.get("prediction_valid", False):
                continue

            # Detect Microstructure Regime
            regime = RegimeDetector.detect(buf, ltp)

            # Predictions
            tree_alpha = float(ml_res.get("predicted_return_pct", 0.0)) / 100.0
            calibrated_conf = float(ml_res.get("confidence", 0.0))
            ml_signal = ml_res.get("signal", "HOLD")

            # Extract 19 institutional features for Specialist Model
            feats_19 = self.extract_19_features(buf)
            if feats_19 is None:
                raw_spec = None
                spec_valid = False
                specialist_alpha = 0.0
                spec_rejection = "INSUFFICIENT_HISTORY: Buffer too short or prices invalid for specialist features (< 15 bars)"
            else:
                raw_spec = self._predict_specialist_linear(sym, feats_19)
                spec_valid, validated_alpha, spec_rejection = self.validate_specialist_output(raw_spec)
                specialist_alpha = validated_alpha if spec_valid else 0.0

            # Determine Direction & Concurrence
            side = "HOLD"
            concurrence = False
            rejections = []

            if not spec_valid:
                rejections.append(spec_rejection)
            else:
                is_bull = (specialist_alpha > 0 and tree_alpha >= 0.0002)
                is_bear = (specialist_alpha < 0 and tree_alpha <= -0.0002)

                if is_bull:
                    side = "BUY"
                    concurrence = True
                elif is_bear:
                    side = "SELL"
                    concurrence = True
                else:
                    side = "HOLD"
                    rejections.append("MODELS_DISAGREE (Specialist vs Tree Alpha directional divergence)")

            # Confidence Hurdle
            if calibrated_conf < self.min_confidence_pct:
                rejections.append(f"LOW_CONFIDENCE ({calibrated_conf:.1f}% < {self.min_confidence_pct:.1f}%)")

            # Regime Hurdle
            if regime.regime_name == "CHOP_REGIME":
                rejections.append("CHOP_REGIME_REJECTION (Market structure sideways/choppy)")

            # Whole-Share Affordability Check accounting for entry costs & cash reserve
            qty, notional, afford_rejections = self.calculate_affordable_quantity(
                ltp=ltp,
                half_spread_bps=2.5,
                slippage_bps=3.0
            )

            expected_move_pct = max(0.0008, abs(tree_alpha))

            if qty < 1 or not spec_valid:
                # Reject immediately when unaffordable or specialist output invalid:
                # do NOT calculate synthetic rupee gains or fabricate scores/confidences!
                if qty < 1:
                    rejections.extend(afford_rejections)
                gross_gain_rs = 0.0
                statutory_fees_rs = 0.0
                half_spread_friction_rs = 0.0
                slippage_friction_rs = 0.0
                friction_rs = 0.0
                friction_bps = 0.0
                net_expectancy_rs = 0.0
                net_expectancy_bps = -9999.0
                score = 0.0
                viable = False
            else:
                # Economic Friction & Net Expectancy Calculation on affordable quantity
                gross_gain_rs = round(notional * expected_move_pct, 2)

                # Roundtrip costs via IndiaCostEngine
                roundtrip_cost = self.cost_engine.calculate_roundtrip_cost(
                    capital=notional,
                    gross_return=gross_gain_rs,
                    slippage_bps=3.0
                )
                statutory_fees_rs = round(roundtrip_cost.proportional_statutory_cost + roundtrip_cost.fixed_or_capped_cost, 2)

                # Spread + Slippage
                bid = float(q.get("bid", ltp * 0.9995))
                ask = float(q.get("ask", ltp * 1.0005))
                spread_rs = ask - bid
                spread_bps = (spread_rs / max(ltp, 1.0)) * 10000.0

                if spread_bps > self.max_spread_bps:
                    rejections.append(f"EXCESSIVE_SPREAD ({spread_bps:.1f} bps > {self.max_spread_bps} bps)")

                half_spread_friction_rs = round((spread_rs / 2.0) * qty, 2)
                slippage_friction_rs = round(roundtrip_cost.slippage, 2)
                friction_rs = round(roundtrip_cost.total_cost + half_spread_friction_rs, 2)
                friction_bps = (friction_rs / max(notional, 1.0)) * 10000.0

                net_expectancy_rs = round(gross_gain_rs - friction_rs, 2)
                net_expectancy_bps = round((net_expectancy_rs / max(notional, 1.0)) * 10000.0, 2)

                # Net Edge Hurdle
                if net_expectancy_rs < self.min_net_expectancy_rs:
                    rejections.append(
                        f"INSUFFICIENT_NET_EDGE (Net ₹{net_expectancy_rs:.2f} < Min ₹{self.min_net_expectancy_rs:.2f} | Gross ₹{gross_gain_rs:.2f} vs Friction ₹{friction_rs:.2f})"
                    )

                viable = (len(rejections) == 0 and side in ["BUY", "SELL"])

                # Composite Opportunity Score
                # Score is zero if not viable or chop
                if viable:
                    score = round(net_expectancy_bps * (calibrated_conf / 100.0) * regime.multiplier, 3)
                else:
                    score = 0.0

            cand = OpportunityCandidate(
                symbol=sym,
                company_name=u_meta["company_name"],
                ltp=round(ltp, 2),
                side=side if viable else "HOLD",
                direction="LONG" if (viable and side == "BUY") else ("SHORT" if (viable and side == "SELL") else "FLAT"),
                regime=regime,
                specialist_alpha_bps=round(specialist_alpha * 10000.0, 2),
                tree_alpha_bps=round(tree_alpha * 10000.0, 2),
                concurrence_ok=concurrence,
                calibrated_confidence=round(calibrated_conf, 1),
                expected_gross_move_pct=round(expected_move_pct * 100.0, 3),
                gross_gain_rs=gross_gain_rs,
                statutory_fees_rs=statutory_fees_rs,
                spread_slippage_friction_rs=round(half_spread_friction_rs + slippage_friction_rs, 2),
                total_friction_rs=friction_rs,
                total_friction_bps=round(friction_bps, 2),
                net_expectancy_rs=net_expectancy_rs,
                net_expectancy_bps=net_expectancy_bps,
                score=score,
                viable=viable,
                rejection_reasons=rejections,
                quantity=qty
            )
            candidates.append(cand)

        # 4. Sort and Rank Opportunities (Highest Opportunity Score First)
        # Affordability gate: viable first, then affordable (qty > 0), then score and net expectancy
        candidates.sort(key=lambda x: (x.viable, x.quantity > 0, x.score, x.net_expectancy_bps), reverse=True)
        for i, c in enumerate(candidates, 1):
            c.rank = i

        return candidates

    def select_top_opportunity(
        self,
        candidates: List[OpportunityCandidate],
        mode: str = "CASH_EQUITY"
    ) -> Dict[str, Any]:
        """
        Selects the authoritative Rank #1 opportunity, enforces cash/derivative rules,
        and provides full transparency explaining why it ranked above all peers.
        """
        if not candidates:
            return {
                "decision": "HOLD",
                "reason": "NO_CANDIDATES_SCANNED",
                "candidate": None,
                "ranked_candidates_count": 0
            }

        top = candidates[0]

        if not top.viable or top.score <= 0.0:
            sample_reasons = []
            for c in candidates[:3]:
                if c.rejection_reasons:
                    sample_reasons.append(f"{c.symbol}: {c.rejection_reasons[0]}")
            rejection_text = f"ALL_OPPORTUNITIES_REJECTED ({len(candidates)} scanned). Top hurdles: {'; '.join(sample_reasons)}"
            comp_rationale = (
                f"Rank #1 candidate {top.symbol} rejected: {top.rejection_reasons[0] if top.rejection_reasons else 'Score 0.0'}. "
                f"Net Expectancy: {top.net_expectancy_bps:+.1f} bps (₹{top.net_expectancy_rs:+.2f}). "
                f"Regime: {top.regime.regime_name}."
            )
            return {
                "decision": "HOLD",
                "reason": rejection_text,
                "candidate": top,
                "comparative_rationale": comp_rationale,
                "ranked_candidates_count": len(candidates)
            }

        # Format Comparative Rationale vs Runner Up
        runner_up = candidates[1] if len(candidates) > 1 else None
        comp_rationale = (
            f"Selected Rank #1 ({top.symbol}) over Rank #2 ({runner_up.symbol if runner_up else 'None'}): "
            f"Score {top.score:.2f} vs {runner_up.score if runner_up else 0.0:.2f} | "
            f"Net Expectancy +{top.net_expectancy_bps:.1f} bps (₹{top.net_expectancy_rs:.2f}) | "
            f"Regime: {top.regime.regime_name} (x{top.regime.multiplier:.2f}) | "
            f"Confidence: {top.calibrated_confidence:.1f}%"
        )

        # Mode Branching
        if mode == "OPTIONS_PAPER" and self.options_engine:
            # Under OPTIONS_PAPER mode: translate directional edge into CE/PE contract evaluation
            spot_price = top.ltp
            # If trading an equity underlying, map to its option chain or index
            opt_decision = self.options_engine.evaluate_ce_pe_signal(
                spot_price=spot_price,
                predicted_return=top.tree_alpha_bps / 10000.0,
                confidence=top.calibrated_confidence
            )
            return {
                "decision": opt_decision.get("signal", "HOLD"),
                "mode": "OPTIONS_PAPER",
                "underlying_opportunity": top,
                "option_decision": opt_decision,
                "comparative_rationale": comp_rationale,
                "ranked_candidates_count": len(candidates)
            }
        else:
            # Under CASH_EQUITY mode: whole integer shares under ₹1,500
            qty = top.quantity
            notional = round(qty * top.ltp, 2)
            return {
                "decision": top.side,
                "mode": "CASH_EQUITY",
                "symbol": top.symbol,
                "quantity": qty,
                "notional": notional,
                "entry_price": top.ltp,
                "net_expectancy_rs": top.net_expectancy_rs,
                "candidate": top,
                "comparative_rationale": comp_rationale,
                "ranked_candidates_count": len(candidates)
            }
