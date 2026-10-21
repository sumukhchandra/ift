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

from v3.execution.live_trader import AlphaNSELiveTrader

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AlphaNSE Real Live Trader")
    parser.add_argument("--test-conn", action="store_true", help="Test Kotak Neo connection and exit")
    parser.add_argument("--inspect-signals", action="store_true", help="Inspect live mathematical signals across all instruments")
    parser.add_argument("--force-active", action="store_true", help="Force active cycle for testing outside hours")
    parser.add_argument("--allow-short-selling", action="store_true", help="Allow intraday short selling (MIS margin mode; default is cash-only no shorting)")
    args = parser.parse_args()

    trader = AlphaNSELiveTrader(force_active=args.force_active, allow_short_selling=args.allow_short_selling)
    if args.test_conn:
        trader.check_connection()
    elif args.inspect_signals:
        trader.inspect_live_signals()
    else:
        trader.run()
