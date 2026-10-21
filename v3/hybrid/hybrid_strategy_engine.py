"""
AlphaNSE V3 — Option C: Hybrid Strategy Engine.
Implements the user-approved Hybrid Trading Architecture:

1. Intraday Trading Universe:
   - NIFTY 50 (^NSEI) via SMC_4CONF_920 (Adaptive SMC Hybrid Regime)
   - Tech Sector: INFY.NS, TCS.NS via V2_15M
   - Banking Sector: SBIN.NS, AXISBANK.NS, ICICIBANK.NS, HDFCBANK.NS via HYPO003 / V3_60M
   - Heavyweights: RELIANCE.NS, BHARTIARTL.NS via V3_60M
   - All positions entered after 09:15 and mandatory flattened by 15:20-15:25 IST (zero overnight risk).

2. Short-Term Swing Trading Universe (2 to 6 Days):
   - High-Beta Financials / NBFC: TATACAP.NS (HYPO001) and BAJFINANCE.NS (HYPO002)
   - Gate: ONLY when Model Confidence >= 0.80 and High-Beta Breakout confirmed.
   - Sizing: Whole-share allocation, held for 2–6 sessions with Zerodha CNC (₹0 delivery brokerage).

3. Risk & Attribution Controls:
   - Stop-loss: 0.70% on Intraday, 1.80% trailing on Swing.
   - Circuit Breakers: 2.5% max daily drawdown.
   - Independent accounting of P&L, Win Rate, Drawdown, Brokerage/Statutory Fees, Slippage, and Overnight Gap Risk.
"""

import os
import sys
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v2.risk.cost_engine import IndiaCostEngine


@dataclass
class HybridPosition:
    position_id: str
    symbol: str
    model_id: str
    style: str              # "INTRADAY" or "SWING_2_6D"
    entry_date: str
    entry_time: str
    entry_price: float
    quantity: int
    notional: float
    stop_loss: float
    target_price: float
    confidence: float
    status: str             # "OPEN", "CLOSED"
    exit_date: Optional[str] = None
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    holding_sessions: int = 1
    gross_pnl_rupees: float = 0.0
    brokerage_rupees: float = 0.0
    statutory_fees_rupees: float = 0.0
    slippage_rupees: float = 0.0
    total_friction_rupees: float = 0.0
    net_pnl_rupees: float = 0.0
    net_roi_pct: float = 0.0
    exit_reason: str = "OPEN"
    overnight_gap_exposure_rupees: float = 0.0


class HybridStrategyEngine:
    """
    Manages Option C: Hybrid Execution across Intraday and Swing universes.
    """

    SWING_SYMBOLS = {"TATACAP.NS", "BAJFINANCE.NS"}
    HIGH_CONFIDENCE_SWING_THRESHOLD = 0.80

    def __init__(
        self,
        initial_capital: float = 5000.0,
        intraday_stop_pct: float = 0.007,
        swing_stop_pct: float = 0.018,
        max_daily_drawdown_pct: float = 0.025
    ):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.intraday_stop_pct = intraday_stop_pct
        self.swing_stop_pct = swing_stop_pct
        self.max_daily_drawdown_pct = max_daily_drawdown_pct
        self.cost_engine = IndiaCostEngine()
        self.closed_positions: List[HybridPosition] = []
        self.active_positions: Dict[str, HybridPosition] = {}

    def classify_opportunity(
        self,
        symbol: str,
        model_id: str,
        confidence: float
    ) -> str:
        """
        Classifies whether an opportunity is treated as SWING_2_6D or INTRADAY.
        """
        if symbol in self.SWING_SYMBOLS and confidence >= self.HIGH_CONFIDENCE_SWING_THRESHOLD:
            return "SWING_2_6D"
        return "INTRADAY"

    def calculate_friction(
        self,
        notional_entry: float,
        notional_exit: float,
        is_swing: bool
    ) -> Dict[str, float]:
        """
        Calculates transaction costs using IndiaCostEngine.
        Equities Delivery (Swing) = ₹0 Zerodha brokerage, 0.1% STT on buy & sell.
        Equities Intraday = 0.03% (max ₹20) brokerage, 0.025% STT on sell side only.
        """
        turnover = notional_entry + notional_exit
        if is_swing:
            # Zerodha CNC Delivery
            brokerage = 0.0
            stt = (notional_entry + notional_exit) * 0.001  # 0.1% both sides
            exch_turnover = turnover * 0.0000325
            stamp_duty = notional_entry * 0.00015         # 0.015% on delivery buy
            sebi = turnover * 0.000001
            gst = (brokerage + exch_turnover + sebi) * 0.18
            slippage = turnover * 0.00015                 # 1.5 bps delivery slippage
        else:
            # Zerodha MIS Intraday
            brokerage = min(20.0, turnover * 0.0003)
            stt = notional_exit * 0.00025                 # 0.025% sell side
            exch_turnover = turnover * 0.0000325
            stamp_duty = notional_entry * 0.00003         # 0.003% buy side
            sebi = turnover * 0.000001
            gst = (brokerage + exch_turnover + sebi) * 0.18
            slippage = turnover * 0.0002                  # 2.0 bps intraday slippage

        statutory = stt + exch_turnover + stamp_duty + sebi + gst
        total_friction = brokerage + statutory + slippage

        return {
            "brokerage": round(brokerage, 2),
            "statutory": round(statutory, 2),
            "slippage": round(slippage, 2),
            "total_friction": round(total_friction, 2)
        }
