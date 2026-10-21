"""
Point-in-Time Intraday Opportunity Ranker for AlphaNSE V2 (Adaptive Research Matrix V2).
Evaluates cross-universe opportunities at each intraday decision step:
  1. Predicts forward expected return r_hat_i,t via frozen Day-D model.
  2. Measures cross-sectional relative strength (z-score) and conviction tiers (Q4 / Top 15%).
  3. Calculates authoritative Capital-Aware Ticket Economics:
       Available Capital -> Affordable Qty -> Gross Expected ₹ -> Statutory Fees -> Spread/Impact -> Net Expected ₹.
  4. Estimates dynamic roundtrip transaction cost C_i,t via DynamicCostModel / IndiaCostEngine.
  5. Computes Expected Net Value: ENV_i,t = expected_gross_bps - C_i,t.
  6. Ranks opportunities across universe strictly by Expected Net Value.
  7. Enforces cost-adjusted viability without forcing artificial trade minimums (0 trades = valid cash preservation).
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd

from v2.features.feature_pipeline import ALL_FEATURE_COLUMNS
from v2.models.estimators import RidgeReturnRegressor
from v2.risk.dynamic_cost_model import DynamicCostModel, ExecutionMode

logger = logging.getLogger(__name__)


class ConvictionTier(str, Enum):
    ALL = "ALL"                                # All signals (unfiltered research slice)
    Q4_TOP_CONVICTION = "Q4_TOP_CONVICTION"    # Cross-sectionally aligned, |z| >= 1.0
    EXTREME_TOP_15 = "EXTREME_TOP_15"          # Top 15% signal conviction (|z| >= 1.44 or |pred| >= 15 bps)


@dataclass(frozen=True)
class TicketEconomicsResult:
    """Authoritative unit-economics calculation for a candidate trade ticket."""
    is_viable: bool                    # Does trade yield positive net INR after all ticket fees?
    qty: int                           # Whole integer shares affordable
    notional: float                    # Total capital required (price * qty)
    gross_expected_inr: float          # Expected monetary return before costs
    total_cost_inr: float              # All statutory taxes + spread + slippage in INR
    net_expected_inr: float            # Net expected monetary edge in INR
    cost_bps: float                    # Total cost normalized in bps
    reject_reason: Optional[str] = None


@dataclass(frozen=True)
class RankedOpportunity:
    symbol: str
    timestamp: pd.Timestamp
    direction: int                     # +1 for Long, -1 for Short
    predicted_return_bps: float        # Model point-in-time prediction in bps
    z_score: float                     # Cross-sectional standardized signal
    conviction_tier: str               # "Q4_TOP_CONVICTION", "EXTREME_TOP_15", or "LOWER"
    expected_gross_bps: float          # Model-calibrated expected move in bps
    expected_cost_bps: float           # Dynamic cost hurdle in bps
    expected_net_value_bps: float      # Predicted gross minus cost hurdle
    current_price: float               # Execution price
    atr: float                         # ATR for stop loss sizing
    volume: float                      # Bar volume
    rank: int                          # Rank across universe at this timestamp
    ticket_economics: TicketEconomicsResult
    is_tradable: bool                  # Passed conviction, ticket economics, and hurdle gates


class OpportunityRanker:
    """
    Ranks opportunities cross-sectionally at each intraday decision point.
    """

    def __init__(
        self,
        min_env_bps: float = 2.0,             # Minimum Expected Net Value in bps after all costs
        min_net_rupees_target: float = 0.0,   # Minimum net profit target in INR (0.0 during research exploration)
        conviction_filter: ConvictionTier = ConvictionTier.ALL,
        max_price_pct_heuristic: Optional[float] = None, # Optional preliminary filter: price <= capital * pct
        max_capital_pct_per_trade: float = 0.30,         # Max 30% capital per stock
        cost_model: Optional[DynamicCostModel] = None,
        execution_mode: ExecutionMode = ExecutionMode.AGGRESSIVE
    ):
        self.min_env_bps = min_env_bps
        self.min_net_rupees_target = min_net_rupees_target
        self.conviction_filter = conviction_filter
        self.max_price_pct_heuristic = max_price_pct_heuristic
        self.max_capital_pct_per_trade = max_capital_pct_per_trade
        self.cost_model = cost_model or DynamicCostModel(base_half_spread_bps=1.0, base_slippage_bps=2.0)
        self.execution_mode = execution_mode

    def evaluate_ticket_economics(
        self,
        symbol: str,
        price: float,
        available_capital: float,
        expected_gross_bps: float,
        vol: float = 50000.0
    ) -> TicketEconomicsResult:
        """
        Authoritative unit-economics calculation for a candidate cash equity trade.
        Determines whether affordable whole shares generate sufficient gross INR to overcome
        fixed ticket friction and statutory minimum taxes.
        """
        # Available allocation: if available_capital is None, assume unconstrained research capital (₹100,000)
        cap = available_capital if available_capital is not None else 100000.0

        if price <= 0 or cap <= 0:
            return TicketEconomicsResult(
                is_viable=False, qty=0, notional=0.0, gross_expected_inr=0.0,
                total_cost_inr=0.0, net_expected_inr=0.0, cost_bps=0.0,
                reject_reason="INVALID_PRICE_OR_CAPITAL"
            )

        # Optional preliminary price heuristic check (e.g. price <= 25% of capital)
        if self.max_price_pct_heuristic is not None:
            max_allowed_px = cap * self.max_price_pct_heuristic
            if price > max_allowed_px:
                return TicketEconomicsResult(
                    is_viable=False, qty=0, notional=0.0, gross_expected_inr=0.0,
                    total_cost_inr=0.0, net_expected_inr=0.0, cost_bps=0.0,
                    reject_reason=f"PRICE_EXCEEDS_HEURISTIC (Price ₹{price:.1f} > ₹{max_allowed_px:.1f})"
                )

        max_alloc = cap * self.max_capital_pct_per_trade
        raw_qty = int(max_alloc / price)
        # Allow at least 1 share if price is within total available capital
        if raw_qty <= 0 and price <= cap:
            qty = 1
        else:
            qty = raw_qty

        if qty <= 0:
            return TicketEconomicsResult(
                is_viable=False, qty=0, notional=0.0, gross_expected_inr=0.0,
                total_cost_inr=0.0, net_expected_inr=0.0, cost_bps=0.0,
                reject_reason="INSUFFICIENT_CAPITAL_FOR_1_SHARE"
            )

        notional = price * qty
        gross_expected_inr = notional * (expected_gross_bps / 10000.0)

        # Compute penny-for-penny friction via DynamicCostModel
        cost_detail = self.cost_model.compute_trade_cost(
            price=price,
            quantity=qty,
            bar_volume=vol,
            execution_mode=self.execution_mode
        )
        total_cost_inr = cost_detail.total_cost_rupees
        net_expected_inr = gross_expected_inr - total_cost_inr
        cost_bps = cost_detail.total_cost_bps

        is_viable = (net_expected_inr > self.min_net_rupees_target)

        reject_reason = None
        if not is_viable:
            reject_reason = f"NEGATIVE_EXPECTED_NET_INR (Gross ₹{gross_expected_inr:.2f} < Cost ₹{total_cost_inr:.2f})"

        return TicketEconomicsResult(
            is_viable=is_viable,
            qty=qty,
            notional=notional,
            gross_expected_inr=round(gross_expected_inr, 2),
            total_cost_inr=round(total_cost_inr, 2),
            net_expected_inr=round(net_expected_inr, 2),
            cost_bps=round(cost_bps, 2),
            reject_reason=reject_reason
        )

    def rank_universe_at_bar(
        self,
        bar_features_df: pd.DataFrame,
        model: RidgeReturnRegressor,
        timestamp: pd.Timestamp,
        available_capital: Optional[float] = None
    ) -> List[RankedOpportunity]:
        """
        Takes the slice of features for all symbols at current bar timestamp,
        evaluates model predictions, computes dynamic transaction costs,
        and returns ranked opportunities with authoritative ticket economics.
        """
        if bar_features_df.empty:
            return []

        clean_df = bar_features_df.dropna(subset=ALL_FEATURE_COLUMNS).copy()
        clean_df = clean_df[clean_df["symbol"] != "^NSEI"].copy().reset_index(drop=True)
        if clean_df.empty:
            return []

        X = clean_df[ALL_FEATURE_COLUMNS].values
        raw_preds_bps = model.predict(X) * 10000.0

        # Cross-sectional signal standardization at this timestamp
        mu_pred = np.mean(raw_preds_bps)
        std_pred = np.std(raw_preds_bps)
        std_pred = std_pred if std_pred > 1e-4 else 1.0
        z_scores = (raw_preds_bps - mu_pred) / std_pred

        opportunities: List[RankedOpportunity] = []

        for idx, row in clean_df.iterrows():
            sym = row["symbol"]
            pred = float(raw_preds_bps[idx])
            z = float(z_scores[idx])
            price = float(row["raw_close"])
            atr = float(row.get("raw_atr_14", price * 0.005))
            vol = float(row.get("raw_volume", 10000.0))
            atr_bps = (atr / price) * 10000.0 if price > 0 else 20.0

            if price <= 0:
                continue

            # Determine directional side strictly from predicted return sign
            direction = 1 if pred >= 0 else -1
            abs_z = abs(z)

            # Conviction Classification:
            # Q4: Cross-sectionally aligned with |z| >= 1.0 OR absolute prediction >= 15.0 bps
            is_q4 = ((direction == 1 and z >= 1.0) or (direction == -1 and z <= -1.0)) or (abs(pred) >= 15.0)
            # Extreme Top 15%: |z| >= 1.44 OR absolute prediction >= 25.0 bps
            is_extreme = ((direction == 1 and z >= 1.44) or (direction == -1 and z <= -1.44)) or (abs(pred) >= 25.0)

            if is_extreme:
                conviction_tier = ConvictionTier.EXTREME_TOP_15.value
            elif is_q4:
                conviction_tier = ConvictionTier.Q4_TOP_CONVICTION.value
            else:
                conviction_tier = "LOWER"

            # Check if candidate satisfies active conviction filter
            if self.conviction_filter == ConvictionTier.EXTREME_TOP_15:
                conviction_passed = is_extreme
            elif self.conviction_filter == ConvictionTier.Q4_TOP_CONVICTION:
                conviction_passed = (is_q4 or is_extreme)
            else:  # ALL
                conviction_passed = True

            # Calibrated expected gross return incorporating prediction and ATR
            if is_extreme:
                conviction_mult = min(2.0, 1.0 + 0.35 * max(0.0, abs_z - 1.0))
                expected_gross_bps = max(abs(pred), atr_bps * conviction_mult)
            elif is_q4:
                conviction_mult = min(1.5, 0.70 + 0.25 * max(0.0, abs_z - 1.0))
                expected_gross_bps = max(abs(pred) * 0.85, atr_bps * conviction_mult)
            else:
                expected_gross_bps = atr_bps * 0.30

            # Evaluate Authoritative Capital-Aware Ticket Economics
            ticket = self.evaluate_ticket_economics(
                symbol=sym,
                price=price,
                available_capital=available_capital,
                expected_gross_bps=expected_gross_bps,
                vol=vol
            )

            cost_bps = ticket.cost_bps
            env_bps = expected_gross_bps - cost_bps

            # Is tradable?
            is_tradable = conviction_passed and ticket.is_viable and (env_bps >= self.min_env_bps)

            opp = RankedOpportunity(
                symbol=sym,
                timestamp=timestamp,
                direction=direction,
                predicted_return_bps=round(pred, 2),
                z_score=round(z, 2),
                conviction_tier=conviction_tier,
                expected_gross_bps=round(expected_gross_bps, 2),
                expected_cost_bps=round(cost_bps, 2),
                expected_net_value_bps=round(env_bps, 2),
                current_price=price,
                atr=atr,
                volume=vol,
                rank=0,  # assigned below
                ticket_economics=ticket,
                is_tradable=is_tradable
            )
            opportunities.append(opp)

        # Sort descending by Expected Net Value (highest net edge first)
        opportunities.sort(key=lambda o: o.expected_net_value_bps, reverse=True)

        # Assign ranks
        ranked = [
            RankedOpportunity(
                symbol=o.symbol,
                timestamp=o.timestamp,
                direction=o.direction,
                predicted_return_bps=o.predicted_return_bps,
                z_score=o.z_score,
                conviction_tier=o.conviction_tier,
                expected_gross_bps=o.expected_gross_bps,
                expected_cost_bps=o.expected_cost_bps,
                expected_net_value_bps=o.expected_net_value_bps,
                current_price=o.current_price,
                atr=o.atr,
                volume=o.volume,
                rank=i + 1,
                ticket_economics=o.ticket_economics,
                is_tradable=o.is_tradable
            )
            for i, o in enumerate(opportunities)
        ]

        return ranked
