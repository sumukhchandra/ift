"""
Off-Market Stock Predictor for Next Trading Session (Tomorrow 09:15 AM IST).
Uses the freshly upgraded 1-minute ML ensemble models to generate high-conviction
opening price targets, expected returns, and signals for the 10 NSE universe stocks.
"""

import os
import sys
import json
from datetime import datetime
import pandas as pd
import numpy as np
import yfinance as yf

# Ensure UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from stocks_config import STOCK_SYMBOLS, STOCK_UNIVERSE, STOCK_BLACKLIST
from models.one_min_predictor import OneMinPredictor
from models.stock_confidence_tracker import StockConfidenceTracker
from regimes.regime_classifier import classify_micro_regime

PREDICTIONS_OUTPUT_FILE = os.path.join(PROJECT_ROOT, "logs", "tomorrow_opening_predictions.json")

def generate_offmarket_predictions():
    print("=" * 85)
    print("NSE OFF-MARKET UNIVERSE PREDICTION ENGINE")
    print(f"Target Setup: Tomorrow Market Open (09:15 AM IST) | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("=" * 85)

    predictor = OneMinPredictor()
    tracker = StockConfidenceTracker()
    print(f"Loaded Upgraded Model: {len(predictor.feature_cols)} features loaded successfully.")

    # Ingest latest candles from NSE
    print("\nFetching latest closing candles from NSE for all 10 universe stocks...")
    predictions = []
    for symbol in STOCK_SYMBOLS:
        try:
            ticker = yf.Ticker(symbol)
            sym_df = ticker.history(period="1d", interval="1m")
            if sym_df is None or sym_df.empty:
                print(f"  [!] {symbol}: Empty candle data", flush=True)
                continue

            # Flatten multi-index columns if present
            if isinstance(sym_df.columns, pd.MultiIndex):
                sym_df.columns = [col[0] for col in sym_df.columns]
            sym_df.columns = [str(c).lower() for c in sym_df.columns]
            sym_df["symbol"] = symbol
            sym_df = sym_df.dropna(subset=["open", "high", "low", "close"])

            if len(sym_df) < 15:
                print(f"  [!] {symbol}: Too few candles ({len(sym_df)})", flush=True)
                continue

            print(f"  [+] {symbol}: Downloaded {len(sym_df)} 1m candles. Running prediction...", flush=True)

            regime_info = classify_micro_regime(sym_df)
            hurdle = 0.0008 * regime_info.get("hurdle_multiplier", 1.0)
            conf_mult = tracker.get_multiplier(symbol)
            is_bl = tracker.is_blacklisted(symbol)

            # Run 1-minute prediction with calibrated parameters
            pred = predictor.predict_next_1m(sym_df, profit_threshold=hurdle, confidence_multiplier=conf_mult)

            stock_prof = tracker.get_profile(symbol)
            pred["regime"] = regime_info["regime"]
            pred["regime_desc"] = regime_info["description"]
            pred["blacklisted"] = is_bl
            pred["stock_accuracy_pct"] = stock_prof["directional_accuracy_pct"]
            pred["stock_tier"] = stock_prof["tier"]

            if is_bl and pred["signal"] == "BUY":
                pred["signal"] = "HOLD"
                pred["suppressed_reason"] = f"Blacklisted ({stock_prof['reason']})"

            predictions.append(pred)
            print(f"  [✓] {symbol}: Pred Ret {pred['predicted_return_pct']}%, Conf {pred['confidence']}%, Signal {pred['signal']}", flush=True)
        except Exception as e:
            print(f"Error predicting {symbol}: {e}", flush=True)
            import traceback
            traceback.print_exc()

    if not predictions:
        print("No predictions generated.")
        return

    # Sort by predicted return descending
    predictions.sort(key=lambda x: x["predicted_return_pct"], reverse=True)

    print("\n" + "-" * 85)
    print(f"{'Symbol':<14} | {'Close (INR)':<11} | {'Target 1m':<11} | {'Pred Ret %':<10} | {'Conf %':<7} | {'Signal':<6} | {'Hurdle %':<8}")
    print("-" * 85)
    for p in predictions:
        sig_indicator = "[BUY] " if p["signal"] == "BUY" else "[HOLD]"
        print(f"{p['symbol']:<14} | INR {p['current_price']:>7.2f} | INR {p['predicted_price_1m']:>7.2f} | {p['predicted_return_pct']:>+9.3f}% | {p['confidence']:>5.1f}% | {sig_indicator:<6} | {p['profit_threshold_pct']:>6.2f}%")

    # Detailed Microstructure Breakdown
    print("\n" + "-" * 85)
    print("DETAILED MICROSTRUCTURE DRIVERS & EXPLANATIONS")
    print("-" * 85)
    for p in predictions:
        status = "BULLISH SETUP" if p["signal"] == "BUY" else "CONSOLIDATION / NEUTRAL"
        print(f"\n* {p['symbol']} ({p['company']}) - {status}")
        print(f"   Current Price:        INR {p['current_price']:,.2f}")
        print(f"   Target Open (1m):     INR {p['predicted_price_1m']:,.2f} ({p['predicted_return_pct']:+.3f}%)")
        print(f"   Confidence / Signal:  {p['confidence']:.1f}% -> {p['signal']}")
        print(f"   Dynamic Hurdle:       {p['profit_threshold_pct']:.2f}% (Volatility Scaled)")
        print(f"   Microstructure:       RSI={p.get('micro_rsi', 50.0):.1f} | EMA Cross={p.get('ema_cross_pct', 0.0):+.3f}% | Vol Z={p.get('vol_zscore', 0.0):+.2f} | Wick Pressure={p.get('wick_pressure', 0.5):.2f}")

    # Save to disk for server/frontend consumption
    output_payload = {
        "generated_at": datetime.now().isoformat(),
        "target_session": "Tomorrow Market Open (09:15 AM IST)",
        "universe_count": len(predictions),
        "buy_signals_count": sum(1 for p in predictions if p["signal"] == "BUY"),
        "hold_signals_count": sum(1 for p in predictions if p["signal"] == "HOLD"),
        "predictions": predictions
    }

    with open(PREDICTIONS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)

    print(f"\nPredictions saved to: {PREDICTIONS_OUTPUT_FILE}")
    print("=" * 85)
    return predictions

if __name__ == "__main__":
    generate_offmarket_predictions()
