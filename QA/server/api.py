"""
FastAPI Server & WebSocket Hub for 1-Minute NSE Prediction & Compounding Engine.

Provides:
- REST API for manual capital adjustments (deposit/withdraw/re-base)
- Real-time WebSockets streaming 1-min predictions, trades, and compounding NAV
- Control endpoints (start, pause, emergency close)
- Interactive OHLCV candle data for charts
- Serves the Website and App frontends
"""

import os
import sys
import json
import asyncio
from typing import List
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from engine.compounding_trader import CompoundingTrader
from engine.ai_agent_supervisor import AIAgentSupervisor
from stocks_config import STOCK_UNIVERSE, STOCK_SYMBOLS

app = FastAPI(title="NSE 1-Min Prediction & Compounding Trading Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global trader instance
trader = CompoundingTrader(starting_capital=100000.0)

# Global Autonomous AI Agent Supervisor
ai_supervisor = AIAgentSupervisor(trader_ref=trader)

# Active WebSocket connections & Main AsyncIO Loop
connected_clients: List[WebSocket] = []
MAIN_EVENT_LOOP = None


def broadcast_event(event_type: str, data: dict):
    """Callback triggered by CompoundingTrader to push events to WebSockets."""
    global MAIN_EVENT_LOOP
    if not connected_clients:
        return

    message = json.dumps({"event": event_type, "data": data, "timestamp": datetime.now().isoformat()}, default=str)

    loop = MAIN_EVENT_LOOP
    if not loop or not loop.is_running():
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None

    if loop and loop.is_running():
        for ws in list(connected_clients):
            try:
                asyncio.run_coroutine_threadsafe(ws.send_text(message), loop)
            except Exception:
                pass


trader.register_subscriber(broadcast_event)

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------

class CapitalAdjustmentRequest(BaseModel):
    action: str          # "deposit" | "withdraw" | "set_capital"
    amount: float
    note: str = ""

class SettingsRequest(BaseModel):
    profit_threshold_pct: float = None
    stop_loss_pct: float = None
    position_sizing_pct: float = None
    target_daily_trades: int = None
    simulation_speed_sec: float = None
    off_market_simulation: bool = None

class ControlRequest(BaseModel):
    action: str          # "start" | "pause" | "emergency_close" | "scan_now"

class ManualTradeRequest(BaseModel):
    symbol: str
    action: str          # "BUY" | "SELL"
    amount: float = 10000.0

class ModelTuneRequest(BaseModel):
    profit_threshold_pct: float = None
    stop_loss_pct: float = None
    position_sizing_pct: float = None

class ExecutePlanRequest(BaseModel):
    plan_id: str

class ToggleAutopilotRequest(BaseModel):
    enabled: bool = None

# -----------------------------------------------------------------------------
# REST Endpoints
# -----------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup():
    """Ensure the automated engine is running autonomously on server start."""
    global MAIN_EVENT_LOOP
    try:
        MAIN_EVENT_LOOP = asyncio.get_running_loop()
    except RuntimeError:
        MAIN_EVENT_LOOP = asyncio.get_event_loop()
    trader.start_engine()
    ai_supervisor.start()
    print("Autonomous trading engine & AI Agent Supervisor auto-started on server startup.")

@app.get("/api/health")
async def get_health():
    return {"status": "ok", "time": datetime.now().isoformat()}

# -----------------------------------------------------------------------------
# Autonomous AI Agent Supervisor Endpoints
# -----------------------------------------------------------------------------

@app.get("/api/agent/status")
def get_agent_status():
    """Returns real-time surveillance status, tri-surface telemetry, thought stream, and action plans."""
    return ai_supervisor.get_status()

@app.post("/api/agent/generate-plan")
def trigger_agent_sweep():
    """Triggers an immediate diagnostic sweep across Web, Mobile, and Simulation Lab."""
    return ai_supervisor.run_diagnostic_sweep()

@app.post("/api/agent/execute-plan")
def execute_agent_plan_endpoint(req: ExecutePlanRequest):
    """Executes a formulated action plan (retraining, parameter tuning, risk buffer)."""
    res = ai_supervisor.execute_plan(req.plan_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res

@app.post("/api/agent/toggle-autopilot")
def toggle_autopilot_endpoint(req: ToggleAutopilotRequest = None):
    """Toggles autonomous action plan execution on/off."""
    enabled_val = req.enabled if req else None
    new_state = ai_supervisor.toggle_autopilot(enabled_val)
    return {"success": True, "autopilot_enabled": new_state}

@app.get("/api/market-status")
async def get_market_status():
    """Return Indian Stock Market status, hours, and autonomous schedule."""
    return trader.get_market_status()

@app.get("/api/state")
def get_state():
    """Return full portfolio capital, active positions, and compounding state."""
    summary = trader.get_summary()
    summary["market_status"] = trader.get_market_status()
    summary["signals"] = trader.state.get("last_signals", [])
    summary["last_signals"] = trader.state.get("last_signals", [])
    return summary

@app.get("/api/signals")
def get_signals():
    """Return latest 1-minute predictions across all 10 NSE stocks."""
    signals = trader.state.get("last_signals", [])
    if not signals or not trader.is_market_open():
        pred_path = os.path.join(PROJECT_ROOT, "logs", "tomorrow_opening_predictions.json")
        if os.path.exists(pred_path):
            try:
                with open(pred_path, "r", encoding="utf-8") as f:
                    preds_data = json.load(f)
                    signals = preds_data.get("predictions", signals)
            except Exception:
                pass
    return {"signals": signals}

@app.get("/api/predictions/verification")
def get_prediction_verifications(limit: int = 50):
    """Return historical verified predictions vs exact realized market values after time arrived, sorted newest first."""
    all_verifs = trader.state.get("prediction_verifications", [])
    recent = list(reversed(all_verifs))[:limit]
    return {
        "accuracy": trader.state.get("prediction_accuracy", {}),
        "verifications": recent,
        "total_count": len(all_verifs),
        "pending_count": len(trader.pending_predictions)
    }

@app.get("/api/stocks/profiles")
def get_stock_profiles():
    """Return per-symbol directional accuracy, confidence multipliers, and blacklist status."""
    return {
        "profiles": trader.confidence_tracker.get_all_profiles(),
        "blacklisted": list(trader.stock_blacklist),
        "active_trading": [s for s in STOCK_SYMBOLS if s not in trader.stock_blacklist]
    }

@app.get("/api/trades")
def get_trades(limit: int = 200, date_filter: str = "session"):
    """Return executed trade records for active session or specified date, sorted newest first."""
    return {"trades": trader.get_trade_history(limit=limit, date_filter=date_filter, reverse=True)}

@app.get("/api/trades/history")
def get_all_trade_history(limit: int = 1000, date: str = None, symbol: str = None):
    """Return complete trade history across all sessions/dates with optional date & symbol filtering."""
    date_filter = date if date else "all"
    trades = trader.get_trade_history(limit=limit, date_filter=date_filter, reverse=True)
    if symbol:
        clean_sym = symbol.upper().replace(".NS", "")
        trades = [t for t in trades if clean_sym in t.get("symbol", "").upper()]
    return {
        "total": len(trades),
        "trades": trades,
        "dates_summary": trader.get_trade_dates_summary()
    }

@app.get("/api/trades/dates-summary")
def get_trade_dates_summary():
    """Return summary performance metrics for each trading date for Settings History."""
    return {"dates": trader.get_trade_dates_summary()}

@app.post("/api/session/new")
def start_new_session_endpoint():
    """Starts a fresh trading session and clears active session logs from the dashboard."""
    return trader.start_new_session()

@app.post("/api/session/clear-logs")
def clear_session_logs_endpoint():
    """Clears current session logs from the active dashboard view."""
    return trader.start_new_session()

@app.get("/api/compounding-curve")
def get_compounding_curve():
    """Return historical compounding NAV points."""
    return {"curve": trader.state.get("compounding_curve", [])}

@app.get("/api/adjustments")
def get_adjustments():
    """Return history of manual deposits and withdrawals."""
    return {"adjustments": trader.state.get("capital_adjustments", [])}

@app.get("/api/candles/{symbol}")
def get_candles(symbol: str, count: int = 60):
    """Return recent 1-minute OHLCV candles for interactive chart."""
    candles_df = trader.get_or_generate_candles(symbol, n_candles=count)
    if candles_df.empty:
        raise HTTPException(status_code=404, detail="Candles not found")
    data = candles_df.tail(count).to_dict(orient="records")
    return {"symbol": symbol, "company": STOCK_UNIVERSE.get(symbol, symbol), "candles": data}

@app.post("/api/capital/adjust")
def adjust_capital(req: CapitalAdjustmentRequest):
    """Manual money adjustment endpoint: Deposit, Withdraw, or Re-base capital."""
    act = req.action.lower()
    if act == "deposit":
        res = trader.deposit_capital(req.amount, req.note or "Manual Web Deposit")
    elif act == "withdraw":
        res = trader.withdraw_capital(req.amount, req.note or "Manual Web Withdrawal")
    elif act in ("set_capital", "rebase"):
        res = trader.set_capital_base(req.amount, req.note or "Manual Web Re-base")
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {req.action}")

    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@app.post("/api/settings")
def update_settings(req: SettingsRequest):
    """Update trading parameters (profit threshold, stop loss, sizing, target trades)."""
    settings_dict = {}
    if req.profit_threshold_pct is not None:
        settings_dict["profit_threshold_pct"] = req.profit_threshold_pct / 100.0 if req.profit_threshold_pct > 0.05 else req.profit_threshold_pct
    if req.stop_loss_pct is not None:
        settings_dict["stop_loss_pct"] = req.stop_loss_pct / 100.0 if req.stop_loss_pct > 0.05 else req.stop_loss_pct
    if req.position_sizing_pct is not None:
        settings_dict["position_sizing_pct"] = req.position_sizing_pct / 100.0 if req.position_sizing_pct > 1.0 else req.position_sizing_pct
    if req.target_daily_trades is not None:
        settings_dict["target_daily_trades"] = req.target_daily_trades
    if req.simulation_speed_sec is not None:
        settings_dict["simulation_speed_sec"] = req.simulation_speed_sec
    if req.off_market_simulation is not None:
        settings_dict["off_market_simulation"] = req.off_market_simulation

    return trader.update_settings(settings_dict)

@app.post("/api/control")
def control_engine(req: ControlRequest):
    """Start, pause, or emergency close positions."""
    act = req.action.lower()
    if act == "start":
        trader.start_engine()
        return {"success": True, "message": "Automated engine started."}
    elif act == "pause":
        trader.pause_engine()
        return {"success": True, "message": "Automated engine paused."}
    elif act == "emergency_close":
        actions = trader.emergency_close_all()
        return {"success": True, "message": f"Closed {len(actions)} open positions.", "actions": actions}
    elif act == "scan_now":
        res = trader.scan_and_trade_step()
        return {"success": True, "message": "Manual 1-minute scan executed.", "result": res}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown control action: {req.action}")

@app.post("/api/manual-trade")
def manual_trade(req: ManualTradeRequest):
    """Execute a manual buy or sell order."""
    res = trader.manual_order(req.symbol, req.action, req.amount)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@app.post("/api/model/retrain")
def trigger_retrain():
    """Triggers preprocessing, feature extraction, and model retraining on fresh market data."""
    import threading
    def _run():
        try:
            import pandas as pd
            from models.one_min_predictor import OneMinPredictor
            data_path = os.path.join(PROJECT_ROOT, "data", "processed", "master_labeled_dataset.parquet")
            if os.path.exists(data_path):
                df = pd.read_parquet(data_path)
                p = OneMinPredictor()
                p.train(df.sample(min(8000, len(df)), random_state=42))
                trader.predictor = p
                print("[Retrain] 1-Minute Model Retrained and reloaded into active trader.")
        except Exception as e:
            print(f"[Retrain] Error during retraining: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"success": True, "message": "1-Minute ML ensemble retraining launched in background."}

@app.post("/api/model/reload")
def reload_model():
    """Reloads the freshly trained 1-minute model artifacts into active trader."""
    try:
        from models.one_min_predictor import OneMinPredictor
        trader.predictor = OneMinPredictor()
        return {
            "success": True,
            "message": "1-Minute model reloaded successfully.",
            "features_count": len(trader.predictor.feature_cols),
            "features": trader.predictor.feature_cols
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/state/reload")
def reload_state():
    """Reloads compounding state and performs day rollover check."""
    try:
        trader._load_or_init_state(trader.state.get("starting_capital", 100000.0))
        return {
            "success": True,
            "message": "State reloaded successfully.",
            "state": trader.get_summary()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/model/predictions")
def get_offmarket_predictions():
    """Returns the latest off-market opening predictions for the universe stocks."""
    pred_path = os.path.join(PROJECT_ROOT, "logs", "tomorrow_opening_predictions.json")
    if os.path.exists(pred_path):
        try:
            with open(pred_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"predictions": [], "message": "No predictions generated yet."}

@app.get("/api/session/recap")
def get_session_recap():
    """Returns today's complete session statistics and execution breakdown."""
    recap_path = os.path.join(PROJECT_ROOT, "logs", "live_metrics", "session_recap.json")
    if os.path.exists(recap_path):
        try:
            with open(recap_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"message": "Session recap not yet generated."}

@app.get("/api/model/metrics")
def get_model_metrics():
    """Returns the latest ML model training and evaluation metrics."""
    metrics_path = os.path.join(PROJECT_ROOT, "models", "saved_models_1m", "model_metrics_1m.json")
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"message": "Model metrics not available."}

@app.post("/api/model/retrain_live")
def trigger_retrain_live():
    """Launches full retraining with real 1m candles in background and hot-reloads models."""
    import threading
    def _run():
        try:
            import subprocess
            cmd = [sys.executable, os.path.join(PROJECT_ROOT, "scripts", "build_and_train_live_1m.py")]
            res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
            print("[Retrain Live] Finished with code:", res.returncode)
            from models.one_min_predictor import OneMinPredictor
            trader.predictor = OneMinPredictor()
            # Also regenerate predictions
            cmd2 = [sys.executable, os.path.join(PROJECT_ROOT, "scripts", "predict_universe_offmarket.py")]
            subprocess.run(cmd2, cwd=PROJECT_ROOT, capture_output=True, text=True)
            print("[Retrain Live] Models and Predictions refreshed successfully.")
        except Exception as e:
            print(f"[Retrain Live] Error: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"success": True, "message": "Overnight 1-minute ML retraining and optimization launched in background."}

@app.post("/api/model/tune_parameters")
def tune_parameters(req: ModelTuneRequest):
    """Adjusts intraday efficiency parameters and hot-applies to engine."""
    with trader.lock:
        if req.profit_threshold_pct is not None:
            trader.profit_threshold_pct = max(0.001, float(req.profit_threshold_pct))
        if req.stop_loss_pct is not None:
            trader.stop_loss_pct = max(0.001, float(req.stop_loss_pct))
        if req.position_sizing_pct is not None:
            trader.position_sizing_pct = min(0.50, max(0.02, float(req.position_sizing_pct)))
        trader._save_state()
        return {
            "success": True,
            "message": "Efficiency parameters updated and hot-applied.",
            "profit_threshold_pct": trader.profit_threshold_pct,
            "stop_loss_pct": trader.stop_loss_pct,
            "position_sizing_pct": trader.position_sizing_pct
        }


# -----------------------------------------------------------------------------
# WebSocket for Live Real-Time Updates
# -----------------------------------------------------------------------------

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    global MAIN_EVENT_LOOP
    try:
        MAIN_EVENT_LOOP = asyncio.get_running_loop()
    except RuntimeError:
        pass
    await websocket.accept()
    connected_clients.append(websocket)
    # Send initial state snapshot upon connection
    initial_payload = {
        "event": "INITIAL_STATE",
        "data": {
            "state": trader.get_summary(),
            "signals": trader.state.get("last_signals", []),
            "recent_trades": trader.get_trade_history(limit=50, date_filter="session", reverse=True),
            "compounding_curve": trader.state.get("compounding_curve", [])[-30:],
            "verifications": list(reversed(trader.state.get("prediction_verifications", [])))[:30]
        },
        "timestamp": datetime.now().isoformat()
    }
    await websocket.send_text(json.dumps(initial_payload))

    try:
        while True:
            # Keep connection alive and receive ping/messages from client
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
    except Exception:
        if websocket in connected_clients:
            connected_clients.remove(websocket)

@app.get("/api/analysis/deviations")
def get_prediction_deviations():
    """
    Analyzes prediction errors vs real market values, identifies loopholes,
    and provides actionable self-improvement recommendations for high-quality predictions.
    """
    verifs = trader.state.get("prediction_verifications", [])
    if not verifs:
        return {
            "total_verified": 0,
            "message": "No verification records collected yet.",
            "deviations": [],
            "loopholes": {},
            "recommendations": {}
        }

    total = len(verifs)
    dir_correct = sum(1 for v in verifs if v.get("direction_correct"))
    exact_close = sum(1 for v in verifs if v.get("exact_close_hit"))
    exact_range = sum(1 for v in verifs if v.get("exact_range_reached"))

    price_errs = [v.get("price_error_pct", 0.0) for v in verifs if "price_error_pct" in v]
    ret_errs = [v.get("return_error_pct", 0.0) for v in verifs if "return_error_pct" in v]

    mean_price_err = round(sum(price_errs) / max(1, len(price_errs)), 3)
    mean_ret_err = round(sum(ret_errs) / max(1, len(ret_errs)), 3)
    dir_acc_pct = round((dir_correct / max(1, total)) * 100.0, 1)

    # Loophole & Error Diagnostics
    whipsaw_count = 0
    opening_err_count = 0
    stagnant_count = 0

    detailed_deviations = []
    symbol_stats = {}

    for v in reversed(verifs):
        pred_p = v.get("predicted_price", 0.0)
        act_p = v.get("actual_price", 0.0)
        pred_ret = v.get("predicted_return_pct", 0.0)
        act_ret = v.get("actual_return_pct", 0.0)
        sym = v.get("symbol", "")

        # Deviation percentage: ((Actual - Predicted) / Actual) * 100
        dev_pct = round(((act_p - pred_p) / (act_p + 1e-9)) * 100.0, 3) if act_p else 0.0
        ret_dev_pct = round(act_ret - pred_ret, 3)

        # Loophole detection:
        pred_time = v.get("predicted_at", "")
        # Opening trap (09:15 - 09:30)
        if "T09:1" in pred_time or "T09:2" in pred_time:
            opening_err_count += 1
        # Whipsaw trap (predicted positive, actual negative with high wick)
        if pred_ret > 0.05 and act_ret < -0.05:
            whipsaw_count += 1
        # Stagnant flatline
        if abs(act_ret) < 0.02 and abs(pred_ret) > 0.05:
            stagnant_count += 1

        if sym not in symbol_stats:
            symbol_stats[sym] = {"total": 0, "hits": 0, "errs": []}
        symbol_stats[sym]["total"] += 1
        if v.get("direction_correct"):
            symbol_stats[sym]["hits"] += 1
        symbol_stats[sym]["errs"].append(abs(dev_pct))

        if len(detailed_deviations) < 60:
            detailed_deviations.append({
                "symbol": sym,
                "company": v.get("company", sym),
                "timestamp": pred_time[:19].replace("T", " "),
                "predicted_price": pred_p,
                "actual_price": act_p,
                "price_deviation_pct": dev_pct,
                "predicted_return_pct": pred_ret,
                "actual_return_pct": act_ret,
                "return_deviation_pct": ret_dev_pct,
                "direction_correct": v.get("direction_correct", False),
                "exact_close_hit": v.get("exact_close_hit", False),
                "exact_range_reached": v.get("exact_range_reached", False),
                "signal": v.get("signal", "HOLD"),
                "confidence": v.get("confidence", 0.0)
            })

    # Rank stock symbols by precision
    ranked_symbols = []
    for sym, sdata in symbol_stats.items():
        hit_rate = round((sdata["hits"] / max(1, sdata["total"])) * 100.0, 1)
        avg_err = round(sum(sdata["errs"]) / max(1, len(sdata["errs"])), 3)
        ranked_symbols.append({
            "symbol": sym,
            "total_predictions": sdata["total"],
            "directional_accuracy_pct": hit_rate,
            "avg_price_deviation_pct": avg_err
        })
    ranked_symbols.sort(key=lambda x: x["directional_accuracy_pct"], reverse=True)

    # Actionable self-improvement recommendations
    recommendations = {
        "recommended_hurdle_pct": 0.18 if mean_ret_err < 0.10 else 0.22,
        "recommended_stop_loss_pct": 0.28,
        "recommended_min_confidence": 65.0,
        "recommended_max_spread_pct": 0.04,
        "whipsaw_risk_level": "HIGH" if (whipsaw_count / max(1, total)) > 0.25 else "MODERATE",
        "opening_caution_needed": bool(opening_err_count > 5),
        "primary_bottleneck": (
            "Opening Auction Volatility" if opening_err_count > whipsaw_count and opening_err_count > 10
            else "Intra-Bar Wick Pressure (Whipsaws)" if whipsaw_count > 15
            else "Low Volume Stagnation" if stagnant_count > 20
            else "Model Prediction Variance Balanced"
        ),
        "suggested_actions": [
            "Enforce 09:15 - 09:20 AM cool-off to eliminate opening spread traps.",
            "Require Micro-RSI confirmation (avoid buying when RSI > 75).",
            "Filter signals with Confidence < 65% to eliminate low-conviction noise.",
            "Cap position allocations on small capital accounts (<= ₹10K) to avoid single-share over-concentration."
        ]
    }

    return {
        "summary": {
            "total_verified": total,
            "direction_accuracy_pct": dir_acc_pct,
            "mean_price_deviation_pct": mean_price_err,
            "mean_return_deviation_pct": mean_ret_err,
            "exact_close_hit_rate_pct": round((exact_close / max(1, total)) * 100.0, 1),
            "exact_range_hit_rate_pct": round((exact_range / max(1, total)) * 100.0, 1)
        },
        "loopholes": {
            "whipsaw_errors_count": whipsaw_count,
            "whipsaw_error_rate_pct": round((whipsaw_count / max(1, total)) * 100.0, 1),
            "opening_trap_count": opening_err_count,
            "stagnation_trap_count": stagnant_count,
        },
        "recommendations": recommendations,
        "symbol_rankings": ranked_symbols,
        "recent_deviations": detailed_deviations
    }


# -----------------------------------------------------------------------------
# Static Files & SPA Routing
# -----------------------------------------------------------------------------

STATIC_DIR = os.path.join(PROJECT_ROOT, "frontend", "static")
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_website():
    """Serves the Standalone Website Control & Treasury Portal."""
    site_path = os.path.join(STATIC_DIR, "website.html")
    if os.path.exists(site_path):
        return FileResponse(site_path)
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Website Portal Initializing... Please refresh in a moment.</h1>")

@app.get("/website")
def serve_website_alias():
    """Alias route for the standalone Website Portal."""
    return serve_website()

@app.get("/app")
def serve_app():
    """Serves the Standalone Live App Monitor view."""
    app_path = os.path.join(STATIC_DIR, "app.html")
    if os.path.exists(app_path):
        return FileResponse(app_path)
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>App Initializing...</h1>")

@app.get("/lab")
@app.get("/aftermarket")
@app.get("/sim")
def serve_lab():
    """Serves the Dedicated After-Market & Simulation AI Lab Studio."""
    lab_path = os.path.join(STATIC_DIR, "lab.html")
    if os.path.exists(lab_path):
        return FileResponse(lab_path)
    return HTMLResponse("<h1>AI Lab Studio Initializing...</h1>")
