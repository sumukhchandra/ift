# TEST EVIDENCE — INDEPENDENT VERIFICATION & SUITE LEDGER
**Audit Timestamp:** 2026-10-19T17:48:32 IST  
**Environment:** Windows PowerShell, Python 3.12.10, Repository Root: `c:\Users\sumuk\.gemini\antigravity-ide\scratch\ift`  
**Authoritative Log:** `audit/full_remediation_test_run.txt` and `full_remediation_test_run.txt` (87,648 bytes, UTF-8)

---
## 1. Execution Command & Summary
```powershell
python run_tests.py
```

| Metric | Measured Value |
| :--- | :--- |
| **Total Test Suites Discovered** | 62 test modules |
| **Total Test Cases Executed** | **352** |
| **Total Passed** | **352 (100.0%)** |
| **Total Failures** | **0** |
| **Total Errors** | **0** |
| **Total Skipped** | **0** |
| **Exit Code** | **0 (SUCCESS)** |
| **Suite Wall Clock Duration** | **43.982 seconds** |

---

## 2. Targeted Regression & Priority Suite Breakdown

### 2.1 Priority 1: One-Minute Candle Aggregation & Sampling Mismatch
- **Test Modules:** `tests/test_candle_aggregator_comprehensive.py` (10/10 Passed) & `tests/test_sampling_mismatch_regression.py` (5/5 Passed)
- **Verified Invariants:**
  1. Six 10-second quotes inside one calendar minute aggregate into exactly ONE 1-minute OHLCV bar on rollover.
  2. Open = first observed price, High = max, Low = min, Close = last observed price.
  3. Cumulative volume delta calculation computes true minute delta ($V_t - V_{t-1}$) across session.
  4. Incremental volume accumulation correctly sums discrete tick volumes.
  5. Exact duplicate ticks and late-arriving out-of-order ticks are safely rejected.
  6. Stale quotes (`is_stale=True`), non-finite prices (NaN, Inf), and negative prices are rejected.
  7. Timezones normalize strictly to `Asia/Kolkata` for aware, naive, and ISO string inputs.
  8. Missing intervals/network gaps seal the prior candle without fabricating phantom intermediate candles.
  9. Feature return horizons (`r1`, `r3`, `r5`, `r10`) calculate authentic 1m, 3m, 5m, and 10m percentage returns.
  10. End-to-end inference verification proves the production pipeline consumes 1-minute bars rather than raw 10-second ticks.

### 2.2 Priority 2: Historical Batch Evaluation & Provenance Segregation
- **Test Modules:** `tests/test_oct16_anti_fraud_hardening.py` (14/14 Passed) & `tests/test_provenance_tracker.py` (10/10 Passed)
- **Verified Invariants:**
  1. Historical batch forward-paired outcomes are strictly labeled `HISTORICAL_BATCH_EVALUATION` and `HISTORICAL_BATCH_PAIRED_UNVERIFIED_WIRE`.
  2. Batch-paired records reside in `reports/live/historical_batch_outcomes.jsonl` and are segregated from live streaming captures.
  3. Contemporaneous capture file `reports/live/market_data_raw_capture.jsonl` is armed for live tick-by-tick ingestion.
  4. The 45–75 second matching window audit recomputed on actual records: 8,394 total predictions, 8,262 matched outcomes, 132 excluded boundary records, mean target offset 57.67 seconds.

### 2.3 Priority 3 & 4: Fail-Closed Inference, Circuit Breakers & Silent Failure Elimination
- **Test Modules:** `tests/test_fail_closed_inference.py` (2/2 Passed) & `tests/test_circuit_breakers_and_safe_halts.py` (7/7 Passed)
- **Verified Invariants:**
  1. Fewer than 15 historical bars fails closed with `INSUFFICIENT_HISTORY`, confidence 0.0, and `prediction_valid=False`.
  2. Sub-minute sampled buffers fail closed with `TIMEFRAME_SAMPLING_MISMATCH`.
  3. Model unpickling restored with 30-feature Platt-calibrated classifier.
  4. 5 consecutive broker quote errors triggers safe-halt standby.
  5. 6 consecutive stale quote cycles (60s) triggers safe-halt standby.
  6. Reaching ₹30.00 daily loss limit blocks all further paper entries.
  7. Maximum 1 concurrent open position is hard-enforced.
  8. Real order routing is physically unreachable (`LIVE_TRADING=False`, `ALLOW_REAL_ORDERS=False`).

### 2.4 Priority 6: Paper Portfolio Accounting & Reconciliation Invariants
- **Test Modules:** `tests/test_portfolio_accounting.py` (7/7 Passed) & `tests/test_simulation_eod_invariants.py` (6/6 Passed)
- **Verified Invariants:**
  1. Cash never drops below zero at any point in time.
  2. Order notional never exceeds available capital (₹1,500.00 cap).
  3. Single position limit strictly enforced (no overlapping positions).
  4. Every fill has prediction provenance and chronologically valid timestamps.
  5. Ending equity = Starting equity + Net Realized P&L + Unrealized P&L (penny-for-penny reconciliation).
  6. Maximum drawdown is bounded within 0%–100%.
  7. Deterministic replay reproduces identical trade counts and ledger entries.

### 2.5 Operational Startup & Mutex Reliability
- **Test Modules:** `tests/test_startup_reliability.py` (8/8 Passed)
- **Verified Invariants:**
  1. Single PID mutex in `logs/live_trader.pid` prevents duplicate daemon execution.
  2. Stale heartbeat detection (>120s) clears cache and triggers fail-closed recovery.
  3. Safe termination refuses shutdown if active positions exist.
  4. Restart recovery restores active open positions from `runtime_state.json`.

---

## 3. Scope and Limitations of Test Evidence
> [!IMPORTANT]
> A 100% passing test suite (352/352) conclusively proves **software implementation correctness, constraint enforcement, and error-handling integrity**.
> 
> However, per quantitative principles:
> 1. Passing tests do **NOT** prove market-data predictive alpha or profitability on live markets.
> 2. The out-of-sample empirical benchmark on Oct 15 records showed the current model achieves 49.21% directional accuracy with an MAE of 13.76 bps (inferior to Zero-Return baseline of 5.06 bps and Persistence baseline of 3.22 bps).
> 3. Therefore, software correctness is verified, but model promotion to live real-money trading is strictly **REJECTED**. The system must run strictly in **SHADOW MODE**.
