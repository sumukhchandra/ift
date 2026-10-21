"""
AlphaNSE V3 — Continuous Live Real-Time Multi-Model Streamer.
Fetches live market quotes every 15 seconds from the active local server/yfinance engine,
evaluates live 1m/5m model signals across all 6 models, and logs real-time ticks.
"""

import os
import sys
import time
import json
import requests
from datetime import datetime

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

SERVER_URL = "http://127.0.0.1:8000"
LOG_DIR = os.path.join(WORKSPACE_ROOT, "QA", "logs", "live_metrics")
os.makedirs(LOG_DIR, exist_ok=True)
FEED_LOG = os.path.join(LOG_DIR, "continuous_live_feed.jsonl")


def stream_live_cycle(iterations: int = 10, interval_seconds: int = 15):
    print("=" * 80)
    print("  🔴 ALPHANSE V3 — CONTINUOUS LIVE MARKET TICK STREAM")
    print(f"  Live Server: {SERVER_URL} | Interval: {interval_seconds}s")
    print("=" * 80)

    model_assignments = {
        "^NSEI": ("SMC_4CONF_920", "NIFTY 50 (Adaptive SMC)"),
        "TATACAP.NS": ("HYPO001", "Tata Capital (NBFC Wave)"),
        "INFY.NS": ("V2_15M", "Infosys (IT Momentum)"),
        "BAJFINANCE.NS": ("HYPO002", "Bajaj Finance (High Beta)"),
        "SBIN.NS": ("HYPO003", "State Bank of India (Dip Reversion)"),
        "RELIANCE.NS": ("V3_60M", "Reliance Ind (Macro Conglomerate)"),
    }

    for i in range(iterations):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            res = requests.get(f"{SERVER_URL}/api/signals", timeout=5)
            if res.status_code == 200:
                signals_data = res.json().get("signals", [])
                signals_dict = {s["symbol"]: s for s in signals_data}

                print(f"\n[{now_str}] LIVE TICK UPDATE #{i+1}")
                print(f"{'Model ID':15} | {'Symbol':14} | {'Live Price':10} | {'Pred 1m %':10} | {'Direction':9} | {'Strategy'}")
                print("-" * 80)

                tick_record = {"timestamp": now_str, "iteration": i + 1, "ticks": []}

                for sym, (m_id, strat) in model_assignments.items():
                    s = signals_dict.get(sym, {})
                    price = s.get("current_price", 0.0)
                    pred_ret = s.get("predicted_return_pct", 0.0)
                    dir_str = s.get("direction", "FLAT")

                    print(f"{m_id:15} | {sym:14} | ₹{price:9.2f} | {pred_ret:+8.3f}% | {dir_str:9} | {strat}")
                    tick_record["ticks"].append({
                        "model_id": m_id,
                        "symbol": sym,
                        "price": price,
                        "predicted_return_pct": pred_ret,
                        "direction": dir_str,
                    })

                with open(FEED_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps(tick_record) + "\n")

            else:
                print(f"[{now_str}] Server returned status code {res.status_code}")
        except Exception as e:
            print(f"[{now_str}] Error streaming live feed: {e}")

        if i < iterations - 1:
            time.sleep(interval_seconds)


if __name__ == "__main__":
    stream_live_cycle(iterations=5, interval_seconds=5)
