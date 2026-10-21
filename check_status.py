#!/usr/bin/env python3
"""
check_status.py
Status Query Sentinel — Inspects the production live trading daemon running on Windows.
Instant inspection without interrupting execution.
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from typing import Optional

WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(WORKSPACE_ROOT, "logs", "live_trader.pid")
STATE_FILE = os.path.join(WORKSPACE_ROOT, "reports", "live", "runtime_state.json")
LOG_FILE = os.path.join(WORKSPACE_ROOT, "logs", "live_trader.log")

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def is_pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            pass
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, Exception):
        return False


def get_status():
    print("=" * 80)
    print("  📊 ALPHANSE V3 — LIVE TRADING DESK STATUS SENTINEL")
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

    # If PID_FILE was stale or not running, fall back to checking PID recorded in runtime_state.json
    if not running and os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state_data = json.load(f)
            cand_pid = state_data.get("pid")
            if cand_pid and is_pid_alive(int(cand_pid)):
                pid = int(cand_pid)
                running = True
                try:
                    with open(PID_FILE, "w", encoding="utf-8") as f:
                        f.write(str(pid))
                except Exception:
                    pass
        except Exception:
            pass

    print(f"  • Operating System Process PID:  {pid if pid else 'None'}")
    print(f"  • Process Execution Status:      {'🟢 ACTIVE & RUNNING ON WINDOWS' if running else '🔴 NOT RUNNING'}")

    # 2. Runtime State
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            exec_mode = state.get('execution_mode', 'PAPER_TESTING')
            mode_badge = "🟢 REAL ORDERS (LIVE MONEY)" if exec_mode == "REAL_ORDERS" else "🟡 PAPER TESTING (ZERO RISK TO CAPITAL)"
            print(f"  • Execution Mode:                {mode_badge}")
            print(f"  • Daemon Lifecycle State:        {state.get('status', 'UNKNOWN')}")
            print(f"  • Broker & Account:              {state.get('broker')} (UCC: {state.get('ucc')})")
            print(f"  • Cycle Counter:                 Cycle #{state.get('cycle', 0)}")
            # Heartbeat freshness / stale heartbeat sentinel
            last_up = state.get("last_updated")
            stale_status = "UNKNOWN"
            stale_seconds = None
            if last_up:
                try:
                    up_dt = datetime.fromisoformat(last_up)
                    stale_seconds = (datetime.now() - up_dt).total_seconds()
                    if running and stale_seconds > 120.0:
                        stale_status = f"🔴 STALE ({stale_seconds:.1f}s ago > 120s limit — process may be hung or suspended)"
                    elif running:
                        stale_status = f"🟢 HEALTHY ({stale_seconds:.1f}s ago)"
                    else:
                        stale_status = f"⚪ INACTIVE ({stale_seconds:.1f}s ago)"
                except Exception:
                    stale_status = "ERROR_PARSING_TIMESTAMP"

            print(f"  • Last Heartbeat:                {last_up or 'N/A'}")
            print(f"  • Stale Heartbeat Sentinel:      {stale_status}")
            
            # Ledger details
            starting_bankroll = state.get("starting_bankroll", 1500.00)
            bankroll = state.get("paper_bankroll", 1500.00)
            tot_in = state.get("total_money_in", 0.0)
            tot_out = state.get("total_money_out", 0.0)
            realized = state.get("realized_pnl", 0.0)
            print(f"  • Current Paper Bankroll:        ₹{bankroll:,.2f} (Starting: ₹{starting_bankroll:,.2f})")
            print(f"  • Total Money Put In (Deployed): ₹{tot_in:,.2f}")
            print(f"  • Total Money Returned (Out):    ₹{tot_out:,.2f}")
            print(f"  • Net Realized P&L Today:        ₹{realized:+,.2f} ({(realized / starting_bankroll) * 100:+.2f}%)")
            print(f"  • Active Open Positions:         {state.get('active_positions_count', 0)}")
            print(f"  • Closed Trades Count:           {state.get('closed_trades_count', 0)}")

            active_pos = state.get("active_positions", {})
            if active_pos:
                print("\n  📌 Active Positions Detail:")
                for mid, pos in active_pos.items():
                    print(f"    - [{mid}] {pos.get('side')} {pos.get('shares')}x {pos.get('kotak_symbol')} @ ₹{pos.get('entry_price', 0.0):.2f} | Deployed: ₹{pos.get('notional', 0.0):.2f} | LTP: ₹{pos.get('current_price', 0.0):.2f} | P&L: ₹{pos.get('unrealized_pnl', 0.0):+.2f}")
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
    return {
        "pid": pid,
        "running": running,
        "state": state if os.path.exists(STATE_FILE) else None
    }


def get_active_positions(state_file: Optional[str] = None) -> dict:
    """Returns dictionary of currently active open positions from runtime state."""
    target_state = state_file or STATE_FILE
    if os.path.exists(target_state):
        try:
            with open(target_state, "r", encoding="utf-8") as f:
                state = json.load(f)
            return state.get("active_positions", {})
        except Exception:
            return {}
    return {}


def safe_terminate_trader(force: bool = False, state_file: Optional[str] = None, pid_file: Optional[str] = None) -> tuple[bool, str]:
    """
    Safely terminates an active trader process ONLY after verifying its state.
    Refuses to kill or terminate if active open positions exist unless force=True.
    """
    target_pid = pid_file or PID_FILE
    pid = None
    if os.path.exists(target_pid):
        try:
            with open(target_pid, "r") as f:
                pid = int(f.read().strip())
        except Exception:
            pass

    if not pid or not is_pid_alive(pid):
        if os.path.exists(target_pid):
            try:
                os.remove(target_pid)
            except Exception:
                pass
        return True, "No active live trader process found."

    # Check state before terminating
    active_positions = get_active_positions(state_file=state_file)
    if active_positions and not force:
        open_syms = [p.get("kotak_symbol", m) for m, p in active_positions.items()]
        return False, f"SAFETY REFUSAL: Active open positions exist ({', '.join(open_syms)}). Refusing to terminate without position square-off! Pass force=True to override."

    import signal
    try:
        os.kill(pid, signal.SIGTERM)
        import time
        for _ in range(20):
            if not is_pid_alive(pid):
                if os.path.exists(PID_FILE):
                    try:
                        os.remove(PID_FILE)
                    except Exception:
                        pass
                return True, f"Process {pid} terminated gracefully."
            time.sleep(0.5)

        if force:
            subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
            if os.path.exists(PID_FILE):
                try:
                    os.remove(PID_FILE)
                except Exception:
                    pass
            return True, f"Process {pid} forcefully terminated."
        return False, f"Process {pid} did not exit within timeout."
    except Exception as e:
        return False, f"Error terminating process {pid}: {e}"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AlphaNSE Live Status Sentinel")
    parser.add_argument("--stop", action="store_true", help="Safely terminate active trader (verifies state first)")
    parser.add_argument("--force", action="store_true", help="Force termination even if positions exist")
    args = parser.parse_args()

    if args.stop:
        success, msg = safe_terminate_trader(force=args.force)
        print(f"[{'OK' if success else 'BLOCKED'}] {msg}")
        sys.exit(0 if success else 1)
    else:
        get_status()
