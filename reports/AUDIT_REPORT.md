# ALPHANSE V3 — SYSTEM AUDIT REPORT (PHASE 1)

**Audit Date:** Tuesday, October 13, 2026 (Post-Market)  
**Target Market Session:** Wednesday, October 14, 2026  
**Standards Enforced:** Strict Non-Fabrication • Zero Heuristic Fallbacks • Exact Code Traversal

---

## 1. Executive Summary & Flow Audit

We have performed a forensic inspection of the complete AlphaNSE V3 codebase, tracing the real data pipeline from raw exchange observations to persistence:

$$\text{Kotak Neo API / Feed} \longrightarrow \text{Validation} \longrightarrow \text{19/30 Features} \longrightarrow \text{Ridge + Tree Ensemble} \longrightarrow \text{Concurrence} \longrightarrow \text{Risk/Friction} \longrightarrow \text{Ledger/Chart}$$

---

## 2. Confirmed Defects with File Paths and Line Numbers

### Defect 1: Stale Historical Replay Data Conflated with Live Production Outputs
- **File:** [scripts/simulate_paper_session.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/scripts/simulate_paper_session.py#L520-L547)
- **Lines:** 520–547
- **Evidence:** `scripts/simulate_paper_session.py` writes its Friday, October 9 historical replay predictions directly to `reports/live/real_vs_predicted_predictions.jsonl` (2,180 records) and compiles `reports/live/real_vs_predicted_chart.html`.
- **Impact:** The live production engine ([v3/execution/live_trader.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/execution/live_trader.py)) never writes to `real_vs_predicted_predictions.jsonl`. Consequently, any user inspecting the live chart or predictions file observes October 9 historical replay data masquerading as live session outputs.
- **Correction:** Separate historical replay artifacts into `reports/replay/` and update `live_trader.py` to record genuine live predictions to a session-stamped file (`reports/live/live_predictions_YYYYMMDD.jsonl`) and render `real_vs_predicted_chart.html` strictly from today's live observations.

---

### Defect 2: Unsafe Fallback Values Masquerading as Inference (50% Breakout Prob & Confidence)
- **Files & Lines:**
  1. [QA/models/one_min_predictor.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/QA/models/one_min_predictor.py#L435-L448): Lines 435–448
  2. [v3/execution/live_trader.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/execution/live_trader.py#L579-L594): Lines 579–594
- **Evidence in `one_min_predictor.py`:**
  ```python
  if len(latest_candles) < 15:
      return {
          "current_price": last_p,
          "predicted_price_1m": last_p,
          "predicted_return_pct": 0.0,
          "confidence": 50.0,
          "raw_breakout_prob": 50.0,
          "signal": "HOLD"
      }
  ```
- **Evidence in `live_trader.py`:**
  ```python
  default_res = {
      "predicted_return": 0.0,
      "breakout_prob": 0.50,
      "confidence": 50.0,
      "signal": "HOLD"
  }
  if not self.ml_predictor or len(buf) < 20:
      return default_res
  ```
- **Impact:** In `live_trader.py` line 641, the entry filter checks `breakout_prob >= 0.50`. Returning a fallback `breakout_prob = 0.50` means unbuffered or failed inferences falsely satisfy the numerical breakout threshold!
- **Correction:** Remove synthetic 50% fallbacks. On missing data or failed inference, return `prediction_valid: False`, `confidence: 0.0`, `breakout_prob: 0.0`, `error: "INSUFFICIENT_BARS"`. The execution engine must immediately discard any invalid prediction.

---

### Defect 3: Breakout Classifier Zero Precision and Recall
- **File:** [QA/models/saved_models_1m/model_metrics_1m.json](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/QA/models/saved_models_1m/model_metrics_1m.json#L43-L45)
- **Lines:** 43–45
- **Evidence:**
  ```json
  "test_breakout_precision_pct": 0.0,
  "test_breakout_recall_pct": 0.0,
  "test_breakout_f1_pct": 0.0
  ```
- **Impact:** The pre-trained `breakout_classifier_1m.joblib` predicted zero true positives in the test split because the positive breakout target threshold was severely imbalanced without threshold tuning. As a result, calibrated probabilities in production consistently hover at 5%–12% and cannot reach the 50% hurdle.
- **Correction:** Retrain or calibrate the classifier using balanced class weights, a realistic 1-minute return threshold (e.g., 5 bps for scalps), and an optimal decision boundary determined by precision-recall AUC rather than an arbitrary 50% cutoff.

---

### Defect 4: Static TOTP String Blocking Background Broker Token Refresh
- **File:** [v3/execution/kotak_adapter.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/execution/kotak_adapter.py#L120)
- **Lines:** 120–123
- **Evidence:** `totp_val = self.direct_totp if self.direct_totp else (pyotp.TOTP(self.totp_secret).now() if self.totp_secret else None)`.
- **Impact:** When `direct_totp` was populated in `.env`, it took precedence over dynamic TOTP generation. After 30 seconds, `direct_totp` expired, causing background re-authentication calls to fail with connection and timeout errors.
- **Correction:** Prioritize `pyotp.TOTP(self.totp_secret).now()` so every token refresh dynamically generates a fresh, valid TOTP.

---

### Defect 5: Stale Candle Buffer Fallback in Live Feed
- **File:** [v3/execution/live_trader.py](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/execution/live_trader.py#L170-L185)
- **Lines:** 170–185
- **Evidence:** When both Kotak API and Yahoo Finance feeds fail, `FastMarketFeed.fetch_quotes` previously returned the last bar from `fallback_buffers` without flagging it as stale.
- **Impact:** Stale weekend or historical candles were repeatedly re-appended to the live buffer, enabling model predictions on frozen prices.
- **Correction:** Added explicit `is_stale: True` and `source: "BUFFER_FALLBACK"` tags. In `evaluate_and_execute_orders()`, all stale observations are blocked from order generation.

---

## 3. Working Components Supported by Evidence

1. **Kotak Neo Broker Authentication & Live Quotes:**
   - Authenticated session confirmed (`scope: ['Trade']`, UCC: `116K1`).
   - Official NSE tokens correctly mapped (`INFY`: 1594, `RELIANCE`: 2885, `BAJFINANCE`: 317, `AXISBANK`: 5900, `TATASTEEL`: 3499, `NIFTYBEES`: 10576).
   - Live genuine market quotes successfully fetched during trading hours (e.g., `INFY` LTP ₹1,053.05, `RELIANCE` ₹1,158.80).
2. **Native Kotak Neo Derivatives & Option Chain API:**
   - `neo_client.expiries('nse_fo', 'NIFTY')` verified returning genuine exchange expiry dates (`2026-10-19`, `2026-10-27`).
   - `neo_client.option_chain('nse_fo', 'NIFTY', expiry='2026-10-19')` verified returning real-time spot (₹22,721.95), ATM/OTM strikes, market lot (65), LTP, volume, and open interest for CE and PE contracts.
3. **Multi-Model Specialist Invariants:**
   - 6 Specialist Ridge models (`active_model_weights.json`) and 3-Tree ML Ensemble load and compute deterministic inference in < 15ms.
4. **Statutory Cost Engine & Pre-Trade Friction Gate:**
   - Correct official rates verified: SEBI turnover fee at ₹10 per crore (0.0001%), STT 0.025% on sell side, GST 18%, Stamp Duty 0.003%, NSE fee 0.00307%.
   - `EdgeFrictionGate` blocks sub-friction entries.
5. **Singleton Process Sentinel & Risk Limits:**
   - `is_pid_alive` prevents duplicate daemon processes from running concurrently.
   - Starting balance fixed at ₹1,500.00, whole-share integer sizing, single position limit, and 15:15 IST mandatory square-off verified.
6. **Unit Test Suite:**
   - `run_tests.py` passes 232/232 unit tests with exit code 0.

---

## 4. Prioritized List of Required Changes

| Priority | Component | Required Action |
| :---: | :--- | :--- |
| **P0** | **Fail-Closed Inference** | Eliminate 50% fallback values in `one_min_predictor.py` and `live_trader.py`; return explicit `prediction_valid: False`. |
| **P0** | **Live vs Replay Separation** | Isolate historical replay records to `reports/replay/`. Live chart and predictions must render strictly from today's live observations. |
| **P1** | **NSE CE/PE Options Module** | Implement `v3/execution/options_engine.py` connecting to Kotak Neo `option_chain` for ATM/OTM CE/PE contract discovery, risk budgeting, and paper execution. |
| **P1** | **Calibrated Threshold Tuning** | Replace broken 50% breakout hurdle with an empirically calibrated threshold based on true test set distribution. |
| **P2** | **Project File Cleanup** | Safely archive 20+ obsolete, duplicate, and legacy experiment scripts after user approval. |
| **P2** | **Session Readiness Verification** | Run preflight verification for Wednesday, October 14, 2026. |

---

## 5. File Classification (Retain, Correct, Archive, Delete)

- **Retain Unchanged:** `QA/nifty50_constituents.py`, `v2/risk/cost_engine.py`, `v3/execution/base_broker.py`, `v3/execution/edge_friction_gate.py`, `v3/risk/test_integer_sizing.py`, `v3/models/multimodel/active_model_weights.json`.
- **Correct:** `v3/execution/live_trader.py`, `QA/models/one_min_predictor.py`, `v3/execution/kotak_adapter.py`, `scripts/simulate_paper_session.py`, `view_paper_trades.py`.
- **Archive:** Legacy session runner scripts (`scripts/archive/check_live_session13_status.py`, `run_phase3a_forensics.py`, `start_kotak_trading_session.py`).
- **Proposed for Deletion (Awaiting User Approval):** Duplicate historical ledgers, orphan scratch files, redundant one-off screener outputs.
