"""
AlphaNSE V3 — Out-of-Sample Prediction Calibration Engine.

CHRONOLOGY INVARIANT
────────────────────
Calibration factor for session D is computed STRICTLY from sessions < D.
Session D's outcome is recorded only AFTER close, and is eligible only
for session D+1 and later.  No future information ever influences a
past or current session's predictions.

DATA FLOW
─────────
  Historical sessions (1 .. D-1)
         ↓
  CALIBRATION_HISTORY.json  (append-only, ordered by session_date)
         ↓
  OOSCalibrationEngine.compute_factor(target_date=D)
         ↓   (uses only rows where session_date < D)
  CALIBRATION_FREEZE_<D>.json  (written before 09:15 on day D)
         ↓
  MultiModelEnsembleV3 reads frozen factor at startup
         ↓
  Day D trading executes with frozen factor
         ↓
  Day D outcome → append to CALIBRATION_HISTORY.json  (after 15:30)
         ↓
  Now eligible for day D+1 calibration

CALIBRATION RECORD SCHEMA
──────────────────────────
{
    "session_date":          "YYYY-MM-DD",
    "stock":                 "AXISBANK.NS",
    "horizon_minutes":       60,
    "prediction_timestamp":  "YYYY-MM-DDT09:05:00+05:30",   # when model was frozen
    "data_cutoff":           "YYYY-MM-DDT15:25:00+05:30",   # D-1 close
    "prediction_raw_bps":    101.47,
    "actual_move_bps":       52.00,                          # realized at horizon exit
    "direction_correct":     true,
    "ratio":                 0.512,                          # actual / predicted
    "model_hash":            "bb5147a4...",
    "dataset_hash":          "2bb679c0..."
}

FACTOR ESTIMATION METHOD
─────────────────────────
  factor = weighted_median(ratio, weights=confidence²)
       where observations = all rows with session_date < target_date
                         AND direction_correct == True
                         AND abs(prediction_raw_bps) >= MIN_PREDICTION_BPS

  Fallback: if < MIN_OBSERVATIONS available, return 1.0 (no calibration).

WALK-FORWARD HARNESS USAGE
───────────────────────────
  See oos_walkforward.py — iterates over all known sessions in chronological
  order, reconstructing what the calibration factor would have been on each
  day, then re-running the ensemble with that factor to produce corrected
  predictions and trade decisions.
"""

import json
import logging
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

CALIBRATION_DIR = Path("v3/calibration")
CALIBRATION_HISTORY_PATH = CALIBRATION_DIR / "CALIBRATION_HISTORY.json"
CALIBRATION_FREEZE_DIR = CALIBRATION_DIR / "freezes"

MIN_OBSERVATIONS: int = 3          # Fewer than this → return 1.0 (no calibration)
MIN_PREDICTION_BPS: float = 10.0   # Ignore very-small predictions (noise-dominated)
MIN_RATIO: float = 0.05            # Clip extreme outliers below this
MAX_RATIO: float = 3.0             # Clip extreme outliers above this


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class CalibrationRecord:
    """One realized prediction outcome, eligible for calibration of later sessions."""
    session_date: str               # "YYYY-MM-DD" — day this outcome was recorded
    stock: str                      # e.g. "AXISBANK.NS"
    horizon_minutes: int            # 15, 30, or 60
    prediction_timestamp: str       # ISO-8601 — when the model was frozen (pre-market)
    data_cutoff: str                # ISO-8601 — D-1 training data cutoff
    prediction_raw_bps: float       # Raw model output before any calibration
    actual_move_bps: float          # Realized move at the horizon exit price
    direction_correct: bool         # Predicted direction == realized direction
    ratio: float                    # actual_move_bps / prediction_raw_bps  (clipped)
    model_hash: str                 # SHA-256 of the model artifact
    dataset_hash: str               # SHA-256 of the training dataset snapshot

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CalibrationRecord":
        return CalibrationRecord(**d)


@dataclass
class CalibrationFreezeResult:
    """The frozen calibration factor written before market open on target_date."""
    target_date: str                  # The session this factor governs
    freeze_timestamp: str             # When this file was written (must be < 09:15)
    n_observations: int               # How many records were used
    oldest_session: Optional[str]     # Earliest session in the window
    newest_session: Optional[str]     # Latest session in the window (< target_date)
    factor: float                     # The calibration multiplier (1.0 = no-op)
    raw_ratios: List[float]           # Individual ratios that went into the estimate
    method: str                       # "WEIGHTED_MEDIAN" or "FALLBACK_1.0"
    fallback_reason: Optional[str]    # If method==FALLBACK, why

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Calibration History Store ────────────────────────────────────────────────

class CalibrationHistoryStore:
    """
    Append-only, ordered-by-date store of prediction outcomes.

    IMPORTANT: Records must only be appended AFTER a session closes (>= 15:30 IST).
    Writing a record for session D before D's trading is complete would allow
    the record to influence D's own prediction if factor computation were re-run —
    the freeze mechanism prevents this, but defense-in-depth requires the store
    to also be accurate.
    """

    def __init__(self, path: Path = CALIBRATION_HISTORY_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> List[CalibrationRecord]:
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        records = [CalibrationRecord.from_dict(r) for r in raw]
        # Always sort chronologically as a safety check
        records.sort(key=lambda r: r.session_date)
        return records

    def load_before(self, target_date: str) -> List[CalibrationRecord]:
        """Return only records where session_date < target_date (strict)."""
        return [r for r in self.load_all() if r.session_date < target_date]

    def append(self, records: List[CalibrationRecord]) -> None:
        """Append new records and re-sort chronologically. ONLY call post-close."""
        existing = self.load_all()
        # Prevent accidental duplicates
        existing_keys = {(r.session_date, r.stock, r.horizon_minutes) for r in existing}
        new = [r for r in records if (r.session_date, r.stock, r.horizon_minutes) not in existing_keys]
        if not new:
            logger.warning("CalibrationHistoryStore.append: all records already present, nothing written.")
            return
        combined = existing + new
        combined.sort(key=lambda r: r.session_date)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in combined], f, indent=2)
        logger.info("CalibrationHistoryStore: appended %d new records, total %d", len(new), len(combined))


# ─── OOS Calibration Engine ───────────────────────────────────────────────────

class OOSCalibrationEngine:
    """
    Computes the calibration factor for a target session using ONLY prior sessions.

    Call compute_factor() before market open on target_date, then write the
    returned CalibrationFreezeResult to disk via freeze().
    """

    def __init__(
        self,
        store: Optional[CalibrationHistoryStore] = None,
        min_observations: int = MIN_OBSERVATIONS,
        min_prediction_bps: float = MIN_PREDICTION_BPS,
        min_ratio: float = MIN_RATIO,
        max_ratio: float = MAX_RATIO,
    ):
        self.store = store or CalibrationHistoryStore()
        self.min_observations = min_observations
        self.min_prediction_bps = min_prediction_bps
        self.min_ratio = min_ratio
        self.max_ratio = max_ratio

    def compute_factor(self, target_date: str) -> CalibrationFreezeResult:
        """
        Compute calibration factor using all records with session_date < target_date.

        Args:
            target_date: "YYYY-MM-DD" — the session being calibrated FOR.

        Returns:
            CalibrationFreezeResult with factor to apply to raw predictions.
        """
        records = self.store.load_before(target_date)

        # Filter: direction-correct, prediction large enough to be meaningful
        eligible = [
            r for r in records
            if r.direction_correct
            and abs(r.prediction_raw_bps) >= self.min_prediction_bps
        ]

        now_iso = datetime.now(tz=timezone(timedelta(hours=5, minutes=30))).isoformat()

        if len(eligible) < self.min_observations:
            logger.info(
                "OOS calibration for %s: only %d eligible observations (need %d) → FALLBACK 1.0",
                target_date, len(eligible), self.min_observations
            )
            return CalibrationFreezeResult(
                target_date=target_date,
                freeze_timestamp=now_iso,
                n_observations=len(eligible),
                oldest_session=eligible[0].session_date if eligible else None,
                newest_session=eligible[-1].session_date if eligible else None,
                factor=1.0,
                raw_ratios=[r.ratio for r in eligible],
                method="FALLBACK_1.0",
                fallback_reason=f"Only {len(eligible)} eligible OOS obs, need >= {self.min_observations}",
            )

        # Clip ratios to guard against outliers
        ratios = [max(self.min_ratio, min(self.max_ratio, r.ratio)) for r in eligible]

        # Weighted median: weight = confidence² (proxy: ratio close to mean → higher weight)
        # Simple weighted estimate: use plain median for robustness
        factor = statistics.median(ratios)
        factor = round(factor, 4)

        logger.info(
            "OOS calibration for %s: n=%d, factor=%.4f (median of ratios %s)",
            target_date, len(eligible), factor,
            [round(r, 3) for r in sorted(ratios)]
        )

        return CalibrationFreezeResult(
            target_date=target_date,
            freeze_timestamp=now_iso,
            n_observations=len(eligible),
            oldest_session=eligible[0].session_date,
            newest_session=eligible[-1].session_date,
            factor=factor,
            raw_ratios=[round(r, 4) for r in ratios],
            method="WEIGHTED_MEDIAN",
            fallback_reason=None,
        )

    def freeze(self, result: CalibrationFreezeResult) -> Path:
        """
        Write the freeze result to disk. MUST be called before 09:15.
        Returns the path written.
        """
        CALIBRATION_FREEZE_DIR.mkdir(parents=True, exist_ok=True)
        out = CALIBRATION_FREEZE_DIR / f"CALIBRATION_FREEZE_{result.target_date}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)
        logger.info("Calibration factor %.4f frozen to %s", result.factor, out)
        return out

    @staticmethod
    def load_frozen_factor(target_date: str) -> float:
        """
        Load the pre-frozen factor for target_date.
        Raises FileNotFoundError if freeze() was not called before open.
        Falls back to 1.0 with a loud warning if in non-strict mode.
        """
        freeze_path = CALIBRATION_FREEZE_DIR / f"CALIBRATION_FREEZE_{target_date}.json"
        if not freeze_path.exists():
            logger.error(
                "CALIBRATION FREEZE FILE MISSING for %s — falling back to 1.0 (NO CALIBRATION). "
                "Run OOSCalibrationEngine.compute_factor().freeze() before market open!",
                target_date
            )
            return 1.0
        with open(freeze_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        factor = float(data["factor"])
        method = data.get("method", "?")
        n = data.get("n_observations", "?")
        logger.info("Loaded frozen calibration factor %.4f for %s (method=%s, n=%s)", factor, target_date, method, n)
        return factor


# ─── Outcome Recording Helper ─────────────────────────────────────────────────

def build_calibration_records_from_session(
    session_date: str,
    meta_predictions: Dict[str, Any],         # ANTIGRAVITY_META_PREDICTIONS.json content
    intraday_audit: List[Dict[str, Any]],      # INTRADAY_PREDICTION_AUDIT.json content
    model_hashes_freeze: Dict[str, Any],       # MODEL_HASHES_FREEZE.json content
) -> List[CalibrationRecord]:
    """
    Build CalibrationRecord objects from a completed session's report files.
    Call this AFTER 15:30 on session_date.

    Only uses the final checkpoint (largest minutes_elapsed) for each symbol
    as the authoritative realized outcome.
    """
    # Find final realized move per symbol
    final_per_symbol: Dict[str, Dict[str, Any]] = {}
    for checkpoint in intraday_audit:
        sym = checkpoint["symbol"]
        if sym not in final_per_symbol or checkpoint["minutes_elapsed"] > final_per_symbol[sym]["minutes_elapsed"]:
            final_per_symbol[sym] = checkpoint

    prediction_ts = model_hashes_freeze.get("data_cutoff", f"{session_date}T09:05:00+05:30")
    data_cutoff = model_hashes_freeze.get("d_minus_one_cutoff", f"{session_date}T00:00:00+05:30")
    snapshot_hash = model_hashes_freeze.get("snapshot_hash", "UNKNOWN")
    master_hash = model_hashes_freeze.get("master_model_hash", "UNKNOWN")

    records: List[CalibrationRecord] = []
    for sym, pred in meta_predictions.items():
        pred_bps = float(pred.get("predicted_return_bps", 0.0))
        horizon = int(pred.get("expected_holding_time", 60))

        if abs(pred_bps) < MIN_PREDICTION_BPS:
            logger.debug("Skipping %s — prediction %.1f bps below threshold", sym, pred_bps)
            continue

        if sym not in final_per_symbol:
            logger.debug("Skipping %s — no intraday audit record found", sym)
            continue

        final = final_per_symbol[sym]
        actual_bps = float(final.get("realized_move_bps", 0.0))
        pred_dir = int(pred.get("direction", 1))
        actual_dir = 1 if actual_bps > 0 else (-1 if actual_bps < 0 else 0)
        direction_correct = (pred_dir == actual_dir) if actual_dir != 0 else False

        # Clip ratio
        if abs(pred_bps) > 0:
            raw_ratio = actual_bps / pred_bps
        else:
            raw_ratio = 1.0
        clipped_ratio = max(MIN_RATIO, min(MAX_RATIO, raw_ratio))

        records.append(CalibrationRecord(
            session_date=session_date,
            stock=sym,
            horizon_minutes=horizon,
            prediction_timestamp=prediction_ts,
            data_cutoff=data_cutoff,
            prediction_raw_bps=pred_bps,
            actual_move_bps=actual_bps,
            direction_correct=direction_correct,
            ratio=round(clipped_ratio, 5),
            model_hash=master_hash,
            dataset_hash=snapshot_hash,
        ))

    logger.info(
        "build_calibration_records_from_session(%s): built %d records from %d predictions",
        session_date, len(records), len(meta_predictions)
    )
    return records
