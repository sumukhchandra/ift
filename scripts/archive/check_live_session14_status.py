#!/usr/bin/env python3
"""
scripts/check_live_session14_status.py
Status Query Sentinel — Inspects the standalone background trading daemon running on Windows.
Does not interfere with or interrupt execution.
"""

import os
import sys
import json
import subprocess
from datetime import datetime

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PID_FILE = os.path.join(WORKSPACE_ROOT, "logs", "session14_live_trader.pid")
STATE_FILE = os.path.join(WORKSPACE_ROOT, "v3", "reports", "SESSION_14_RUNTIME_STATE.json")
LOG_FILE = os.path.join(WORKSPACE_ROOT, "logs", "session14_live_trading.log")

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def is_pid_alive(pid: int) -> bool:
    try:
        output = subprocess.check_output(f'tasklist /FI "PID eq {pid}" /NH', shell=True).decode("utf-8", errors="replace")
        return str(pid) in output
    except Exception:
        return False


def get_status():
    print("=" * 80)
    print("  📊 ALPHANSE V3 — SESSION 14 LIVE STATUS SENTINEL")
    print(f"  QUERY TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST")
    print("=" * 80)

    # 1. Process Health
    pid = None
    running = False
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            running = is_pid_alive(pid)
        except Exception:
            pass

    print(f"  • Standalone Windows Process PID: {pid if pid else 'None'}")
    print(f"  • Process Execution Status:      {'🟢 RUNNING INDEPENDENTLY ON OS' if running else '🔴 NOT RUNNING'}")

    # 2. Runtime State
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            print(f"  • Daemon Lifecycle State:        {state.get('status', 'UNKNOWN')}")
            print(f"  • Broker & Account:              {state.get('broker')} (UCC: {state.get('ucc')})")
            print(f"  • Cycle Counter:                 Cycle #{state.get('cycle', 0)}")
            print(f"  • Last Heartbeat:                {state.get('last_updated', 'N/A')}")
            print(f"  • Active Open Positions:         {state.get('active_positions_count', 0)}")
            print(f"  • Realized P&L Today:            ₹{state.get('realized_pnl', 0.0):+,.2f}")
            print(f"  • Closed Trades Count:           {state.get('closed_trades_count', 0)}")

            active_pos = state.get("active_positions", {})
            if active_pos:
                print("\n  📌 Active Positions Detail:")
                for mid, pos in active_pos.items():
                    print(f"    - [{mid}] {pos.get('side')} {pos.get('shares')}x {pos.get('kotak_symbol')} @ ₹{pos.get('entry_price', 0.0):.2f} | LTP: ₹{pos.get('current_price', 0.0):.2f} | P&L: ₹{pos.get('unrealized_pnl', 0.0):+.2f}")
        except Exception as e:
            print(f"  [WARN] Failed to parse state file: {e}")
    else:
        print("  • Runtime State File:            Awaiting first cycle write")

    # 3. Recent Log Output
    if os.path.exists(LOG_FILE):
        print("\n  📝 Recent Log Ticks (Last 5 lines):")
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                lines = [line.strip() for line in f if line.strip()]
            for l in lines[-5:]:
                print(f"    {l}")
        except Exception as e:
            print(f"    [WARN] Unable to read log file: {e}")

    print("=" * 80)


if __name__ == "__main__":
    get_status()
