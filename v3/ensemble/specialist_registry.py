"""
v3/ensemble/specialist_registry.py
Specialist Model Registry and Signal Adapters.
Encapsulates all 7 independent quantitative models without altering or weakening their internal logic.
"""

from datetime import datetime
from typing import Dict, List, Any, Optional
import numpy as np

from v3.ensemble.specialist_signal import SpecialistSignal, SignalDirection, HorizonCategory


class BaseSpecialistAdapter:
    """Base interface for all specialist model adapters."""
    model_id: str = "BASE"
    model_name: str = "Base Specialist"
    horizon: HorizonCategory = HorizonCategory.INTRADAY_15M
    designated_asset: str = "ANY"

    def generate_signal(self, market_snapshot: Dict[str, Any]) -> SpecialistSignal:
        raise NotImplementedError


class SMC4Conf920Adapter(BaseSpecialistAdapter):
    """
    Model 1: SMC 4-Confirmation Sniper & 9:20 Straddle Engine.
    Specializes in ^NSEI (NIFTY 50 Index) liquidity sweeps and opening volatility harvesting.
    """
    model_id = "SMC_4CONF_920"
    model_name = "SMC 4-Conf Sniper & 9:20 Straddle"
    horizon = HorizonCategory.INTRADAY_5M
    designated_asset = "^NSEI"

    def generate_signal(self, market_snapshot: Dict[str, Any]) -> SpecialistSignal:
        data = market_snapshot.get(self.designated_asset, {})
        ltp = float(data.get("price", data.get("current_price", 22497.15)))
        vwap = float(data.get("vwap", ltp))
        rsi = float(data.get("rsi", 45.0))
        vol_surge = float(data.get("vol_surge", 1.0))
        bsl = float(data.get("bsl", 22650.0))
        ssl = float(data.get("ssl", 22465.0))

        # SMC Liquidity Sweep & Straddle Decision Logic
        if ltp <= ssl * 1.0015 and rsi <= 35.0:
            # Sell-side liquidity sweep -> Downside continuation or swift reversal
            return SpecialistSignal(
                symbol=self.designated_asset,
                model_id=self.model_id,
                model_name=self.model_name,
                direction=SignalDirection.SELL,
                horizon=self.horizon,
                confidence=0.82,
                predicted_return_pct=-0.45,
                expected_holding_mins=45,
                rationale=f"SMC SSL sweep below {ssl:.1f} with RSI {rsi:.1f}",
                features={"vwap_dist": (ltp - vwap) / vwap, "rsi": rsi, "vol_surge": vol_surge}
            )
        elif ltp >= bsl * 0.9985 and rsi >= 65.0:
            # Buy-side liquidity sweep -> Call expansion
            return SpecialistSignal(
                symbol=self.designated_asset,
                model_id=self.model_id,
                model_name=self.model_name,
                direction=SignalDirection.BUY,
                horizon=self.horizon,
                confidence=0.78,
                predicted_return_pct=0.40,
                expected_holding_mins=45,
                rationale=f"SMC BSL expansion above {bsl:.1f} with RSI {rsi:.1f}",
                features={"vwap_dist": (ltp - vwap) / vwap, "rsi": rsi, "vol_surge": vol_surge}
            )

        return SpecialistSignal(
            symbol=self.designated_asset,
            model_id=self.model_id,
            model_name=self.model_name,
            direction=SignalDirection.HOLD,
            horizon=self.horizon,
            confidence=0.50,
            predicted_return_pct=0.0,
            expected_holding_mins=0,
            rationale="Equilibrium zone between BSL and SSL; neutral straddle stance"
        )


class V215MAdapter(BaseSpecialistAdapter):
    """
    Model 2: V2 15m Momentum Trend Rider.
    Specializes in INFY.NS tech momentum and 5/20 EMA cross acceleration.
    """
    model_id = "V2_15M"
    model_name = "V2 15m Momentum Trend Rider"
    horizon = HorizonCategory.INTRADAY_15M
    designated_asset = "INFY.NS"

    def generate_signal(self, market_snapshot: Dict[str, Any]) -> SpecialistSignal:
        data = market_snapshot.get(self.designated_asset, {})
        ltp = float(data.get("price", data.get("current_price", 1018.5)))
        ema5 = float(data.get("ema5", ltp * 1.002))
        ema20 = float(data.get("ema20", ltp * 0.998))
        rsi = float(data.get("rsi", 54.0))
        vol_surge = float(data.get("vol_surge", 1.25))

        if ema5 > ema20 and vol_surge >= 1.20 and rsi > 50.0:
            return SpecialistSignal(
                symbol=self.designated_asset,
                model_id=self.model_id,
                model_name=self.model_name,
                direction=SignalDirection.BUY,
                horizon=self.horizon,
                confidence=0.76,
                predicted_return_pct=0.35,
                expected_holding_mins=60,
                rationale=f"15m Bullish EMA5/20 cross with volume surge {vol_surge:.2f}x",
                features={"ema_diff": (ema5 - ema20) / ema20, "rsi": rsi, "vol_surge": vol_surge}
            )
        elif ema5 < ema20 and vol_surge >= 1.20 and rsi < 45.0:
            return SpecialistSignal(
                symbol=self.designated_asset,
                model_id=self.model_id,
                model_name=self.model_name,
                direction=SignalDirection.SELL,
                horizon=self.horizon,
                confidence=0.72,
                predicted_return_pct=-0.30,
                expected_holding_mins=60,
                rationale=f"15m Bearish EMA breakdown with volume {vol_surge:.2f}x",
                features={"ema_diff": (ema5 - ema20) / ema20, "rsi": rsi, "vol_surge": vol_surge}
            )

        return SpecialistSignal(
            symbol=self.designated_asset,
            model_id=self.model_id,
            model_name=self.model_name,
            direction=SignalDirection.HOLD,
            horizon=self.horizon,
            confidence=0.45,
            predicted_return_pct=0.0,
            expected_holding_mins=0,
            rationale="EMA convergence / low trend momentum"
        )


class V360MAdapter(BaseSpecialistAdapter):
    """
    Model 3: Adaptive 60m Multi-Factor Master.
    Specializes in RELIANCE.NS macro composite trend progression.
    """
    model_id = "V3_60M"
    model_name = "Adaptive 60m Multi-Factor Master"
    horizon = HorizonCategory.INTRADAY_60M
    designated_asset = "RELIANCE.NS"

    def generate_signal(self, market_snapshot: Dict[str, Any]) -> SpecialistSignal:
        data = market_snapshot.get(self.designated_asset, {})
        ltp = float(data.get("price", data.get("current_price", 1183.2)))
        vwap = float(data.get("vwap", 1192.5))
        composite_score = float(data.get("composite_factor_score", -0.42))

        if composite_score <= -0.25 and ltp < vwap:
            return SpecialistSignal(
                symbol=self.designated_asset,
                model_id=self.model_id,
                model_name=self.model_name,
                direction=SignalDirection.SELL,
                horizon=self.horizon,
                confidence=0.75,
                predicted_return_pct=-0.38,
                expected_holding_mins=75,
                rationale=f"60m Multi-Factor Bearish alignment (Score: {composite_score:+.2f})",
                features={"composite_score": composite_score, "vwap_dist": (ltp - vwap) / vwap}
            )
        elif composite_score >= 0.25 and ltp > vwap:
            return SpecialistSignal(
                symbol=self.designated_asset,
                model_id=self.model_id,
                model_name=self.model_name,
                direction=SignalDirection.BUY,
                horizon=self.horizon,
                confidence=0.74,
                predicted_return_pct=0.36,
                expected_holding_mins=75,
                rationale=f"60m Multi-Factor Bullish expansion (Score: {composite_score:+.2f})",
                features={"composite_score": composite_score, "vwap_dist": (ltp - vwap) / vwap}
            )

        return SpecialistSignal(
            symbol=self.designated_asset,
            model_id=self.model_id,
            model_name=self.model_name,
            direction=SignalDirection.HOLD,
            horizon=self.horizon,
            confidence=0.48,
            predicted_return_pct=0.0,
            expected_holding_mins=0,
            rationale="Composite factor score in neutral band"
        )


class HYPO001Adapter(BaseSpecialistAdapter):
    """
    Model 4: HYPO001 30m AlphaFlow Institutional Volume Wave.
    Specializes in TATACAP.NS midday institutional accumulation shelves.
    """
    model_id = "HYPO001"
    model_name = "HYPO001 30m AlphaFlow Volume Wave"
    horizon = HorizonCategory.INTRADAY_30M
    designated_asset = "TATACAP.NS"

    def generate_signal(self, market_snapshot: Dict[str, Any]) -> SpecialistSignal:
        data = market_snapshot.get(self.designated_asset, {})
        ltp = float(data.get("price", data.get("current_price", 319.35)))
        vol_surge = float(data.get("vol_surge", 1.85))
        support_shelf = float(data.get("support_shelf", 316.5))

        if vol_surge >= 1.60 and ltp >= support_shelf:
            return SpecialistSignal(
                symbol=self.designated_asset,
                model_id=self.model_id,
                model_name=self.model_name,
                direction=SignalDirection.BUY,
                horizon=self.horizon,
                confidence=0.74,
                predicted_return_pct=0.42,
                expected_holding_mins=60,
                rationale=f"30m Institutional volume shelf surge ({vol_surge:.2f}x)",
                features={"vol_surge": vol_surge, "shelf_dist": (ltp - support_shelf) / support_shelf}
            )

        return SpecialistSignal(
            symbol=self.designated_asset,
            model_id=self.model_id,
            model_name=self.model_name,
            direction=SignalDirection.HOLD,
            horizon=self.horizon,
            confidence=0.45,
            predicted_return_pct=0.0,
            expected_holding_mins=0,
            rationale="Volume surge below institutional threshold"
        )


class HYPO002Adapter(BaseSpecialistAdapter):
    """
    Model 5: HYPO002 60m High-Beta Breakout & Channel Breakdown.
    Specializes in BAJFINANCE.NS volatility expansion swings.
    """
    model_id = "HYPO002"
    model_name = "HYPO002 60m High-Beta Breakout"
    horizon = HorizonCategory.INTRADAY_60M
    designated_asset = "BAJFINANCE.NS"

    def generate_signal(self, market_snapshot: Dict[str, Any]) -> SpecialistSignal:
        data = market_snapshot.get(self.designated_asset, {})
        ltp = float(data.get("price", data.get("current_price", 981.2)))
        chan_low = float(data.get("channel_low", 995.0))
        chan_high = float(data.get("channel_high", 1045.0))

        if ltp < chan_low:
            return SpecialistSignal(
                symbol=self.designated_asset,
                model_id=self.model_id,
                model_name=self.model_name,
                direction=SignalDirection.SELL,
                horizon=self.horizon,
                confidence=0.78,
                predicted_return_pct=-0.50,
                expected_holding_mins=80,
                rationale=f"60m High-Beta breakdown below channel floor {chan_low:.1f}",
                features={"channel_break_pct": (ltp - chan_low) / chan_low}
            )
        elif ltp > chan_high:
            return SpecialistSignal(
                symbol=self.designated_asset,
                model_id=self.model_id,
                model_name=self.model_name,
                direction=SignalDirection.BUY,
                horizon=self.horizon,
                confidence=0.75,
                predicted_return_pct=0.48,
                expected_holding_mins=80,
                rationale=f"60m High-Beta breakout above channel ceiling {chan_high:.1f}",
                features={"channel_break_pct": (ltp - chan_high) / chan_high}
            )

        return SpecialistSignal(
            symbol=self.designated_asset,
            model_id=self.model_id,
            model_name=self.model_name,
            direction=SignalDirection.HOLD,
            horizon=self.horizon,
            confidence=0.40,
            predicted_return_pct=0.0,
            expected_holding_mins=0,
            rationale="Inside Donchian channel; no breakout"
        )


class HYPO003Adapter(BaseSpecialistAdapter):
    """
    Model 6: HYPO003 15m Downside Sparsity / Dip Buyer.
    Specializes in AXISBANK.NS / SBIN.NS mean reversion discount taps.
    """
    model_id = "HYPO003"
    model_name = "HYPO003 15m Downside Sparsity / Dip Buyer"
    horizon = HorizonCategory.INTRADAY_15M
    designated_asset = "AXISBANK.NS"

    def generate_signal(self, market_snapshot: Dict[str, Any]) -> SpecialistSignal:
        data = market_snapshot.get(self.designated_asset, {})
        ltp = float(data.get("price", data.get("current_price", 1222.5)))
        rsi = float(data.get("rsi", 29.5))
        bb_pct_b = float(data.get("bb_pct_b", -0.05))

        if rsi < 32.0 and bb_pct_b <= 0.05:
            return SpecialistSignal(
                symbol=self.designated_asset,
                model_id=self.model_id,
                model_name=self.model_name,
                direction=SignalDirection.BUY,
                horizon=self.horizon,
                confidence=0.73,
                predicted_return_pct=0.32,
                expected_holding_mins=45,
                rationale=f"15m Oversold discount tap (RSI {rsi:.1f} < 32, %B {bb_pct_b:+.2f})",
                features={"rsi": rsi, "bb_pct_b": bb_pct_b}
            )

        return SpecialistSignal(
            symbol=self.designated_asset,
            model_id=self.model_id,
            model_name=self.model_name,
            direction=SignalDirection.HOLD,
            horizon=self.horizon,
            confidence=0.45,
            predicted_return_pct=0.0,
            expected_holding_mins=0,
            rationale="RSI above oversold discount threshold"
        )


class SwingRev3DMacroAdapter(BaseSpecialistAdapter):
    """
    Model 7: Phase 16 3-Day Swing Reversal + 50 EMA Macro Filter.
    Specializes in multi-day equity rotation with macro cash preservation.
    """
    model_id = "SWING_REV_3D_MACRO"
    model_name = "Phase 16 3-Day Swing Reversal + Macro"
    horizon = HorizonCategory.MULTI_DAY_SWING
    designated_asset = "UNIVERSE"

    def generate_signal(self, market_snapshot: Dict[str, Any]) -> SpecialistSignal:
        nifty_data = market_snapshot.get("^NSEI", {})
        nifty_close = float(nifty_data.get("price", nifty_data.get("current_price", 22497.15)))
        nifty_ema50 = float(nifty_data.get("ema50", 23842.22))

        # Strict Macro Filter: NIFTY must be above 50-day EMA for long equity swings
        if nifty_close < nifty_ema50:
            return SpecialistSignal(
                symbol="UNIVERSE",
                model_id=self.model_id,
                model_name=self.model_name,
                direction=SignalDirection.HOLD,
                horizon=self.horizon,
                confidence=0.90,
                predicted_return_pct=0.0,
                expected_holding_mins=0,
                rationale=f"Macro BEAR regime (NIFTY {nifty_close:.1f} < EMA50 {nifty_ema50:.1f}); 100% Cash Preservation enforced"
            )

        # In Bull regime: select bottom 2 reversal stocks
        return SpecialistSignal(
            symbol="BOTTOM_2_EQUITIES",
            model_id=self.model_id,
            model_name=self.model_name,
            direction=SignalDirection.BUY,
            horizon=self.horizon,
            confidence=0.70,
            predicted_return_pct=0.58,
            expected_holding_mins=1125,  # 3 trading sessions (~18.75 hours)
            rationale=f"Macro BULL regime (NIFTY > EMA50); rotating into bottom 2 reversal equities"
        )


class SpecialistRegistry:
    """Registry coordinating all 7 specialist adapters."""
    def __init__(self):
        self.specialists: Dict[str, BaseSpecialistAdapter] = {
            "SMC_4CONF_920": SMC4Conf920Adapter(),
            "V2_15M": V215MAdapter(),
            "V3_60M": V360MAdapter(),
            "HYPO001": HYPO001Adapter(),
            "HYPO002": HYPO002Adapter(),
            "HYPO003": HYPO003Adapter(),
            "SWING_REV_3D_MACRO": SwingRev3DMacroAdapter()
        }

    def evaluate_all(self, market_snapshot: Dict[str, Any]) -> Dict[str, SpecialistSignal]:
        """Queries every specialist independently and returns standardized signals."""
        signals = {}
        for model_id, adapter in self.specialists.items():
            try:
                signals[model_id] = adapter.generate_signal(market_snapshot)
            except Exception as e:
                signals[model_id] = SpecialistSignal(
                    symbol=getattr(adapter, "designated_asset", "UNKNOWN"),
                    model_id=model_id,
                    model_name=getattr(adapter, "model_name", model_id),
                    direction=SignalDirection.HOLD,
                    horizon=getattr(adapter, "horizon", HorizonCategory.INTRADAY_15M),
                    confidence=0.0,
                    predicted_return_pct=0.0,
                    expected_holding_mins=0,
                    rationale=f"Specialist evaluation error: {e}"
                )
        return signals
