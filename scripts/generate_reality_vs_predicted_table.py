#!/usr/bin/env python3
"""
scripts/generate_reality_vs_predicted_table.py
AlphaNSE V3 — Comprehensive Reality vs. Predicted Price Comparison Table.
Compiles all 615 live 30-minute forward forecasts and side-by-side real market prints
from Session 12 (Thursday, October 08, 2026).
"""

import os
import sys
import json
from datetime import datetime

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STREAM_PATH = os.path.join(WORKSPACE_ROOT, "v3", "reports", "ROLLING_30M_LIVE_STREAM.jsonl")
OUTPUT_MD = os.path.join(WORKSPACE_ROOT, "v3", "reports", "REALITY_VS_PREDICTED_TABLE.md")


def main():
    if not os.path.exists(STREAM_PATH):
        print(f"[ERR] File not found: {STREAM_PATH}")
        return

    with open(STREAM_PATH, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    print(f"Loaded {len(records)} verified forecast records from {STREAM_PATH}.")

    by_sym = {}
    for r in records:
        by_sym.setdefault(r["symbol"], []).append(r)

    md_lines = [
        "# 📊 AlphaNSE V3 — Reality vs. Predicted Price Verification Table",
        "",
        "**Trading Session:** `Session 12 (Thursday, October 08, 2026 — Weekly Expiry)`  ",
        "**Forecasting Horizon:** `Rolling 30 Minutes Forward` ($T \\rightarrow T + 30\\text{m}$)  ",
        f"**Total Verified Comparisons:** **{len(records):,} Live Forecasts**  ",
        f"**Overall Directional Accuracy:** **{sum(1 for r in records if r['is_correct']) / len(records) * 100:.1f}%**  ",
        "",
        "---",
        "",
        "## 1. Instrument Performance Summary",
        "",
        "| Symbol | Asset Name | Total Predictions | Correct Hits | Directional Hit Rate % | Mean Price Error (₹) | Mean Error (bps) | Quant Verdict |",
        "|---|---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    sym_names = {
        "^NSEI": "NIFTY 50 Index",
        "INFY.NS": "Infosys",
        "RELIANCE.NS": "Reliance Industries",
        "BAJFINANCE.NS": "Bajaj Finance",
        "AXISBANK.NS": "Axis Bank",
        "TATACAP.NS": "Tata Capital"
    }

    for sym, name in sym_names.items():
        recs = by_sym.get(sym, [])
        if not recs:
            continue
        tot = len(recs)
        hits = sum(1 for r in recs if r["is_correct"])
        acc = (hits / tot * 100) if tot > 0 else 0
        mae_rs = sum(r["error_rs"] for r in recs) / tot
        mae_bps = sum(r["error_bps"] for r in recs) / tot
        verdict = "🟢 Elite (>80%)" if acc >= 80 else ("🟢 Strong (>60%)" if acc >= 60 else ("🟡 Positive (>50%)" if acc >= 50 else "🔴 Sub-50%"))
        md_lines.append(
            f"| `{sym}` | {name} | {tot} | {hits} | **{acc:.1f}%** | ₹{mae_rs:.2f} | {mae_bps:.1f} bps | {verdict} |"
        )

    md_lines.extend([
        "",
        "---",
        "",
        "## 2. Chronological Reality vs. Predicted Comparisons (By Instrument)",
        ""
    ])

    # Sample intervals across the trading session for clean presentation
    for sym, name in sym_names.items():
        recs = by_sym.get(sym, [])
        if not recs:
            continue

        md_lines.extend([
            f"### {name} (`{sym}`)",
            "",
            "| Forecast Time (T) | Target Time (T+30m) | Initial Price (₹) | **Predicted Price (₹)** | **REAL Live Price (₹)** | Pred Dir | Real Dir | Result | Price Error (₹) | Error (bps) |",
            "|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
        ])

        # Pick every 6th record to provide a full-day spread from open to close
        step = max(1, len(recs) // 16)
        sampled = recs[::step]
        if recs[-1] not in sampled:
            sampled.append(recs[-1])

        for r in sampled:
            hit_str = "✅ HIT" if r["is_correct"] else "❌ MISS"
            md_lines.append(
                f"| {r['forecast_time']} IST | {r['target_time']} IST | ₹{r['initial_price']:,.2f} | "
                f"**₹{r['predicted_price']:,.2f}** | **₹{r['actual_price']:,.2f}** | "
                f"`{r['predicted_dir']}` | `{r['actual_dir']}` | {hit_str} | ₹{r['error_rs']:.2f} | {r['error_bps']:.1f} bps |"
            )
        md_lines.append("")

    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"Saved complete Reality vs Predicted table to: {OUTPUT_MD}")


if __name__ == "__main__":
    main()
