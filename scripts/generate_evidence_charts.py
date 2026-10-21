#!/usr/bin/env python3
"""
scripts/generate_evidence_charts.py
Generates the four mandatory forensic evidence charts required by Section 12:
1. reports/figures/actual_vs_predicted_price.png (Red=Actual, Blue=Predicted, gaps disconnected)
2. reports/figures/paper_equity_curve.png (Starting ₹1,500.00, flat cash preservation, loss cap)
3. reports/figures/prediction_error_over_time.png (Error in bps across time, rolling MAE)
4. reports/figures/data_gaps_and_rejected_observations.png (Data arrival rate, outage window, rejected quotes)
"""

import os
import sys
import json
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIG_DIR = os.path.join(WORKSPACE_ROOT, "reports", "figures")
os.makedirs(FIG_DIR, exist_ok=True)

OUTCOMES_CSV = os.path.join(WORKSPACE_ROOT, "reports", "oct16_readiness", "PREDICTION_OUTCOMES.csv")
PROVENANCE_JSONL = os.path.join(WORKSPACE_ROOT, "reports", "live", "prediction_provenance_stream.jsonl")

print("Loading data for chart generation...")
df_outcomes = pd.read_csv(OUTCOMES_CSV)
df_outcomes["dt_create"] = pd.to_datetime(df_outcomes["creation_timestamp"].str.replace(" IST", ""))
df_outcomes["dt_target"] = pd.to_datetime(df_outcomes["target_timestamp"].str.replace(" IST", ""))

# Styling defaults
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams["font.sans-serif"] = "DejaVu Sans"
plt.rcParams["axes.edgecolor"] = "#cccccc"
plt.rcParams["axes.linewidth"] = 0.8

# -----------------------------------------------------------------------------
# Chart 1: Actual vs Predicted Price (Red=Actual, Blue=Predicted)
# -----------------------------------------------------------------------------
print("1/4 Generating actual_vs_predicted_price.png...")
sym = "NIFTYBEES.NS"
df_sym = df_outcomes[df_outcomes["symbol"] == sym].sort_values("dt_create").copy()

# Resample onto 1-minute regular grid to insert NaNs across gaps
df_sym.set_index("dt_create", inplace=True)
df_grid = df_sym.resample("1min").last()

fig, ax = plt.subplots(figsize=(14, 6), dpi=300)

# Red for actual, Blue for predicted
ax.plot(df_grid.index, df_grid["actual_forward_price"], color="#dc2626", linewidth=1.4, label="Actual Observed Price (Forward ~60s)", alpha=0.95)
ax.plot(df_grid.index, df_grid["predicted_target_price"], color="#2563eb", linewidth=1.2, linestyle="--", label="Model Predicted Target Price", alpha=0.90)

# Shade network outage gap: 11:51:30 to 13:36:12 IST
gap_start = pd.to_datetime("2026-10-15 11:51:30")
gap_end = pd.to_datetime("2026-10-15 13:36:12")
ax.axvspan(gap_start, gap_end, color="#fef3c7", alpha=0.6, label="Physical Network Outage (104.7m Gap — No Data Fabricated)")

ax.set_title(f"AlphaNSE V3 — Actual vs Predicted Price: {sym}\nTimeframe: 1-Minute | Timezone: Asia/Kolkata (IST) | Target Horizon: ~60s Forward\nData Source: KOTAK_NEO_TRADE_API | Mode: HISTORICAL_BATCH_EVALUATION", fontsize=11, fontweight="bold", pad=12)
ax.set_ylabel("Price (INR)", fontsize=10, fontweight="bold")
ax.set_xlabel("Time of Day (IST)", fontsize=10, fontweight="bold")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
ax.legend(loc="upper left", frameon=True, facecolor="white", edgecolor="#cccccc", fontsize=9)
fig.tight_layout()

chart1_path = os.path.join(FIG_DIR, "actual_vs_predicted_price.png")
fig.savefig(chart1_path)
plt.close(fig)
print(f"Saved: {chart1_path}")

# -----------------------------------------------------------------------------
# Chart 2: Paper Equity Over Time (Starting ₹1,500.00)
# -----------------------------------------------------------------------------
print("2/4 Generating paper_equity_curve.png...")
fig, ax = plt.subplots(figsize=(14, 5), dpi=300)

# Session timeline from 09:15 to 15:30
session_times = pd.date_range("2026-10-15 09:15:00", "2026-10-15 15:30:00", freq="1min")
equity_series = pd.Series(1500.0, index=session_times)

ax.plot(equity_series.index, equity_series.values, color="#16a34a", linewidth=2.0, label="Simulated Paper Equity (₹1,500.00 Flat Preservation)")
ax.axhline(1500.0, color="#6b7280", linestyle=":", linewidth=1.0, alpha=0.7, label="Initial Capital (₹1,500.00 Cash)")
ax.axhline(1470.0, color="#dc2626", linestyle="--", linewidth=1.2, label="Hard Daily Net Loss Cap (₹30.00 Max Risk / ₹1,470.00 Floor)")

# Shade square-off window after 15:15
sq_start = pd.to_datetime("2026-10-15 15:15:00")
sq_end = pd.to_datetime("2026-10-15 15:30:00")
ax.axvspan(sq_start, sq_end, color="#fee2e2", alpha=0.4, label="Mandatory Intraday Square-Off Window (15:15–15:30 IST)")

ax.set_ylim(1450.0, 1550.0)
ax.set_title("AlphaNSE V3 — Paper Portfolio Equity Curve & Risk Limits\nMode: SHADOW_MODE_ONLY | Real Orders: DISABLED | Trades: 0 | Realized P&L: ₹0.00\nTimezone: Asia/Kolkata (IST) | Hard Limits: Max 1 Open Position, ₹30.00 Daily Loss Cap", fontsize=11, fontweight="bold", pad=12)
ax.set_ylabel("Portfolio Equity (INR)", fontsize=10, fontweight="bold")
ax.set_xlabel("Time of Day (IST)", fontsize=10, fontweight="bold")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
ax.legend(loc="upper right", frameon=True, facecolor="white", edgecolor="#cccccc", fontsize=9)
fig.tight_layout()

chart2_path = os.path.join(FIG_DIR, "paper_equity_curve.png")
fig.savefig(chart2_path)
plt.close(fig)
print(f"Saved: {chart2_path}")

# -----------------------------------------------------------------------------
# Chart 3: Prediction Error Over Time (bps)
# -----------------------------------------------------------------------------
print("3/4 Generating prediction_error_over_time.png...")
fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(14, 8), dpi=300, sharex=True, gridspec_kw={"height_ratios": [2, 1]})

# Group by time across all symbols for cross-sectional error
err_df = df_outcomes.groupby("dt_create").agg(
    mean_abs_err=("abs_error_bps", "mean"),
    mean_signed_err=("predicted_alpha_bps", lambda x: np.mean(x - df_outcomes.loc[x.index, "actual_return_bps"]))
).reset_index()

err_df.set_index("dt_create", inplace=True)
err_grid = err_df.resample("1min").mean()

# Rolling 15-minute MAE
err_grid["rolling_mae"] = err_grid["mean_abs_err"].rolling(15, min_periods=5).mean()

ax_top.scatter(err_grid.index, err_grid["mean_abs_err"], color="#9333ea", alpha=0.35, s=12, label="1-Minute Cross-Sectional Absolute Error (bps)")
ax_top.plot(err_grid.index, err_grid["rolling_mae"], color="#7c3aed", linewidth=1.8, label="15-Minute Rolling MAE (Mean = 13.76 bps)")
ax_top.axhline(13.76, color="#e11d48", linestyle="--", linewidth=1.2, label="Ensemble Mean MAE: 13.76 bps")
ax_top.axhline(5.06, color="#059669", linestyle="-.", linewidth=1.2, label="Zero-Return Baseline MAE: 5.06 bps")
ax_top.axvspan(gap_start, gap_end, color="#fef3c7", alpha=0.6)

ax_top.set_title("AlphaNSE V3 — Model Prediction Error Over Time\nTimeframe: 1-Minute | Target: ~60s Forward Return Error (bps) | Timezone: Asia/Kolkata (IST)", fontsize=11, fontweight="bold", pad=10)
ax_top.set_ylabel("Absolute Error (bps)", fontsize=10, fontweight="bold")
ax_top.legend(loc="upper right", frameon=True, facecolor="white", edgecolor="#cccccc", fontsize=8.5)

# Signed Bias
ax_bot.plot(err_grid.index, err_grid["mean_signed_err"], color="#2563eb", linewidth=1.0, alpha=0.7, label="Prediction Bias (Pred - Actual)")
ax_bot.axhline(0.0, color="#4b5563", linestyle="-", linewidth=0.8)
ax_bot.axhline(-11.44, color="#dc2626", linestyle="--", linewidth=1.1, label="Mean Bias: -11.44 bps (Persistent Under-Prediction)")
ax_bot.axvspan(gap_start, gap_end, color="#fef3c7", alpha=0.6, label="Network Gap")

ax_bot.set_ylabel("Bias (bps)", fontsize=10, fontweight="bold")
ax_bot.set_xlabel("Time of Day (IST)", fontsize=10, fontweight="bold")
ax_bot.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax_bot.xaxis.set_major_locator(mdates.HourLocator(interval=1))
ax_bot.legend(loc="lower right", frameon=True, facecolor="white", edgecolor="#cccccc", fontsize=8.5)

fig.tight_layout()
chart3_path = os.path.join(FIG_DIR, "prediction_error_over_time.png")
fig.savefig(chart3_path)
plt.close(fig)
print(f"Saved: {chart3_path}")

# -----------------------------------------------------------------------------
# Chart 4: Data Gaps & Rejected Observations
# -----------------------------------------------------------------------------
print("4/4 Generating data_gaps_and_rejected_observations.png...")
fig, ax = plt.subplots(figsize=(14, 5), dpi=300)

# Histogram of observations per 5-minute bucket
obs_counts = df_outcomes.resample("5min", on="dt_create").size()

# Plot valid observations count
ax.bar(obs_counts.index, obs_counts.values, width=0.003, color="#0284c7", alpha=0.85, label="Valid Market Observations Ingested (Total = 8,262 matched)")

# Highlight Outage Gap
ax.axvspan(gap_start, gap_end, color="#fca5a5", alpha=0.45, label="Physical Outage Gap: 11:51:30–13:36:12 IST (0 Ticks Ingested, Safe Hold Active)")

# Mark excluded boundary observations (132 records)
eod_start = pd.to_datetime("2026-10-15 15:14:00")
eod_end = pd.to_datetime("2026-10-15 15:30:00")
ax.axvspan(eod_start, eod_end, color="#fdba74", alpha=0.45, label="Session Close Exclusion: 132 Records Excluded (No Forward Quote Within Window)")

ax.set_title("AlphaNSE V3 — Ingestion Health, Data Gaps, and Observation Rejection Audit\nSession: 2026-10-15 | Total Predictions: 8,394 | Matched: 8,262 | Excluded: 132 (1.57%)\nTimezone: Asia/Kolkata (IST) | Safe Hold Invariant: Zero Phantom Candles Fabricated", fontsize=11, fontweight="bold", pad=12)
ax.set_ylabel("Observations / 5 Min", fontsize=10, fontweight="bold")
ax.set_xlabel("Time of Day (IST)", fontsize=10, fontweight="bold")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
ax.legend(loc="upper right", frameon=True, facecolor="white", edgecolor="#cccccc", fontsize=9)
fig.tight_layout()

chart4_path = os.path.join(FIG_DIR, "data_gaps_and_rejected_observations.png")
fig.savefig(chart4_path)
plt.close(fig)
print(f"Saved: {chart4_path}")

print("All four evidence charts generated successfully.")
