"""
AlphaNSE V3 — Cryptographic Audit Ledger & Lineage Engine.
Tracks model manifests and forensic trade audit records for the 60m adaptive pipeline.
Maintains absolute segregation from V2 ledgers.

STATUS: EXPERIMENT / VALIDATION
Explicitly tracks whether an execution is:
- HISTORICAL_REPLAY (Sessions 1-4 baseline)
- FORWARD_VALIDATION (Session 5 onward)
"""

import os
import json
import hashlib
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import pandas as pd

from v3.config.v3_config import (
    EXPERIMENT_MODE,
    PROFITABILITY_CLAIM,
    REPLAY_DISCLAIMER,
    FORWARD_VALIDATION_LABEL,
    V3_LEDGER_DIR,
    V3_MANIFESTS_DIR,
    V3_TRADES_DIR
)


@dataclass(frozen=True)
class DailyModelManifestV3:
    """
    Cryptographic specification of the frozen 60m model deployed for Day D.
    """
    session_date: str                  # e.g. "2026-09-24"
    data_cutoff: str                   # e.g. "2026-09-23T15:25:00+05:30"
    dataset_hash: str                  # SHA-256 of training dataset (<= D-1)
    feature_version: str               # Version / hash of feature pipeline
    model_version: str                 # e.g. "AlphaNSE_V3_60m_20260924_v1"
    model_hash: str                    # SHA-256 of serialized model weights
    target_column: str                 # "target_return_60m"
    horizon_bars: int                  # 12 (60 minutes)
    training_window: str               # e.g. "2026-06-29 to 2026-09-23"
    training_rows: int                 # Number of training samples
    validation_result: Dict[str, Any]  # Pre-market sanity gate metrics
    regime_at_open: str                # "LOW_VOL", "NORMAL_VOL", or "HIGH_VOL"
    created_at: str                    # ISO timestamp
    experiment_mode: str = EXPERIMENT_MODE
    profitability_claim: bool = PROFITABILITY_CLAIM
    disclaimer: str = REPLAY_DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DailyModelManifestV3":
        return cls(**data)


@dataclass(frozen=True)
class TradeAuditRecordV3:
    """
    Forensic audit record for an executed trade under V3.
    Captures exact rupee net-edge calculations and itemized transaction friction.
    """
    trade_id: str
    session_date: str
    entry_time: str
    exit_time: str
    symbol: str
    direction: int                      # +1 for Long, -1 for Short
    entry_price: float
    exit_price: float
    quantity: int
    notional: float

    # Point-in-Time Prediction & Sizing Metrics (Rupee Net-Edge Formula)
    predicted_return_bps: float         # Raw model predicted return (no ATR inflation)
    expected_gross_rupees: float        # Predicted gross rupee return = notional * (predicted_bps / 10000)
    expected_total_cost_rupees: float   # Modeled total transaction friction in ₹
    expected_net_rupees: float          # Expected net rupee return
    expected_cost_bps: float            # Expected friction in bps

    # Realized Trade Performance
    gross_return_bps: float
    cost_bps: float
    net_return_bps: float
    gross_pnl_rupees: float
    net_pnl_rupees: float

    # Itemized Penny-for-Penny Costs (Statutory + Execution)
    brokerage_rupees: float
    stt_rupees: float
    exchange_charges_rupees: float
    sebi_charges_rupees: float
    stamp_duty_rupees: float
    gst_rupees: float
    statutory_total_rupees: float
    spread_rupees: float
    slippage_rupees: float

    # Execution Metadata
    exit_reason: str                    # "HORIZON_REACHED", "STOP_LOSS", "EOD_CLOSE"
    horizon_bars: int = 12
    holding_duration_mins: float = 60.0
    model_version: str = ""
    model_hash: str = ""
    dataset_hash: str = ""
    data_cutoff: str = ""
    execution_type: str = "HISTORICAL_REPLAY"  # "HISTORICAL_REPLAY" or "FORWARD_VALIDATION"
    disclaimer: str = REPLAY_DISCLAIMER
    supporting_models: str = "[]"
    contradicting_models: str = "[]"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradeAuditRecordV3":
        return cls(**data)


@dataclass(frozen=True)
class CandidateDecisionAuditRecordV3:
    """
    Complete audit record for every evaluated candidate instrument at every bar.
    Captures all 5 model predictions, ensemble aggregation, itemized costs,
    and the final economic decision (TRADE vs HOLD_CASH).
    """
    timestamp: str
    symbol: str

    # 5 Models Individual Outputs
    V2_15M_prediction: float
    V2_15M_confidence: float

    HYPO001_prediction: float
    HYPO001_confidence: float

    HYPO002_prediction: float
    HYPO002_confidence: float

    HYPO003_prediction: float
    HYPO003_confidence: float

    V3_60M_prediction: float
    V3_60M_confidence: float

    # Model Agreement & Consensus
    model_agreement_count: int
    valid_model_count: int
    agreement_ratio: str
    supporting_models: List[str]
    contradicting_models: List[str]

    # Consolidated Ensemble Metrics
    ensemble_direction: int
    ensemble_confidence: float
    selected_horizon: int
    ensemble_expected_gross_bps: float
    ensemble_expected_net_bps: float
    ensemble_expected_net_rupees: float

    # Capital & Sizing
    price: float
    affordable_quantity: int
    capital_required: float

    # Itemized Costs
    estimated_brokerage: float
    estimated_statutory_cost: float
    estimated_spread: float
    estimated_slippage: float
    estimated_impact: float
    total_cost: float

    # Final Outcome
    final_decision: str                 # "TRADE" or "HOLD_CASH"
    decision_reason: str

    # Cryptographic Provenance
    model_hashes: Dict[str, str]
    dataset_hash: str
    feature_schema_hash: str
    training_cutoff: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateDecisionAuditRecordV3":
        return cls(**data)


class AuditLedgerV3:
    """
    Manages cryptographic storage and verification of V3 manifests and trade ledgers.
    Maintains clean directory isolation from V2.
    """

    def __init__(self, ledger_dir: str = V3_LEDGER_DIR):
        self.ledger_dir = ledger_dir
        self.manifests_dir = os.path.join(ledger_dir, "manifests")
        self.trades_dir = os.path.join(ledger_dir, "trades")
        self.candidate_audits_dir = os.path.join(ledger_dir, "candidate_audits")
        os.makedirs(self.manifests_dir, exist_ok=True)
        os.makedirs(self.trades_dir, exist_ok=True)
        os.makedirs(self.candidate_audits_dir, exist_ok=True)

    def save_manifest(self, manifest: DailyModelManifestV3) -> str:
        date_str = manifest.session_date.replace("-", "")
        path = os.path.join(self.manifests_dir, f"manifest_{date_str}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2)
        return path

    def load_manifest(self, session_date: str) -> Optional[DailyModelManifestV3]:
        date_clean = session_date.replace("-", "")
        path = os.path.join(self.manifests_dir, f"manifest_{date_clean}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return DailyModelManifestV3.from_dict(data)

    def save_trades(self, session_date: str, trades: List[TradeAuditRecordV3]) -> str:
        date_clean = session_date.replace("-", "")
        json_path = os.path.join(self.trades_dir, f"trades_{date_clean}.json")
        parquet_path = os.path.join(self.trades_dir, f"trades_{date_clean}.parquet")

        trade_dicts = [t.to_dict() for t in trades]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(trade_dicts, f, indent=2)

        if trade_dicts:
            df = pd.DataFrame(trade_dicts)
            df.to_parquet(parquet_path, index=False)
        else:
            # Empty trades ledger for cash-holding sessions
            df = pd.DataFrame(columns=[
                "trade_id", "session_date", "entry_time", "exit_time", "symbol",
                "direction", "entry_price", "exit_price", "quantity", "notional",
                "predicted_return_bps", "expected_gross_rupees", "expected_total_cost_rupees",
                "expected_net_rupees", "expected_cost_bps", "gross_return_bps", "cost_bps",
                "net_return_bps", "gross_pnl_rupees", "net_pnl_rupees", "brokerage_rupees",
                "stt_rupees", "exchange_charges_rupees", "sebi_charges_rupees",
                "stamp_duty_rupees", "gst_rupees", "statutory_total_rupees", "spread_rupees",
                "slippage_rupees", "exit_reason", "horizon_bars", "holding_duration_mins",
                "model_version", "model_hash", "dataset_hash", "data_cutoff",
                "execution_type", "disclaimer"
            ])
            df.to_parquet(parquet_path, index=False)

        return json_path

    def load_trades(self, session_date: str) -> List[TradeAuditRecordV3]:
        date_clean = session_date.replace("-", "")
        json_path = os.path.join(self.trades_dir, f"trades_{date_clean}.json")
        if not os.path.exists(json_path):
            return []
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [TradeAuditRecordV3.from_dict(d) for d in data]

    def save_candidate_audits(self, session_date: str, audits: List[CandidateDecisionAuditRecordV3]) -> str:
        date_clean = session_date.replace("-", "")
        json_path = os.path.join(self.candidate_audits_dir, f"candidate_audits_{date_clean}.json")
        parquet_path = os.path.join(self.candidate_audits_dir, f"candidate_audits_{date_clean}.parquet")

        audit_dicts = [a.to_dict() for a in audits]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(audit_dicts, f, indent=2)

        if audit_dicts:
            df = pd.DataFrame(audit_dicts)
            # Store model_hashes as string for parquet compatibility
            df["model_hashes"] = df["model_hashes"].apply(json.dumps)
            df["supporting_models"] = df["supporting_models"].apply(json.dumps)
            df["contradicting_models"] = df["contradicting_models"].apply(json.dumps)
            df.to_parquet(parquet_path, index=False)

        return json_path

    def load_candidate_audits(self, session_date: str) -> List[CandidateDecisionAuditRecordV3]:
        date_clean = session_date.replace("-", "")
        json_path = os.path.join(self.candidate_audits_dir, f"candidate_audits_{date_clean}.json")
        if not os.path.exists(json_path):
            return []
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [CandidateDecisionAuditRecordV3.from_dict(d) for d in data]

    def verify_provenance(self, session_date: str) -> Dict[str, Any]:
        manifest = self.load_manifest(session_date)
        trades = self.load_trades(session_date)

        if manifest is None:
            return {"status": "FAILED", "reason": "Manifest not found"}

        for trade in trades:
            if trade.model_hash != manifest.model_hash:
                return {
                    "status": "FAILED",
                    "reason": f"Model hash mismatch in trade {trade.trade_id}"
                }
            if trade.dataset_hash != manifest.dataset_hash:
                return {
                    "status": "FAILED",
                    "reason": f"Dataset hash mismatch in trade {trade.trade_id}"
                }

        return {
            "status": "VERIFIED",
            "session_date": session_date,
            "trade_count": len(trades),
            "model_version": manifest.model_version,
            "model_hash": manifest.model_hash,
            "dataset_hash": manifest.dataset_hash
        }
