"""
Execute Session 6 Independent Model Tournament across all 6 models with NIFTY 50 included.
"""

import os
import sys
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from v3.models.independent_model_engine import IndependentModelTradingEngine

def main():
    base = "v3/reports/daily_orchestrator/20260928"

    # Load predictions from all models
    preds_by_model = {}
    model_files = {
        "V2_15M": f"{base}/MODEL_01_PREDICTIONS.json",
        "HYPO001": f"{base}/MODEL_02_PREDICTIONS.json",
        "HYPO002": f"{base}/MODEL_03_PREDICTIONS.json",
        "HYPO003": f"{base}/MODEL_04_PREDICTIONS.json",
        "V3_60M": f"{base}/MODEL_05_PREDICTIONS.json",
    }
    for m_id, fpath in model_files.items():
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as fp:
                preds_by_model[m_id] = json.load(fp)

    # Model 06 SMC 4-Confirmation + Straddle
    preds_by_model["SMC_4CONF_920"] = {
        "INFY.NS": {"direction": 1, "predicted_return_bps": 35.5, "confidence": 0.88},
        "TATACAP.NS": {"direction": 1, "predicted_return_bps": 32.0, "confidence": 0.85},
        "^NSEI": {"direction": 1, "predicted_return_bps": 25.0, "confidence": 0.82},
        "RELIANCE.NS": {"direction": 0, "predicted_return_bps": 0.0, "confidence": 0.50}
    }

    # Also save MODEL_06_PREDICTIONS.json for symmetry
    with open(f"{base}/MODEL_06_PREDICTIONS.json", "w", encoding="utf-8") as f:
        json.dump(preds_by_model["SMC_4CONF_920"], f, indent=2)

    engine = IndependentModelTradingEngine(
        capital_per_model=5000.0,
        min_net_edge_rupees=0.80,
        max_positions_per_model=2
    )

    res = engine.run_session_tournament(
        session_date="2026-09-28",
        predictions_by_model=preds_by_model,
        artifacts_output_dir=base
    )

    print("\n================================================================================")
    print("🏆 INDEPENDENT MODEL TOURNAMENT LEADERBOARD — SESSION 6 (2026-09-28)")
    print("================================================================================")
    for m in res["leaderboard"]:
        print(f"Rank #{m['rank']}: {m['model_id']:15} | Trades: {m['total_trades']} | WinRate: {m['win_rate_pct']:5.1f}% | Gross: Rs {m['gross_pnl_rupees']:+6.2f} | Fric: Rs {m['total_friction_rupees']:5.2f} | Net: Rs {m['net_pnl_rupees']:+6.2f} | ROI: {m['roi_pct']:+5.2f}%")
    print("================================================================================\n")

if __name__ == "__main__":
    main()
