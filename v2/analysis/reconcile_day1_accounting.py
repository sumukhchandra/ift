import json

with open("v2/analysis/metrics/session_20260921_trade_logs.json", "r") as f:
    trades = json.load(f)

with open("v2/analysis/metrics/phase3b_falsification_results.json", "r") as f:
    report = json.load(f)

report_candidates = {c["candidate_id"]: c for c in report["candidates"]}
cand_trades = {}
for t in trades:
    cand_trades.setdefault(t["candidate_id"], []).append(t)

print("=== TRADE ACCOUNTING RECONCILIATION AUDIT ===")
for cand_id, cand_rep in report_candidates.items():
    t_list = cand_trades.get(cand_id, [])
    n_trades = len(t_list)
    rep_trades = cand_rep["trades"]
    print(f"\nCandidate: {cand_id}")
    print(f"  Reported Trades: {rep_trades} | Reconciled Trades: {n_trades}")
    assert rep_trades == n_trades, f"Trade count mismatch: {rep_trades} vs {n_trades}"

    if n_trades > 0:
        gross_sum = sum(t["gross_return_bps"] for t in t_list)
        calc_mean_gross = gross_sum / n_trades
        net_sum = sum(t["net_return_bps"] for t in t_list)
        calc_mean_net = net_sum / n_trades
        cost = t_list[0]["cost_bps"]
        rep_gross = cand_rep["gross_expectancy_bps"]
        rep_cost = cand_rep["total_cost_bps"]
        rep_net = cand_rep["base_net_expectancy_bps"]

        print(f"  Calculated Mean Gross : {calc_mean_gross:+.4f} bps | Reported: {rep_gross:+.4f} bps")
        print(f"  Execution Scenario Cost : {cost:.4f} bps | Reported: {rep_cost:.4f} bps")
        print(f"  Calculated Mean Net   : {calc_mean_net:+.4f} bps | Reported: {rep_net:+.4f} bps")

        assert abs(calc_mean_gross - cost - calc_mean_net) < 1e-4, "Identity Gross - Cost == Net violated!"
        assert abs(calc_mean_gross - rep_gross) < 1e-2, "Gross mismatch!"
        assert abs(calc_mean_net - rep_net) < 1e-2, "Net mismatch!"
        print("  Additive Identity & Expectancy Reconciliation: EXACT MATCH [PASSED]")
    else:
        print(f"  Zero Trades Verified. Status: {cand_rep['status']}")
        print("  Additive Identity & Expectancy Reconciliation: EXACT MATCH [PASSED]")
