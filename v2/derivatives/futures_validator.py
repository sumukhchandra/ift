"""
NSE Futures Validation Engine — Dual-Output Framework.
Strictly separates:
Output A: ECONOMIC SENSITIVITY (Hypothetical gross return under futures cost scenarios)
Output B: ACTUAL SIGNAL TRANSFER (Cash model -> futures-aligned execution -> basis drift -> net expectancy)

Scientific Invariant:
Output A cannot establish futures alpha. Only Output B can evaluate whether edge survives.
"""

from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd

from .futures_cost_model import (
    NSEFuturesCostModel,
    FuturesExecutionStyle,
    FuturesTradeCostDetail
)
from .basis_model import FuturesBasisModel
from .contract_master import NSEContractMaster
from .contract_specs import NSEContractSpec


@dataclass(frozen=True)
class EconomicSensitivityRow:
    notional_inr: float
    execution_style: str
    statutory_cost_bps: float
    microstructure_cost_bps: float
    total_friction_bps: float
    hypothetical_gross_bps: float
    theoretical_net_bps: float
    is_positive: bool


@dataclass(frozen=True)
class FuturesValidationResult:
    underlying: str
    horizon: str
    gross_futures_expectancy_bps: float
    basis_slippage_drag_bps: float
    average_futures_friction_bps: float
    net_futures_expectancy_bps: float
    win_rate_pct: float
    trades_executed: int
    trades_rejected_margin: int
    positive_folds: int
    total_folds: int
    gate_verdict: str               # "PASS", "FAIL", or "INCONCLUSIVE"
    summary_disclaimer: str


class FuturesValidator:
    """
    Executes rigorous dual-output validation for NSE stock futures feasibility.
    """

    def __init__(
        self,
        cost_model: Optional[NSEFuturesCostModel] = None,
        basis_model: Optional[FuturesBasisModel] = None,
        contract_master: Optional[NSEContractMaster] = None
    ):
        self.cost_model = cost_model or NSEFuturesCostModel()
        self.basis_model = basis_model or FuturesBasisModel()
        self.contract_master = contract_master or NSEContractMaster()

    def run_economic_sensitivity_analysis(
        self,
        hypothetical_gross_bps: float = 12.76,
        notional_brackets: Optional[List[float]] = None
    ) -> List[EconomicSensitivityRow]:
        """
        OUTPUT A: Evaluates theoretical net edge under various contract sizes and execution styles.
        Shows the sensitivity of cash alpha to post-April 2026 statutory rates and market friction.
        """
        if notional_brackets is None:
            # Typical contract values on NSE: ₹2.5L (midcap), ₹5L, ₹10L (large-cap default), ₹25L
            notional_brackets = [250000.0, 500000.0, 1000000.0, 2500000.0]

        rows: List[EconomicSensitivityRow] = []
        for notional in notional_brackets:
            for style in [FuturesExecutionStyle.AGGRESSIVE, FuturesExecutionStyle.PASSIVE, FuturesExecutionStyle.CONSERVATIVE_PASSIVE]:
                detail = self.cost_model.compute_round_trip_cost(
                    contract_notional=notional,
                    style=style
                )
                microstructure = (
                    detail.spread_component_bps +
                    detail.impact_bps +
                    detail.adverse_selection_bps +
                    detail.basis_slippage_bps
                )
                theoretical_net = hypothetical_gross_bps - detail.total_friction_bps
                rows.append(EconomicSensitivityRow(
                    notional_inr=notional,
                    execution_style=style.value,
                    statutory_cost_bps=detail.statutory_bps,
                    microstructure_cost_bps=microstructure,
                    total_friction_bps=detail.total_friction_bps,
                    hypothetical_gross_bps=hypothetical_gross_bps,
                    theoretical_net_bps=theoretical_net,
                    is_positive=(theoretical_net > 0)
                ))

        return rows

    def run_signal_transfer_simulation(
        self,
        underlying: str,
        df_bars: pd.DataFrame,
        cash_predictions_col: str,
        cash_forward_returns_col: str,
        horizon_name: str = "60m",
        capital_allocated: float = 2000000.0,  # ₹20 Lakhs capital
        execution_style: FuturesExecutionStyle = FuturesExecutionStyle.PASSIVE
    ) -> FuturesValidationResult:
        """
        OUTPUT B: Runs empirical signal transfer simulation incorporating:
        - Real underlying contract specifications from contract master
        - Integer lot size allocation constraints
        - Basis dynamics, carry decay, and microstructure noise
        - Dynamic post-April 2026 execution friction
        """
        if not self.contract_master.has_fo_contract(underlying):
            return FuturesValidationResult(
                underlying=underlying,
                horizon=horizon_name,
                gross_futures_expectancy_bps=0.0,
                basis_slippage_drag_bps=0.0,
                average_futures_friction_bps=0.0,
                net_futures_expectancy_bps=0.0,
                win_rate_pct=0.0,
                trades_executed=0,
                trades_rejected_margin=0,
                positive_folds=0,
                total_folds=0,
                gate_verdict="REJECTED_INELIGIBLE",
                summary_disclaimer=f"Underlying '{underlying}' has NO active F&O contract on NSE."
            )

        contracts = self.contract_master.get_contracts_for_underlying(underlying)
        if not contracts:
            raise ValueError(f"No contracts found for {underlying}")
        contract = contracts[0]

        trades_executed = 0
        trades_rejected = 0
        futures_gross_returns = []
        futures_net_returns = []
        basis_drags = []
        friction_records = []

        # Simulate over valid predictions
        valid_df = df_bars.dropna(subset=[cash_predictions_col, cash_forward_returns_col]).copy()
        for idx, row in valid_df.iterrows():
            pred = float(row[cash_predictions_col])
            spot_return = float(row[cash_forward_returns_col])
            spot_price = float(row.get("raw_close", row.get("close", row.get("adj_close", 100.0))))

            # Filter to trading signals (e.g. hurdle > 10 bps)
            if abs(pred) < 0.0010:  # 10 bps threshold
                continue

            direction = 1.0 if pred > 0 else -1.0

            # 1. Lot size integer constraint check
            margin_per_lot = contract.calculate_required_margin(spot_price, lots=1)
            lots = int(capital_allocated // margin_per_lot)
            if lots < 1:
                trades_rejected += 1
                continue

            trades_executed += 1
            contract_notional = contract.calculate_contract_value(spot_price, lots=lots)

            # 2. Synthetic futures return simulation (spot return + carry decay + basis noise)
            fut_return = self.basis_model.simulate_synthetic_futures_return(
                spot_return=spot_return,
                days_to_expiry_start=15,  # mid-cycle assumption
                random_seed=idx % 10000
            )
            trade_gross_return = direction * fut_return * 10000.0  # in bps
            basis_drag = (trade_gross_return - (direction * spot_return * 10000.0))

            # 3. Dynamic friction calculation
            cost_detail = self.cost_model.compute_round_trip_cost(
                contract_notional=contract_notional,
                style=execution_style
            )
            friction_bps = cost_detail.total_friction_bps
            trade_net_return = trade_gross_return - friction_bps

            futures_gross_returns.append(trade_gross_return)
            futures_net_returns.append(trade_net_return)
            basis_drags.append(basis_drag)
            friction_records.append(friction_bps)

        if not futures_net_returns:
            return FuturesValidationResult(
                underlying=underlying,
                horizon=horizon_name,
                gross_futures_expectancy_bps=0.0,
                basis_slippage_drag_bps=0.0,
                average_futures_friction_bps=0.0,
                net_futures_expectancy_bps=0.0,
                win_rate_pct=0.0,
                trades_executed=0,
                trades_rejected_margin=trades_rejected,
                positive_folds=0,
                total_folds=0,
                gate_verdict="INSUFFICIENT_SIGNALS",
                summary_disclaimer="No tradable signals generated under margin constraints."
            )

        mean_gross = float(np.mean(futures_gross_returns))
        mean_net = float(np.mean(futures_net_returns))
        mean_drag = float(np.mean(basis_drags))
        mean_friction = float(np.mean(friction_records))
        win_rate = float(np.mean([1.0 if r > 0 else 0.0 for r in futures_net_returns])) * 100.0

        verdict = "PASS" if mean_net > 0 and win_rate > 51.5 else "FAIL"

        return FuturesValidationResult(
            underlying=underlying,
            horizon=horizon_name,
            gross_futures_expectancy_bps=mean_gross,
            basis_slippage_drag_bps=mean_drag,
            average_futures_friction_bps=mean_friction,
            net_futures_expectancy_bps=mean_net,
            win_rate_pct=win_rate,
            trades_executed=trades_executed,
            trades_rejected_margin=trades_rejected,
            positive_folds=1 if mean_net > 0 else 0,
            total_folds=1,
            gate_verdict=verdict,
            summary_disclaimer=(
                "The cash observation implies a theoretical economic sensitivity of X under futures costs; "
                "actual futures signal transfer remains to be validated across multi-contract empirical data."
            )
        )
