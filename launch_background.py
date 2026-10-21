#!/usr/bin/env python3
"""
launch_background.py
AlphaNSE V3 — Controlled Detached Background Process Launcher.
Launches the live trader in a fully detached background process that survives
terminal closure on Windows, enforces singleton instance prevention,
and reports process health.
"""

import os
import sys
import time
import json
import argparse
import subprocess

WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from check_status import is_pid_alive, get_status, safe_terminate_trader

PID_FILE = os.path.join(WORKSPACE_ROOT, "logs", "live_trader.pid")
STATE_FILE = os.path.join(WORKSPACE_ROOT, "reports", "live", "runtime_state.json")
LOG_FILE = os.path.join(WORKSPACE_ROOT, "logs", "live_trader.log")


def launch_background_trader(mode: str = "CASH_EQUITY", force_active: bool = False, allow_short: bool = False):
    print("=" * 80)
    print("  🚀 ALPHANSE V3 — BACKGROUND PROCESS LAUNCH SENTINEL")
    print("=" * 80)

    # 1. Duplicate-Instance Check
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                existing_pid = int(f.read().strip())
            if is_pid_alive(existing_pid):
                print(f"❌ [BLOCKED] Another AlphaNSE Live Trader instance is already running!")
                print(f"   Existing PID: {existing_pid}")
                print(f"   Use 'python check_status.py' to monitor or 'python check_status.py --stop' to terminate safely.")
                return False
        except Exception:
            pass

    # 2. Launch in Detached Mode (Survives Terminal Closure on Windows)
    runner_script = os.path.join(WORKSPACE_ROOT, "run_live_trader.py")
    cmd = [sys.executable, runner_script, "--mode", mode]
    if force_active:
        cmd.append("--force-active")
    if allow_short:
        cmd.append("--allow-short-selling")

    creation_flags = 0
    if sys.platform == "win32":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        creation_flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    bg_stdout_file = os.path.join(WORKSPACE_ROOT, "logs", "background_stdout.log")
    bg_stderr_file = os.path.join(WORKSPACE_ROOT, "logs", "background_stderr.log")
    bg_out = open(bg_stdout_file, "a", encoding="utf-8")
    bg_err = open(bg_stderr_file, "a", encoding="utf-8")

    proc = subprocess.Popen(
        cmd,
        cwd=WORKSPACE_ROOT,
        creationflags=creation_flags,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=bg_out,
        stderr=bg_err
    )

    print(f"  • Spawned Background Process PID: {proc.pid}")
    print(f"  • Execution Mode:                 {mode}")
    print(f"  • Detached Console:               🟢 YES (Survives terminal closure)")
    print(f"  • Verifying process health (waiting 2.0s)...")
    time.sleep(2.0)

    # 3. Health Check
    if not is_pid_alive(proc.pid):
        print(f"❌ [CRITICAL] Background process {proc.pid} died immediately after launch!")
        print(f"   Check logs at: {LOG_FILE}")
        return False

    print(f"  • Process Health Status:          🟢 ACTIVE & RUNNING (PID {proc.pid})")
    print(f"  • Log File Stream:                {LOG_FILE}")
    print("=" * 80)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AlphaNSE Background Process Manager")
    parser.add_argument("--mode", choices=["CASH_EQUITY", "OPTIONS_PAPER"], default="CASH_EQUITY", help="Strategy execution mode")
    parser.add_argument("--force-active", action="store_true", help="Force active trading loop")
    parser.add_argument("--allow-short-selling", action="store_true", help="Allow short selling")
    parser.add_argument("--stop", action="store_true", help="Safely terminate background trader")
    parser.add_argument("--status", action="store_true", help="Report process health status")
    parser.add_argument("--force", action="store_true", help="Force termination override")
    args = parser.parse_args()

    if args.status:
        get_status()
    elif args.stop:
        success, msg = safe_terminate_trader(force=args.force)
        print(f"[{'OK' if success else 'BLOCKED'}] {msg}")
    else:
        launch_background_trader(mode=args.mode, force_active=args.force_active, allow_short=args.allow_short_selling)
