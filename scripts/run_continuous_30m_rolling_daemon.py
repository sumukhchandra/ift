#!/usr/bin/env python3
"""
scripts/run_continuous_30m_rolling_daemon.py
AlphaNSE V3 — Continuous Live Rolling 30-Minute Price Forecasting & Verification Daemon.

MANDATE:
Runs continuously in real-time until 15:30 IST market close.
Every minute as each new candle forms:
1. Pulls the latest real market price.
2. Evaluates and compares the 30-minute forecast made 30 minutes ago (T - 30m ➔ T).
3. Issues a new 30-minute forecast for the upcoming target time (T ➔ T + 30m).
   (e.g., at 10:50 -> 11:20; at 11:00 -> 11:30; at 11:01 -> 11:31; at 11:02 -> 11:32... up to 15:00 -> 15:30).
4. Maintains an immutable live verification log of all 30m forecasts.
"""

import os
import sys
import math
import json
import time
from datetime import datetime, timedelta, time as dtime
from typing import Dict, Any, List

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import yfinance as yf
from scripts.benchmark_model_prediction_accuracy import compute_features, SYMBOLS

WEIGHTS_30M_PATH = os.path.join(WORKSPACE_ROOT, "v3", "models", "multimodel", "session12_30m_forward_weights.json")
STREAM_LOG = os.path.join(WORKSPACE_ROOT, "v3", "reports", "ROLLING_30M_LIVE_STREAM.jsonl")
SCORECARD_FILE = os.path.join(WORKSPACE_ROOT, "v3", "reports", "ROLLING_30M_LIVE_SCORECARD.json")


def run_daemon(poll_interval: int = 60):
    print("=" * 105)
    print("  ⚡ ALPHANSE V3 — LIVE ROLLING 30-MINUTE PREDICTION & DELAYED VERIFICATION DAEMON")
    print(f"  CADENCE: Every {poll_interval}s | TARGET HORIZON: T ➔ T + 30m | EOD CUTOFF: 15:30 IST")
    print("=" * 105)

    with open(WEIGHTS_30M_PATH, "r", encoding="utf-8") as f:
        weights_data = json.load(f)

    sym_list = list(SYMBOLS.keys())
    # pending_forecasts: (sym, target_time) -> dict
    pending_forecasts: Dict[str, Dict[str, Any]] = {}
    verified_history: List[Dict[str, Any]] = []

    market_close = dtime(15, 30)

    cycle = 0
    while True:
        now = datetime.now()
        current_time = now.time()
        time_hhmm = now.strftime("%H:%M")
        cycle += 1

        print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')} IST] ─── CYCLE #{cycle} ({time_hhmm} IST) ───")

        # 1. Fetch Latest 1m Tape from NSE
        try:
            df = yf.download(sym_list, period="1d", interval="1m", progress=False)
            if df.empty:
                time.sleep(poll_interval)
                continue
        except Exception as e:
            print(f"  [WARN] Data fetch failed: {e}")
            time.sleep(poll_interval)
            continue

        latest_prices = {}
        candles_by_sym = {}
        for sym in sym_list:
            try:
                c_s = df["Close"][sym].dropna()
                o_s = df["Open"][sym].dropna()
                h_s = df["High"][sym].dropna()
                l_s = df["Low"][sym].dropna()
                v_s = df["Volume"][sym].dropna()

                candles = []
                for k in range(len(c_s)):
                    candles.append({
                        "close": float(c_s.iloc[-1]),
                        "open": float(o_s.iloc[-1]),
                        "high": float(h_s.iloc[-1]),
                        "low": float(l_s.iloc[-1]),
                        "volume": float(v_s.iloc[-1]) if not v_s.empty else 1000.0
                    })
                candles_by_sym[sym] = candles
                latest_prices[sym] = float(c_s.iloc[-1])
            except Exception:
                pass

        # 2. Check Any Matured 30-Minute Predictions
        # A prediction is matured if current_time >= target_time
        matured_keys = []
        for key, p in pending_forecasts.items():
            if time_hhmm >= p["target_time"]:
                matured_keys.append(key)

        if matured_keys:
            print("\n  🎯 [VERIFYING MATURED 30-MINUTE PREDICTIONS RIGHT NOW]:")
            print(f"  {'Symbol':<14} | {'Forecast Time':<14} | {'Target Time':<12} | {'Initial Px':<12} | {'Predicted Px':<15} | {'Real Live Px':<15} | {'Pred Dir':<9} | {'Act Dir':<8} | {'Hit?':<8} | {'Error (Rs)':<10}")
            print("  " + "-" * 115)

            for key in matured_keys:
                p = pending_forecasts.pop(key)
                sym = p["symbol"]
                p_actual = latest_prices.get(sym)
                if p_actual is None:
                    continue

                p_entry = p["initial_price"]
                p_pred = p["predicted_price"]
                act_ret = (p_actual - p_entry) / (p_entry or 1e-6)
                act_dir = "UP" if act_ret > 0 else ("DOWN" if act_ret < 0 else "FLAT")

                is_correct = (p["predicted_dir"] == act_dir) if act_dir != "FLAT" else True
                abs_err = abs(p_actual - p_pred)
                match_str = "✅ YES" if is_correct else "❌ NO"

                print(f"  {sym:<14} | {p['forecast_time']:<14} | {p['target_time']:<12} | ₹{p_entry:>10.2f} | ₹{p_pred:>13.2f} | ₹{p_actual:>13.2f} | {p['predicted_dir']:<9} | {act_dir:<8} | {match_str:<8} | ₹{abs_err:>8.2f}")

                rec = {
                    "timestamp": now.isoformat(),
                    "forecast_time": p["forecast_time"],
                    "target_time": p["target_time"],
                    "symbol": sym,
                    "initial_price": p_entry,
                    "predicted_price": p_pred,
                    "actual_price": p_actual,
                    "predicted_dir": p["predicted_dir"],
                    "actual_dir": act_dir,
                    "is_correct": is_correct,
                    "error_rs": round(abs_err, 2),
                    "error_bps": round((abs_err / p_entry) * 10000, 2)
                }
                verified_history.append(rec)
                os.makedirs(os.path.dirname(STREAM_LOG), exist_ok=True)
                with open(STREAM_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec) + "\n")

        # 3. Generate New 30-Minute Forward Predictions for Target Time (T + 30m)
        target_obj = now + timedelta(minutes=30)
        target_hhmm = target_obj.strftime("%H:%M")

        print(f"\n  🔮 [REGISTERING NEW 30-MINUTE FORWARD FORECASTS FOR TARGET: {target_hhmm} IST]:")
        print(f"  {'Symbol':<14} | {'Current Live Px (T)':<20} | {'Forecast Px (T+30m)':<21} | {'Expected Edge':<15} | {'Predicted Dir':<14}")
        print("  " + "-" * 88)

        for sym in sym_list:
            m_data = weights_data.get(sym)
            candles = candles_by_sym.get(sym, [])
            if not m_data or len(candles) < 25:
                continue

            try:
                feats = compute_features(candles, len(candles) - 1)
                if not feats:
                    continue

                w = m_data["weights"]
                b = m_data["bias"]
                means = m_data["means"]
                stds = m_data["stds"]

                x_norm = [(feats[j] - means[j]) / (stds[j] or 1.0) for j in range(min(len(feats), len(w)))]
                pred_ret = sum(wj * xj for wj, xj in zip(w, x_norm)) + b

                p_now = latest_prices[sym]
                p_next_30m = round(p_now * (1.0 + pred_ret), 2)
                p_dir = "UP" if pred_ret > 0 else ("DOWN" if pred_ret < 0 else "FLAT")
                edge_bps = pred_ret * 10000

                print(f"  {sym:<14} | ₹{p_now:>18.2f} | ₹{p_next_30m:>19.2f} | {edge_bps:>+11.1f} bps | {p_dir:<14}")

                key = f"{sym}_{target_hhmm}"
                pending_forecasts[key] = {
                    "symbol": sym,
                    "forecast_time": time_hhmm,
                    "target_time": target_hhmm,
                    "initial_price": p_now,
                    "predicted_price": p_next_30m,
                    "predicted_dir": p_dir,
                    "edge_bps": round(edge_bps, 2)
                }
            except Exception:
                pass

        # 4. Save Status Scorecard
        tot = len(verified_history)
        hits = sum(1 for v in verified_history if v["is_correct"])
        acc = round((hits / tot * 100.0), 2) if tot > 0 else 0.0

        scorecard = {
            "session_date": "2026-10-08",
            "last_updated": now.isoformat(),
            "cycle": cycle,
            "total_verified": tot,
            "correct_hits": hits,
            "accuracy_pct": acc,
            "pending_queue_count": len(pending_forecasts),
            "recent_verified": verified_history[-10:]
        }
        with open(SCORECARD_FILE, "w", encoding="utf-8") as f:
            json.dump(scorecard, f, indent=2)

        if current_time >= market_close and now.weekday() < 5:
            print("\n⏰ [15:30 IST] Market closed. Daemon finished successfully.")
            break

        time.sleep(poll_interval)


if __name__ == "__main__":
    run_daemon(poll_interval=60)
