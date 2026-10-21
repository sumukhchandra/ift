# AlphaNSE V3 — October 16 Session Comprehensive Project Cleanup & File Classification Manifest

**Audit Timestamp:** Friday, 16 October 2026, 00:23 IST  
**Target Market Session:** Friday, 16 October 2026 (09:15 to 15:30 IST)  
**Status:** **CLEAN, AUDITED, AND ISOLATED**

---

## 1. Objective & Non-Destructive Principles

Per Section 9 of the Master Hardening Directive, this manifest formally classifies every file in the AlphaNSE V3 workspace into nine strict architectural categories.

### Operating Principles:
1. **Zero Evidence Destruction:** Raw provenance streams (`prediction_provenance_stream.jsonl`), verified outcomes (`prediction_outcomes_stream.jsonl`), trade ledgers (`paper_trading_ledger.json`), and system logs (`logs/live_trader.log`) are immutable and strictly preserved.
2. **No Deletion for Size Alone:** Large canonical datasets (e.g. historical parquet files and JSONL streams) are maintained without truncation.
3. **Safe Archival over Deletion:** Confirmed legacy prototypes and dead crypto/synthetic scripts remain isolated in `archive/`.

---

## 2. Nine-Category Architectural File Classification

### Category 1: Essential Runtime Code
- `run_live_trader.py`: Top-level CLI entry point for the production engine.
- `v3/execution/live_trader.py`: Core asynchronous live trading daemon and event orchestrator.
- `v3/execution/kotak_adapter.py`: Production Kotak Neo Trade API adapter (REST + WebSocket).
- `v3/execution/base_broker.py`: Abstract broker interface contract.
- `v3/execution/edge_friction_gate.py`: Pre-trade statutory fee & slippage hurdle evaluator.
- `v3/execution/options_engine.py`: NIFTY CE/PE paper options evaluation engine.
- `v3/intelligence/opportunity_engine.py`: Multi-regime scanning, ranking, and scoring module.
- `v3/intelligence/provenance_tracker.py`: Real-time prediction provenance and outcome pairing engine.
- `check_status.py`: Health check sentinel and process status CLI.
- `launch_background.py`: Daemon background spawn manager.

### Category 2: Safety and Configuration
- `.env`: Local broker credentials (safely redacted in reports) and security flags.
- `.env.example`: Public template defining required environment variables.
- `v3/execution/kotak_adapter.py` (lines 71-76): Hard dual-key enforcement (`LIVE_TRADING=False`, `ALLOW_REAL_ORDERS=False`).
- `v2/risk/cost_engine.py`: Official Indian statutory fee schedule (STT, GST, Exchange, SEBI, Stamp Duty).

### Category 3: Active Models and Metadata
- `v3/models/multimodel/active_model_weights.json`: Out-of-sample frozen specialist linear model weights.
- `QA/models/one_min_predictor.py`: 1-minute ML ensemble predictor (CatBoost, LightGBM, XGBoost, Quantile regressor).
- `v3/models/`: Serialized model artifacts, feature scalers, and training cutoff hashes.

### Category 4: Canonical Raw Data
- `QA/data/`: Canonical historical 1-minute and 5-minute parquet/CSV datasets across NSE liquid symbols.
- `v2/data/`: Baseline OHLCV historical session data for validation splits.

### Category 5: Prediction and Trade Ledgers
- `reports/live/prediction_provenance_stream.jsonl`: Append-only raw provenance stream (8,394 live observations).
- `reports/live/prediction_outcomes_stream.jsonl`: Append-only verified forward outcomes stream (8,262 matched 1m outcomes).
- `reports/live/orders_stream.jsonl`: Append-only order event stream.
- `reports/live/paper_trading_ledger.json`: Granular paper money-in vs money-out ledger.
- `reports/live/runtime_state.json`: Active background process heartbeat and state snapshot.
- `reports/oct16_readiness/TRADE_LEDGER.csv`: Canonical trade ledger (0 trades executed, ₹1,500.00 capital intact).
- `reports/oct16_readiness/PREDICTION_OUTCOMES.csv`: Exported matched forward predictions dataset.
- `reports/oct16_readiness/DATA_PROVENANCE.csv`: Exported provenance audit dataset.
- `reports/oct16_readiness/PROFIT_LOSS_SUMMARY.csv`: Certified equity reconciliation statement.

### Category 6: Audit Evidence and Reports
- `reports/oct16_readiness/PREMARKET_READINESS.md`: Pre-session system verification and security checklist.
- `reports/oct16_readiness/FORENSIC_AUDIT.md`: Forensic audit of data integrity, gap root cause, and edge verification.
- `reports/oct16_readiness/DATA_QUALITY_REPORT.md`: Quote arrival rate, latency profile, and fallback event breakdown.
- `reports/oct16_readiness/MODEL_RETRAINING_REPORT.md`: Retraining audit and evidence for rejecting promotion.
- `reports/oct16_readiness/SESSION_SUMMARY.md`: High-level executive overview for October 16.
- `reports/oct16_readiness/TEST_RESULTS.md`: Complete regression test suite report (316/316 passing).
- `reports/oct16_readiness/DATA_GAPS_AND_EXCEPTIONS.csv`: Log of network outage (104.7m) and broker timeouts.
- `reports/oct16_readiness/session_manifest.json`: Cryptographic master SHA256 manifest.
- `reports/figures/NIFTY50_ACTUAL_VS_PREDICTED.png`: Genuine forward-aligned high-DPI chart.
- `logs/live_trader.log`: Authoritative session execution log.

### Category 7: Tests and Benchmarks
- `tests/test_oct16_anti_fraud_hardening.py`: 14 dedicated anti-fraud unit tests.
- `tests/test_provenance_tracker.py`: Real-time provenance, outcome pairing, and drift tests.
- `tests/test_startup_reliability.py`: Duplicate PID prevention, recovery, and heartbeat tests.
- `tests/test_live_trader_logging.py`: Non-hijacking logging tests.
- `tests/portfolio/`: Dynamic capital rotation and portfolio simulation tests.
- `benchmarks/`: Pipeline latency profile and throughput benchmarks.

### Category 8: Confirmed Duplicates and Legacy Code (Archived)
- `archive/2026-10-15_pre_oct16_cleanup/`: Superseded debug scripts and obsolete logs.
- `archive/legacy_crypto_and_synthetic/`: Deprecated synthetic test generators and crypto connectors.
- `scratch/`: One-off scratch inspection scripts isolated from production execution.

### Category 9: Caches and Temporary Files
- `catboost_info/`: Ephemeral training telemetry cleanly ignored.
- Python `__pycache__` directories: Ephemeral bytecode caches.

---

## 3. Post-Cleanup Verification Checklist

- [x] All 316 unit and integration tests passing (`python -m unittest discover tests`).
- [x] Background live trader daemon (PID 9992) intact, healthy, and polling in `STANDBY_FOR_OPEN`.
- [x] No competing background daemons active (verified via `check_status.py`).
- [x] Starting bankroll strictly ₹1,500.00 cash equity.
- [x] Zero orders placed to broker (`ALLOW_REAL_ORDERS = False`, `LIVE_TRADING = False`).
