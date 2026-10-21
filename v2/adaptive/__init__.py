"""
AlphaNSE V2 — Adaptive Daily Retraining & Trading Pipeline Package.
Enforces the daily 9-stage adaptive cycle:
  1. Data Acquisition (through D-1)
  2. Dataset Update & Deduplication
  3. Feature Engineering (Point-in-Time)
  4. Daily Model Retraining
  5. Pre-Market Model Validation & Sanity Gates
  6. Daily Model Freezing (SHA-256 audit manifest)
  7. Intraday Sequential Bar Processing
  8. Point-in-Time Prediction & Opportunity Ranking
  9. Risk Sizing, Execution & Trade Audit Lineage
"""

from .audit_ledger import DailyModelManifest, TradeAuditRecord, AuditLedger
from .dataset_updater import DatasetUpdater
from .model_updater import ModelUpdater, ModelSanityGateError
from .opportunity_ranker import OpportunityRanker, RankedOpportunity
from .session_trader import SessionTrader, ActivePosition
from .daily_pipeline import AdaptiveDailyPipeline, DailySessionResult

__all__ = [
    "DailyModelManifest",
    "TradeAuditRecord",
    "AuditLedger",
    "DatasetUpdater",
    "ModelUpdater",
    "ModelSanityGateError",
    "OpportunityRanker",
    "RankedOpportunity",
    "SessionTrader",
    "ActivePosition",
    "AdaptiveDailyPipeline",
    "DailySessionResult"
]
