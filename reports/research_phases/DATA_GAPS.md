# AlphaNSE V2 — Data Gap Analysis & Historical Feasibility Audit

**Document Status**: Phase 0 Baseline Audit  
**Classification**: **`DATA_BLOCKED`** (For Model Certification, Edge Validation, and Autonomous Routing)  
**Engineering Status**: **`SUFFICIENT_FOR_CONTINUATION`** (For Pipeline, Streaming, Feature, and Replay Infrastructure)  
**Evaluation Date**: September 19, 2026  
**Auditor**: Senior Quantitative Software Architect  

---

## 1. Available Datasets Inventory

An exhaustive forensic scan of the entire repository filesystem was conducted to identify every stored tabular dataset, tick log, and feature matrix. The table below represents the actual physical datasets present on disk:

| Dataset Path | Format | File Size | Symbols Covered | First Timestamp (IST) | Last Timestamp (IST) | Sessions | Row Count | Missing Intervals | Notes |
| :--- | :--- | ---: | :--- | :--- | :--- | ---: | ---: | :--- | :--- |
| `QA/data/friday_session_features.csv` | CSV | 179,100 B | 10 NSE Equities | 2026-09-18 13:06:14 | 2026-09-18 15:44:03 | 1 (Partial) | 1,090 | 09:15–13:05 not present | Harvested features from Friday afternoon |
| `QA/logs/dataset_friday_session_1m.jsonl` | JSONL | 562,516 B | 10 NSE Equities | 2026-09-18 13:06:14 | 2026-09-18 15:44:03 | 1 (Partial) | 1,090 | 09:15–13:05 not present | Raw 1-min predictions and harvest ticks |
| `QA/logs/closing_sentinel_ticks.jsonl` | JSONL | 168,443 B | 10 NSE Equities | 2026-09-18 15:00:02 | 2026-09-18 15:30:15 | 1 (Closing) | 31 | Only covers EOD window | Harvested closing ticks by sentinel |
| `QA/logs/compounding_trades.jsonl` | JSONL | 1,595 B | `TATACAP.NS` | 2026-09-18 09:31:23 | 2026-09-18 12:22:33 | 1 | 4 rows | Only 2 trades recorded | 2 BUYs, 2 SELLs on Tata Capital |
| `QA/models/saved_models/feature_importances.csv` | CSV | 595 B | N/A | N/A | N/A | N/A | 24 | N/A | Static XGBoost feature importance list |
| `QA/data/processed/master_labeled_dataset.parquet` | Parquet | 0 B | **NONE** | **NOT PRESENT** | **NOT PRESENT** | 0 | 0 | **ENTIRE DATASET MISSING** | Referenced in code, does not exist on disk |
| `QA/data/processed/labeled_data.parquet` | Parquet | 0 B | **NONE** | **NOT PRESENT** | **NOT PRESENT** | 0 | 0 | **ENTIRE DATASET MISSING** | Referenced in backtests, does not exist on disk |

---

## 2. Actual Historical Coverage

* **Historical Span on Disk**: Only **2 hours and 38 minutes** of 1-minute data exist physically on disk (from Friday, September 18, 2026, 13:06 to 15:44 IST).
* **Number of Trading Sessions**: Exactly **one single partial session**.
* **Number of Symbols**: 10 symbols (`RELIANCE.NS`, `HDFCBANK.NS`, `BHARTIARTL.NS`, `ICICIBANK.NS`, `TATACAP.NS`, `INFY.NS`, `TCS.NS`, `SBIN.NS`, `AXISBANK.NS`, `BAJFINANCE.NS`).
* **Market Regimes Represented**: **Only ONE regime** is represented on disk: a low-volatility Friday afternoon consolidation/sideways drift. There are zero bull trend days, zero bear trend days, zero high-volatility event days (e.g., RBI rate decisions, Union Budget, earnings shocks) stored in the repository.
* **Walk-Forward Validation Feasibility**: **COMPLETELY IMPOSSIBLE on existing on-disk data**. A multi-month walk-forward cross-validation analysis requires at least 6–12 months of contiguous intraday data (approximately 120–250 trading sessions). Attempting walk-forward validation on 1,090 rows across 10 stocks would result in catastrophic overfitting and zero statistical confidence.

---

## 3. Symbol Coverage & Granularity

The 10 equities tracked in the codebase are large-cap, high-liquidity symbols belonging to the Nifty 50 or broad market indices:
1. `RELIANCE.NS` (Energy / Telecom / Retail)
2. `HDFCBANK.NS` (Private Banking)
3. `BHARTIARTL.NS` (Telecom)
4. `ICICIBANK.NS` (Private Banking)
5. `TATACAP.NS` (Financial Services / NBFC)
6. `INFY.NS` (Information Technology)
7. `TCS.NS` (Information Technology)
8. `SBIN.NS` (Public Sector Banking)
9. `AXISBANK.NS` (Private Banking)
10. `BAJFINANCE.NS` (Non-Banking Financial)

**Coverage Limitation**:
While these 10 symbols represent high market liquidity, they are heavily skewed toward Financial Services (5 out of 10 stocks). More importantly, there is no mid-cap or high-beta universe representation that might offer the volatility required to overcome transaction costs on 1-minute or 5-minute timeframes.

---

## 4. Session Coverage & Completeness

* **Active Trading Hours on NSE**: 09:15 to 15:30 IST (375 trading minutes per normal session).
* **Stored Friday Session Completeness**:
  * Opening Window (09:15 to 13:05 IST): **MISSING** (230 minutes unrecorded).
  * Afternoon Window (13:06 to 15:30 IST): **PRESENT** (144 minutes recorded).
  * Post-Market Window (15:30 to 15:44 IST): **PRESENT** (14 minutes of closing prices).
  * Total completeness for the single recorded session: **38.4%**.

---

## 5. Timeframe Coverage & Mismatch

* **Current Operational Timeframe**: 1-minute candles (`1m`).
* **Average 1-Minute Move in Liquid NSE Equities**:
  * Median absolute price change on a 1-minute bar during midday is **0.02% to 0.05%** (2 to 5 bps).
* **Round-Trip Transaction Friction in India**:
  * Zerodha intraday equity brokerage + STT + exchange charges + SEBI + GST + stamp duty + 2.5 bps slippage = **0.08% to 0.15%** (8 to 15 bps).
* **Structural Mismatch**:
  * The 1-minute timeframe produces an expected price movement that is **smaller than the cost to enter and exit**. This creates an insurmountable structural headwind.
  * Migrating to **5-minute candles (`5m`)**, where typical moves range between **0.15% and 0.40%** (15 to 40 bps), is mathematically necessary to allow gross alpha to exceed transaction friction.

---

## 6. Missing Data & Interval Gaps

1. **Morning Friday Session Gap**:
   - Timestamps between 09:15:00 and 13:06:13 are completely missing from `QA/data/friday_session_features.csv` and `dataset_friday_session_1m.jsonl`.
2. **Missing Master Historical Dataset**:
   - The master training dataset `QA/data/processed/master_labeled_dataset.parquet` referenced in `QA/data/fetch_stock_data.py` does not exist on disk.
   - Any script relying on historical parquet files crashes with `FileNotFoundError` or returns early with `"Data not found."`

---

## 7. Duplicate Data & Out-of-Order Records

* Inspection of `QA/data/friday_session_features.csv` confirmed:
  * Duplicate rows: **0**.
  * Out-of-order timestamps: **0**.
  * Timestamp ordering: Monotonically increasing from 13:06:14 to 15:44:03.
* Inspection of `QA/logs/dataset_friday_session_1m.jsonl` confirmed:
  * Duplicate JSON lines: **0**.
  * Monotonically increasing timestamps aligned with CSV records.

---

## 8. Timestamp Integrity & Timezone Handling

* In `QA/data/friday_session_features.csv`, timestamps are recorded in local Indian Standard Time (IST, UTC+05:30) as ISO-8601 strings without an explicit timezone offset string (e.g. `2026-09-18T13:06:14.469707`).
* In `QA/data/fetch_stock_data.py`, yfinance returns timezone-aware timestamps (`Asia/Kolkata`), which the script strips via `dt.tz_localize(None)`.
* **Risk**: Naive datetime manipulation across different modules risks subtle alignment bugs between NIFTY 50 index timestamps and individual stock timestamps during pandas `merge_asof` joins.

---

## 9. Corporate Action Status & Price Adjustments

* `fetch_stock_data.py` calls `yf.download(..., auto_adjust=False)`.
* Raw prices (`open`, `high`, `low`, `close`) are stored alongside `adj_close`.
* For intraday scalping (1-minute and 5-minute), splits and dividends occurring overnight cause severe unadjusted gap artifacts unless corporate action split adjustments are explicitly applied at session open.
* The current 1-minute dataset does not include an adjustment factor column or corporate action calendar metadata.

---

## 10. Data Provider & API Source Information

| Attribute | Current Provider: Yahoo Finance (`yfinance`) | Requirements for Production V2 Provider |
| :--- | :--- | :--- |
| **Data Feed Type** | REST HTTP scraping (unauthenticated API) | Direct Broker WebSocket Feed (e.g. Kite Connect / SmartAPI) |
| **Live Support** | Polling only; 15–45 second latency per batch | Streaming tick-by-tick / 1-second WebSocket packets |
| **Historical 1m Depth** | Strictly limited to **7 calendar days** | At least 60–90 days of continuous 1-minute historical bars |
| **Historical 5m Depth** | Up to **60 calendar days** | At least 180–365 days of continuous 5-minute historical bars |
| **Rate Limits** | IP-throttled by Yahoo (HTTP 429 errors under fast polling) | Broker authenticated limits (e.g. 3 requests/sec REST, unlimited WS) |
| **Data Reliability** | High failure rate; delayed or missing ticks during market open | Exchange-certified tick timestamps with sequence numbers |
| **Authentication** | None (public endpoints) | API Key + API Secret + Daily TOTP Access Token |
| **Cost** | Free | ₹2,000 – ₹4,000 / month API subscription |

---

## 11. Universe Definition & Survivorship Bias

1. **Universe Selection Mechanism**:
   - The universe of 10 stocks in `QA/stocks_config.py` is **100% hardcoded**.
   - There is no dynamic universe selection logic based on liquidity, volume rank, or volatility percentiles.
2. **Survivorship Bias**:
   - The hardcoded list was chosen in September 2026 based on current mega-cap status.
   - Any historical backtest run over 2023–2024 using this static list suffers from survivorship bias (survivors of the period are selected with hindsight).
3. **Point-in-Time Universe Filtration**:
   - Universe filters do not query historical index constituent snapshots (e.g., Nifty 50 historical membership on Jan 1, 2024).

---

## 12. Universe Filter Audit & Historical Lookahead Risk

In `QA/stocks_config.py`:
```python
STOCK_BLACKLIST = {
    "SBIN.NS",        # 36.0% historical baseline accuracy
    "AXISBANK.NS",    # 44.0% historical baseline accuracy
    "ICICIBANK.NS",   # 44.0% historical baseline accuracy
    "HDFCBANK.NS",    # 48.0% historical baseline accuracy
    "BAJFINANCE.NS",  # 48.0% historical baseline accuracy
}
```
* **Severe Lookahead Leakage**:
  - These accuracy percentages were computed over an evaluation window and hardcoded directly into the static configuration file.
  - Applying this blacklist to historical simulations constitutes lookahead bias: the engine uses future evaluation knowledge to avoid trading poorly performing stocks in the past.

---

## 13. Data Sufficiency Classification

### Classification: **`DATA_BLOCKED`**

#### Rationale:
1. **Zero Multi-Month Historical Data on Disk**:
   - The repository contains only 1,090 rows covering 2.5 hours of a single Friday afternoon.
   - The master historical training dataset (`master_labeled_dataset.parquet`) is physically absent from disk.
2. **yfinance API Hard Constraints**:
   - yfinance allows retrieving at most 5–7 days of 1-minute historical data. It is technically impossible to extract 6 months of historical 1-minute bars from yfinance.
3. **Statistical Invalidation**:
   - Walk-forward validation, purged cross-validation, regime stress testing, and edge gate verification cannot be performed without multi-month data.
   - Any model trained solely on 5 days of yfinance data (such as the current 1-minute models trained on 11,110 samples) has an out-of-sample breakout recall of **4.55%** and lacks generalizability.

---

## 14. DATA_BLOCKED Behavioral Rules

Because the data status is classified as `DATA_BLOCKED`, the following strict operational boundaries must be enforced:

```text
+----------------------------------------------------------------------------------------------------+
|                                    DATA_BLOCKED OPERATIONAL BOUNDARIES                             |
+--------------------------------------------------------------------+-------------------------------+
| WHAT MAY PROCEED (Engineering & Infrastructure)                    | WHAT IS STRICTLY PROHIBITED   |
+--------------------------------------------------------------------+-------------------------------+
| [YES] Core V2 architecture implementation                          | [NO] Declaring any model as   |
| [YES] Streaming data pipeline design & WebSocket ingestion engine  |      CHAMPION or production-  |
| [YES] Incremental feature engine implementation & equivalence tests|      certified                |
| [YES] Transaction-cost and integer-share position sizing refactor  | [NO] Passing the edge gate    |
| [YES] Order execution state machine & idempotency implementation   | [NO] Activating autonomous    |
| [YES] Replay simulation engine build                               |      capital routing          |
| [YES] Paper trading infrastructure & telemetry dashboard build     | [NO] Connecting live broker   |
| [YES] Unit test suite creation (aiming for 100% test coverage)     |      capital execution        |
+--------------------------------------------------------------------+-------------------------------+
```

The project **does not stop**. Engineering work proceeds at full capacity. However, financial risk and statistical validation remain locked behind the data gate.

---

## 15. Required Additional Data for AlphaNSE V2

To lift the `DATA_BLOCKED` condition and proceed through Phase 4+ (statistical validation, model promotion, and live routing), the following datasets must be acquired and validated:

1. **Intraday 5-Minute Historical Dataset**:
   - Span: Minimum **180 trading sessions** (approximately 9 calendar months), ideally 2 years.
   - Frequency: 5-minute OHLCV bars.
   - Coverage: 15–20 high-liquidity NSE equities + NIFTY 50 benchmark index (`^NSEI`).
   - Source: Broker historical API (e.g., Zerodha Kite Connect Historical API) or commercial vendor (e.g., TrueData / Global DataFeeds).
2. **Intraday 1-Minute Calibration Dataset**:
   - Span: Minimum **30 trading sessions** (continuous).
   - Frequency: 1-minute OHLCV bars for micro-regime validation.
3. **Corporate Actions & Dividends Table**:
   - Point-in-time stock split and bonus adjustment factors for all universe constituents across the historical period.

---

## 16. Fallback Plan if Historical Data Remains Limited

If commercial high-depth historical broker feeds are delayed:
1. **Continuous Paper Harvester**:
   - Activate the Friday harvester (`QA/monitoring/friday_session_harvester.py`) as a 24/7 daemon to automatically record every minute of live market data from 09:15 to 15:30 IST daily.
   - Accumulate a proprietary, unmanipulated point-in-time dataset across 20 consecutive trading days (7,500 1-minute bars per symbol).
2. **Synthetic Regime Expansion**:
   - Use the existing synthetic module (`QA/synthetic/bootstrap_generator.py` and `monte_carlo_regime_simulator.py`) to generate realistic GARCH/jump-diffusion paths conditioned on historical volatility distributions, solely for stress testing the execution engine and risk filters.
3. **5-Minute Historical Scrape**:
   - yfinance supports up to 60 days of 5-minute candles. Fetch the full 60-day 5-minute history across the universe (approximately 4,500 bars per stock) to bootstrap initial 5-minute model training while the live harvester accumulates proprietary data.
