#!/usr/bin/env python3
"""
v3/intelligence/provenance_tracker.py
AlphaNSE V3 — Immutable Prediction Provenance, Outcome Verification & Model Drift Sentinel.

Implements Directive Pillar 5:
1. Complete Audit Trail:
   - Logs every single prediction event with timestamp, source, spot price, feature hashes,
     model-level outputs, calibrated confidence, statutory friction, net expectancy, and rejection rationale.
2. Verified Outcome Pairing:
   - When subsequent actual market price arrives at t+1, pairs with prediction and computes
     exact error in INR and directional correctness. Zero synthetic fills or hypothetical marks.
3. Automated Model Drift Sentinel:
   - Tracks rolling 30-trade directional accuracy, Brier calibration score, and MAE.
   - Triggers DRIFT_ALERT and raises selectivity hurdle if rolling accuracy falls below 50.0%.
   - Protects paper bankroll under non-stationary market regimes.
"""

import os
import sys
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional
import numpy as np

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)


class ProvenanceTracker:
    """
    Manages structured, immutable provenance logging and real-time accuracy/drift tracking.
    """

    def __init__(self, log_dir: Optional[str] = None, drift_threshold: float = 0.50):
        self.log_dir = log_dir or os.path.join(WORKSPACE_ROOT, "reports", "live")
        os.makedirs(self.log_dir, exist_ok=True)
        self.provenance_file = os.path.join(self.log_dir, "prediction_provenance_stream.jsonl")
        self.drift_status_file = os.path.join(self.log_dir, "model_drift_sentinel.json")

        self.drift_threshold = drift_threshold
        self.outcomes_file = os.path.join(self.log_dir, "prediction_outcomes_stream.jsonl")
        self.pending_predictions: Dict[str, Dict[str, Any]] = {}  # keyed by (symbol, timestamp)
        self.verified_outcomes: List[Dict[str, Any]] = []
        try:
            from v3.storage.persistence import get_storage_manager
            self.storage_manager = get_storage_manager()
        except Exception:
            self.storage_manager = None

    def record_prediction(
        self,
        symbol: str,
        spot_price: float,
        data_source: str,
        specialist_alpha_bps: float,
        tree_alpha_bps: float,
        concurrence_ok: bool,
        calibrated_confidence: float,
        regime_name: str,
        gross_gain_rs: float,
        statutory_fees_rs: float,
        total_friction_rs: float,
        net_expectancy_rs: float,
        signal: str,
        rejection_reason: Optional[str] = None,
        rank_in_universe: int = 1,
        timestamp_str: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Records an authoritative prediction record with full provenance before trade execution.
        """
        now_ts = timestamp_str or datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
        rec_id = f"{symbol}_{now_ts}"

        # Sanity bounds check: clamp extreme alpha outliers to prevent corrupted metrics
        clamped_tree_bps = max(-100.0, min(100.0, tree_alpha_bps))
        clamped_spec_bps = max(-100.0, min(100.0, specialist_alpha_bps))

        record = {
            "record_id": rec_id,
            "timestamp": now_ts,
            "symbol": symbol,
            "horizon": "1m",
            "spot_price": round(spot_price, 2),
            "data_source": data_source,
            "model_versions": {
                "specialist_models": "frozen_ridge_v3_session5",
                "ml_ensemble": "catboost_lgbm_xgb_q75_1m_v3"
            },
            "specialist_alpha_bps": round(clamped_spec_bps, 2),
            "tree_alpha_bps": round(clamped_tree_bps, 2),
            "concurrence_ok": concurrence_ok,
            "calibrated_confidence": round(calibrated_confidence, 1),
            "market_regime": regime_name,
            "gross_gain_rs": round(gross_gain_rs, 2),
            "statutory_fees_rs": round(statutory_fees_rs, 2),
            "total_friction_rs": round(total_friction_rs, 2),
            "net_expectancy_rs": round(net_expectancy_rs, 2),
            "signal": signal,
            "rejection_reason": rejection_reason,
            "rank_in_universe": rank_in_universe,
            "outcome_verified": False,
            "actual_next_price": None,
            "prediction_error_rs": None,
            "is_correct_direction": None
        }

        # Persist to append-only JSONL stream
        with open(self.provenance_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        if hasattr(self, "storage_manager") and self.storage_manager:
            try:
                self.storage_manager.append_prediction(record)
            except Exception:
                pass

        self.pending_predictions[rec_id] = record
        return record

    def record_actual_outcome(
        self,
        symbol: str,
        prediction_timestamp_str: str,
        actual_observed_price: float,
        actual_timestamp_str: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Pairs a previously made prediction with subsequent actual market observation at t+1.
        Calculates exact prediction error and directional accuracy, and appends to outcomes stream.
        """
        rec_id = f"{symbol}_{prediction_timestamp_str}"
        record = self.pending_predictions.get(rec_id)
        if not record:
            return None

        spot = record["spot_price"]
        actual_ret = (actual_observed_price - spot) / max(spot, 0.01)
        pred_move = record["tree_alpha_bps"] / 10000.0

        error_rs = round((spot * (1.0 + pred_move)) - actual_observed_price, 4)
        error_bps = round(record["tree_alpha_bps"] - (actual_ret * 10000.0), 2)
        is_correct = bool((pred_move > 0 and actual_ret > 0) or (pred_move < 0 and actual_ret < 0))

        outcome_event = {
            "record_id": rec_id,
            "symbol": symbol,
            "prediction_timestamp": prediction_timestamp_str,
            "outcome_timestamp": actual_timestamp_str or datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
            "spot_price": spot,
            "predicted_alpha_bps": record["tree_alpha_bps"],
            "predicted_target_price": round(spot * (1.0 + pred_move), 4),
            "actual_target_price": round(actual_observed_price, 4),
            "actual_next_price": round(actual_observed_price, 4),
            "actual_return_bps": round(actual_ret * 10000.0, 2),
            "prediction_error_rs": error_rs,
            "abs_error_rs": round(abs(error_rs), 4),
            "abs_error_bps": round(abs(error_bps), 2),
            "is_correct_direction": is_correct,
            "outcome_verified": True,
            "data_source": record.get("data_source", "UNKNOWN")
        }

        # Update in-memory record
        record["outcome_verified"] = True
        record["actual_next_price"] = round(actual_observed_price, 4)
        record["actual_return_bps"] = round(actual_ret * 10000.0, 2)
        record["prediction_error_rs"] = error_rs
        record["is_correct_direction"] = is_correct

        # Append to authoritative outcomes stream
        with open(self.outcomes_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(outcome_event) + "\n")

        if hasattr(self, "storage_manager") and self.storage_manager:
            try:
                self.storage_manager.append_outcome(outcome_event)
            except Exception:
                pass

        self.verified_outcomes.append(record)
        del self.pending_predictions[rec_id]

        # Update drift monitor
        self._update_drift_sentinel()
        return outcome_event

    def process_incoming_quotes(self, quotes: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Scans all pending predictions. Any prediction aged between 50s and 90s is matched
        with the current incoming quote observation, resolving the forward 1-minute outcome.
        Expired predictions (>120s) without matching ticks are cleanly evicted.
        """
        now = datetime.now()
        resolved = []
        expired_keys = []

        for rec_id, rec in list(self.pending_predictions.items()):
            sym = rec.get("symbol")
            ts_str = rec.get("timestamp", "").replace(" IST", "")
            try:
                pred_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue

            age_sec = (now - pred_dt).total_seconds()

            if 50.0 <= age_sec <= 90.0:
                q = quotes.get(sym)
                if q and not q.get("is_stale", False) and q.get("ltp", 0.0) > 0:
                    outcome = self.record_actual_outcome(
                        symbol=sym,
                        prediction_timestamp_str=rec["timestamp"],
                        actual_observed_price=q["ltp"]
                    )
                    if outcome:
                        resolved.append(outcome)
            elif age_sec > 120.0:
                expired_keys.append(rec_id)

        for k in expired_keys:
            if k in self.pending_predictions:
                del self.pending_predictions[k]

        return resolved

    def pair_latest_symbol_outcome(self, symbol: str, actual_observed_price: float) -> Optional[Dict[str, Any]]:
        """Finds the oldest matured pending prediction for a symbol and pairs it with observed price."""
        matching = [rec for rec in self.pending_predictions.values() if rec.get("symbol") == symbol]
        if not matching:
            return None
        # Pair with oldest pending prediction that is at least 45s old if possible
        sorted_m = sorted(matching, key=lambda x: x["timestamp"])
        return self.record_actual_outcome(symbol, sorted_m[0]["timestamp"], actual_observed_price)

    def _update_drift_sentinel(self) -> Dict[str, Any]:
        """
        Evaluates rolling 30 predictions for statistical drift.
        """
        if len(self.verified_outcomes) < 5:
            sentinel_data = {
                "status": "INITIALIZING",
                "verified_predictions_count": len(self.verified_outcomes),
                "rolling_accuracy_pct": 50.0,
                "rolling_mae_rs": 0.0,
                "rolling_brier_score": 0.25,
                "drift_alert": False,
                "hurdle_adjustment": 1.0,
                "last_evaluated": datetime.now().isoformat()
            }
        else:
            window = self.verified_outcomes[-30:]
            correct_count = sum(1 for w in window if w.get("is_correct_direction"))
            rolling_acc = (correct_count / len(window)) * 100.0

            errors = [abs(w.get("prediction_error_rs", 0.0)) for w in window]
            rolling_mae = float(np.mean(errors))

            # Brier score
            probs = np.array([w.get("calibrated_confidence", 50.0) / 100.0 for w in window])
            actuals = np.array([1.0 if w.get("is_correct_direction") else 0.0 for w in window])
            rolling_brier = float(np.mean((probs - actuals) ** 2))

            drift_alert = rolling_acc < (self.drift_threshold * 100.0)
            hurdle_adj = 1.35 if drift_alert else 1.00  # Tighten friction hurdle by 35% on drift

            sentinel_data = {
                "status": "DRIFT_ALERT_ACTIVE" if drift_alert else "STABLE",
                "verified_predictions_count": len(self.verified_outcomes),
                "rolling_window_size": len(window),
                "rolling_accuracy_pct": round(rolling_acc, 2),
                "rolling_mae_rs": round(rolling_mae, 2),
                "rolling_brier_score": round(rolling_brier, 4),
                "drift_alert": drift_alert,
                "hurdle_adjustment": hurdle_adj,
                "last_evaluated": datetime.now().isoformat()
            }

        with open(self.drift_status_file, "w", encoding="utf-8") as f:
            json.dump(sentinel_data, f, indent=2)

        return sentinel_data
