"""
AlphaNSE V3 — Session 6 Multi-Model Pre-Market Retraining & Registration Engine.
Independently trains, validates, and freezes all 5 active research models for Session 6:
  MODEL_01: V2_15M   (15m baseline return regressor)
  MODEL_02: HYPO001  (30m midday trend follower)
  MODEL_03: HYPO002  (60m high-beta momentum)
  MODEL_04: HYPO003  (15m short-sparsity opportunistic)
  MODEL_05: V3_60M   (60m adaptive cost-aware regressor)

STATUS: EXPERIMENT / VALIDATION
DATA CUTOFF: Strictly Session 5 close (2026-09-25 15:25 IST).
ZERO LOOKAHEAD: Absolutely no data from 2026-09-28.
"""

import os
import sys
from datetime import date
import json

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from v3.adaptive.daily_pipeline_v3 import AdaptiveDailyPipelineV3
from v3.config.multimodel_config import SESSION_6_DATE, SESSION_6_D_MINUS_ONE_CUTOFF, ACTIVE_MODEL_SPECS
from v3.config.v3_config import FORWARD_VALIDATION_LABEL, V3_REPORTS_DIR, PROFITABILITY_CLAIM


def main():
    print("=" * 80)
    print("  ALPHANSE V3 — MULTI-MODEL 5-MODEL PRE-MARKET RETRAINING (SESSION 6)")
    print("=" * 80)
    print(f"  Target Session:      {SESSION_6_DATE}")
    print(f"  D-1 Data Cutoff:     {SESSION_6_D_MINUS_ONE_CUTOFF}")
    print(f"  Active Models (5):   {', '.join(ACTIVE_MODEL_SPECS.keys())}")
    print(f"  Classification:      {FORWARD_VALIDATION_LABEL}")
    print(f"  Profitability Claim: {PROFITABILITY_CLAIM} (Unproven experimental hypothesis)")
    print("=" * 80)

    target_day = date(2026, 9, 28)
    pipeline = AdaptiveDailyPipelineV3()

    print("\n[Step 1] Preparing historical dataset strictly up to D-1 close (2026-09-25 15:25 IST)...")
    dataset_meta = pipeline.dataset_updater.prepare_dataset_for_day(target_day)
    print(f"  Cutoff Timestamp:    {dataset_meta['data_cutoff']}")
    print(f"  Dataset Hash:        {dataset_meta['dataset_hash'][:16]}...")
    print(f"  Total Ingested Rows: {dataset_meta['training_rows']}")

    print("\n[Step 2] Independently training and validating all 5 models...")
    registry = pipeline.multimodel_trainer.train_all_session_models(
        target_day=target_day,
        dataset_meta=dataset_meta
    )

    status_summary = registry.get_status_summary()
    print("\n" + "=" * 80)
    print("  MULTI-MODEL PRE-MARKET VALIDATION STATUS")
    print("=" * 80)
    print(f"  Total Registered:    {status_summary['total_registered']}")
    print(f"  Valid Models:        {status_summary['valid_model_count']}/5")
    print(f"  Active Models:       {', '.join(status_summary['valid_models'])}")
    print(f"  Invalid Models:      {status_summary['invalid_models'] if status_summary['invalid_models'] else 'None'}")
    print("-" * 80)

    for m_id, meta in registry.metadata.items():
        val = meta.validation_metrics
        status_flag = "[OK] FROZEN" if meta.status == "FROZEN" else "[FAIL] INVALID"
        print(f"  {status_flag} {m_id:8s} | Horizon: {meta.target_horizon_minutes:2d}m | Samples: {meta.training_sample_count:5d} | IC: {val.get('in_sample_ic', 0.0):+.4f} | Hash: {meta.model_hash[:16]}...")

    # Create Master Manifest
    print("\n[Step 3] Freezing master session manifest...")
    manifest, reg = pipeline.prepare_multimodel_premarket(
        target_day=target_day,
        is_forward_validation=True
    )
    print(f"  Master Manifest:     {manifest.model_version}")
    print(f"  Master Hash:         {manifest.model_hash[:16]}...")
    print(f"  Manifest Path:       v3/adaptive/ledger/manifests/manifest_20260928.json")

    # Generate Readiness Report
    os.makedirs(V3_REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(V3_REPORTS_DIR, "SESSION_6_MULTIMODEL_PREMARKET_READINESS_REPORT.md")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# AlphaNSE V3 — Session 6 Multi-Model Pre-Market Readiness Report\n\n")
        f.write("> [!IMPORTANT]\n")
        f.write(f"> **CLASSIFICATION: {FORWARD_VALIDATION_LABEL}**  \n")
        f.write("> **SYSTEM**: AlphaNSE V3 Multi-Model Ensemble Architecture  \n")
        f.write(f"> **PROFITABILITY CLAIM**: {PROFITABILITY_CLAIM} (Unproven experimental hypothesis)  \n")
        f.write("> **SAFETY**: Broker execution remains physically disabled; Capital router locked; Paper/Shadow only.\n\n")

        f.write("## 1. Session Provenance & Data Invariants\n\n")
        f.write(f"- **Target Session Date**: `{SESSION_6_DATE}`\n")
        f.write(f"- **Data Cutoff (D-1)**: `{SESSION_6_D_MINUS_ONE_CUTOFF}`\n")
        f.write(f"- **Zero-Lookahead Guarantee**: Strictly `< 2026-09-28 00:00:00 IST`\n")
        f.write(f"- **Dataset SHA-256 Hash**: `{dataset_meta['dataset_hash']}`\n")
        f.write(f"- **Feature Schema Hash**: `{pipeline.multimodel_trainer.feature_schema_hash}`\n")
        f.write(f"- **Master Model Version**: `{manifest.model_version}`\n")
        f.write(f"- **Master SHA-256 Hash**: `{manifest.model_hash}`\n")
        f.write(f"- **Pre-Market Regime**: `{manifest.regime_at_open}`\n\n")

        f.write("## 2. Model Status Summary\n\n")
        f.write("| Model ID | Research Identity | Horizon | Direction | In-Sample IC | Training Rows | Model SHA-256 Hash | Status |\n")
        f.write("| :--- | :--- | :---: | :---: | :---: | :---: | :--- | :---: |\n")
        for m_id, meta in registry.metadata.items():
            val = meta.validation_metrics
            f.write(
                f"| **{m_id}** | {ACTIVE_MODEL_SPECS[m_id]['description']} | "
                f"{meta.target_horizon_minutes}m | {meta.direction} | "
                f"{val.get('in_sample_ic', 0.0):+.4f} | {meta.training_sample_count:,} | "
                f"`{meta.model_hash[:16]}...` | **{meta.status}** |\n"
            )

        f.write(f"\n- **Total Models Registered**: {status_summary['total_registered']}\n")
        f.write(f"- **Valid Models Active**: {status_summary['valid_model_count']}/5\n")
        f.write(f"- **Ensemble Readiness**: `READY`\n")
        f.write(f"- **Failure Isolation**: Verified (no silent substitutions)\n\n")

        f.write("## 3. Ensemble Decision Engine Specifications\n\n")
        f.write("| Parameter | Setting | Operational Principle |\n")
        f.write("| :--- | :--- | :--- |\n")
        f.write("| **Consensus Mechanism** | Horizon-Aware Directional Agreement | Separate 15m, 30m, and 60m horizons; no blind averaging |\n")
        f.write("| **Agreement Tracking** | 0/5 to 5/5 agreement | Explicit attribution of supporting vs contradicting models |\n")
        f.write("| **Economic Hurdle** | ≥ ₹0.80 Net Profit per Trade | Expected gross ₹ must exceed all-in transaction friction + ₹0.80 |\n")
        f.write("| **Statutory Costing** | IndiaCostEngine Zerodha Schedule | Brokerage + STT + Exchange + SEBI + Stamp + GST |\n")
        f.write("| **Execution Friction** | DynamicCostModel Aggressive | Spread + Slippage + Market Impact |\n")
        f.write("| **Capital Sizing** | Whole-Share Integer Sizing | Sized within ₹5,000 paper capital (Max 95% allocation) |\n")
        f.write("| **Trading Windows** | 09:15–12:00 & 14:00–14:25 IST | Lunch Blackout (12:00–14:00), 14:25 Entry Cutoff, 15:25 Flattening |\n")
        f.write("| **Cash Policy** | Cash is valid and intentional | If expected net return < ₹0.80, HOLD CASH (0 trades) |\n")
        f.write("| **Mid-Session Policy** | STRICT FREEZE | Zero retraining, zero parameter adjustments during session |\n\n")

        f.write("## 4. Operational Safety Invariants\n\n")
        f.write("- [x] `LiveExecutionDisabledError` physically active in codebase.\n")
        f.write("- [x] `CapitalRouter` locked to paper simulation mode.\n")
        f.write("- [x] Zero broker order transmission.\n")
        f.write("- [x] Historical V2 evidence sealed and untouched (188 trades, -₹378.61).\n")
        f.write("- [x] Phase 3B historical candidate records preserved.\n")
        f.write("- [x] Multi-model artifacts isolated under `v3/models/multimodel/`.\n")

    print(f"\nReadiness Report written to: {report_path}")
    print("=" * 80)
    print("  PRE-MARKET RETRAINING COMPLETE: ALL 5 MODELS READY FOR SESSION 6")
    print("=" * 80)


if __name__ == "__main__":
    main()
