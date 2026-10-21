"""
AlphaNSE V3 — Session 5 Pre-Market Preparation & Model Freezing.
Executes the D-1 daily adaptive cycle for Session 5:
  1. Data Cutoff: Strictly Day 4 close (2026-09-24 15:25:00 IST).
  2. Dataset Update: Merges historical + Session 4 fresh data.
  3. Feature Engineering: 26 features over all data up to 2026-09-24.
  4. 60m Target Labeling: target_return_60m (horizon_bars=12).
  5. Pre-Market Sanity Gates: Leakage check, feature integrity, regime classification.
  6. Model Retraining & Freezing: Serialized model weights + SHA-256 hash.
  7. Manifest Serialization: Marked as FRESH FORWARD VALIDATION (SESSION 5).
"""

import os
import sys
from datetime import date

# Add workspace root to sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from v3.adaptive.daily_pipeline_v3 import AdaptiveDailyPipelineV3
from v3.config.v3_config import (
    FORWARD_VALIDATION_LABEL,
    EXPERIMENT_MODE,
    PROFITABILITY_CLAIM,
    V3_REPORTS_DIR
)


def main():
    print("=" * 80)
    print("  ALPHANSE V3 — SESSION 5 PRE-MARKET RETRAINING & MODEL FREEZING")
    print("=" * 80)
    print(f"  MODE: {FORWARD_VALIDATION_LABEL}")
    print(f"  EXPERIMENT STATUS: {EXPERIMENT_MODE} (Profitability Claim: {PROFITABILITY_CLAIM})")
    print("=" * 80)

    # Session 5 target date is 2026-09-25
    session5_date = date(2026, 9, 25)

    pipeline = AdaptiveDailyPipelineV3()

    print("\n[Step 1] Preparing dataset strictly up to D-1 (2026-09-24)...")
    dataset_meta = pipeline.dataset_updater.prepare_dataset_for_day(session5_date)
    print(f"  Cutoff Timestamp: {dataset_meta['data_cutoff']}")
    print(f"  Dataset Hash:     {dataset_meta['dataset_hash'][:16]}...")
    print(f"  Training Rows:    {dataset_meta['training_rows']}")

    print("\n[Step 2] Retraining 60m adaptive model and running sanity gates...")
    model, manifest = pipeline.model_updater.train_and_freeze_for_day(
        target_day=session5_date,
        dataset_meta=dataset_meta,
        is_forward_validation=True
    )
    manifest_path = pipeline.audit_ledger.save_manifest(manifest)

    print("\n[Step 3] Model Frozen and Manifest Serialized Successfully!")
    print(f"  Model Version:    {manifest.model_version}")
    print(f"  Model Hash:       {manifest.model_hash}")
    print(f"  Target Column:    {manifest.target_column}")
    print(f"  Horizon:          {manifest.horizon_bars * 5}m ({manifest.horizon_bars} bars)")
    print(f"  Regime at Open:   {manifest.regime_at_open}")
    print(f"  Training Window:  {manifest.training_window}")
    print(f"  Manifest Path:    {manifest_path}")

    # Generate Session 5 Readiness Artifact
    os.makedirs(V3_REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(V3_REPORTS_DIR, "SESSION_5_PREMARKET_READINESS_REPORT.md")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# AlphaNSE V3 — Session 5 Pre-Market Readiness Report\n\n")
        f.write("> [!IMPORTANT]\n")
        f.write(f"> **CLASSIFICATION: {FORWARD_VALIDATION_LABEL}**  \n")
        f.write("> **EXPERIMENT TYPE**: Daily-Adaptive 60-Minute Horizon with Rupee Net-Edge Gating  \n")
        f.write(f"> **PROFITABILITY CLAIM**: {PROFITABILITY_CLAIM} (Unproven experimental hypothesis)  \n")
        f.write("> **SAFETY**: Capital router locked; Broker execution physically disabled.\n\n")

        f.write("## 1. Cryptographic Model Provenance\n\n")
        f.write(f"- **Target Session Date**: {session5_date.strftime('%Y-%m-%d')}\n")
        f.write(f"- **Data Cutoff (D-1)**: `{manifest.data_cutoff}`\n")
        f.write(f"- **Training Dataset Hash**: `{manifest.dataset_hash}`\n")
        f.write(f"- **Feature Pipeline Version**: `{manifest.feature_version}`\n")
        f.write(f"- **Model Version**: `{manifest.model_version}`\n")
        f.write(f"- **Model SHA-256 Hash**: `{manifest.model_hash}`\n")
        f.write(f"- **Training Window**: {manifest.training_window}\n")
        f.write(f"- **Training Observations**: {manifest.training_rows:,} rows\n")
        f.write(f"- **Pre-Market Regime**: `{manifest.regime_at_open}`\n\n")

        f.write("## 2. In-Sample Pre-Market Validation Metrics\n\n")
        val = manifest.validation_result
        f.write(f"- **In-Sample Rows**: {val.get('in_sample_rows', 0):,}\n")
        f.write(f"- **In-Sample MAE**: {val.get('mae_bps', 0.0)} bps\n")
        f.write(f"- **In-Sample IC**: {val.get('ic_in_sample', 0.0)}\n")
        f.write(f"- **Annualized Regime Volatility**: {val.get('regime_vol_annualized', 0.0)}%\n")
        f.write(f"- **Sanity Gates Status**: `PASSED`\n\n")

        f.write("## 3. Session 5 Execution Parameters\n\n")
        f.write("| Parameter | Value | Rationale |\n")
        f.write("| :--- | :--- | :--- |\n")
        f.write("| **Holding Horizon** | 12 bars (60 minutes) | Lower turnover, higher gross return opportunity |\n")
        f.write("| **Universe** | Dynamic Tradable Equities (no index) | Dynamic ranking across all available liquid symbols |\n")
        f.write("| **Whitelist/Blacklist** | None (Dynamic) | Avoid premature blacklisting from only 4 sessions |\n")
        f.write("| **Morning Entry Window** | 09:15 to 12:00 IST | Active morning liquidity |\n")
        f.write("| **Lunch Blackout** | 12:00 to 14:00 IST | Strictly NO NEW ENTRIES (avoids lunch chop) |\n")
        f.write("| **Afternoon Entry Window** | 14:00 to 14:25 IST | Post-lunch momentum |\n")
        f.write("| **Entry Cutoff** | 14:25 IST | Ensures 60m position completes before 15:25 close |\n")
        f.write("| **Intraday Square-Off** | 15:25 IST | Zero overnight holding invariant |\n")
        f.write("| **Net-Edge Hurdle** | ≥ ₹0.80 net expected profit | Must clear all statutory taxes, spread, slippage |\n")
        f.write("| **Available Capital** | ₹5,000.00 | Micro-capital account constraint |\n")
        f.write("| **Cash Policy** | Cash is valid & intentional | If net edge < ₹0.80, HOLD CASH (0 trades) |\n\n")

        f.write("## 4. Verification Check\n\n")
        f.write("```bash\n")
        f.write("# Verify manifest on disk:\n")
        f.write(f"type {manifest_path}\n")
        f.write("```\n")

    print(f"\nReadiness Report written to: {report_path}")
    print("=" * 80)
    print("  SESSION 5 IS PREPARED AND READY FOR FORWARD VALIDATION")
    print("=" * 80)


if __name__ == "__main__":
    main()
