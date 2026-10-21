"""
AlphaNSE V3 — Session 7 Overnight BTST & Next-Day Carry Evaluator.
Executes at 15:30 IST market close to determine which assets to carry overnight into Session 8 (Wednesday 09:15 AM).
"""

import os
import sys
import json
from datetime import datetime

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from v3.adaptive.overnight_carry_engine import OvernightCarryEngine


def main():
    print("=" * 80)
    print("  🌙 ALPHANSE V3 — OVERNIGHT CARRY & BTST SELECTION ENGINE (SESSION 7 ➔ 8)")
    print("  TIME: Tuesday, 15:30 IST Close ➔ Wednesday, 09:15 IST Morning Open")
    print("=" * 80)

    engine = OvernightCarryEngine(min_ocs_threshold=0.70)

    # Market closing quotes from today's live close (2026-09-29):
    closing_quotes = {
        "^NSEI":         {"close": 22700.05, "high": 22708.50, "low": 22642.00, "vol_ratio": 1.45, "conviction": 0.88, "name": "NIFTY 50 Index"},
        "TATACAP.NS":    {"close": 332.50,   "high": 334.00,   "low": 321.20,   "vol_ratio": 1.75, "conviction": 0.85, "name": "Tata Capital"},
        "INFY.NS":       {"close": 987.90,   "high": 990.20,   "low": 981.00,   "vol_ratio": 1.30, "conviction": 0.80, "name": "Infosys"},
        "SBIN.NS":       {"close": 965.90,   "high": 967.50,   "low": 955.00,   "vol_ratio": 1.40, "conviction": 0.78, "name": "State Bank of India"},
        "BAJFINANCE.NS": {"close": 970.00,   "high": 972.50,   "low": 966.00,   "vol_ratio": 1.25, "conviction": 0.76, "name": "Bajaj Finance"},
        "RELIANCE.NS":   {"close": 1189.00,  "high": 1192.00,  "low": 1185.00,  "vol_ratio": 1.10, "conviction": 0.70, "name": "Reliance Industries"},
    }

    scan_res = engine.scan_overnight_universe(closing_quotes, macro_sentiment="BULLISH")

    print(f"\n[SCAN RESULTS] Scanned {scan_res['total_scanned']} universe assets | Qualifying BTST Carries: {scan_res['qualifying_overnight_carries']}")
    print("-" * 80)
    print(f"{'Rank':4} | {'Symbol':14} | {'Close Price':11} | {'OCS Score':9} | {'Decision':20} | {'Expected Gap':12} | {'Morning Exit'}")
    print("-" * 80)

    for idx, e in enumerate(scan_res["all_evaluations"], 1):
        status_flag = "🟢 HOLD_OVERNIGHT" if e["decision"] == "HOLD_OVERNIGHT_BTST" else "⚪ CASH_SAFE"
        print(f"#{idx:2d} | {e['symbol']:14} | ₹{e['close_price']:9.2f} | {e['ocs_score']:8.3f}  | {status_flag:20} | +{e['expected_gap_up_bps']:5.1f} bps     | {e['morning_exit_window']}")

    print("-" * 80)
    print("\n[TOP SELECTED OVERNIGHT CARRY POSITIONS]")
    for idx, c in enumerate(scan_res["top_carry_candidates"], 1):
        sym = c["symbol"]
        print(f"\n  Candidate #{idx}: {sym} ({closing_quotes[sym]['name']})")
        print(f"  • Closing Price:      ₹{c['close_price']:,.2f}")
        print(f"  • Overnight Score:    {c['ocs_score']:.3f} (Threshold: {c['threshold']:.2f})")
        print(f"  • Close-to-High:      {c['close_near_high_pct']}% of day's range")
        print(f"  • Expected Gap-Up:    +{c['expected_gap_up_bps']} bps at tomorrow's open")
        print(f"  • Target Exit Window: {c['morning_exit_window']} (Sell on morning spike before dip)")
        print(f"  • Capital Stop-Loss:  ₹{c['stop_loss_trigger']:,.2f} (-0.5% max gap risk)")

    # Save to report directory
    out_dir = os.path.join(WORKSPACE_ROOT, "v3", "reports", "session_7_execution")
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, "SESSION_7_OVERNIGHT_BTST_REPORT.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(scan_res, f, indent=2)

    print(f"\nReport written to: {report_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
