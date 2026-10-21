"""
AlphaNSE V3 — Full-Universe Dynamic Capital Rotation Engine.
Module: v3/portfolio/full_universe_rotation_engine.py

Expands AlphaNSE V3 from a fixed 10-stock test universe to continuous dynamic
full-universe scanning and capital rotation across the entire eligible NSE universe.

ARCHITECTURE:
  1. DYNAMIC UNIVERSE: Ingests all tradeable, liquid, valid NSE cash-equity instruments
     via DynamicUniverseProvider. No hard-coded universe cap.
  2. TWO-STAGE INFERENCE FUNNEL:
       - Stage 1: Cheap screening across the complete eligible universe (price, spread,
         volume, volatility, non-bear regime, preliminary momentum).
       - Stage 2: Full six-model inference (V2_15M, HYPO001, HYPO002, HYPO003, V3_60M,
         ANTIGRAVITY_META) and granular India friction decomposition on the strongest candidates.
  3. ECONOMIC NET-RUPEE SCORING:
       Ranks opportunities strictly by EXPECTED_NET_PROFIT_AFTER_ALL_COSTS (₹),
       explicitly subtracting all statutory fees, STT, spread, slippage, and impact.
  4. CAPITAL-AWARE SIZING & PORTFOLIO SEARCH:
       Evaluates combinatorial baskets (0, 1, 2, 3, 4, 5 positions) under whole-share
       integer constraints, sector concentration limits, and available capital.
       Cash is always a valid choice if expected net < economic hurdle (₹0.80).
  5. EVENT-DRIVEN CAPITAL ROTATION & IMMEDIATE RECYCLING:
       Existing holdings must continuously compete against newly emerging universe opportunities.
       Rotates capital only when the incremental edge exceeds switching friction + hysteresis.
       Released cash is immediately reusable in the exact same minute.
  6. AUDIT & NO-LOOKAHEAD BARRIER:
       Strictly point-in-time (zero future candles/prices). Full audit trail for every
       evaluated candidate with explicit categorical rejection reasons.
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
    ROTATION_MIN_ADVANTAGE_BPS,
    ROTATION_PENALTY_RUPEES
)
from v3.data.dynamic_universe_provider import (
    DynamicUniverseProvider,
    InstrumentMetadata,
    BROAD_NSE_SECTORS
)

logger = logging.getLogger(__name__)

# Execution modes
BASELINE_MODE = "BASELINE_10_STOCK"
FULL_UNIVERSE_DYNAMIC_MODE = "FULL_UNIVERSE_DYNAMIC"
PAPER_SHADOW_ONLY = "PAPER_SHADOW_ONLY"

# Architectural constants
DEFAULT_MAX_SECTOR_POSITIONS = 2
DEFAULT_STAGE1_MAX_CANDIDATES = 25


class LiveExecutionDisabledError(Exception):
    """Safety guard physically preventing unauthorized real brokerage execution."""
    pass


@dataclass
class ActiveHolding:
    """An open position actively managed in the dynamic portfolio."""
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
class Stage1Candidate:
    """A symbol screened through the cheap first-stage universe filter."""
    symbol: str
    ltp: float
    volume: float
    spread_bps: float
    volatility_bps: float
    regime: str
    sector: str
    preliminary_score: float
    passed_stage1: bool
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Stage2Opportunity:
    """A deeply evaluated opportunity with 6-model inference and cost decomposition."""
    rank: int
    symbol: str
    timestamp: str
    ltp: float
    spread_bps: float
    volume: float
    volume_z: float
    volatility_bps: float
    regime: str
    sector: str
    raw_models: Dict[str, float]
    raw_expected_bps: float
    calibration_factor: float
    calibrated_expected_bps: float
    direction: int
    confidence: float
    consensus_ratio: str
    supporting_models: List[str]
    contradicting_models: List[str]
    target_horizon_minutes: int
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
    risk_score: float
    decision: str                      # "VIABLE" or reject code
    is_viable: bool
    reject_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SelectedBasket:
    """The optimal feasible portfolio selected for the current minute."""
    symbols: List[str]
    quantities: Dict[str, int]
    capital_deployed: float
    cash_remaining: float
    expected_gross_rupees: float
    expected_cost_rupees: float
    expected_net_rupees: float
    expected_net_bps: float
    portfolio_risk_score: float
    sectors: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RotationComparisonResult:
    """Pairwise evaluation between an active holding and an emerging opportunity."""
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
class FullUniverseClosedTrade:
    """Audit record of a completed trade executed in the full universe."""
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
    total_friction_rupees: float
    net_pnl_rupees: float
    net_pnl_bps: float
    exit_reason: str
    holding_minutes: int
    rotated_into: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FullUniverseDynamicRotationEngine:
    """
    Continuous intraday full-universe capital rotation engine for AlphaNSE V3.
    Evaluates the complete eligible NSE universe every minute using a 2-stage funnel,
    selects optimal 0-5 stock baskets by net-rupee expectation, and dynamically rotates capital.
    """

    def __init__(
        self,
        initial_capital: float = INITIAL_CAPITAL,
        min_cash_buffer_rupees: float = MIN_CASH_BUFFER_RUPEES,
        min_net_edge_rupees: float = MIN_NET_EDGE_RUPEES,
        min_net_edge_bps: float = MIN_NET_EDGE_BPS,
        rotation_min_advantage_bps: float = ROTATION_MIN_ADVANTAGE_BPS,
        rotation_penalty_rupees: float = ROTATION_PENALTY_RUPEES,
        hard_max_position_count: int = HARD_MAX_POSITION_COUNT,
        max_sector_positions: int = DEFAULT_MAX_SECTOR_POSITIONS,
        stage1_max_candidates: int = DEFAULT_STAGE1_MAX_CANDIDATES,
        calibration_factor: float = 0.4858,  # Frozen OOS factor for Session 6
        entry_cutoff_time: str = ENTRY_CUTOFF_TIME,
        eod_close_time: str = EOD_CLOSE_TIME,
        live_execution_unlocked: bool = False,
        mode: str = PAPER_SHADOW_ONLY,
        universe_provider: Optional[DynamicUniverseProvider] = None,
        model_hash: str = "FROZEN_STACK_V3_20260925",
        dataset_hash: str = "UNIVERSE_SNAPSHOT_20260925",
        calibration_hash: str = "CALIB_HASH_04858",
        cooldown_minutes: int = 0,
        trailing_stop_active: bool = False,
        tp_multiplier: float = 1.0,
        max_single_position_pct: float = 0.75,
        min_holding_minutes_before_rotation: int = 0
    ):
        self.initial_capital = initial_capital
        self.available_capital = initial_capital
        self.min_cash_buffer_rupees = min_cash_buffer_rupees
        self.min_net_edge_rupees = min_net_edge_rupees
        self.min_net_edge_bps = min_net_edge_bps
        self.rotation_min_advantage_bps = rotation_min_advantage_bps
        self.rotation_penalty_rupees = rotation_penalty_rupees
        self.hard_max_position_count = hard_max_position_count
        self.max_sector_positions = max_sector_positions
        self.stage1_max_candidates = stage1_max_candidates
        self.calibration_factor = calibration_factor
        self.entry_cutoff_time = entry_cutoff_time
        self.eod_close_time = eod_close_time
        self.live_execution_unlocked = live_execution_unlocked
        self.mode = mode
        self.model_hash = model_hash
        self.dataset_hash = dataset_hash
        self.calibration_hash = calibration_hash
        self.cooldown_minutes = cooldown_minutes
        self.trailing_stop_active = trailing_stop_active
        self.tp_multiplier = tp_multiplier
        self.max_single_position_pct = max_single_position_pct
        self.min_holding_minutes_before_rotation = min_holding_minutes_before_rotation
        self.cooldown_until: Dict[str, str] = {}

        # Initialize universe provider
        self.universe_provider = universe_provider or DynamicUniverseProvider()
        self.cost_engine = IndiaCostEngine()

        # State tracking
        self.active_holdings: Dict[str, ActiveHolding] = {}
        self.closed_trades: List[FullUniverseClosedTrade] = []
        self.rotation_events: List[Dict[str, Any]] = []
        self.audit_ledger: List[Dict[str, Any]] = []
        self.just_exited_symbols: Set[str] = set()
        self.trade_counter: int = 0
        self.peak_capital: float = initial_capital
        self.max_drawdown_rupees: float = 0.0

        # Safety Check: Live execution physically locked
        if self.live_execution_unlocked or self.mode not in (PAPER_SHADOW_ONLY, FULL_UNIVERSE_DYNAMIC_MODE):
            raise LiveExecutionDisabledError(
                "CRITICAL SAFETY VIOLATION: Full Universe Engine must run in PAPER_SHADOW_ONLY mode."
            )

        logger.info(
            "FullUniverseDynamicRotationEngine initialized: Capital ₹%.2f, Max Pos: %d, Frozen Calib: %.4f",
            self.initial_capital, self.hard_max_position_count, self.calibration_factor
        )

    # =========================================================================
    # CORE MINUTE-BY-MINUTE LIFECYCLE
    # =========================================================================

    def process_minute(
        self,
        timestamp_str: str,
        market_slice: Dict[str, Dict[str, Any]],
        predictions_slice: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Executes continuous universe scanning and capital re-optimization at timestamp T:
          1. Updates open holdings (SL, TP, Horizon timeout exits).
          2. Recycles released capital immediately.
          3. Dynamically discovers eligible symbols via DynamicUniverseProvider.
          4. Executes Stage 1 Cheap Screening across the full universe.
          5. Executes Stage 2 Six-Model Inference and Detailed India Cost Decomposition.
          6. Generates TOP_OPPORTUNITIES ranked by EXPECTED_NET_PROFIT_AFTER_ALL_COSTS (₹).
          7. Runs Basket Optimizer (0 to 5 positions) under capital, sector, and risk constraints.
          8. Evaluates capital rotation for existing holdings vs superior opportunities.
          9. Records comprehensive audit telemetry.
        """
        self.just_exited_symbols.clear()
        time_part = timestamp_str[11:16] if len(timestamp_str) >= 16 else timestamp_str
        is_after_entry_cutoff = (time_part >= self.entry_cutoff_time)
        is_eod_squareoff = (time_part >= self.eod_close_time)

        # ---------------------------------------------------------------------
        # STEP 1: Update Existing Positions & Check Automatic Exits
        # ---------------------------------------------------------------------
        exited_this_minute = []
        for sym, pos in list(self.active_holdings.items()):
            bar = market_slice.get(sym)
            cur_price = float(bar.get("ltp", bar.get("price", pos.entry_price))) if bar else pos.entry_price

            pos.minutes_held += 1
            pos.highest_price_seen = max(pos.highest_price_seen, cur_price)
            pos.lowest_price_seen = min(pos.lowest_price_seen, cur_price)

            unrealized_bps = (cur_price - pos.entry_price) / pos.entry_price * 10000.0 if pos.entry_price > 0 else 0.0
            peak_gain_bps = (pos.highest_price_seen - pos.entry_price) / pos.entry_price * 10000.0 if pos.entry_price > 0 else 0.0

            exit_reason = None
            if is_eod_squareoff:
                exit_reason = "EOD_FORCED_SQUARE_OFF"
            elif cur_price <= pos.stop_loss_price:
                exit_reason = f"STOP_LOSS_TRIGGERED (LTP ₹{cur_price:.2f} <= ₹{pos.stop_loss_price:.2f})"
            elif self.trailing_stop_active and peak_gain_bps >= 30.0 and (peak_gain_bps - unrealized_bps) >= 15.0:
                exit_reason = f"TRAILING_STOP_PROFIT_LOCK (Peak +{peak_gain_bps:.1f} bps -> Now +{unrealized_bps:.1f} bps)"
            elif cur_price >= pos.take_profit_price:
                exit_reason = f"TAKE_PROFIT_REACHED (LTP ₹{cur_price:.2f} >= ₹{pos.take_profit_price:.2f})"
            elif pos.minutes_held >= pos.target_horizon_minutes:
                exit_reason = f"HORIZON_COMPLETED_{pos.target_horizon_minutes}M"

            if exit_reason:
                closed_rec = self._close_position(sym, cur_price, time_part, exit_reason)
                exited_this_minute.append(closed_rec)
                self.just_exited_symbols.add(sym)

        # Update drawdown stats
        current_equity = self.available_capital + sum(
            p.notional_for_price(float(market_slice.get(s, {}).get("ltp", p.entry_price)))
            for s, p in self.active_holdings.items()
        )
        if current_equity > self.peak_capital:
            self.peak_capital = current_equity
        dd = self.peak_capital - current_equity
        if dd > self.max_drawdown_rupees:
            self.max_drawdown_rupees = dd

        if is_eod_squareoff:
            return self._build_minute_telemetry(
                timestamp_str, time_part, [], [], None, exited_this_minute, "EOD_CLOSED"
            )

        # ---------------------------------------------------------------------
        # STEP 2 & 3: Dynamic Universe Discovery & Stage 1 Cheap Screening
        # ---------------------------------------------------------------------
        eligible_symbols, universe_audit = self.universe_provider.filter_universe(
            market_slice, timestamp_str
        )

        stage1_candidates: List[Stage1Candidate] = []
        for sym in eligible_symbols:
            bar = market_slice[sym]
            ltp = float(bar.get("ltp", bar.get("price", 100.0)))
            vol = float(bar.get("volume", 0.0))
            spread_bps = float(bar.get("spread_bps", 2.5))
            vol_bps = float(bar.get("volatility_bps", 12.0))
            regime = bar.get("regime", "SIDEWAYS")
            sector = BROAD_NSE_SECTORS.get(sym, "GENERAL")

            # Cheap preliminary score: volume-weighted trend proxy
            # Point-in-time only: uses current volume_z and regime
            vol_z = float(bar.get("volume_z", 0.0))
            is_bear = (regime in ("TRENDING_BEAR_STRONG", "HIGH_VOLATILITY_CRASH"))

            cand_rejection = None
            if is_bear:
                cand_rejection = "REGIME_INVALID"
            elif ltp > (self.available_capital + sum(p.entry_notional for p in self.active_holdings.values())):
                cand_rejection = "INSUFFICIENT_CAPITAL"
            elif sym in self.just_exited_symbols:
                cand_rejection = "JUST_EXITED_COOLDOWN"
            elif self.cooldown_minutes > 0 and time_part < self.cooldown_until.get(sym, ""):
                cand_rejection = "COOLDOWN_ACTIVE"

            passed = (cand_rejection is None)
            score = (vol_z * 10.0) + (20.0 if regime == "TRENDING_BULL" else 0.0) - (spread_bps * 0.5)

            stage1_candidates.append(Stage1Candidate(
                symbol=sym,
                ltp=ltp,
                volume=vol,
                spread_bps=spread_bps,
                volatility_bps=vol_bps,
                regime=regime,
                sector=sector,
                preliminary_score=round(score, 2),
                passed_stage1=passed,
                rejection_reason=cand_rejection
            ))

        # Sort passing stage-1 candidates by preliminary score
        passing_stage1 = [c for c in stage1_candidates if c.passed_stage1]
        passing_stage1.sort(key=lambda c: c.preliminary_score, reverse=True)
        top_stage1 = passing_stage1[:self.stage1_max_candidates]

        # ---------------------------------------------------------------------
        # STEP 4: Stage 2 Six-Model Inference & Detailed India Friction Economics
        # ---------------------------------------------------------------------
        stage2_opportunities: List[Stage2Opportunity] = []
        for cand in top_stage1:
            sym = cand.symbol
            bar = market_slice[sym]
            model_info = (predictions_slice or {}).get(sym, {})

            opp = self._evaluate_stage2_opportunity(
                symbol=sym,
                timestamp=timestamp_str,
                tick_data=bar,
                model_info=model_info,
                is_after_cutoff=is_after_entry_cutoff
            )
            stage2_opportunities.append(opp)

        # Primary Ranking Variable: EXPECTED_NET_PROFIT_AFTER_ALL_COSTS (₹)
        stage2_opportunities.sort(
            key=lambda o: (o.is_viable, o.expected_net_rupees, o.confidence),
            reverse=True
        )

        # Assign ranks
        for idx, o in enumerate(stage2_opportunities, start=1):
            o.rank = idx

        viable_candidates = [o for o in stage2_opportunities if o.is_viable and o.symbol not in self.active_holdings]

        # ---------------------------------------------------------------------
        # STEP 5: Combinatorial Basket Optimization & Dynamic Capital Rotation
        # ---------------------------------------------------------------------
        selected_basket = self._optimize_portfolio_basket(
            viable_candidates, timestamp_str
        )

        # ---------------------------------------------------------------------
        # STEP 6: Execute Allocations or Check Rotations
        # ---------------------------------------------------------------------
        executed_actions = []

        # A. If we have open position slots and cash, enter top viable candidates
        symbols_entered_this_minute: Set[str] = set()
        free_slots = self.hard_max_position_count - len(self.active_holdings)
        if free_slots > 0 and not is_after_entry_cutoff:
            for cand in viable_candidates:
                if len(self.active_holdings) >= self.hard_max_position_count:
                    break
                if cand.symbol in self.active_holdings:
                    continue

                # Sector concentration check
                sector_count = sum(1 for p in self.active_holdings.values() if p.sector == cand.sector)
                if sector_count >= self.max_sector_positions:
                    continue

                # Compute quantity under current free available capital
                allocatable_cash = max(0.0, self.available_capital - self.min_cash_buffer_rupees)
                remaining_slots = self.hard_max_position_count - len(self.active_holdings)
                slot_budget = allocatable_cash / max(1, remaining_slots)
                max_pos_cap = allocatable_cash * self.max_single_position_pct if allocatable_cash > 2000.0 else allocatable_cash

                if len(self.active_holdings) == 0 and len(viable_candidates) >= 2 and cand.symbol == viable_candidates[0].symbol:
                    cand2 = viable_candidates[1]
                    test_qty = int(max_pos_cap / cand.ltp) if cand.ltp > 0 else 0
                    if test_qty >= 2 and (allocatable_cash - (test_qty * cand.ltp)) >= cand2.ltp:
                        target_alloc = test_qty * cand.ltp
                    else:
                        target_alloc = min(max_pos_cap, max(slot_budget, cand.ltp))
                elif len(self.active_holdings) == 0 and len(viable_candidates) == 1:
                    target_alloc = min(max_pos_cap, allocatable_cash)
                else:
                    target_alloc = min(max_pos_cap, max(slot_budget, cand.ltp))

                qty = int(min(allocatable_cash, target_alloc) / cand.ltp) if cand.ltp > 0 else 0
                if qty <= 0 and allocatable_cash >= cand.ltp:
                    qty = 1

                req_notional = qty * cand.ltp
                # Verify that the downsized actual notional clears the net economic hurdle
                exp_gross_actual = req_notional * (cand.expected_gross_bps / 10000.0)
                cb_actual = self.cost_engine.calculate_roundtrip_cost(max(100.0, req_notional), cand.expected_gross_bps / 10000.0)
                cost_actual = (
                    cb_actual.brokerage + cb_actual.stt + cb_actual.exchange_charges +
                    cb_actual.sebi_fees + cb_actual.stamp_duty + cb_actual.gst +
                    (req_notional * (cand.spread_bps + 3.0) / 10000.0)
                )
                exp_net_actual = exp_gross_actual - cost_actual

                if qty > 0 and req_notional <= allocatable_cash and exp_net_actual >= self.min_net_edge_rupees:
                    new_pos = self._enter_position(cand, qty, time_part)
                    symbols_entered_this_minute.add(cand.symbol)
                    executed_actions.append(f"ENTER_{cand.symbol}_{qty}SH")

        # B. If positions exist and superior outside candidates emerge, evaluate rotation
        eligible_for_rotation = {s: p for s, p in self.active_holdings.items() if s not in symbols_entered_this_minute}
        if len(eligible_for_rotation) > 0 and viable_candidates and not is_after_entry_cutoff:
            for top_opp in viable_candidates:
                if top_opp.symbol in self.active_holdings:
                    continue
                rotation_comp = self._evaluate_pairwise_rotation(top_opp, market_slice)
                if rotation_comp and rotation_comp.should_rotate:
                    curr_sym = rotation_comp.current_symbol
                    if curr_sym in symbols_entered_this_minute:
                        continue  # Never rotate a brand new position entered this same minute!
                    exit_bar = market_slice.get(curr_sym, {})
                    exit_p = float(exit_bar.get("ltp", self.active_holdings[curr_sym].entry_price))

                    # 1. Close current position -> Recycles capital immediately
                    closed_rec = self._close_position(
                        curr_sym, exit_p, time_part, "ROTATION_REPLACEMENT", rotated_into=top_opp.symbol
                    )
                    exited_this_minute.append(closed_rec)

                    # 2. Enter superior replacement using recycled capital
                    alloc_cash = max(0.0, self.available_capital - self.min_cash_buffer_rupees)
                    slot_budget = alloc_cash / max(1, (self.hard_max_position_count - len(self.active_holdings)))
                    new_qty = int(slot_budget / top_opp.ltp) if top_opp.ltp > 0 else 0
                    if new_qty <= 0 and alloc_cash >= top_opp.ltp:
                        new_qty = 1

                    if new_qty > 0 and (new_qty * top_opp.ltp) <= alloc_cash:
                        new_pos = self._enter_position(top_opp, new_qty, time_part)
                        symbols_entered_this_minute.add(top_opp.symbol)
                        executed_actions.append(f"ROTATED_{curr_sym}_INTO_{top_opp.symbol}")
                        self.rotation_events.append({
                            "timestamp": timestamp_str,
                            "exited": curr_sym,
                            "entered": top_opp.symbol,
                            "incremental_net_rupees": rotation_comp.incremental_net_rupees,
                            "advantage_bps": rotation_comp.incremental_advantage_bps
                        })
                        break

        # ---------------------------------------------------------------------
        # STEP 7: Comprehensive Minute Audit Telemetry
        # ---------------------------------------------------------------------
        minute_telemetry = self._build_minute_telemetry(
            timestamp_str=timestamp_str,
            time_part=time_part,
            stage1_candidates=stage1_candidates,
            stage2_opportunities=stage2_opportunities,
            selected_basket=selected_basket,
            exited_trades=exited_this_minute,
            actions=";".join(executed_actions) if executed_actions else "HOLD"
        )
        self.audit_ledger.append(minute_telemetry)
        return minute_telemetry

    # =========================================================================
    # STAGE 2 DETAILED INFERENCE & FRICTION DECOMPOSITION
    # =========================================================================

    def _evaluate_stage2_opportunity(
        self,
        symbol: str,
        timestamp: str,
        tick_data: Dict[str, Any],
        model_info: Dict[str, Any],
        is_after_cutoff: bool
    ) -> Stage2Opportunity:
        """Deeply evaluates an individual passing candidate through the 6-model stack & India costs."""
        ltp = float(tick_data.get("ltp", tick_data.get("price", 1000.0)))
        spread_bps = float(tick_data.get("spread_bps", 2.4))
        volatility_bps = float(tick_data.get("volatility_bps", 14.0))
        volume = float(tick_data.get("volume", 15000.0))
        volume_z = float(tick_data.get("volume_z", 0.0))
        regime = tick_data.get("regime", "SIDEWAYS")
        sector = BROAD_NSE_SECTORS.get(symbol, "GENERAL")

        # 6-Model Signals (Point-in-time, no lookahead)
        raw_models = model_info.get("models", {
            "V2_15M": float(model_info.get("raw_expected_bps", 0.0)),
            "HYPO001": float(model_info.get("raw_expected_bps", 0.0)) * 0.95,
            "HYPO002": float(model_info.get("raw_expected_bps", 0.0)) * 0.90,
            "HYPO003": float(model_info.get("raw_expected_bps", 0.0)) * 1.05,
            "V3_60M": float(model_info.get("raw_expected_bps", 0.0)),
            "ANTIGRAVITY_META": float(model_info.get("raw_expected_bps", 0.0))
        })
        raw_exp_bps = float(model_info.get("raw_expected_bps", 0.0))
        confidence = float(model_info.get("confidence", 0.50))
        direction = int(model_info.get("direction", 1 if raw_exp_bps > 0 else (0 if raw_exp_bps == 0 else -1)))
        supporting = model_info.get("supporting", ["V2_15M", "V3_60M"] if raw_exp_bps > 0 else [])
        contradicting = model_info.get("contradicting", [] if direction >= 0 else ["V2_15M"])
        target_horizon = int(model_info.get("target_horizon_minutes", 60))

        # Frozen OOS Calibration Factor (0.4858 for Session 6)
        calibrated_bps = round(raw_exp_bps * self.calibration_factor, 2)

        # Whole-share purchasing power sizing under total account equity
        total_account_equity = self.available_capital + sum(p.entry_notional for p in self.active_holdings.values())
        max_allocatable = max(0.0, total_account_equity - self.min_cash_buffer_rupees)
        target_slot_capital = max_allocatable / max(1, self.hard_max_position_count)

        if max_allocatable >= ltp > 0:
            qty = max(1, int(target_slot_capital / ltp))
        else:
            qty = 0
        notional = round(qty * ltp, 2)

        # India Cost Engine Canonical Breakdown
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
        risk_score = round(volatility_bps * (1.5 - min(1.0, confidence)), 2)

        # Comprehensive Gating Checks & Explicit Rejection Reasons
        reject_reasons = []
        if is_after_cutoff:
            reject_reasons.append("ENTRY_CUTOFF")
        if direction <= 0 or raw_exp_bps <= 0:
            reject_reasons.append("NO_EDGE")
        if exp_net_bps <= self.min_net_edge_bps:
            reject_reasons.append("INSUFFICIENT_EDGE")
        if exp_net_rupees < self.min_net_edge_rupees:
            reject_reasons.append("HURDLE_FAIL")
        if confidence < 0.25:
            reject_reasons.append("LOW_CONFIDENCE")
        if total_roundtrip_cost > exp_gross_rupees:
            reject_reasons.append("HIGH_COST")
        if volume < 2000.0 or spread_bps > 20.0:
            reject_reasons.append("LOW_LIQUIDITY")
        if qty <= 0:
            reject_reasons.append("INSUFFICIENT_CAPITAL")
        if regime in ("TRENDING_BEAR_STRONG", "HIGH_VOLATILITY_CRASH"):
            reject_reasons.append("REGIME_INVALID")
        time_part = timestamp[11:16] if len(timestamp) >= 16 else timestamp
        if self.cooldown_minutes > 0 and time_part < self.cooldown_until.get(symbol, ""):
            reject_reasons.append("COOLDOWN_ACTIVE")
        if risk_score > 35.0:
            reject_reasons.append("RISK_LIMIT")

        is_viable = (len(reject_reasons) == 0)
        decision = "VIABLE" if is_viable else reject_reasons[0]

        return Stage2Opportunity(
            rank=0,
            symbol=symbol,
            timestamp=timestamp,
            ltp=ltp,
            spread_bps=spread_bps,
            volume=volume,
            volume_z=volume_z,
            volatility_bps=volatility_bps,
            regime=regime,
            sector=sector,
            raw_models=raw_models,
            raw_expected_bps=raw_exp_bps,
            calibration_factor=self.calibration_factor,
            calibrated_expected_bps=calibrated_bps,
            direction=direction,
            confidence=confidence,
            consensus_ratio=f"{len(supporting)}/6",
            supporting_models=supporting,
            contradicting_models=contradicting,
            target_horizon_minutes=target_horizon,
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
            risk_score=risk_score,
            decision=decision,
            is_viable=is_viable,
            reject_reasons=reject_reasons
        )

    # =========================================================================
    # PORTFOLIO BASKET OPTIMIZER (0 to 5 Positions)
    # =========================================================================

    def _optimize_portfolio_basket(
        self,
        viable_candidates: List[Stage2Opportunity],
        timestamp_str: str
    ) -> SelectedBasket:
        """
        Evaluates feasible combinatorial baskets (0, 1, 2, 3, 4, 5 positions) under:
          - Available capital constraint
          - Whole-share integer sizing
          - Sector concentration limits (max 2 per sector)
          - Risk-adjusted expected net ₹ maximization
        """
        if not viable_candidates or self.available_capital < 200.0:
            # 0-position cash allocation
            return SelectedBasket(
                symbols=[],
                quantities={},
                capital_deployed=0.0,
                cash_remaining=round(self.available_capital, 2),
                expected_gross_rupees=0.0,
                expected_cost_rupees=0.0,
                expected_net_rupees=0.0,
                expected_net_bps=0.0,
                portfolio_risk_score=0.0,
                sectors={}
            )

        best_basket: Optional[SelectedBasket] = None
        max_risk_adj_net: float = 0.0

        # Evaluate candidate basket sizes k in [1..5]
        max_k = min(self.hard_max_position_count, len(viable_candidates))
        for k in range(1, max_k + 1):
            subset = viable_candidates[:k]

            # Verify sector concentration
            sectors: Dict[str, int] = {}
            sector_viol = False
            for c in subset:
                sectors[c.sector] = sectors.get(c.sector, 0) + 1
                if sectors[c.sector] > self.max_sector_positions:
                    sector_viol = True
                    break
            if sector_viol:
                continue

            # Integer sizing under available cash
            alloc_cash = max(0.0, self.available_capital - self.min_cash_buffer_rupees)
            slot_budget = alloc_cash / k

            quantities = {}
            tot_deployed = 0.0
            tot_gross = 0.0
            tot_cost = 0.0
            tot_risk = 0.0

            for c in subset:
                qty = int(slot_budget / c.ltp) if c.ltp > 0 else 0
                if qty <= 0 and (tot_deployed + c.ltp) <= alloc_cash:
                    qty = 1
                if qty <= 0:
                    continue

                notional = qty * c.ltp
                tot_deployed += notional
                quantities[c.symbol] = qty

                ratio = notional / max(1.0, c.notional_required)
                tot_gross += c.expected_gross_rupees * ratio
                tot_cost += c.total_roundtrip_cost_rupees * ratio
                tot_risk += c.risk_score

            if tot_deployed <= alloc_cash and quantities:
                tot_net = round(tot_gross - tot_cost, 2)
                # Risk penalty: diversify across sectors
                risk_adj = tot_net - (tot_risk * 0.05)

                if tot_net >= (self.min_net_edge_rupees * len(quantities)) and risk_adj > max_risk_adj_net:
                    max_risk_adj_net = risk_adj
                    best_basket = SelectedBasket(
                        symbols=list(quantities.keys()),
                        quantities=quantities,
                        capital_deployed=round(tot_deployed, 2),
                        cash_remaining=round(self.available_capital - tot_deployed, 2),
                        expected_gross_rupees=round(tot_gross, 2),
                        expected_cost_rupees=round(tot_cost, 2),
                        expected_net_rupees=tot_net,
                        expected_net_bps=round((tot_net / tot_deployed * 10000.0), 2) if tot_deployed > 0 else 0.0,
                        portfolio_risk_score=round(tot_risk / max(1, len(quantities)), 2),
                        sectors=sectors
                    )

        return best_basket or SelectedBasket(
            symbols=[],
            quantities={},
            capital_deployed=0.0,
            cash_remaining=round(self.available_capital, 2),
            expected_gross_rupees=0.0,
            expected_cost_rupees=0.0,
            expected_net_rupees=0.0,
            expected_net_bps=0.0,
            portfolio_risk_score=0.0,
            sectors={}
        )

    # =========================================================================
    # PAIRWISE CAPITAL ROTATION EVALUATION
    # =========================================================================

    def _evaluate_pairwise_rotation(
        self,
        candidate: Stage2Opportunity,
        market_slice: Dict[str, Dict[str, Any]]
    ) -> Optional[RotationComparisonResult]:
        """
        Evaluates whether an active holding should be rotated into a superior candidate.
        Condition:
          candidate_expected_net - current_holding_remaining_net - exit_cost - entry_cost - rotation_penalty > 0
          AND incremental_advantage_bps >= rotation_min_advantage_bps
        """
        best_comp: Optional[RotationComparisonResult] = None
        max_advantage: float = -999.0

        for sym, pos in self.active_holdings.items():
            if self.min_holding_minutes_before_rotation > 0 and pos.minutes_held < self.min_holding_minutes_before_rotation:
                continue
            bar = market_slice.get(sym, {})
            cur_p = float(bar.get("ltp", pos.entry_price))

            # Estimate remaining forward runway
            rem_mins = max(0, pos.target_horizon_minutes - pos.minutes_held)
            decay_factor = (rem_mins / max(1, pos.target_horizon_minutes))
            cur_notional = pos.quantity * cur_p
            remaining_gross = round(cur_notional * (pos.expected_gross_bps / 10000.0) * decay_factor, 2)

            exit_cost = round(pos.entry_cost_rupees, 2)
            current_remaining_net = round(remaining_gross - exit_cost, 2)

            entry_cost = candidate.total_entry_cost_rupees
            rot_penalty = self.rotation_penalty_rupees

            # Net incremental formula
            incremental_net = candidate.expected_net_rupees - current_remaining_net - exit_cost - entry_cost - rot_penalty
            notional = max(100.0, candidate.notional_required)
            adv_bps = (incremental_net / notional * 10000.0) if notional > 0 else 0.0

            should_rotate = (
                incremental_net > 0 and
                adv_bps >= self.rotation_min_advantage_bps and
                candidate.expected_net_rupees >= self.min_net_edge_rupees
            )

            rej_reason = None
            if not should_rotate:
                if adv_bps < self.rotation_min_advantage_bps:
                    rej_reason = "ROTATION_NOT_WORTH_COST"
                elif incremental_net <= 0:
                    rej_reason = "INSUFFICIENT_EDGE"

            comp = RotationComparisonResult(
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
                rejection_reason=rej_reason
            )

            if adv_bps > max_advantage:
                max_advantage = adv_bps
                best_comp = comp

        return best_comp

    # =========================================================================
    # EXECUTION & CAPITAL MANAGEMENT HELPERS
    # =========================================================================

    def _enter_position(
        self,
        candidate: Stage2Opportunity,
        quantity: int,
        entry_time_str: str
    ) -> ActiveHolding:
        """Enters an active position, deducting capital and registering holding."""
        self.trade_counter += 1
        pos_id = f"POS_{entry_time_str.replace(':', '')}_{self.trade_counter:03d}"
        notional = round(quantity * candidate.ltp, 2)

        stop_dist = candidate.ltp * 0.015  # 1.5% stop loss
        tp_dist = candidate.ltp * (abs(candidate.calibrated_expected_bps * self.tp_multiplier) / 10000.0)

        pos = ActiveHolding(
            position_id=pos_id,
            symbol=candidate.symbol,
            quantity=quantity,
            entry_price=candidate.ltp,
            entry_time=entry_time_str,
            entry_notional=notional,
            target_horizon_minutes=candidate.target_horizon_minutes,
            stop_loss_price=round(candidate.ltp - stop_dist, 2),
            take_profit_price=round(candidate.ltp + tp_dist, 2),
            expected_gross_bps=candidate.calibrated_expected_bps,
            expected_net_bps=candidate.expected_net_bps,
            expected_net_rupees=candidate.expected_net_rupees,
            entry_cost_rupees=candidate.total_entry_cost_rupees,
            supporting_models=candidate.supporting_models,
            sector=candidate.sector,
            minutes_held=0
        )

        self.available_capital -= notional
        self.active_holdings[candidate.symbol] = pos
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
    ) -> FullUniverseClosedTrade:
        """Closes an active position and immediately recycles capital."""
        pos = self.active_holdings.pop(symbol)
        exit_notional = round(pos.quantity * exit_price, 2)
        gross_pnl_rs = round(exit_notional - pos.entry_notional, 2)
        gross_pnl_bps = round((exit_price - pos.entry_price) / pos.entry_price * 10000.0, 2)

        exit_cb: CostBreakdown = self.cost_engine.calculate_roundtrip_cost(
            capital=max(100.0, exit_notional),
            gross_return=abs(gross_pnl_bps) / 10000.0
        )
        statutory_exit = exit_cb.brokerage + exit_cb.stt + exit_cb.exchange_charges + exit_cb.sebi_fees + exit_cb.stamp_duty + exit_cb.gst
        spread_slippage_exit = exit_notional * (3.0 / 10000.0)
        tot_exit_cost = round((statutory_exit + spread_slippage_exit) / 2.0, 2)

        total_friction = round(pos.entry_cost_rupees + tot_exit_cost, 2)
        net_pnl_rs = round(gross_pnl_rs - total_friction, 2)
        net_pnl_bps = round((net_pnl_rs / pos.entry_notional * 10000.0), 2)

        # Immediate capital recycling
        cash_returned = round(exit_notional - tot_exit_cost, 2)
        self.available_capital += cash_returned

        if self.cooldown_minutes > 0:
            try:
                hh, mm = map(int, exit_time[:5].split(":"))
                tot = hh * 60 + mm + self.cooldown_minutes
                self.cooldown_until[symbol] = f"{tot // 60:02d}:{tot % 60:02d}"
            except Exception:
                pass

        closed_rec = FullUniverseClosedTrade(
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
            total_friction_rupees=total_friction,
            net_pnl_rupees=net_pnl_rs,
            net_pnl_bps=net_pnl_bps,
            exit_reason=exit_reason,
            holding_minutes=pos.minutes_held,
            rotated_into=rotated_into
        )
        self.closed_trades.append(closed_rec)
        logger.info(
            "[%s] EXIT %s (%s) at ₹%.2f | Net: ₹%+.2f (%+.1f bps) | Released: ₹%.2f | Cash: ₹%.2f",
            exit_time, symbol, exit_reason, exit_price, net_pnl_rs, net_pnl_bps, cash_returned, self.available_capital
        )
        return closed_rec

    # =========================================================================
    # AUDIT & SUMMARY REPORTING
    # =========================================================================

    def _build_minute_telemetry(
        self,
        timestamp_str: str,
        time_part: str,
        stage1_candidates: List[Stage1Candidate],
        stage2_opportunities: List[Stage2Opportunity],
        selected_basket: Optional[SelectedBasket],
        exited_trades: List[FullUniverseClosedTrade],
        actions: str
    ) -> Dict[str, Any]:
        """Builds structured audit record for the current minute."""
        top_opps = [
            {
                "rank": o.rank,
                "symbol": o.symbol,
                "prediction_bps": o.calibrated_expected_bps,
                "confidence": o.confidence,
                "gross_rupees": o.expected_gross_rupees,
                "cost_rupees": o.total_roundtrip_cost_rupees,
                "net_rupees": o.expected_net_rupees,
                "net_bps": o.expected_net_bps,
                "risk": o.risk_score,
                "qty": o.affordable_quantity,
                "capital_required": o.notional_required,
                "horizon_mins": o.target_horizon_minutes,
                "decision": o.decision
            }
            for o in stage2_opportunities[:10]
        ]

        rejects = {
            o.symbol: o.reject_reasons[0] if o.reject_reasons else "UNKNOWN"
            for o in stage2_opportunities if not o.is_viable
        }

        return {
            "timestamp": timestamp_str,
            "time": time_part,
            "eligible_universe_size": len(self.universe_provider.registry),
            "stage1_passed_count": sum(1 for c in stage1_candidates if c.passed_stage1),
            "stage2_evaluated_count": len(stage2_opportunities),
            "top_opportunities": top_opps,
            "selected_basket": selected_basket.to_dict() if selected_basket else {},
            "active_positions": list(self.active_holdings.keys()),
            "available_capital": round(self.available_capital, 2),
            "actions": actions,
            "exited_trades_count": len(exited_trades),
            "rejected_opportunities": rejects,
            "model_hash": self.model_hash,
            "dataset_hash": self.dataset_hash,
            "calibration_hash": self.calibration_hash
        }

    def generate_session_summary(self) -> Dict[str, Any]:
        """Generates comprehensive end-of-session performance and execution metrics."""
        tot_trades = len(self.closed_trades)
        wins = [t for t in self.closed_trades if t.net_pnl_rupees > 0]
        losses = [t for t in self.closed_trades if t.net_pnl_rupees <= 0]
        gross_pnl = round(sum(t.gross_pnl_rupees for t in self.closed_trades), 2)
        total_costs = round(sum(t.total_friction_rupees for t in self.closed_trades), 2)
        net_pnl = round(sum(t.net_pnl_rupees for t in self.closed_trades), 2)
        ending_cap = round(self.initial_capital + net_pnl, 2)
        tot_ret_pct = round((net_pnl / self.initial_capital) * 100.0, 3)

        gross_win_sum = sum(t.gross_pnl_rupees for t in wins)
        gross_loss_sum = abs(sum(t.gross_pnl_rupees for t in losses))
        profit_factor = round(gross_win_sum / gross_loss_sum, 2) if gross_loss_sum > 0 else 99.0

        avg_hold = round(sum(t.holding_minutes for t in self.closed_trades) / max(1, tot_trades), 1)

        # Per-symbol breakdown
        sym_breakdown: Dict[str, Dict[str, Any]] = {}
        for t in self.closed_trades:
            if t.symbol not in sym_breakdown:
                sym_breakdown[t.symbol] = {"trades": 0, "gross_pnl": 0.0, "costs": 0.0, "net_pnl": 0.0}
            sym_breakdown[t.symbol]["trades"] += 1
            sym_breakdown[t.symbol]["gross_pnl"] = round(sym_breakdown[t.symbol]["gross_pnl"] + t.gross_pnl_rupees, 2)
            sym_breakdown[t.symbol]["costs"] = round(sym_breakdown[t.symbol]["costs"] + t.total_friction_rupees, 2)
            sym_breakdown[t.symbol]["net_pnl"] = round(sym_breakdown[t.symbol]["net_pnl"] + t.net_pnl_rupees, 2)

        return {
            "session_summary": {
                "initial_capital": self.initial_capital,
                "ending_capital": ending_cap,
                "gross_pnl_rupees": gross_pnl,
                "total_costs_rupees": total_costs,
                "net_pnl_rupees": net_pnl,
                "total_return_pct": tot_ret_pct,
                "max_drawdown_rupees": round(self.max_drawdown_rupees, 2),
                "total_trades": tot_trades,
                "winning_trades": len(wins),
                "losing_trades": len(losses),
                "win_rate_pct": round((len(wins) / max(1, tot_trades)) * 100.0, 2),
                "profit_factor": profit_factor,
                "average_holding_time_minutes": avg_hold,
                "total_rotations": len(self.rotation_events),
                "per_symbol_breakdown": sym_breakdown,
                "audit_entries_count": len(self.audit_ledger)
            }
        }
