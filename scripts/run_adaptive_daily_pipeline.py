"""
AlphaNSE V2 — Adaptive Daily Retraining & Trading CLI Runner.
Executes the pre-market retraining, sanity validation, model freezing,
and sequential intraday session trading across unseen chronological market days.
"""

import os
import sys
import glob
import argparse
import logging
from datetime import datetime, date
import pandas as pd

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from v2.adaptive.daily_pipeline import AdaptiveDailyPipeline, DailySessionResult
from v2.adaptive.audit_ledger import AuditLedger

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def generate_report_markdown(results: list[DailySessionResult], output_path: str = "ADAPTIVE_PIPELINE_REPORT.md") -> str:
    """
    Generates a quantitative audit report of the adaptive daily pipeline performance.
    """
    total_trades = sum(r.total_trades for r in results)
    total_net_pnl = sum(r.net_pnl_rupees for r in results)
    avg_profit_per_trade = (total_net_pnl / total_trades) if total_trades > 0 else 0.0
    wins = sum(sum(1 for t in r.trades if t.net_pnl_rupees > 0) for r in results)
    overall_win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0

    lines = [
        "# ALPHANSE V2 — ADAPTIVE DAILY RETRAINING & TRADING REPORT",
        "",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}  ",
        f"**Sessions Evaluated**: {len(results)}  ",
        f"**Capital Router**: 🔒 STRICTLY LOCKED  ",
        f"**Live Execution**: 🔒 PHYSICALLY DISABLED (`LiveExecutionDisabledError`)  ",
        "",
        "---",
        "",
        "## 1. Executive Performance Summary",
        "",
        "| Metric | Target Standard | Observed Result | Status |",
        "| :--- | :---: | :---: | :---: |",
        f"| **Average Net Profit / Trade** | $\\ge ₹0.80$ | **₹{avg_profit_per_trade:.2f}** | {'✅ PASS' if avg_profit_per_trade >= 0.80 else '❌ FAIL'} |",
        f"| **Total Evaluated Trades** | $\\ge 30$ / day | **{total_trades}** ({total_trades / len(results):.1f} / day) | {'✅ PASS' if total_trades >= 30 * len(results) else '🔄 ACCUMULATING'} |",
        f"| **Directional Win Rate** | $> 51.5\\%$ | **{overall_win_rate:.1f}%** | {'✅ PASS' if overall_win_rate >= 51.5 else '❌ FAIL'} |",
        f"| **Cumulative Net PnL (₹5k Portfolio)** | $> ₹0.00$ | **₹{total_net_pnl:.2f}** | {'✅ PASS' if total_net_pnl > 0 else '❌ FAIL'} |",
        "",
        "---",
        "",
        "## 2. Session-by-Session Adaptive Retraining Ledger",
        "",
        "| Session Date | Model Version | Regime at Open | Pre-Market Cutoff | Trades | Net PnL (₹) | Avg Profit/Trade | Win Rate | Ending Capital |",
        "| :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: |"
    ]

    for r in results:
        lines.append(
            f"| **{r.session_date}** | `{r.manifest.model_version}` | `{r.manifest.regime_at_open}` | "
            f"`{r.manifest.data_cutoff.split('T')[0]}` | {r.total_trades} | ₹{r.net_pnl_rupees:+.2f} | "
            f"₹{r.avg_net_profit_per_trade_rupees:+.2f} | {r.win_rate_pct:.1f}% | ₹{r.ending_capital:.2f} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Cryptographic Model & Lineage Audit Manifest",
        "",
        "Every session retrains strictly on data available prior to market open, freezing a verifiable model:",
        "",
        "| Session | Model Hash (SHA-256) | Dataset Hash (SHA-256) | Training Rows | Val IC |",
        "| :--- | :--- | :--- | :---: | :---: |"
    ])

    for r in results:
        m = r.manifest
        lines.append(
            f"| `{m.session_date}` | `{m.model_hash[:20]}...` | `{m.dataset_hash[:20]}...` | "
            f"{m.training_rows} | {m.validation_result.get('val_ic', 0.0):.4f} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 4. Methodological Invariants Enforced",
        "",
        "1. **Zero Lookahead Guarantee**: For every session Day D, training data strictly ends at Day D-1 15:25 IST.",
        "2. **Pre-Market Model Freezing**: Model weights are frozen prior to market open and remain unchanged during intraday trading.",
        "3. **Dynamic Cost Realism**: All trades account for Zerodha statutory taxes (STT, stamp duty, turnover charges, SEBI, GST), half-spread, and impact slippage.",
        "4. **Integer Position Sizing**: Whole shares sized dynamically on ₹5,000 cash balance via `IntegerPositionSizer`.",
        "",
        "---",
        "*Report generated autonomously by AlphaNSE V2 Adaptive Daily Pipeline Engine.*",
        ""
    ])

    report_text = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    logger.info(f"Report written to: {output_path}")
    return report_text


def main():
    parser = argparse.ArgumentParser(description="AlphaNSE V2 Adaptive Daily Retraining & Trading CLI")
    parser.add_argument("--day", type=str, help="Specific session date (YYYY-MM-DD)")
    parser.add_argument("--walk-forward", action="store_true", help="Run multi-day adaptive walk-forward across fresh sessions")
    parser.add_argument("--capital", type=float, default=5000.0, help="Initial portfolio capital in INR")
    parser.add_argument("--report", action="store_true", default=True, help="Generate ADAPTIVE_PIPELINE_REPORT.md")
    args = parser.parse_args()

    pipeline = AdaptiveDailyPipeline(initial_capital=args.capital)

    if args.walk_forward:
        # Discover all fresh sessions in storage
        pattern = os.path.join("v2", "data", "storage", "fresh", "session_*_5m.parquet")
        files = sorted(glob.glob(pattern))
        session_dates = []
        for f in files:
            bname = os.path.basename(f)
            dstr = bname.replace("session_", "").replace("_5m.parquet", "")
            try:
                dt = datetime.strptime(dstr, "%Y%m%d").date()
                session_dates.append(dt)
            except ValueError:
                continue

        if not session_dates:
            logger.error("No fresh session files found in v2/data/storage/fresh/!")
            return 1

        results = pipeline.run_walk_forward(session_dates)

    elif args.day:
        target_dt = datetime.strptime(args.day, "%Y-%m-%d").date()
        results = [pipeline.run_day(target_dt)]

    else:
        logger.error("Must specify either --day YYYY-MM-DD or --walk-forward")
        return 1

    if args.report:
        generate_report_markdown(results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
