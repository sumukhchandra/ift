# ALPHANSE V2 — PHASE 2 DATA COVERAGE & VALIDATION REPORT

**Evaluation Timestamp**: `2026-09-19T12:56:01 IST`  
**Pipeline Version**: `AlphaNSE_V2_Phase2`  
**Evaluation Status**: `DATA_LIMITED` (Gate Cleared: `PASS ✅`)  
**Live Execution Lockout**: `ACTIVE (PHYSICALLY DISABLED)`

---

## 1. Executive Summary

In response to forensic review and audit feedback, AlphaNSE V2 Phase 2 data architecture has resolved the two key data requirements:
1. **Raw vs Adjusted Economic Disambiguation**: Resolved the identical SHA-256 hash issue. Implemented the standard backward corporate-action adjustment engine (CRSP methodology) incorporating all splits and cash dividends from `corporate_actions.parquet`. Raw execution prices (`historical_5m_raw.parquet`) and research continuous return prices (`historical_5m_adjusted.parquet`) are now distinctly computed, mathematically validated, and verified with **distinct cryptographic SHA-256 hashes**.
2. **Deterministic Volatility-Regime Gate Evaluated**: Fully evaluated and verified the pre-committed volatility-regime coverage criterion across all 59 trading sessions. The dataset covers **3 distinct volatility regimes** (`LOW_VOL`: 16 sessions, `NORMAL_VOL`: 29 sessions, `HIGH_VOL`: 14 sessions), passing the $\ge 2$ regime threshold.
3. **Maturity Classification**: Maintained strictly at **`DATA_LIMITED`**. This dataset is verified for 5-minute feature engineering, walk-forward model prototyping, and chronological replay backtesting, but does **not** claim multi-year regime universality or live broker authorization. Live broker routing remains physically disabled via `LiveExecutionDisabledError`.
4. **Baseline Universe Boundary**: Clarified that the 11 assets in `universe_membership.parquet` represent the **fixed baseline research universe** for Phase 2/3 engineering, not a dynamic point-in-time index rebalancing engine.
5. **Automated Test Suite**: Extended with comprehensive unit and pipeline tests, resulting in **47/47 passing tests (100% pass rate in 1.31s)**.

---

## 2. Raw vs Adjusted Series: Policy, Math & Verification

### 2.1 The Architectural Distinction
In quantitative algorithmic trading, raw execution prices and adjusted research prices serve fundamentally different economic functions:

```text
RAW EXECUTION SERIES (historical_5m_raw.parquet)
├── Traded exchange prices as recorded on the National Stock Exchange (NSE)
├── Enforces cash feasibility, buying power, and broker margin limits
├── Drives integer share position sizing: Q = floor(Capital / Price)
└── Computes statutory transaction costs (STT, Exchange turnover, Stamp Duty, Brokerage)

ADJUSTED RESEARCH SERIES (historical_5m_adjusted.parquet)
├── Continuous total-return price series adjusted backward for corporate actions
├── Eliminates artificial dividend and split price gaps
├── Prevents ML models from learning spurious drops on dividend ex-dates
└── Provides stationary return inputs for return forecasting and feature generation
```

### 2.2 Why Were the Initial Hashes Identical?
During the initial Phase 2 download, Yahoo Finance's intraday feed natively applied stock split adjustments when `auto_adjust=True`, but **did not adjust intraday bars for cash dividends**. Because no stock splits occurred during the 60-calendar-day window (June 29 to September 18, 2026), both queries returned the same price values.

### 2.3 Backward Corporate Action Adjustment Methodology (CRSP Standard)
We implemented an explicit corporate-action adjustment engine directly in `ParquetPipeline.apply_corporate_action_adjustments()`.

For a cash dividend $D$ occurring on ex-dividend date $T_{\text{ex}}$:
1. Locate the unadjusted closing price $P_{\text{prev}}$ on the trading day immediately preceding $T_{\text{ex}}$.
2. Compute the price adjustment factor:
   $$f = \frac{P_{\text{prev}} - D}{P_{\text{prev}}} = 1 - \frac{D}{P_{\text{prev}}}$$
3. For all bars prior to $T_{\text{ex}}$ ($t < T_{\text{ex}}$):
   $$P_{\text{adj}}(t) = P_{\text{raw}}(t) \times f$$
4. Bars on or after $T_{\text{ex}}$ ($t \ge T_{\text{ex}}$) remain unadjusted ($f = 1.0$). Volume is unchanged for cash dividends (divided by split ratio for stock splits).

### 2.4 Empirical Verification: Active Window Corporate Actions
During the 59-session window, exactly 6 cash dividends occurred across our 10-stock equity universe. The table below details the exact unadjusted close, dividend value, adjustment factor, and the verified before/after price adjustments:

| Symbol | Action Type | Ex-Date ($T_{\text{ex}}$) | Cash Value ($D$) | Pre-Ex Close ($P_{\text{prev}}$) | Adjustment Factor ($f$) | Pre-Ex Close: Raw $\to$ Adj | Ex-Date Open: Raw $\to$ Adj |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **AXISBANK.NS** | Cash Dividend | `2026-07-10` | ₹1.00 | ₹1,297.60 | `0.999229` | ₹1,297.60 $\to$ **₹1,296.60** (diff: ₹1.00) | ₹1,304.90 $\to$ **₹1,304.90** (diff: ₹0.00) |
| **BAJFINANCE.NS** | Cash Dividend | `2026-06-30` | ₹6.00 | ₹982.05 | `0.993890` | ₹982.05 $\to$ **₹976.05** (diff: ₹6.00) | ₹986.90 $\to$ **₹986.90** (diff: ₹0.00) |
| **BHARTIARTL.NS** | Cash Dividend | `2026-07-24` | ₹24.00 | ₹1,931.00 | `0.987571` | ₹1,931.00 $\to$ **₹1,907.00** (diff: ₹24.00) | ₹1,901.00 $\to$ **₹1,901.00** (diff: ₹0.00) |
| **ICICIBANK.NS** | Cash Dividend | `2026-08-03` | ₹12.00 | ₹1,433.80 | `0.991631` | ₹1,433.80 $\to$ **₹1,421.80** (diff: ₹12.00) | ₹1,442.40 $\to$ **₹1,442.40** (diff: ₹0.00) |
| **TATACAP.NS** | Cash Dividend | `2026-07-27` | ₹0.57 | ₹342.00 | `0.998333` | ₹342.00 $\to$ **₹341.43** (diff: ₹0.57) | ₹344.90 $\to$ **₹344.90** (diff: ₹0.00) |
| **TCS.NS** | Cash Dividend | `2026-07-15` | ₹12.00 | ₹2,197.00 | `0.994538` | ₹2,197.00 $\to$ **₹2,185.00** (diff: ₹12.00) | ₹2,165.20 $\to$ **₹2,165.20** (diff: ₹0.00) |

* **Symbols with Dividends**: `historical_5m_raw.parquet` preserves raw traded prices; `historical_5m_adjusted.parquet` preserves the backward dividend-adjusted total-return prices.
* **Symbols without Dividends in Window** (`RELIANCE.NS`, `INFY.NS`, `SBIN.NS`, `^NSEI`): Raw and adjusted series are identical ($f = 1.0$).
* **1-Minute Calibration Dataset** (September 10 to September 18, 2026): No corporate actions occurred during this 7-day window. Therefore, `historical_1m_raw.parquet` and `historical_1m_adjusted.parquet` have identical SHA-256 hashes for a documented, mathematically verified reason.

### 2.5 Ingestion Manifest & Distinct SHA-256 Checksums

| File Name | File Size | Row Count | SHA-256 Checksum | Distinct Status |
| :--- | :---: | :---: | :--- | :---: |
| `historical_5m_raw.parquet` | 1,002 KB | 48,009 | `62c14fe79e4bb551500a60bc4e93cf146f80ad1a836e9dc6d3a74086602208cc` | **DISTINCT ✅** |
| `historical_5m_adjusted.parquet` | 1,002 KB | 48,009 | `01d6ed6eed05b58664a31bc319f6e89437a421d561e231610e525692f101125a` | **DISTINCT ✅** |
| `historical_1m_raw.parquet` | 406 KB | 23,986 | `7873d7911fef91d60ce7414054fbb151a7ea878341af79f4037e44420fa4504c` | Verified (No actions in window) |
| `historical_1m_adjusted.parquet` | 406 KB | 23,986 | `7873d7911fef91d60ce7414054fbb151a7ea878341af79f4037e44420fa4504c` | Verified (No actions in window) |
| `universe_membership.parquet` | 5.9 KB | 11 | `81c24e95c9abfc9ade908b4ab5d68c309b39c2ddf052b1da41f5a9ae3f0b8792` | Baseline universe |
| `corporate_actions.parquet` | 14.2 KB | 363 | `699eef53acf4d6047e3ca8e102dadfa64ee2e55919004ee546eb2b967fd6f676` | Explicit audit table |

---

## 3. Volatility-Regime Gate Evaluation

### 3.1 Mathematical Methodology
To verify that the dataset is not confined to a single market condition, each of the 59 sessions was classified by its cross-sectional equity realized volatility.

For each session $d$ and each equity $m$, the 5-minute intraday log returns $r_{m,t} = \ln(P_{m,t} / P_{m,t-1})$ are computed, and the annualized realized volatility is:
$$\sigma_{m,d} = \sqrt{\sum_{t=1}^{N_d} r_{m,t}^2} \times \sqrt{252}$$
The session benchmark volatility $\sigma_d$ is the cross-sectional mean across the equity universe:
$$\sigma_d = \frac{1}{M} \sum_{m=1}^M \sigma_{m,d}$$

Sessions are mapped to standard quantitative volatility regimes:
* **`LOW_VOL`**: $\sigma_d < 15.0\%$ annualized (calm, trending or quiet consolidation)
* **`NORMAL_VOL`**: $15.0\% \le \sigma_d \le 19.0\%$ annualized (typical equity market conditions)
* **`HIGH_VOL`**: $\sigma_d > 19.0\%$ annualized (elevated macro swings, RBI policy announcements, earnings surprises)

### 3.2 Empirical Regime Distribution

```text
========================================================================================
VOLATILITY REGIME     SESSION COUNT     PERCENTAGE     RANGE (ANNUALIZED VOL)
========================================================================================
LOW_VOL               16 sessions       27.1%          11.75% – 14.98%
NORMAL_VOL            29 sessions       49.2%          15.02% – 18.96%
HIGH_VOL              14 sessions       23.7%          19.05% – 30.22%
========================================================================================
TOTAL SESSIONS        59 sessions       100.0%         Mean: 17.02%, Std: 3.24%
DISTINCT REGIMES      3 regimes         (Required: >= 2) -> PASS ✅
========================================================================================
```

### 3.3 Representation Analysis
* **Low Volatility Days (16 sessions)**: E.g., mid-July range-bound consolidation where index moves were subdued ($< 0.4\%$ daily range).
* **Normal Volatility Days (29 sessions)**: Standard two-way auction sessions with consistent 5-minute moves between 15–30 bps.
* **High Volatility Days (14 sessions)**: Sessions in early August and mid-September characterized by wide intraday swings ($> 1.2\%$ moves across tech and banking heavyweights, annualized volatility reaching 30.2%).
* **Gate Verdict**: The dataset satisfies the pre-committed requirement of at least 2 distinct regimes by capturing **3 distinct market environments**.

---

## 4. Complete Deterministic Data Gate Evaluation

### 4.1 Per-Symbol Missing-Bar Validation Gate (`max_missing_bar_pct_per_symbol <= 5.0%`)

In accordance with strict quantitative data governance, the universe does not pass merely because the aggregate missing rate is below 5.0%. Every required constituent must independently satisfy $\text{missing\_pct}(s) \le 5.0\%$:

| Symbol | Company / Instrument | Actual Bars | Expected Grid Bars | Missing Bars | Missing % | Per-Symbol Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **AXISBANK.NS** | Axis Bank Limited | 4,351 | 4,425 | 74 | 1.67% | **PASS ✅** |
| **BAJFINANCE.NS** | Bajaj Finance Limited | 4,350 | 4,425 | 75 | 1.69% | **PASS ✅** |
| **BHARTIARTL.NS** | Bharti Airtel Limited | 4,348 | 4,425 | 77 | 1.74% | **PASS ✅** |
| **HDFCBANK.NS** | HDFC Bank Limited | 4,355 | 4,425 | 70 | 1.58% | **PASS ✅** |
| **ICICIBANK.NS** | ICICI Bank Limited | 4,351 | 4,425 | 74 | 1.67% | **PASS ✅** |
| **INFY.NS** | Infosys Limited | 4,351 | 4,425 | 74 | 1.67% | **PASS ✅** |
| **RELIANCE.NS** | Reliance Industries | 4,353 | 4,425 | 72 | 1.63% | **PASS ✅** |
| **SBIN.NS** | State Bank of India | 4,354 | 4,425 | 71 | 1.60% | **PASS ✅** |
| **TATACAP.NS** | Tata Capital Limited | 4,425 | 4,425 | 0 | 0.00% | **PASS ✅** |
| **TCS.NS** | Tata Consultancy Services | 4,346 | 4,425 | 79 | 1.79% | **PASS ✅** |
| **^NSEI** | Nifty 50 Index Benchmark | 4,425 | 4,425 | 0 | 0.00% | **PASS ✅** |

**Universal Constituent Verdict**: **`ALL_REQUIRED_SYMBOLS_PASS = TRUE`**  
The worst-performing symbol missing rate is **1.79%** (`TCS.NS`), confirming that zero constituents are starved or degraded.

---

### 4.2 Comprehensive 7-Criterion Deterministic Gate

```text
==================================================================================================
CRITERION                          TARGET         ACTUAL MEASURED     VERDICT     DETAILS
==================================================================================================
minimum_sessions_required          >= 40          59 sessions         PASS ✅     59 distinct NSE sessions
max_missing_bar_pct                <= 5.0%        1.37%               PASS ✅     666 / 48,675 bars missing
max_missing_bar_pct_per_symbol     <= 5.0%        1.79% (TCS.NS)      PASS ✅     All 11 symbols <= 1.79%
min_symbols_required               >= 11          11 symbols          PASS ✅     10 equities + ^NSEI
max_duplicate_pct                  == 0.0%        0.00%               PASS ✅     0 duplicate timestamps
min_bars_per_symbol                >= 2500        4,346 bars (TCS)    PASS ✅     All symbols >= 4,346 bars
required_regimes_covered           >= 2           3 regimes           PASS ✅     16 Low, 29 Normal, 14 High
==================================================================================================
FINAL DATA GATE DECISION: DATA_LIMITED (ALL 7 CRITERIA PASSED)
ALL_REQUIRED_SYMBOLS_PASS = TRUE
==================================================================================================
```

---

## 5. Scope & Boundary of `DATA_LIMITED` Status

We explicitly reiterate the strict boundaries of the `DATA_LIMITED` classification:

### Permitted (Unblocked):
1. **5-Minute Feature Engineering**: Safe calculation of 30+ technical, momentum, volatility, and volume indicators.
2. **Replay Engine Execution**: Deterministic event-driven simulation using `HistoricalReplayAdapter.from_parquet()` with strict point-in-time `AsOfClock` no-lookahead guarantees.
3. **Walk-Forward Model Prototyping**: Partitioning the 59 sessions into train (sessions 1–40), validation (sessions 41–50), and out-of-sample test (sessions 51–59) with purged and embargoed splits.
4. **Economic Expectancy Evaluation**: Testing candidate signals against the `IndiaCostEngine` (~10.4 bps round-trip friction) to establish if a true gross edge exceeds transaction costs.

### Strictly Prohibited (Blocked):
1. **Live Execution**: `ExecutionRouter.route_order()` actively raises `LiveExecutionDisabledError`. Live trading cannot be executed.
2. **Model Promotion to CHAMPION**: `ModelRegistry` will not certify any model as production-ready based solely on a single 59-session window.
3. **Overfitting Claims**: 59 sessions cannot prove multi-year structural edge; it is the minimum required empirical sample to test whether a 5-minute intraday signal exists.

---

## 6. Baseline Research Universe Specification

As noted during audit, `universe_membership.parquet` records 11 rows:
* **10 Large-Cap Equities**: `RELIANCE.NS`, `HDFCBANK.NS`, `BHARTIARTL.NS`, `ICICIBANK.NS`, `TATACAP.NS`, `INFY.NS`, `TCS.NS`, `SBIN.NS`, `AXISBANK.NS`, `BAJFINANCE.NS`.
* **1 Benchmark Index**: `^NSEI` (Nifty 50).

**Architecture Note**: This represents the **fixed baseline research universe** selected for Phase 2/3 engineering, not a dynamic point-in-time index rebalancing engine. Dynamic survivorship-free index reconstitution will be implemented when scaling beyond the initial 10-stock universe.

---

## 7. Conclusion & Readiness for Phase 3

Both blocking issues have been resolved:
1. `historical_5m_raw.parquet` and `historical_5m_adjusted.parquet` are now distinct, mathematically verified series with unique SHA-256 hashes.
2. The volatility-regime gate has been evaluated and confirmed with 3 distinct regimes covered across 59 sessions.

Phase 2 is complete. The system stands ready for **Phase 3: 5-Minute Return Horizon, Model Architecture & Walk-Forward Training**.
*(Implementation will NOT begin until explicitly requested and approved by the user).*
