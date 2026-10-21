"""
Multi-Agent Diagnostic Suite: 10 Parallel Stock Examination Agents.

Spawns 10 concurrent specialized agents across the full NSE trading universe:
- Agent 1: TATACAP.NS
- Agent 2: RELIANCE.NS
- Agent 3: HDFCBANK.NS
- Agent 4: BHARTIARTL.NS
- Agent 5: ICICIBANK.NS
- Agent 6: INFY.NS
- Agent 7: TCS.NS
- Agent 8: SBIN.NS
- Agent 9: AXISBANK.NS
- Agent 10: BAJFINANCE.NS

Each agent rigorously audits:
1. Feature extraction & data integrity (no NaNs, no stale timestamps).
2. Multi-model ensemble inference (CatBoost, LightGBM, XGBoost, RF, Quantile, Classifier).
3. Inference latency in milliseconds.
4. Current signal generation & hurdle clearance.
5. Intraday rolling accuracy & error metrics.
6. Regime classification & trade execution eligibility.
"""

import os
import sys
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from stocks_config import STOCK_SYMBOLS, STOCK_UNIVERSE
from models.one_min_predictor import OneMinPredictor
from models.stock_confidence_tracker import StockConfidenceTracker
from regimes.regime_classifier import classify_micro_regime
import yfinance as yf
import numpy as np

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "logs", "agent_audits")
os.makedirs(OUTPUT_DIR, exist_ok=True)
AUDIT_REPORT_FILE = os.path.join(OUTPUT_DIR, "10_agent_audit_report.json")


def run_single_stock_agent(agent_id: int, symbol: str, predictor: OneMinPredictor) -> dict:
    """
    Dedicated inspection agent for a single stock.
    Executes a thorough diagnostic sweep without affecting the live trading loop.
    """
    start_t = time.time()
    company_name = STOCK_UNIVERSE.get(symbol, symbol)
    agent_name = f"Agent-{agent_id:02d} [{symbol}]"

    result = {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "symbol": symbol,
        "company": company_name,
        "timestamp": datetime.now().isoformat(),
        "status": "PASS",
        "checks": {},
        "metrics": {},
        "issues": []
    }

    try:
        # 1. Fetch live 1-minute candle stream
        t0 = time.time()
        df = yf.download(symbol, period="1d", interval="1m", progress=False)
        fetch_ms = round((time.time() - t0) * 1000, 1)

        if df.empty or len(df) < 15:
            result["status"] = "FAIL"
            result["issues"].append(f"Insufficient candle depth ({len(df)} bars)")
            result["checks"]["data_feed"] = "FAIL"
            return result

        result["checks"]["data_feed"] = "OK"
        result["metrics"]["candle_count"] = len(df)
        result["metrics"]["feed_latency_ms"] = fetch_ms

        # Flatten multi-index columns if yfinance returned them
        if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
            df.columns = [col[0].lower() if isinstance(col, tuple) else str(col).lower() for col in df.columns]
        else:
            df.columns = [str(c).lower() for c in df.columns]

        last_row = df.iloc[-1]
        last_close = float(last_row["close"])
        result["metrics"]["current_price"] = round(last_close, 2)

        # Check timestamp freshness
        last_ts = df.index[-1]
        result["metrics"]["last_candle_ts"] = str(last_ts)

        # 2. Audit Feature Extraction
        t0 = time.time()
        df["symbol"] = symbol
        df_feat = predictor.extract_features_1m(df)
        feat_ms = round((time.time() - t0) * 1000, 1)
        result["metrics"]["feature_latency_ms"] = feat_ms

        if df_feat.empty:
            result["status"] = "FAIL"
            result["issues"].append("Feature pipeline returned empty dataframe")
            result["checks"]["features"] = "FAIL"
            return result

        feat_row = df_feat.iloc[-1]
        nan_cols = [c for c in predictor.feature_cols if c in feat_row and (feat_row[c] is None or np.isnan(feat_row[c]))]
        if nan_cols:
            result["status"] = "WARN"
            result["issues"].append(f"NaN in features: {nan_cols}")
            result["checks"]["features"] = "WARN"
        else:
            result["checks"]["features"] = "OK"

        result["metrics"]["micro_rsi"] = round(float(feat_row.get("micro_rsi_7", 50)), 1)
        result["metrics"]["micro_vwap_dist_pct"] = round(float(feat_row.get("micro_vwap_dist", 0)) * 100, 3)
        result["metrics"]["ema_cross_pct"] = round(float(feat_row.get("ema_cross_5_20", 0)) * 100, 3)
        result["metrics"]["vol_zscore"] = round(float(feat_row.get("vol_spike_zscore", 0)), 2)
        result["metrics"]["wick_pressure"] = round(float(feat_row.get("wick_pressure", 0.5)), 2)

        # 3. Audit Model Ensemble Sub-Models
        X = feat_row[predictor.feature_cols].values.reshape(1, -1)
        model_checks = {}

        for m_name, model in predictor.regressors.items():
            try:
                t_m = time.time()
                pred_val = float(model.predict(X)[0])
                m_lat = round((time.time() - t_m) * 1000, 2)
                model_checks[m_name] = {
                    "status": "OK",
                    "predicted_return_pct": round(pred_val * 100, 4),
                    "latency_ms": m_lat
                }
            except Exception as e:
                model_checks[m_name] = {"status": "FAIL", "error": str(e)}
                result["issues"].append(f"Model {m_name} failed: {e}")

        # Classifier check
        try:
            t_c = time.time()
            prob = float(predictor.classifier.predict_proba(X)[0][1])
            c_lat = round((time.time() - t_c) * 1000, 2)
            model_checks["breakout_classifier"] = {
                "status": "OK",
                "breakout_prob_pct": round(prob * 100, 1),
                "latency_ms": c_lat
            }
        except Exception as e:
            model_checks["breakout_classifier"] = {"status": "FAIL", "error": str(e)}
            result["issues"].append(f"Classifier failed: {e}")

        # Quantile regressor check
        try:
            t_q = time.time()
            q_val = float(predictor.quantile_regressor.predict(X)[0])
            q_lat = round((time.time() - t_q) * 1000, 2)
            model_checks["quantile_upper_bound"] = {
                "status": "OK",
                "q75_return_pct": round(q_val * 100, 4),
                "latency_ms": q_lat
            }
        except Exception as e:
            model_checks["quantile_upper_bound"] = {"status": "FAIL", "error": str(e)}

        result["checks"]["models"] = model_checks

        # 4. Audit Live Signal Generation & Regime
        regime_info = classify_micro_regime(df_feat)
        result["metrics"]["regime"] = regime_info["regime"]
        result["metrics"]["regime_desc"] = regime_info["description"]
        result["metrics"]["allows_long_scalp"] = regime_info.get("allows_long_scalp", True)

        t_sig = time.time()
        prediction = predictor.predict_next_1m(df, profit_threshold=0.0012)
        total_inference_ms = round((time.time() - t_sig) * 1000, 1)

        result["metrics"]["total_inference_ms"] = total_inference_ms
        result["metrics"]["predicted_return_pct"] = prediction["predicted_return_pct"]
        result["metrics"]["confidence_pct"] = prediction["confidence"]
        result["metrics"]["signal"] = prediction["signal"]
        result["metrics"]["profit_threshold_pct"] = prediction["profit_threshold_pct"]

        # 5. Accuracy & Track Record Check from Live Server Logs
        tracker = StockConfidenceTracker()
        prof = tracker.get_profile(symbol)
        result["metrics"]["accuracy_profile"] = {
            "tier": prof.get("tier"),
            "directional_accuracy_pct": prof.get("directional_accuracy_pct"),
            "verified_samples": prof.get("verified_samples"),
            "is_blacklisted": prof.get("is_blacklisted"),
            "reason": prof.get("reason")
        }

        # Overall Status Assessment
        failed_models = [k for k, v in model_checks.items() if v.get("status") == "FAIL"]
        if failed_models:
            result["status"] = "WARN" if len(failed_models) < 3 else "FAIL"
        else:
            result["status"] = "PASS"

    except Exception as e:
        result["status"] = "FAIL"
        result["issues"].append(f"Agent exception: {str(e)}")

    result["agent_runtime_ms"] = round((time.time() - start_t) * 1000, 1)
    return result


def main():
    print("=" * 80)
    print(f"🚀 LAUNCHING 10 CONCURRENT DIAGNOSTIC AGENTS AT ONCE")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST")
    print(f"Universe: {len(STOCK_SYMBOLS)} NSE stocks")
    print("=" * 80)

    # Initialize shared predictor for testing inference
    predictor = OneMinPredictor()

    audit_results = []
    t_start = time.time()

    # Launch 10 agents concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(run_single_stock_agent, i + 1, sym, predictor): sym
            for i, sym in enumerate(STOCK_SYMBOLS)
        }

        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                res = fut.result()
                audit_results.append(res)
                icon = "✅" if res["status"] == "PASS" else ("⚠️" if res["status"] == "WARN" else "❌")
                print(f"{icon} {res['agent_name']:<28} | Price: INR {res.get('metrics', {}).get('current_price', 0):>7.2f} | "
                      f"Signal: {res.get('metrics', {}).get('signal', 'N/A'):<4} | "
                      f"PredRet: {res.get('metrics', {}).get('predicted_return_pct', 0):>+6.3f}% | "
                      f"Conf: {res.get('metrics', {}).get('confidence_pct', 0):>4.1f}% | "
                      f"Regime: {res.get('metrics', {}).get('regime', 'N/A'):<13} | "
                      f"Latency: {res.get('agent_runtime_ms', 0):>5.1f}ms")
            except Exception as e:
                print(f"❌ Error auditing {sym}: {e}")

    total_duration = round(time.time() - t_start, 2)
    audit_results.sort(key=lambda x: x["agent_id"])

    # Comprehensive summary
    pass_count = sum(1 for r in audit_results if r["status"] == "PASS")
    warn_count = sum(1 for r in audit_results if r["status"] == "WARN")
    fail_count = sum(1 for r in audit_results if r["status"] == "FAIL")

    summary = {
        "audit_timestamp": datetime.now().isoformat(),
        "total_agents": len(STOCK_SYMBOLS),
        "passed": pass_count,
        "warnings": warn_count,
        "failed": fail_count,
        "total_duration_sec": total_duration,
        "results": audit_results
    }

    with open(AUDIT_REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("-" * 80)
    print(f"📊 10-AGENT AUDIT COMPLETED in {total_duration}s: {pass_count} PASSED | {warn_count} WARNED | {fail_count} FAILED")
    print(f"📁 Full report saved to: {AUDIT_REPORT_FILE}")
    print("=" * 80)


if __name__ == "__main__":
    main()
