#!/usr/bin/env python3
"""
view_paper_trades.py
AlphaNSE V3 — Quantitative Paper Testing Cashflow & Bankroll Ledger Viewer
Answers: "If we keep money, how much money will come?"
Displays penny-for-penny Money In, Money Out, Taxes Paid, and Running Bankroll.
"""

import os
import sys
import json
import argparse
from datetime import datetime

WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(WORKSPACE_ROOT, "reports", "live", "runtime_state.json")
LIVE_LEDGER_FILE = os.path.join(WORKSPACE_ROOT, "reports", "live", "paper_trading_ledger.json")
REPLAY_DIR = os.path.join(WORKSPACE_ROOT, "reports", "replay")
REPLAY_LEDGER_FILE = os.path.join(REPLAY_DIR, "paper_replay_ledger.json") if os.path.exists(os.path.join(REPLAY_DIR, "paper_replay_ledger.json")) else os.path.join(WORKSPACE_ROOT, "reports", "live", "paper_replay_ledger.json")
PID_FILE = os.path.join(WORKSPACE_ROOT, "logs", "live_trader.pid")

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


def display_ledger(ledger_data: dict, title: str):
    print("=" * 105)
    print(f"  💰 {title}")
    print("=" * 105)

    starting = float(ledger_data.get("starting_bankroll") or ledger_data.get("initial_bankroll") or 1500.0)
    current = float(ledger_data.get("current_bankroll") or ledger_data.get("final_bankroll") or 1500.0)
    trades = ledger_data.get("trades", [])
    
    tot_in = sum(float(t.get("money_in", 0.0)) for t in trades)
    tot_out = sum(float(t.get("money_out", 0.0)) for t in trades)
    tot_taxes = sum(float(t.get("charges", {}).get("total_friction", t.get("charges", {}).get("total_charges", 0.0)) if isinstance(t.get("charges"), dict) else t.get("taxes_friction", 0.0)) for t in trades)
    tot_net = current - starting
    win_trades = [t for t in trades if float(t.get("net_pnl", 0.0)) > 0]
    win_rate = (len(win_trades) / len(trades) * 100.0) if trades else 0.0

    print(f"  • Starting Bankroll:          ₹{starting:>10,.2f}")
    print(f"  • Current Bankroll:           ₹{current:>10,.2f}")
    print(f"  • Total Money Put In:         ₹{tot_in:>10,.2f}  (Cumulative capital deployed across {len(trades)} trades)")
    print(f"  • Total Money Returned:       ₹{tot_out:>10,.2f}  (Cumulative capital returned upon exit)")
    print(f"  • Total Taxes & Fees:         ₹{tot_taxes:>10,.2f}  (Trade Free: ₹0 Brokerage, STT/GST/Exchange only)")
    print(f"  • Net P&L:                    ₹{tot_net:>+10,.2f}  ({(tot_net / starting) * 100:+.2f}%)")
    print(f"  • Win Rate:                    {win_rate:>9.1f}%  ({len(win_trades)} wins / {len(trades) - len(win_trades)} losses)")
    print("-" * 135)

    if not trades:
        print("  ℹ️  No trades have executed yet for this session.")
        print("      Market opens at 09:15:00 IST. The engine is armed in STANDBY_FOR_OPEN.")
        print("-" * 135)
        return

    print(f"{'#':<3} | {'TRADE ID':<18} | {'INSTRUMENT':<13} | {'DIR':<4} | {'TIMES (IN -> OUT)':<19} | {'QTY':<3} | {'PUT IN (₹)':<10} | {'RETURNED (₹)':<12} | {'TAX':<5} | {'NET (₹)':<8} | {'ROI %':<6} | {'BANKROLL (₹)':<12} | {'EXIT REASON'}")
    print("-" * 135)

    for i, t in enumerate(trades, 1):
        trd_id = t.get("trade_id", f"TRD-{i:03d}")
        sym = t.get("instrument") or t.get("symbol") or t.get("kotak_symbol", "N/A")
        direction = t.get("direction") or t.get("side", "N/A")
        t_in = str(t.get("entry_time", ""))[:8]
        t_out = str(t.get("exit_time", ""))[:8]
        time_str = f"{t_in} -> {t_out}" if (t_in and t_out) else (t_out or t_in or "N/A")
        qty = t.get("quantity") or t.get("shares", 1)
        m_in = float(t.get("money_in", 0.0))
        m_out = float(t.get("money_out", 0.0))
        tax_val = float(t.get("charges", {}).get("total_friction", t.get("charges", {}).get("total_charges", 0.0)) if isinstance(t.get("charges"), dict) else t.get("taxes_friction", 0.0))
        net = float(t.get("net_pnl", 0.0))
        roi = float(t.get("return_pct", 0.0))
        b_after = float(t.get("bankroll_after", 0.0))
        reason = t.get("exit_reason", "")

        net_str = f"{net:+6.2f}"
        badge = "🟢" if net > 0 else ("🔴" if net < 0 else "⚪")

        print(f"{i:<3} | {trd_id:<18} | {sym:<13} | {direction:<4} | {time_str:<19} | {qty:<3} | ₹{m_in:>8.2f} | ₹{m_out:>10.2f} | ₹{tax_val:>4.2f} | {badge} {net_str} | {roi:>+5.2f}% | ₹{b_after:>10.2f} | {reason}")

    print("=" * 135)


def main():
    parser = argparse.ArgumentParser(description="AlphaNSE Paper Trading Cashflow & Ledger Viewer")
    parser.add_argument("--replay-only", action="store_true", help="View the full-day replay benchmark only")
    args = parser.parse_args()

    # 1. Daemon Health Status
    pid = None
    running = False
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            running = is_pid_alive(pid)
        except Exception:
            pass

    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            if not running:
                cand_pid = state.get("pid")
                if cand_pid and is_pid_alive(int(cand_pid)):
                    pid = int(cand_pid)
                    running = True
        except Exception:
            pass

    print("\n" + "=" * 105)
    print("  🚀 ALPHANSE V3 — QUANTITATIVE PAPER TESTING ENGINE")
    print(f"  TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST | MODE: PAPER TESTING (ZERO RISK TO CAPITAL)")
    print(f"  DAEMON STATUS: {'🟢 ACTIVE & RUNNING (PID ' + str(pid) + ')' if running else '🔴 NOT RUNNING'} | LIFECYCLE: {state.get('status', 'STANDBY')}")
    print("=" * 105)

    if not args.replay_only:
        # Load Live Paper Ledger
        live_data = None
        if os.path.exists(LIVE_LEDGER_FILE):
            try:
                with open(LIVE_LEDGER_FILE, "r", encoding="utf-8") as f:
                    live_data = json.load(f)
            except Exception:
                pass

        if not live_data:
            live_data = {
                "session_date": datetime.now().strftime("%Y-%m-%d"),
                "starting_bankroll": 1500.00,
                "current_bankroll": 1500.00,
                "trades": []
            }

        display_ledger(live_data, f"TODAY'S LIVE PAPER SESSION ({datetime.now().strftime('%Y-%m-%d')})")

    # Display Cash-Only Benchmark
    cash_only_file = os.path.join(WORKSPACE_ROOT, "reports", "replay", "paper_replay_ledger_cash_only.json")
    if not os.path.exists(cash_only_file):
        cash_only_file = os.path.join(WORKSPACE_ROOT, "reports", "live", "paper_replay_ledger_cash_only.json")
    if os.path.exists(cash_only_file):
        try:
            with open(cash_only_file, "r", encoding="utf-8") as f:
                c_data = json.load(f)
            print()
            display_ledger(c_data, "FULL-DAY PAPER REPLAY: CASH-ONLY (STRICT MANDATE: NO MARGIN, NO SHORTING)")
        except Exception:
            pass

    # Display Intraday MIS Margin Benchmark
    mis_file = os.path.join(WORKSPACE_ROOT, "reports", "replay", "paper_replay_ledger_mis.json")
    if not os.path.exists(mis_file):
        mis_file = os.path.join(WORKSPACE_ROOT, "reports", "live", "paper_replay_ledger_mis.json")
    if os.path.exists(mis_file):
        try:
            with open(mis_file, "r", encoding="utf-8") as f:
                mis_data = json.load(f)
            print()
            display_ledger(mis_data, "COMPARATIVE BENCHMARK: INTRADAY MIS (MARGIN SHORTING ALLOWED WITH 15:15 SQUARE-OFF)")
        except Exception:
            pass

    print("\n  💡 SUMMARY EXPLANATION ('If we keep money, how much comes?'):")
    print("     1. Capital Limit: Starting paper account balance is EXACTLY ₹1,500.00. Whole shares bought under available cash.")
    print("     2. Single Position: Under ₹1,500 capital, only 1 position is held concurrently (zero negative balance, zero margin).")
    print("     3. Profit Harvest: When a model gains +1.0% (+₹15.00), it automatically takes profit and returns ₹1,515.00.")
    print("     4. Breakeven Lock: At +0.5% (+₹7.50), stop-loss moves to ₹0.00 to guarantee capital preservation.")
    print("     5. Loss Cap: If price moves against the model, a hard 0.30% stop-loss triggers, capping max loss at ~₹4.50.")
    print("     6. Intraday Liquidation: At 15:15:00 IST, all open positions are liquidated to 100% cash.")
    print("     7. Taxes: Kotak Neo Trade Free plan charges ₹0 brokerage on equity intraday; only statutory STT/GST is deducted.")
    print("=" * 105 + "\n")


if __name__ == "__main__":
    main()
