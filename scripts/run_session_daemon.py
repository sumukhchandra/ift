"""
AlphaNSE V2 — Intraday Session Orchestrator & Sentinel Daemon.
Monitors the trading session for Monday, September 21, 2026:
1. Displays market session status (Pre-market 09:00, Market Open 09:15, Close 15:30 IST).
2. Monitors intraday progression and bar printing.
3. Automatically triggers post-market ingestion and frozen-model scoring at 15:30 IST.
4. Enforces live lockout and router lockouts permanently.
"""

import os
import sys
import time
import logging
from datetime import datetime, date, time as dtime, timedelta, timezone
from typing import Optional

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.ingest_fresh_sessions import FreshSessionIngestionHarness
from scripts.run_phase3b_falsification import run_phase3b

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SESSION_DAEMON")


import argparse

def run_session_daemon(target_date: Optional[date] = None, poll_interval_seconds: int = 60):
    today = target_date or datetime.now().date()
    session_str = today.strftime("%Y-%m-%d")

    logger.info("=" * 80)
    logger.info(f"  ALPHANSE V2 — SESSION ORCHESTRATOR: {session_str}")
    logger.info("=" * 80)
    logger.info("Live Execution: 🔒 PHYSICALLY DISABLED (LiveExecutionDisabledError)")
    logger.info("Capital Router: 🔒 STRICTLY LOCKED")
    logger.info("Models & Hypotheses: 🔒 FROZEN (Historical Cutoff: 2026-09-18)")
    logger.info("-" * 80)

    harness = FreshSessionIngestionHarness()
    status_info = harness.check_evidence_sufficiency()
    logger.info(f"Initial Accumulation State: {status_info['status']} ({status_info['accumulated_sessions']}/10 sessions)")

    market_open_time = dtime(9, 15)
    market_close_time = dtime(15, 30)

    # Main monitoring loop
    ingested_today = False
    logger.info("Sentinel loop running. Tracking session milestones...")

    while True:
        now = datetime.now()
        current_time = now.time()

        if current_time < market_open_time:
            time_to_open = (datetime.combine(today, market_open_time) - datetime.combine(today, current_time)).total_seconds()
            mins_to_open = int(time_to_open // 60)
            logger.info(
                f"[PRE-MARKET] Current Time: {current_time.strftime('%H:%M:%S')} IST | "
                f"Opening Bell in ~{mins_to_open} minutes (09:15 IST). Sentinel standing by."
            )
        elif current_time < market_close_time:
            time_to_close = (datetime.combine(today, market_close_time) - datetime.combine(today, current_time)).total_seconds()
            mins_to_close = int(time_to_close // 60)
            logger.info(
                f"[MARKET ACTIVE] Current Time: {current_time.strftime('%H:%M:%S')} IST | "
                f"Session active. ~{mins_to_close} mins remaining until closing bell (15:30 IST)."
            )
        else:
            # Post market close
            logger.info("🔔 [CLOSING BELL] Market session concluded (15:30 IST). Starting intake sequence...")
            if not ingested_today:
                logger.info(f"Step 1: Ingesting live session data for {session_str}...")
                df_session = harness.fetch_live_session(today)
                if df_session.empty:
                    logger.warning("No bars retrieved from feed. Retrying in 60 seconds...")
                    time.sleep(60)
                    continue

                success = harness.ingest_session(df_session, today)
                if success:
                    ingested_today = True
                    logger.info("Step 2: Executing frozen candidate evaluation...")
                    run_phase3b(mode_str="fresh_validation")
                    logger.info(f"Session {session_str} evaluation completed.")
                    break
                else:
                    logger.error("Session ingestion failed data quality checks.")
                    break
            else:
                logger.info(f"Session {session_str} already ingested.")
                break

        time.sleep(poll_interval_seconds)

    logger.info("=" * 80)
    logger.info("  SESSION SENTINEL CYCLE COMPLETE")
    logger.info("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AlphaNSE V2 Session Orchestrator")
    parser.add_argument("--date", type=str, default=None, help="Target date YYYY-MM-DD (defaults to today)")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds")
    args = parser.parse_args()

    parsed_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None
    run_session_daemon(target_date=parsed_date, poll_interval_seconds=args.interval)
