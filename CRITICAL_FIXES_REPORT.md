# ALPHANSE V3 — CRITICAL ARCHITECTURAL FIXES REPORT

**Execution Timestamp:** Saturday, 17 October 2026, 16:05 IST  
**Target Market Session:** Monday, 19 October 2026 (09:15 – 15:30 IST)  
**Workspace:** `c:\Users\sumuk\.gemini\antigravity-ide\scratch\ift`  
**Operational Status:** **READY FOR SHADOW MODE** (Real-Money Execution Strictly Blocked)  

---

## Executive Summary

Pursuant to the mission directive for **AlphaNSE V3**, the two critical architectural defects identified in previous forensic audits have been resolved, integrated into the real runtime path, and proven via automated regression suites:

1. **Fix 1 (Timezone Consistency):** Standardized all timestamp parsing, normalization, feature extraction, and training pipelines to canonical **Indian Standard Time (`Asia/Kolkata` / UTC+05:30)**. Resolved the tree branch collapse defect where timestamps were previously converted to UTC wall clock via `.dt.tz_convert(None)` before training, distorting time-of-day features across 90% of the trading day.
2. **Fix 2 (Specialist-Model Output Handling):** Completely decoupled the specialist model from placeholder defaults, implemented true 19-indicator technical feature extraction directly from candle buffers, and introduced strict schema validation (`validate_specialist_output` and `_predict_specialist_linear`) enforcing scalar types, 19-dimensional shapes, required metadata fields, and finite values. Invalid or missing outputs fail closed with explicit rejection reasons and strictly prevent fabricated scores or confidences.
3. **Automated Verification:** All 316 pre-existing tests plus 14 newly authored regression tests pass (**330 / 330 passing, 0 failures, 0 errors**).
4. **Model Reproducibility:** Historical baseline evaluation on canonical October 15 records ($N = 8,262$) was reproduced with exact numerical precision. Candidate retraining models were evaluated against predefined acceptance criteria and rejected for real-money trading.

---

## 1. Task 1: Timezone Consistency Fix

### 1.1 Root Cause Forensic Analysis
- **Problem Statement:** During model training and feature extraction, timestamps were treated inconsistently between training data preprocessing and live shadow inference.
- **Defective Code (`QA/scripts/build_and_train_live_1m.py` lines 91–95):**
  ```python
  def normalize_tz(df):
      if "timestamp" in df.columns and hasattr(df["timestamp"].dt, "tz"):
          if df["timestamp"].dt.tz is not None:
              df["timestamp"] = df["timestamp"].dt.tz_convert(None)
      return df
  ```
- **Failure Mechanism:**
  1. In pandas, calling `.dt.tz_convert(None)` on a timezone-aware Series with `tz='Asia/Kolkata'` (`+05:30`) converts the timestamp to UTC wall clock **before** stripping timezone awareness.
  2. For example, Indian market open (`2026-10-15 09:15:00+05:30`) was converted to `2026-10-15 03:45:00` (naive UTC).
  3. In `QA/models/one_min_predictor.py` (`extract_features_1m`), time-of-day features were computed as:
     ```python
     minutes_from_open = (ts.dt.hour * 60 + ts.dt.minute) - (9 * 60 + 15)
     minutes_from_open = minutes_from_open.clip(0, 375)
     ```
  4. During training, `ts.dt.hour` was UTC (hours 3 through 9). Thus `(3 * 60 + 45) - 555 = -330`.
  5. The `.clip(0, 375)` clipped negative values to **0.0 for ~90% of the entire trading day** (from 09:15 to 14:45 IST).
  6. The decision trees were trained almost exclusively on `time_sin = 0.0` and `time_cos = 1.0`.
  7. During live shadow execution, timestamps were generated in IST (hours 9 through 15), causing `time_sin` and `time_cos` to cycle smoothly between -1.0 and +1.0. Encountering these unseen feature values during live inference traversed uncalibrated decision paths, inducing a systematic **-4.28 bps negative bias** across the ensemble.

### 1.2 Architectural Resolution
- **Canonical Timezone Standard:** All timestamps across data ingestion, training pipelines, feature extraction, and live trading are standardized to **`Asia/Kolkata` (Indian Standard Time, UTC+05:30)**.
- **Daylight Independence:** India does not observe Daylight Saving Time (DST). `Asia/Kolkata` is permanently fixed at UTC+05:30 (19,800 seconds offset) year-round.

#### Exact Code Changes:
1. **[`QA/scripts/build_and_train_live_1m.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/QA/scripts/build_and_train_live_1m.py):**
   ```python
   # 3. Normalize timestamps to canonical Asia/Kolkata (Indian Standard Time) convention
   def normalize_tz(df):
       if "timestamp" in df.columns:
           ts = pd.to_datetime(df["timestamp"])
           if hasattr(ts.dt, "tz"):
               if ts.dt.tz is None:
                   # Naive timestamps represent Indian market hours (09:15-15:30 IST)
                   df["timestamp"] = ts.dt.tz_localize("Asia/Kolkata")
               else:
                   df["timestamp"] = ts.dt.tz_convert("Asia/Kolkata")
       return df
   ```
2. **[`QA/models/one_min_predictor.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/QA/models/one_min_predictor.py):**
   ```python
   # 13. Time-of-Day (sin/cos encoding of minute within trading session in canonical Asia/Kolkata)
   if "timestamp" in df.columns:
       ts = pd.to_datetime(df["timestamp"])
       if hasattr(ts.dt, "tz"):
           if ts.dt.tz is None:
               # Naive timestamps represent Indian market hours (09:15-15:30 IST)
               ts = ts.dt.tz_localize("Asia/Kolkata")
           else:
               # Timezone-aware timestamps (UTC, IST, or other) converted to canonical Asia/Kolkata
               ts = ts.dt.tz_convert("Asia/Kolkata")
       minutes_from_open = (ts.dt.hour * 60 + ts.dt.minute) - (9 * 60 + 15)  # Minutes since 9:15 AM IST
       minutes_from_open = minutes_from_open.clip(0, 375).fillna(0)  # 375 = 6h15m trading session
       df["time_sin"] = np.sin(2 * np.pi * minutes_from_open / 375).fillna(0)
       df["time_cos"] = np.cos(2 * np.pi * minutes_from_open / 375).fillna(0)
       # Session phase: 0=open rush (0-30min), 1=morning (30-120), 2=midday (120-240), 3=close rush (240-375)
       df["session_phase"] = np.where(minutes_from_open <= 30, 0,
                             np.where(minutes_from_open <= 120, 1,
                             np.where(minutes_from_open <= 240, 2, 3))).astype(float)
   ```

### 1.3 Dataset Integrity & Regression Evidence
- **Dataset Preservation:** Canonical raw files on disk (`QA/data/genuine_forward_oos_oct13_oct14.csv`, `*_1m_weekend.csv`) retain their authentic timestamps and have **not** been shifted or relabeled.
- **Regression Suite:** Added [`tests/test_timezone_regression.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/tests/test_timezone_regression.py) testing:
  - `test_01_ist_aware_and_naive_timestamps`: Aware and naive IST timestamps yield identical time-of-day features.
  - `test_02_utc_timestamps_convert_identically_to_ist`: Aware UTC timestamps (e.g. 03:45 UTC) convert to IST (09:15 IST) without shift.
  - `test_03_daylight_independent_conversion`: Invariant UTC+05:30 conversion across summer and winter dates.
  - `test_04_session_boundaries_and_phases`: Pre-market (08:45–09:14), open (09:15), open rush (0–30m), morning (30–120m), midday (120–240m), close rush (240–375m), close (15:30), and post-market (15:31+).
  - `test_05_existing_datasets_not_silently_shifted`: Ingests untouched on-disk CSV records and confirms 09:15 IST alignment.
- **Status:** **VERIFIED & PASSING (5 / 5 tests passed in 1.48s)**.

---

## 2. Task 2: Specialist-Model Output Handling Fix

### 2.1 Root Cause Forensic Analysis
- **Problem Statement:** In `v3/intelligence/opportunity_engine.py`, the specialist linear model evaluation suffered from two major defects:
  1. **Feature Decoupling:** Instead of passing real market features, lines 468–479 hardcoded static constants (`bb_bw=0.005`, `bb_pct_b=0.5`, `atr14=0.002`, `park_vol=0.002`, `orderflow=0.0`, `upper_w=0.1`, `lower_w=0.1`, `vol_surge=1.0`), and inserted `orderflow` into position 12, shifting subsequent features out of alignment with the trained model weights.
  2. **Implicit Defaults & Schema Vulnerability:** `_predict_specialist_linear` returned a bare `float(0.0)` when model weights were missing or unconfigured. In `scan_and_rank_opportunities`, a `0.0` output failed concurrence (`is_bull = specialist_alpha > 0 ...`) and logged `"MODELS_DISAGREE"`, silently masking missing or corrupt model artifacts. Furthermore, no validation existed for output types (e.g. booleans, strings), array shapes, required dict keys, or non-finite numbers (`NaN`, `Inf`).

### 2.2 Architectural Resolution
- **19-Feature Mathematical Extraction:** Added `OpportunityDiscoveryEngine.extract_19_features(buf)` to calculate all 19 institutional features (`r1, r3, r5, r10, accel1, rsi7/100, rsi14/100, vwap_dist, bb_pct_b, bb_bandwidth, micro_atr14, parkinson_vol, wick_pressure, upper_wick, lower_wick, vol_surge, r1*vol_surge, vwap_dist*rsi14/100, accel1*bb_bandwidth`) directly from candle buffers, perfectly matching the live trading adapter.
- **Specialist Output Schema Validation:** Added `OpportunityDiscoveryEngine.validate_specialist_output(raw_output)` to enforce:
  1. **Type Validation:** Accepts numeric floats, ints, 1D size-1 arrays, or dicts containing `'predicted_alpha'` / `'alpha'`. Explicitly rejects booleans, strings, and non-numeric types.
  2. **Shape Validation:** Rejects multi-element or multi-dimensional arrays with explicit shape mismatch errors.
  3. **Finite Value Validation:** Strictly checks `math.isfinite(val)`. Rejects `NaN`, `+Inf`, and `-Inf`.
  4. **Required Fields:** Rejects dicts lacking required alpha fields.
- **Fail-Closed Gate:** In `scan_and_rank_opportunities`:
  - When the specialist model fails or produces invalid output:
    - `spec_valid = False`
    - Explicit rejection reason added to `rejection_reasons` (e.g. `INVALID_SPECIALIST_OUTPUT: Specialist prediction is None (missing model output)`).
    - `concurrence = False`
    - `viable = False`
    - `score = 0.0`
    - `gross_gain_rs = 0.0`, `net_expectancy_rs = 0.0`, `net_expectancy_bps = -9999.0`
    - `side = "HOLD"`, `direction = "FLAT"`
    - **Never replaces missing model output with a fabricated score or confidence.**

#### Exact Code Changes in [`v3/intelligence/opportunity_engine.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/intelligence/opportunity_engine.py):
1. **Feature Extractor:**
   ```python
   @staticmethod
   def extract_19_features(buf: List[Dict[str, Any]]) -> Optional[List[float]]:
       if not buf or len(buf) < 15:
           return None
       # Mathematical calculation of 19 institutional features
       ...
       return feats
   ```
2. **Output Validator:**
   ```python
   @staticmethod
   def validate_specialist_output(raw_output: Any) -> Tuple[bool, Optional[float], Optional[str]]:
       if raw_output is None:
           return False, None, "INVALID_SPECIALIST_OUTPUT: Specialist prediction is None (missing model output)"
       if isinstance(raw_output, bool):
           return False, None, "INVALID_SPECIALIST_OUTPUT: Unsupported output type bool, expected numeric float or dict"
       ...
       float_val = float(val)
       if math.isnan(float_val) or math.isinf(float_val):
           return False, None, "INVALID_SPECIALIST_OUTPUT: Non-finite numeric value (NaN/Inf) in specialist prediction"
       return True, float_val, None
   ```
3. **Linear Predictor with Metadata & Input Validation:**
   ```python
   def _predict_specialist_linear(self, symbol: str, features_19: Optional[List[float]]) -> Optional[float]:
       if not self.specialist_weights or not isinstance(self.specialist_weights, dict):
           return None
       if features_19 is None or len(features_19) != 19:
           return None
       # Validates assigned model exists and contains ["weights", "bias", "means", "stds"] of length 19
       # Validates all arrays are finite; returns None on failure
       ...
       return float(np.dot(w_arr, norm_x) + b_val)
   ```
4. **Opportunity Scoring Integration:**
   ```python
   feats_19 = self.extract_19_features(buf)
   if feats_19 is None:
       raw_spec = None
       spec_valid = False
       specialist_alpha = 0.0
       spec_rejection = "INSUFFICIENT_HISTORY: Buffer too short or prices invalid for specialist features (< 15 bars)"
   else:
       raw_spec = self._predict_specialist_linear(sym, feats_19)
       spec_valid, validated_alpha, spec_rejection = self.validate_specialist_output(raw_spec)
       specialist_alpha = validated_alpha if spec_valid else 0.0

   if not spec_valid:
       rejections.append(spec_rejection)
   ...
   if qty < 1 or not spec_valid:
       score = 0.0
       viable = False
   ```

### 2.3 Regression Evidence
- **Regression Suite:** Added [`tests/test_specialist_output_regression.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/tests/test_specialist_output_regression.py) testing:
  - `test_01_valid_float_output`: Valid float parsed, concurrence verified, viable trade formed.
  - `test_02_valid_dict_output_with_required_fields`: Dict with `'predicted_alpha'` / `'alpha'` parsed.
  - `test_03_valid_1d_size_1_array_output`: 1D array unpacked to scalar float.
  - `test_04_missing_specialist_output_fails_safely_no_fabricated_scores`: `None` output fails closed with explicit rejection, score=0.0.
  - `test_05_malformed_dict_missing_required_fields`: Dict missing alpha rejected.
  - `test_06_malformed_shape_rejected`: Multi-element array rejected for shape mismatch.
  - `test_07_malformed_type_rejected`: String, boolean, and arbitrary object rejected.
  - `test_08_non_finite_outputs_nan_and_inf_rejected`: `NaN`, `+Inf`, `-Inf` rejected, score=0.0.
  - `test_09_specialist_weights_validation_and_fail_closed`: Missing/corrupt model metadata returns `None`.
- **Status:** **VERIFIED & PASSING (9 / 9 tests passed in 2.03s)**.

---

## 3. Full Test Suite & Diff Verification

### 3.1 Test Suite Verification
- **Command:** `python run_tests.py`
- **Total Tests Run:** **330 tests**
- **Passed:** **330 (100%)**
- **Failures / Errors:** **0**
- **Execution Time:** **68.19 seconds**

### 3.2 Exact Files Changed

| File Path | Nature of Change | Core Purpose |
| :--- | :--- | :--- |
| [`QA/scripts/build_and_train_live_1m.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/QA/scripts/build_and_train_live_1m.py) | Modified | Replaced `.dt.tz_convert(None)` with canonical `Asia/Kolkata` normalization |
| [`QA/models/one_min_predictor.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/QA/models/one_min_predictor.py) | Modified | Localizes naive timestamps and converts aware timestamps to `Asia/Kolkata` before computing session minute |
| [`v3/intelligence/opportunity_engine.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/intelligence/opportunity_engine.py) | Modified | Added 19-feature extractor, specialist output validator, metadata check, and fail-closed scoring |
| [`tests/test_timezone_regression.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/tests/test_timezone_regression.py) | Created | Regression suite for Task 1 (5 tests) |
| [`tests/test_specialist_output_regression.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/tests/test_specialist_output_regression.py) | Created | Regression suite for Task 2 (9 tests) |

---

## 4. Model Evaluation & Baseline Comparison

Using untouched canonical records ($N = 8,262$ matched forward observations from October 15), benchmarks and candidate models were recomputed via [`v3/research/controlled_model_research.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/research/controlled_model_research.py):

| Model / Baseline | MAE (bps) | RMSE (bps) | Directional Acc (%) | IC ($r$) | Bias (bps) | P90 Error (bps) | Net Edge (Post 14.7 bps Friction) | Promotion Verdict |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Zero-Return Baseline ($\hat{y}=0$)** | **5.06** | **7.79** | 0.00% | 0.0000 | -0.25 | 11.50 | 0.00 bps | Benchmark |
| **Persistence Baseline ($\hat{y}_t=y_{t-1}$)** | 5.72 | 8.57 | 47.80% | +0.0107 | -0.17 | 12.57 | -14.77 bps | Benchmark |
| **Mean-Reversion Baseline ($\hat{y}_t=-y_{t-1}$)** | 5.58 | 8.65 | 52.20% | -0.0107 | -0.33 | 12.68 | -14.63 bps | Benchmark |
| **Current Model Ensemble** | 13.76 | 17.61 | 49.21% | -0.0238 | -11.44 | 28.20 | -14.92 bps | Retained (Shadow) |
| **Candidate A (Ridge L2)** | 5.43 | 8.06 | 49.08% | +0.0203 | +1.08 | 11.84 | -14.67 bps | **REJECTED** |
| **Candidate B (LightGBM MAE)** | 5.12 | 7.81 | 49.92% | -0.0052 | +0.38 | 11.51 | -14.59 bps | **REJECTED** |

### Acceptance Criteria Gate Evaluation:
- **Directional Accuracy $\ge 52.0\%$:** Failed (Candidate A: 49.08%, Candidate B: 49.92%)
- **MAE $<$ Zero-Return Baseline (5.06 bps):** Failed (Candidate A: 5.43 bps, Candidate B: 5.12 bps)
- **Information Coefficient $r \ge +0.0300$:** Failed (Candidate A: +0.0203, Candidate B: -0.0052)
- **Post-Friction Net Edge $> 0.0$ bps:** Failed (Candidate A: -14.67 bps, Candidate B: -14.59 bps)
- **Decision:** **CANDIDATES REJECTED**. Neither candidate cleared the acceptance gates. Current model retained strictly in shadow mode.

---

## 5. Monday Pre-Flight Operational Verification

1. **Market Calendar:** The NSE exchange is closed for the weekend (Oct 17–18). Trading resumes on **Monday, 19 October 2026** at 09:15 IST.
2. **Pre-Market Window:** 08:45 – 09:00 IST on Monday morning.
3. **Data Feed & Broker Connectivity:**
   - Pre-flight test (`python run_live_trader.py --test-conn`): **AUTHENTICATED (Kotak Neo Trade API, UCC: 116K1)**.
   - All 6 universe symbols (`NIFTYBEES.NS`, `INFY.NS`, `TATASTEEL.NS`, `BAJFINANCE.NS`, `AXISBANK.NS`, `RELIANCE.NS`) successfully retrieved quotes and 60-bar historical warm-up candle buffers.
4. **Process State & Duplicate Prevention:**
   - OS Process Table: Verified **no live trader daemon is currently running**.
   - State File (`reports/live/runtime_state.json`): Clean `STANDBY_FOR_OPEN`.
   - Single-instance mutex: Confirmed that starting a second instance aborts immediately with `ABORT_DUPLICATE_INSTANCE`.
5. **Air-Gap Security:**
   - `.env`: `LIVE_TRADING=False`, `ALLOW_REAL_ORDERS=False`.
   - Capital: ₹1,500.00 simulated paper bankroll, cash-only equity mode, maximum 1 open position, ₹30.00 daily loss stop.
   - Order Dispatch Gate: Zero real orders submitted; broker order placement locked.

---

## 6. Final Operational Readiness Verdict

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                     CRITICAL FIXES & READINESS VERDICT                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║   1. TIMEZONE CONSISTENCY:         🟢 VERIFIED FIXED & REGRESSION TESTED    ║
║   2. SPECIALIST OUTPUT HANDLING:   🟢 VERIFIED FIXED & REGRESSION TESTED    ║
║   3. FULL TEST SUITE (330 TESTS):  🟢 100% PASSING (0 FAILURES, 0 ERRORS)   ║
║   4. DATA PROVENANCE & ISOLATION:  🟢 VERIFIED AIR-GAPPED                   ║
║   5. REAL-MONEY EXECUTION:         🔴 STRICTLY BLOCKED (SUB-50% DIR ACC)    ║
║   6. SHADOW MODE EXECUTION:        🟢 100% READY FOR MONDAY OCT 19          ║
║                                                                              ║
║   OVERALL OPERATIONAL STATUS:      READY FOR SHADOW MODE                     ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```
