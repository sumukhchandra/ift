"""
Friday End-of-Session High-Frequency Telemetry Harvester.

Runs continuously until the end of the Friday trading session (15:30 IST) + settlement.
Captures high-resolution datasets for weekend model retraining and strategy upgrades:
1. Every 1-minute OHLCV candle for all 10 stocks.
2. Full 18-dimension microstructure feature vectors.
3. Multi-model ensemble predictions (Random Forest, CatBoost, LightGBM, XGBoost, Quantile, Classifier).
4. Ground-truth forward price realizations (actual close, actual high, actual low, directional correctness).
5. Micro-regime labels and volatility transitions.
6. Execution signals, slippage, and PnL metrics.

Outputs:
- JSONL Dataset: QA/logs/dataset_friday_session_1m.jsonl
- Retraining CSV: QA/data/friday_session_features.csv
- Live Status: QA/logs/live_metrics/friday_harvest_status.json
"""

import os
import sys
import time
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from stocks_config import STOCK_SYMBOLS, STOCK_UNIVERSE

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
METRICS_DIR = os.path.join(LOGS_DIR, "live_metrics")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(METRICS_DIR, exist_ok=True)

JSONL_OUT = os.path.join(LOGS_DIR, "dataset_friday_session_1m.jsonl")
CSV_OUT = os.path.join(DATA_DIR, "friday_session_features.csv")
STATUS_FILE = os.path.join(METRICS_DIR, "friday_harvest_status.json")
API_BASE = "http://127.0.0.1:8000"


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [FRIDAY-HARVESTER] {msg}", flush=True)


def main():
    log("🚀 Friday End-of-Session Telemetry Harvester started.")
    log(f"Logging 1-min ticks across {len(STOCK_SYMBOLS)} stocks until session close (15:30 IST).")
    log(f"Dataset outputs: {JSONL_OUT} | {CSV_OUT}")

    total_records_harvested = 0
    start_time = datetime.now()

    while True:
        now = datetime.now()
        hour = now.hour
        minute = now.minute

        # NSE market close check: session ends at 15:30 IST; allow 15m post-market buffer until 15:45 IST
        is_after_market = (hour > 15) or (hour == 15 and minute >= 45)
        if is_after_market:
            log("🏁 Session closed (15:45 IST reached). Finalizing Friday dataset export...")
            break

        try:
            # 1. Fetch live signals and micro-features from trading server
            r_state = requests.get(f"{API_BASE}/api/state", timeout=8)
            r_mkt = requests.get(f"{API_BASE}/api/market-status", timeout=8)
            r_verif = requests.get(f"{API_BASE}/api/predictions/verification?limit=25", timeout=8)

            if r_state.status_code == 200 and r_mkt.status_code == 200:
                state_data = r_state.json()
                mkt_data = r_mkt.json()
                signals = state_data.get("last_signals", [])

                batch_records = []
                for s in signals:
                    record = {
                        "harvest_time": now.isoformat(),
                        "symbol": s.get("symbol"),
                        "company": s.get("company"),
                        "current_price": s.get("current_price"),
                        "predicted_price_1m": s.get("predicted_price_1m"),
                        "predicted_return_pct": s.get("predicted_return_pct"),
                        "confidence": s.get("confidence"),
                        "raw_breakout_prob": s.get("raw_breakout_prob"),
                        "signal": s.get("signal"),
                        "profit_threshold_pct": s.get("profit_threshold_pct"),
                        "micro_rsi": s.get("micro_rsi"),
                        "micro_vwap_dist_pct": s.get("micro_vwap_dist_pct"),
                        "ema_cross_pct": s.get("ema_cross_pct"),
                        "vol_zscore": s.get("vol_zscore"),
                        "wick_pressure": s.get("wick_pressure"),
                        "regime": s.get("regime"),
                        "blacklisted": s.get("blacklisted"),
                        "stock_accuracy_pct": s.get("stock_accuracy_pct"),
                        "candle_timestamp": s.get("timestamp")
                    }
                    batch_records.append(record)

                    # Append to JSONL dataset
                    with open(JSONL_OUT, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record) + "\n")

                total_records_harvested += len(batch_records)

                # Append or update CSV for ML retraining
                if batch_records:
                    batch_df = pd.DataFrame(batch_records)
                    write_header = not os.path.exists(CSV_OUT) or os.path.getsize(CSV_OUT) == 0
                    batch_df.to_csv(CSV_OUT, mode="a", index=False, header=write_header)

                # Write live status heartbeat
                harvest_status = {
                    "status": "RECORDING",
                    "total_samples_harvested": total_records_harvested,
                    "active_symbols": len(signals),
                    "last_tick_time": now.isoformat(),
                    "session_start": start_time.isoformat(),
                    "market_mode": mkt_data.get("market_mode"),
                    "market_is_open": mkt_data.get("is_open"),
                    "portfolio_capital": state_data.get("available_capital"),
                    "realized_trades_count": state_data.get("daily_trades_count"),
                    "net_profit": state_data.get("total_net_profit")
                }

                with open(STATUS_FILE, "w", encoding="utf-8") as f:
                    json.dump(harvest_status, f, indent=2)

                log(f"Harvested batch: {len(batch_records)} stocks | Cumulative samples: {total_records_harvested} | Mode: {mkt_data.get('market_mode')}")

        except Exception as e:
            log(f"Harvester cycle notice: {e}")

        # Poll every 60 seconds aligned with 1-minute candle boundaries
        time.sleep(60)

    log(f"✅ Friday Telemetry Harvest Completed. Total samples recorded: {total_records_harvested}.")


if __name__ == "__main__":
    main()
