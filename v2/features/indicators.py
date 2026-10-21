"""
Pure mathematical indicators and formulas for intraday microstructure features.
"""

import math
from typing import Tuple, Optional


def calculate_true_range(high: float, low: float, prev_close: Optional[float]) -> float:
    """Calculate True Range for a bar given current H/L and previous Close."""
    if prev_close is None:
        return high - low
    return max(
        high - low,
        abs(high - prev_close),
        abs(low - prev_close)
    )


def calculate_parkinson_volatility(high: float, low: float) -> float:
    """Parkinson extreme-value volatility estimator from bar High and Low."""
    if low <= 0 or high <= 0 or high < low:
        return 0.0
    hl_ratio = math.log(high / low)
    return math.sqrt((hl_ratio ** 2) / (4.0 * math.log(2.0)))


def calculate_rsi(gains: list, losses: list) -> float:
    """RSI from average gains and losses over a rolling window. Returns 50.0 if flat."""
    avg_gain = sum(gains) / len(gains) if gains else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    if avg_gain == 0.0 and avg_loss == 0.0:
        return 50.0
    rs = avg_gain / (avg_loss + 1e-9)
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_wick_ratios(open_p: float, high: float, low: float, close: float) -> Tuple[float, float, float]:
    """
    Returns (wick_pressure, upper_wick_ratio, lower_wick_ratio).
    All ratios bounded in [0.0, 1.0].
    """
    bar_span = max(high - low, 1e-5)
    wick_pressure = max(0.0, min(1.0, (close - low) / bar_span))
    upper_wick = max(0.0, min(1.0, (high - max(open_p, close)) / bar_span))
    lower_wick = max(0.0, min(1.0, (min(open_p, close) - low) / bar_span))
    return wick_pressure, upper_wick, lower_wick
