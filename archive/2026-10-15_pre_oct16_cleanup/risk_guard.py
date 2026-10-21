import logging
from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class RiskLimits:
    max_position_size_pct: float = 0.10  # Max 10% of capital per trade
    max_daily_loss_pct: float = 0.02      # Stop all trading if 2% loss in a day
    min_available_margin: float = 5000.0 # Minimum cash to keep in account
    max_open_positions: int = 5          # Max simultaneous trades

class AutonomousRiskGuard:
    """
    The 'Financial Bodyguard'.
    This class overrides the AI and can force-close positions or block trades.
    """
    def __init__(self, limits: RiskLimits = RiskLimits()):
        self.limits = limits
        self.logger = logging.getLogger("RiskGuard")
        self.daily_start_balance = None
        self.current_daily_loss = 0.0

    def validate_trade(self, proposed_investment: float, total_capital: float, open_positions_count: int) -> (bool, str):
        """Check if a trade is safe before sending it to the broker."""

        # 1. Check Max Position Size
        if proposed_investment > (total_capital * self.limits.max_position_size_pct):
            return False, f"Trade size too large: {proposed_investment} > limit {total_capital * self.limits.max_position_size_pct}"

        # 2. Check Max Open Positions
        if open_positions_count >= self.limits.max_open_positions:
            return False, f"Too many open positions: {open_positions_count} >= {self.limits.max_open_positions}"

        # 3. Check Daily Loss Limit
        if self.current_daily_loss > (self.daily_start_balance * self.limits.max_daily_loss_pct if self.daily_start_balance else float('inf')):
            return False, "Daily loss limit reached. Trading suspended for today."

        return True, "SAFE"

    def update_daily_pnl(self, current_balance: float):
        """Track daily performance to enforce stop-loss."""
        if self.daily_start_balance is None:
            self.daily_start_balance = current_balance

        self.current_daily_loss = self.daily_start_balance - current_balance
        if self.current_daily_loss > 0:
            self.logger.warning(f"Current daily loss: Rs.{self.current_daily_loss:.2f}")

    def reset_day(self, current_balance: float):
        """Reset trackers for a new trading day."""
        self.daily_start_balance = current_balance
        self.current_daily_loss = 0.0
