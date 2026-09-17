"""
Live Real-Time Server & Prediction Monitor.

Monitors:
1. FastAPI Server Health & Market Status
2. Compounding NAV, Win Rate & Capital Compounding
3. Real-Time Prediction Verifications:
   - Predicted Price vs Exact Actual Price that arrived after elapsed time
   - Exact Range Hits (did market price reach predicted value?)
   - Return Accuracy & Direction Match Rate
   - Mean Absolute Error (MAE)
"""

import os
import sys
import time
import json
import requests
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://localhost:8000"

def get_server_health():
    try:
        r = requests.get(f"{BASE_URL}/api/health", timeout=3)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def get_market_status():
    try:
        r = requests.get(f"{BASE_URL}/api/market-status", timeout=3)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}

def get_trader_state():
    try:
        r = requests.get(f"{BASE_URL}/api/state", timeout=3)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}

def get_prediction_verifications():
    try:
        r = requests.get(f"{BASE_URL}/api/predictions/verification?limit=20", timeout=3)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}

def run_monitor(max_cycles: int = 15, delay_sec: float = 3.0):
    print("=" * 80)
    print("        ALPHANSE REAL-TIME SERVER & PREDICTION VERIFICATION MONITOR")
    print(f"        Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("=" * 80)

    # Check server availability
    health = get_server_health()
    if not health:
        print("[ERROR] FastAPI server is not responding at http://localhost:8000.")
        print("Please ensure the uvicorn server is running.")
        return False

    print("[SUCCESS] Server is UP & HEALTHY! Beginning close monitoring...")
    print("-" * 80)

    for cycle in range(1, max_cycles + 1):
        state = get_trader_state()
        mkt = get_market_status()
        verif_data = get_prediction_verifications()
        acc = verif_data.get("accuracy", {})
        verifs = verif_data.get("verifications", [])

        print(f"\n>>> CYCLE {cycle}/{max_cycles} @ {datetime.now().strftime('%H:%M:%S')} <<<")
        print(f"Engine Status: {state.get('engine_status', 'UNKNOWN')} | Market Mode: {mkt.get('market_mode', 'N/A')} | Next Session: {mkt.get('next_market_open', 'N/A')}")
        
        # Portfolio metrics
        tot_cap = state.get("total_capital", 0.0)
        avail_cap = state.get("available_capital", 0.0)
        inv_cap = state.get("invested_capital", 0.0)
        mult = state.get("compounding_multiplier", 1.0)
        net_prof = state.get("total_net_profit", 0.0)
        trades_count = state.get("daily_trades_count", 0)
        target_trades = state.get("target_daily_trades", 15)
        win_rate = state.get("win_rate_pct", 0.0)
        open_pos = state.get("positions", {})

        print(f"PORTFOLIO: Total: INR {tot_cap:,.2f} | Available: INR {avail_cap:,.2f} | Invested: INR {inv_cap:,.2f}")
        print(f"COMPOUNDING: Multiplier: {mult}x | Net Profit: INR {net_prof:+,.2f} | Win Rate: {win_rate}% | Trades Today: {trades_count}/{target_trades}")
        print(f"ACTIVE POSITIONS: {len(open_pos)} open -> {list(open_pos.keys())}")

        # Prediction Accuracy & Exact Value Realization
        total_v = acc.get("total_verified", 0)
        range_hits = acc.get("exact_range_hits", 0)
        range_hit_rate = acc.get("exact_range_hit_rate_pct", 0.0)
        close_hits = acc.get("exact_close_hits", 0)
        close_hit_rate = acc.get("exact_close_hit_rate_pct", 0.0)
        dir_acc = acc.get("direction_accuracy_pct", 0.0)
        ret_err = acc.get("mean_abs_return_error_pct", 0.0)
        price_err = acc.get("mean_price_error_pct", 0.0)

        print("\n--- PREDICTION ACCURACY & REALIZED VALUES SUMMARY ---")
        print(f"Total Predictions Verified After Arrival: {total_v}")
        print(f"Exact Price Range Hits: {range_hits}/{total_v} ({range_hit_rate}%) -> Market reached exact predicted price")
        print(f"Exact Close Hits (<=0.1% diff): {close_hits}/{total_v} ({close_hit_rate}%)")
        print(f"Directional Prediction Accuracy: {dir_acc}%")
        print(f"Mean Absolute Return Error: {ret_err}% | Mean Price Error: {price_err}%")

        if verifs:
            print("\nRecent Predictions vs Exact Realized Market Values (Last 8):")
            print(f"{'Time':<8} | {'Stock':<12} | {'Pred Price':<11} | {'Actual Price':<12} | {'Exact Reached?':<15} | {'Pred Ret':<9} | {'Act Ret':<9} | {'Dir':<7} | {'Abs Err'}")
            print("-" * 105)
            for v in verifs[-8:]:
                res_time = v.get("resolved_at", "")
                if "T" in res_time:
                    res_time = res_time.split("T")[1][:8]
                sym = v.get("symbol", "").replace(".NS", "")
                pp = v.get("predicted_price", 0.0)
                ap = v.get("actual_price", 0.0)
                exact_hit = "YES (EXACT)" if v.get("exact_range_reached") else f"NO ({v.get('price_error_pct', 0.0):.2f}%)"
                pr = f"{v.get('predicted_return_pct', 0.0):+.2f}%"
                ar = f"{v.get('actual_return_pct', 0.0):+.2f}%"
                dir_match = "MATCH" if v.get("direction_correct") else "MISS"
                err = f"{v.get('return_error_pct', 0.0):.2f}%"
                print(f"{res_time:<8} | {sym:<12} | INR {pp:<7.2f} | INR {ap:<8.2f} | {exact_hit:<15} | {pr:<9} | {ar:<9} | {dir_match:<7} | {err}")

        time.sleep(delay_sec)

    print("\n" + "=" * 80)
    print("MONITORING SUMMARY REPORT COMPLETED.")
    print("=" * 80)
    return True

if __name__ == "__main__":
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    run_monitor(max_cycles=cycles, delay_sec=interval)
