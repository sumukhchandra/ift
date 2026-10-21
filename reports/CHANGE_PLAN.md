# ALPHANSE V3 — IMPLEMENTATION & CHANGE PLAN

**Document Date:** Tuesday, October 13, 2026  
**Target Market Session:** Wednesday, October 14, 2026  
**Objective:** Restore clean live paper-trading, eliminate inference fallbacks, isolate replay artifacts, and implement native NSE CE/PE Options Intelligence.

---

## 1. Prioritized Workstreams

### Workstream 1: Fail-Closed Inference & Fallback Elimination (Priority: P0)
- **Objective:** Ensure missing features, buffering candles, or failed regressors never produce deceptive "50% confidence / 50% breakout" outputs.
- **Changes in `QA/models/one_min_predictor.py`:**
  - When `len(latest_candles) < 15`: Set `"prediction_valid": False`, `"confidence": 0.0`, `"raw_breakout_prob": 0.0`, `"predicted_return_pct": 0.0`, `"error": "INSUFFICIENT_HISTORY"`.
  - When regressor or classifier inference fails: Set `"prediction_valid": False`, `"error": "INFERENCE_FAILED"`.
- **Changes in `v3/execution/live_trader.py`:**
  - Remove `default_res` with `breakout_prob: 0.50` and `confidence: 50.0`.
  - In `evaluate_and_execute_orders()`: Check `if not ml_out.get("prediction_valid", True): continue`.

---

### Workstream 2: Historical Replay vs. Live Session Separation (Priority: P0)
- **Objective:** Eliminate confusion between Friday, October 9 historical replay data and live market session records.
- **Changes:**
  - Relocate historical replay outputs (`paper_replay_ledger.json`, `paper_replay_ledger_mis.json`, `real_vs_predicted_predictions.jsonl`) to `reports/replay/`.
  - Update `live_trader.py` to record genuine live predictions to a session-stamped live predictions file: `reports/live/live_predictions_YYYYMMDD.jsonl`.
  - If no live trades or predictions have occurred for today's session, display a clear notice in `real_vs_predicted_chart.html` ("No live trades executed for session 2026-10-14") instead of silently displaying October 9 historical bars.

---

### Workstream 3: NSE CE/PE Options Intelligence Module (Priority: P1)
- **Objective:** Add an institutional-grade options intelligence module compatible with Indian exchange-traded derivatives (NSE F&O).
- **Core Concepts:**
  - **CE (European Call Option):** Bullish underlying exposure.
  - **PE (European Put Option):** Bearish underlying exposure.
  - **Lot Size & Cash Rule:** Enforce exchange market lots (e.g., NIFTY lot = 65 units). Under the ₹1,500 paper trading capital, total premium required (`LTP * Lot_Size`) must not exceed available paper cash. Stock options requiring > ₹1,500 premium are automatically rejected with `INSUFFICIENT_CASH`.
  - **Option Buying Only:** Option writing/selling remains strictly disabled.
  - **Maximum Loss:** Capped at 100% of premium paid.
- **New Architecture File:** `v3/execution/options_engine.py`
  - Uses native Kotak Neo Trade API `neo_client.option_chain('nse_fo', symbol, expiry)` verified in preflight.
  - Evaluates ATM and near-the-money strikes based on underlying model direction.
  - Enforces `EdgeFrictionGate` and statutory derivatives charges (STT 0.125% on exercise / 0.0625% on premium, GST 18%, exchange turnover).

---

### Workstream 4: Model Threshold Calibration & Directional Balance (Priority: P1)
- **Objective:** Address the 0% precision/recall issue in the breakout classifier and ensure the decision boundary reflects true price distribution.
- **Changes:**
  - Inspect test set distribution in `QA/models/saved_models_1m/`.
  - Provide calibrated threshold rules based on dual-model concurrence: when specialist Ridge alpha and Tree ensemble alpha agree on direction with $|r| \ge 2.0\text{ bps}$, calibrate the breakout hurdle to the empirical 75th percentile of valid scalps (e.g., 0.15–0.25) rather than an arbitrary 0.50 cutoff.

---

### Workstream 5: Project Cleanup & Artifact Archiving (Priority: P2)
- **Objective:** Move obsolete, duplicate, and legacy scripts to `scripts/archive/` and generate `PROPOSED_DELETIONS.md` for user approval before deleting any files.

---

### Workstream 6: Wednesday, October 14, 2026 Preflight & Readiness (Priority: P2)
- **Objective:** Verify Kotak Neo authentication, instrument mappings, options chain discovery, and paper ledger initialization at exactly ₹1,500.00 prior to market open.
