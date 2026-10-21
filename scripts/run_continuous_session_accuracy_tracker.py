#!/usr/bin/env python3
"""
scripts/run_continuous_session_accuracy_tracker.py
AlphaNSE V3 — Continuous Real-Time End-of-Session Prediction Accuracy Daemon.

Runs continuously in the background for Session 12 until 15:30 IST market close.
On every 1-minute candle:
1. Records actual live price.
2. Compares previous prediction vs actual print.
3. Generates new prediction for the next candle.
4. Updates SESSION_12_LIVE_ACCURACY_SCORECARD.json in real time.
5. At 15:30 IST, generates the complete final EOD report.
"""

import os
import sys
import time
import json
from datetime import datetime, time as dtime
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
from scripts.benchmark_model_prediction_accuracy import compute_features, SYMBOLS, WEIGHTS_PATH

SCORECARD_PATH = os.path.join(WORKSPACE_ROOT, "v3", "reports", "SESSION_12_LIVE_ACCURACY_SCORECARD.json")
STREAM_LOG_PATH = os.path.join(WORKSPACE_ROOT, "v3", "reports", "SESSION_12_PREDICTION_STREAM.jsonl")


def run_tracker(interval: int = 30):
    print("=" * 95)
    print("  🚀 SESSION 12 CONTINUOUS END-OF-SESSION PREDICTION BENCHMARK DAEMON")
    print(f"  POLLING CADENCE: {interval}s | TARGET CUTOFF: 15:30 IST (End of Session)")
    print("=" * 95)

    with open(WEIGHTS_PATH, "r", encoding="utf-8") as f:
        weights_data = json.load(f)

    pending_preds: Dict[str, Dict[str, Any]] = {}
    history: List[Dict[str, Any]] = []

    sym_list = list(SYMBOLS.keys())
    market_close = dtime(15, 30)

    cycle = 0
    while True:
        now = datetime.now()
        current_time = now.time()
        cycle += 1

        print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')} IST] Cycle #{cycle} | Tracking live tape...")

        try:
            df = yf.download(sym_list, period="1d", interval="1m", progress=False)
            if df.empty:
                time.sleep(interval)
                continue
        except Exception as e:
            print(f"  [WARN] Fetch failed: {e}")
            time.sleep(interval)
            continue

        latest_quotes = {}
        for sym in sym_list:
            c_s = df["Close"][sym].dropna()
            if not c_s.empty:
                latest_quotes[sym] = float(c_s.iloc[-1])

        # 1. Verify previous predictions
        if pending_preds:
            for sym, pred in list(pending_preds.items()):
                p_now = latest_quotes.get(sym)
                if p_now is None:
                    continue

                p_entry = pred["entry_price"]
                p_pred = pred["predicted_price"]
                act_ret = (p_now - p_entry) / (p_entry or 1e-6)
                act_dir = "UP" if act_ret > 0 else ("DOWN" if act_ret < 0 else "FLAT")

                is_correct = (pred["pred_dir"] == act_dir) if act_dir != "FLAT" else True
                abs_err = abs(p_now - p_pred)
                match_str = "✅ YES" if is_correct else "❌ NO"

                record = {
                    "timestamp": now.isoformat(),
                    "time": now.strftime("%H:%M:%S"),
                    "model": pred["model"],
                    "symbol": sym,
                    "entry_px": p_entry,
                    "pred_px": p_pred,
                    "actual_px": p_now,
                    "pred_dir": pred["pred_dir"],
                    "act_dir": act_dir,
                    "is_correct": is_correct,
                    "abs_err_rs": round(abs_err, 2),
                    "abs_err_bps": round((abs_err / p_entry) * 10000, 2)
                }
                history.append(record)

                with open(STREAM_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")

                print(f"  • {pred['model']:<14} ({sym:<14}): Pred ₹{p_pred:.2f} ({pred['pred_dir']}) ➔ Act ₹{p_now:.2f} ({act_dir}) | {match_str} | Err: ₹{abs_err:.2f}")

            pending_preds.clear()

        # 2. Make new forward predictions
        for sym in sym_list:
            sym_info = SYMBOLS.get(sym)
            if not sym_info:
                continue
            mid = sym_info["model"]
            m_data = weights_data.get(mid)
            if not m_data:
                continue

            try:
                c_s = df["Close"][sym].dropna()
                o_s = df["Open"][sym].dropna()
                h_s = df["High"][sym].dropna()
                l_s = df["Low"][sym].dropna()
                v_s = df["Volume"][sym].dropna()

                candles = []
                for k in range(len(c_s)):
                    candles.append({
                        "close": float(c_s.iloc[k]),
                        "open": float(o_s.iloc[k]),
                        "high": float(h_s.iloc[k]),
                        "low": float(l_s.iloc[k]),
                        "volume": float(v_s.iloc[k]) if not v_s.empty else 1000.0
                    })

                if len(candles) < 25:
                    continue

                idx = len(candles) - 1
                feats = compute_features(candles, idx)
                if not feats:
                    continue

                w = m_data["weights"]
                b = m_data["bias"]
                means = m_data["means"]
                stds = m_data["stds"]

                x_norm = [(feats[j] - means[j]) / (stds[j] or 1.0) for j in range(min(len(feats), len(w)))]
                pred_ret = sum(wj * xj for wj, xj in zip(w, x_norm)) + b

                p_now = candles[-1]["close"]
                p_next_pred = round(p_now * (1.0 + pred_ret), 2)
                p_dir = "UP" if pred_ret > 0 else ("DOWN" if pred_ret < 0 else "FLAT")

                pending_preds[sym] = {
                    "model": mid,
                    "entry_price": p_now,
                    "predicted_price": p_next_pred,
                    "pred_dir": p_dir
                }
            except Exception:
                pass

        # 3. Update Live Scorecard JSON
        if history:
            tot = len(history)
            hits = sum(1 for h in history if h["is_correct"])
            acc = round((hits / tot) * 100.0, 2)
            avg_err_rs = round(sum(h["abs_err_rs"] for h in history) / tot, 2)
            avg_err_bps = round(sum(h["abs_err_bps"] for h in history) / tot, 2)

            scorecard = {
                "session_date": "2026-10-08",
                "last_updated": now.isoformat(),
                "cycle": cycle,
                "total_forecasts": tot,
                "correct_forecasts": hits,
                "overall_accuracy_pct": acc,
                "mean_error_rs": avg_err_rs,
                "mean_error_bps": avg_err_bps,
                "recent_forecasts": history[-12:]
            }
            with open(SCORECARD_PATH, "w", encoding="utf-8") as f:
                json.dump(scorecard, f, indent=2)

        # Check for market close
        if current_time >= market_close and now.weekday() < 5:
            print(f"\n⏰ [15:30 IST] Market is closed. Session 12 tracking complete!")
            break

        time.sleep(interval)


if __name__ == "__main__":
    run_tracker(interval=30)
