"""
AlphaNSE V2 — Intraday Trade Log Inspector.
Extracts and renders the full granular trade execution logs for Monday, September 21, 2026
across all three frozen candidate hypotheses.
"""

import os
import sys
import json
import logging
from datetime import datetime, date, timezone
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
import numpy as np

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from v2.features.feature_pipeline import FeaturePipeline, ALL_FEATURE_COLUMNS
from v2.features.labeling import IntradayLabeler
from v2.models.estimators import RidgeReturnRegressor
from v2.models.hypothesis import CandidateHypothesis
from v2.models.phase3b_evaluator import Phase3BEvaluator, ValidationMode
from v2.risk.cost_scenarios import CostScenarioRegistry, ScenarioType

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TRADE_INSPECTOR")


def extract_today_trade_logs():
    # 1. Load candidate hypotheses
    hypo_path = os.path.join("v2", "models", "hypotheses", "candidate_hypotheses.json")
    with open(hypo_path, "r") as f:
        hypo_raw_list = json.load(f)

    candidates = [CandidateHypothesis.load_from_dict(d, enforce_locked_set=True) for d in hypo_raw_list]

    # 2. Combine fresh session with historical base for feature pipeline continuity
    fresh_dir = os.path.join("v2", "data", "storage", "fresh")
    fresh_files = [os.path.join(fresh_dir, f) for f in os.listdir(fresh_dir) if f.startswith("session_") and f.endswith(".parquet")]

    hist_raw = pd.read_parquet("v2/data/storage/normalized/historical_5m_raw.parquet")
    hist_adj = pd.read_parquet("v2/data/storage/adjusted/historical_5m_adjusted.parquet")
    fresh_dfs = [pd.read_parquet(f) for f in fresh_files]
    combined_fresh = pd.concat(fresh_dfs, ignore_index=True)

    all_raw = pd.concat([hist_raw, combined_fresh], ignore_index=True).drop_duplicates(subset=["symbol", "timestamp"]).sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)
    all_adj = pd.concat([hist_adj, combined_fresh], ignore_index=True).drop_duplicates(subset=["symbol", "timestamp"]).sort_values(by=["symbol", "timestamp"]).reset_index(drop=True)

    tmp_raw = os.path.join(fresh_dir, "_eval_raw.parquet")
    tmp_adj = os.path.join(fresh_dir, "_eval_adj.parquet")
    all_raw.to_parquet(tmp_raw, index=False)
    all_adj.to_parquet(tmp_adj, index=False)

    pipeline = FeaturePipeline(raw_parquet_path=tmp_raw, adj_parquet_path=tmp_adj)
    feature_df = pipeline.compute_all_features()

    labeler = IntradayLabeler(horizons=[3, 6, 12], cost_hurdle_bps=15.0)
    labeled_df = labeler.construct_forward_labels(feature_df)

    tradable_df = labeled_df[labeled_df["symbol"] != "^NSEI"].copy().reset_index(drop=True)
    tradable_df["date"] = pd.to_datetime(tradable_df["timestamp"]).dt.date

    # Regime tagging
    daily_vol = tradable_df.groupby("date")["adj_log_return_5m"].std() * np.sqrt(75 * 252) * 100.0
    vol_map = {}
    for d, v in daily_vol.items():
        if v < 15.0:
            vol_map[d] = "LOW_VOL"
        elif v <= 20.0:
            vol_map[d] = "NORMAL_VOL"
        else:
            vol_map[d] = "HIGH_VOL"
    tradable_df["volatility_regime"] = tradable_df["date"].map(vol_map).fillna("NORMAL_VOL")

    time_series = pd.to_datetime(tradable_df["timestamp"]).dt.time
    t1 = datetime.strptime("10:00", "%H:%M").time()
    t2 = datetime.strptime("11:00", "%H:%M").time()
    t3 = datetime.strptime("13:00", "%H:%M").time()
    t4 = datetime.strptime("14:30", "%H:%M").time()

    conditions = [
        time_series < t1,
        (time_series >= t1) & (time_series < t2),
        (time_series >= t2) & (time_series < t3),
        (time_series >= t3) & (time_series < t4),
        time_series >= t4
    ]
    choices = ["09:15-10:00", "10:00-11:00", "11:00-13:00", "13:00-14:30", "14:30-15:15"]
    tradable_df["time_window"] = np.select(conditions, choices, default="11:00-13:00")

    horizons_map = {
        "15m": (3, "target_return_15m"),
        "30m": (6, "target_return_30m"),
        "60m": (12, "target_return_60m"),
    }

    hist_cutoff = date(2026, 9, 18)
    hist_df = tradable_df[tradable_df["date"] <= hist_cutoff].copy()
    fresh_df = tradable_df[tradable_df["date"] == date(2026, 9, 21)].copy()

    all_oos_predictions = []
    for h_name, (h_bars, target_col) in horizons_map.items():
        train_data = hist_df.dropna(subset=[target_col] + ALL_FEATURE_COLUMNS)
        test_data = fresh_df.dropna(subset=[target_col] + ALL_FEATURE_COLUMNS)

        model = RidgeReturnRegressor(alpha=20.0)
        model.fit(train_data[ALL_FEATURE_COLUMNS].values, train_data[target_col].values)
        model.freeze()

        preds = model.predict(test_data[ALL_FEATURE_COLUMNS].values)
        test_df = test_data.copy()
        test_df["pred_ridge"] = preds
        test_df["target_return"] = test_data[target_col]
        test_df["horizon"] = h_name
        all_oos_predictions.append(test_df)

    scored_fresh_df = pd.concat(all_oos_predictions, ignore_index=True)
    evaluator = Phase3BEvaluator(mode=ValidationMode.FRESH_VALIDATION)

    # 3. Extract trades per candidate
    print("\n" + "=" * 110)
    print("                ALPHANSE V2 — MONDAY SEPTEMBER 21, 2026 GRANULAR TRADE LOGS")
    print("=" * 110)

    all_trades_records = []

    for candidate in candidates:
        trades = evaluator.filter_candidate_trades(scored_fresh_df, candidate)
        scenario_type = ScenarioType(candidate.execution_scenario)
        cost_scenario = CostScenarioRegistry.get_scenario(scenario_type)
        cost_dict = cost_scenario.compute_total_cost_bps(notional=5000.0)
        cost_bps = cost_dict["cost_per_completed_trade_bps"]

        symbols_str = candidate.interaction_rules.get("symbols", "ALL NSE-10")
        print(f"    Cost Model Friction: {cost_bps:.2f} bps | Target Symbols: {symbols_str}")
        print("-" * 110)

        if trades.empty:
            print("    [NO TRADES TRIGGERED TODAY — Market conditions did not breach conviction hurdle]")
            continue

        trades["cost_bps"] = cost_bps
        trades["net_return_bps"] = trades["gross_return_bps"] - cost_bps
        trades["win"] = trades["net_return_bps"] > 0
        trades["time_ist"] = pd.to_datetime(trades["timestamp"]).dt.strftime("%H:%M")
        trades["dir_label"] = trades["trade_direction"].apply(lambda d: "LONG" if d > 0 else "SHORT")

        print(f"{'#':<3} | {'Time':<5} | {'Symbol':<14} | {'Dir':<5} | {'Pred (bps)':<10} | {'Gross (bps)':<12} | {'Cost':<9} | {'Net (bps)':<11} | {'Outcome'}")
        print("-" * 110)

        for i, (_, row) in enumerate(trades.iterrows(), start=1):
            pred_bps = row["pred_ridge"] * 10000.0
            outcome = "[WIN]" if row["win"] else "[LOSS]"
            print(
                f"{i:<3} | {row['time_ist']:<5} | {row['symbol']:<14} | {row['dir_label']:<5} | "
                f"{pred_bps:+8.2f} bps | {row['gross_return_bps']:+10.2f} bps | {row['cost_bps']:6.2f} bps | "
                f"{row['net_return_bps']:+9.2f} bps | {outcome}"
            )
            all_trades_records.append({
                "candidate_id": candidate.id,
                "timestamp": str(row["timestamp"]),
                "time_ist": row["time_ist"],
                "symbol": row["symbol"],
                "direction": row["dir_label"],
                "prediction_bps": round(pred_bps, 2),
                "gross_return_bps": round(row["gross_return_bps"], 2),
                "cost_bps": round(row["cost_bps"], 2),
                "net_return_bps": round(row["net_return_bps"], 2),
                "outcome": "WIN" if row["win"] else "LOSS"
            })

        mean_gross = trades["gross_return_bps"].mean()
        mean_net = trades["net_return_bps"].mean()
        win_rate = trades["win"].mean() * 100.0
        print("-" * 110)
        print(f"Summary: {len(trades)} Trades | Win Rate: {win_rate:.1f}% | Gross Expectancy: {mean_gross:+.2f} bps | Net Expectancy: {mean_net:+.2f} bps")

    # Save to JSON
    output_path = os.path.join("v2", "analysis", "metrics", "session_20260921_trade_logs.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_trades_records, f, indent=2)
    print(f"\n[INFO] Granular logs serialized to: {output_path}")


if __name__ == "__main__":
    extract_today_trade_logs()
