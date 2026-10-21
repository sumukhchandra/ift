"""
Sequential Intraday Session Trader for AlphaNSE V2 (Adaptive Research Matrix V2).
Executes intraday trades bar-by-bar (09:15 - 15:25 IST) with:
  • Strict AsOfClock point-in-time sequential processing (no future data)
  • Authoritative Capital-Aware Ticket Economics (eliminates 1-share fee traps)
  • Configurable holding horizons: 15m (3 bars), 30m (6 bars), 60m (12 bars), EOD (session close)
  • Dynamic ATR stop losses & time-horizon profit taking
  • Real-world statutory taxes & execution friction (DynamicCostModel / IndiaCostEngine)
  • Permission to hold 100% Cash when no candidate clears gates (0 trades = valid outcome)
  • Full cryptographic trade lineage linking to DailyModelManifest
"""

import os
import uuid
import math
import logging
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

from v2.risk.integer_sizer import IntegerPositionSizer, SizingResult
from v2.risk.dynamic_cost_model import DynamicCostModel, ExecutionMode
from .opportunity_ranker import OpportunityRanker, RankedOpportunity, ConvictionTier
from .audit_ledger import DailyModelManifest, TradeAuditRecord, CandidateDecisionAuditRecord

logger = logging.getLogger(__name__)


@dataclass
class ActivePosition:
    position_id: str
    symbol: str
    direction: int
    entry_price: float
    entry_time: pd.Timestamp
    quantity: int
    stop_loss_price: float
    horizon_bars: int
    bars_held: int
    predicted_return_bps: float
    expected_net_value_bps: float
    conviction_tier: str
    entry_cost_rupees: float
    conviction_percentile: float = 0.0
    z_score: float = 0.0
    entry_slippage_bps: float = 2.0


class SessionTrader:
    """
    Executes a single intraday NSE trading session with full risk, cost, and ticket realism.
    """

    def __init__(
        self,
        manifest: DailyModelManifest,
        initial_capital: float = 5000.0,
        max_active_positions: int = 3,
        horizon_bars: int = 6,  # Default 6 bars = 30m (can be 3 for 15m, 12 for 60m, or 999 for EOD)
        cost_model: Optional[DynamicCostModel] = None,
        ranker: Optional[OpportunityRanker] = None,
        sizer: Optional[IntegerPositionSizer] = None,
        direction_filter: Optional[int] = None
    ):
        self.manifest = manifest
        self.initial_capital = initial_capital
        self.available_capital = initial_capital
        self.total_capital = initial_capital
        self.max_active_positions = max_active_positions
        self.horizon_bars = horizon_bars
        self.direction_filter = direction_filter

        self.cost_model = cost_model or DynamicCostModel(base_half_spread_bps=1.0, base_slippage_bps=2.0)
        self.ranker = ranker or OpportunityRanker(cost_model=self.cost_model)
        self.sizer = sizer or IntegerPositionSizer(
            max_risk_per_trade_pct=0.015,       # 1.5% risk
            max_position_allocation_pct=0.30,   # 30% max capital per stock
            atr_stop_multiplier=1.5,
            min_stop_loss_pct=0.003
        )

        self.active_positions: Dict[str, ActivePosition] = {}
        self.completed_trades: List[TradeAuditRecord] = []
        self.candidate_decisions: List[CandidateDecisionAuditRecord] = []

    def run_session(
        self,
        session_df: pd.DataFrame,
        feature_df: pd.DataFrame,
        model: Any
    ) -> List[TradeAuditRecord]:
        """
        Steps chronologically through each bar of the session (09:15 to 15:25 IST).
        """
        logger.info(
            f"Starting sequential session trading for {self.manifest.session_date} "
            f"(Horizon: {self.horizon_bars} bars, Capital: ₹{self.available_capital:.2f})..."
        )

        # Ensure timestamps are localized and sorted
        session_df = session_df.sort_values(by="timestamp").reset_index(drop=True)
        unique_timestamps = sorted(session_df["timestamp"].unique())

        for ts in unique_timestamps:
            bar_session = session_df[session_df["timestamp"] == ts]
            bar_features = feature_df[feature_df["timestamp"] == ts]

            # 1. Process open positions (Check stop loss, horizon expiry, EOD close)
            self._update_and_exit_positions(bar_session, ts)

            # 2. Rank new opportunities and evaluate entry (stop entering after 15:00 IST)
            current_time = pd.to_datetime(ts).time()
            if current_time < pd.to_datetime("15:00").time():
                self._evaluate_entries(bar_features, model, ts)

        # Force close any residual positions at end of day (15:25 IST)
        if self.active_positions and unique_timestamps:
            last_ts = unique_timestamps[-1]
            last_bar = session_df[session_df["timestamp"] == last_ts]
            for sym in list(self.active_positions.keys()):
                pos = self.active_positions[sym]
                sym_row = last_bar[last_bar["symbol"] == sym]
                exit_px = float(sym_row["close"].iloc[0]) if not sym_row.empty else pos.entry_price
                self._close_position(pos, exit_px, last_ts, "EOD_CLOSE")

        logger.info(
            f"Session {self.manifest.session_date} complete: {len(self.completed_trades)} trades executed. "
            f"Ending capital: ₹{self.total_capital:.2f}"
        )
        return self.completed_trades

    def _update_and_exit_positions(
        self,
        bar_df: pd.DataFrame,
        current_ts: pd.Timestamp
    ) -> None:
        """
        Checks open positions against stop-loss and time-horizon boundaries.
        """
        for sym in list(self.active_positions.keys()):
            pos = self.active_positions[sym]
            sym_row = bar_df[bar_df["symbol"] == sym]
            if sym_row.empty:
                pos.bars_held += 1
                continue

            high = float(sym_row["high"].iloc[0])
            low = float(sym_row["low"].iloc[0])
            close = float(sym_row["close"].iloc[0])
            pos.bars_held += 1

            # Stop loss checks
            if pos.direction == 1:  # Long
                if low <= pos.stop_loss_price:
                    self._close_position(pos, pos.stop_loss_price, current_ts, "STOP_LOSS")
                    continue
            else:  # Short
                if high >= pos.stop_loss_price:
                    self._close_position(pos, pos.stop_loss_price, current_ts, "STOP_LOSS")
                    continue

            # Horizon check (e.g. held for N bars; if horizon_bars >= 900, holds until EOD)
            if pos.bars_held >= pos.horizon_bars:
                self._close_position(pos, close, current_ts, "HORIZON_REACHED")

    def _evaluate_entries(
        self,
        feature_df: pd.DataFrame,
        model: Any,
        current_ts: pd.Timestamp
    ) -> None:
        """
        Ranks universe and evaluates entries bar-by-bar with authoritative ticket economics.
        Captures full forensic telemetry for EVERY candidate opportunity evaluated (entered or rejected).
        """
        ranked_opps = self.ranker.rank_universe_at_bar(
            feature_df,
            model,
            current_ts,
            available_capital=self.available_capital
        )

        for opp in ranked_opps:
            ticket = opp.ticket_economics
            qty = ticket.qty
            notional = opp.current_price * qty if qty > 0 else opp.current_price
            pred_direction = 1 if opp.predicted_return_bps >= 0 else -1

            # Standardized conviction percentile via normal CDF of |z|
            abs_z = abs(opp.z_score)
            conviction_pct = round(0.5 * (1.0 + math.erf(abs_z / math.sqrt(2.0))) * 100.0, 1)

            # Pre-evaluate single-source authoritative cost components for candidate snapshot
            cost_detail_eval = self.cost_model.compute_trade_cost(
                price=opp.current_price,
                quantity=max(1, qty),
                bar_volume=opp.volume,
                execution_mode=ExecutionMode.AGGRESSIVE
            )
            stat_eval = self.cost_model.cost_engine.calculate_roundtrip_cost(
                capital=notional,
                gross_return=0.0,
                slippage_bps=0.0
            )
            spread_cost = round(notional * (cost_detail_eval.spread_bps / 10000.0), 2)
            slippage_cost = round(notional * (cost_detail_eval.slippage_bps / 10000.0), 2)
            tot_friction = round(cost_detail_eval.total_cost_rupees, 2)

            # 1. Direction Filter Gate (if configured on trader)
            if self.direction_filter is not None and opp.direction != self.direction_filter:
                self._record_candidate_decision(
                    opp=opp,
                    current_ts=current_ts,
                    qty=qty,
                    notional=notional,
                    pred_direction=pred_direction,
                    conviction_pct=conviction_pct,
                    stat_eval=stat_eval,
                    spread_cost=spread_cost,
                    slippage_cost=slippage_cost,
                    tot_friction=tot_friction,
                    risk_gate_result="DIRECTION_FILTERED",
                    final_decision="REJECTED_DIRECTION",
                    rejection_reason=f"Candidate direction {opp.direction} blocked by filter ({self.direction_filter})"
                )
                continue

            # 2. Tradability / Conviction / Ticket Economics Gates
            if not opp.is_tradable:
                if opp.conviction_tier == "LOWER" and self.ranker.conviction_filter != ConvictionTier.ALL:
                    rej_dec = "REJECTED_CONVICTION"
                    rej_gate = "CONVICTION_BELOW_FILTER"
                    rej_msg = f"Conviction tier {opp.conviction_tier} (z={opp.z_score:.2f}) does not clear {self.ranker.conviction_filter.value}"
                elif not ticket.is_viable:
                    rej_dec = "REJECTED_TICKET_ECONOMICS"
                    rej_gate = "TICKET_ECONOMICS_NEGATIVE"
                    rej_msg = ticket.reject_reason or "Negative expected net INR after friction"
                elif opp.expected_net_value_bps < self.ranker.min_env_bps:
                    rej_dec = "REJECTED_TICKET_ECONOMICS"
                    rej_gate = "ENV_BELOW_HURDLE"
                    rej_msg = f"Expected Net Value {opp.expected_net_value_bps:.1f} bps below hurdle {self.ranker.min_env_bps:.1f} bps"
                else:
                    rej_dec = "REJECTED_RANKER"
                    rej_gate = "RANKER_CRITERIA_UNMET"
                    rej_msg = "Did not meet opportunity ranker gates"

                self._record_candidate_decision(
                    opp=opp,
                    current_ts=current_ts,
                    qty=qty,
                    notional=notional,
                    pred_direction=pred_direction,
                    conviction_pct=conviction_pct,
                    stat_eval=stat_eval,
                    spread_cost=spread_cost,
                    slippage_cost=slippage_cost,
                    tot_friction=tot_friction,
                    risk_gate_result=rej_gate,
                    final_decision=rej_dec,
                    rejection_reason=rej_msg
                )
                continue

            # 3. Portfolio Capacity Limit Gate
            if len(self.active_positions) >= self.max_active_positions:
                self._record_candidate_decision(
                    opp=opp,
                    current_ts=current_ts,
                    qty=qty,
                    notional=notional,
                    pred_direction=pred_direction,
                    conviction_pct=conviction_pct,
                    stat_eval=stat_eval,
                    spread_cost=spread_cost,
                    slippage_cost=slippage_cost,
                    tot_friction=tot_friction,
                    risk_gate_result="MAX_ACTIVE_POSITIONS_REACHED",
                    final_decision="REJECTED_RISK_GATE",
                    rejection_reason=f"Portfolio capacity reached ({self.max_active_positions} active positions)"
                )
                continue

            # 4. Duplicate Position Gate
            if opp.symbol in self.active_positions:
                self._record_candidate_decision(
                    opp=opp,
                    current_ts=current_ts,
                    qty=qty,
                    notional=notional,
                    pred_direction=pred_direction,
                    conviction_pct=conviction_pct,
                    stat_eval=stat_eval,
                    spread_cost=spread_cost,
                    slippage_cost=slippage_cost,
                    tot_friction=tot_friction,
                    risk_gate_result="ALREADY_ACTIVE_POSITION",
                    final_decision="REJECTED_RISK_GATE",
                    rejection_reason=f"Position already open for {opp.symbol}"
                )
                continue

            if qty <= 0:
                self._record_candidate_decision(
                    opp=opp,
                    current_ts=current_ts,
                    qty=qty,
                    notional=notional,
                    pred_direction=pred_direction,
                    conviction_pct=conviction_pct,
                    stat_eval=stat_eval,
                    spread_cost=spread_cost,
                    slippage_cost=slippage_cost,
                    tot_friction=tot_friction,
                    risk_gate_result="INSUFFICIENT_CAPITAL_FOR_1_SHARE",
                    final_decision="REJECTED_RISK_GATE",
                    rejection_reason="Affordable quantity is zero shares"
                )
                continue

            # 5. Entry Cost & Cash Sizing Gate
            entry_cost_rupees = (cost_detail_eval.statutory_cost_rupees * 0.5) + (opp.current_price * qty * cost_detail_eval.slippage_bps / 10000.0)
            total_cash_needed = notional + entry_cost_rupees

            if self.available_capital < total_cash_needed:
                self._record_candidate_decision(
                    opp=opp,
                    current_ts=current_ts,
                    qty=qty,
                    notional=notional,
                    pred_direction=pred_direction,
                    conviction_pct=conviction_pct,
                    stat_eval=stat_eval,
                    spread_cost=spread_cost,
                    slippage_cost=slippage_cost,
                    tot_friction=tot_friction,
                    risk_gate_result="INSUFFICIENT_AVAILABLE_CAPITAL",
                    final_decision="REJECTED_RISK_GATE",
                    rejection_reason=f"Cash required ₹{total_cash_needed:.2f} exceeds available ₹{self.available_capital:.2f}"
                )
                continue

            # ALL GATES CLEARED: Register active position
            trade_id = str(uuid.uuid4())[:8]

            # Stop loss price determination (1.5 * ATR stop loss)
            atr_stop_distance = max(opp.current_price * 0.003, opp.atr * 1.5)
            if opp.direction == 1:
                stop_px = round(opp.current_price - atr_stop_distance, 2)
            else:
                stop_px = round(opp.current_price + atr_stop_distance, 2)

            self.available_capital -= total_cash_needed

            pos = ActivePosition(
                position_id=trade_id,
                symbol=opp.symbol,
                direction=opp.direction,
                entry_price=opp.current_price,
                entry_time=current_ts,
                quantity=qty,
                stop_loss_price=stop_px,
                horizon_bars=self.horizon_bars,
                bars_held=0,
                predicted_return_bps=opp.predicted_return_bps,
                expected_net_value_bps=opp.expected_net_value_bps,
                conviction_tier=opp.conviction_tier,
                entry_cost_rupees=entry_cost_rupees,
                conviction_percentile=conviction_pct,
                z_score=opp.z_score,
                entry_slippage_bps=cost_detail_eval.slippage_bps
            )
            self.active_positions[opp.symbol] = pos

            # Record candidate decision as ENTERED
            self._record_candidate_decision(
                opp=opp,
                current_ts=current_ts,
                qty=qty,
                notional=notional,
                pred_direction=pred_direction,
                conviction_pct=conviction_pct,
                stat_eval=stat_eval,
                spread_cost=spread_cost,
                slippage_cost=slippage_cost,
                tot_friction=tot_friction,
                risk_gate_result="PASSED",
                final_decision="ENTERED",
                rejection_reason="NONE",
                trade_id=trade_id
            )

    def _close_position(
        self,
        pos: ActivePosition,
        exit_price: float,
        exit_ts: pd.Timestamp,
        reason: str
    ) -> None:
        """
        Executes position exit, computes actual net return & PnL via single authoritative CostEngine,
        and emits TradeAuditRecord.
        """
        del self.active_positions[pos.symbol]

        notional_entry = pos.entry_price * pos.quantity
        notional_exit = exit_price * pos.quantity

        # Gross return and realized direction
        if pos.direction == 1:
            gross_pnl_rupees = notional_exit - notional_entry
            gross_return_bps = ((exit_price - pos.entry_price) / pos.entry_price) * 10000.0
            actual_direction = 1 if exit_price > pos.entry_price else (-1 if exit_price < pos.entry_price else 0)
        else:
            gross_pnl_rupees = notional_entry - notional_exit
            gross_return_bps = ((pos.entry_price - exit_price) / pos.entry_price) * 10000.0
            actual_direction = 1 if exit_price < pos.entry_price else (-1 if exit_price > pos.entry_price else 0)

        # Single authoritative round-trip statutory calculation
        gross_return_frac = (gross_pnl_rupees / notional_entry) if notional_entry > 0 else 0.0
        stat_breakdown = self.cost_model.cost_engine.calculate_roundtrip_cost(
            capital=notional_entry,
            gross_return=gross_return_frac,
            slippage_bps=0.0
        )
        brokerage = stat_breakdown.brokerage
        stt = stat_breakdown.stt
        stamp_duty = stat_breakdown.stamp_duty
        exchange_charges = stat_breakdown.exchange_charges
        sebi_fees = stat_breakdown.sebi_fees
        gst = stat_breakdown.gst
        statutory_rupees = stat_breakdown.fixed_or_capped_cost + stat_breakdown.proportional_statutory_cost

        # Execution friction: spread and market impact slippage
        cost_detail_exit = self.cost_model.compute_trade_cost(
            price=exit_price,
            quantity=pos.quantity,
            execution_mode=ExecutionMode.AGGRESSIVE
        )
        spread_bps = self.cost_model.base_half_spread_bps * 2.0
        spread_cost_rupees = (notional_entry + notional_exit) * 0.5 * (spread_bps / 10000.0)
        slippage_bps = (pos.entry_slippage_bps + cost_detail_exit.slippage_bps) / 2.0
        slippage_cost_rupees = (notional_entry * pos.entry_slippage_bps + notional_exit * cost_detail_exit.slippage_bps) / 10000.0

        total_cost_rupees = round(statutory_rupees + spread_cost_rupees + slippage_cost_rupees, 4)
        cost_bps = (total_cost_rupees / notional_entry) * 10000.0 if notional_entry > 0 else 0.0

        # Net PnL and Return
        net_pnl_rupees = round(gross_pnl_rupees - total_cost_rupees, 4)
        net_return_bps = round(gross_return_bps - cost_bps, 2)

        # Exact duration
        t_entry = pd.to_datetime(pos.entry_time)
        t_exit = pd.to_datetime(exit_ts)
        duration_mins = (t_exit - t_entry).total_seconds() / 60.0

        # Update capital accounts with identical net_pnl_rupees
        self.available_capital += notional_entry + net_pnl_rupees
        self.total_capital += net_pnl_rupees

        record = TradeAuditRecord(
            trade_id=pos.position_id,
            session_date=self.manifest.session_date,
            entry_time=pos.entry_time.isoformat(),
            exit_time=exit_ts.isoformat(),
            symbol=pos.symbol,
            direction=pos.direction,
            entry_price=round(pos.entry_price, 2),
            exit_price=round(exit_price, 2),
            quantity=pos.quantity,
            gross_return_bps=round(gross_return_bps, 2),
            cost_bps=round(cost_bps, 2),
            net_return_bps=round(net_return_bps, 2),
            net_pnl_rupees=round(net_pnl_rupees, 2),
            predicted_return_bps=round(pos.predicted_return_bps, 2),
            expected_net_value_bps=round(pos.expected_net_value_bps, 2),
            model_version=self.manifest.model_version,
            model_hash=self.manifest.model_hash,
            dataset_hash=self.manifest.dataset_hash,
            data_cutoff=self.manifest.data_cutoff,
            exit_reason=reason,
            horizon_bars=pos.horizon_bars,
            holding_duration_mins=round(duration_mins, 1),
            conviction_tier=pos.conviction_tier,
            # Enhanced 29-field telemetry fields
            notional=round(notional_entry, 2),
            gross_pnl_rupees=round(gross_pnl_rupees, 2),
            predicted_direction=1 if pos.predicted_return_bps >= 0 else -1,
            actual_direction=actual_direction,
            brokerage_rupees=round(brokerage, 2),
            stt_rupees=round(stt, 2),
            stamp_duty_rupees=round(stamp_duty, 2),
            exchange_charges_rupees=round(exchange_charges, 2),
            sebi_fees_rupees=round(sebi_fees, 2),
            gst_rupees=round(gst, 2),
            spread_cost_rupees=round(spread_cost_rupees, 2),
            spread_bps=round(spread_bps, 2),
            slippage_cost_rupees=round(slippage_cost_rupees, 2),
            slippage_bps=round(slippage_bps, 2),
            total_friction_rupees=round(total_cost_rupees, 2),
            conviction_percentile=round(pos.conviction_percentile, 1),
            z_score=round(pos.z_score, 2),
            ticket_economics_result="VIABLE",
            risk_gate_result="PASSED",
            final_decision="ENTERED",
            rejection_reason=""
        )
        self.completed_trades.append(record)

        # Update candidate decision record if present
        self._update_candidate_decision_on_exit(
            trade_id=pos.position_id,
            exit_price=exit_price,
            gross_pnl_rupees=gross_pnl_rupees,
            net_pnl_rupees=net_pnl_rupees,
            net_return_bps=net_return_bps,
            actual_direction=actual_direction,
            brokerage=brokerage,
            stt=stt,
            stamp_duty=stamp_duty,
            exchange_charges=exchange_charges,
            sebi_fees=sebi_fees,
            gst=gst,
            spread_cost=spread_cost_rupees,
            slippage_cost=slippage_cost_rupees,
            total_friction=total_cost_rupees
        )

    def _record_candidate_decision(
        self,
        opp: RankedOpportunity,
        current_ts: pd.Timestamp,
        qty: int,
        notional: float,
        pred_direction: int,
        conviction_pct: float,
        stat_eval: Any,
        spread_cost: float,
        slippage_cost: float,
        tot_friction: float,
        risk_gate_result: str,
        final_decision: str,
        rejection_reason: str,
        trade_id: Optional[str] = None
    ) -> None:
        """Pure side-effect observer: records immutable snapshot of candidate decision."""
        try:
            record = CandidateDecisionAuditRecord(
                timestamp=current_ts.isoformat(),
                session_date=self.manifest.session_date,
                symbol=opp.symbol,
                model_version=self.manifest.model_version,
                model_hash=self.manifest.model_hash,
                dataset_hash=self.manifest.dataset_hash,
                data_cutoff=self.manifest.data_cutoff,
                predicted_return_bps=round(opp.predicted_return_bps, 2),
                realized_return_bps=None,
                predicted_direction=pred_direction,
                actual_direction=None,
                quantity=qty,
                entry_price=round(opp.current_price, 2),
                exit_price=None,
                notional=round(notional, 2),
                gross_pnl_rupees=None,
                brokerage_rupees=round(stat_eval.brokerage, 2),
                stt_rupees=round(stat_eval.stt, 2),
                stamp_duty_rupees=round(stat_eval.stamp_duty, 2),
                exchange_charges_rupees=round(stat_eval.exchange_charges, 2),
                sebi_fees_rupees=round(stat_eval.sebi_fees, 2),
                gst_rupees=round(stat_eval.gst, 2),
                spread_cost_rupees=round(spread_cost, 2),
                slippage_cost_rupees=round(slippage_cost, 2),
                total_friction_rupees=round(tot_friction, 2),
                net_pnl_rupees=None,
                conviction_percentile=round(conviction_pct, 1),
                z_score=round(opp.z_score, 2),
                conviction_tier=opp.conviction_tier,
                ticket_economics_result="VIABLE" if opp.ticket_economics.is_viable else "UNVIABLE",
                risk_gate_result=risk_gate_result,
                final_decision=final_decision,
                rejection_reason=rejection_reason,
                trade_id=trade_id
            )
            self.candidate_decisions.append(record)
        except Exception as e:
            logger.warning(f"Telemetry logging failed for candidate {opp.symbol}: {e}")

    def _update_candidate_decision_on_exit(
        self,
        trade_id: str,
        exit_price: float,
        gross_pnl_rupees: float,
        net_pnl_rupees: float,
        net_return_bps: float,
        actual_direction: int,
        brokerage: float,
        stt: float,
        stamp_duty: float,
        exchange_charges: float,
        sebi_fees: float,
        gst: float,
        spread_cost: float,
        slippage_cost: float,
        total_friction: float
    ) -> None:
        """Side-effect observer: enriches candidate decision with realized outcome once position exits."""
        try:
            for idx, d in enumerate(self.candidate_decisions):
                if d.trade_id == trade_id:
                    updated = CandidateDecisionAuditRecord(
                        timestamp=d.timestamp,
                        session_date=d.session_date,
                        symbol=d.symbol,
                        model_version=d.model_version,
                        model_hash=d.model_hash,
                        dataset_hash=d.dataset_hash,
                        data_cutoff=d.data_cutoff,
                        predicted_return_bps=d.predicted_return_bps,
                        realized_return_bps=round(net_return_bps, 2),
                        predicted_direction=d.predicted_direction,
                        actual_direction=actual_direction,
                        quantity=d.quantity,
                        entry_price=d.entry_price,
                        exit_price=round(exit_price, 2),
                        notional=d.notional,
                        gross_pnl_rupees=round(gross_pnl_rupees, 2),
                        brokerage_rupees=round(brokerage, 2),
                        stt_rupees=round(stt, 2),
                        stamp_duty_rupees=round(stamp_duty, 2),
                        exchange_charges_rupees=round(exchange_charges, 2),
                        sebi_fees_rupees=round(sebi_fees, 2),
                        gst_rupees=round(gst, 2),
                        spread_cost_rupees=round(spread_cost, 2),
                        slippage_cost_rupees=round(slippage_cost, 2),
                        total_friction_rupees=round(total_friction, 2),
                        net_pnl_rupees=round(net_pnl_rupees, 2),
                        conviction_percentile=d.conviction_percentile,
                        z_score=d.z_score,
                        conviction_tier=d.conviction_tier,
                        ticket_economics_result=d.ticket_economics_result,
                        risk_gate_result=d.risk_gate_result,
                        final_decision=d.final_decision,
                        rejection_reason=d.rejection_reason,
                        trade_id=d.trade_id
                    )
                    self.candidate_decisions[idx] = updated
                    break
        except Exception as e:
            logger.warning(f"Telemetry update failed on exit for trade {trade_id}: {e}")
