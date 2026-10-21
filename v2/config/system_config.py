"""
Central Application Configuration for AlphaNSE V2.
Aggregates all subsystem configurations into a single validated, immutable tree.
"""

from dataclasses import dataclass, field
import os

from .market_config import MarketHoursConfig, UniverseConfig
from .risk_config import RiskConfig
from .execution_config import ExecutionConfig
from .model_config import ModelConfig


@dataclass(frozen=True)
class AppConfig:
    environment: str = "RESEARCH"              # "RESEARCH" | "PAPER" | "LIVE"
    starting_capital: float = 5000.0           # Default starting account capital in INR
    data_dir: str = field(default_factory=lambda: os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "QA", "data")))
    logs_dir: str = field(default_factory=lambda: os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "QA", "logs")))
    market: MarketHoursConfig = field(default_factory=MarketHoursConfig)
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    model: ModelConfig = field(default_factory=ModelConfig)

    def validate(self) -> None:
        """Sanity check configuration boundaries."""
        if self.starting_capital <= 0:
            raise ValueError(f"Starting capital must be positive: {self.starting_capital}")
        if not (0 < self.risk.max_daily_loss_pct < 0.5):
            raise ValueError(f"Invalid max_daily_loss_pct: {self.risk.max_daily_loss_pct}")
        if not (0 < self.risk.max_risk_per_trade_pct < 0.2):
            raise ValueError(f"Invalid max_risk_per_trade_pct: {self.risk.max_risk_per_trade_pct}")
        if not (0 < self.risk.max_position_allocation_pct <= 1.0):
            raise ValueError(f"Invalid max_position_allocation_pct: {self.risk.max_position_allocation_pct}")
        if self.risk.max_open_positions < 1:
            raise ValueError(f"max_open_positions must be >= 1: {self.risk.max_open_positions}")


def load_config(environment: str = "RESEARCH", starting_capital: float = 5000.0) -> AppConfig:
    cfg = AppConfig(environment=environment, starting_capital=starting_capital)
    cfg.validate()
    return cfg
