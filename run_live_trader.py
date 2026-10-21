#!/usr/bin/env python3
"""
run_live_trader.py
Top-level runner for AlphaNSE V3 Real-Money Production Live Trading Engine.
"""

import os
import sys

# Ensure root is in sys.path
WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

if sys.stdout and getattr(sys.stdout, "encoding", None) and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and getattr(sys.stderr, "encoding", None) and sys.stderr.encoding.lower() != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from v3.execution.live_trader import AlphaNSELiveTrader

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AlphaNSE Real Live Trader")
    parser.add_argument("--test-conn", action="store_true", help="Test Kotak Neo connection and exit")
    parser.add_argument("--inspect-signals", action="store_true", help="Inspect live mathematical signals across all instruments")
    parser.add_argument("--force-active", action="store_true", help="Force active cycle for testing outside hours")
    parser.add_argument("--allow-short-selling", action="store_true", help="Allow intraday short selling (MIS margin mode; default is cash-only no shorting)")
    parser.add_argument("--mode", choices=["CASH_EQUITY", "OPTIONS_PAPER"], default="CASH_EQUITY", help="Strategy execution mode (CASH_EQUITY or OPTIONS_PAPER)")
    parser.add_argument("--execute-paper", action="store_true", help="Authorize paper order fills (default is False: runs in SHADOW MODE per audit gate)")
    args = parser.parse_args()

    shadow_mode = not args.execute_paper
    trader = AlphaNSELiveTrader(
        force_active=args.force_active,
        allow_short_selling=args.allow_short_selling,
        mode=args.mode,
        shadow_mode=shadow_mode
    )

    trader.log_structured(
        "STARTUP",
        {
            "entry_point": "run_live_trader.py",
            "pid": os.getpid(),
            "mode": args.mode,
            "shadow_mode": shadow_mode,
            "force_active": args.force_active,
            "allow_short_selling": args.allow_short_selling,
            "test_conn": args.test_conn,
            "inspect_signals": args.inspect_signals
        },
        f"Production runner invoked (mode={args.mode}, shadow_mode={shadow_mode})"
    )

    if args.test_conn:
        trader.check_connection()
    elif args.inspect_signals:
        trader.log_structured("INSPECT_SIGNALS", {"mode": args.mode}, "Inspecting live signals")
        trader.inspect_live_signals()
    else:
        trader.run()
