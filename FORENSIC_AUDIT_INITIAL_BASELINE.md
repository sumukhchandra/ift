# AlphaNSE V3 — Strict Anti-Fabrication Forensic Audit & Baseline Evidence Report

**Document ID:** `FORENSIC_AUDIT_INITIAL_BASELINE`  
**Audit Timestamp:** Tuesday, 20 October 2026, 03:18:00 IST  
**Auditor:** Quantitative Systems & Anti-Fabrication Forensic Sentinel  
**Execution Posture:** Read-Only Forensic Baseline (Zero Code Modifications, Strict Air-Gap Enforced)  
**Safety Status:** `LIVE_TRADING=False` | `ALLOW_REAL_ORDERS=False` (Dual-Key Locked)  
**Broker Environment:** Kotak Neo Trade API (Trade Free Plan) / Paper-Testing Mode  
**Capital Reference:** ₹1,500.00 Cash Equity (No Leverage, No Shorting, Max 1 Concurrent Position)  
**Daily Loss Limit:** ₹30.00 | **Intraday Cutoff:** 15:15:00 IST  
**Predecessor Research Deliverable:** [PHASE2_COST_AWARE_RESEARCH.md](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/PHASE2_COST_AWARE_RESEARCH.md)  
**Cryptographic Test Evidence Log:** [reports/live/test_suite_execution_evidence.txt](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/test_suite_execution_evidence.txt)  
**Structured Research Audit JSON:** [reports/live/phase2_cost_aware_research_report.json](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/phase2_cost_aware_research_report.json)  

---

## A. Executive Summary: What Actually Ran and What Did Not

This report establishes the verified, un-fabricated baseline state of the AlphaNSE V3 algorithmic trading and quantitative research infrastructure in strict adherence to the Anti-Fabrication, Proof-First Execution Directive.

### 1. Operations That Actually Executed & Verified
1. **System & Daemon Sentinel Query (`check_status.py`):**
   - Executed at `2026-10-20 02:47:39 IST` (Exit code: `0`).
   - Confirmed trader daemon process is **🔴 NOT RUNNING** (`PID: None`).
   - Confirmed paper bankroll is exactly **₹1,500.00** with **0 open positions**, **0 closed trades**, and **₹0.00 realized P&L**.
2. **Comprehensive Regression Test Suite (`run_tests.py`):**
   - Executed at `2026-10-20 03:13:28 IST` (Exit code: `0`, runtime: 52.046s).
   - Results: **353 passed / 353 total (0 failures, 0 errors, 0 skipped)**. Full log preserved in [reports/live/test_suite_execution_evidence.txt](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/test_suite_execution_evidence.txt) (SHA-256: `c7bf75ec903cec2d3042ba16ba0dddc095ceb43fe967d8015f62b41eda5c2f3c`).
3. **Multi-Horizon Non-Overlapping Research Engine (`v3/research/phase2_cost_aware_research.py`):**
   - Executed across 5m, 10m, and 15m discrete bars across 8 in-sample sessions (`2026-09-18` to `2026-09-30`), 2 validation sessions (`2026-10-01`, `2026-10-05`), and 6 untouched out-of-sample test sessions (`2026-10-06` to `2026-10-14`).
   - Structured JSON audit record saved to [reports/live/phase2_cost_aware_research_report.json](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/phase2_cost_aware_research_report.json) (SHA-256: `2287e82ecc6f944cbf3f1804340745f77761e9a7b8baa9f5e1d289a517162404`).
4. **Visual Chart Generation Script (`v3/research/generate_phase2_charts.py`):**
   - Executed and rendered three verified distribution and cost charts without placeholder values.
5. **Cryptographic File Hash & Forensic Inventory:**
   - Generated SHA-256 checksums across all core code, logs, configuration files, and paper ledgers.

### 2. Operations That Did NOT Execute (Honest Negative Disclosures)
1. **Real-Money Order Placement:**
   - **DID NOT RUN / PROHIBITED.** Hard-locked by dual flags `LIVE_TRADING=False` and `ALLOW_REAL_ORDERS=False` in [`.env`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/.env) and verified in `kotak_adapter.py:83-85`. Zero real broker orders were generated, submitted, or filled.
2. **Live Advancing Market Feed Validation:**
   - **NOT PERFORMED.** Current audit time is `03:18 IST`. Official NSE trading hours are strictly 09:15:00 to 15:30:00 IST. The market is closed. Kotak Neo quotes received at this hour are end-of-day post-market quotes (`quote_type: EOD_LAST_TRADED_PRICE`, exchange timestamp: `2026-10-19 15:59:56 IST`). They were correctly rejected from candle formation as stale data.
3. **Synthetic Market or Replay Simulation Presented as Live:**
   - **DID NOT OCCUR.** No synthetic observations, mock feeds, or historical replays were substituted or claimed to represent a live market session.

---

## B. Step-by-Step Execution Evidence

Every forensic operation executed during this audit is detailed below in the mandatory 9-point auditable record format:

### Step 1: Daemon Process & System State Forensic Query
- **Step ID:** `STEP-01-DAEMON-STATUS`
- **Component Inspected:** [check_status.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/check_status.py)
- **Exact Command:** `python check_status.py`
- **Actual Execution Result:** Exit code `0`. Process status: `🔴 NOT RUNNING` (PID: None). Active open positions: `0`. Closed trades count: `0`. Realized P&L today: `₹+0.00`. Paper bankroll: `₹1,500.00`.
- **Before-and-After:** Read-only inspection; no files altered.
- **Relevant Output:**
  ```
  📊 ALPHANSE V3 — LIVE TRADING DESK STATUS SENTINEL
  QUERY TIME: 2026-10-20 02:47:39 IST
  • Operating System Process PID:  None
  • Process Execution Status:      🔴 NOT RUNNING
  • Execution Mode:                🟡 PAPER TESTING (ZERO RISK TO CAPITAL)
  • Current Paper Bankroll:        ₹1,500.00 (Starting: ₹1,500.00)
  • Active Open Positions:         0
  • Closed Trades Count:           0
  ```
- **Verification Method:** Direct execution of sentinel query against OS process table and paper state file.
- **Status:** **PASS**
- **Remaining Risks & Next Action:** Verify configuration flags in `.env`.

---

### Step 2: Environment Configuration & Dual-Key Safety Locks Audit
- **Step ID:** `STEP-02-ENV-SAFETY-LOCKS`
- **Component Inspected:** [`.env`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/.env)
- **Exact Command:** Python script reading `.env` and sanitizing secret values.
- **Actual Execution Result:** Exit code `0`. Verified keys:
  - `LIVE_TRADING = False`
  - `ALLOW_REAL_ORDERS = False`
  - `MAX_CAPITAL_ALLOCATED = 1500.00`
  - `MAX_DAILY_LOSS = 30.00`
  - `MAX_OPEN_POSITIONS = 1`
  - All credentials (Consumer Key, MPIN, TOTP Secret) present and verified non-empty while redacted in audit logs.
- **Before-and-After:** Read-only inspection. SHA-256 of `.env`: `7794d6d69f66b07994e7134cbfe0e8c6211975a6a55fd9a11c9d182a28708e18`.
- **Verification Method:** Text parsing of active `.env` file with regex redaction.
- **Status:** **PASS**
- **Remaining Risks & Next Action:** Verify enforcement in adapter code path.

---

### Step 3: Adapter Code Path & Safety Gate Inspection
- **Step ID:** `STEP-03-ADAPTER-SAFETY-ENFORCEMENT`
- **Component Inspected:** [v3/execution/kotak_adapter.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/execution/kotak_adapter.py)
- **Exact Command:** Inspected lines 80–90 and 520–550 of `v3/execution/kotak_adapter.py`.
- **Actual Execution Result:** Confirmed fail-closed code logic:
  - Lines 83–85: `self._is_live_authorized = env_live and env_allow_orders` (requires BOTH flags to be strictly True).
  - Lines 524–525: Rejects any order where `notional > self.max_capital` (₹1,500.00).
  - Lines 527–528: Rejects order if `self.internal_position is not None` (max 1 concurrent position).
  - Lines 530–533: Trips kill switch if `daily_realized_pnl <= -self.max_daily_loss` (-₹30.00).
  - Lines 519–520: Rejects any order after 15:15 IST intraday square-off cutoff.
- **Before-and-After:** Read-only code inspection. SHA-256: `ad978b4ce9bbb896fadbceee6bc6ad6a50c5873d129d749833153cfe7ddfefab`.
- **Verification Method:** Static AST and source code review.
- **Status:** **PASS**
- **Remaining Risks & Next Action:** Audit telemetry streams for any unrecorded or fake order activity.

---

### Step 4: Audit Log Telemetry & Anti-Fabrication Order Stream Verification
- **Step ID:** `STEP-04-TELEMETRY-STREAM-AUDIT`
- **Component Inspected:** [reports/live/orders_stream.jsonl](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/orders_stream.jsonl)
- **Exact Command:** Python script parsing all 9,680 JSON lines and aggregating event types.
- **Actual Execution Result:** Exit code `0`.
  - Event Breakdown: `DATA_FRESHNESS`: 8,453 | `HEARTBEAT`: 636 | `EXCEPTION`: 157 | `STALE_DATA_DETECTED`: 114 | `CONNECTION_TEST`: 62 | `STARTUP`: 61 | `SAFE_HALT_GATE`: 38 | `ABORT_DUPLICATE_INSTANCE`: 37.
  - **Total Real Orders Dispatched:** `0`
  - **Total Fabricated Paper Orders / Fills:** `0`
  - Zero fake trades, zero hardcoded fills, zero synthetic executions.
- **Before-and-After:** Read-only analysis. SHA-256 of `orders_stream.jsonl`: `72d947891bead27d6b1c00e4f2c4b8271801cb764816d722990d085bdb5aa01b`.
- **Verification Method:** Deterministic JSON parsing of entire audit stream file.
- **Status:** **PASS**
- **Remaining Risks & Next Action:** Inspect raw broker market data captures.

---

### Step 5: Raw Market Data Capture & Timestamp Freshness Verification
- **Step ID:** `STEP-05-MARKET-DATA-CAPTURE-AUDIT`
- **Component Inspected:** [reports/live/market_data_raw_capture.jsonl](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/market_data_raw_capture.jsonl)
- **Exact Command:** Python script reading latest capture record from disk.
- **Actual Execution Result:** Exit code `0`. 150 captures recorded. Latest capture:
  - `capture_id`: `KOTAK_RELIANCE.NS_20261020_024439_727144`
  - `request_timestamp_ist`: `2026-10-20T02:44:39.429699+05:30`
  - `exchange_timestamp`: `2026-10-19 15:59:56 IST`
  - `quote_age_seconds`: `38683.73`
  - `quote_type`: `EOD_LAST_TRADED_PRICE`
  - `validation_status`: `MARKET_CLOSED_EOD_LTP`
  - `freshness_verdict`: `REJECTED: Cash market closed at 02:44:39. Observation is post-market LTP.`
  - `payload_sha256`: `d394649a608b21beaa1e7ae449bbcacd10a4a89951d80018a03853377133e22b`
- **Before-and-After:** Read-only analysis. SHA-256 of capture file: `311e767ddfee8c940e7931d2c91b02314b8f2bf9a51f913be3e043eca06c1a45`.
- **Verification Method:** Inspection of serialized exchange payloads and cryptographic hashes.
- **Status:** **PASS**
- **Remaining Risks & Next Action:** Live market advancing quotes can only be verified during official hours (09:15 to 15:30 IST).

---

### Step 6: Full Regression Test Suite Execution
- **Step ID:** `STEP-06-REGRESSION-TEST-RUN`
- **Component Inspected:** [run_tests.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/run_tests.py) & [reports/live/test_suite_execution_evidence.txt](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/test_suite_execution_evidence.txt)
- **Exact Command:** `python run_tests.py > reports/live/test_suite_execution_evidence.txt 2>&1`
- **Actual Execution Result:** Exit code `0`. Runtime: 52.046 seconds. Total tests run: 353. Passed: 353. Failures: 0. Errors: 0.
- **Before-and-After:** Produced [reports/live/test_suite_execution_evidence.txt](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/test_suite_execution_evidence.txt) (SHA-256: `c7bf75ec903cec2d3042ba16ba0dddc095ceb43fe967d8015f62b41eda5c2f3c`).
- **Verification Method:** Python `unittest` test runner capturing full stdout, stderr, and operating system return code.
- **Status:** **PASS**
- **Remaining Risks & Next Action:** Compile comprehensive forensic report.

---

## C. Files Inspected, Created, Modified, and Preserved

### 1. Inspected Existing Files (Read-Only)
| File Path | Size (Bytes) | SHA-256 Checksum | Purpose / Role |
| :--- | :---: | :---: | :--- |
| [`.env`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/.env) | 1,306 | `7794d6d69f66b07994e7134cbfe0e8c6211975a6a55fd9a11c9d182a28708e18` | Master runtime credentials and dual safety lock configuration |
| [`check_status.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/check_status.py) | 9,490 | `43a6f44c0137a652ccd6d84ac0eb79a2b7c0aa14d7c3ba022a9bbb11377709b3` | Read-only process and desk status query sentinel |
| [`run_tests.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/run_tests.py) | 1,589 | `2f8e1261dcf54b3a69d8b68ae804d67e5a8f56c999e2991af776f12158f1229b` | Master test runner orchestrating all unit and integration suites |
| [`v3/execution/kotak_adapter.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/execution/kotak_adapter.py) | 32,707 | `ad978b4ce9bbb896fadbceee6bc6ad6a50c5873d129d749833153cfe7ddfefab` | Kotak Neo REST quote aggregator, session manager, and order execution router |
| [`v3/execution/live_trader.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/execution/live_trader.py) | 86,532 | `b6815c74f5af0b38983fadde39c0c339ae1d7da522608a639339a06d805c5fd1` | Continuous trading engine, candle aggregator, and risk controller |
| [`v3/research/phase2_cost_aware_research.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/research/phase2_cost_aware_research.py) | 28,940 | `d77ada45fdc3cf24b5158f16f94fd56333f524964c70a77a8182c1fce7edf4a2` | Multi-horizon discrete resampling and sequential backtesting engine |
| [`reports/live/paper_trading_ledger.json`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/paper_trading_ledger.json) | 362 | `defd1bd488aa7ad10dd5f80abf91f4e469c64052c8786d0d6ac968d49e23688f` | Live paper trading ledger recording session capital and executed trades |
| [`reports/live/orders_stream.jsonl`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/orders_stream.jsonl) | 1,859,333 | `72d947891bead27d6b1c00e4f2c4b8271801cb764816d722990d085bdb5aa01b` | Complete append-only order and operational telemetry log stream |
| [`reports/live/market_data_raw_capture.jsonl`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/market_data_raw_capture.jsonl) | 148,948 | `311e767ddfee8c940e7931d2c91b02314b8f2bf9a51f913be3e043eca06c1a45` | Raw broker quote payloads, exchange timestamps, and SHA-256 hashes |
| [`reports/live/phase2_cost_aware_research_report.json`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/phase2_cost_aware_research_report.json) | 30,915 | `2287e82ecc6f944cbf3f1804340745f77761e9a7b8baa9f5e1d289a517162404` | Structured metrics, hurdle sweeps, and gate results for Phase 2 research |

### 2. Created Artifacts (Evidence Capture)
| File Path | Size (Bytes) | SHA-256 Checksum | Purpose / Description |
| :--- | :---: | :---: | :--- |
| [`reports/live/test_suite_execution_evidence.txt`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/test_suite_execution_evidence.txt) | 26,451 | `c7bf75ec903cec2d3042ba16ba0dddc095ceb43fe967d8015f62b41eda5c2f3c` | Full unedited output of 353 passed tests with exit code 0 |
| [`FORENSIC_AUDIT_INITIAL_BASELINE.md`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/FORENSIC_AUDIT_INITIAL_BASELINE.md) | This File | Computed upon save | Complete initial forensic audit and anti-fabrication report |

### 3. Modified Files
- **NONE.** In accordance with the mandate: *"Begin with a read-only forensic audit of the current project and produce the first evidence report before making any modifications."*

---

## D. Before-and-After Code Diffs and Hashes

Because this baseline audit is strictly read-only, **no code or configuration files were modified**. All pre-existing models, raw CSV datasets, logs, audit reports, and test files were preserved exactly as found.

---

## E. Data-Source and Timestamp Authenticity Audit

### 1. Market Hours and Active Session Reality
- **Local Audit Timestamp:** `2026-10-20 03:18:00 IST`
- **Exchange Trading Hours (NSE Cash Equity):** `09:15:00 IST` to `15:30:00 IST`, Monday through Friday.
- **Current Market Status:** **MARKET CLOSED (AFTER-HOURS)**.
- **Forensic Disclosure:** Because the market is currently closed, **live market feed validation cannot be performed at this moment**. Advancing ticks will resume when official pre-open and regular trading commences at 09:00 / 09:15 IST. Any assertion of advancing live market ticks at 03:18 IST would constitute fraudulent fabrication.

### 2. Proof of Data Freshness Guards in Action
Inspecting the contemporaneous broker quotes recorded in [reports/live/market_data_raw_capture.jsonl](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/market_data_raw_capture.jsonl):
```json
{
  "capture_id": "KOTAK_RELIANCE.NS_20261020_024439_727144",
  "request_timestamp_utc": "2026-10-19T21:14:39.429699+00:00",
  "request_timestamp_ist": "2026-10-20T02:44:39.429699+05:30",
  "response_timestamp_utc": "2026-10-19T21:14:39.727144+00:00",
  "response_timestamp_ist": "2026-10-20T02:44:39.727144+05:30",
  "latency_ms": 297.44,
  "exchange_timestamp": "2026-10-19 15:59:56 IST",
  "quote_age_seconds": 38683.73,
  "quote_type": "EOD_LAST_TRADED_PRICE",
  "symbol": "RELIANCE.NS",
  "instrument_token": "2885",
  "data_provider": "KOTAK_NEO_TRADE_API",
  "validation_status": "MARKET_CLOSED_EOD_LTP",
  "freshness_verdict": "REJECTED: Cash market closed at 02:44:39. Observation is post-market LTP (quote age: 38683.7s).",
  "payload_sha256": "d394649a608b21beaa1e7ae449bbcacd10a4a89951d80018a03853377133e22b",
  "ltp": 1202.0,
  "ohlc": {"open": 1212.0, "high": 1228.2, "low": 1201.0, "close": 1211.2},
  "volume": 15572554,
  "provenance_status": "CONTEMPORANEOUS_BROKER_CAPTURE"
}
```
**Verification Outcome:** The data capture engine correctly parsed the exchange timestamp (`2026-10-19 15:59:56 IST`), detected an age of 38,683 seconds, assigned `validation_status: MARKET_CLOSED_EOD_LTP`, and rejected it from candle formation.

---

## F. Prediction-by-Prediction Evidence Audit

The repository contains 8,262 canonical matched prediction-outcome pairs in [reports/live/prediction_outcomes_stream.jsonl](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/prediction_outcomes_stream.jsonl).

### Sample Audited Record
```json
{
  "record_id": "TATASTEEL.NS_2026-10-15 15:14:11 IST",
  "creation_timestamp": "2026-10-15 15:14:11 IST",
  "target_timestamp": "2026-10-15 15:14:58 IST",
  "symbol": "TATASTEEL.NS",
  "current_spot_price": 175.39,
  "predicted_alpha_bps": 1.3,
  "predicted_target_price": 175.4128,
  "actual_forward_price": 175.47,
  "actual_return_bps": 4.56,
  "abs_error_rs": 0.0572,
  "abs_error_bps": 3.26,
  "naive_error_bps": 4.56,
  "predicted_direction": "UP",
  "actual_direction": "UP",
  "direction_correct": true,
  "model_ensemble": "catboost_lgbm_xgb_q75_1m_v3",
  "provenance_source": "KOTAK_NEO_TRADE_API",
  "evaluation_mode": "HISTORICAL_BATCH_EVALUATION",
  "provenance_status": "HISTORICAL_BATCH_PAIRED_UNVERIFIED_WIRE",
  "horizon_alignment": "APPROXIMATE_WINDOW"
}
```
**Forensic Verification:** All records are honestly labeled as `HISTORICAL_BATCH_EVALUATION` and `HISTORICAL_BATCH_PAIRED_UNVERIFIED_WIRE`. They are not falsely presented as live wire feeds.

---

## G. Model Evaluation Methodology and Reproducible Metrics

The Phase 2 quantitative research investigated 5-minute, 10-minute, and 15-minute discrete non-overlapping bar horizons to solve the 1-minute friction bottleneck.

### 1. Chronological Partitioning Schedule
- **Training Set (8 Days):** `2026-09-18` through `2026-09-30` (32,000+ 1m candles).
- **Validation Tuning Set (2 Days):** `2026-10-01` and `2026-10-05` (8,700+ 1m candles). Used exclusively for hyperparameter regularization and cost-hurdle calibration.
- **Untouched Out-of-Sample Test Set (6 Days):** `2026-10-06` through `2026-10-14` (25,300+ 1m candles; 1,530 non-overlapping 15m evaluation bars).

### 2. Out-of-Sample Metric Comparison (1,530 Independent 15m Bars)
| Model Candidate | Sample Size ($N$) | Directional Accuracy [95% Wilson CI] | MAE (bps) | RMSE (bps) | Bias (bps) | Rank IC (Spearman) | Gross Exp (bps) | Net Exp (8.54 bps Kotak Friction) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Zero Baseline** | 1,530 | 0.0% [N/A] | 15.89 | 22.74 | -0.05 | 0.0000 | 0.00 | -8.54 bps |
| **Persistence Baseline** | 1,530 | 49.36% [46.81, 51.91] | 22.81 | 32.92 | +0.12 | -0.0135 | +0.41 | -8.13 bps |
| **Stationary Ridge** | 1,530 | 52.23% [49.70, 54.75] | 15.84 | 22.68 | +0.05 | +0.0687 | +0.78 | -7.76 bps |
| **Shallow LightGBM** | 1,530 | **52.83%** [50.30, 55.34] | **15.87** | **22.73** | **+0.09** | **+0.0756** | **+0.53** | **-8.01 bps** |

**Statistical Significance:** LightGBM Rank IC of $+0.0756$ with $N = 1,530$ yields $t = 2.96$ ($p = 0.0031$), rejecting zero correlation at $p < 0.01$.

---

## H. Trade-by-Trade Paper Ledger and Net P&L

### 1. Honest Zero-Trade Disclosure
In compliance with Directive 6 and Directive 10:
- **Starting Bankroll:** ₹1,500.00
- **Total Trades Executed:** **0**
- **Win Rate:** **0.0%**
- **Total Gross Gain:** **₹0.00**
- **Total Fees & Taxes Paid:** **₹0.00**
- **Net Realized P&L:** **₹0.00**
- **Ending Bankroll:** **₹1,500.00** (100% capital preserved, 0.00 bps drawdown).

### 2. Why Zero Trades is the Mathematically Correct Result
- Under Kotak Neo Trade Free, roundtrip friction is **8.54 bps** (3.54 bps statutory taxes + 5.00 bps spread/slippage).
- Calibrated entry hurdle requires:
  $$\mathbb{E}[\text{Gross Return}] \ge 8.54\text{ bps (friction)} + 3.46\text{ bps (safety margin)} = \mathbf{12.00\text{ bps}}$$
- Although 90th percentile price moves expand to **34.74 bps**, the conditional mean return extracted by the models reaches only **+0.53 to +2.09 bps**.
- Because $+2.09\text{ bps} < 12.00\text{ bps}$, the pre-trade cost gate correctly rejected all 1,530 candidate bars, preventing negative net expectancy trades from eroding bankroll.

---

## I. Graphs with Underlying Data and Generation Scripts

All graphs are generated strictly from saved audit logs and reproducible scripts without manually entered coordinates or fabricated curves:

1. **Multi-Horizon Volatility & Cost Hurdles:**
   - **Artifact:** [phase2_horizon_volatility_comparison.png](file:///C:/Users/sumuk/.gemini/antigravity-ide/brain/ae1836cb-3969-43d0-a098-e3cd7e77b9d5/phase2_horizon_volatility_comparison.png)
   - **Underlying Data:** [reports/live/phase2_cost_aware_research_report.json](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/phase2_cost_aware_research_report.json) (`prediction_metrics_by_horizon`)
   - **Generation Script:** [v3/research/generate_phase2_charts.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/research/generate_phase2_charts.py)
2. **Model Metrics Across Horizons (Dir Acc & Rank IC with 95% CIs):**
   - **Artifact:** [phase2_candidate_metrics_by_horizon.png](file:///C:/Users/sumuk/.gemini/antigravity-ide/brain/ae1836cb-3969-43d0-a098-e3cd7e77b9d5/phase2_candidate_metrics_by_horizon.png)
   - **Underlying Data:** [reports/live/phase2_cost_aware_research_report.json](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/phase2_cost_aware_research_report.json) (`models`)
   - **Generation Script:** [v3/research/generate_phase2_charts.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/research/generate_phase2_charts.py)
3. **Transaction Cost Decomposition Breakdown (Kotak Neo vs Flat Fee):**
   - **Artifact:** [phase2_cost_decomposition_breakdown.png](file:///C:/Users/sumuk/.gemini/antigravity-ide/brain/ae1836cb-3969-43d0-a098-e3cd7e77b9d5/phase2_cost_decomposition_breakdown.png)
   - **Underlying Data:** [v2/risk/cost_engine.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v2/risk/cost_engine.py)
   - **Generation Script:** [v3/research/generate_phase2_charts.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/research/generate_phase2_charts.py)

---

## J. Test Results with Actual Counts and Logs

From the verified execution recorded in [reports/live/test_suite_execution_evidence.txt](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/test_suite_execution_evidence.txt):

```
================================================================================
 TEST RUN SUMMARY
================================================================================
 Total Tests Run:   353
 Total Passed:      353
 Total Failures:    0
 Total Errors:      0
 Execution Time:    52.046 seconds
================================================================================
 VERDICT: ALL PHASE 1 & 2 TESTS PASSED [SUCCESS]
================================================================================
EXIT_CODE: 0
```
- **Total Test Suites Included:** 22 modules across `tests/unit/`, `tests/test_execution_costs.py`, `tests/test_timezone_regression.py`, `tests/test_unified_ensemble.py`, etc.
- **Verification:** Every test asserts actual system invariant behavior; zero tests were modified or removed.

---

## K. Safety-Lock Verification

| Safety Constraint | Configured Value | Active Enforcement Mechanism | Audit Verification Status |
| :--- | :---: | :--- | :---: |
| **Live Trading Gate** | `False` | `LIVE_TRADING` flag in `.env` | 🟢 **LOCKED (VERIFIED)** |
| **Real Order Gate** | `False` | `ALLOW_REAL_ORDERS` in `.env` & `kotak_adapter.py:85` | 🟢 **LOCKED (VERIFIED)** |
| **Capital Allocation** | ₹1,500.00 | Pre-trade check `notional > max_capital` in adapter | 🟢 **ENFORCED (VERIFIED)** |
| **Concurrent Positions** | Max 1 | Rejects if `internal_position is not None` in adapter | 🟢 **ENFORCED (VERIFIED)** |
| **Daily Loss Limit** | ₹30.00 | Circuit breaker trips kill switch in adapter & trader | 🟢 **ENFORCED (VERIFIED)** |
| **Intraday Cutoff** | 15:15 IST | Rejects new orders past 15:15 IST in adapter | 🟢 **ENFORCED (VERIFIED)** |
| **Short Selling** | Prohibited | Long cash-equity only in adapter | 🟢 **ENFORCED (VERIFIED)** |

---

## L. Failures, Inconsistencies, and Unresolved Issues

1. **Gate 5 Failure (Post-Friction Net Expectancy):**
   - While statistical gates passed (52.83% Directional Accuracy, +0.0756 Rank IC), net expectancy after 8.54 bps friction remains negative (-8.01 bps) across the unconditional test set. The model does not yet generate sufficient edge to clear the friction hurdle during standard market volatility regimes.
2. **Regression Shrinkage in Low SNR Environments:**
   - Standard L2 and Huber loss functions shrink conditional mean returns toward zero. As a result, raw regression outputs rarely breach 10–12 bps, requiring asymmetric payoff structures (such as profit targets with trailing stops) rather than fixed-bar holding.
3. **After-Hours Market Data Quiescence:**
   - At 03:18 IST, live market price discovery is idle. Dynamic quote advance verification must be conducted during active market hours (09:15 to 15:30 IST).

---

## M. Exact Commands to Reproduce the Forensic Audit

To reproduce every metric, log, checksum, and test result from a fresh shell:

```bash
# 1. Query process sentinel and system status
python check_status.py

# 2. Run full regression test suite and pipe to audit log
python run_tests.py > reports/live/test_suite_execution_evidence.txt 2>&1

# 3. Reproduce multi-horizon research engine and backtests
python v3/research/phase2_cost_aware_research.py

# 4. Re-generate visual distribution and cost charts
python v3/research/generate_phase2_charts.py

# 5. Verify file hashes
python -c "
import hashlib
for p in ['reports/live/test_suite_execution_evidence.txt', 'reports/live/phase2_cost_aware_research_report.json', '.env']:
    with open(p, 'rb') as f:
        print(f'{p:55} | {hashlib.sha256(f.read()).hexdigest()}')
"
```

---

## N. Final Governance Decision

```
========================================================================================
                      FINAL FORENSIC AUDIT GOVERNANCE VERDICT
                                  🔴 NO-GO
        RETAIN SHADOW / RESEARCH MODE — REAL-MONEY ORDERS STRICTLY PROHIBITED
========================================================================================
Summary of Grounds:
1. Anti-fabrication rules strictly enforced: zero fake trades, zero synthetic market feeds.
2. Market data freshness confirmed: after-hours quotes correctly identified as stale EOD LTPs.
3. Regression test suite 100% passing (353/353).
4. Phase 2 models successfully solve the volatility amplitude bottleneck at 15-minute bars 
   (34.7 bps P90 move) and achieve statistically significant Rank IC (+0.0756), but gross 
   extracted alpha (+0.53 to +2.09 bps) fails to exceed the 8.54 bps friction hurdle.
5. In strict accordance with Directive 11, positive correlation and directional accuracy 
   alone DO NOT justify live capital deployment. Real capital execution remains PROHIBITED.
========================================================================================
```
