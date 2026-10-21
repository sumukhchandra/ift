# ALPHANSE V3 — PROPOSED FILE CLEANUP & ARCHIVAL LIST (PHASE 2)

**Document Date:** Tuesday, October 13, 2026  
**Status:** **PROPOSED — AWAITING USER APPROVAL BEFORE ANY DELETION**  
**Safety Protocol:** No files will be permanently deleted without explicit user confirmation. All approved files will be moved to a reversible zip/archive folder first.

---

## 1. Classification by Category

### Category A: Protected Files (DO NOT DELETE — ESSENTIAL)
These files form the core production system, historical market data, model weights, and live ledgers. They will be strictly preserved:
1. `run_live_trader.py` (Main production runner)
2. `check_status.py` (System sentinel)
3. `view_paper_trades.py` (Portfolio viewer)
4. `run_tests.py` (Full test suite)
5. `v3/execution/live_trader.py` (Core engine)
6. `v3/execution/kotak_adapter.py` (Broker adapter)
7. `v3/execution/edge_friction_gate.py` (Friction gate)
8. `v2/risk/cost_engine.py` (Statutory cost engine)
9. `QA/models/one_min_predictor.py` (ML Tree Ensemble)
10. `v3/models/multimodel/active_model_weights.json` (6 Specialist model weights)
11. `QA/data/*.csv` (Historical 1m market datasets)
12. `reports/live/paper_trading_ledger.json` (Production paper trading ledger)
13. `reports/live/runtime_state.json` (Real-time daemon state)
14. `reports/live/paper_intraday_summary.json` (Today's session summary)
15. `reports/TEST_RUN_EVIDENCE.txt` (Unit test evidence)
16. `reports/ALPHANSE_V3_AUDIT_AND_COMPLIANCE_REPORT.md` (Baseline audit report)

---

### Category B: Files Proposed for Archival (Move to `scripts/archive/` or `reports/archive/`)
These are legacy runner scripts, superseded screener scripts, and historical simulation tools that should be archived rather than deleted:

| Relative Path | Size | Reason for Archival |
| :--- | :---: | :--- |
| `scripts/run_phase3a_forensics.py` | 15.6 KB | Superseded by Phase 1 forensic audit report. |
| `scripts/run_phase3b_falsification.py` | 17.9 KB | Superseded by unit test invariants in `run_tests.py`. |
| `scripts/start_kotak_trading_session.py` | 19.1 KB | Redundant launcher; `run_live_trader.py` is the single production entry point. |
| `scripts/start_nifty50_live_prediction_trading.py` | 17.9 KB | Redundant legacy daemon; superseded by `run_live_trader.py`. |
| `scripts/start_todays_live_trading_session.py` | 5.4 KB | Wrapper script; superseded by `run_live_trader.py`. |
| `scripts/run_all_models_concurrent_live_trading.py` | 15.7 KB | Legacy multi-process runner that caused duplicate process collisions. |
| `scripts/run_realtime_live_trading_daemon.py` | 31.7 KB | Superseded by `v3/execution/live_trader.py`. |
| `scripts/run_side_test_screener.py` | 21.7 KB | One-off manual screener script. |
| `scripts/view_today_trades.py` | 8.5 KB | Duplicate of `view_paper_trades.py`. |
| `scripts/run_today_all_models_simulation.py` | 15.7 KB | Duplicate of `scripts/simulate_paper_session.py`. |
| `scripts/run_continuous_session_accuracy_tracker.py` | 7.4 KB | One-off accuracy tracker; superseded by live predictor logging. |
| `scripts/benchmark_full_session_capacity.py` | 15.3 KB | Completed one-time performance benchmark. |
| `scripts/run_adaptive_daily_pipeline.py` | 6.7 KB | Superseded by `run_daily_orchestrator.py`. |

---

### Category C: Proposed for Relocation to `reports/replay/`
These files contain historical simulation data from October 9, 2026, and should not sit in `reports/live/`:

| Relative Path | Size | Reason for Relocation |
| :--- | :---: | :--- |
| `reports/live/paper_replay_ledger.json` | ~3.8 KB | Friday, October 9 historical replay ledger. |
| `reports/live/paper_replay_ledger_mis.json` | ~3.8 KB | Friday, October 9 MIS short-selling benchmark. |
| `reports/live/paper_replay_ledger_cash_only.json` | ~362 B | Friday, October 9 cash-only replay ledger. |
| `reports/live/paper_intraday_summary_mis.json` | ~350 B | October 9 MIS summary. |
| `reports/live/paper_intraday_summary_cash_only.json` | ~279 B | October 9 cash-only summary. |
| `reports/live/real_vs_predicted_predictions.jsonl` | ~650 KB | 2,180 historical replay prediction records from Oct 9. |

---

### Category D: Files Proposed for Permanent Deletion (Only After User Approval)
These are temporary, scratch, and redundant output files:

| Relative Path | Size | Reason for Deletion |
| :--- | :---: | :--- |
| `scratch/test_market_api.py` | 2.5 KB | One-off scratch test file; functions now integrated in `run_live_trader.py --test-conn`. |
| `scripts/archive/check_live_session13_status.py` | 5.2 KB | Obsolete session 13 status script. |
| `scripts/archive/check_live_session14_status.py` | 5.2 KB | Obsolete session 14 status script. |
| `scripts/archive/run_session13_kotak_live_trader.py` | 31.7 KB | Obsolete session 13 daemon. |
| `scripts/archive/run_session14_kotak_live_trader.py` | 31.7 KB | Obsolete session 14 daemon. |

---

## 2. Reversible Backup Plan

Upon receiving user approval:
1. All files marked for archival or deletion will be zipped into `backup/pre_cleanup_backup_20261013.zip`.
2. Files in Category B will be moved to `scripts/archive/`.
3. Files in Category C will be moved to `reports/replay/`.
4. Only Category D files will be removed from working tree after backup verification.
