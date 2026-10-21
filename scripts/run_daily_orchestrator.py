"""
AlphaNSE V3 — Daily Adaptive Multi-Model Orchestrator Operational Runner.
Executes the unified 16-step daily adaptive research + decision cycle for any session date:
  1. Data Cleaner & Compactor (preserves all raw/immutable data)
  2. 15-Domain Multi-Intelligence Collection
  3. Pre-Market T-10 Minute Freeze (09:05 IST)
  4. Market World State Synthesis
  5. Pre-Market Trading Roadmap (Constrained Beam Search)
  6. 5-Model Independent Predictions
  7. Antigravity Meta-Orchestrator Consensus Evaluation
  8. Capital Allocation Plan & Risk/Cost Hurdle Gating (>= ₹0.80)
  9. Intraday Chronological Streaming & 1-Minute Thesis Verification
  10. Active Position Monitoring & 15:25 Mandatory Square-Off
  11. Post-Session Forensics & Learning Loop

Generates all 14 required daily artifacts in v3/reports/daily_orchestrator/<SESSION_DATE>/.
"""

import os
import sys
import argparse
from datetime import datetime, date

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from v3.orchestration.daily_orchestrator import DailyAdaptiveOrchestratorV3
from v3.config.multimodel_config import SESSION_5_DATE


def main():
    parser = argparse.ArgumentParser(description="AlphaNSE V3 Daily Adaptive Orchestrator")
    parser.add_argument("--date", type=str, default=SESSION_5_DATE, help="Session date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=5000.0, help="Initial capital in ₹")
    parser.add_argument("--hurdle", type=float, default=0.80, help="Minimum net rupee edge hurdle")
    args = parser.parse_args()

    print("=" * 80)
    print("  ALPHANSE V3 — DAILY ADAPTIVE MULTI-MODEL TRADING ORCHESTRATOR  ")
    print("=" * 80)
    print(f"  Target Session:      {args.date}")
    print(f"  Starting Capital:    ₹{args.capital:.2f}")
    print(f"  Net Edge Hurdle:     ₹{args.hurdle:.2f}")
    print(f"  Safety Lock Status:  LIVE EXECUTION PHYSICALLY DISABLED (Paper/Research Mode)")
    print("=" * 80)

    orchestrator = DailyAdaptiveOrchestratorV3(
        workspace_root=WORKSPACE_ROOT,
        initial_capital=args.capital,
        min_net_edge_rupees=args.hurdle,
        live_execution_unlocked=False
    )

    result = orchestrator.run_daily_cycle(session_date=args.date)

    print("\n" + "=" * 80)
    print("  DAILY ADAPTIVE MULTI-MODEL CYCLE SUMMARY")
    print("=" * 80)
    print(f"  Session Date:        {result['session_date']}")
    print(f"  Candidate Universe:  {len(result['world_state']['candidate_universe'])} symbols")
    print(f"  Market Regime:       {result['world_state']['market_regime']}")
    print(f"  Primary Roadmap:     {result['roadmaps']['ROADMAP_1_PRIMARY']['path_summary']}")
    print(f"  Primary Rationale:   {result['roadmaps']['ROADMAP_1_PRIMARY']['selection_rationale']}")
    print(f"  Capital Allocated:   ₹{result['capital_plan']['allocated_capital']:.2f}")
    print(f"  Cash Reserved:       ₹{result['capital_plan']['reserved_cash']:.2f}")
    print(f"  Trades Executed:     {len(result['trades'])}")
    print(f"  Artifacts Generated: {result['artifacts_dir']}")
    print("=" * 80)


if __name__ == "__main__":
    main()
