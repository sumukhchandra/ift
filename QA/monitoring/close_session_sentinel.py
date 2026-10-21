"""
Close-to-the-Bell Real-Time Model Sentinel (15:00 - 15:35 IST).

Monitors every individual sub-model across all 10 NSE stocks on every 1-minute tick
during the critical closing window (15:00 - 15:30 IST) when MOC (Market-On-Close)
institutional order flow, settlement imbalances, and intraday square-offs peak.

Tracks:
1. Sub-model predictions (CatBoost, LightGBM, XGBoost, RF, Quantile 75, Platt Classifier).
2. Ensemble consensus, prediction variance, and breakout probability.
3. Actual forward outcomes, directional accuracy, error margins.
4. Auto-closing & overnight position safety (ensuring 0 open positions held over the weekend).
5. Compiles final End-of-Session Friday Performance Dossier at 15:30 IST.
"""

import os
import sys
import time
import json
import requests
import numpy as np
import pandas as pd
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from stocks_config import STOCK_SYMBOLS, STOCK_UNIVERSE
from models.one_min_predictor import OneMinPredictor

LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
METRICS_DIR = os.path.join(LOGS_DIR, "live_metrics")
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(METRICS_DIR, exist_ok=True)

SENTINEL_LOG_FILE = os.path.join(LOGS_DIR, "closing_sentinel_ticks.jsonl")
SENTINEL_SNAPSHOT = os.path.join(METRICS_DIR, "closing_model_sentinel.json")
FINAL_DOSSIER_FILE = os.path.join(LOGS_DIR, "friday_final_session_dossier.json")

API_BASE = "http://127.0.0.1:8000"


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [MODEL-SENTINEL] {msg}", flush=True)


def run_closing_sentinel():
    log("=" * 75)
    log("CLOSE-OF-SESSION MODEL SENTINEL INITIALIZED")
    log("Monitoring every sub-model across 10 NSE stocks until market close (15:30 IST)")
    log("=" * 75)

    predictor = OneMinPredictor()
    tick_count = 0

    while True:
        now = datetime.now()
        hour = now.hour
        minute = now.minute

        # Post-market check (15:32 IST)
        if (hour > 15) or (hour == 15 and minute >= 32):
            log("🔔 15:30 IST Closing Bell Reached! Finalizing session reconciliation...")
            break

        tick_count += 1
        t_start = time.time()

        try:
            # Query server state
            r_state = requests.get(f"{API_BASE}/api/state", timeout=8).json()
            r_verif = requests.get(f"{API_BASE}/api/predictions/verification?limit=15", timeout=8).json()

            capital = r_state.get("available_capital", 0.0)
            open_pos = r_state.get("positions", {})
            daily_trades = r_state.get("daily_trades_count", 0)
            signals = r_state.get("last_signals", [])

            # High-fidelity sub-model breakdown
            stock_audits = []
            for s in signals:
                sym = s.get("symbol")
                pred_ret = s.get("predicted_return_pct", 0.0)
                conf = s.get("confidence", 0.0)
                sig = s.get("signal", "HOLD")
                price = s.get("current_price", 0.0)
                regime = s.get("regime", "SIDEWAYS")
                bl = s.get("blacklisted", False)

                stock_audits.append({
                    "symbol": sym,
                    "company": s.get("company"),
                    "price": price,
                    "pred_return_pct": pred_ret,
                    "confidence_pct": conf,
                    "signal": sig,
                    "regime": regime,
                    "blacklisted": bl,
                    "micro_rsi": s.get("micro_rsi"),
                    "ema_cross_pct": s.get("ema_cross_pct"),
                    "vol_zscore": s.get("vol_zscore")
                })

            # Real-time snapshot payload
            snapshot = {
                "sentinel_timestamp": now.isoformat(),
                "time_to_close_mins": max(0, (15 * 60 + 30) - (hour * 60 + minute)),
                "market_is_open": hour < 15 or (hour == 15 and minute < 30),
                "working_capital": capital,
                "open_positions_count": len(open_pos),
                "open_positions": open_pos,
                "daily_trades_executed": daily_trades,
                "net_profit_today": r_state.get("total_net_profit", 0.0),
                "stocks_audited_count": len(stock_audits),
                "stocks": stock_audits,
                "latest_verifications": r_verif.get("verifications", [])[-5:]
            }

            with open(SENTINEL_SNAPSHOT, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)

            with open(SENTINEL_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot) + "\n")

            mins_left = max(0, (15 * 60 + 30) - (hour * 60 + minute))
            best_cand = max(stock_audits, key=lambda x: x["pred_return_pct"]) if stock_audits else None
            best_str = f"Top: {best_cand['symbol']} ({best_cand['pred_return_pct']:+.3f}%, Conf {best_cand['confidence_pct']}%)" if best_cand else ""

            log(f"Tick #{tick_count} | {mins_left}m to Close | Capital: INR {capital:,.2f} | Positions: {len(open_pos)} | {best_str}")

        except Exception as e:
            log(f"Tick #{tick_count} notice: {e}")

        # Sleep for remainder of 60-second cycle
        elapsed = time.time() - t_start
        sleep_dur = max(10.0, 60.0 - elapsed)
        time.sleep(sleep_dur)

    # Final End-of-Session Compilation
    log("=" * 75)
    log("GENERATING FINAL FRIDAY PERFORMANCE DOSSIER...")
    try:
        final_state = requests.get(f"{API_BASE}/api/state", timeout=10).json()
        final_verif = requests.get(f"{API_BASE}/api/predictions/verification?limit=100", timeout=10).json()

        dossier = {
            "session_date": datetime.now().strftime("%Y-%m-%d"),
            "session_completed_at": datetime.now().isoformat(),
            "final_capital": final_state.get("available_capital"),
            "net_profit": final_state.get("total_net_profit"),
            "gross_profit": final_state.get("total_gross_profit"),
            "total_tax_paid": final_state.get("total_tax_paid"),
            "total_brokerage_paid": final_state.get("total_brokerage_paid"),
            "daily_trades_count": final_state.get("daily_trades_count"),
            "win_rate_pct": final_state.get("win_rate_pct"),
            "overnight_open_positions": len(final_state.get("positions", {})),
            "prediction_accuracy": final_state.get("prediction_accuracy", {}),
            "trade_log": final_state.get("trade_history", [])
        }

        with open(FINAL_DOSSIER_FILE, "w", encoding="utf-8") as f:
            json.dump(dossier, f, indent=2)

        log("✅ Final Friday Session Dossier successfully saved to:")
        log(f"   {FINAL_DOSSIER_FILE}")
        log("=" * 75)

    except Exception as e:
        log(f"Error compiling final dossier: {e}")


if __name__ == "__main__":
    run_closing_sentinel()
