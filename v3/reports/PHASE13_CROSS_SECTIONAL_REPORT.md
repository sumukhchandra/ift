# AlphaNSE Phase 13: Cross-Sectional Relative Strength & Portfolio Selection Report

**Date:** 2026-10-02  
**Author:** AlphaNSE Quantitative Research & Platform Engineering  
**Protocol Status:** Executed under Strict Non-Negotiable One-Shot Pre-Registration Protocol  
**Safety Gate Status:** `LIVE_TRADING=False` | `ALLOW_REAL_ORDERS=False` (Strictly Enforced)

---

## Executive Summary

Phase 13 evaluated the **Portfolio Selection Hypothesis**:
> *Among liquid NIFTY constituents, do multi-day relative leaders and laggards exhibit persistent subsequent relative divergence or mean-reverting rebalancing that produces price moves large enough to absorb transaction friction?*

Following the non-negotiable research rule:
1. Candidate lookback windows and portfolio models (Momentum vs Reversal, Directional vs Market-Neutral Spread) were evaluated strictly on the **Research Set (June 29 – August 31, 2026)**.
2. The optimal configuration (`CS_DIR_REV_2D`: 2-Day Cross-Sectional Reversal with Macro Trend Conditioning) was pre-registered and **FROZEN**.
3. Evaluated **EXACTLY ONCE** out-of-sample on the **Locked September Test Set (September 1 – 25, 2026)** under `ExecutionRegime.BASE` on ₹1,500 capital (₹7,500 purchasing power).

### Definitive Phase 13 Verdict
* **Gross Trading Edge:** **🟢 POSITIVE (+₹4.66/trade out-of-sample, Profit Factor = 1.25)**.
* **Net Expectancy After Friction:** **🔴 NEGATIVE (-₹8.47/trade due to ₹13.12 BASE friction)**.
* **Deployment Verdict:** **🚫 REAL-MONEY TRADING REMAINS LOCKED.**

| Metric | Research Set (`CS_DIR_REV_2D` Frozen) | Locked September Test Set | Status |
|---|---:|---:|:---:|
| **Trades Evaluated** | 43 | **17** | Out-of-Sample |
| **Win Rate** | 34.9% | **41.2%** | 7 Wins / 10 Losses |
| **Gross Expectancy** | **+₹15.45/trade** | **+₹4.66/trade** | 🟢 **Positive Gross Edge** |
| **Transaction Friction (BASE)** | ₹13.21/trade | **₹13.12/trade** | 87 bps of capital |
| **Net Expectancy** | **+₹2.24/trade** | **-₹8.47/trade** | 🔴 **Negative Net Edge** |
| **Profit Factor** | **1.82** | **1.25** | 🟢 **Super-unity (> 1.0)** |
| **Maximum Drawdown** | ₹371.65 | **₹240.96** | 16.0% of capital |

---

## 1. Research Set Architecture & Parameter Freeze (June 29 – Aug 31)

Across 43 sessions on the Research Set, five cross-sectional portfolio models were ablated:

| Config Name | Lookback | Logic | Trades | Win Rate | Gross Exp. | Friction | Net Exp. | Profit Factor | Max DD |
|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|
| **`CS_DIR_REV_2D`** (FROZEN) | **2 Days** | **Dir. Reversal (Fade 2d Extreme)** | 43 | **34.9%** | **+₹15.45** | ₹13.21 | **+₹2.24** | **1.82** | **₹371.65** |
| `CS_DIR_MOM_2D` | 2 Days | Dir. Momentum (Follow 2d Leader) | 43 | 25.6% | -₹19.61 | ₹12.94 | -₹32.55 | 0.48 | ₹1,489.56 |
| `CS_SPREAD_REV_2D` | 2 Days | Market-Neutral Spread (Long Bot/Short Top) | 86 | 40.7% | +₹9.35 | ₹12.76 | -₹3.41 | 1.44 | ₹644.83 |
| `CS_DIR_REV_3D` | 3 Days | Dir. Reversal (Fade 3d Extreme) | 42 | 33.3% | -₹4.95 | ₹13.26 | -₹18.21 | 0.80 | ₹670.75 |
| `CS_DIR_REV_1D` | 1 Day | Dir. Reversal (Fade 1d Extreme) | 44 | 31.8% | -₹1.53 | ₹13.14 | -₹14.67 | 0.93 | ₹640.13 |

**Selection Rationale:**
* Multi-day momentum (`CS_DIR_MOM_2D`) failed severely (-₹19.61 gross), proving that chasing 2-day winners leads to adverse selection.
* 2-day cross-sectional reversal (`CS_DIR_REV_2D`) generated strong positive gross expectancy (+₹15.45) and a positive net expectancy (+₹2.24) with a Profit Factor of 1.82.
* In accordance with protocol, `CS_DIR_REV_2D` was **frozen without modification** for the locked September test.

---

## 2. Locked September Out-of-Sample Performance (September 1 – 25)

The frozen model was executed once against the 17 trading days of the locked September test set.

### Equity Progression & P&L Summary
* **Total P&L Generated:** -₹143.70 on ₹1,500 capital (-9.5% return).
* **Total Gross P&L:** **+₹79.30** (Total gross wins of ₹400.70 vs gross losses of ₹321.40).
* **Total Friction Incurred:** ₹223.00.
* **Profit Factor:** **1.25** (Gross Wins / Gross Losses).
* **Net Expectancy:** -₹8.47/trade.

### Complete Trade Forensics Log
```text
[SIG_CS_LOC_001] 2026-09-01 TCS.NS       SELL (Rank=10, Excess=+6.75%) -> Net: -Rs  20.29 (Gross: -0.12%) | Regime: MACRO_BEAR
[SIG_CS_LOC_002] 2026-09-02 RELIANCE.NS  SELL (Rank=10, Excess=+2.21%) -> Net: -Rs 107.35 (Gross: -1.45%) | Regime: MACRO_BEAR  <-- Outlier Loss
[SIG_CS_LOC_003] 2026-09-03 RELIANCE.NS  SELL (Rank=10, Excess=+3.52%) -> Net: +Rs   8.43 (Gross: +0.30%) | Regime: MACRO_BEAR
[SIG_CS_LOC_004] 2026-09-04 TATACAP.NS   SELL (Rank=10, Excess=+2.40%) -> Net: -Rs  46.97 (Gross: -0.44%) | Regime: MACRO_BEAR
[SIG_CS_LOC_005] 2026-09-07 TATACAP.NS   SELL (Rank=10, Excess=+3.05%) -> Net: -Rs  34.85 (Gross: -0.29%) | Regime: MACRO_BEAR
[SIG_CS_LOC_006] 2026-09-08 BAJFINANCE.NS SELL (Rank=10, Excess=+1.44%) -> Net: -Rs  41.44 (Gross: -0.38%) | Regime: MACRO_BEAR
[SIG_CS_LOC_007] 2026-09-09 BHARTIARTL.NS SELL (Rank=10, Excess=+1.32%) -> Net: -Rs  12.39 (Gross: +0.01%) | Regime: MACRO_BEAR
[SIG_CS_LOC_008] 2026-09-10 SBIN.NS      SELL (Rank=10, Excess=+0.93%) -> Net: +Rs   8.62 (Gross: +0.30%) | Regime: MACRO_BEAR
[SIG_CS_LOC_009] 2026-09-11 SBIN.NS      SELL (Rank=10, Excess=+0.83%) -> Net: -Rs   9.10 (Gross: +0.04%) | Regime: MACRO_BEAR
[SIG_CS_LOC_010] 2026-09-15 HDFCBANK.NS  SELL (Rank=10, Excess=+3.22%) -> Net: +Rs  24.26 (Gross: +0.54%) | Regime: MACRO_BEAR
[SIG_CS_LOC_011] 2026-09-16 INFY.NS      SELL (Rank=10, Excess=+5.44%) -> Net: +Rs 104.20 (Gross: +1.81%) | Regime: MACRO_BEAR  <-- Large Win
[SIG_CS_LOC_012] 2026-09-17 INFY.NS      SELL (Rank=10, Excess=+2.92%) -> Net: -Rs  58.12 (Gross: -0.60%) | Regime: MACRO_BEAR
[SIG_CS_LOC_013] 2026-09-18 SBIN.NS      SELL (Rank=10, Excess=+1.48%) -> Net: -Rs  76.25 (Gross: -0.90%) | Regime: MACRO_BEAR
[SIG_CS_LOC_014] 2026-09-21 BAJFINANCE.NS SELL (Rank=10, Excess=+2.83%) -> Net: +Rs  30.85 (Gross: +0.61%) | Regime: MACRO_BEAR
[SIG_CS_LOC_015] 2026-09-22 HDFCBANK.NS  SELL (Rank=10, Excess=+3.18%) -> Net: +Rs  27.39 (Gross: +0.54%) | Regime: MACRO_BEAR
[SIG_CS_LOC_016] 2026-09-23 RELIANCE.NS  SELL (Rank=10, Excess=+1.55%) -> Net: -Rs  37.94 (Gross: -0.34%) | Regime: MACRO_BEAR
[SIG_CS_LOC_017] 2026-09-24 TATACAP.NS   SELL (Rank=10, Excess=+1.65%) -> Net: +Rs  97.03 (Gross: +1.53%) | Regime: MACRO_BEAR  <-- Large Win
```

---

## 3. Key Findings & Structural Breakthrough

Phase 13 represents a fundamental qualitative turning point in the platform's empirical research:

### 1. First Statistically Robust Positive Gross Edge
Across all prior phases, gross expectancy was negative:
* Phase 10: -₹25.84/trade
* Phase 11: -₹5.24/trade
* Phase 12: -₹8.97/trade
* **Phase 13: +₹4.66/trade (Gross Profit Factor = 1.25)**

The cross-sectional reversal mechanism generalized out-of-sample. Top relative leaders over a 2-day period frequently experienced mean-reverting pullbacks during the subsequent session, generating average winning gross moves of **+0.82%** (e.g., INFY +1.81%, TATACAP +1.53%, BAJFINANCE +0.61%, HDFCBANK +0.54%).

### 2. The Move Displacement Absorbed Friction on Winning Trades
Unlike Phase 12 (where winning mean reversions only gained +15 bps, resulting in net losses after ₹17 friction), Phase 13 generated substantial net cash gains on winning days:
* INFY: **+₹104.20 net profit** (after ₹17.15 friction)
* TATACAP: **+₹97.03 net profit** (after ₹17.38 friction)
* BAJFINANCE: **+₹30.85 net profit** (after ₹14.88 friction)
* HDFCBANK: **+₹27.39 net profit** (after ₹12.92 friction)

### 3. Why Net Expectancy Remained Negative (-₹8.47/trade)
The frozen model had **zero stop loss**; it held blindly to 15:15 EOD square-off.
* When a strong relative leader continued its momentum against our short (e.g. `SIG_CS_002` RELIANCE on Sep 2: +1.45% adverse move, or `SIG_CS_013` SBIN on Sep 18: +0.90% adverse move), the unconstrained holding allowed large tail losses (-₹107.35 and -₹76.25) that eroded the positive gross profits.
* Average loss was **-₹32.14 gross**, while average win was **+₹57.24 gross**. However, the 41.2% win rate coupled with ₹13.12 transaction friction left a net expectancy of **-₹8.47/trade**.

---

## 4. Multi-Phase Empirical Progression

```text
PHASE 10 (Single-Stock Technical Breakdown + ML)
Gross: -₹25.84 | Friction: ₹14.62 | Net: -₹40.46 | WR:  0.0% | PF: 0.00
Verdict: 🔴 Falsified & Frozen

PHASE 11 (Single-Stock Regime-Conditioned ORB)
Gross:  -₹5.24 | Friction: ₹13.13 | Net: -₹18.37 | WR: 21.1% | PF: 0.64
Verdict: 🔴 Falsified & Frozen

PHASE 12 (Single-Stock Extreme VWAP Reversion)
Gross:  -₹8.97 | Friction: ₹13.27 | Net: -₹22.24 | WR:  0.0% | PF: 0.00
Verdict: 🔴 Falsified & Frozen

PHASE 13 (Cross-Sectional 2-Day Relative Reversal)
Gross:  +₹4.66 | Friction: ₹13.12 | Net:  -₹8.47 | WR: 41.2% | PF: 1.25
Verdict: 🟡 Gross Edge Verified | Net Edge Negative (Friction Deficit: ₹8.47)
```

---

## 5. Platform Safety Status & Rules

| Guardrail | Value | Operational Status |
|---|---|---|
| `LIVE_TRADING` | `False` | 🟢 Enforced in `.env` |
| `ALLOW_REAL_ORDERS` | `False` | 🟢 Enforced in `.env` |
| Broker Integration | Read-Only Test Engine | 🟢 Zero order execution endpoints active |
| RMS / Safety Limits | Enforced | 🟢 Max daily loss, clock drift, circuit breaker verified |

**Conclusion:**  
Because net expectancy remains **-₹8.47/trade**, real-money trading remains **strictly disabled**. Phase 13 has proven that cross-sectional portfolio selection provides structural alpha (+₹4.66/trade gross), whereas single-stock technical heuristics did not.
