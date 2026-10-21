"""
AlphaNSE V3 — Centralized Configuration.
Research Pipeline: Daily-Adaptive 60-Minute Horizon with Rupee Net-Edge Allocation.

STATUS: EXPERIMENT / VALIDATION
DISCLAIMER:
  The 60m horizon is an experimental hypothesis undergoing forward validation.
  Historical 60m results (25 trades across 2 sessions, negative IC) are unproven
  and do NOT constitute evidence of future profitability.
  Sessions 1-4 replay is strictly HISTORICAL REPLAY / BASELINE, not fresh validation.
  Session 5 onward constitutes actual fresh forward validation.
"""

from typing import List, Tuple
from dataclasses import dataclass


# =============================================================================
# EXPERIMENT & AUDIT CLASSIFICATION
# =============================================================================
EXPERIMENT_MODE: str = "EXPERIMENT_VALIDATION"
EXPERIMENT_STATUS: str = "HYPOTHESIS_FORWARD_VALIDATION"
PROFITABILITY_CLAIM: bool = False

REPLAY_DISCLAIMER: str = (
    "HISTORICAL REPLAY / BASELINE — "
    "NOT FRESH VALIDATION — "
    "NOT LIVE PERFORMANCE — "
    "NOT PROFITABILITY PROOF"
)

FORWARD_VALIDATION_LABEL: str = "FRESH FORWARD VALIDATION (SESSION 5 ONWARD)"


# =============================================================================
# MODEL & HORIZON SPECIFICATIONS
# =============================================================================
HORIZON_BARS: int = 12                     # 12 bars * 5m = 60 minutes holding horizon
HORIZON_NAME: str = "60m"
TARGET_RETURN_COLUMN: str = "target_return_60m"
ALPHA_RIDGE: float = 20.0
COST_HURDLE_BPS: float = 15.0


# =============================================================================
# TIME BOUNDARIES & SESSION WINDOWS (IST)
# =============================================================================
MARKET_OPEN_TIME: str = "09:15"
MORNING_ENTRY_END: str = "12:00"

# Lunch Blackout: 12:00 to 14:00 IST (Strictly NO NEW ENTRIES)
LUNCH_BLACKOUT_START: str = "12:00"
LUNCH_BLACKOUT_END: str = "14:00"

# Afternoon Entry Window
AFTERNOON_ENTRY_START: str = "14:00"
# Entry Cutoff: 14:25 IST ensures a 12-bar (60m) trade completes before 15:25 close
ENTRY_CUTOFF_TIME: str = "14:25"

# Intraday Square-off (Strict No-Overnight Invariant)
EOD_CLOSE_TIME: str = "15:25"


# =============================================================================
# CAPITAL & SIZING CONSTRAINTS
# =============================================================================
INITIAL_CAPITAL: float = 5000.0             # Micro-capital account constraint (₹5,000)
MAX_CAPITAL_PCT_PER_TRADE: float = 0.95     # Allocate up to 95% of available capital
HARD_MAX_POSITION_COUNT: int = 5            # Configurable safety ceiling for portfolio basket sizing
MAX_ACTIVE_POSITIONS: int = 5               # Dynamic upper bound determined by portfolio optimization
MIN_CASH_BUFFER_RUPEES: float = 50.0        # Mandatory minimum liquidity reserve


# =============================================================================
# RUPEE NET-EDGE & OPPORTUNITY GATING
# =============================================================================
# Sizing & Edge Rule:
# Predicted gross return (%)
#        ↓
# actual affordable whole shares
#        ↓
# expected gross ₹
#        ↓
# statutory costs + spread + slippage + impact = all-in costs ₹
#        ↓
# expected net ₹ = expected gross ₹ - all-in costs ₹
#        ↓
# minimum required edge ₹
#        ↓
# TRADE / HOLD CASH

# =============================================================================
# PREDICTION MAGNITUDE CALIBRATION
# =============================================================================
# !! CHRONOLOGY LOCK !!
# The 0.50 factor below was initially derived from Session-5 (2026-09-25)
# realized/predicted ratios and MUST NOT be used to calibrate Session-5
# predictions — that would be look-ahead contamination.
#
# CORRECT PROTOCOL (OOS walk-forward):
#   1. Calibration factor for session D is computed ONLY from sessions < D.
#   2. Factor is frozen before 09:15 on session D.
#   3. Session D outcome is recorded AFTER close.
#   4. That outcome becomes eligible only for session D+1 calibration.
#
# This constant is now set to 1.0 (identity / passthrough) pending the
# proper OOS walk-forward implemented in:
#   v3/calibration/oos_calibration_engine.py
#
# For Session 6 forward, the engine reads the frozen calibration dataset
# (v3/calibration/CALIBRATION_HISTORY.json) built from sessions 1-5 and
# computes the factor before market open — it is never set by hand here.
#
# DO NOT manually set this to any session's realized ratio.
PREDICTION_SHRINKAGE_FACTOR: float = 1.0   # DISABLED — OOS engine governs; see oos_calibration_engine.py

MIN_NET_EDGE_RUPEES: float = 0.80           # Minimum required net edge in ₹ per trade (authoritative gate)
MIN_NET_EDGE_BPS: float = 0.0               # Expected net return must be strictly positive (> 0 bps)
MIN_PREDICTED_RETURN_BPS: float = 6.0       # Model prediction must exceed minimal signal floor
MIN_BAR_VOLUME: float = 5000.0              # Minimum volume on entry bar
MAX_SPREAD_BPS: float = 12.0                # Reject symbols with wide spread
ALLOW_CASH_HOLDING: bool = True             # Holding cash is an intentional, first-class decision

# Stop loss sizing
STOP_LOSS_ATR_MULT: float = 2.0             # Stop loss distance in ATR multiples

# Dynamic Intraday Capital Rotation
ROTATION_MIN_ADVANTAGE_BPS: float = 8.0     # Minimum net advantage in bps over current position to trigger rotation
ROTATION_PENALTY_RUPEES: float = 0.50       # Explicit friction penalty on rotation switching


# =============================================================================
# STORAGE & LEDGER PATHS
# =============================================================================
V3_ROOT_DIR: str = "v3"
V3_MODELS_DIR: str = "v3/models/adaptive_models"
V3_LEDGER_DIR: str = "v3/adaptive/ledger"
V3_MANIFESTS_DIR: str = "v3/adaptive/ledger/manifests"
V3_TRADES_DIR: str = "v3/adaptive/ledger/trades"
V3_REPORTS_DIR: str = "v3/reports"

# Shared historical storage (read-only)
BASE_RAW_PATH: str = "v2/data/storage/normalized/historical_5m_raw.parquet"
BASE_ADJ_PATH: str = "v2/data/storage/adjusted/historical_5m_adjusted.parquet"
FRESH_DIR: str = "v2/data/storage/fresh"
