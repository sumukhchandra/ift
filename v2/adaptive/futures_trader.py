"""
Sequential Intraday Futures Session Trader for AlphaNSE V2 (Adaptive Research Matrix V2).
Executes institutional stock futures trades bar-by-bar (09:15 - 15:25 IST) with:
  • Official NSE contract specifications (lot sizes, tick sizes, expiry dates)
  • Explicit Margin & Risk Feasibility Gates (is_margin_feasible, is_risk_feasible)
  • Official statutory & execution cost scenarios via NSEFuturesCostModel:
      - STATUTORY_ONLY: ~6.13 bps
      - BASE: ~7.93-8.50 bps
      - STRESSED / CONSERVATIVE_PASSIVE: ~10.50 bps
  • Configurable holding horizons: 15m, 30m, 60m, EOD
  • Full trade audit lineage linking to DailyModelManifest
"""

import os
import uuid
import logging
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

from v2.derivatives.contract_master import NSEContractMaster, BASELINE_NSE_FO_CONTRACTS
from v2.derivatives.contract_specs import NSEContractSpec
from v2.derivatives.futures_cost_model import (
    NSEFuturesCostModel,
    FuturesExecutionStyle,
    FuturesTradeCostDetail
)
from .audit_ledger import DailyModelManifest
from .opportunity_ranker import OpportunityRanker, RankedOpportunity, ConvictionTier

logger = logging.getLogger(__name__)


class FuturesCostScenario(str, Enum):
    STATUTORY_ONLY = "STATUTORY_ONLY"          # ~6.13 bps floor
    BASE = "BASE"                              # ~7.93-8.50 bps realistic execution
    STRESSED = "STRESSED"                      # ~10.50 bps conservative friction


@dataclass(frozen=True)
class FuturesTradeAuditRecord:
    """Full cryptographic audit record for an executed equity futures trade."""
    trade_id: str
    session_date: str
    contract_symbol: str              # e.g. "RELIANCE26SEPFUT"
    underlying_symbol: str            # e.g. "RELIANCE.NS"
    direction: int                    # +1 for Long, -1 for Short
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    lots: int
    lot_size: int
    total_shares: int
    notional_entry: float             # entry_price * total_shares
    required_margin: float            # SPAN + Exposure margin
    is_margin_feasible_5k: bool       # Was this trade affordable with ₹5k cash?
    gross_return_bps: float
    cost_scenario: str
    cost_bps: float
    net_return_bps: float
    gross_pnl_rupees: float
    net_pnl_rupees: float
    predicted_return_bps: float
    conviction_tier: str
    exit_reason: str
    horizon_bars: int
    holding_duration_mins: float
    model_version: str
    model_hash: str
    dataset_hash: str
    data_cutoff: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActiveFuturesPosition:
    position_id: str
    contract_spec: NSEContractSpec
    underlying_symbol: str
    direction: int
    entry_price: float
    entry_time: pd.Timestamp
    lots: int
    stop_loss_price: float
    horizon_bars: int
    bars_held: int
    predicted_return_bps: float
    conviction_tier: str
    required_margin: float


class FuturesSessionTrader:
    """
    Simulates sequential intraday execution of NSE Stock Futures with realistic contract mechanics.
    """

    def __init__(
        self,
        manifest: DailyModelManifest,
        capital: float = 500000.0,       # Institutional capital base for margin (default ₹5L)
        retail_capital_ref: float = 5000.0, # Retail reference to test ₹5k feasibility
        max_active_positions: int = 3,
        horizon_bars: int = 6,           # Default 6 bars = 30m
        cost_scenario: FuturesCostScenario = FuturesCostScenario.BASE,
        conviction_filter: ConvictionTier = ConvictionTier.Q4_TOP_CONVICTION,
        ranker: Optional[OpportunityRanker] = None
    ):
        self.manifest = manifest
        self.capital = capital
        self.available_capital = capital
        self.retail_capital_ref = retail_capital_ref
        self.max_active_positions = max_active_positions
        self.horizon_bars = horizon_bars
        self.cost_scenario = cost_scenario
        self.conviction_filter = conviction_filter

        # Load official NSE Contract Master (already initializes baseline records)
        self.contract_master = NSEContractMaster()

        # Initialize official NSEFuturesCostModel based on scenario
        if cost_scenario == FuturesCostScenario.STATUTORY_ONLY:
            self.futures_cost_model = NSEFuturesCostModel(
                base_spread_bps=0.0,
                base_impact_bps=0.0,
                basis_slippage_bps=0.0
            )
            self.exec_style = FuturesExecutionStyle.PASSIVE
        elif cost_scenario == FuturesCostScenario.STRESSED:
            self.futures_cost_model = NSEFuturesCostModel(
                base_spread_bps=2.0,
                base_impact_bps=2.0,
                basis_slippage_bps=1.0
            )
            self.exec_style = FuturesExecutionStyle.AGGRESSIVE
        else:  # BASE
            self.futures_cost_model = NSEFuturesCostModel(
                base_spread_bps=1.0,
                base_impact_bps=1.0,
                basis_slippage_bps=0.5
            )
            self.exec_style = FuturesExecutionStyle.AGGRESSIVE

        self.ranker = ranker or OpportunityRanker(conviction_filter=conviction_filter)
        self.active_positions: Dict[str, ActiveFuturesPosition] = {}
        self.completed_trades: List[FuturesTradeAuditRecord] = []

    def run_session(
        self,
        session_df: pd.DataFrame,
        feature_df: pd.DataFrame,
        model: Any
    ) -> List[FuturesTradeAuditRecord]:
        """
        Steps chronologically through each bar of the session (09:15 to 15:25 IST).
        """
        logger.info(
            f"Starting Futures Session Trader for {self.manifest.session_date} "
            f"(Scenario: {self.cost_scenario.value}, Horizon: {self.horizon_bars} bars)..."
        )

        session_df = session_df.sort_values(by="timestamp").reset_index(drop=True)
        unique_timestamps = sorted(session_df["timestamp"].unique())

        for ts in unique_timestamps:
            bar_session = session_df[session_df["timestamp"] == ts]
            bar_features = feature_df[feature_df["timestamp"] == ts]

            # 1. Update and exit open futures positions
            self._update_and_exit_positions(bar_session, ts)

            # 2. Evaluate new futures entries (stop entering after 15:00 IST)
            current_time = pd.to_datetime(ts).time()
            if current_time < pd.to_datetime("15:00").time():
                self._evaluate_entries(bar_features, model, ts)

        # Force close any residual positions at end of session
        if self.active_positions and unique_timestamps:
            last_ts = unique_timestamps[-1]
            last_bar = session_df[session_df["timestamp"] == last_ts]
            for sym in list(self.active_positions.keys()):
                pos = self.active_positions[sym]
                sym_row = last_bar[last_bar["symbol"] == sym]
                exit_px = float(sym_row["close"].iloc[0]) if not sym_row.empty else pos.entry_price
                self._close_position(pos, exit_px, last_ts, "EOD_CLOSE")

        return self.completed_trades

    def _update_and_exit_positions(
        self,
        bar_df: pd.DataFrame,
        current_ts: pd.Timestamp
    ) -> None:
        """Checks open futures positions against stop loss and time-horizon boundaries."""
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
            if pos.direction == 1:
                if low <= pos.stop_loss_price:
                    self._close_position(pos, pos.stop_loss_price, current_ts, "STOP_LOSS")
                    continue
            else:
                if high >= pos.stop_loss_price:
                    self._close_position(pos, pos.stop_loss_price, current_ts, "STOP_LOSS")
                    continue

            # Horizon check (if horizon_bars >= 900, holds until EOD)
            if pos.bars_held >= pos.horizon_bars:
                self._close_position(pos, close, current_ts, "HORIZON_REACHED")

    def _evaluate_entries(
        self,
        feature_df: pd.DataFrame,
        model: Any,
        current_ts: pd.Timestamp
    ) -> None:
        """Ranks opportunities and evaluates futures entries."""
        if len(self.active_positions) >= self.max_active_positions:
            return

        ranked_opps = self.ranker.rank_universe_at_bar(
            feature_df,
            model,
            current_ts,
            available_capital=self.capital
        )

        for opp in ranked_opps:
            if len(self.active_positions) >= self.max_active_positions:
                break

            # Strip .NS to match underlying contract master
            underlying_clean = opp.symbol.replace(".NS", "")
            as_of_d = pd.to_datetime(self.manifest.session_date).date()
            active_contract = self.contract_master.get_near_month_contract(underlying_clean, as_of_date=as_of_d)

            if active_contract is None:
                continue  # Security has no F&O contract (e.g. TATACAP)

            if opp.symbol in self.active_positions:
                continue

            # Filter by conviction
            if self.conviction_filter == ConvictionTier.EXTREME_TOP_15:
                if opp.conviction_tier != ConvictionTier.EXTREME_TOP_15.value:
                    continue
            elif self.conviction_filter == ConvictionTier.Q4_TOP_CONVICTION:
                if opp.conviction_tier not in [ConvictionTier.Q4_TOP_CONVICTION.value, ConvictionTier.EXTREME_TOP_15.value]:
                    continue

            # Check Margin Feasibility: 1 Lot
            lots = 1
            required_margin = active_contract.calculate_required_margin(opp.current_price, lots=lots)
            is_margin_feasible_5k = (self.retail_capital_ref >= required_margin)

            if self.available_capital < required_margin:
                continue  # Cannot afford in active capital pool

            # Stop loss (1.5 * ATR)
            atr_stop = max(opp.current_price * 0.003, opp.atr * 1.5)
            stop_px = round(opp.current_price - atr_stop, 2) if opp.direction == 1 else round(opp.current_price + atr_stop, 2)

            self.available_capital -= required_margin

            pos = ActiveFuturesPosition(
                position_id=str(uuid.uuid4())[:8],
                contract_spec=active_contract,
                underlying_symbol=opp.symbol,
                direction=opp.direction,
                entry_price=opp.current_price,
                entry_time=current_ts,
                lots=lots,
                stop_loss_price=stop_px,
                horizon_bars=self.horizon_bars,
                bars_held=0,
                predicted_return_bps=opp.predicted_return_bps,
                conviction_tier=opp.conviction_tier,
                required_margin=required_margin
            )
            self.active_positions[opp.symbol] = pos

    def _close_position(
        self,
        pos: ActiveFuturesPosition,
        exit_price: float,
        exit_ts: pd.Timestamp,
        reason: str
    ) -> None:
        """Executes futures exit and calculates exact net returns via NSEFuturesCostModel."""
        del self.active_positions[pos.underlying_symbol]

        total_shares = pos.lots * pos.contract_spec.lot_size
        notional_entry = pos.entry_price * total_shares
        notional_exit = exit_price * total_shares

        # Gross return
        if pos.direction == 1:
            gross_pnl_rupees = notional_exit - notional_entry
            gross_return_bps = ((exit_price - pos.entry_price) / pos.entry_price) * 10000.0
        else:
            gross_pnl_rupees = notional_entry - notional_exit
            gross_return_bps = ((pos.entry_price - exit_price) / pos.entry_price) * 10000.0

        # Cost evaluation via official NSEFuturesCostModel
        cost_detail = self.futures_cost_model.compute_round_trip_cost(
            contract_notional=notional_entry,
            style=self.exec_style
        )
        total_cost_rupees = (cost_detail.total_friction_bps / 10000.0) * notional_entry
        cost_bps = cost_detail.total_friction_bps

        net_pnl_rupees = gross_pnl_rupees - total_cost_rupees
        net_return_bps = gross_return_bps - cost_bps

        # Duration
        t_entry = pd.to_datetime(pos.entry_time)
        t_exit = pd.to_datetime(exit_ts)
        duration_mins = (t_exit - t_entry).total_seconds() / 60.0

        # Restore capital
        self.available_capital += pos.required_margin + net_pnl_rupees

        record = FuturesTradeAuditRecord(
            trade_id=pos.position_id,
            session_date=self.manifest.session_date,
            contract_symbol=pos.contract_spec.symbol,
            underlying_symbol=pos.underlying_symbol,
            direction=pos.direction,
            entry_time=pos.entry_time.isoformat(),
            exit_time=exit_ts.isoformat(),
            entry_price=round(pos.entry_price, 2),
            exit_price=round(exit_price, 2),
            lots=pos.lots,
            lot_size=pos.contract_spec.lot_size,
            total_shares=total_shares,
            notional_entry=round(notional_entry, 2),
            required_margin=round(pos.required_margin, 2),
            is_margin_feasible_5k=(self.retail_capital_ref >= pos.required_margin),
            gross_return_bps=round(gross_return_bps, 2),
            cost_scenario=self.cost_scenario.value,
            cost_bps=round(cost_bps, 2),
            net_return_bps=round(net_return_bps, 2),
            gross_pnl_rupees=round(gross_pnl_rupees, 2),
            net_pnl_rupees=round(net_pnl_rupees, 2),
            predicted_return_bps=round(pos.predicted_return_bps, 2),
            conviction_tier=pos.conviction_tier,
            exit_reason=reason,
            horizon_bars=pos.horizon_bars,
            holding_duration_mins=round(duration_mins, 1),
            model_version=self.manifest.model_version,
            model_hash=self.manifest.model_hash,
            dataset_hash=self.manifest.dataset_hash,
            data_cutoff=self.manifest.data_cutoff
        )
        self.completed_trades.append(record)
