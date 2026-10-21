"""
Risk Engine Configuration for AlphaNSE V2.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    """
    Typed parameters for portfolio risk control and integer position sizing.
    
    IMPORTANT NOTE:
    Arbitrary single-share price caps (such as the legacy ₹1,250 cap) are eliminated.
    Symbol tradability is strictly evaluated on economic feasibility:
    available cash, integer whole shares, risk-capital-per-trade, and ATR stop distance.
    """
    max_daily_loss_pct: float = 0.02           # 2.0% daily portfolio drawdown circuit breaker
    max_risk_per_trade_pct: float = 0.01       # 1.0% maximum risk of portfolio equity per trade
    max_position_allocation_pct: float = 0.25  # 25% max total capital invested in any single stock
    max_open_positions: int = 5                # Maximum simultaneous open positions
    min_trade_allocation_inr: float = 350.0    # Minimum economically viable order allocation (INR)
    default_atr_stop_multiplier: float = 1.5   # Stop loss placed at 1.5 * ATR from entry
    max_hold_bars: int = 15                    # Maximum bars to hold a scalp before decay liquidation
    cooldown_seconds: int = 300                # Cooldown after closing a position on a symbol
