"""
Portfolio Circuit Breakers and Drawdown Halts for AlphaNSE V2.
"""

from typing import Optional


class CircuitBreakerTrippedError(Exception):
    """Raised when an order submission is attempted after the circuit breaker has tripped."""
    pass


class PortfolioCircuitBreaker:
    """
    Monitors intraday portfolio equity and realized losses.
    Enforces a hard trading halt if cumulative daily loss exceeds max_daily_loss_pct (default 2.0%).
    """

    def __init__(self, starting_daily_capital: float, max_daily_loss_pct: float = 0.02):
        self.starting_capital = starting_daily_capital
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_allowed_loss = starting_daily_capital * max_daily_loss_pct
        self.current_realized_loss: float = 0.0
        self._is_tripped: bool = False
        self._trip_reason: Optional[str] = None

    @property
    def is_tripped(self) -> bool:
        return self._is_tripped

    @property
    def trip_reason(self) -> Optional[str]:
        return self._trip_reason

    def record_loss(self, loss_amount: float) -> None:
        """Add realized loss (positive number represents a loss)."""
        if loss_amount > 0:
            self.current_realized_loss += loss_amount
            if self.current_realized_loss >= self.max_allowed_loss:
                self._is_tripped = True
                self._trip_reason = (
                    f"Max daily loss limit breached: realized loss ₹{self.current_realized_loss:.2f} "
                    f">= allowed ₹{self.max_allowed_loss:.2f} ({self.max_daily_loss_pct*100:.1f}%)"
                )

    def assert_trading_permitted(self) -> None:
        """Assert that trading is allowed. Raises CircuitBreakerTrippedError if tripped."""
        if self._is_tripped:
            raise CircuitBreakerTrippedError(f"Trading halted: {self._trip_reason}")

    def reset_for_new_session(self, new_starting_capital: float) -> None:
        """Reset the circuit breaker for a new morning session."""
        self.starting_capital = new_starting_capital
        self.max_allowed_loss = new_starting_capital * self.max_daily_loss_pct
        self.current_realized_loss = 0.0
        self._is_tripped = False
        self._trip_reason = None
