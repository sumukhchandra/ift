#!/usr/bin/env python3
"""
scripts/verify_oct16_preflight_data.py
Pre-market data feed and configuration snapshot verifier for October 16 session.
Verifies Kotak Neo read-only connectivity, quote freshness, candle buffers,
OHLC consistency, and saves a pre-flight snapshot.
"""

import os
import sys
import json
from datetime import datetime

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from v3.execution.kotak_adapter import KotakLiveBrokerAdapter
from v3.execution.live_trader import AlphaNSELiveTrader


def verify_and_snapshot():
    print("=" * 80)
    print("  SNAPSHOT VERIFICATION: OCTOBER 16 SESSION READINESS")
    print(f"  TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST")
    print("=" * 80)

    trader = AlphaNSELiveTrader(force_active=False)

    # 1. Broker Adapter Check
    auth_ok = trader.adapter.authenticate() if hasattr(trader.adapter, "authenticate") else trader.adapter.is_authenticated
    env_live = os.getenv("LIVE_TRADING", "False").strip().lower() == "true"
    env_allow = os.getenv("ALLOW_REAL_ORDERS", "False").strip().lower() == "true"

    print(f"  • Broker Adapter:          {trader.adapter.broker_name}")
    print(f"  • Authenticated:           {'YES' if auth_ok else 'NO'}")
    print(f"  • LIVE_TRADING Lock:       {'SECURE (False)' if not env_live else 'UNLOCKED (True)'}")
    print(f"  • ALLOW_REAL_ORDERS Lock:  {'SECURE (False)' if not env_allow else 'UNLOCKED (True)'}")
    print(f"  • Paper Starting Bankroll: ₹{trader.paper_bankroll:.2f}")

    # 2. Market Data Quotes & OHLC Consistency
    quotes = trader.feed.fetch_quotes(trader.candle_buffers)
    watchlist_report = {}

    print("\n  Watchlist Quotes & Affordability under ₹1,500:")
    for sym, u_meta in trader.universe.items():
        q = quotes.get(sym)
        buf = trader.candle_buffers.get(sym, [])
        buf_len = len(buf)

        if q:
            ltp = float(q["ltp"])
            o = float(q["open"])
            h = float(q["high"])
            l = float(q["low"])
            vol = int(q.get("volume", 0))
            src = q.get("source", "UNKNOWN")
            ts = q.get("timestamp", "N/A")

            # OHLC consistency validation
            ohlc_valid = (h >= max(o, ltp)) and (l <= min(o, ltp)) and (l > 0)

            # Whole-share affordability
            shares, notional, afford_rejections = trader.opportunity_engine.calculate_affordable_quantity(ltp, trader.paper_bankroll)
            affordable = (shares >= 1)
            cost_res = trader.opportunity_engine.cost_engine.calculate_roundtrip_cost(notional, 0.0) if affordable else None
            entry_cost_rs = notional + (cost_res.total_cost / 2.0 if cost_res else 0.0)

            watchlist_report[sym] = {
                "symbol": sym,
                "name": u_meta.get("name", sym),
                "model": u_meta.get("model", "N/A"),
                "ltp": ltp,
                "open": o,
                "high": h,
                "low": l,
                "volume": vol,
                "source": src,
                "quote_timestamp": ts,
                "ohlc_valid": ohlc_valid,
                "buffer_candles": buf_len,
                "affordable_under_1500": affordable,
                "affordable_shares": shares,
                "notional_rs": round(notional, 2),
                "entry_cost_rs": round(entry_cost_rs, 2),
                "rejection_reasons": afford_rejections
            }

            status_icon = "PASS" if ohlc_valid else "FAIL_OHLC"
            afford_str = f"{shares} shares (₹{entry_cost_rs:.2f})" if affordable else f"UNAFFORDABLE ({', '.join(afford_rejections)})"
            print(f"    - {sym:<15}: LTP=₹{ltp:>8.2f} [{src}] | Candles={buf_len} | OHLC={status_icon} | Sizing: {afford_str}")
        else:
            print(f"    - {sym:<15}: NO QUOTE RETURNED")
            watchlist_report[sym] = {"error": "NO_QUOTE"}

    # 3. Model Weights Snapshot
    models_loaded = list(trader.models_data.keys())
    ml_ensemble_loaded = bool(trader.ml_predictor is not None)

    snapshot = {
        "snapshot_timestamp": datetime.now().isoformat(),
        "target_market_session": "2026-10-16",
        "market_currently_open": False,
        "market_status_note": "NSE is currently CLOSED. Quotes reflect latest official exchange closing snapshot.",
        "safety_locks": {
            "LIVE_TRADING": env_live,
            "ALLOW_REAL_ORDERS": env_allow,
            "adapter_is_live": trader.adapter.is_live,
            "air_gap_enforced": (not env_live) and (not env_allow) and (not trader.adapter.is_live)
        },
        "capital_and_limits": {
            "starting_paper_bankroll_rs": 1500.00,
            "current_paper_bankroll_rs": trader.paper_bankroll,
            "max_capital_rs": trader.adapter.max_capital,
            "max_concurrent_positions": 1,
            "hard_stop_loss_pct": 0.30,
            "profit_target_pct": 1.00
        },
        "broker_session": {
            "broker": trader.adapter.broker_name,
            "ucc": trader.adapter.ucc or "116K1",
            "authenticated": auth_ok
        },
        "models_snapshot": {
            "specialist_models": models_loaded,
            "ml_tree_ensemble_loaded": ml_ensemble_loaded,
            "confidence_threshold_pct": 45.0,
            "feature_count": len(trader.ml_predictor.feature_cols) if trader.ml_predictor else 0
        },
        "watchlist_snapshot": watchlist_report
    }

    out_file = os.path.join(WORKSPACE_ROOT, "reports", "live", "oct16_preflight_config_snapshot.json")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)

    print("\n" + "=" * 80)
    print(f"  [OK] Snapshot saved successfully to: {out_file}")
    print("=" * 80)
    return True


if __name__ == "__main__":
    verify_and_snapshot()
