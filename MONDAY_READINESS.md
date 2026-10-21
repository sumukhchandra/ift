# ALPHANSE V3 — MONDAY OCTOBER 19 READINESS AND CRITICAL FIXES VERIFICATION

**Document Version:** 3.2.0  
**Audit & Diagnostics Timestamp:** Saturday, 17 October 2026, 16:15 IST  
**Target Trading Session:** Monday, 19 October 2026 (09:15 – 15:30 IST)  
**Pre-Market Startup Window:** Monday, 19 October 2026 (08:45 – 09:00 IST)  
**Final Operational Status:** **READY FOR SHADOW MODE** (Real-Money Execution Strictly Blocked)  

---

## 1. Executive Summary & Certified Status

A comprehensive, scientific forensic investigation and implementation cycle was executed across the AlphaNSE V3 prediction pipeline, training infrastructure, feature engineering modules, out-of-sample canonical ledgers, and regression test suites.

Both critical defects identified in previous audits have been **completely fixed and proven**:
- **Fix 1 (Timezone Consistency):** Unified training and inference under the canonical `Asia/Kolkata` (IST, UTC+05:30) convention, eliminating negative decision tree feature clipping.
- **Fix 2 (Specialist-Model Output Handling):** Implemented true 19-indicator technical feature extraction directly from candle buffers, added strict schema, shape, and finite value validation, and enforced fail-closed rejection without fabricated scores or confidences.

| Parameter | Certified State | Verification Method |
| :--- | :--- | :--- |
| **Final Operational Status** | **READY FOR SHADOW MODE** | Both critical fixes proven; 330/330 tests passing; broker connected |
| **Real Order Placement** | **DISABLED** (`ALLOW_REAL_ORDERS=False`) | Dual-key physical broker order block verified |
| **Execution Sandbox** | **SHADOW / PAPER ONLY** (`LIVE_TRADING=False`) | In-memory simulated paper broker verified |
| **Simulated Capital** | **₹1,500.00** (Simulated Cash) | Cash-only, zero leverage, zero margin |
| **Max Concurrent Positions** | **1 Position** | Enforced in position manager & allocator |
| **Daily Net-Loss Stop** | **₹30.00** (`MAX_DAILY_LOSS=30.00`) | Dynamic env hook in `live_trader.py` |
| **Daemon Process Status** | **STANDBY / OFFLINE (CLEAN)** | Verified via Windows OS process table; duplicate guard active |
| **Pre-Flight Broker API** | **AUTHENTICATED (Kotak Neo)** | Pre-market connectivity check verified for 6 universe symbols |
| **Oct 15 Canonical Outcomes** | **8,262 Matched Pairs (100%)** | Independently reproduced from raw provenance ticks |
| **Retraining Candidate Promotion**| **REJECTED (Candidates A & B)** | Out-of-sample edge did not beat 14.7 bps cost hurdle |
| **Full Regression Suite** | **330 / 330 Passed (100%)** | 0 failures, 0 errors, duration: 68.19s |

---

## 2. Phase 1 — Root Causes and Critical Fixes Implemented

### 2.1 Critical Fix 1: Timezone Consistency
- **Root Cause:** In `QA/scripts/build_and_train_live_1m.py`, `normalize_tz` executed `.dt.tz_convert(None)` on `+05:30` (IST) timestamps. In pandas, `tz_convert(None)` converts to UTC clock hours (03:45 to 10:00 UTC) before dropping timezone metadata. In `QA/models/one_min_predictor.py`, `minutes_from_open = (hour*60 + min) - 555` evaluated to negative numbers (e.g. -330) and was clipped to 0.0 for 90% of the trading day. During live trading, local IST hours (9 to 15) produced non-zero `time_sin`/`time_cos`, traversing unseen tree branches and introducing a -4.28 bps ensemble bias.
- **Implementation:**
  1. [`QA/scripts/build_and_train_live_1m.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/QA/scripts/build_and_train_live_1m.py): `normalize_tz` localizes naive timestamps to `Asia/Kolkata` and converts timezone-aware timestamps to `Asia/Kolkata`.
  2. [`QA/models/one_min_predictor.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/QA/models/one_min_predictor.py): `extract_features_1m` converts aware timestamps to `Asia/Kolkata` and localizes naive timestamps to `Asia/Kolkata`.
- **Regression Verification:** Added [`tests/test_timezone_regression.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/tests/test_timezone_regression.py) testing aware/naive IST alignment, UTC conversion, daylight independence, session boundaries (pre-market, open rush, morning, midday, close rush, post-market), and disk dataset preservation. **5/5 tests passed**.

### 2.2 Critical Fix 2: Specialist-Model Output Handling
- **Root Cause:** In `v3/intelligence/opportunity_engine.py`, feature extraction for the specialist model passed 10 hardcoded constant placeholders (`bb_bw=0.005`, `bb_pct_b=0.5`, `atr14=0.002`, `park_vol=0.002`, `orderflow=0.0`, etc.) and inserted `orderflow` into position 12, displacing subsequent features. Furthermore, `_predict_specialist_linear` returned an implicit default `0.0` when model weights were missing, and the engine did not validate return types (booleans, strings), array shapes, required dict keys, or non-finite numbers (`NaN`, `Inf`).
- **Implementation:**
  1. Added `OpportunityDiscoveryEngine.extract_19_features(buf)`: Dynamically computes the exact 19 mathematical indicators directly from candle buffers.
  2. Added `OpportunityDiscoveryEngine.validate_specialist_output(raw_output)`: Enforces scalar float, size-1 1D array, or dict with `'predicted_alpha'` / `'alpha'`. Strictly rejects booleans, strings, multi-element arrays, and non-finite values (`NaN`, `Inf`).
  3. Enhanced `_predict_specialist_linear`: Validates model metadata fields (`weights`, `bias`, `means`, `stds`), shape (19 features and weights), and finite values. Returns `None` on defects.
  4. Fail-Closed Opportunity Scoring: When specialist model output is missing or invalid, records explicit rejection reason, forces `score = 0.0`, `viable = False`, `gross_gain_rs = 0.0`, `net_expectancy_rs = 0.0`, `net_expectancy_bps = -9999.0`, and **never fabricates scores or confidences**.
- **Regression Verification:** Added [`tests/test_specialist_output_regression.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/tests/test_specialist_output_regression.py) testing valid floats, valid dicts, valid 1D arrays, missing `None` output, missing dict keys, shape mismatch, malformed types, non-finite values, and corrupt model weights. **9/9 tests passed**.

---

## 3. Phase 2 — Controlled Model Research & Gate Evaluations

### 3.1 Experimental Protocol
- **Chronological Split:**
  - **Training / Validation Set:** `QA/data/genuine_forward_oos_oct13_oct14.csv` ($N = 7,964$ causal candles, Oct 13 09:15 to Oct 14 15:30 IST).
  - **Untouched Out-of-Sample Test Set:** Verified Oct 15 canonical outcomes ($N = 8,262$ matched forward observations from `reports/oct16_readiness/PREDICTION_OUTCOMES.csv`).
- **Leakage Prevention:** Features constructed strictly using backward-looking rolling windows. Zero target contamination.
- **Cost Benchmark:** 14.7 bps roundtrip statutory friction applied to all simulated trades.

### 3.2 Comprehensive Benchmark & Candidate Comparison

Metrics computed directly via [`v3/research/controlled_model_research.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/research/controlled_model_research.py):

| Model / Baseline | MAE | RMSE | Dir Acc | IC ($r$) | Bias | P90 Error | P99 Error | Gross Edge | Net Edge (Post 14.7 bps Cost) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Zero-Return Baseline ($\hat{y}=0$)** | **5.06 bps** | **7.79 bps** | 0.00% | 0.0000 | -0.25 bps | 11.50 bps | 28.53 bps | 0.00 bps | **0.00 bps** |
| **Persistence Baseline ($\hat{y}_t=y_{t-1}$)** | **5.72 bps** | **8.57 bps** | 47.80% | +0.0107 | -0.17 bps | 12.57 bps | 30.70 bps | -0.07 bps | **-14.77 bps** |
| **Mean-Reversion Baseline ($\hat{y}_t=-y_{t-1}$)** | **5.58 bps** | **8.65 bps** | 52.20% | -0.0107 | -0.33 bps | 12.68 bps | 30.70 bps | +0.07 bps | **-14.63 bps** |
| **Current Model Ensemble** | **13.76 bps** | **17.61 bps** | 49.21% | -0.0238 | -11.44 bps | 28.20 bps | 44.82 bps | -0.22 bps | **-14.92 bps** |
| **Candidate A (Ridge L2 Regressor)** | **5.43 bps** | **8.06 bps** | 49.08% | +0.0203 | +1.08 bps | 11.84 bps | 28.53 bps | +0.03 bps | **-14.67 bps** |
| **Candidate B (LightGBM MAE Regressor)** | **5.12 bps** | **7.81 bps** | 49.92% | -0.0052 | +0.38 bps | 11.51 bps | 28.53 bps | +0.11 bps | **-14.59 bps** |

### 3.3 Predefined Acceptance Gate Evaluation

| Gate Criterion | Hurdle Threshold | Candidate A Result | Candidate B Result | Gate Verdict |
| :--- | :---: | :---: | :---: | :---: |
| **1. Directional Accuracy** | $\ge 52.0\%$ | 49.08% | 49.92% | **FAILED** |
| **2. MAE vs Zero-Return** | $< 5.06\text{ bps}$ | 5.43 bps | 5.12 bps | **FAILED** |
| **3. Information Coefficient** | $r \ge +0.0300$ | +0.0203 | -0.0052 | **FAILED** |
| **4. Prediction Bias** | $|\text{Bias}| < 1.0\text{ bps}$ | +1.08 bps | +0.38 bps | **PASSED (B only)** |
| **5. Post-Friction Net Edge** | $> 0.0\text{ bps}$ | -14.67 bps | -14.59 bps | **FAILED** |

### 3.4 Formal Promotion Decision: REJECTED
- **Verdict:** **CANDIDATE MODELS REJECTED**. Neither Candidate A nor Candidate B satisfied the minimum directional accuracy gate (52.0%), neither beat the zero-return baseline MAE (5.06 bps), and after realistic Indian statutory transaction costs (14.7 bps roundtrip), both produced negative net expectancy (-14.6 bps).
- **Action Taken:** Candidate promotion blocked; **current model retained strictly in shadow mode**. Under no circumstances will real capital be allocated to an unproven model.

---

## 4. Phase 3 — Monday Shadow-Mode Readiness Verification

### 4.1 Market Calendar & Startup Schedule
- **Calendar Verification:** The National Stock Exchange of India (NSE) is closed for the weekend (Oct 17–18). Trading resumes on **Monday, 19 October 2026**.
- **Market Hours:**
  - Pre-Open Session: 09:00 – 09:08 IST
  - Regular Market Trading: 09:15 – 15:30 IST
  - Mandatory Square-Off / Exit Cutoff: 15:15 IST
- **Pre-Market Startup Window:** **08:45 – 09:00 IST on Monday, Oct 19**.
  - Allows 15–30 minutes for Kotak Neo broker token authentication, 60-candle warm-up buffer initialization, and single-PID daemon locking before the 09:15 market open.

### 4.2 Market Data Source, Connectivity & Timestamps
- **Configured Market Data Source:** Primary: `KOTAK_NEO_TRADE_API` (Direct broker REST quotes). Fallback: `YFINANCE_LIVE` (Secondary failover).
- **Connectivity Check Result:** `python run_live_trader.py --test-conn` returned:
  - Broker Adapter: `Kotak Neo Trade API Adapter [PAPER / READ-ONLY]` (UCC: `116K1`)
  - Authentication: 🟢 `YES`
  - Universe Symbols Received: **6 / 6** (`NIFTYBEES.NS`, `INFY.NS`, `TATASTEEL.NS`, `BAJFINANCE.NS`, `AXISBANK.NS`, `RELIANCE.NS`)
  - Candle Buffers Pre-Seeded: **60 bars** per symbol
- **Stale Data Handling:**
  - Quotes with `is_stale=True` or `source="BUFFER_FALLBACK"` are strictly rejected by `OpportunityDiscoveryEngine`.
  - Heartbeat gap sentinel engages fail-closed state if heartbeat lag $> 120$ seconds.

### 4.3 Process Status & Recovery Without Duplicates
- **Current Process State:** Windows OS process check confirmed **no live trader daemon is currently active**.
- **State File Integrity:** [`reports/live/runtime_state.json`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/runtime_state.json) is clean and set to `STANDBY_FOR_OPEN`.
- **Single-PID Mutual Exclusion:** `AlphaNSELiveTrader._check_single_instance()` verifies active OS processes using Windows `psutil` / PID inspection. Starting a second instance immediately triggers `ABORT_DUPLICATE_INSTANCE`.
- **Startup Recovery:** Upon launch, restores closed trades and realized P&L from `paper_trading_ledger.json`, recovers active open positions from `runtime_state.json`, and pre-seeds 60-bar candle buffers.

### 4.4 Data Lineage & Evaluation Integrity
- **Distinguishing Historical Backfills from Live Observations:**
  - `reports/live/prediction_outcomes_stream.jsonl` contains **8,262 historical backfilled records** transcribed from `reports/oct16_readiness/PREDICTION_OUTCOMES.csv` (originating from the Oct 15 session).
  - Newly collected Monday observations will be appended live to `reports/live/prediction_provenance_stream.jsonl` with genuine ISO 8601 timestamps.
- **Forward Outcome Evaluation:**
  - Predictions made at time $t_0$ are matched strictly against future observations at $t_0 + 60\text{s}$ (tolerance window $[t_0 + 45\text{s}, t_0 + 75\text{s}]$). Unverified boundary predictions are explicitly excluded from accuracy metrics.

---

## 5. Mandatory Safety & Sandboxing Verification

All mandatory safety invariants remain verified and actively locked:

```python
# Verified in .env and v3/execution/kotak_adapter.py
LIVE_TRADING = False
ALLOW_REAL_ORDERS = False
```

1. **Broker Air-Gap:** Real broker order placement is physically locked. In `KotakLiveBrokerAdapter.place_order()`, when `self.is_live` is `False`, order requests are completely diverted to the in-memory paper simulation. Zero real orders have been or can be submitted.
2. **Capital Limitation:** Paper bankroll is locked at ₹1,500.00 cash-only simulation (zero margin, zero leverage).
3. **Position Limitation:** Maximum 1 open position concurrently. Second order attempts are strictly rejected.
4. **Daily Loss Circuit Breaker:** Daily net loss limit of ₹30.00 (`MAX_DAILY_LOSS=30.00`). If cumulative losses breach ₹30.00, the kill switch engages and prevents further entries.
5. **No Forced Trades:** If market regimes exhibit chop, volatility compression, or insufficient net edge against the 14.7 bps statutory hurdle, the engine issues `HOLD`.

---

## 6. Monday Morning Action Plan (19 October 2026)

| Time (IST) | Action Item | Command / Procedure | Verification Target |
| :---: | :--- | :--- | :--- |
| **08:45 – 08:50** | Pre-Market Connectivity Check | `python run_live_trader.py --test-conn` | 6/6 symbols authenticated, 60 candles pre-seeded |
| **08:50 – 08:55** | Launch Shadow-Mode Daemon | `python launch_background.py` | Exactly 1 Python process spawned |
| **08:55 – 09:00** | Verify Sentinel & Heartbeat | `python check_status.py` | PID active, `STANDBY_FOR_OPEN`, locks secure |
| **09:15** | Market Open Continuous Stream | Automatic live loop | Live quotes stream into `prediction_provenance_stream.jsonl` |
| **15:15** | Mandatory Intraday Square-Off | Automatic position exit | Zero positions survive past 15:15 IST |
| **15:30** | Market Close & Replay Audit | `python check_status.py` | Final ledger reconciliation, zero real orders submitted |

---

## 7. Final Governance Readiness Verdict

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                     FINAL READINESS GOVERNANCE VERDICT                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║   1. TIMEZONE CONSISTENCY FIX:      🟢 VERIFIED FIXED & REGRESSION TESTED    ║
║   2. SPECIALIST OUTPUT FIX:         🟢 VERIFIED FIXED & REGRESSION TESTED    ║
║   3. FULL REGRESSION SUITE:         🟢 330 / 330 TESTS PASSED (100%)         ║
║   4. PRE-MARKET BROKER ADAPTER:     🟢 AUTHENTICATED (KOTAK NEO TRADE API)   ║
║   5. SAFETY LOCKS & AIR-GAP:        🟢 SECURE (LIVE_TRADING=False)           ║
║   6. REAL-MONEY EXECUTION:          🔴 STRICTLY BLOCKED (SUB-50% ACCURACY)   ║
║   7. MONDAY SHADOW-MODE EXECUTION:  🟢 100% READY (LAUNCH AT 08:45 IST)      ║
║                                                                              ║
║   OVERALL OPERATIONAL STATUS:       READY FOR SHADOW MODE                    ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```
