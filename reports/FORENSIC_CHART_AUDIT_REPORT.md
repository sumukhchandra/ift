# AlphaNSE V3 — Forensic Verification Report: Live Price vs Prediction Graph
**Audit Date:** 2026-10-15T20:36:00+05:30 (IST)  
**Audit Target Files:**
- `reports/live/real_vs_predicted_chart.html` (SHA256: `c9c11928d333286ae708df5d44cb53659dd7e17ec1c633253bdb3ebd96b7e584`)
- `reports/live/real_vs_predicted_chart.png` (SHA256: `4d8c8fd8c2e94a3e26f8f3429f91966eacd7e9fbf6ddd778e232f74e93ba3262`)
- `reports/live/prediction_provenance_stream.jsonl` (SHA256: `bb49c716cd55850f3c2b369dae352be11e9e73e874563c13a07a57b7e7482e4d`)
- `reports/live/runtime_state.json` (SHA256: `0b97d29e66aafe8be9c8c70beb8ade9b321e3ece303394bee29db09e70df3b2f`)

**Operating Mode:** **SHADOW MODE ONLY** (Dual safety air-gap verified: `LIVE_TRADING=False`, `ALLOW_REAL_ORDERS=False`)  
**Operating System Process:** PID `9992` (`python run_live_trader.py`), Cycle #3549+, Status: `STANDBY_FOR_OPEN` (Heartbeat 6.8s ago)  
**Audit Classification & Final Verdict:** **UNVERIFIED PREDICTIVE EDGE / SHADOW MODE ONLY**

---

## 1. Traceability of Plotted Points to Exact Raw Source Records

Every point plotted on the chart originates from the immutable stream file `reports/live/prediction_provenance_stream.jsonl` (8,394 total records, 6,753,442 bytes).

### 1.1 Watchlist Ingestion Mapping
Across the 6 NIFTY 50 watchlist instruments, records are divided exactly as follows:
- **`BAJFINANCE.NS`:** 1,399 records (Primary chart series)
- **`RELIANCE.NS`:** 1,399 records
- **`INFY.NS`:** 1,399 records
- **`AXISBANK.NS`:** 1,399 records
- **`NIFTYBEES.NS`:** 1,399 records
- **`TATASTEEL.NS`:** 1,399 records
- **Total Records:** 8,394 records across 233 active trading minutes.

### 1.2 Data Ingestion Feed Attribution
- **`KOTAK_NEO_TRADE_API`:** 8,346 records (99.43%) — Direct institutional market feed.
- **`YFINANCE_LIVE`:** 48 records (0.57%) — FastMarketFeed parallel fallback during socket reconnects.
- **`BUFFER_FALLBACK`:** 0 records (0.00%) — Zero stale synthetic cache fills.

### 1.3 Exact Source Record Trace Examples (`BAJFINANCE.NS`)
- **First Point of Session (09:15:04 IST):** Line 1 of `prediction_provenance_stream.jsonl`
  ```json
  {"record_id": "BAJFINANCE.NS_2026-10-15 09:15:04 IST", "timestamp": "2026-10-15 09:15:04 IST", "symbol": "BAJFINANCE.NS", "horizon": "1m", "spot_price": 952.3, "data_source": "KOTAK_NEO_TRADE_API", "model_versions": {"specialist_models": "frozen_ridge_v3_session5", "ml_ensemble": "catboost_lgbm_xgb_q75_1m_v3"}, "specialist_alpha_bps": -3.42, "tree_alpha_bps": 15.1, "concurrence_ok": false, "calibrated_confidence": 57.5, "market_regime": "CHOP_REGIME", "signal": "HOLD"}
  ```
- **Midday Break Point (11:51:34 IST):** Line 5,023 of `prediction_provenance_stream.jsonl`
  ```json
  {"record_id": "BAJFINANCE.NS_2026-10-15 11:51:34 IST", "timestamp": "2026-10-15 11:51:34 IST", "symbol": "BAJFINANCE.NS", "horizon": "1m", "spot_price": 963.6, "data_source": "KOTAK_NEO_TRADE_API", "specialist_alpha_bps": -16.48, "tree_alpha_bps": -17.2, "signal": "HOLD"}
  ```
- **Midday Resume Point (13:36:18 IST):** Line 5,029 of `prediction_provenance_stream.jsonl`
  ```json
  {"record_id": "BAJFINANCE.NS_2026-10-15 13:36:18 IST", "timestamp": "2026-10-15 13:36:18 IST", "symbol": "BAJFINANCE.NS", "horizon": "1m", "spot_price": 971.6, "data_source": "KOTAK_NEO_TRADE_API", "specialist_alpha_bps": -6.12, "tree_alpha_bps": -5.7, "signal": "HOLD"}
  ```
- **Last Point of Session (15:14:58 IST):** Line 8,389 of `prediction_provenance_stream.jsonl`
  ```json
  {"record_id": "BAJFINANCE.NS_2026-10-15 15:14:58 IST", "timestamp": "2026-10-15 15:14:58 IST", "symbol": "BAJFINANCE.NS", "horizon": "1m", "spot_price": 967.4, "data_source": "KOTAK_NEO_TRADE_API", "specialist_alpha_bps": 2.14, "tree_alpha_bps": 5.8, "signal": "HOLD"}
  ```

---

## 2. Point-by-Point Forensic Verification

| Verification Field | Verified Value | Evidence / Integrity Status |
| :--- | :--- | :--- |
| **Data Source** | Kotak Neo Trade API (99.43%) / Yahoo Live (0.57%) | Authenticated L1 Feed |
| **Exchange Timestamp** | Monotonic from 09:15:04 to 15:14:58 IST | Verified Monotonic |
| **Symbol Coverage** | `BAJFINANCE.NS`, `RELIANCE.NS`, `INFY.NS`, `AXISBANK.NS`, `NIFTYBEES.NS`, `TATASTEEL.NS` | 6 Valid NIFTY 50 Symbols |
| **Specialist Model Version** | `frozen_ridge_v3_session5` | Frozen Linear Model |
| **Tree Ensemble Version** | `catboost_lgbm_xgb_q75_1m_v3` | GBDT Tri-Model Ensemble |
| **Prediction Timestamp** | Wall-clock IST timestamp at start of inference cycle | Prior to outcome |
| **Target Horizon** | 1-minute forward ($t+1$) | 1m Intraday |
| **Actual Outcome In-Stream** | Initially logged as `null` in streaming append log | Verified by forward matcher |

---

## 3. Investigation of Prior-to-Outcome Provenance & The Tracking Illusion

### 3.1 Provenance Proof: Was the prediction created before the outcome?
**YES.** Predictions were generated in real time inside `live_trader.py` (lines 786–805) immediately after `quotes = self.feed.fetch_quotes()` and logged to `prediction_provenance_stream.jsonl` before subsequent market ticks were observed.
- Zero future-bar leakage was found in the feature extractor (`one_min_predictor.py` uses rolling backward-looking windows of past closes).
- Feature calculations use `.shift(1)` or strictly past bars.

### 3.2 The Root Cause of the Tracking Illusion: Concurrent Close Plotting
Forensic investigation revealed a critical bug in how `v3/reports/chart_generator.py` originally rendered the chart:
- In the original chart generator:
  ```python
  sub_df["actual_price"] = sub_df["spot_price"]
  sub_df["pred_price"] = sub_df["actual_price"] * (1.0 + (sub_df["tree_alpha_bps"] / 10000.0))
  # Both plotted at the SAME timestamp dt:
  ax.plot(sub_df["dt"], sub_df["actual_price"])
  ax.plot(sub_df["dt"], sub_df["pred_price"])
  ```
- **The Defect:** At timestamp $t$, the red curve plotted the spot price $P(t)$, and the blue curve plotted $P(t) \cdot (1 + \hat{\alpha}_t)$ at the **SAME** timestamp $t$.
- Because predicted alpha $\hat{\alpha}_t$ is only a few basis points (-11.6 bps on average), $P(t) \cdot (1 + \hat{\alpha}_t)$ is mathematically within 0.1% of $P(t)$.
- Plotting them at the identical timestamp created the **false optical illusion** that the model was tracking future price movements with near-perfect precision!
- In reality, the blue curve was simply plotting a 0.1% perturbation of the *current input price*, NOT displaying a verified forecast against its actual future target price $P(t+1)$.

---

## 4. Investigation of the Straight Segment and Data Gaps

### 4.1 Did the Straight Line Come from Stale Quotes or Interpolation?
- **Consecutive Identical Quotes:** The maximum run of consecutive identical quotes in `BAJFINANCE.NS` was **6 records** (from 10:58:33 to 10:59:28 IST, lasting 55 seconds). There was **no artificial forward filling or quote replication**.
- **The Midday Gap:** Exactly one large missing data window occurred:
  - **Gap Start:** `2026-10-15 11:51:34 IST` (Spot: ₹963.60)
  - **Gap End:** `2026-10-15 13:36:18 IST` (Spot: ₹971.60)
  - **Duration:** **104.73 minutes** (6,284 seconds)
  - **Missing Records:** Approximately 628 polling cycles were missed during a broker feed disconnect/system sleep.
- **Why the Line Appeared Straight in `real_vs_predicted_chart.html`:**
  - In `chart_generator.py`, Plotly received raw timestamps without explicit `null`/`NaN` entries for the missing 104 minutes.
  - While `connectgaps=False` was set, Plotly's scatter line connecting algorithm only breaks lines when it encounters an explicit `null`/`NaN` value.
  - Because no `null` points existed between `11:51:34` and `13:36:18`, Plotly connected the two coordinates with a **continuous straight line** across the 104-minute void.

---

## 5. Correct One-Step-Ahead Target Alignment

To evaluate the forecast honestly, the prediction $\hat{P}_{T-1 \to T}$ generated at $T-1$ must be plotted at its **target timestamp $T$** against the actual price $P(T)$ realized at timestamp $T$:
$$\hat{P}(T) = P(T-1) \cdot \left(1 + \frac{\hat{\alpha}_{T-1}}{10000}\right)$$
- If the market is missing at $T$ or $T-1$, both lines must contain `NaN`, cleanly breaking the line across the 104-minute gap.
- At 13:36 IST (feed resumption), actual price is ₹971.15, but predicted price is `NaN` because no prediction was generated at 13:35 IST.

---

## 6. Recomputed Prediction Errors from Raw Records

Matching every prediction at $t$ to its actual observed market price 60 seconds forward ($t+60\text{s}$) across all 6 symbols reveals the true empirical accuracy:

```
+===================================================================================================+
| Symbol         | Sample Size | Model MAE (bps) | Naive Baseline (bps) | Directional Accuracy      |
+================+=============+=================+======================+===========================+
| BAJFINANCE.NS  | 1,377       | 14.55 bps       | 6.12 bps             | 47.57% (Sub-50% / No Edge)|
| RELIANCE.NS    | 1,377       | 15.07 bps       | 5.39 bps             | 45.39% (Sub-50% / No Edge)|
| INFY.NS        | 1,377       | 13.48 bps       | 6.17 bps             | 46.77% (Sub-50% / No Edge)|
| AXISBANK.NS    | 1,377       | 13.04 bps       | 5.29 bps             | 46.99% (Sub-50% / No Edge)|
| NIFTYBEES.NS   | 1,377       | 12.74 bps       | 2.44 bps             | 41.47% (Sub-50% / No Edge)|
| TATASTEEL.NS   | 1,377       | 13.68 bps       | 4.98 bps             | 46.33% (Sub-50% / No Edge)|
+===================================================================================================+
| UNIVERSE MEAN  | 8,262       | 13.76 bps       | 5.07 bps             | 45.76% (NO PREDICTIVE EDGE|
+===================================================================================================+
```

### Forensic Findings:
1. **Directional Accuracy is 45.76% (Worse than 50/50 Coin Toss):**
   Across all 6 symbols, the model's directional accuracy ranged from 41.47% to 47.57%.
2. **Model Error is 2.7x Worse than Naive Zero-Return Baseline:**
   Predicting zero price change yields a Mean Absolute Error of **5.07 bps**. The model's predictions yielded an MAE of **13.76 bps** (₹1.40 on `BAJFINANCE.NS`).
3. **The Friction Gate Was 100% Right to Reject Every Trade:**
   With round-trip statutory costs + spread + slippage totaling 14.7 bps, executing trades with 45.7% accuracy would have rapidly destroyed the ₹1,500 bankroll. The engine's 8,394 HOLD decisions saved the capital.

---

## 7. Rebuilt Verified Chart

The chart generator (`v3/reports/chart_generator.py`) was rewritten with forensic precision:
- **Resampling:** Both HTML and PNG resample the raw stream into 1-minute bins with explicit `NaN` preservation for missing periods.
- **Line Disconnection:** Matplotlib and Plotly traces are strictly broken across the 104-minute gap.
- **Hatched Shading:** The missing window (11:51:34 to 13:36:18 IST) is visibly shaded with diagonal hatching and labeled: `Feed Interruption / Missing Data (104.7m)`.
- **Target Alignment:** Blue curve strictly plots $\hat{P}_{T-1 \to T}$ at time $T$.

![AlphaNSE V3 Live Session — Actual (Red) vs Aligned 1-Min Ahead Forecast (Blue)](file:///C:/Users/sumuk/.gemini/antigravity-ide/brain/c633bf16-4bdf-41c8-a21b-85f856277684/real_vs_predicted_chart.png)

---

## 8. Operating System Process Telemetry & Standby Health

A chart existing on disk does not prove the system is active. Live process verification at 20:35 IST confirms:

```
================================================================================
  ALPHANSE V3 — LIVE PROCESS STATUS & HEALTH MONITOR
================================================================================
• Local System Timestamp:       2026-10-15 20:35:48 IST
• Target Session:               Friday, Oct 16, 2026 (09:15:00 IST)
• Operating System Process PID: 9992
• Process Execution Status:     🟢 ACTIVE & RUNNING ON WINDOWS
• Execution Mode:               🟡 PAPER TESTING (ZERO RISK TO CAPITAL)
• Daemon Lifecycle State:       STANDBY_FOR_OPEN
• Broker & Account:             Kotak Neo Trade API Adapter [PAPER / READ-ONLY] (UCC: 116K1)
• Cycle Counter:                Cycle #3549
• Stale Heartbeat Sentinel:     🟢 HEALTHY (6.8s ago)
• Current Paper Bankroll:       ₹1,500.00 (Starting: ₹1,500.00)
• Total Money In / Out:         ₹0.00 / ₹0.00
• Realized P&L:                 ₹0.00
• Active Open Positions:        0
• Closed Trades Count:          0
================================================================================
```

---

## 9. Final Decision & Classification

```
+===================================================================================================+
|                                    FINAL FORENSIC VERDICT                                         |
+===================================================================================================+
|                                                                                                   |
|              >>>  CHART CLASSIFICATION: UNVERIFIED PREDICTIVE EDGE  <<<                           |
|              >>>  OPERATIONAL DIRECTIVE: SHADOW MODE ONLY           <<<                           |
|                                                                                                   |
|   1. Ingestion Data Authenticity:             VERIFIED (Kotak Neo Trade API)                      |
|   2. Absence of Lookahead / Target Leakage:   VERIFIED (Past bars only)                           |
|   3. Accounting & Non-Negative Cash Limits:   VERIFIED (Rs. 1,500 locked, Rs. 0 discrepancy)      |
|   4. Statistical Predictive Edge:             FAILED / UNVERIFIED (45.76% Directional Accuracy)  |
|   5. Realized MAE vs Naive Baseline:          FAILED (13.76 bps vs 5.07 bps naive)               |
|                                                                                                   |
|   STANDING DIRECTIVE FOR FRIDAY, OCTOBER 16, 2026:                                                |
|   • The live daemon (PID 9992) remains in STANDBY_FOR_OPEN until 09:15:00 IST.                    |
|   • All live order fills remain STRICTLY BLOCKED.                                                 |
|   • The system will continue in SHADOW MODE to record genuine market prices and predictions       |
|     without placing paper capital at risk.                                                        |
|                                                                                                   |
+===================================================================================================+
```
