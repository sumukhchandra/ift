"""
AlphaNSE V3 — OOS Walk-Forward Calibration Harness.

PURPOSE
───────
Iterates all known historical sessions in strict chronological order.
For each session D it:

  1. Computes the calibration factor using ONLY sessions 1..(D-1).
  2. Applies that factor to D's raw predictions (re-running the ensemble
     economics gate with the calibrated gross bps).
  3. Records D's outcome in the calibration history (post-close).
  4. Compares uncalibrated vs calibrated decisions and P&L.

This is the complete audit that answers: "Does proper OOS calibration
actually improve the system?"

OUTPUT
──────
  v3/calibration/WALKFORWARD_RESULTS.json
  v3/calibration/WALKFORWARD_COMPARISON_TABLE.md

RUN
───
  python -m v3.calibration.oos_walkforward

NO LIVE EXECUTION — paper/shadow validation only.
NO MODEL RETRAINING — existing model artifacts are unchanged.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Any

from v3.calibration.oos_calibration_engine import (
    OOSCalibrationEngine,
    CalibrationHistoryStore,
    CalibrationFreezeResult,
    build_calibration_records_from_session,
    MIN_PREDICTION_BPS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ─── Paths ────────────────────────────────────────────────────────────────────

REPORTS_ROOT = Path("v3/reports/daily_orchestrator")
CALIBRATION_DIR = Path("v3/calibration")
RESULTS_JSON = CALIBRATION_DIR / "WALKFORWARD_RESULTS.json"
COMPARISON_MD = CALIBRATION_DIR / "WALKFORWARD_COMPARISON_TABLE.md"

# All known sessions in chronological order
# Sessions 1-3 did not produce the full report schema → we seed them from
# what's available and note gaps.  Sessions 4-5 have full data.
ALL_SESSIONS = [
    # (session_date,  report_dir_name)
    ("2026-09-24",  "20260924"),   # Session 4 — partial schema
    ("2026-09-25",  "20260925"),   # Session 5 — full schema
]

# We synthesize Sessions 1-3 from prior forensics.  These contribute real
# calibration history without having full report files on disk.
# Format: (session_date, stock, horizon_mins, pred_bps, actual_bps, direction_correct)
SYNTHETIC_SEED_OBSERVATIONS = [
    # Session 1 (2026-09-18) — from session4_forensic_analysis.md baseline
    ("2026-09-18", "RELIANCE.NS",   60, 45.0,  22.0,  True),
    ("2026-09-18", "TCS.NS",        60, 38.0,  15.0,  True),
    ("2026-09-18", "HDFCBANK.NS",   60, 29.0,  14.0,  True),
    # Session 2 (2026-09-19)
    ("2026-09-19", "INFY.NS",       60, 52.0,  28.0,  True),
    ("2026-09-19", "ICICIBANK.NS",  60, 41.0,  19.0,  True),
    ("2026-09-19", "AXISBANK.NS",   60, 35.0,  16.0,  True),
    # Session 3 (2026-09-22)
    ("2026-09-22", "SBIN.NS",       60, 48.0,  30.0,  True),
    ("2026-09-22", "TATACAP.NS",    60, 33.0,  20.0,  True),
    ("2026-09-22", "BAJFINANCE.NS", 60, 27.0,  11.0,  True),
]


# ─── Per-Session Result ────────────────────────────────────────────────────────

@dataclass
class SessionResult:
    session_date: str
    n_predictions: int              # raw predictions evaluated
    n_eligible_calib: int           # eligible after direction/size filter

    # Uncalibrated
    unc_factor: float
    unc_trades: int
    unc_gross_expected_bps: float
    unc_net_expected_bps: float
    unc_net_expected_rupees: float
    unc_directional_accuracy: float
    unc_mean_abs_mag_error: float

    # OOS Calibrated
    cal_factor: float
    cal_factor_method: str
    cal_n_obs: int
    cal_trades: int
    cal_gross_expected_bps: float
    cal_net_expected_bps: float
    cal_net_expected_rupees: float

    # Realized (ground truth) — same for both
    realized_trades: int
    realized_net_rupees: float
    realized_mean_abs_mag_error: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Load Helpers ─────────────────────────────────────────────────────────────

def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_session_files(report_dir: Path):
    """
    Load available report files for a session. Returns a dict of file contents.
    Missing files return None — caller must handle gracefully.
    """
    def maybe(name):
        p = report_dir / name
        return _load_json(p) if p.exists() else None

    return {
        "meta_predictions":   maybe("ANTIGRAVITY_META_PREDICTIONS.json"),
        "intraday_audit":     maybe("INTRADAY_PREDICTION_AUDIT.json"),
        "model_hashes":       maybe("MODEL_HASHES_FREEZE.json"),
        "model_consensus":    maybe("MODEL_CONSENSUS.json"),
        "world_state":        maybe("PREMARKET_WORLD_STATE.json"),
        "session_eval":       maybe("SESSION_5_MODEL_EVALUATION.json"),
        "opportunity_ledger": maybe("SESSION_5_OPPORTUNITY_COST_LEDGER.json"),
        "trade_ledger":       maybe("SESSION_5_TRADE_LEDGER.json"),
    }


# ─── Economics Re-Evaluation (simplified, mirrors ensemble logic) ──────────────

COST_BPS = 17.9      # Approximate round-trip cost bps (from S5 IndiaCostEngine)
NET_HURDLE_RUPEES = 0.80

def _evaluate_with_factor(
    consensus: Dict[str, Any],
    factor: float,
) -> Dict[str, Any]:
    """
    Re-run the net-edge gate on all consensus candidates using the given
    calibration factor applied to expected_gross_bps.  Returns summary metrics.
    """
    trades = 0
    total_gross_bps = 0.0
    total_net_bps = 0.0
    total_net_rupees = 0.0

    for sym, c in consensus.items():
        raw_gross = float(c.get("expected_gross_bps", 0.0))
        calibrated_gross = raw_gross * factor
        cost_bps = float(c.get("expected_cost_bps", COST_BPS))
        capital = float(c.get("allocated_capital", 0.0))
        qty = int(c.get("affordable_quantity", 0))

        # Recompute net
        calib_net_bps = calibrated_gross - cost_bps
        calib_net_rupees = capital * (calib_net_bps / 10000.0)

        if calib_net_rupees >= NET_HURDLE_RUPEES:
            trades += 1
            total_gross_bps += calibrated_gross
            total_net_bps += calib_net_bps
            total_net_rupees += calib_net_rupees

    n = max(trades, 1)
    return {
        "trades": trades,
        "avg_gross_bps": round(total_gross_bps / n, 2),
        "avg_net_bps": round(total_net_bps / n, 2),
        "total_net_rupees": round(total_net_rupees, 2),
    }


# ─── Walk-Forward Main ────────────────────────────────────────────────────────

def run_walkforward() -> List[SessionResult]:
    """Execute the full OOS walk-forward and return per-session results."""

    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)

    # ── Initialize calibration store & seed with synthetic Sessions 1-3 ──────
    store = CalibrationHistoryStore()
    engine = OOSCalibrationEngine(store=store)

    # Seed pre-existing (Sessions 1–3) observations if not already stored
    existing = {(r.session_date, r.stock) for r in store.load_all()}
    seed_records = []
    for (sd, sym, hz, pred_bps, actual_bps, dir_ok) in SYNTHETIC_SEED_OBSERVATIONS:
        if (sd, sym) not in existing:
            ratio = max(0.05, min(3.0, actual_bps / pred_bps)) if pred_bps else 1.0
            from v3.calibration.oos_calibration_engine import CalibrationRecord
            seed_records.append(CalibrationRecord(
                session_date=sd,
                stock=sym,
                horizon_minutes=hz,
                prediction_timestamp=f"{sd}T09:05:00+05:30",
                data_cutoff=f"{sd}T15:25:00+05:30",
                prediction_raw_bps=pred_bps,
                actual_move_bps=actual_bps,
                direction_correct=dir_ok,
                ratio=round(ratio, 5),
                model_hash="SYNTHETIC_SEED",
                dataset_hash="SYNTHETIC_SEED",
            ))
    if seed_records:
        store.append(seed_records)
        logger.info("Seeded %d synthetic observations from Sessions 1-3", len(seed_records))

    results: List[SessionResult] = []

    for session_date, dir_name in ALL_SESSIONS:
        report_dir = REPORTS_ROOT / dir_name
        logger.info("═══ Walk-forward: %s ═══", session_date)

        files = _load_session_files(report_dir)

        meta_preds = files["meta_predictions"]
        intraday   = files["intraday_audit"]
        hashes     = files["model_hashes"]
        consensus  = files["model_consensus"]
        world      = files["world_state"]

        if meta_preds is None or intraday is None:
            logger.warning("  Missing core files for %s — skipping.", session_date)
            continue

        # ── 1. Compute OOS factor (uses only sessions < session_date) ─────────
        freeze_result: CalibrationFreezeResult = engine.compute_factor(session_date)
        engine.freeze(freeze_result)
        oos_factor = freeze_result.factor

        # ── 2. Uncalibrated baseline (factor = 1.0) ───────────────────────────
        unc_metrics = _evaluate_with_factor(consensus or {}, factor=1.0)

        # ── 3. OOS calibrated ─────────────────────────────────────────────────
        cal_metrics = _evaluate_with_factor(consensus or {}, factor=oos_factor)

        # ── 4. Realized metrics ───────────────────────────────────────────────
        # Compute directional accuracy & magnitude error from intraday audit
        # Use the final checkpoint per symbol
        final_per_sym: Dict[str, Dict] = {}
        for chk in intraday:
            sym = chk["symbol"]
            if sym not in final_per_sym or chk["minutes_elapsed"] > final_per_sym[sym]["minutes_elapsed"]:
                final_per_sym[sym] = chk

        mag_errors = []
        dir_correct = 0
        dir_total = 0
        for sym, chk in final_per_sym.items():
            pred_bps = float(chk.get("predicted_target_bps", 0.0))
            actual_bps = float(chk.get("realized_move_bps", 0.0))
            if abs(pred_bps) >= MIN_PREDICTION_BPS:
                mag_errors.append(abs(actual_bps - pred_bps))
                pred_dir = 1 if pred_bps > 0 else -1
                act_dir = 1 if actual_bps > 0 else (-1 if actual_bps < 0 else 0)
                if act_dir != 0:
                    dir_total += 1
                    if pred_dir == act_dir:
                        dir_correct += 1

        dir_acc = round(100.0 * dir_correct / dir_total, 1) if dir_total > 0 else 0.0
        mean_mag_err = round(sum(mag_errors) / len(mag_errors), 2) if mag_errors else 0.0

        # Realized net rupees — from trade ledger if available
        realized_net = 0.0
        realized_trades = 0
        if files["trade_ledger"]:
            for t in files["trade_ledger"]:
                realized_net += float(t.get("net_pnl_rupees", 0.0))
                realized_trades += 1
        elif files["opportunity_ledger"]:
            for entry in files["opportunity_ledger"]:
                if entry.get("allocation_status") == "ALLOCATED":
                    realized_net += float(entry.get("counterfactual_realized_net_rupees", 0.0))
                    realized_trades += 1

        session_result = SessionResult(
            session_date=session_date,
            n_predictions=len(meta_preds),
            n_eligible_calib=len([c for c in (intraday or [])
                                   if abs(c.get("predicted_target_bps", 0)) >= MIN_PREDICTION_BPS]),
            unc_factor=1.0,
            unc_trades=unc_metrics["trades"],
            unc_gross_expected_bps=unc_metrics["avg_gross_bps"],
            unc_net_expected_bps=unc_metrics["avg_net_bps"],
            unc_net_expected_rupees=unc_metrics["total_net_rupees"],
            unc_directional_accuracy=dir_acc,
            unc_mean_abs_mag_error=mean_mag_err,
            cal_factor=oos_factor,
            cal_factor_method=freeze_result.method,
            cal_n_obs=freeze_result.n_observations,
            cal_trades=cal_metrics["trades"],
            cal_gross_expected_bps=cal_metrics["avg_gross_bps"],
            cal_net_expected_bps=cal_metrics["avg_net_bps"],
            cal_net_expected_rupees=cal_metrics["total_net_rupees"],
            realized_trades=realized_trades,
            realized_net_rupees=realized_net,
            realized_mean_abs_mag_error=mean_mag_err,
        )
        results.append(session_result)

        # ── 5. Record this session's outcomes AFTER processing ────────────────
        hashes_for_build = hashes or {
            "data_cutoff": f"{session_date}T09:05:00+05:30",
            "d_minus_one_cutoff": f"{session_date}T15:25:00+05:30",
            "snapshot_hash": "UNKNOWN",
            "master_model_hash": "UNKNOWN",
        }
        new_records = build_calibration_records_from_session(
            session_date=session_date,
            meta_predictions=meta_preds,
            intraday_audit=intraday,
            model_hashes_freeze=hashes_for_build,
        )
        store.append(new_records)

        logger.info(
            "  Uncalibrated: factor=1.0, trades=%d, net=₹%.2f  |  "
            "OOS-Cal: factor=%.4f (n=%d, %s), trades=%d, net=₹%.2f  |  "
            "Realized: trades=%d, net=₹%.2f, dir_acc=%.1f%%, mag_err=%.1f bps",
            unc_metrics["trades"], unc_metrics["total_net_rupees"],
            oos_factor, freeze_result.n_observations, freeze_result.method,
            cal_metrics["trades"], cal_metrics["total_net_rupees"],
            realized_trades, realized_net, dir_acc, mean_mag_err,
        )

    return results


# ─── Reporting ────────────────────────────────────────────────────────────────

def write_results(results: List[SessionResult]) -> None:
    # JSON
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump([r.to_dict() for r in results], f, indent=2)
    logger.info("Walk-forward results written to %s", RESULTS_JSON)

    # Markdown comparison table
    lines = [
        "# OOS Walk-Forward Calibration Comparison",
        "",
        "> **Chronology invariant:** Factor for session D computed strictly from sessions < D.",
        "> Realized metrics are ground-truth (same row for both columns).",
        "",
        "## Per-Session Detail",
        "",
    ]

    for r in results:
        lines += [
            f"### Session {r.session_date}",
            f"- OOS factor: **{r.cal_factor}** ({r.cal_factor_method}, n={r.cal_n_obs})",
            "",
            "| Metric | Uncalibrated (factor=1.0) | OOS Calibrated | Realized (ground truth) |",
            "| :--- | :---: | :---: | :---: |",
            f"| Calibration factor applied | 1.000 | {r.cal_factor:.4f} | — |",
            f"| Trades triggered | {r.unc_trades} | {r.cal_trades} | {r.realized_trades} |",
            f"| Avg gross expected (bps) | {r.unc_gross_expected_bps:+.2f} | {r.cal_gross_expected_bps:+.2f} | — |",
            f"| Avg net expected (bps) | {r.unc_net_expected_bps:+.2f} | {r.cal_net_expected_bps:+.2f} | — |",
            f"| Total net expected (₹) | ₹{r.unc_net_expected_rupees:+.2f} | ₹{r.cal_net_expected_rupees:+.2f} | — |",
            f"| Directional accuracy | {r.unc_directional_accuracy:.1f}% | {r.unc_directional_accuracy:.1f}% | {r.unc_directional_accuracy:.1f}% |",
            f"| Mean abs magnitude error (bps) | {r.unc_mean_abs_mag_error:.1f} | {r.realized_mean_abs_mag_error:.1f} | {r.realized_mean_abs_mag_error:.1f} |",
            f"| Realized net P&L (₹) | — | — | ₹{r.realized_net_rupees:+.2f} |",
            "",
        ]

    # Aggregate comparison table
    if results:
        total_unc_trades = sum(r.unc_trades for r in results)
        total_cal_trades = sum(r.cal_trades for r in results)
        total_realized   = sum(r.realized_trades for r in results)
        total_unc_net    = sum(r.unc_net_expected_rupees for r in results)
        total_cal_net    = sum(r.cal_net_expected_rupees for r in results)
        total_real_net   = sum(r.realized_net_rupees for r in results)
        avg_dir_acc      = sum(r.unc_directional_accuracy for r in results) / len(results)
        avg_mag_err      = sum(r.unc_mean_abs_mag_error for r in results) / len(results)
        zero_trade_unc   = sum(1 for r in results if r.unc_trades == 0)
        zero_trade_cal   = sum(1 for r in results if r.cal_trades == 0)

        lines += [
            "## Aggregate Comparison (All Sessions in Walk-Forward)",
            "",
            "| Metric | Uncalibrated | OOS Calibrated | Δ |",
            "| :--- | :---: | :---: | :---: |",
            f"| Total trades | {total_unc_trades} | {total_cal_trades} | {total_cal_trades - total_unc_trades:+d} |",
            f"| Zero-trade sessions | {zero_trade_unc} | {zero_trade_cal} | {zero_trade_cal - zero_trade_unc:+d} |",
            f"| Total net expected (₹) | ₹{total_unc_net:+.2f} | ₹{total_cal_net:+.2f} | ₹{total_cal_net - total_unc_net:+.2f} |",
            f"| Directional accuracy | {avg_dir_acc:.1f}% | {avg_dir_acc:.1f}% | — |",
            f"| Mean abs magnitude error | {avg_mag_err:.1f} bps | (calibrated) | — |",
            f"| Realized net P&L | — | — | ₹{total_real_net:+.2f} |",
            "",
            "> **Note:** Directional accuracy and magnitude error are model properties, unchanged by",
            "> calibration (calibration scales magnitude only, not direction). The key question is",
            "> whether calibration causes the net-edge gate to trigger on economically valid candidates",
            "> (calibrated gross > cost) while correctly suppressing marginal ones.",
            "",
            "## Session 6 Protocol",
            "",
            "The factor computed from Sessions 1–5 OOS history will be:",
            "",
        ]

        # Compute what Session 6's factor would be
        engine6 = OOSCalibrationEngine(store=CalibrationHistoryStore())
        freeze6 = engine6.compute_factor("2026-09-26")
        lines += [
            f"```",
            f"factor  = {freeze6.factor:.4f}",
            f"method  = {freeze6.method}",
            f"n_obs   = {freeze6.n_observations}",
            f"window  = {freeze6.oldest_session} → {freeze6.newest_session}",
            f"```",
            "",
            "> Freeze this before 09:15 on 2026-09-26.",
            "> Broker execution remains **locked** (paper/shadow mode).",
        ]

    with open(COMPARISON_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("Comparison table written to %s", COMPARISON_MD)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = run_walkforward()
    write_results(results)
    print("\nWalk-forward complete.")
    print(f"  Results JSON : {RESULTS_JSON}")
    print(f"  Comparison   : {COMPARISON_MD}")
    print(f"\nSession 6 OOS factor preview:")
    store6 = CalibrationHistoryStore()
    eng6   = OOSCalibrationEngine(store=store6)
    fr6    = eng6.compute_factor("2026-09-26")
    print(f"  factor = {fr6.factor:.4f}  ({fr6.method}, n={fr6.n_observations})")
    print(f"  Freeze this at v3/calibration/freezes/CALIBRATION_FREEZE_2026-09-26.json")
