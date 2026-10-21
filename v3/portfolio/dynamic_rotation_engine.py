"""
AlphaNSE V3 — Dynamic Intraday Capital Rotation Engine V1.
Module: v3/portfolio/dynamic_rotation_engine.py

Upgrades AlphaNSE V3 from a static pre-market basket allocation system
into a continuously re-optimizing intraday capital allocation system.

CHRONOLOGICAL INVARIANTS:
1. NO LOOKAHEAD: Decisions at timestamp T strictly consume information available at or before T.
2. FROZEN CALIBRATION: The session's OOS calibration factor is immutable. Current session
   outcomes NEVER alter the current session's calibration or models.
3. STRICT PAPER/SHADOW: Live execution remains physically disabled via LiveExecutionDisabledError.
4. NO RETRAINING: Models remain frozen from pre-market freeze (09:05 IST).
5. NO FORCED TRADING: Cash is always a valid decision; the engine never chases trade count.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, time
import logging
import math
from typing import Dict, List, Any, Optional, Tuple, Set
import numpy as np

from v2.risk.cost_engine import IndiaCostEngine, CostBreakdown
from v3.config.v3_config import (
    INITIAL_CAPITAL,
    MIN_CASH_BUFFER_RUPEES,
    MIN_NET_EDGE_RUPEES,
    MIN_NET_EDGE_BPS,
    ENTRY_CUTOFF_TIME,
    EOD_CLOSE_TIME,
    HARD_MAX_POSITION_COUNT,
    STOP_LOSS_ATR_MULT,
    ROTATION_MIN_ADVANTAGE_BPS,
    ROTATION_PENALTY_RUPEES
)

logger = logging.getLogger(__name__)

# Execution modes
BASELINE_MODE = "BASELINE"
DYNAMIC_ROTATION_MODE = "DYNAMIC_ROTATION"
PAPER_SHADOW_ONLY = "PAPER_SHADOW_ONLY"

# Default rotation hysteresis threshold in basis points
DEFAULT_ROTATION_MIN_ADVANTAGE_BPS: float = ROTATION_MIN_ADVANTAGE_BPS
DEFAULT_ROTATION_PENALTY_RUPEES: float = ROTATION_PENALTY_RUPEES
MAX_SECTOR_CONCENTRATION: int = 3

SECTOR_MAP: Dict[str, str] = {
    "AXISBANK.NS": "FINANCIAL_SERVICES",
    "TATACAP.NS": "FINANCIAL_SERVICES",
    "INFY.NS": "INFORMATION_TECHNOLOGY",
    "HDFCBANK.NS": "FINANCIAL_SERVICES",
    "BAJFINANCE.NS": "FINANCIAL_SERVICES",
    "BHARTIARTL.NS": "TELECOMMUNICATION",
    "ICICIBANK.NS": "FINANCIAL_SERVICES",
    "SBIN.NS": "FINANCIAL_SERVICES",
    "TCS.NS": "INFORMATION_TECHNOLOGY",
    "RELIANCE.NS": "ENERGY"
}


class LiveExecutionDisabledError(Exception):
    """Safety guard physically preventing unauthorized real brokerage execution."""
    pass


@dataclass
class ActivePosition:
    """An open position managed by the dynamic rotation engine."""
    position_id: str
    symbol: str
    quantity: int
    entry_price: float
    entry_time: str
    entry_notional: float
    target_horizon_minutes: int
    stop_loss_price: float
    take_profit_price: float
    expected_gross_bps: float
    expected_net_bps: float
    expected_net_rupees: float
    entry_cost_rupees: float
    supporting_models: List[str]
    sector: str
    minutes_held: int = 0
    highest_price_seen: float = 0.0
    lowest_price_seen: float = 0.0

    def __post_init__(self):
        if self.highest_price_seen == 0.0:
            self.highest_price_seen = self.entry_price
        if self.lowest_price_seen == 0.0:
            self.lowest_price_seen = self.entry_price

    def notional_for_price(self, p: float) -> float:
        return round(self.quantity * p, 2)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PositionRemainingValue:
    """Valuation of an active position's remaining runway vs candidate opportunities."""
    symbol: str
    current_price: float
    unrealized_pnl_bps: float
    unrealized_pnl_rupees: float
    minutes_held: int
    remaining_minutes: int
    remaining_expected_gross_bps: float
    remaining_expected_gross_rupees: float
    estimated_exit_cost_rupees: float
    remaining_expected_net_rupees: float
    remaining_expected_net_bps: float
    risk_bps: float
    thesis_status: str          # "ON_TRACK", "LATE", "STOP_LOSS", "TAKE_PROFIT", "TIMEOUT", "INVALIDATED"
    exit_recommended: bool = False
    exit_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateOpportunity:
    """An evaluated opportunity from the full universe at timestamp T."""
    symbol: str
    timestamp: str
    ltp: float
    spread_bps: float
    volume: float
    volume_z: float
    volatility_bps: float
    regime: str
    sector: str
    raw_predictions: Dict[str, float]
    raw_expected_return_bps: float
    calibration_factor: float
    calibrated_expected_return_bps: float
    direction: int                      # +1 Long, -1 Short, 0 Neutral
    confidence: float
    consensus_ratio: str
    supporting_models: List[str]
    contradicting_models: List[str]
    affordable_quantity: int
    notional_required: float
    expected_gross_bps: float
    expected_gross_rupees: float
    statutory_cost_rupees: float
    spread_cost_rupees: float
    slippage_cost_rupees: float
    impact_cost_rupees: float
    total_entry_cost_rupees: float
    total_roundtrip_cost_rupees: float
    expected_net_rupees: float
    expected_net_bps: float
    target_horizon_minutes: int = 60
    is_viable: bool = True
    reject_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RotationComparison:
    """Pairwise comparison between a candidate opportunity and an existing holding."""
    candidate_symbol: str
    current_symbol: str
    candidate_expected_net: float
    current_remaining_expected_net: float
    exit_cost_current: float
    entry_cost_candidate: float
    rotation_penalty: float
    incremental_net_rupees: float
    incremental_advantage_bps: float
    threshold_advantage_bps: float
    should_rotate: bool
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClosedTradeRecord:
    """Archival record of a completed trade."""
    trade_id: str
    symbol: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    quantity: int
    notional: float
    gross_pnl_bps: float
    gross_pnl_rupees: float
    statutory_cost_rupees: float
    execution_friction_rupees: float
    total_friction_rupees: float
    net_pnl_bps: float
    net_pnl_rupees: float
    holding_minutes: int
    exit_reason: str
    rotated_into: Optional[str] = None
    supporting_models: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DynamicIntradayCapitalRotationEngine:
    """
    Continuous 1-minute capital rotation engine for AlphaNSE V3.
    Evaluates all 10 universe stocks every minute, assesses active holdings,
    recycles released capital immediately, and rotates into superior risk-adjusted
    opportunities whenever the net advantage exceeds the hysteresis barrier.
    """

    def __init__(
        self,
        initial_capital: float = INITIAL_CAPITAL,
        min_cash_buffer_rupees: float = MIN_CASH_BUFFER_RUPEES,
        min_net_edge_rupees: float = MIN_NET_EDGE_RUPEES,
        min_net_edge_bps: float = MIN_NET_EDGE_BPS,
        rotation_min_advantage_bps: float = DEFAULT_ROTATION_MIN_ADVANTAGE_BPS,
        rotation_penalty_rupees: float = DEFAULT_ROTATION_PENALTY_RUPEES,
        hard_max_position_count: int = HARD_MAX_POSITION_COUNT,
        calibration_factor: float = 1.0,
        entry_cutoff_time: str = ENTRY_CUTOFF_TIME,
        eod_close_time: str = EOD_CLOSE_TIME,
        live_execution_unlocked: bool = False,
        mode: str = PAPER_SHADOW_ONLY,
        model_hash: str = "FROZEN_MODEL_HASH",
        dataset_hash: str = "FROZEN_DATASET_HASH",
        calibration_hash: str = "FROZEN_CALIBRATION_HASH",
        cooldown_minutes: int = 0,
        trailing_stop_active: bool = False,
        tp_multiplier: float = 1.0,
        max_single_position_pct: float = 0.75
    ):
        if live_execution_unlocked:
            raise LiveExecutionDisabledError("Live broker execution is permanently locked! Paper/shadow only.")

        self.initial_capital = initial_capital
        self.available_capital = initial_capital
        self.min_cash_buffer_rupees = min_cash_buffer_rupees
        self.min_net_edge_rupees = min_net_edge_rupees
        self.min_net_edge_bps = min_net_edge_bps
        self.rotation_min_advantage_bps = rotation_min_advantage_bps
        self.rotation_penalty_rupees = rotation_penalty_rupees
        self.hard_max_position_count = hard_max_position_count
        self.calibration_factor = calibration_factor
        self.entry_cutoff_time = entry_cutoff_time
        self.eod_close_time = eod_close_time
        self.mode = mode
        self.model_hash = model_hash
        self.dataset_hash = dataset_hash
        self.calibration_hash = calibration_hash
        self.cooldown_minutes = cooldown_minutes
        self.trailing_stop_active = trailing_stop_active
        self.tp_multiplier = tp_multiplier
        self.max_single_position_pct = max_single_position_pct
        self.cooldown_until: Dict[str, str] = {}

        # Subsystems
        self.cost_engine = IndiaCostEngine()

        # Engine State
        self.active_positions: Dict[str, ActivePosition] = {}
        self.closed_trades: List[ClosedTradeRecord] = []
        self.audit_ledger: List[Dict[str, Any]] = []
        self.rotation_events: List[Dict[str, Any]] = []
        self.trade_counter: int = 0
        self.last_processed_timestamp: Optional[str] = None

    # =========================================================================
    # CORE MINUTE-BY-MINUTE CYCLE
    # =========================================================================

    def process_minute(
        self,
        timestamp_str: str,
        universe_market_slice: Dict[str, Dict[str, Any]],
        multi_model_predictions: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Executes one discrete 1-minute re-evaluation and capital allocation cycle.
        """
        time_part = self._extract_time_str(timestamp_str)
        self.last_processed_timestamp = timestamp_str

        # ---------------------------------------------------------------------
        # 1. TIME BOUNDARY GATING
        # ---------------------------------------------------------------------
        is_eod_square_off = (time_part >= self.eod_close_time)
        is_after_entry_cutoff = (time_part >= self.entry_cutoff_time)

        # If EOD square-off reached, forcibly close all positions and return
        if is_eod_square_off:
            eod_closures = self._force_eod_square_off(timestamp_str, universe_market_slice)
            return {
                "timestamp": timestamp_str,
                "action": "EOD_SQUARE_OFF",
                "closed_positions": [c.to_dict() for c in eod_closures],
                "active_positions_count": 0,
                "available_capital": round(self.available_capital, 2),
                "audit_entry": None
            }

        # ---------------------------------------------------------------------
        # 2. EVALUATE & REFRESH EXISTING ACTIVE POSITIONS
        # ---------------------------------------------------------------------
        position_evaluations: Dict[str, PositionRemainingValue] = {}
        positions_to_close: List[Tuple[str, str, float]] = []  # (sym, reason, exit_price)

        for sym, pos in list(self.active_positions.items()):
            pos.minutes_held += 1
            tick_data = universe_market_slice.get(sym, {})
            current_p = float(tick_data.get("ltp", tick_data.get("price", pos.entry_price)))
            pos.highest_price_seen = max(pos.highest_price_seen, current_p)
            pos.lowest_price_seen = min(pos.lowest_price_seen, current_p)

            eval_res = self._evaluate_position_remaining_value(pos, current_p)
            position_evaluations[sym] = eval_res

            if eval_res.exit_recommended:
                positions_to_close.append((sym, eval_res.exit_reason or "THESIS_EXIT", current_p))

        # Close positions flagged for natural exit (Stop loss, Take profit, Horizon timeout, Invalidation)
        symbols_exited_this_minute: Set[str] = set()
        for sym, reason, exit_p in positions_to_close:
            self._close_position(
                symbol=sym,
                exit_price=exit_p,
                exit_time=time_part,
                exit_reason=reason,
                rotated_into=None
            )
            symbols_exited_this_minute.add(sym)

        # ---------------------------------------------------------------------
        # 3. FULL UNIVERSE EVALUATION (ALL 10 STOCKS)
        # ---------------------------------------------------------------------
        candidate_evaluations: Dict[str, CandidateOpportunity] = {}
        viable_candidates: List[CandidateOpportunity] = []

        for sym, tick_data in universe_market_slice.items():
            model_info = (multi_model_predictions or {}).get(sym, {})
            cand = self._evaluate_candidate_opportunity(
                symbol=sym,
                timestamp=timestamp_str,
                tick_data=tick_data,
                model_info=model_info,
                is_after_entry_cutoff=is_after_entry_cutoff
            )
            # If stock exited on this exact minute, do not re-enter immediately (cooldown)
            if sym in symbols_exited_this_minute:
                cand.is_viable = False
                cand.reject_reasons.append("JUST_EXITED_COOLDOWN")

            candidate_evaluations[sym] = cand
            if cand.is_viable and sym not in self.active_positions:
                viable_candidates.append(cand)

        # Sort viable candidates by expected net rupees descending
        viable_candidates.sort(key=lambda c: c.expected_net_rupees, reverse=True)

        # ---------------------------------------------------------------------
        # 4. CAPITAL ALLOCATION & ROTATION LOGIC
        # ---------------------------------------------------------------------
        decisions: List[Dict[str, Any]] = []

        if not is_after_entry_cutoff:
            for cand_idx, cand in enumerate(viable_candidates):
                # Check sector limit for candidate
                current_sector_count = sum(
                    1 for p in self.active_positions.values() if p.sector == cand.sector
                )
                if current_sector_count >= MAX_SECTOR_CONCENTRATION:
                    cand.is_viable = False
                    cand.reject_reasons.append("SECTOR_LIMIT")
                    continue

                # Case A: Capacity exists within HARD_MAX_POSITION_COUNT and available cash
                deployable_cash = self.available_capital - self.min_cash_buffer_rupees
                if len(self.active_positions) < self.hard_max_position_count and deployable_cash >= cand.ltp:
                    # Allocate slot dynamically based on candidates and remaining slots
                    remaining_slots = self.hard_max_position_count - len(self.active_positions)
                    remaining_candidates = len(viable_candidates) - cand_idx
                    target_slots = max(1, min(remaining_slots, remaining_candidates))
                    capital_per_slot = deployable_cash / target_slots
                    # Cap single position at max_single_position_pct of total deployable cash
                    max_pos_cap = deployable_cash * self.max_single_position_pct if deployable_cash > 2000.0 else deployable_cash
                    if len(self.active_positions) == 0 and len(viable_candidates) >= 2 and cand.symbol == viable_candidates[0].symbol:
                        cand2 = viable_candidates[1]
                        test_qty = int(max_pos_cap / cand.ltp)
                        if test_qty >= 2 and (deployable_cash - (test_qty * cand.ltp)) >= cand2.ltp:
                            target_alloc = test_qty * cand.ltp
                        else:
                            target_alloc = min(max_pos_cap, max(capital_per_slot, cand.ltp))
                    elif len(self.active_positions) == 0 and len(viable_candidates) == 1:
                        target_alloc = min(max_pos_cap, deployable_cash)
                    else:
                        target_alloc = min(max_pos_cap, max(capital_per_slot, cand.ltp))
                    qty = int(min(deployable_cash, target_alloc) / cand.ltp)
                    if qty > 0:
                        self._enter_position(cand, qty, time_part)
                        decisions.append({
                            "action": "ENTER",
                            "symbol": cand.symbol,
                            "quantity": qty,
                            "price": cand.ltp,
                            "reason": "DIRECT_CAPITAL_ALLOCATION"
                        })
                        continue

                # Case B: Portfolio at limit or capital tied up -> Evaluate ROTATION
                if self.active_positions:
                    rotation_comp = self._find_best_rotation_target(cand, position_evaluations)
                    if rotation_comp and rotation_comp.should_rotate:
                        target_sym = rotation_comp.current_symbol
                        target_pos = self.active_positions[target_sym]
                        target_p = float(universe_market_slice.get(target_sym, {}).get("ltp", target_pos.entry_price))

                        # Execute ROTATE: Exit existing position & immediately enter new candidate
                        self._close_position(
                            symbol=target_sym,
                            exit_price=target_p,
                            exit_time=time_part,
                            exit_reason="ROTATION_REPLACEMENT",
                            rotated_into=cand.symbol
                        )

                        # Sizing for new candidate using released capital
                        new_deployable = self.available_capital - self.min_cash_buffer_rupees
                        new_qty = int(new_deployable / cand.ltp)
                        if new_qty > 0:
                            self._enter_position(cand, new_qty, time_part)
                            decisions.append({
                                "action": "ROTATE",
                                "symbol_out": target_sym,
                                "symbol_in": cand.symbol,
                                "quantity_in": new_qty,
                                "advantage_bps": rotation_comp.incremental_advantage_bps,
                                "reason": f"ROTATION_ADVANTAGE ({rotation_comp.incremental_advantage_bps:.1f} bps > {self.rotation_min_advantage_bps:.1f} bps)"
                            })
                            self.rotation_events.append(asdict(rotation_comp))
                            continue
                    else:
                        cand.is_viable = False
                        if rotation_comp and rotation_comp.rejection_reason:
                            cand.reject_reasons.append(rotation_comp.rejection_reason)
                        else:
                            cand.reject_reasons.append("ROTATION_NOT_WORTH_COST")
                else:
                    cand.is_viable = False
                    cand.reject_reasons.append("INSUFFICIENT_CAPITAL")

        # ---------------------------------------------------------------------
        # 5. AUDIT LOGGING & REJECT REASON TRACEABILITY
        # ---------------------------------------------------------------------
        audit_entry = {
            "timestamp": timestamp_str,
            "time": time_part,
            "available_capital": round(self.available_capital, 2),
            "active_positions_count": len(self.active_positions),
            "active_positions": [p.symbol for p in self.active_positions.values()],
            "closed_trades_count": len(self.closed_trades),
            "decisions": decisions,
            "candidate_evaluations": {
                sym: {
                    "ltp": c.ltp,
                    "calibrated_bps": c.calibrated_expected_return_bps,
                    "expected_net_rs": c.expected_net_rupees,
                    "expected_net_bps": c.expected_net_bps,
                    "confidence": c.confidence,
                    "is_viable": c.is_viable,
                    "reject_reasons": c.reject_reasons
                }
                for sym, c in candidate_evaluations.items()
            },
            "position_evaluations": {
                sym: {
                    "unrealized_bps": ev.unrealized_pnl_bps,
                    "unrealized_rs": ev.unrealized_pnl_rupees,
                    "remaining_net_rs": ev.remaining_expected_net_rupees,
                    "minutes_held": ev.minutes_held,
                    "thesis_status": ev.thesis_status
                }
                for sym, ev in position_evaluations.items()
            },
            "model_hash": self.model_hash,
            "dataset_hash": self.dataset_hash,
            "calibration_hash": self.calibration_hash,
            "calibration_factor": self.calibration_factor
        }
        self.audit_ledger.append(audit_entry)

        return {
            "timestamp": timestamp_str,
            "time": time_part,
            "decisions": decisions,
            "active_positions": list(self.active_positions.keys()),
            "available_capital": round(self.available_capital, 2),
            "closed_trades_count": len(self.closed_trades)
        }

    # =========================================================================
    # CANDIDATE & POSITION EVALUATION LOGIC
    # =========================================================================

    def _evaluate_candidate_opportunity(
        self,
        symbol: str,
        timestamp: str,
        tick_data: Dict[str, Any],
        model_info: Dict[str, Any],
        is_after_entry_cutoff: bool
    ) -> CandidateOpportunity:
        """Evaluates an individual universe candidate at timestamp T."""
        ltp = float(tick_data.get("ltp", tick_data.get("price", 1000.0)))
        spread_bps = float(tick_data.get("spread_bps", 2.4))
        volatility_bps = float(tick_data.get("volatility_bps", 15.0))
        volume = float(tick_data.get("volume", 10000.0))
        volume_z = float(tick_data.get("volume_z", 0.0))
        regime = tick_data.get("regime", "SIDEWAYS")
        sector = SECTOR_MAP.get(symbol, "GENERAL")

        raw_models = model_info.get("models", {})
        raw_exp_bps = float(model_info.get("raw_expected_bps", 0.0))
        confidence = float(model_info.get("confidence", 0.50))
        direction = int(model_info.get("direction", 1 if raw_exp_bps > 0 else (0 if raw_exp_bps == 0 else -1)))
        supporting = model_info.get("supporting", [])
        contradicting = model_info.get("contradicting", [])

        # Apply frozen OOS calibration factor
        calibrated_bps = round(raw_exp_bps * self.calibration_factor, 2)

        # Whole share sizing under total account purchasing power (enables rotation evaluation)
        total_account_equity = self.available_capital + sum(p.entry_notional for p in self.active_positions.values())
        max_allocatable = max(0.0, total_account_equity - self.min_cash_buffer_rupees)
        
        # Sizing target: 1 slot or at least 1 whole share if affordable under total capital
        target_slot_capital = max_allocatable / max(1, self.hard_max_position_count)
        if max_allocatable >= ltp > 0:
            qty = max(1, int(target_slot_capital / ltp))
        else:
            qty = 0
        notional = round(qty * ltp, 2)

        # Cost computation
        exp_gross_rupees = round(notional * (abs(calibrated_bps) / 10000.0), 2)
        cb: CostBreakdown = self.cost_engine.calculate_roundtrip_cost(
            capital=max(100.0, notional),
            gross_return=abs(calibrated_bps) / 10000.0,
            slippage_bps=0.0
        )
        statutory_rs = round(cb.brokerage + cb.stt + cb.exchange_charges + cb.sebi_fees + cb.stamp_duty + cb.gst, 2)
        spread_rs = round(notional * (spread_bps / 10000.0), 2)
        slippage_rs = round(notional * (2.0 / 10000.0), 2)
        impact_rs = round(notional * (1.0 / 10000.0), 2)
        total_roundtrip_cost = round(statutory_rs + spread_rs + slippage_rs + impact_rs, 2)
        total_entry_cost = round(total_roundtrip_cost / 2.0, 2)

        exp_net_rupees = round(exp_gross_rupees - total_roundtrip_cost, 2)
        exp_net_bps = round((exp_net_rupees / notional * 10000.0), 2) if notional > 0 else 0.0

        # Gating checks
        reject_reasons = []
        if is_after_entry_cutoff:
            reject_reasons.append("ENTRY_CUTOFF")
        if direction <= 0 or raw_exp_bps <= 0:
            reject_reasons.append("NO_EDGE")
        if exp_net_bps <= self.min_net_edge_bps:
            reject_reasons.append("INSUFFICIENT_EDGE")
        if exp_net_rupees < self.min_net_edge_rupees:
            reject_reasons.append("HURDLE_FAIL")
        if confidence < 0.20:
            reject_reasons.append("INSUFFICIENT_CONFIDENCE")
        if volume < 2000.0 or spread_bps > 15.0:
            reject_reasons.append("INSUFFICIENT_LIQUIDITY")
        if qty <= 0:
            reject_reasons.append("INSUFFICIENT_CAPITAL")
        if regime in ("TRENDING_BEAR_STRONG", "HIGH_VOLATILITY_CRASH"):
            reject_reasons.append("REGIME_INVALID")
        time_part = self._extract_time_str(timestamp)
        if self.cooldown_minutes > 0 and time_part < self.cooldown_until.get(symbol, ""):
            reject_reasons.append("COOLDOWN_ACTIVE")

        is_viable = (len(reject_reasons) == 0)

        return CandidateOpportunity(
            symbol=symbol,
            timestamp=timestamp,
            ltp=ltp,
            spread_bps=spread_bps,
            volume=volume,
            volume_z=volume_z,
            volatility_bps=volatility_bps,
            regime=regime,
            sector=sector,
            raw_predictions=raw_models,
            raw_expected_return_bps=raw_exp_bps,
            calibration_factor=self.calibration_factor,
            calibrated_expected_return_bps=calibrated_bps,
            direction=direction,
            confidence=confidence,
            consensus_ratio=f"{len(supporting)}/5",
            supporting_models=supporting,
            contradicting_models=contradicting,
            affordable_quantity=qty,
            notional_required=notional,
            expected_gross_bps=calibrated_bps,
            expected_gross_rupees=exp_gross_rupees,
            statutory_cost_rupees=statutory_rs,
            spread_cost_rupees=spread_rs,
            slippage_cost_rupees=slippage_rs,
            impact_cost_rupees=impact_rs,
            total_entry_cost_rupees=total_entry_cost,
            total_roundtrip_cost_rupees=total_roundtrip_cost,
            expected_net_rupees=exp_net_rupees,
            expected_net_bps=exp_net_bps,
            target_horizon_minutes=int(model_info.get("target_horizon_minutes", 60)),
            is_viable=is_viable,
            reject_reasons=reject_reasons
        )

    def _evaluate_position_remaining_value(
        self,
        pos: ActivePosition,
        current_price: float
    ) -> PositionRemainingValue:
        """Estimates the remaining forward value of an active holding."""
        unrealized_bps = round((current_price - pos.entry_price) / pos.entry_price * 10000.0, 2)
        peak_gain_bps = round((pos.highest_price_seen - pos.entry_price) / pos.entry_price * 10000.0, 2)
        current_notional = pos.quantity * current_price
        unrealized_rs = round(current_notional * (unrealized_bps / 10000.0), 2)
        remaining_mins = max(0, pos.target_horizon_minutes - pos.minutes_held)

        # Exit cost calculation (half of roundtrip)
        exit_cost_res = self.cost_engine.calculate_roundtrip_cost(
            capital=current_notional, gross_return=0.0, slippage_bps=0.0
        )
        exit_statutory = round(
            exit_cost_res.brokerage + exit_cost_res.stt + exit_cost_res.exchange_charges +
            exit_cost_res.sebi_fees + exit_cost_res.stamp_duty + exit_cost_res.gst, 2
        )
        exit_friction = round(current_notional * (3.0 / 10000.0), 2)
        total_exit_cost = round((exit_statutory / 2.0) + exit_friction, 2)

        # Remaining expected gross move
        progress_ratio = min(1.0, pos.minutes_held / max(1, pos.target_horizon_minutes))
        remaining_expected_gross_bps = max(0.0, pos.expected_gross_bps * (1.0 - progress_ratio ** 0.5))
        remaining_expected_gross_rs = round(current_notional * (remaining_expected_gross_bps / 10000.0), 2)
        remaining_expected_net_rs = round(remaining_expected_gross_rs - total_exit_cost, 2)
        remaining_expected_net_bps = round(
            (remaining_expected_net_rs / current_notional * 10000.0), 2
        ) if current_notional > 0 else 0.0

        # Exit conditions check
        exit_recommended = False
        exit_reason = None
        thesis_status = "ON_TRACK"

        # 1. Stop Loss Hit
        if current_price <= pos.stop_loss_price:
            exit_recommended = True
            exit_reason = f"STOP_LOSS_TRIGGERED (LTP ₹{current_price:.2f} <= ₹{pos.stop_loss_price:.2f})"
            thesis_status = "STOP_LOSS"
        # 2. Take Profit Hit
        elif current_price >= pos.take_profit_price:
            exit_recommended = True
            exit_reason = f"TAKE_PROFIT_REACHED (LTP ₹{current_price:.2f} >= ₹{pos.take_profit_price:.2f})"
            thesis_status = "TAKE_PROFIT"
        # 2b. Trailing Stop Profit Lock
        elif self.trailing_stop_active and peak_gain_bps >= 25.0 and (peak_gain_bps - unrealized_bps) >= 12.0:
            exit_recommended = True
            exit_reason = f"TRAILING_STOP_PROFIT_LOCK (Peak +{peak_gain_bps:.1f} bps -> Now +{unrealized_bps:.1f} bps)"
            thesis_status = "TAKE_PROFIT"
        # 3. Horizon Timeout
        elif pos.minutes_held >= pos.target_horizon_minutes:
            exit_recommended = True
            exit_reason = f"HORIZON_COMPLETED_{pos.target_horizon_minutes}M"
            thesis_status = "TIMEOUT"
        # 4. Momentum Exhaustion / Lateness
        elif progress_ratio > 0.60 and unrealized_bps < 5.0:
            thesis_status = "LATE"

        return PositionRemainingValue(
            symbol=pos.symbol,
            current_price=current_price,
            unrealized_pnl_bps=unrealized_bps,
            unrealized_pnl_rupees=unrealized_rs,
            minutes_held=pos.minutes_held,
            remaining_minutes=remaining_mins,
            remaining_expected_gross_bps=round(remaining_expected_gross_bps, 2),
            remaining_expected_gross_rupees=remaining_expected_gross_rs,
            estimated_exit_cost_rupees=total_exit_cost,
            remaining_expected_net_rupees=remaining_expected_net_rs,
            remaining_expected_net_bps=remaining_expected_net_bps,
            risk_bps=25.0,
            thesis_status=thesis_status,
            exit_recommended=exit_recommended,
            exit_reason=exit_reason
        )

    # =========================================================================
    # ROTATION COMPARISON & EXECUTION
    # =========================================================================

    def _find_best_rotation_target(
        self,
        candidate: CandidateOpportunity,
        position_evals: Dict[str, PositionRemainingValue]
    ) -> Optional[RotationComparison]:
        """
        Finds if candidate has sufficient risk-adjusted net edge over any current holding
        to justify paying exit cost + new entry cost + rotation penalty.
        """
        if not self.active_positions:
            return None

        best_comparison: Optional[RotationComparison] = None
        max_advantage_bps = -999.0

        for sym, pos in self.active_positions.items():
            pos_eval = position_evals.get(sym)
            if not pos_eval:
                continue

            current_remaining_net = pos_eval.remaining_expected_net_rupees
            exit_cost = pos_eval.estimated_exit_cost_rupees
            entry_cost = candidate.total_entry_cost_rupees
            rot_penalty = self.rotation_penalty_rupees

            # Incremental net in ₹
            incremental_net = candidate.expected_net_rupees - current_remaining_net - exit_cost - entry_cost - rot_penalty

            # Convert to bps relative to candidate notional
            notional = candidate.notional_required if candidate.notional_required > 0 else (pos.entry_notional)
            adv_bps = (incremental_net / notional * 10000.0) if notional > 0 else 0.0

            # Affordability check: ensure released capital + available capital can purchase at least 1 share of candidate
            released_capital = pos.quantity * pos_eval.current_price
            est_available = (self.available_capital - self.min_cash_buffer_rupees) + released_capital - exit_cost
            can_afford = (est_available >= candidate.ltp)

            should_rotate = (
                can_afford and
                incremental_net > 0 and
                adv_bps >= self.rotation_min_advantage_bps and
                candidate.expected_net_rupees >= self.min_net_edge_rupees
            )

            rejection_reason = None
            if not should_rotate:
                if not can_afford:
                    rejection_reason = "CANNOT_AFFORD_SINGLE_SHARE"
                elif adv_bps < self.rotation_min_advantage_bps:
                    rejection_reason = "ROTATION_NOT_WORTH_COST"
                elif incremental_net <= 0:
                    rejection_reason = "INSUFFICIENT_EDGE"

            comp = RotationComparison(
                candidate_symbol=candidate.symbol,
                current_symbol=sym,
                candidate_expected_net=candidate.expected_net_rupees,
                current_remaining_expected_net=current_remaining_net,
                exit_cost_current=exit_cost,
                entry_cost_candidate=entry_cost,
                rotation_penalty=rot_penalty,
                incremental_net_rupees=round(incremental_net, 2),
                incremental_advantage_bps=round(adv_bps, 2),
                threshold_advantage_bps=self.rotation_min_advantage_bps,
                should_rotate=should_rotate,
                rejection_reason=rejection_reason
            )

            if adv_bps > max_advantage_bps:
                max_advantage_bps = adv_bps
                best_comparison = comp

        return best_comparison

    # =========================================================================
    # ORDER EXECUTION & CAPITAL MANAGEMENT HELPERS
    # =========================================================================

    def _enter_position(
        self,
        candidate: CandidateOpportunity,
        quantity: int,
        entry_time_str: str
    ) -> ActivePosition:
        """Executes position entry, deducting capital and registering holding."""
        self.trade_counter += 1
        pos_id = f"POS_{entry_time_str.replace(':', '')}_{self.trade_counter:03d}"
        notional = round(quantity * candidate.ltp, 2)

        # Dynamic stop loss and take profit
        stop_dist = candidate.ltp * (0.015)  # 1.5% stop loss
        tp_dist = candidate.ltp * (abs(candidate.calibrated_expected_return_bps * self.tp_multiplier) / 10000.0)

        pos = ActivePosition(
            position_id=pos_id,
            symbol=candidate.symbol,
            quantity=quantity,
            entry_price=candidate.ltp,
            entry_time=entry_time_str,
            entry_notional=notional,
            target_horizon_minutes=candidate.target_horizon_minutes,
            stop_loss_price=round(candidate.ltp - stop_dist, 2),
            take_profit_price=round(candidate.ltp + tp_dist, 2),
            expected_gross_bps=candidate.calibrated_expected_return_bps,
            expected_net_bps=candidate.expected_net_bps,
            expected_net_rupees=candidate.expected_net_rupees,
            entry_cost_rupees=candidate.total_entry_cost_rupees,
            supporting_models=candidate.supporting_models,
            sector=candidate.sector,
            minutes_held=0
        )

        # Deduct deployed capital
        self.available_capital -= notional
        self.active_positions[candidate.symbol] = pos
        logger.info(
            "[%s] ENTER %d shares of %s at ₹%.2f (Notional: ₹%.2f, Rem Cash: ₹%.2f)",
            entry_time_str, quantity, candidate.symbol, candidate.ltp, notional, self.available_capital
        )
        return pos

    def _close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_time: str,
        exit_reason: str,
        rotated_into: Optional[str] = None
    ) -> ClosedTradeRecord:
        """Closes an active position and immediately recycles released capital."""
        pos = self.active_positions.pop(symbol)
        exit_notional = round(pos.quantity * exit_price, 2)
        gross_pnl_rs = round(exit_notional - pos.entry_notional, 2)
        gross_pnl_bps = round((exit_price - pos.entry_price) / pos.entry_price * 10000.0, 2)

        # Exact roundtrip friction via IndiaCostEngine
        cb = self.cost_engine.calculate_roundtrip_cost(
            capital=pos.entry_notional, gross_return=gross_pnl_bps / 10000.0, slippage_bps=0.0
        )
        statutory_rs = round(cb.brokerage + cb.stt + cb.exchange_charges + cb.sebi_fees + cb.stamp_duty + cb.gst, 2)
        spread_rs = round(pos.entry_notional * (2.4 / 10000.0), 2)
        slippage_rs = round(pos.entry_notional * (2.0 / 10000.0), 2)
        impact_rs = round(pos.entry_notional * (1.0 / 10000.0), 2)
        friction_rs = round(spread_rs + slippage_rs + impact_rs, 2)
        total_cost_rs = round(statutory_rs + friction_rs, 2)

        net_pnl_rs = round(gross_pnl_rs - total_cost_rs, 2)
        net_pnl_bps = round((net_pnl_rs / pos.entry_notional * 10000.0), 2) if pos.entry_notional > 0 else 0.0

        # RECYCLE CAPITAL IMMEDIATELY: returned capital + net profit/loss
        capital_returned = pos.entry_notional + net_pnl_rs
        self.available_capital += capital_returned

        if self.cooldown_minutes > 0:
            try:
                hh, mm = map(int, exit_time[:5].split(":"))
                tot = hh * 60 + mm + self.cooldown_minutes
                self.cooldown_until[symbol] = f"{tot // 60:02d}:{tot % 60:02d}"
            except Exception:
                pass

        closed_rec = ClosedTradeRecord(
            trade_id=f"TRD_{pos.position_id}",
            symbol=symbol,
            entry_time=pos.entry_time,
            exit_time=exit_time,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            quantity=pos.quantity,
            notional=pos.entry_notional,
            gross_pnl_bps=gross_pnl_bps,
            gross_pnl_rupees=gross_pnl_rs,
            statutory_cost_rupees=statutory_rs,
            execution_friction_rupees=friction_rs,
            total_friction_rupees=total_cost_rs,
            net_pnl_bps=net_pnl_bps,
            net_pnl_rupees=net_pnl_rs,
            holding_minutes=pos.minutes_held,
            exit_reason=exit_reason,
            rotated_into=rotated_into,
            supporting_models=pos.supporting_models
        )
        self.closed_trades.append(closed_rec)
        logger.info(
            "[%s] EXIT %s (%s) at ₹%.2f | Net: ₹%+.2f (%+.1f bps) | Released: ₹%.2f | Cash: ₹%.2f",
            exit_time, symbol, exit_reason, exit_price, net_pnl_rs, net_pnl_bps, capital_returned, self.available_capital
        )
        return closed_rec

    def _force_eod_square_off(
        self,
        timestamp_str: str,
        universe_market_slice: Dict[str, Dict[str, Any]]
    ) -> List[ClosedTradeRecord]:
        """Forcibly squares off all open positions at EOD (15:25 IST)."""
        time_part = self._extract_time_str(timestamp_str)
        closed_records = []
        for sym in list(self.active_positions.keys()):
            pos = self.active_positions[sym]
            exit_p = float(universe_market_slice.get(sym, {}).get("ltp", pos.entry_price))
            rec = self._close_position(
                symbol=sym,
                exit_price=exit_p,
                exit_time=time_part,
                exit_reason="EOD_MANDATORY_SQUARE_OFF"
            )
            closed_records.append(rec)
        return closed_records

    # =========================================================================
    # SUMMARY & REPORTING
    # =========================================================================

    def generate_session_summary(self) -> Dict[str, Any]:
        """Generates comprehensive end-of-session performance metrics."""
        gross_pnl = sum(t.gross_pnl_rupees for t in self.closed_trades)
        total_costs = sum(t.total_friction_rupees for t in self.closed_trades)
        net_pnl = sum(t.net_pnl_rupees for t in self.closed_trades)
        wins = [t for t in self.closed_trades if t.net_pnl_rupees > 0]
        losses = [t for t in self.closed_trades if t.net_pnl_rupees < 0]
        win_rate = (len(wins) / len(self.closed_trades) * 100.0) if self.closed_trades else 0.0
        avg_holding = (sum(t.holding_minutes for t in self.closed_trades) / len(self.closed_trades)) if self.closed_trades else 0.0
        gross_profit = sum(t.net_pnl_rupees for t in wins)
        gross_loss = abs(sum(t.net_pnl_rupees for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        rotations = [t for t in self.closed_trades if t.exit_reason == "ROTATION_REPLACEMENT"]

        per_symbol_pnl: Dict[str, Dict[str, Any]] = {}
        for t in self.closed_trades:
            if t.symbol not in per_symbol_pnl:
                per_symbol_pnl[t.symbol] = {"trades": 0, "net_pnl": 0.0, "gross_pnl": 0.0, "costs": 0.0}
            per_symbol_pnl[t.symbol]["trades"] += 1
            per_symbol_pnl[t.symbol]["net_pnl"] += t.net_pnl_rupees
            per_symbol_pnl[t.symbol]["gross_pnl"] += t.gross_pnl_rupees
            per_symbol_pnl[t.symbol]["costs"] += t.total_friction_rupees

        return {
            "initial_capital": self.initial_capital,
            "ending_capital": round(self.available_capital, 2),
            "gross_pnl_rupees": round(gross_pnl, 2),
            "total_costs_rupees": round(total_costs, 2),
            "net_pnl_rupees": round(net_pnl, 2),
            "total_return_pct": round((net_pnl / self.initial_capital) * 100.0, 3),
            "total_trades": len(self.closed_trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": round(win_rate, 2),
            "average_trade_net_rupees": round(net_pnl / len(self.closed_trades), 2) if self.closed_trades else 0.0,
            "profit_factor": round(profit_factor, 2),
            "average_holding_time_minutes": round(avg_holding, 1),
            "total_rotations": len(rotations),
            "open_positions_remaining": len(self.active_positions),
            "calibration_factor_applied": self.calibration_factor,
            "per_symbol_breakdown": per_symbol_pnl
        }

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _extract_time_str(self, ts: str) -> str:
        """Extracts HH:MM string from ISO timestamp or returns as-is if already HH:MM."""
        if "T" in ts:
            part = ts.split("T")[1]
            return part[:5]
        return ts[:5]
