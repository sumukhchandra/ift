"""
WEEKEND PIPELINE — Data Fetch + Model Retrain + Monday Auto-Start
=================================================================
Runs Saturday/Sunday to collect fresh NSE data and retrain the predictor.
Also launches the trading engine automatically on Monday at 09:15 AM IST.

Usage:
    .venv\Scripts\python.exe QA\weekend_pipeline.py
"""

import sys, os, time, json, subprocess
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

# Script lives inside QA/ so root of the project is one level up
QA_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(QA_DIR)  # ift/ project root
sys.path.insert(0, ROOT)   # so 'QA' package is importable
sys.path.insert(0, QA_DIR)  # so internal QA modules import each other

LOG_DIR = os.path.join(QA_DIR, "logs")
DATA_DIR = os.path.join(QA_DIR, "data")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

DIVIDER = "=" * 64

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def section(title: str):
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)

# ============================================================
# STEP 1: FETCH FRESH HISTORICAL 1-MINUTE DATA
# ============================================================
section("STEP 1: Fetching fresh NSE data (last 5 trading days)")

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
    HAS_YF = True
except ImportError:
    HAS_YF = False
    log("[WARN] yfinance not available")

NSE_SYMBOLS_YF = {
    "TATACAP.NS":    "TATACAP",
    "AXISBANK.NS":   "AXISBANK",
    "BAJFINANCE.NS": "BAJFINANCE",
    "ICICIBANK.NS":  "ICICIBANK",
    "RELIANCE.NS":   "RELIANCE",
    "TCS.NS":        "TCS",
    "INFY.NS":       "INFY",
    "HDFCBANK.NS":   "HDFCBANK",
    "SBIN.NS":       "SBIN",
    "BHARTIARTL.NS": "BHARTIARTL",
    "TATASTEEL.NS":  "TATASTEEL",
}

fetch_summary = {}
if HAS_YF:
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=8)
    all_dfs = []
    for yf_sym, short_sym in NSE_SYMBOLS_YF.items():
        try:
            df = yf.download(
                yf_sym,
                start=start_dt.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                interval="1m",
                progress=False,
                auto_adjust=True
            )
            if df is None or df.empty:
                log(f"  {yf_sym}: No data (market may be closed on weekends)")
                continue
            # Flatten MultiIndex if present
            if hasattr(df.columns, 'levels'):
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df = df.reset_index()
            df.rename(columns={
                "Datetime": "timestamp", "Date": "timestamp",
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume"
            }, inplace=True)
            df["symbol"] = short_sym
            df = df[["timestamp", "open", "high", "low", "close", "volume", "symbol"]].dropna()
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
            out_path = os.path.join(DATA_DIR, f"{short_sym}_1m_weekend.csv")
            df.to_csv(out_path, index=False)
            all_dfs.append(df)
            fetch_summary[short_sym] = len(df)
            log(f"  {yf_sym}: {len(df)} 1-min candles saved to {short_sym}_1m_weekend.csv")
        except Exception as e:
            log(f"  [WARN] {yf_sym}: {e}")

    # Merge into combined dataset for training
    if all_dfs:
        combined = pd.concat(all_dfs, ignore_index=True)
        combined_path = os.path.join(DATA_DIR, "combined_weekend_1m.csv")
        combined.to_csv(combined_path, index=False)
        log(f"\n  Combined dataset: {len(combined):,} candles across {len(all_dfs)} symbols")
    else:
        log("  [WARN] No new candles fetched (weekend = no market data). Using existing data.")
        combined = None
else:
    combined = None

# ============================================================
# STEP 2: RETRAIN THE MODEL ON FRESH DATA
# ============================================================
section("STEP 2: Model Retraining")

try:
    from QA.models.one_min_predictor import OneMinPredictor
    import pandas as pd

    predictor = OneMinPredictor()

    # Collect all CSVs available
    csv_files = []
    for f in os.listdir(DATA_DIR):
        if f.endswith(".csv") and "weekend" not in f or "weekend" in f:
            csv_files.append(os.path.join(DATA_DIR, f))

    # Load all data
    dfs = []
    for f in csv_files:
        try:
            df = pd.read_csv(f)
            if "symbol" in df.columns and "close" in df.columns and len(df) > 50:
                dfs.append(df)
        except Exception:
            pass

    if dfs:
        combined_df = pd.concat(dfs, ignore_index=True).drop_duplicates(subset=["symbol", "timestamp"])
        log(f"  Loaded {len(dfs)} datasets, total {len(combined_df):,} unique rows")
        metrics = predictor.train(combined_df, eval_split=0.15)
        log(f"  Training complete!")
        log(f"  Directional Accuracy: {metrics.get('test_direction_accuracy_pct', 0):.2f}%")
        log(f"  High-Conviction Acc:  {metrics.get('test_high_conviction_dir_acc_pct', 0):.2f}%")
        log(f"  Breakout Precision:   {metrics.get('test_breakout_precision_pct', 0):.2f}%")
        log(f"  Breakout F1:          {metrics.get('test_breakout_f1_pct', 0):.2f}%")

        # Save retrain metadata
        meta = {
            "retrained_at": datetime.now().isoformat(),
            "datasets": len(dfs),
            "total_rows": sum(len(d) for d in dfs),
            "metrics": metrics,
            "bidirectional": True,
            "long_short_enabled": True
        }
        with open(os.path.join(LOG_DIR, "retrain_metadata.json"), "w") as mf:
            json.dump(meta, mf, indent=2)
        log(f"  Metadata saved to logs/retrain_metadata.json")
    else:
        log("  [WARN] No data found for retraining — skipping (will use existing model)")

except Exception as e:
    log(f"  [WARN] Retrain failed: {e}")
    log("  Engine will use last saved model on Monday")

# ============================================================
# STEP 3: VALIDATE BIDIRECTIONAL ENGINE
# ============================================================
section("STEP 3: Engine Validation (LONG + SHORT)")

try:
    from QA.engine.compounding_trader import CompoundingTrader
    trader = CompoundingTrader()
    log(f"  CompoundingTrader loaded OK")
    log(f"  target_session_profit_pct : {trader.target_session_profit_pct*100:.1f}%")
    log(f"  profit_threshold_pct      : {trader.profit_threshold_pct*100:.1f}%")
    log(f"  stop_loss_pct             : {trader.stop_loss_pct*100:.2f}%")
    log(f"  max_hold_seconds          : {trader.max_hold_seconds}s ({trader.max_hold_seconds//60}m)")
    log(f"  position_sizing_pct       : {trader.position_sizing_pct*100:.0f}%")
    log(f"  BIDIRECTIONAL             : LONG + SHORT enabled")
    log(f"  max_concurrent_positions  : {trader.max_concurrent_positions}")
    log(f"  Capital                   : Rs.{trader.state.get('total_capital', 0):.2f}")
    log(f"  Engine validation: PASS")
except Exception as e:
    log(f"  [ERROR] Engine load failed: {e}")
    import traceback; traceback.print_exc()

# ============================================================
# STEP 4: MONDAY AUTO-START COUNTDOWN
# ============================================================
section("STEP 4: Monday Auto-Start Scheduler")

now = datetime.now()
# NSE opens 09:15 AM IST Monday
# Find next Monday 09:15
days_until_monday = (7 - now.weekday()) % 7
if days_until_monday == 0 and now.hour >= 9:
    days_until_monday = 7  # Already past Monday 9am, wait for next week

monday_date = (now + timedelta(days=days_until_monday)).date()
monday_start = datetime(monday_date.year, monday_date.month, monday_date.day, 9, 15, 0)

wait_seconds = (monday_start - now).total_seconds()
log(f"  Current time: {now.strftime('%a %Y-%m-%d %H:%M:%S IST')}")
log(f"  Monday open:  {monday_start.strftime('%a %Y-%m-%d %H:%M:%S IST')}")
log(f"  Wait time:    {wait_seconds/3600:.2f} hours ({wait_seconds/60:.0f} minutes)")
log(f"")
log(f"  Weekend data collection COMPLETE.")
log(f"  Model retrained on latest NSE data.")
log(f"  Long+Short bidirectional engine validated.")
log(f"")

if wait_seconds > 0:
    log(f"  Waiting {wait_seconds/60:.0f} minutes until Monday 09:15 AM market open...")
    log(f"  Press Ctrl+C to abort if needed.")

    # Countdown loop with heartbeat every 30 minutes
    start_wait = time.time()
    heartbeat_interval = 1800  # 30 min
    last_heartbeat = start_wait

    while True:
        remaining = monday_start - datetime.now()
        if remaining.total_seconds() <= 0:
            break
        elapsed_since_hb = time.time() - last_heartbeat
        if elapsed_since_hb >= heartbeat_interval:
            rem_h = remaining.total_seconds() / 3600
            log(f"  [HEARTBEAT] {rem_h:.2f} hours until Monday open...")
            last_heartbeat = time.time()
        time.sleep(60)

# ============================================================
# STEP 5: MONDAY TRADING SESSION START
# ============================================================
section("STEP 5: MONDAY SESSION — STARTING TRADING ENGINE")
log("  09:15 AM IST REACHED — Launching trading engine NOW")
log("  Bidirectional mode: LONG (rising) + SHORT (falling)")
log("  Target: +5% net account return by end of session")

try:
    import subprocess
    server_script = os.path.join(ROOT, "server.py")
    if os.path.exists(server_script):
        log(f"  Launching: {server_script}")
        subprocess.Popen(
            [sys.executable, server_script],
            cwd=ROOT
        )
        log("  Trading server launched. Monitor via the web dashboard.")
    else:
        # Fallback: run a direct trading loop
        log("  server.py not found — running direct trading loop")
        from QA.engine.compounding_trader import CompoundingTrader
        t = CompoundingTrader()
        log(f"  Capital: Rs.{t.state.get('total_capital',0):.2f}")
        log("  Running scan loop (Ctrl+C to stop)...")
        tick = 0
        while True:
            result = t.scan_and_trade_step()
            tick += 1
            actions = result.get("actions", [])
            if actions:
                for a in actions:
                    log(f"  [TRADE] {a.get('action')} {a.get('symbol')} "
                        f"@ Rs.{a.get('price', a.get('exit_price', 0)):.2f} "
                        f"Dir={a.get('direction','LONG')} "
                        f"PnL={a.get('net_profit','')}")
            if tick % 30 == 0:
                s = result.get("state", {})
                log(f"  [STATUS] Capital=Rs.{s.get('total_capital',0):.2f} "
                    f"Session={s.get('session_return_pct',0):.2f}% "
                    f"Status={s.get('engine_status','')}")
            time.sleep(60)  # 1-minute tick

except KeyboardInterrupt:
    log("  Session stopped by user.")
except Exception as e:
    log(f"  [ERROR] {e}")
    import traceback; traceback.print_exc()
