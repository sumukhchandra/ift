"""
AlphaNSE V3 — Multi-Model Session 5 Configuration.
Defines specifications for the 5 active research models participating in Session 5:
  MODEL_01: V2_15M   (15m baseline return regressor)
  MODEL_02: HYPO001  (30m midday trend follower)
  MODEL_03: HYPO002  (60m high-beta momentum)
  MODEL_04: HYPO003  (15m short-sparsity opportunistic)
  MODEL_05: V3_60M   (60m adaptive cost-aware regressor)

STATUS: EXPERIMENT / VALIDATION
EXECUTION: PAPER/SHADOW ONLY (Live execution physically disabled)
"""

from typing import Dict, Any, List
from dataclasses import dataclass


# Active Session Dates
SESSION_5_DATE: str = "2026-09-25"
D_MINUS_ONE_CUTOFF: str = "2026-09-24T15:25:00+05:30"

SESSION_6_DATE: str = "2026-09-28"
SESSION_6_D_MINUS_ONE_CUTOFF: str = "2026-09-25T15:25:00+05:30"

SESSION_7_DATE: str = "2026-09-29"
SESSION_7_D_MINUS_ONE_CUTOFF: str = "2026-09-28T15:25:00+05:30"

SESSION_8_DATE: str = "2026-09-30"
SESSION_8_D_MINUS_ONE_CUTOFF: str = "2026-09-29T15:25:00+05:30"

SESSION_9_DATE: str = "2026-10-01"
SESSION_9_D_MINUS_ONE_CUTOFF: str = "2026-09-30T15:25:00+05:30"

# Model Registry Specifications
ACTIVE_MODEL_SPECS: Dict[str, Dict[str, Any]] = {
    "V2_15M": {
        "model_id": "V2_15M",
        "name": "V2 15m Baseline Model",
        "target_definition": "target_return_15m",
        "target_horizon_minutes": 15,
        "horizon_bars": 3,
        "alpha": 20.0,
        "direction": "LONG_AND_SHORT",
        "description": "Baseline Ridge return regressor targeting 15m forward return",
        "min_signal_floor_bps": 4.0
    },
    "HYPO001": {
        "model_id": "HYPO001",
        "name": "HYPO001 30m Midday Trend",
        "target_definition": "target_return_30m",
        "target_horizon_minutes": 30,
        "horizon_bars": 6,
        "alpha": 15.0,
        "direction": "LONG_AND_SHORT",
        "description": "Midday trend following regressor targeting 30m forward return",
        "min_signal_floor_bps": 5.0
    },
    "HYPO002": {
        "model_id": "HYPO002",
        "name": "HYPO002 60m High Beta",
        "target_definition": "target_return_60m",
        "target_horizon_minutes": 60,
        "horizon_bars": 12,
        "alpha": 25.0,
        "direction": "LONG_AND_SHORT",
        "description": "Extended horizon high-beta momentum regressor targeting 60m forward return",
        "min_signal_floor_bps": 6.0
    },
    "HYPO003": {
        "model_id": "HYPO003",
        "name": "HYPO003 15m Short Sparsity",
        "target_definition": "target_return_15m",
        "target_horizon_minutes": 15,
        "horizon_bars": 3,
        "alpha": 20.0,
        "direction": "SHORT_SPARSITY",
        "description": "Opportunistic downside exhaustion regressor targeting 15m short return",
        "min_signal_floor_bps": 5.0
    },
    "V3_60M": {
        "model_id": "V3_60M",
        "name": "V3 60m Adaptive Model",
        "target_definition": "target_return_60m",
        "target_horizon_minutes": 60,
        "horizon_bars": 12,
        "alpha": 20.0,
        "direction": "LONG_AND_SHORT",
        "description": "Adaptive cost-aware Ridge return regressor targeting 60m forward return",
        "min_signal_floor_bps": 6.0
    },
    "SMC_4CONF_920": {
        "model_id": "SMC_4CONF_920",
        "name": "SMC 4-Confirmation + 9:20 Straddle Combined",
        "target_definition": "target_smc_directional_and_straddle",
        "target_horizon_minutes": 5,
        "horizon_bars": 1,
        "alpha": 0.0,
        "direction": "LONG_AND_SHORT",
        "description": "SMC 4-Confirmation (C1-C4, F1-F2) directional & 9:20 AM Short Straddle theta decay",
        "min_signal_floor_bps": 5.0,
        "model_type": "SMC_STRADDLE"
    }
}

# Storage paths for multi-model architecture
V3_MULTIMODEL_DIR: str = "v3/models/multimodel"
V3_MULTIMODEL_REGISTRY_PATH: str = "v3/models/multimodel/model_registry.json"
V3_DECISION_AUDIT_DIR: str = "v3/adaptive/ledger/candidate_audits"
