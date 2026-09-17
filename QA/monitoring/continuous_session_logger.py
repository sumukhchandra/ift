"""
Continuous Background Session & Prediction Monitor.

Runs quietly in the background alongside the FastAPI server:
- Logs session transitions (Standby -> Live NSE Market Open at 09:15 AM IST).
- Records compounding equity, win rate, daily trades, and active positions.
- Tracks prediction verification metrics (exact value reached %, direction accuracy, MAE).
- Appends logs to QA/logs/live_metrics/market_session_monitor.log
- Updates live status snapshot in QA/logs/live_metrics/session_summary.json
"""

import os
import sys
import time
import json
import requests
from datetime import datetime

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs", "live_metrics")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "market_session_monitor.log")
SNAPSHOT_FILE = os.path.join(LOG_DIR, "session_summary.json")

def write_log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def main():
    write_log("Starting Continuous Background Session Monitor for AlphaNSE...")
    write_log(f"Target Server: {BASE_URL}")

    last_market_mode = None

    while True:
        try:
            r_health = requests.get(f"{BASE_URL}/api/health", timeout=10)
            if r_health.status_code != 200:
                write_log(f"[WARN] Health check returned status {r_health.status_code}")
                time.sleep(15)
                continue

            r_state = requests.get(f"{BASE_URL}/api/state", timeout=10).json()
            r_verif = requests.get(f"{BASE_URL}/api/predictions/verification?limit=10", timeout=10).json()
            r_mkt = requests.get(f"{BASE_URL}/api/market-status", timeout=10).json()

            market_mode = r_mkt.get("market_mode", "UNKNOWN")
            is_open = r_mkt.get("is_open", False)

            # Detect transition into live market hours
            if market_mode != last_market_mode:
                if is_open:
                    write_log("🚨 [MARKET SESSION OPEN] Indian Stock Market (NSE) is LIVE! Real-time 1m tick trading active.")
                else:
                    write_log(f"ℹ️ [MARKET STANDBY] Mode: {market_mode}. Next session: {r_mkt.get('next_market_open', 'N/A')}")
                last_market_mode = market_mode

            acc = r_verif.get("accuracy", {})
            total_cap = r_state.get("total_capital", 0.0)
            trades_count = r_state.get("daily_trades_count", 0)
            win_rate = r_state.get("win_rate_pct", 0.0)
            open_pos = list(r_state.get("positions", {}).keys())

            log_entry = (
                f"Status: {r_state.get('engine_status')} | "
                f"Equity: INR {total_cap:,.2f} | "
                f"Trades: {trades_count} | "
                f"WinRate: {win_rate}% | "
                f"Positions: {open_pos} | "
                f"ExactHits: {acc.get('exact_range_hit_rate_pct', 0)}% ({acc.get('exact_range_hits', 0)}/{acc.get('total_verified', 0)}) | "
                f"DirAcc: {acc.get('direction_accuracy_pct', 0)}% | "
                f"MAE: {acc.get('mean_abs_return_error_pct', 0)}%"
            )
            write_log(log_entry)

            # Save snapshot for external inspection
            snapshot = {
                "updated_at": datetime.now().isoformat(),
                "market_status": r_mkt,
                "portfolio": {
                    "total_capital": total_cap,
                    "available_capital": r_state.get("available_capital", 0.0),
                    "invested_capital": r_state.get("invested_capital", 0.0),
                    "total_net_profit": r_state.get("total_net_profit", 0.0),
                    "daily_trades_count": trades_count,
                    "win_rate_pct": win_rate,
                    "open_positions": open_pos
                },
                "prediction_accuracy": acc,
                "latest_verifications": r_verif.get("verifications", [])[-5:]
            }
            with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)

        except Exception as e:
            write_log(f"[ERROR] Exception in monitoring cycle: {e}")

        time.sleep(30)

if __name__ == "__main__":
    main()
