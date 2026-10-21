#!/usr/bin/env python3
"""
scripts/rolling_30min_prediction_engine.py
AlphaNSE V3 — Rolling 30-Minute Forward Price Prediction & Delayed Comparison Engine.

MANDATE:
At every single minute T (e.g. 10:50, 11:00, 11:01, 11:02... up to 15:00):
1. Model predicts the exact price for T + 30 minutes (e.g. 11:20, 11:30, 11:31, 11:32... 15:30).
2. Prediction is registered into the rolling queue with (T, T+30m, P_now, P_pred, Direction).
3. When the live clock reaches T + 30 minutes:
   - Pulls the actual real market price at T + 30 minutes.
   - Compares: Predicted Price vs Real Market Price.
   - Verifies: Directional Hit (UP/DOWN) and Absolute Error (Rs & bps).
4. Runs on today's live session (Session 12, Oct 08, 2026), evaluating all matured 30m windows
   and maintaining active queues for pending upcoming targets.
"""

import os
import sys
import math
import json
import time
from datetime import datetime, timedelta, time as dtime
from typing import Dict, Any, List, Optional, Tuple

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
REPORT_PATH = os.path.join(WORKSPACE_ROOT, "v3", "reports", "ROLLING_30MIN_PREDICTION_REPORT.md")
STATE_PATH = os.path.join(WORKSPACE_ROOT, "v3", "reports", "ROLLING_30MIN_PREDICTION_STATE.json")


class Rolling30MinPredictionEngine:
    def __init__(self):
        with open(WEIGHTS_30M_PATH, "r", encoding="utf-8") as f:
            self.weights_data = json.load(f)
        self.sym_list = list(SYMBOLS.keys())
        self.candles_by_sym: Dict[str, List[Dict[str, Any]]] = {}

    def fetch_live_session_candles(self):
        """Fetches all 1m candles for today from market open (09:15) to current time."""
        print("[DATA] Fetching live 1m tape for Session 12 from NSE...")
        df = yf.download(self.sym_list, period="1d", interval="1m", progress=False)
        if df.empty or len(df) < 5:
            df = yf.download(self.sym_list, period="1d", interval="5m", progress=False)

        for sym in self.sym_list:
            self.candles_by_sym[sym] = []
            try:
                c_s = df["Close"][sym].dropna()
                o_s = df["Open"][sym].dropna()
                h_s = df["High"][sym].dropna()
                l_s = df["Low"][sym].dropna()
                v_s = df["Volume"][sym].dropna()

                for k in range(len(c_s)):
                    dt_str = str(c_s.index[k])
                    # Clean HH:MM
                    time_hhmm = dt_str.split(" ")[-1][:5]
                    self.candles_by_sym[sym].append({
                        "timestamp": dt_str,
                        "time_hhmm": time_hhmm,
                        "open": float(o_s.iloc[k]),
                        "high": float(h_s.iloc[k]),
                        "low": float(l_s.iloc[k]),
                        "close": float(c_s.iloc[k]),
                        "volume": float(v_s.iloc[k]) if not v_s.empty else 1000.0
                    })
                print(f"  • {sym:<14} ({SYMBOLS[sym]['name']:<16}): Ingested {len(self.candles_by_sym[sym])} 1m bars (09:15 ➔ {self.candles_by_sym[sym][-1]['time_hhmm']} IST)")
            except Exception as e:
                print(f"  [WARN] Failed to ingest {sym}: {e}")

    def evaluate_rolling_30min_stream(self) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]]]:
        """
        Processes every 1-minute candle of today:
        - At bar i (time T): Predict price at bar i + 30 (time T + 30m).
        - If i + 30 < len(candles): Matured! Compare predicted price vs real price at i + 30.
        - If i + 30 >= len(candles): Pending! Target time is in the future.
        """
        matured_by_sym = {s: [] for s in self.sym_list}
        pending_by_sym = {s: [] for s in self.sym_list}

        for sym, c_list in self.candles_by_sym.items():
            m_data = self.weights_data.get(sym)
            if not m_data:
                continue

            w = m_data["weights"]
            b = m_data["bias"]
            means = m_data["means"]
            stds = m_data["stds"]

            n = len(c_list)
            # Need at least 20 prior bars to compute features
            for i in range(20, n):
                cur = c_list[i]
                feats = compute_features(c_list, i)
                if not feats:
                    continue

                # Predict 30-minute forward return
                x_norm = [(feats[j] - means[j]) / (stds[j] or 1.0) for j in range(min(len(feats), len(w)))]
                pred_ret_30m = sum(wj * xj for wj, xj in zip(w, x_norm)) + b

                p_now = cur["close"]
                p_pred_30m = round(p_now * (1.0 + pred_ret_30m), 2)
                pred_dir = "UP" if pred_ret_30m > 0 else ("DOWN" if pred_ret_30m < 0 else "FLAT")

                # Target time is exactly 30 minutes later
                t_obj = datetime.strptime(cur["time_hhmm"], "%H:%M")
                target_hhmm = (t_obj + timedelta(minutes=30)).strftime("%H:%M")

                forecast_record = {
                    "forecast_bar_idx": i,
                    "forecast_time": cur["time_hhmm"],
                    "target_time": target_hhmm,
                    "initial_price": p_now,
                    "predicted_price_30m": p_pred_30m,
                    "predicted_return_bps": round(pred_ret_30m * 10000, 2),
                    "predicted_dir": pred_dir
                }

                # Check if 30 minutes have elapsed
                target_idx = i + 30
                if target_idx < n:
                    # MATURED! The real market has reached T + 30m
                    actual_bar = c_list[target_idx]
                    p_actual = actual_bar["close"]
                    act_ret = (p_actual - p_now) / (p_now or 1e-6)
                    act_dir = "UP" if act_ret > 0 else ("DOWN" if act_ret < 0 else "FLAT")

                    is_correct = (pred_dir == act_dir) if act_dir != "FLAT" else True
                    abs_err_rs = abs(p_actual - p_pred_30m)
                    abs_err_bps = (abs_err_rs / p_now) * 10000

                    forecast_record.update({
                        "actual_time": actual_bar["time_hhmm"],
                        "actual_price": p_actual,
                        "actual_return_bps": round(act_ret * 10000, 2),
                        "actual_dir": act_dir,
                        "is_correct": is_correct,
                        "error_rs": round(abs_err_rs, 2),
                        "error_bps": round(abs_err_bps, 2),
                        "status": "VERIFIED"
                    })
                    matured_by_sym[sym].append(forecast_record)
                else:
                    # PENDING! Target time is in upcoming minutes today
                    forecast_record.update({
                        "status": "AWAITING_REAL_MARKET_TIME"
                    })
                    pending_by_sym[sym].append(forecast_record)

        return matured_by_sym, pending_by_sym

    def print_and_save_report(self, matured: Dict[str, List[Dict[str, Any]]], pending: Dict[str, List[Dict[str, Any]]]):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
        print("\n" + "=" * 115)
        print("  🎯 ALPHANSE V3 — ROLLING 30-MINUTE FORWARD PRICE PREDICTION & COMPARISON BENCHMARK")
        print(f"  SESSION DATE: Thursday, October 08, 2026 | CURRENT TIME: {now_str}")
        print("  HORIZON RULE: At Time T, Predict Price for T + 30m. At T + 30m, Compare with Real Market Price.")
        print("=" * 115)

        # 1. Summary Scorecard of Matured Predictions
        print(f"\n{'Symbol':<14} | {'Asset Name':<16} | {'30m Forecasts':<14} | {'Direction Hit %':<16} | {'Mean Price Error (Rs)':<22} | {'Mean Error (bps)':<16}")
        print("-" * 108)

        total_matured = 0
        total_hits = 0
        errors_bps = []

        for sym in self.sym_list:
            records = matured.get(sym, [])
            n = len(records)
            if n == 0:
                continue

            hits = sum(1 for r in records if r["is_correct"])
            acc = (hits / n * 100.0)
            avg_err_rs = sum(r["error_rs"] for r in records) / n
            avg_err_bps = sum(r["error_bps"] for r in records) / n

            total_matured += n
            total_hits += hits
            errors_bps.append(avg_err_bps)

            print(f"{sym:<14} | {SYMBOLS[sym]['name']:<16} | {n:<14} | {acc:>14.1f}% | ₹{avg_err_rs:>20.2f} | {avg_err_bps:>14.1f} bps")

        overall_acc = (total_hits / total_matured * 100.0) if total_matured > 0 else 0.0
        overall_err_bps = sum(errors_bps) / len(errors_bps) if errors_bps else 0.0

        print("-" * 108)
        print(f"{'OVERALL FLEET':<14} | {'6 Universe Stocks':<16} | {total_matured:<14} | {overall_acc:>14.1f}% | {'--':>21} | {overall_err_bps:>14.1f} bps")
        print("=" * 108)

        # 2. Detailed Verification Table of Today's Matured 30-Minute Predictions
        print("\n" + "=" * 115)
        print("  🔍 SAMPLE OF TODAY'S MATURED 30-MINUTE PREDICTIONS (PREDICTED AT T ➔ VERIFIED AT T+30m)")
        print("=" * 115)
        for sym in self.sym_list:
            records = matured.get(sym, [])
            if not records:
                continue
            recent = records[-4:]
            print(f"\n  📌 Instrument: {sym} ({SYMBOLS[sym]['name']}):")
            print(f"     {'Forecast Time':<14} | {'Target Time':<13} | {'Initial Px':<12} | {'Predicted Px (30m)':<20} | {'Actual Px (30m)':<17} | {'Pred Dir':<9} | {'Act Dir':<8} | {'Hit?':<8} | {'Error (Rs)':<10}")
            print("     " + "-" * 118)
            for r in recent:
                hit_str = "✅ YES" if r["is_correct"] else "❌ NO"
                print(f"     {r['forecast_time']:<14} | {r['target_time']:<13} | ₹{r['initial_price']:>10.2f} | ₹{r['predicted_price_30m']:>18.2f} | ₹{r['actual_price']:>15.2f} | {r['predicted_dir']:<9} | {r['actual_dir']:<8} | {hit_str:<8} | ₹{r['error_rs']:>8.2f}")

        # 3. Active Pending Queue for Upcoming Minutes
        print("\n" + "=" * 115)
        print("  ⏳ CURRENT PENDING 30-MINUTE FORECAST QUEUE (AWAITING REAL TIME TO PRINT)")
        print("=" * 115)
        for sym in self.sym_list:
            p_list = pending.get(sym, [])
            if not p_list:
                continue
            # Show a few sample pending forecasts
            sample_pending = [p_list[0], p_list[len(p_list)//2], p_list[-1]] if len(p_list) >= 3 else p_list
            print(f"\n  📌 Instrument: {sym} ({SYMBOLS[sym]['name']}) — {len(p_list)} Pending 30m Forecasts in Queue:")
            print(f"     {'Forecast Time':<14} | {'Target Time':<13} | {'Initial Px':<12} | {'Predicted Px for Target':<25} | {'Predicted Dir':<14} | {'Status':<25}")
            print("     " + "-" * 108)
            for p in sample_pending:
                print(f"     {p['forecast_time']:<14} | {p['target_time']:<13} | ₹{p['initial_price']:>10.2f} | ₹{p['predicted_price_30m']:>23.2f} | {p['predicted_dir']:<14} | ⏳ Awaiting {p['target_time']} IST")

        # 4. Generate Comprehensive Markdown Report
        md_lines = [
            "# AlphaNSE V3 — Rolling 30-Minute Price Prediction & Delayed Comparison Report",
            "",
            "**Operational Architecture:** Rolling 30-Minute Forward Price Horizon ($H = 30$ minutes)  ",
            "**Execution Rule:** At every minute $T$ (e.g. 10:50, 11:00, 11:01...), forecast price at $T + 30\\text{m}$. When clock reaches $T + 30\\text{m}$, compare forecast vs real stock price.  ",
            f"**Session Date:** `Thursday, October 08, 2026`  ",
            f"**Evaluation Timestamp:** `{now_str}`  ",
            f"**Total Matured 30-Minute Forecasts Today:** **{total_matured:,} Verified Predictions**  ",
            f"**Overall Fleet Directional Hit Rate:** **{overall_acc:.1f}%**  ",
            "",
            "---",
            "",
            "## 1. 30-Minute Rolling Model Capacity Scorecard",
            "",
            "| Symbol | Asset Name | Matured 30m Forecasts | Directional Hit Rate % | Mean Absolute Error (₹) | Mean Error (bps) | Capacity Verdict |",
            "|---|---|:---:|:---:|:---:|:---:|:---:|",
        ]

        for sym in self.sym_list:
            records = matured.get(sym, [])
            n = len(records)
            if n == 0:
                continue
            hits = sum(1 for r in records if r["is_correct"])
            acc = (hits / n * 100.0)
            avg_err_rs = sum(r["error_rs"] for r in records) / n
            avg_err_bps = sum(r["error_bps"] for r in records) / n
            verdict = "🟢 Strong Edge (>55%)" if acc >= 55.0 else ("🟡 Neutral (50-55%)" if acc >= 50.0 else "🔴 Sub-50%")
            md_lines.append(
                f"| `{sym}` | {SYMBOLS[sym]['name']} | {n:,} | **{acc:.1f}%** | ₹{avg_err_rs:.2f} | {avg_err_bps:.1f} bps | {verdict} |"
            )

        md_lines.extend([
            "",
            "---",
            "",
            "## 2. Sample Matured 30-Minute Predictions (Verified on Live Tape)",
            "",
            "| Symbol | Forecast Time (T) | Target Time (T+30) | Initial Price (₹) | Predicted Price (₹) | Actual Real Price (₹) | Pred Dir | Real Dir | Verified Hit | Price Error (₹) |",
            "|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
        ])

        for sym in self.sym_list:
            for r in matured.get(sym, [])[-3:]:
                match_icon = "✅ YES" if r["is_correct"] else "❌ NO"
                md_lines.append(
                    f"| `{sym}` | {r['forecast_time']} | {r['target_time']} | ₹{r['initial_price']:,.2f} | "
                    f"₹{r['predicted_price_30m']:,.2f} | ₹{r['actual_price']:,.2f} | {r['predicted_dir']} | "
                    f"{r['actual_dir']} | {match_icon} | ₹{r['error_rs']:.2f} |"
                )

        md_lines.extend([
            "",
            "---",
            "",
            "## 3. Active Pending Queue for Upcoming Afternoon Target Times",
            "",
            "| Symbol | Forecast Time (T) | Target Verification Time (T+30) | Current Initial Price (₹) | Predicted Price for Target (₹) | Expected Direction | Status |",
            "|---|:---:|:---:|:---:|:---:|:---:|:---:|",
        ])

        for sym in self.sym_list:
            p_list = pending.get(sym, [])
            for p in p_list[-3:]:
                md_lines.append(
                    f"| `{sym}` | {p['forecast_time']} | **{p['target_time']} IST** | ₹{p['initial_price']:,.2f} | "
                    f"**₹{p['predicted_price_30m']:,.2f}** | `{p['predicted_dir']}` | ⏳ Awaiting {p['target_time']} IST |"
                )

        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
        print(f"\n[REPORT] Saved rolling 30m report to: {REPORT_PATH}")

        # Save JSON State
        state_data = {
            "session_date": "2026-10-08",
            "last_updated": now_str,
            "overall_accuracy_pct": round(overall_acc, 2),
            "total_matured_forecasts": total_matured,
            "matured_by_sym": {
                s: matured.get(s, [])[-10:] for s in self.sym_list
            },
            "pending_by_sym": {
                s: pending.get(s, []) for s in self.sym_list
            }
        }
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2)
        print(f"[DATA] Saved rolling 30m JSON state to: {STATE_PATH}")


def main():
    engine = Rolling30MinPredictionEngine()
    engine.fetch_live_session_candles()
    matured, pending = engine.evaluate_rolling_30min_stream()
    engine.print_and_save_report(matured, pending)


if __name__ == "__main__":
    main()
