#!/usr/bin/env python3
"""
scripts/generate_prediction_vs_price_chart.py
Generates an authoritative chart showing actual observed prices in red
and the recorded model prediction series in blue, with missing data visibly indicated.
Outputs PNG to reports/figures/ and artifact directory.
"""

import os
import sys
import shutil
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.research.forward_evaluation import ForwardEvaluationPipeline


def generate_chart():
    print("=" * 80)
    print("  GENERATING PREDICTION VS ACTUAL OBSERVED PRICE CHART")
    print("=" * 80)

    data_path = os.path.join(WORKSPACE_ROOT, "QA", "data", "genuine_forward_oos_oct13_oct14.csv")
    if not os.path.exists(data_path):
        print(f"Error: test data not found at {data_path}")
        return False

    df = pd.read_csv(data_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    pipeline = ForwardEvaluationPipeline(test_data_path=data_path)
    pred_dfs = pipeline.compute_all_predictions(df)

    # Pick NIFTYBEES.NS or BAJFINANCE as illustrative example of liquid equity
    target_sym = "BAJFINANCE"
    if target_sym not in pred_dfs:
        target_sym = list(pred_dfs.keys())[0]

    sym_df = pred_dfs[target_sym].copy()
    sym_df = sym_df.sort_values("timestamp").reset_index(drop=True)

    # 1-step ahead predicted price = close * (1 + pred_return)
    sym_df["predicted_price"] = sym_df["close"] * (1.0 + sym_df["pred_return"])

    # Detect data gaps / missing timestamps (> 2 minutes gap during trading hours)
    sym_df["time_diff"] = sym_df["timestamp"].diff().dt.total_seconds() / 60.0
    gaps = sym_df[sym_df["time_diff"] > 2.0]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True, gridspec_kw={"height_ratios": [2.5, 1]})

    # 1. Main Price vs Prediction Chart
    ax1.plot(sym_df["timestamp"], sym_df["close"], color="crimson", linewidth=1.5, label=f"Actual Observed Price ({target_sym}) [RED]")
    ax1.plot(sym_df["timestamp"], sym_df["predicted_price"], color="royalblue", linewidth=1.2, linestyle="--", alpha=0.85, label=f"Model Predicted Target Price (t+1) [BLUE]")

    # Visibly indicate missing data / market close overnight gap
    gap_labeled = False
    for _, gap_row in gaps.iterrows():
        gap_end = gap_row["timestamp"]
        # approximate gap start
        idx = gap_row.name
        gap_start = sym_df.loc[idx - 1, "timestamp"]
        lbl = "Missing Data / Exchange Closed Gap" if not gap_labeled else ""
        ax1.axvspan(gap_start, gap_end, color="gray", alpha=0.35, hatch="//", label=lbl)
        ax2.axvspan(gap_start, gap_end, color="gray", alpha=0.35, hatch="//")
        gap_labeled = True

    ax1.set_title(f"AlphaNSE V3 — Actual Observed Price (Red) vs Model Predictions (Blue)\nAsset: {target_sym} | Out-of-Sample Forward Window: Oct 13 - Oct 14, 2026", fontsize=13, fontweight="bold", pad=12)
    ax1.set_ylabel("Price (INR / ₹)", fontsize=11, fontweight="bold")
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="upper left", framealpha=0.9)

    # 2. Prediction Residuals / Delta (Bps)
    sym_df["delta_bps"] = (sym_df["predicted_price"] - sym_df["close"]) / sym_df["close"] * 10000.0
    ax2.plot(sym_df["timestamp"], sym_df["delta_bps"], color="navy", linewidth=0.8, label="Predicted Move (bps)")
    ax2.axhline(0, color="black", linestyle="-", linewidth=0.8)
    ax2.axhline(pipeline.confidence_threshold, color="orange", linestyle=":", alpha=0.7, label="Threshold Buffer")
    ax2.axhline(-pipeline.confidence_threshold, color="orange", linestyle=":", alpha=0.7)
    ax2.set_ylabel("Expected Return (bps)", fontsize=10, fontweight="bold")
    ax2.set_xlabel("Exchange Timestamp (IST)", fontsize=11, fontweight="bold")
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="upper right", framealpha=0.9)

    plt.tight_layout()

    # Save to reports/figures/
    fig_dir = os.path.join(WORKSPACE_ROOT, "reports", "figures")
    os.makedirs(fig_dir, exist_ok=True)
    out_png = os.path.join(fig_dir, "prediction_vs_price_oct13_oct14.png")
    plt.savefig(out_png, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  [OK] Saved chart to: {out_png}")

    # Copy to artifact directory for embedding
    artifact_dir = r"C:\Users\sumuk\.gemini\antigravity-ide\brain\c633bf16-4bdf-41c8-a21b-85f856277684"
    if os.path.exists(artifact_dir):
        artifact_png = os.path.join(artifact_dir, "prediction_vs_price_oct13_oct14.png")
        shutil.copyfile(out_png, artifact_png)
        print(f"  [OK] Copied chart to artifact dir: {artifact_png}")

    return True


if __name__ == "__main__":
    generate_chart()
