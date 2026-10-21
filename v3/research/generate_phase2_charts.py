import os
import sys
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ARTIFACT_DIR = r"C:\Users\sumuk\.gemini\antigravity-ide\brain\ae1836cb-3969-43d0-a098-e3cd7e77b9d5"
os.makedirs(ARTIFACT_DIR, exist_ok=True)
REPORTS_DIR = os.path.join(WORKSPACE_ROOT, "reports", "live")
os.makedirs(REPORTS_DIR, exist_ok=True)

# Set style
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams["font.sans-serif"] = "DejaVu Sans"
plt.rcParams["font.size"] = 10

# Load report JSON
with open(os.path.join(REPORTS_DIR, "phase2_cost_aware_research_report.json")) as f:
    rep = json.load(f)

# -------------------------------------------------------------
# Chart 1: Horizon Volatility & Friction Hurdle Comparison
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 6), dpi=300)

horizons = ["1-Min\n(Sprint 1)", "5-Min\n(Discrete)", "10-Min\n(Discrete)", "15-Min\n(Discrete)"]
# 1m baseline from Sprint 1: mean ~4.1 bps, p90 ~9.2 bps
mean_moves = [4.12, rep["prediction_metrics_by_horizon"]["5"]["mean_move_bps"],
              rep["prediction_metrics_by_horizon"]["10"]["mean_move_bps"],
              rep["prediction_metrics_by_horizon"]["15"]["mean_move_bps"]]

p90_moves = [9.20, rep["prediction_metrics_by_horizon"]["5"]["p90_move_bps"],
             rep["prediction_metrics_by_horizon"]["10"]["p90_move_bps"],
             rep["prediction_metrics_by_horizon"]["15"]["p90_move_bps"]]

x = np.arange(len(horizons))
width = 0.35

rects1 = ax.bar(x - width/2, mean_moves, width, label="Mean Absolute Move (bps)", color="#3b82f6", alpha=0.85)
rects2 = ax.bar(x + width/2, p90_moves, width, label="90th Percentile Move (bps)", color="#1d4ed8", alpha=0.95)

# Horizontal lines for frictions
ax.axhline(8.54, color="#e11d48", linestyle="--", linewidth=1.8, label="Realistic Kotak Neo Friction (8.54 bps)")
ax.axhline(14.70, color="#b91c1c", linestyle="-.", linewidth=1.8, label="Conservative Audit Friction (14.70 bps)")

ax.set_ylabel("Price Movement Amplitude (Basis Points / bps)", fontsize=11, fontweight="bold")
ax.set_title("AlphaNSE V3 — Multi-Horizon Price Amplitude vs Cost Hurdles\nExpansion of Gross Movement Window Across Discrete Time Horizons", fontsize=12, fontweight="bold", pad=14)
ax.set_xticks(x)
ax.set_xticklabels(horizons, fontsize=10, fontweight="bold")
ax.legend(loc="upper left", frameon=True, framealpha=0.9)
ax.set_ylim(0, 42)

for bar in rects1:
    h = bar.get_height()
    ax.annotate(f"{h:.1f} bp",
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 3), textcoords="offset points",
                ha="center", va="bottom", fontsize=9, fontweight="bold")

for bar in rects2:
    h = bar.get_height()
    ax.annotate(f"{h:.1f} bp",
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 3), textcoords="offset points",
                ha="center", va="bottom", fontsize=9, fontweight="bold", color="#1e3a8a")

# Annotation text box
ax.text(0.68, 0.45, "15m Horizon expands P90 amplitude to 34.7 bp\n(4.1x realistic Kotak Neo friction)\nOpening physical opportunity for alpha",
        transform=ax.transAxes, fontsize=9, bbox=dict(boxstyle="round,pad=0.5", facecolor="#eff6ff", edgecolor="#93c5fd"))

plt.tight_layout()
chart1_path_art = os.path.join(ARTIFACT_DIR, "phase2_horizon_volatility_comparison.png")
chart1_path_rep = os.path.join(REPORTS_DIR, "phase2_horizon_volatility_comparison.png")
plt.savefig(chart1_path_art)
plt.savefig(chart1_path_rep)
plt.close()

# -------------------------------------------------------------
# Chart 2: Predictive Metrics by Horizon (Dir Acc & Rank IC)
# -------------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5), dpi=300)

horiz_labels = ["5-Minute", "10-Minute", "15-Minute"]
models_to_plot = ["Stationary Ridge", "Shallow LightGBM", "Persistence Baseline"]

# Directional Accuracy Plot
for mod_name, color, marker in [("Shallow LightGBM", "#10b981", "o"), ("Stationary Ridge", "#6366f1", "s"), ("Persistence Baseline", "#94a3b8", "^")]:
    accs = []
    ci_err_low = []
    ci_err_high = []
    for h in ["5", "10", "15"]:
        mod = next(m for m in rep["prediction_metrics_by_horizon"][h]["models"] if mod_name in m["name"])
        accs.append(mod["dir_acc_pct"])
        ci_err_low.append(mod["dir_acc_pct"] - mod["dir_acc_ci_95"][0])
        ci_err_high.append(mod["dir_acc_ci_95"][1] - mod["dir_acc_pct"])
    ax1.errorbar(horiz_labels, accs, yerr=[ci_err_low, ci_err_high], label=mod_name, color=color, marker=marker, linewidth=2, capsize=5, markersize=7)

ax1.axhline(50.0, color="#ef4444", linestyle=":", linewidth=1.5, label="50.0% Coin Flip")
ax1.axhline(52.0, color="#10b981", linestyle="--", linewidth=1.5, label="Gate 1 Threshold (52.0%)")
ax1.set_ylabel("Directional Accuracy (%) [95% Wilson CI]", fontsize=10, fontweight="bold")
ax1.set_title("Directional Accuracy by Horizon (Unseen OOS Test)", fontsize=11, fontweight="bold")
ax1.set_ylim(45, 58)
ax1.legend(loc="upper left", frameon=True, fontsize=8.5)

# Rank IC Plot
for mod_name, color, marker in [("Shallow LightGBM", "#10b981", "o"), ("Stationary Ridge", "#6366f1", "s"), ("Persistence Baseline", "#94a3b8", "^")]:
    ics = []
    for h in ["5", "10", "15"]:
        mod = next(m for m in rep["prediction_metrics_by_horizon"][h]["models"] if mod_name in m["name"])
        ics.append(mod["rank_ic"])
    ax2.plot(horiz_labels, ics, label=mod_name, color=color, marker=marker, linewidth=2, markersize=7)

ax2.axhline(0.0, color="#ef4444", linestyle=":", linewidth=1.5, label="Zero Correlation")
ax2.axhline(0.030, color="#10b981", linestyle="--", linewidth=1.5, label="Gate 2 Threshold (+0.030 IC)")
ax2.set_ylabel("Rank Information Coefficient (Spearman IC)", fontsize=10, fontweight="bold")
ax2.set_title("Rank IC by Horizon (Unseen OOS Test)", fontsize=11, fontweight="bold")
ax2.set_ylim(-0.05, 0.10)
ax2.legend(loc="upper left", frameon=True, fontsize=8.5)

plt.tight_layout()
chart2_path_art = os.path.join(ARTIFACT_DIR, "phase2_candidate_metrics_by_horizon.png")
chart2_path_rep = os.path.join(REPORTS_DIR, "phase2_candidate_metrics_by_horizon.png")
plt.savefig(chart2_path_art)
plt.savefig(chart2_path_rep)
plt.close()

# -------------------------------------------------------------
# Chart 3: Cost Decomposition Breakdown (Kotak Neo vs Traditional Broker)
# -------------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5), dpi=300)

labels = ["STT\n(2.5 bps)", "Exchange\n(0.61 bps)", "Stamp Duty\n(0.30 bps)", "SEBI+GST\n(0.13 bps)", "Spread+Slip\n(5.00 bps)"]
sizes = [2.50, 0.61, 0.30, 0.13, 5.00]
colors = ["#f59e0b", "#3b82f6", "#8b5cf6", "#ec4899", "#10b981"]

wedges, texts, autotexts = ax1.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=140, colors=colors, textprops=dict(fontsize=9, fontweight="bold"))
ax1.set_title("Kotak Neo Trade Free Friction Decomposition\nTotal Friction = 8.54 bps (Rs. 1.28 on Rs. 1,500 trade)", fontsize=11, fontweight="bold")

# Comparison bar: Kotak Neo vs Traditional Flat Brokerage (Rs. 20/order)
broker_types = ["Kotak Neo\nTrade Free", "Traditional Flat Fee\n(Rs. 20/order)"]
friction_bps = [8.54, 8.54 + (40.0 / 1500.0) * 10000.0]  # Rs. 40 roundtrip = 266.67 bps
bars = ax2.bar(broker_types, friction_bps, color=["#10b981", "#ef4444"], width=0.45)
ax2.set_ylabel("Roundtrip Cost (Basis Points)", fontsize=10, fontweight="bold")
ax2.set_title("Economic Viability on Rs. 1,500 Capital\nKotak Neo Zero Brokerage vs Retail Flat Fee", fontsize=11, fontweight="bold")
for b in bars:
    y = b.get_height()
    ax2.annotate(f"{y:.1f} bps\n(Rs. {y*1500/10000:.2f})",
                 xy=(b.get_x() + b.get_width() / 2, y),
                 xytext=(0, 4), textcoords="offset points",
                 ha="center", va="bottom", fontsize=10, fontweight="bold")
ax2.set_ylim(0, 320)

plt.tight_layout()
chart3_path_art = os.path.join(ARTIFACT_DIR, "phase2_cost_decomposition_breakdown.png")
chart3_path_rep = os.path.join(REPORTS_DIR, "phase2_cost_decomposition_breakdown.png")
plt.savefig(chart3_path_art)
plt.savefig(chart3_path_rep)
plt.close()

print("Successfully generated all 3 Phase 2 visual charts in artifacts and reports directory.")
