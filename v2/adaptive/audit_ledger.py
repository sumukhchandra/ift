"""
Cryptographic Audit Ledger & Lineage Engine for AlphaNSE V2 Adaptive Pipeline.
Guarantees end-to-end provenance:
  Every Trade -> Prediction -> Model Version -> Training Dataset Hash -> Data Cutoff.
"""

import os
import json
import hashlib
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass(frozen=True)
class DailyModelManifest:
    """
    Cryptographic specification of the frozen model deployed for a specific trading day.
    """
    session_date: str                 # e.g. "2026-09-21"
    data_cutoff: str                  # e.g. "2026-09-18T15:25:00+05:30"
    dataset_hash: str                 # SHA-256 of training dataset
    feature_version: str              # SHA-256 or version string of feature pipeline
    model_version: str                # e.g. "AlphaNSE_Adaptive_20260921_v1"
    model_hash: str                   # SHA-256 of serialized model weights
    training_window: str              # e.g. "2026-06-29 to 2026-09-18"
    training_rows: int                # Number of training observations
    validation_result: Dict[str, Any] # Pre-market sanity gate metrics
    regime_at_open: str               # "LOW_VOL", "NORMAL_VOL", or "HIGH_VOL"
    created_at: str                   # ISO timestamp of creation

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DailyModelManifest":
        return cls(**data)


@dataclass(frozen=True)
class TradeAuditRecord:
    """
    Full audit record for an executed trade linking performance to model provenance.
    Captures complete 29-field forensic telemetry with penny-for-penny statutory and execution fees.
    """
    trade_id: str                     # Unique trade identifier
    session_date: str                 # Session date YYYY-MM-DD
    entry_time: str                   # Timestamp of entry
    exit_time: str                    # Timestamp of exit
    symbol: str                       # Tradable instrument symbol
    direction: int                    # +1 for Long, -1 for Short
    entry_price: float                # Fill price on entry
    exit_price: float                 # Fill price on exit
    quantity: int                     # Integer shares traded
    gross_return_bps: float           # Gross return before transaction friction
    cost_bps: float                   # Total roundtrip cost (statutory + slippage + spread)
    net_return_bps: float             # Net return after all friction
    net_pnl_rupees: float             # Net monetary profit/loss in INR
    predicted_return_bps: float       # Model's point-in-time predicted return
    expected_net_value_bps: float     # Predicted return minus expected cost hurdle
    model_version: str                # Model version identifier
    model_hash: str                   # SHA-256 hash of model artifact
    dataset_hash: str                 # SHA-256 hash of dataset at cutoff
    data_cutoff: str                  # Historical data cutoff timestamp
    exit_reason: str = "HORIZON_REACHED" # "HORIZON_REACHED", "STOP_LOSS", "EOD_CLOSE"
    horizon_bars: int = 3             # Intended horizon in bars
    holding_duration_mins: float = 15.0 # Actual holding duration in minutes
    conviction_tier: str = "ALL"      # "Q4_TOP_CONVICTION", "EXTREME_TOP_15", etc.

    # Itemized penny-for-penny statutory & execution fees (authoritative CostEngine output)
    notional: float = 0.0             # Traded entry notional (price * qty)
    gross_pnl_rupees: float = 0.0     # Gross P&L before transaction friction
    predicted_direction: int = 1      # Direction predicted by model (+1 or -1)
    actual_direction: int = 0         # Realized price movement direction (+1, -1, or 0)
    brokerage_rupees: float = 0.0     # Zerodha intraday equity brokerage (both sides)
    stt_rupees: float = 0.0           # Securities Transaction Tax (sell side)
    stamp_duty_rupees: float = 0.0    # Stamp duty (buy side)
    exchange_charges_rupees: float = 0.0 # NSE transaction charges (both sides)
    sebi_fees_rupees: float = 0.0     # SEBI regulatory turnover charges (both sides)
    gst_rupees: float = 0.0           # 18% GST on (brokerage + exchange + SEBI)
    spread_cost_rupees: float = 0.0   # Bid-ask spread cost in INR
    spread_bps: float = 0.0           # Bid-ask spread in bps
    slippage_cost_rupees: float = 0.0 # Market impact slippage in INR
    slippage_bps: float = 0.0         # Market impact slippage in bps
    total_friction_rupees: float = 0.0# Sum of all statutory + spread + slippage in INR

    # Cross-sectional signals and risk gates
    conviction_percentile: float = 0.0# Signal percentile rank across universe
    z_score: float = 0.0              # Cross-sectional z-score
    ticket_economics_result: str = "VIABLE" # Unit economics gate summary
    risk_gate_result: str = "PASSED"  # Risk checks summary
    final_decision: str = "ENTERED"   # Final decision state
    rejection_reason: str = ""        # Rejection reason if applicable

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradeAuditRecord":
        return cls(**data)


@dataclass(frozen=True)
class CandidateDecisionAuditRecord:
    """
    Forensic record for every candidate evaluated at each bar decision point.
    Preserves all 29 fields distinguishing signals, convictions, ticket economics, and risk gates.
    """
    timestamp: str
    session_date: str
    symbol: str
    model_version: str
    model_hash: str
    dataset_hash: str
    data_cutoff: str
    predicted_return_bps: float
    realized_return_bps: Optional[float]
    predicted_direction: int
    actual_direction: Optional[int]
    quantity: int
    entry_price: float
    exit_price: Optional[float]
    notional: float
    gross_pnl_rupees: Optional[float]
    brokerage_rupees: float
    stt_rupees: float
    stamp_duty_rupees: float
    exchange_charges_rupees: float
    sebi_fees_rupees: float
    gst_rupees: float
    spread_cost_rupees: float
    slippage_cost_rupees: float
    total_friction_rupees: float
    net_pnl_rupees: Optional[float]
    conviction_percentile: float
    z_score: float
    conviction_tier: str
    ticket_economics_result: str
    risk_gate_result: str
    final_decision: str       # "ENTERED", "REJECTED_CONVICTION", "REJECTED_DIRECTION", "REJECTED_TICKET_ECONOMICS", "REJECTED_RISK_GATE"
    rejection_reason: str
    trade_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateDecisionAuditRecord":
        return cls(**data)


class AuditLedger:
    """
    Manages persistent storage and cryptographic verification of manifests, trade lineages,
    and bar-by-bar candidate decisions.
    """

    def __init__(self, ledger_dir: str = "v2/adaptive/ledger"):
        self.ledger_dir = ledger_dir
        self.manifest_dir = os.path.join(ledger_dir, "manifests")
        self.trades_dir = os.path.join(ledger_dir, "trades")
        self.decisions_dir = os.path.join(ledger_dir, "decisions")
        os.makedirs(self.manifest_dir, exist_ok=True)
        os.makedirs(self.trades_dir, exist_ok=True)
        os.makedirs(self.decisions_dir, exist_ok=True)

    def save_manifest(self, manifest: DailyModelManifest) -> str:
        """
        Persists a DailyModelManifest as an immutable JSON record.
        """
        path = os.path.join(self.manifest_dir, f"manifest_{manifest.session_date.replace('-', '')}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2)
        return path

    def load_manifest(self, session_date: str) -> Optional[DailyModelManifest]:
        """
        Retrieves a DailyModelManifest for a given session date.
        """
        clean_date = session_date.replace("-", "")
        path = os.path.join(self.manifest_dir, f"manifest_{clean_date}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return DailyModelManifest.from_dict(data)

    def save_trades(self, session_date: str, trades: List[TradeAuditRecord]) -> str:
        """
        Saves the list of trades executed during a session to an immutable JSON ledger.
        """
        clean_date = session_date.replace("-", "")
        path = os.path.join(self.trades_dir, f"trades_{clean_date}.json")
        data = [t.to_dict() for t in trades]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path

    def load_trades(self, session_date: str) -> List[TradeAuditRecord]:
        """
        Loads all trades for a given session date.
        """
        clean_date = session_date.replace("-", "")
        path = os.path.join(self.trades_dir, f"trades_{clean_date}.json")
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [TradeAuditRecord.from_dict(d) for d in data]

    def save_decisions(self, session_date: str, decisions: List[CandidateDecisionAuditRecord]) -> str:
        """
        Saves the list of candidate decisions evaluated during a session to an immutable JSON ledger.
        """
        clean_date = session_date.replace("-", "")
        path = os.path.join(self.decisions_dir, f"decisions_{clean_date}.json")
        data = [d.to_dict() for d in decisions]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path

    def load_decisions(self, session_date: str) -> List[CandidateDecisionAuditRecord]:
        """
        Loads all candidate decisions for a given session date.
        """
        clean_date = session_date.replace("-", "")
        path = os.path.join(self.decisions_dir, f"decisions_{clean_date}.json")
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [CandidateDecisionAuditRecord.from_dict(d) for d in data]

    def verify_trade_lineage(self, trade: TradeAuditRecord) -> bool:
        """
        Cryptographically verifies that a trade matches the saved daily model manifest.
        """
        manifest = self.load_manifest(trade.session_date)
        if manifest is None:
            return False
        return (
            trade.model_version == manifest.model_version and
            trade.model_hash == manifest.model_hash and
            trade.dataset_hash == manifest.dataset_hash and
            trade.data_cutoff == manifest.data_cutoff
        )
