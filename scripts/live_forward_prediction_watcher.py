#!/usr/bin/env python3
"""
scripts/live_forward_prediction_watcher.py
AlphaNSE V3 — Live Real-Time Forward Price Prediction & Stock Accuracy Watcher.

Continuously predicts the upcoming price of live stocks, waits for the real candle
to form on NSE, and compares the model prediction directly against the real market price.
"""

import os
import sys
import time
import math
import json
from datetime import datetime
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

LOG_PATH = os.path.join(WORKSPACE_ROOT, "v3", "reports", "LIVE_FORWARD_ACCURACY_LOG.jsonl")


def run_live_prediction_watcher(cycles: int = 5, sleep_sec: int = 45):
    with open(WEIGHTS_PATH, "r", encoding="utf-8") as f:
        weights_data = json.load(f)

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

    print("=" * 105)
    print("  🔮 ALPHANSE V3 — LIVE FORWARD PREDICTION & REAL STOCK COMPARISON ENGINE")
    print("  Comparing Model Price Forecasts vs Real NSE Market Closes In Real Time")
    print("=" * 105)

    pending_predictions: Dict[str, Dict[str, Any]] = {}
    verified_results: List[Dict[str, Any]] = []

    sym_list = list(SYMBOLS.keys())

    for c in range(1, cycles + 1):
        now_str = datetime.now().strftime("%H:%M:%S IST")
        print(f"\n[{now_str}] ─── STEP {c}/{cycles}: INGESTING LIVE TAPE & EVALUATING PENDING FORECASTS ───")

        # 1. Fetch Latest 1m Data from NSE
        try:
            df = yf.download(sym_list, period="1d", interval="1m", progress=False)
            if df.empty:
                print("  [WARN] Data feed empty. Retrying...")
                time.sleep(10)
                continue
        except Exception as e:
            print(f"  [ERR] Fetch failed: {e}")
            time.sleep(10)
            continue

        latest_quotes = {}
        for sym in sym_list:
            c_s = df["Close"][sym].dropna()
            if not c_s.empty:
                latest_quotes[sym] = {
                    "price": float(c_s.iloc[-1]),
                    "timestamp": str(c_s.index[-1]).split("+")[0].split(" ")[-1]
                }

        # 2. Check and Compare Any Pending Predictions From Previous Cycle
        if pending_predictions:
            print("\n  📊 [VERIFICATION RESULTS OF PREVIOUS CYCLE FORECASTS]:")
            print(f"  {'Model':<14} | {'Symbol':<14} | {'Entry Px':<11} | {'Predicted Px':<14} | {'Actual Live Px':<15} | {'Pred Dir':<9} | {'Act Dir':<8} | {'Hit?':<8} | {'Error (Rs)':<10}")
            print("  " + "-" * 115)

            for sym, pred in list(pending_predictions.items()):
                actual_info = latest_quotes.get(sym)
                if not actual_info:
                    continue

                p_entry = pred["entry_price"]
                p_pred = pred["predicted_price"]
                p_actual = actual_info["price"]

                actual_return = (p_actual - p_entry) / (p_entry or 1e-6)
                act_dir = "UP" if actual_return > 0 else ("DOWN" if actual_return < 0 else "FLAT")

                is_correct = (pred["predicted_dir"] == act_dir) if act_dir != "FLAT" else True
                abs_err = abs(p_actual - p_pred)
                match_icon = "✅ YES" if is_correct else "❌ NO"

                print(f"  {pred['model']:<14} | {sym:<14} | ₹{p_entry:>9.2f} | ₹{p_pred:>12.2f} | ₹{p_actual:>13.2f} | {pred['predicted_dir']:<9} | {act_dir:<8} | {match_icon:<8} | ₹{abs_err:>8.2f}")

                rec = {
                    "timestamp": datetime.now().isoformat(),
                    "model": pred["model"],
                    "symbol": sym,
                    "entry_price": p_entry,
                    "predicted_price": p_pred,
                    "actual_price": p_actual,
                    "pred_dir": pred["predicted_dir"],
                    "act_dir": act_dir,
                    "is_correct": is_correct,
                    "abs_err_rs": round(abs_err, 2)
                }
                verified_results.append(rec)
                with open(LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec) + "\n")

            pending_predictions.clear()

        # 3. Generate Next 1-Minute Forward Predictions
        print("\n  🔮 [GENERATING NEW FORWARD PRICE PREDICTIONS FOR UPCOMING BAR]:")
        print(f"  {'Model':<14} | {'Symbol':<14} | {'Asset Name':<16} | {'Current Live Px':<16} | {'Forecast Next Px':<17} | {'Expected Edge':<14} | {'Predicted Dir':<13}")
        print("  " + "-" * 115)

        for sym in sym_list:
            sym_info = SYMBOLS.get(sym)
            if not sym_info:
                continue
            mid = sym_info["model"]
            m_data = weights_data.get(mid)
            if not m_data:
                continue

            # Build candle list for symbol
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
                edge_bps = pred_ret * 10000

                print(f"  {mid:<14} | {sym:<14} | {sym_info['name']:<16} | ₹{p_now:>14.2f} | ₹{p_next_pred:>15.2f} | {edge_bps:>+10.1f} bps | {p_dir:<13}")

                pending_predictions[sym] = {
                    "model": mid,
                    "entry_price": p_now,
                    "predicted_price": p_next_pred,
                    "predicted_dir": p_dir,
                    "edge_bps": edge_bps,
                    "forecast_time": datetime.now().strftime("%H:%M:%S")
                }
            except Exception as e:
                pass

        if c < cycles:
            print(f"\n  ⏳ Waiting {sleep_sec}s for the next real market candle to form on NSE...")
            time.sleep(sleep_sec)

    # Summary
    if verified_results:
        tot = len(verified_results)
        hits = sum(1 for r in verified_results if r["is_correct"])
        acc = (hits / tot * 100.0) if tot > 0 else 0.0
        avg_err = sum(r["abs_err_rs"] for r in verified_results) / tot
        print("\n" + "=" * 98)
        print("  🏆 LIVE SESSION VERIFICATION SUMMARY")
        print(f"  Total Live Forward Tests: {tot} | Correct Directional Forecasts: {hits}/{tot} ({acc:.1f}%)")
        print(f"  Mean Absolute Price Error: ₹{avg_err:.2f}")
        print("=" * 98)


if __name__ == "__main__":
    run_live_prediction_watcher(cycles=3, sleep_sec=30)
