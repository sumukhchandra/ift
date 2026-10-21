"""
AlphaNSE V3 — Sequential Intraday Session Trader (60-Minute Horizon).
Executes chronological intraday trading bar-by-bar (09:15 to 15:25 IST).

STATUS: EXPERIMENT / VALIDATION
KEY CONSTRAINTS & INVARIANTS:
  1. 60m Holding Horizon: 12 bars of 5m (target holding duration = 60 minutes).
  2. Lunch Blackout: 12:00 to 14:00 IST (Strictly NO NEW ENTRIES; open positions monitored normally).
  3. Afternoon Entry Cutoff: 14:25 IST (No new entries after 14:25 so 12 bars complete by 15:25).
  4. End-of-Day Square-Off: 15:25 IST (Strict zero overnight position invariant).
  5. Rupee Net-Edge Gating: Trades entered ONLY when expected net profit >= hurdle (>= ₹0.80).
  6. Cash Preservation: Holding cash is a valid, intentional outcome.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime, time
import pandas as pd
import numpy as np

from v2.risk.dynamic_cost_model import DynamicCostModel, ExecutionMode
from v3.config.v3_config import (
    HORIZON_BARS,
    INITIAL_CAPITAL,
    MAX_CAPITAL_PCT_PER_TRADE,
    MAX_ACTIVE_POSITIONS,
    STOP_LOSS_ATR_MULT,
    LUNCH_BLACKOUT_START,
    LUNCH_BLACKOUT_END,
    ENTRY_CUTOFF_TIME,
    EOD_CLOSE_TIME,
    REPLAY_DISCLAIMER,
    FORWARD_VALIDATION_LABEL
)
from v3.adaptive.audit_ledger_v3 import DailyModelManifestV3, TradeAuditRecordV3, CandidateDecisionAuditRecordV3
from v3.adaptive.opportunity_engine_v3 import OpportunityEngineV3, RankedOpportunityV3
from v3.ensemble.multimodel_ensemble_v3 import EnsembleDecisionOutput

logger = logging.getLogger(__name__)


@dataclass
class ActivePositionV3:
    """Tracks an open position held during the trading session."""
    symbol: str
    direction: int                      # +1 for Long, -1 for Short
    entry_price: float
    quantity: int
    notional: float
    entry_time: pd.Timestamp
    stop_loss_price: float
    predicted_return_bps: float
    expected_gross_rupees: float
    expected_cost_rupees: float
    expected_net_rupees: float
    expected_cost_bps: float
    bars_held: int = 0
    horizon_bars: int = 12
    supporting_models: Optional[List[str]] = None
    contradicting_models: Optional[List[str]] = None


class SessionTraderV3:
    """
    Chronological 5-minute bar sequential trader for AlphaNSE V3.
    """

    def __init__(
        self,
        manifest: DailyModelManifestV3,
        initial_capital: float = INITIAL_CAPITAL,
        horizon_bars: int = HORIZON_BARS,
        max_active_positions: int = MAX_ACTIVE_POSITIONS,
        is_forward_validation: bool = False
    ):
        self.manifest = manifest
        self.initial_capital = initial_capital
        self.available_capital = initial_capital
        self.total_capital = initial_capital
        self.horizon_bars = horizon_bars
        self.max_active_positions = max_active_positions
        self.is_forward_validation = is_forward_validation

        self.opportunity_engine = OpportunityEngineV3()
        self.cost_model = DynamicCostModel(base_half_spread_bps=1.0, base_slippage_bps=2.0)

        self.active_positions: Dict[str, ActivePositionV3] = {}
        self.completed_trades: List[TradeAuditRecordV3] = []
        self.candidate_audits: List[CandidateDecisionAuditRecordV3] = []
        self.trade_counter: int = 0

        # Time thresholds
        self.lunch_start = datetime.strptime(LUNCH_BLACKOUT_START, "%H:%M").time()
        self.lunch_end = datetime.strptime(LUNCH_BLACKOUT_END, "%H:%M").time()
        self.entry_cutoff = datetime.strptime(ENTRY_CUTOFF_TIME, "%H:%M").time()
        self.eod_close_time = datetime.strptime(EOD_CLOSE_TIME, "%H:%M").time()

    def run_session(
        self,
        session_df: pd.DataFrame,
        feature_df: pd.DataFrame,
        model: Any
    ) -> List[TradeAuditRecordV3]:
        """
        Steps chronologically bar-by-bar from 09:15 to 15:25 IST.
        """
        logger.info(
            f"[V3] Starting sequential session trading for {self.manifest.session_date} "
            f"(Horizon: {self.horizon_bars} bars / 60m, Capital: ₹{self.available_capital:.2f})..."
        )

        session_df = session_df.sort_values(by="timestamp").reset_index(drop=True)
        unique_timestamps = sorted(session_df["timestamp"].unique())

        for ts in unique_timestamps:
            bar_session = session_df[session_df["timestamp"] == ts]
            bar_features = feature_df[feature_df["timestamp"] == ts]
            current_time = pd.to_datetime(ts).time()

            # 1. Update and exit existing active positions
            self._update_and_exit_positions(bar_session, ts)

            # 2. Check entry windows
            # Lunch Blackout (12:00 to 14:00 IST): strictly NO NEW ENTRIES
            if self.lunch_start <= current_time < self.lunch_end:
                continue

            # Entry cutoff (>= 14:25 IST): strictly NO NEW ENTRIES
            if current_time >= self.entry_cutoff:
                continue

            # Active entry evaluation
            if len(self.active_positions) < self.max_active_positions:
                self._evaluate_entries(bar_features, model, ts)

        # 3. Force square-off any residual positions at end of session
        if self.active_positions and unique_timestamps:
            last_ts = unique_timestamps[-1]
            last_bar = session_df[session_df["timestamp"] == last_ts]
            for sym in list(self.active_positions.keys()):
                pos = self.active_positions[sym]
                sym_row = last_bar[last_bar["symbol"] == sym]
                exit_px = float(sym_row["close"].iloc[0]) if not sym_row.empty else pos.entry_price
                self._close_position(pos, exit_px, last_ts, "EOD_CLOSE")

        logger.info(
            f"[V3] Session {self.manifest.session_date} complete: {len(self.completed_trades)} trades executed. "
            f"Ending capital: ₹{self.total_capital:.2f}"
        )
        return self.completed_trades

    def _update_and_exit_positions(
        self,
        bar_df: pd.DataFrame,
        current_ts: pd.Timestamp
    ) -> None:
        """
        Updates bar counts and evaluates stop-loss and 60m horizon exits.
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

            # Horizon reached check (uses position's selected horizon)
            if pos.bars_held >= pos.horizon_bars:
                self._close_position(pos, close, current_ts, "HORIZON_REACHED")

    def _evaluate_entries(
        self,
        bar_features: pd.DataFrame,
        model: Any,
        current_ts: pd.Timestamp
    ) -> None:
        """
        Evaluates opportunities using the Rupee Net-Edge gate across single or multi-model architectures.
        """
        if self.available_capital < 100.0:
            return

        # Check if model is a MultiModelRegistryV3 or dictionary of models
        is_multimodel = hasattr(model, "get_valid_models") or (isinstance(model, dict) and "V2_15M" in model)

        if is_multimodel:
            viable_opps, audits = self.opportunity_engine.evaluate_multimodel_universe_at_bar(
                bar_features_df=bar_features,
                model_registry=model,
                timestamp=current_ts,
                available_capital=self.available_capital,
                dataset_hash=self.manifest.dataset_hash,
                training_cutoff=self.manifest.data_cutoff
            )
            self.candidate_audits.extend(audits)

            if not viable_opps:
                return

            top_ensemble_opp = viable_opps[0]

            if top_ensemble_opp.symbol in self.active_positions:
                return

            entry_price = top_ensemble_opp.price
            qty = top_ensemble_opp.affordable_quantity
            notional = top_ensemble_opp.capital_required

            if notional > self.available_capital or qty <= 0:
                return

            # Dynamic horizon in bars based on ensemble's selected horizon
            pos_horizon_bars = max(1, top_ensemble_opp.selected_horizon // 5)

            sym_row = bar_features[bar_features["symbol"] == top_ensemble_opp.symbol]
            atr = float(sym_row["raw_atr_14"].iloc[0]) if not sym_row.empty and "raw_atr_14" in sym_row else (entry_price * 0.005)
            stop_dist = max(atr * STOP_LOSS_ATR_MULT, entry_price * 0.003)

            if top_ensemble_opp.ensemble_direction == 1:
                stop_loss = entry_price - stop_dist
            else:
                stop_loss = entry_price + stop_dist

            self.available_capital -= notional

            pos = ActivePositionV3(
                symbol=top_ensemble_opp.symbol,
                direction=top_ensemble_opp.ensemble_direction,
                entry_price=entry_price,
                quantity=qty,
                notional=notional,
                entry_time=current_ts,
                stop_loss_price=stop_loss,
                predicted_return_bps=top_ensemble_opp.ensemble_expected_gross_bps,
                expected_gross_rupees=top_ensemble_opp.expected_gross_rupees,
                expected_cost_rupees=top_ensemble_opp.estimated_total_cost_rupees,
                expected_net_rupees=top_ensemble_opp.ensemble_expected_net_rupees,
                expected_cost_bps=top_ensemble_opp.estimated_cost_bps,
                bars_held=0,
                horizon_bars=pos_horizon_bars,
                supporting_models=top_ensemble_opp.supporting_models,
                contradicting_models=top_ensemble_opp.contradicting_models
            )
            self.active_positions[top_ensemble_opp.symbol] = pos
            logger.info(
                f"[V3 ENSEMBLE ENTRY] {current_ts.strftime('%H:%M')} {top_ensemble_opp.symbol} "
                f"Dir:{top_ensemble_opp.ensemble_direction} Qty:{qty} @ ₹{entry_price:.2f} | "
                f"Horizon:{top_ensemble_opp.selected_horizon}m ({pos_horizon_bars} bars) | "
                f"Agreement:{top_ensemble_opp.agreement_ratio} | Exp Net: ₹{top_ensemble_opp.ensemble_expected_net_rupees:.2f}"
            )
        else:
            # Single-model fallback
            ranked_opps = self.opportunity_engine.rank_universe_at_bar(
                bar_features_df=bar_features,
                model=model,
                timestamp=current_ts,
                available_capital=self.available_capital
            )

            if not ranked_opps:
                return

            top_opp = ranked_opps[0]

            if top_opp.symbol in self.active_positions:
                return

            entry_price = top_opp.price
            qty = top_opp.quantity
            notional = top_opp.notional

            if notional > self.available_capital or qty <= 0:
                return

            sym_row = bar_features[bar_features["symbol"] == top_opp.symbol]
            atr = float(sym_row["raw_atr_14"].iloc[0]) if not sym_row.empty and "raw_atr_14" in sym_row else (entry_price * 0.005)
            stop_dist = max(atr * STOP_LOSS_ATR_MULT, entry_price * 0.003)

            if top_opp.direction == 1:
                stop_loss = entry_price - stop_dist
            else:
                stop_loss = entry_price + stop_dist

            self.available_capital -= notional

            pos = ActivePositionV3(
                symbol=top_opp.symbol,
                direction=top_opp.direction,
                entry_price=entry_price,
                quantity=qty,
                notional=notional,
                entry_time=current_ts,
                stop_loss_price=stop_loss,
                predicted_return_bps=top_opp.predicted_return_bps,
                expected_gross_rupees=top_opp.expected_gross_rupees,
                expected_cost_rupees=top_opp.expected_cost_rupees,
                expected_net_rupees=top_opp.expected_net_rupees,
                expected_cost_bps=top_opp.expected_cost_bps,
                bars_held=0,
                horizon_bars=self.horizon_bars
            )
            self.active_positions[top_opp.symbol] = pos
            logger.debug(
                f"[V3 ENTRY] {current_ts.strftime('%H:%M')} {top_opp.symbol} Dir:{top_opp.direction} "
                f"Qty:{qty} @ ₹{entry_price:.2f} | Exp Net: ₹{top_opp.expected_net_rupees:.2f}"
            )

    def _close_position(
        self,
        pos: ActivePositionV3,
        exit_price: float,
        exit_ts: pd.Timestamp,
        exit_reason: str
    ) -> None:
        """
        Closes position, computes exact realized statutory and friction fees,
        and generates an immutable TradeAuditRecordV3.
        """
        self.trade_counter += 1
        trade_id = f"T_{self.manifest.session_date.replace('-', '')}_{self.trade_counter:04d}"

        direction = pos.direction
        qty = pos.quantity
        notional = pos.notional

        # Realized gross PnL
        if direction == 1:  # Long
            gross_pnl_rupees = (exit_price - pos.entry_price) * qty
        else:               # Short
            gross_pnl_rupees = (pos.entry_price - exit_price) * qty

        gross_return_bps = (gross_pnl_rupees / notional) * 10000.0 if notional > 0 else 0.0

        # Compute penny-for-penny actual transaction costs
        # (uses aggressive market-order friction model)
        cost_detail = self.cost_model.compute_trade_cost(
            price=(pos.entry_price + exit_price) / 2.0,
            quantity=qty,
            bar_volume=50000.0,
            execution_mode=ExecutionMode.AGGRESSIVE
        )

        stat_breakdown = self.cost_model.cost_engine.calculate_roundtrip_cost(
            capital=notional,
            gross_return=gross_return_bps / 10000.0,
            slippage_bps=0.0
        )

        brokerage_rupees = stat_breakdown.brokerage
        stt_rupees = stat_breakdown.stt
        exchange_charges_rupees = stat_breakdown.exchange_charges
        sebi_charges_rupees = stat_breakdown.sebi_fees
        stamp_duty_rupees = stat_breakdown.stamp_duty
        gst_rupees = stat_breakdown.gst
        statutory_total_rupees = stat_breakdown.fixed_or_capped_cost + stat_breakdown.proportional_statutory_cost

        # Friction components (spread + slippage)
        spread_rupees = notional * (cost_detail.spread_bps / 10000.0)
        slippage_rupees = notional * (cost_detail.slippage_bps / 10000.0)
        total_cost_rupees = statutory_total_rupees + spread_rupees + slippage_rupees
        cost_bps = (total_cost_rupees / notional) * 10000.0 if notional > 0 else 0.0

        # Exact Net PnL (accounting identity: Net = Gross - Total Costs)
        net_pnl_rupees = gross_pnl_rupees - total_cost_rupees
        net_return_bps = gross_return_bps - cost_bps

        # Release capital
        self.available_capital += notional + net_pnl_rupees
        self.total_capital += net_pnl_rupees

        holding_duration_mins = pos.bars_held * 5.0

        execution_type = "FORWARD_VALIDATION" if self.is_forward_validation else "HISTORICAL_REPLAY"
        disclaimer = FORWARD_VALIDATION_LABEL if self.is_forward_validation else REPLAY_DISCLAIMER

        record = TradeAuditRecordV3(
            trade_id=trade_id,
            session_date=self.manifest.session_date,
            entry_time=str(pos.entry_time),
            exit_time=str(exit_ts),
            symbol=pos.symbol,
            direction=direction,
            entry_price=round(pos.entry_price, 2),
            exit_price=round(exit_price, 2),
            quantity=qty,
            notional=round(notional, 2),
            predicted_return_bps=pos.predicted_return_bps,
            expected_gross_rupees=pos.expected_gross_rupees,
            expected_total_cost_rupees=pos.expected_cost_rupees,
            expected_net_rupees=pos.expected_net_rupees,
            expected_cost_bps=pos.expected_cost_bps,
            gross_return_bps=round(gross_return_bps, 2),
            cost_bps=round(cost_bps, 2),
            net_return_bps=round(net_return_bps, 2),
            gross_pnl_rupees=round(gross_pnl_rupees, 2),
            net_pnl_rupees=round(net_pnl_rupees, 2),
            brokerage_rupees=round(brokerage_rupees, 2),
            stt_rupees=round(stt_rupees, 2),
            exchange_charges_rupees=round(exchange_charges_rupees, 2),
            sebi_charges_rupees=round(sebi_charges_rupees, 2),
            stamp_duty_rupees=round(stamp_duty_rupees, 2),
            gst_rupees=round(gst_rupees, 2),
            statutory_total_rupees=round(statutory_total_rupees, 2),
            spread_rupees=round(spread_rupees, 2),
            slippage_rupees=round(slippage_rupees, 2),
            exit_reason=exit_reason,
            horizon_bars=self.horizon_bars,
            holding_duration_mins=holding_duration_mins,
            model_version=self.manifest.model_version,
            model_hash=self.manifest.model_hash,
            dataset_hash=self.manifest.dataset_hash,
            data_cutoff=self.manifest.data_cutoff,
            execution_type=execution_type,
            disclaimer=disclaimer,
            supporting_models=str(pos.supporting_models),
            contradicting_models=str(pos.contradicting_models)
        )

        self.completed_trades.append(record)
        del self.active_positions[pos.symbol]

        logger.debug(
            f"[V3 EXIT] {exit_ts.strftime('%H:%M')} {pos.symbol} Reason:{exit_reason} "
            f"Gross:₹{gross_pnl_rupees:.2f} Fees:₹{total_cost_rupees:.2f} Net:₹{net_pnl_rupees:.2f}"
        )
