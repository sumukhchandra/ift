import json

with open("reports/live/phase2_cost_aware_research_report.json") as f:
    d = json.load(f)

for h in ["5", "10", "15"]:
    print(f"Horizon {h}m (Mean move: {d['prediction_metrics_by_horizon'][h]['mean_move_bps']:.2f} bps, P90: {d['prediction_metrics_by_horizon'][h]['p90_move_bps']:.2f} bps):")
    for m in d["prediction_metrics_by_horizon"][h]["models"]:
        print(f"  {m['name']}: MAE={m['mae_bps']}, DirAcc={m['dir_acc_pct']}%, RankIC={m['rank_ic']}, GrossExp={m['gross_exp_bps']} bps, NetExp={m['net_exp_bps']} bps")
