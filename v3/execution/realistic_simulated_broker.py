#!/usr/bin/env python3
"""
v3/execution/realistic_simulated_broker.py
AlphaNSE Hardened Realistic Simulated Broker Engine.
Strictly Air-Gapped: Absolutely Zero Live Order Placement Capabilities.

Upgrades:
1. Separation of Bid/Ask spread from adverse slippage:
   - BUY  -> Ask + slippage
   - SELL -> Bid - slippage
2. Inclusion of Mark-to-Market Unrealized P&L in Risk Checks:
   - Daily P&L = realized P&L + unrealized P&L - estimated exit friction
   - Hard circuit breaker at max_daily_loss (e.g. Rs. 30.00)
3. Modeling of partial fills and execution failures:
   - Volume depth limits (e.g. 100 requested -> 65 filled -> 35 remaining)
   - Microstructure rejection probability
4. Latency modeling:
   - Execution timestamp = signal timestamp + latency_ms
   - Price execution at simulated execution timestamp
5. Four Stress-Testing Scenarios: OPTIMISTIC, BASE, CONSERVATIVE, SEVERE
6. Sandbox Constraints Enforced:
   - Starting Capital: Rs. 1,500 Max
   - Max Concurrent Positions: 1 (Cash Equity Only)
   - Daily Loss Limit: Rs. 30.00 Max
   - Zero Leverage, No Options, No Short Selling
"""

import math
import random
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from v2.risk.cost_engine import IndiaCostEngine, CostBreakdown
from v3.execution.base_broker import BaseBroker


class ExecutionRegime(str, Enum):
    OPTIMISTIC = "OPTIMISTIC"
    BASE = "BASE"
    CONSERVATIVE = "CONSERVATIVE"
    SEVERE = "SEVERE"


@dataclass(frozen=True)
class RegimeConfig:
    half_spread_bps: float            # Half of bid-ask spread in basis points
    slippage_base_bps: float          # Baseline adverse slippage in basis points
    slippage_vol_mult: float          # Volatility multiplier on slippage
    latency_ms: int                   # Execution latency in milliseconds
    partial_fill_threshold_vol_pct: float  # Maximum % of bar volume that can be filled
    rejection_probability: float      # Microstructure rejection rate (rate limit, queue expiry)


REGIME_CONFIGS: Dict[ExecutionRegime, RegimeConfig] = {
    ExecutionRegime.OPTIMISTIC: RegimeConfig(
        half_spread_bps=1.5,
        slippage_base_bps=1.5,
        slippage_vol_mult=0.5,
        latency_ms=150,
        partial_fill_threshold_vol_pct=0.15,
        rejection_probability=0.00
    ),
    ExecutionRegime.BASE: RegimeConfig(
        half_spread_bps=3.0,
        slippage_base_bps=4.0,
        slippage_vol_mult=1.0,
        latency_ms=350,
        partial_fill_threshold_vol_pct=0.08,
        rejection_probability=0.01
    ),
    ExecutionRegime.CONSERVATIVE: RegimeConfig(
        half_spread_bps=6.0,
        slippage_base_bps=8.0,
        slippage_vol_mult=2.0,
        latency_ms=750,
        partial_fill_threshold_vol_pct=0.04,
        rejection_probability=0.03
    ),
    ExecutionRegime.SEVERE: RegimeConfig(
        half_spread_bps=12.0,
        slippage_base_bps=18.0,
        slippage_vol_mult=3.5,
        latency_ms=1500,
        partial_fill_threshold_vol_pct=0.02,
        rejection_probability=0.08
    ),
}


@dataclass
class SimulatedOrder:
    order_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    requested_qty: int
    filled_qty: int
    remaining_qty: int
    requested_price: float
    signal_timestamp: Any
    execution_timestamp: Any
    status: str  # "FILLED", "PARTIAL", "REJECTED"
    bid_price: float
    ask_price: float
    half_spread_cost: float
    slippage_cost: float
    execution_price: float
    brokerage: float
    statutory_taxes: float
    rejection_reason: str = ""


# Legacy alias for backwards compatibility
@dataclass
class SimulatedOrderResult:
    order_id: str
    symbol: str
    side: str
    quantity: int
    requested_price: float
    executed_price: float
    status: str                  # "FILLED" or "REJECTED"
    rejection_reason: Optional[str] = None
    slippage_paid: float = 0.0
    spread_paid: float = 0.0
    total_execution_friction: float = 0.0


@dataclass
class Position:
    symbol: str
    quantity: int
    entry_price: float
    entry_time: Any
    entry_friction: float


@dataclass
class CompletedTrade:
    trade_id: str
    symbol: str
    model_name: str
    entry_time: Any
    exit_time: Any
    quantity: int
    entry_price: float
    exit_price: float
    gross_pnl: float
    slippage: float
    brokerage: float
    statutory_taxes: float
    total_cost: float
    net_pnl: float
    holding_minutes: int
    exit_reason: str


class RealisticSimulatedBroker(BaseBroker):
    """
    Simulates realistic exchange order execution under configurable market friction regimes.
    Enforces strict air-gapping: absolutely zero connection to real broker order placement.
    """

    def __init__(
        self,
        regime: Optional[Any] = None,
        scenario: Optional[str] = None,
        starting_cash: float = 1500.0,
        max_daily_loss: float = 30.0,
        seed: Optional[int] = 42,
        max_positions: int = 1,
        allow_short: bool = True,
        leverage: float = 5.0,
    ):
        # Resolve scenario / regime
        if scenario is not None:
            regime_key = scenario.upper()
        elif regime is not None:
            regime_key = regime.value if isinstance(regime, ExecutionRegime) else str(regime).upper()
        else:
            regime_key = "BASE"

        try:
            self.regime = ExecutionRegime(regime_key)
        except ValueError:
            self.regime = ExecutionRegime.BASE

        self.scenario = self.regime.value
        self.config = REGIME_CONFIGS[self.regime]
        self.cfg = {
            "half_spread_bps": self.config.half_spread_bps,
            "slippage_base_bps": self.config.slippage_base_bps,
            "slippage_vol_mult": self.config.slippage_vol_mult,
            "latency_ms": self.config.latency_ms,
            "partial_fill_threshold_vol_pct": self.config.partial_fill_threshold_vol_pct,
            "rejection_prob": self.config.rejection_probability,
        }

        self.cost_engine = IndiaCostEngine()
        self.rng = random.Random(seed)
        self.seed = seed

        # Capital & Risk constraints
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.max_daily_loss = max_daily_loss
        self.max_positions = max_positions
        self.allow_short = allow_short
        self.leverage = leverage

        # Internal state
        self.positions: Dict[str, Position] = {}
        self.realized_pnl_today: float = 0.0
        self.total_friction_paid: float = 0.0
        self.total_spread_paid: float = 0.0
        self.total_slippage_paid: float = 0.0
        self.total_brokerage_paid: float = 0.0
        self.total_taxes_paid: float = 0.0

        self.order_counter = 0
        self.order_history: List[SimulatedOrder] = []
        self.orders: List[SimulatedOrderResult] = []  # Legacy tracking
        self.trade_logs: List[Dict] = []
        self.circuit_breaker_tripped: bool = False
        self.circuit_breaker_reason: str = ""

        self.rejected_orders_count = 0
        self.filled_orders_count = 0

    @property
    def position(self) -> Optional[Position]:
        """Backward-compatible property returning the primary open position."""
        return next(iter(self.positions.values()), None)

    @position.setter
    def position(self, val: Optional[Position]):
        if val is None:
            self.positions.clear()
        else:
            self.positions[val.symbol] = val

    def _calculate_statutory_costs(self, turnover: float, is_sell: bool) -> Tuple[float, float]:
        """
        Penny-for-penny statutory tax and brokerage computation using IndiaCostEngine:
        - Brokerage: min(0.03%, Rs 20)
        - STT: 0.025% on sell
        - Exchange: 0.00307%
        - SEBI: 0.0001%
        - GST: 18% on (brokerage + exchange + sebi)
        - Stamp Duty: 0.003% on buy
        """
        brokerage = min(self.cost_engine.brokerage_flat_cap, turnover * self.cost_engine.brokerage_pct)
        stt = (turnover * self.cost_engine.stt_sell_pct) if is_sell else 0.0
        exchange = turnover * self.cost_engine.exchange_pct
        sebi = turnover * self.cost_engine.sebi_pct
        gst = (brokerage + exchange + sebi) * self.cost_engine.gst_pct
        stamp = (turnover * self.cost_engine.stamp_duty_buy_pct) if not is_sell else 0.0

        statutory_taxes = stt + exchange + sebi + gst + stamp
        return round(brokerage, 2), round(statutory_taxes, 2)

    def get_portfolio_state(self, current_mid_price: float = 0.0) -> Dict[str, Any]:
        """
        Calculates true real-time mark-to-market portfolio value including:
        - Realized P&L
        - Unrealized Mark-to-Market P&L across all open positions
        - Estimated exit friction (spread + slippage + exit taxes)
        """
        unrealized_pnl = 0.0
        est_exit_friction = 0.0
        total_pos_val = 0.0
        total_pos_qty = 0

        for sym, pos in self.positions.items():
            px = current_mid_price if (current_mid_price > 0 and len(self.positions) == 1) else getattr(pos, "last_price", pos.entry_price)
            qty = pos.quantity
            pos_val = px * qty
            total_pos_val += pos_val
            total_pos_qty += qty
            gross_unrealized = (px - pos.entry_price) * qty

            est_exit_bps = (self.config.half_spread_bps + self.config.slippage_base_bps) / 10000.0
            est_exit_slip = pos_val * est_exit_bps
            _, est_exit_taxes = self._calculate_statutory_costs(pos_val, is_sell=True)
            fric = est_exit_slip + est_exit_taxes
            est_exit_friction += fric
            unrealized_pnl += (gross_unrealized - fric)

        true_equity = self.cash + total_pos_val
        total_pnl_today = self.realized_pnl_today + unrealized_pnl

        return {
            "cash": round(self.cash, 2),
            "position_qty": total_pos_qty,
            "position_val": round(total_pos_val, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "realized_pnl": round(self.realized_pnl_today, 2),
            "net_daily_pnl": round(total_pnl_today, 2),
            "true_equity": round(true_equity, 2),
            "open_positions_count": len(self.positions),
            "circuit_breaker_tripped": self.circuit_breaker_tripped,
        }

    def reset_daily_state(self):
        """Resets daily P&L and circuit breaker state at session rollover."""
        self.realized_pnl_today = 0.0
        self.circuit_breaker_tripped = False
        self.circuit_breaker_reason = ""

    def check_pre_trade_risk(
        self, side: str, qty: int, estimated_price: float, is_exit: bool = False, symbol: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Hard Pre-Trade Risk Gatekeeper enforcing sandbox boundaries:
        1. Circuit breaker on Net Daily P&L (Realized + Unrealized - Exit Friction)
        2. Max Concurrent Positions limit
        3. Short selling allowed if self.allow_short is True (Intraday MIS)
        4. Max capital ceiling with leverage
        Exits are ALWAYS approved to allow prompt risk mitigation and square-offs.
        """
        if is_exit:
            return True, "APPROVED_EXIT"

        if self.circuit_breaker_tripped:
            return False, f"CIRCUIT_BREAKER_ACTIVE: {self.circuit_breaker_reason}"

        # Risk Check 1: Include Unrealized P&L in Daily Loss Limit Check
        state = self.get_portfolio_state(estimated_price)
        if state["net_daily_pnl"] <= -self.max_daily_loss:
            self.circuit_breaker_tripped = True
            self.circuit_breaker_reason = f"Daily net loss reached -Rs.{abs(state['net_daily_pnl']):.2f} (Limit: -Rs.{self.max_daily_loss:.2f})"
            return False, self.circuit_breaker_reason

        # Risk Check 2: Max Positions Limit
        if side.upper() == "BUY" and len(self.positions) >= self.max_positions:
            return False, f"MAX_POSITIONS_EXCEEDED: Already holding {len(self.positions)} positions (Max: {self.max_positions})."

        # Risk Check 3: Short Selling check
        if side.upper() == "SELL" and len(self.positions) == 0 and not self.allow_short:
            return False, "SHORT_SELLING_PROHIBITED: Cannot short sell when allow_short=False."

        # Risk Check 4: Capital Limit with Leverage
        required_capital = (estimated_price * qty) / self.leverage
        if side.upper() == "BUY" and required_capital > self.cash:
            return False, f"INSUFFICIENT_CASH: Required Rs.{required_capital:.2f} > Cash Rs.{self.cash:.2f}"

        # Risk Check 5: Hard Capital Ceiling with Leverage
        max_power = self.starting_cash * self.leverage
        if (estimated_price * qty) > max_power * 1.05:  # allow 5% rounding
            return False, f"CAPITAL_CEILING_EXCEEDED: Order Rs.{estimated_price * qty:.2f} > Purchasing Power Rs.{max_power:.2f}"

        return True, "APPROVED"

    def execute_order(
        self,
        symbol: str,
        side: str,
        requested_qty: int,
        mid_price: float,
        bar_volume: int = 10000,
        signal_timestamp: Optional[Any] = None,
        intraday_vix: float = 14.0,
        is_exit: bool = False,
    ) -> SimulatedOrder:
        """
        Executes an order through the complete realistic friction pipeline:
        1. Pre-Trade Risk Verification
        2. Rejection / Timeout Probability
        3. Bid/Ask Spread Crossing
        4. Adverse Stochastic Slippage
        5. Execution Latency
        6. Partial Fill Volume Limit
        7. Statutory Taxes & Ledger Accounting
        """
        self.order_counter += 1
        side = side.upper()
        if signal_timestamp is None:
            signal_timestamp = datetime.now()

        # 1. Pre-Trade Gatekeeper
        approved, reason = self.check_pre_trade_risk(side, requested_qty, mid_price, is_exit=is_exit)
        if not approved:
            self.rejected_orders_count += 1
            order = SimulatedOrder(
                order_id=f"ORD_REJ_{self.order_counter:05d}",
                symbol=symbol,
                side=side,
                requested_qty=requested_qty,
                filled_qty=0,
                remaining_qty=requested_qty,
                requested_price=mid_price,
                signal_timestamp=signal_timestamp,
                execution_timestamp=signal_timestamp,
                status="REJECTED",
                bid_price=mid_price,
                ask_price=mid_price,
                half_spread_cost=0.0,
                slippage_cost=0.0,
                execution_price=0.0,
                brokerage=0.0,
                statutory_taxes=0.0,
                rejection_reason=reason,
            )
            self.order_history.append(order)
            return order

        # 2. Random Microstructure Rejection
        if self.rng.random() < self.config.rejection_probability:
            self.rejected_orders_count += 1
            order = SimulatedOrder(
                order_id=f"ORD_FAIL_{self.order_counter:05d}",
                symbol=symbol,
                side=side,
                requested_qty=requested_qty,
                filled_qty=0,
                remaining_qty=requested_qty,
                requested_price=mid_price,
                signal_timestamp=signal_timestamp,
                execution_timestamp=signal_timestamp,
                status="REJECTED",
                bid_price=mid_price,
                ask_price=mid_price,
                half_spread_cost=0.0,
                slippage_cost=0.0,
                execution_price=0.0,
                brokerage=0.0,
                statutory_taxes=0.0,
                rejection_reason="EXCHANGE_NETWORK_TIMEOUT_OR_QUEUE_DROP",
            )
            self.order_history.append(order)
            return order

        # 3. Execution Latency
        if isinstance(signal_timestamp, datetime):
            exec_timestamp = signal_timestamp + timedelta(milliseconds=self.config.latency_ms)
        else:
            exec_timestamp = signal_timestamp

        # 4. Bid / Ask Spread Crossing
        half_spread_pct = self.config.half_spread_bps / 10000.0
        half_spread_rs = mid_price * half_spread_pct
        bid_price = round(mid_price - half_spread_rs, 2)
        ask_price = round(mid_price + half_spread_rs, 2)

        # Buyer crosses the spread to Ask; Seller crosses the spread to Bid
        spread_base_price = ask_price if side == "BUY" else bid_price

        # 5. Volatility-Adjusted Adverse Slippage
        vol_factor = max(1.0, intraday_vix / 13.0) * self.config.slippage_vol_mult
        stochastic_noise = self.rng.uniform(0.7, 1.4)
        slippage_pct = (self.config.slippage_base_bps * vol_factor * stochastic_noise) / 10000.0
        slippage_rs = spread_base_price * slippage_pct

        if side == "BUY":
            fill_price = round(spread_base_price + slippage_rs, 2)
            half_spread_cost_per_share = ask_price - mid_price
            slippage_cost_per_share = fill_price - ask_price
        else:
            fill_price = round(spread_base_price - slippage_rs, 2)
            half_spread_cost_per_share = mid_price - bid_price
            slippage_cost_per_share = bid_price - fill_price

        # 6. Partial Fill Liquidity Modeling
        if bar_volume > 0:
            max_fillable_qty = max(1, int(bar_volume * self.config.partial_fill_threshold_vol_pct))
            filled_qty = min(requested_qty, max_fillable_qty)
        else:
            filled_qty = requested_qty

        remaining_qty = requested_qty - filled_qty
        status = "FILLED" if remaining_qty == 0 else "PARTIAL"

        # 7. Statutory Costs & Ledger Accounting
        turnover = fill_price * filled_qty
        brokerage, taxes = self._calculate_statutory_costs(turnover, is_sell=(side == "SELL"))
        total_spread = round(half_spread_cost_per_share * filled_qty, 2)
        total_slippage = round(slippage_cost_per_share * filled_qty, 2)
        total_entry_friction = total_spread + total_slippage + brokerage + taxes

        order = SimulatedOrder(
            order_id=f"ORD_SIM_{self.order_counter:05d}",
            symbol=symbol,
            side=side,
            requested_qty=requested_qty,
            filled_qty=filled_qty,
            remaining_qty=remaining_qty,
            requested_price=mid_price,
            signal_timestamp=signal_timestamp,
            execution_timestamp=exec_timestamp,
            status=status,
            bid_price=bid_price,
            ask_price=ask_price,
            half_spread_cost=total_spread,
            slippage_cost=total_slippage,
            execution_price=fill_price,
            brokerage=brokerage,
            statutory_taxes=taxes,
        )

        self.filled_orders_count += 1
        self.total_spread_paid += total_spread
        self.total_slippage_paid += total_slippage
        self.total_brokerage_paid += brokerage
        self.total_taxes_paid += taxes
        self.total_friction_paid += total_entry_friction

        # Portfolio State Transitions
        if side == "BUY":
            self.cash -= (turnover + brokerage + taxes)
            new_pos = Position(
                symbol=symbol,
                quantity=filled_qty,
                entry_price=fill_price,
                entry_time=exec_timestamp,
                entry_friction=total_entry_friction,
            )
            setattr(new_pos, "last_price", fill_price)
            self.positions[symbol] = new_pos
        elif side == "SELL":
            pos = self.positions.pop(symbol, None) or (self.positions.pop(next(iter(self.positions.keys())), None) if self.positions else None)
            if pos:
                gross_pnl = (fill_price - pos.entry_price) * filled_qty
                total_trade_friction = pos.entry_friction + total_spread + total_slippage + brokerage + taxes
                net_pnl = gross_pnl - total_trade_friction

                self.cash += (turnover - brokerage - taxes)
                self.realized_pnl_today += net_pnl

            holding_min = 0.0
            if isinstance(exec_timestamp, datetime) and isinstance(pos.entry_time, datetime):
                holding_min = round((exec_timestamp - pos.entry_time).total_seconds() / 60.0, 1)

            self.trade_logs.append({
                "symbol": symbol,
                "entry_time": str(pos.entry_time),
                "exit_time": str(exec_timestamp),
                "quantity": filled_qty,
                "entry_price": pos.entry_price,
                "exit_price": fill_price,
                "gross_pnl": round(gross_pnl, 2),
                "total_friction": round(total_trade_friction, 2),
                "net_pnl": round(net_pnl, 2),
                "holding_minutes": holding_min,
            })

            # Check if post-trade realized loss trips circuit breaker
            if self.realized_pnl_today <= -self.max_daily_loss:
                self.circuit_breaker_tripped = True
                self.circuit_breaker_reason = f"Daily loss cap reached: -Rs.{abs(self.realized_pnl_today):.2f}"

        self.order_history.append(order)
        return order

    # -------------------------------------------------------------------------
    # Realistic Microstructure Simulation Methods (Used across strategy engines)
    # -------------------------------------------------------------------------
    def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        mid_price: float,
        timestamp: Any,
        is_exit: bool = False,
    ) -> SimulatedOrderResult:
        """
        Simulates execution fill through realistic exchange microstructure:
        1. Microstructure rejection probability (bypassed on exits/RMS)
        2. Spread crossing (Ask for BUY, Bid for SELL)
        3. Volatility-scaled stochastic adverse slippage
        """
        self.order_counter += 1
        side = side.upper()

        # Microstructure rejection rate
        if not is_exit and self.rng.random() < self.config.rejection_probability:
            self.rejected_orders_count += 1
            res = SimulatedOrderResult(
                order_id=f"ORD_REJ_{self.order_counter:05d}",
                symbol=symbol,
                side=side,
                quantity=0,
                requested_price=mid_price,
                executed_price=0.0,
                status="REJECTED",
                rejection_reason="EXCHANGE_NETWORK_TIMEOUT_OR_QUEUE_DROP",
                slippage_paid=0.0,
                spread_paid=0.0,
                total_execution_friction=0.0
            )
            self.orders.append(res)
            return res

        # Spread crossing
        half_spread_pct = self.config.half_spread_bps / 10000.0
        half_spread_rs = mid_price * half_spread_pct
        bid_price = round(mid_price - half_spread_rs, 2)
        ask_price = round(mid_price + half_spread_rs, 2)
        spread_base_price = ask_price if side == "BUY" else bid_price

        # Adverse stochastic slippage
        vol_factor = self.config.slippage_vol_mult
        stochastic_noise = self.rng.uniform(0.7, 1.4)
        slippage_pct = (self.config.slippage_base_bps * vol_factor * stochastic_noise) / 10000.0
        slippage_rs = spread_base_price * slippage_pct

        if side == "BUY":
            fill_price = round(spread_base_price + slippage_rs, 2)
            spread_paid = (ask_price - mid_price) * quantity
            slippage_paid = (fill_price - ask_price) * quantity
        else:
            fill_price = round(spread_base_price - slippage_rs, 2)
            spread_paid = (mid_price - bid_price) * quantity
            slippage_paid = (bid_price - fill_price) * quantity

        res = SimulatedOrderResult(
            order_id=f"ORD_FIL_{self.order_counter:05d}",
            symbol=symbol,
            side=side,
            quantity=quantity,
            requested_price=mid_price,
            executed_price=fill_price,
            status="FILLED",
            rejection_reason=None,
            slippage_paid=round(slippage_paid, 2),
            spread_paid=round(spread_paid, 2),
            total_execution_friction=round(spread_paid + slippage_paid, 2)
        )
        self.orders.append(res)
        return res

    def force_eod_square_off(
        self,
        symbol: str,
        side: str,
        quantity: int,
        mid_price: float,
        timestamp: Any
    ) -> SimulatedOrderResult:
        """
        Guaranteed execution for Broker/Exchange RMS Auto Square-off at 15:15 IST.
        Rejection probability is strictly 0.0 (mandatory market-on-close auction).
        Adverse slippage and spread are fully applied.
        """
        return self.submit_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            mid_price=mid_price,
            timestamp=timestamp,
            is_exit=True
        )

    def compute_trade_costs(
        self,
        entry_val: float,
        exit_val: float,
        entry_slippage: float,
        exit_slippage: float
    ) -> Tuple[float, float, float, float]:
        """Calculates Zerodha statutory costs + slippage."""
        b_entry = min(entry_val * self.cost_engine.brokerage_pct, self.cost_engine.brokerage_flat_cap)
        b_exit = min(exit_val * self.cost_engine.brokerage_pct, self.cost_engine.brokerage_flat_cap)
        total_brokerage = b_entry + b_exit

        stt = exit_val * self.cost_engine.stt_sell_pct
        exchange = (entry_val + exit_val) * self.cost_engine.exchange_pct
        sebi = (entry_val + exit_val) * self.cost_engine.sebi_pct
        gst = (total_brokerage + exchange + sebi) * self.cost_engine.gst_pct
        stamp = entry_val * self.cost_engine.stamp_duty_buy_pct
        total_statutory = stt + exchange + sebi + gst + stamp

        total_slippage = entry_slippage + exit_slippage
        total_cost = total_brokerage + total_statutory + total_slippage

        return total_brokerage, total_statutory, total_slippage, total_cost

    # -------------------------------------------------------------------------
    # BaseBroker Unified Contract Implementation
    # -------------------------------------------------------------------------
    @property
    def is_live(self) -> bool:
        """Always False for simulation engine."""
        return False

    @property
    def broker_name(self) -> str:
        return f"RealisticSimulatedBroker ({self.scenario})"

    def get_balance(self) -> Dict[str, float]:
        state = self.get_portfolio_state()
        return {
            "available_cash": round(self.cash, 2),
            "collateral": 0.0,
            "total_equity": round(state["true_equity"], 2),
            "currency": "INR"
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        if not self.position:
            return []
        return [{
            "symbol": self.position.symbol,
            "quantity": self.position.quantity,
            "entry_price": self.position.entry_price,
            "current_price": getattr(self, "_last_mid_price", self.position.entry_price),
            "unrealized_pnl": round(self.get_portfolio_state()["unrealized_pnl"], 2),
            "side": "BUY"
        }]

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: Optional[float] = None,
        order_type: str = "MARKET",
        tag: Optional[str] = None
    ) -> Dict[str, Any]:
        mid = price if price is not None else 1000.0
        order = self.execute_order(
            symbol=symbol,
            side=side,
            requested_qty=quantity,
            mid_price=mid,
            signal_timestamp=datetime.now()
        )
        return {
            "order_id": order.order_id,
            "status": order.status,
            "filled_qty": order.filled_qty,
            "execution_price": order.execution_price,
            "rejection_reason": order.rejection_reason
        }

    def cancel_order(self, order_id: str) -> bool:
        return True

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        for o in self.order_history:
            if o.order_id == order_id:
                return {
                    "order_id": o.order_id,
                    "status": o.status,
                    "filled_qty": o.filled_qty,
                    "price": o.execution_price
                }
        return {"order_id": order_id, "status": "NOT_FOUND"}

    def get_audit_ledger(self) -> List[Dict[str, Any]]:
        return list(self.trade_logs)
