"""
NSE Equity Futures Basis & Cost-of-Carry Model.
Models spot-futures basis, theoretical fair value, basis drift, and rollover friction:
- Cost of Carry: F_t = S_t * [1 + (r - q) * (T - t) / 365]
- Basis convergence: Basis_t -> 0 as t -> T (cash settlement on expiry)
- Intraday basis volatility and slippage
- Calendar spread roll cost for contract transitions
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional
import math
import numpy as np


@dataclass(frozen=True)
class FuturesBasisState:
    """Snapshot of spot-futures basis and fair value."""
    spot_price: float
    futures_price: float
    fair_value: float
    basis_inr: float                # F - S
    basis_bps: float                # (F - S) / S * 10,000
    mispricing_bps: float           # (F - FairValue) / S * 10,000
    days_to_expiry: int
    annualized_carry_rate: float


class FuturesBasisModel:
    """
    Computes fair value pricing, basis dynamics, and basis risk for NSE stock futures.
    """

    def __init__(
        self,
        risk_free_rate: float = 0.065,      # 6.5% RBI repo / MIBOR benchmark
        default_dividend_yield: float = 0.012, # 1.2% typical Nifty constituent dividend yield
        basis_noise_std_bps: float = 2.5,   # Standard deviation of 5m basis noise
        roll_spread_bps: float = 2.0        # One-way calendar roll execution friction
    ):
        self.risk_free_rate = risk_free_rate
        self.default_dividend_yield = default_dividend_yield
        self.basis_noise_std_bps = basis_noise_std_bps
        self.roll_spread_bps = roll_spread_bps

    def compute_fair_value(
        self,
        spot_price: float,
        days_to_expiry: int,
        dividend_yield: Optional[float] = None
    ) -> float:
        """
        Calculates theoretical futures fair value via cost of carry.
        F = S * (1 + (r - q) * (T - t) / 365)
        """
        if spot_price <= 0:
            raise ValueError(f"Spot price must be positive, got {spot_price}")
        if days_to_expiry < 0:
            raise ValueError(f"Days to expiry cannot be negative, got {days_to_expiry}")

        q = dividend_yield if dividend_yield is not None else self.default_dividend_yield
        net_carry = self.risk_free_rate - q
        time_fraction = days_to_expiry / 365.0
        return spot_price * (1.0 + net_carry * time_fraction)

    def evaluate_basis(
        self,
        spot_price: float,
        futures_price: float,
        days_to_expiry: int,
        dividend_yield: Optional[float] = None
    ) -> FuturesBasisState:
        """
        Evaluates observed basis relative to theoretical fair value.
        """
        fair_val = self.compute_fair_value(spot_price, days_to_expiry, dividend_yield)
        basis_inr = futures_price - spot_price
        basis_bps = (basis_inr / spot_price) * 10000.0
        mispricing_bps = ((futures_price - fair_val) / spot_price) * 10000.0
        net_carry = self.risk_free_rate - (dividend_yield if dividend_yield is not None else self.default_dividend_yield)

        return FuturesBasisState(
            spot_price=spot_price,
            futures_price=futures_price,
            fair_value=fair_val,
            basis_inr=basis_inr,
            basis_bps=basis_bps,
            mispricing_bps=mispricing_bps,
            days_to_expiry=days_to_expiry,
            annualized_carry_rate=net_carry
        )

    def simulate_synthetic_futures_return(
        self,
        spot_return: float,
        days_to_expiry_start: int,
        holding_period_days: float = 1.0 / 75.0,  # Single 5m bar = 1/75 of trading day
        random_seed: Optional[int] = None
    ) -> float:
        """
        Translates a cash spot return into a synthetic futures return:
        R_fut = R_spot + Delta_carry + Epsilon_basis
        Where Delta_carry is theta convergence and Epsilon_basis is microstructure noise.
        """
        if random_seed is not None:
            np.random.seed(random_seed)

        # Decay of carry over holding period
        time_decay = holding_period_days / 365.0
        net_carry = self.risk_free_rate - self.default_dividend_yield
        carry_drift = -net_carry * time_decay  # Basis contracts towards expiry

        # Basis noise component
        basis_noise = np.random.normal(0, self.basis_noise_std_bps / 10000.0)

        # Total synthetic futures return
        return spot_return + carry_drift + basis_noise
