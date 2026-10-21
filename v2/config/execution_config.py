"""
Execution Engine Configuration for AlphaNSE V2.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionConfig:
    default_slippage_bps: float = 2.5          # Default modeled slippage: 2.5 bps (0.025%)
    simulated_latency_ms: int = 50             # Internal pipeline and order dispatch buffer
    order_timeout_seconds: int = 30            # Timeout before marking pending order as EXPIRED
    max_retries: int = 3                       # Retries for state reconciliation
    enforce_idempotency: bool = True           # Reject any order with reused idempotency key
    allow_partial_fills: bool = False          # Intraday cash equity paper default
