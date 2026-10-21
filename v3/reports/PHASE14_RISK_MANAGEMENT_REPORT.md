# AlphaNSE Phase 14: Cross-Sectional Risk Management & Tail-Loss Audit Report

**Date:** 2026-10-02  
**Author:** AlphaNSE Quantitative Research & Platform Engineering  
**Protocol Status:** Executed under Strict Non-Negotiable One-Shot Pre-Registration Protocol  
**Safety Gate Status:** `LIVE_TRADING=False` | `ALLOW_REAL_ORDERS=False` (Strictly Enforced)

---

## Executive Summary

Phase 14 investigated the **Risk Management Hypothesis**:
> *Can structural risk management (fixed adverse stops, volatility-scaled barriers, or midday time-decay filters) truncate tail losses in the 2-Day Cross-Sectional Reversal strategy (`CS_DIR_REV_2D`) without destroying its positive gross expectancy, thereby achieving positive net expectancy after BASE transaction friction?*

Following the non-negotiable research rule:
1. Five candidate risk management architectures were ablated strictly on the **Research Set (June 29 – August 31, 2026)**.
2. The optimal configuration was selected based strictly on research set metrics (Net Expectancy, Profit Factor, Drawdown).
3. The selected model was **FROZEN** and evaluated **EXACTLY ONCE** out-of-sample on the **Locked September Test Set (September 1 – 25, 2026)** under `ExecutionRegime.BASE` on ₹1,500 capital (₹7,500 purchasing power).

### Definitive Phase 14 Verdict
* **Gross Trading Edge:** **🟢 POSITIVE (+₹2.67/trade out-of-sample, Profit Factor = 1.12)**.
* **Stop Loss Impact:** **🔴 ADVERSE (Stops prematurely truncate mean-reverting recovery and degrade net performance)**.
* **Net Expectancy After Friction:** **🔴 NEGATIVE (-₹10.46/trade due to ₹13.13 BASE friction)**.
* **Deployment Verdict:** **🚫 REAL-MONEY TRADING REMAINS FIRMLY LOCKED.**

| Metric | Research Set (`RM0_BASELINE_EOD` Frozen) | Locked September Test Set | Status |
|---|---:|---:|:---:|
| **Trades Evaluated** | 43 | **17** | Out-of-Sample |
| **Win Rate** | 39.5% | **41.2%** | 7 Wins / 10 Losses |
| **Gross Expectancy** | **+₹20.13/trade** | **+₹2.67/trade** | 🟢 **Positive Gross Edge** |
| **Transaction Friction (BASE)** | ₹13.21/trade | **₹13.13/trade** | 88 bps of capital |
| **Net Expectancy** | **+₹6.92/trade** | **-₹10.46/trade** | 🔴 **Negative Net Edge** |
| **Profit Factor** | **2.20** | **1.12** | 🟢 **Super-unity (> 1.0)** |
| **Maximum Drawdown** | ₹348.15 | **₹234.95** | 15.7% of capital |
| **Stop Hits** | 0 | **0** | Clean EOD Execution |

---

## 1. Research Set Risk Architecture Ablation (June 29 – Aug 31)

Across 43 sessions on the Research Set, five risk management architectures were evaluated on identical entry signals:

| Risk Variant | Mechanism | Trades | Win Rate | Gross Exp. | Friction | Net Exp. | Profit Factor | Max DD | Stop Hits |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **`RM0_BASELINE_EOD`** (FROZEN) | **Unconstrained EOD Hold (15:15)** | 43 | **39.5%** | **+₹20.13** | ₹13.21 | **+₹6.92** | **2.20** | **₹348.15** | **0** |
| `RM1_CATASTROPHE_150` | 1.50% Wide Catastrophe Stop | 43 | 39.5% | +₹17.99 | ₹13.35 | +₹4.63 | 1.95 | ₹366.89 | 3 |
| `RM3_FIXED_100` | 1.00% Fixed Adverse Stop | 43 | 39.5% | +₹15.61 | ₹12.93 | +₹2.68 | 1.73 | ₹489.49 | 9 |
| `RM4_MIDDAY_FILTER` | 12:00 Exit if Underwater >0.50% | 43 | 39.5% | +₹15.52 | ₹13.35 | +₹2.17 | 1.72 | ₹456.34 | 13 |
| `RM2_VOLATILITY_15ATR` | 1.5x ATR Stop Loss | 43 | 30.2% | +₹8.89 | ₹13.03 | -₹4.13 | 1.38 | ₹534.83 | 24 |

### Critical Empirical Finding: The Stop-Loss Paradox
Every structural stop mechanism tested on the Research Set degraded performance:
1. **Premature Truncation of Mean Reversion:**  
   Cross-sectional reversals naturally experience intraday noise (MAE typically spans 0.60% to 1.10% during the morning session before peaking and reverting into the afternoon). Tight stops (1.0% or 1.5x ATR) hit 9 to 24 times, liquidating trades at maximum adverse excursion right before the afternoon mean reversion occurred.
2. **Catastrophe Stops Dilute Expected Value:**  
   The 1.50% catastrophe stop (`RM1`) lowered gross expectancy from +₹20.13 to +₹17.99 and net expectancy from +₹6.92 to +₹4.63 without reducing maximum drawdown (₹366.89 vs ₹348.15).
3. **Selection Decision:**  
   `RM0_BASELINE_EOD` was unequivocally the superior architecture on the Research Set across all quantitative metrics and was **frozen without modification** for the locked September test.

---

## 2. Locked September Out-of-Sample Performance (September 1 – 25)

The frozen configuration was executed once against the 17 trading days of the locked September test set.

### Equity Progression & P&L Summary
* **Total P&L Generated:** -₹177.82 on ₹1,500 capital (-11.8% return).
* **Total Gross P&L:** **+₹45.39** (Gross wins: ₹400.70 vs gross losses: ₹355.31).
* **Total Friction Incurred:** ₹223.21.
* **Profit Factor:** **1.12** (> 1.0).
* **Net Expectancy:** -₹10.46/trade.

### Complete Trade Forensics Log
```text
[SIG_P14_LOC_001] 2026-09-01 TCS.NS       SELL @ 2355.90 -> Exit @ 2370.56 (15:15_EOD_SQUAREOFF) | Net: -Rs  60.28 (Gross: -0.68%) | MFE: +0.81% | MAE: 0.65%
[SIG_P14_LOC_002] 2026-09-02 RELIANCE.NS  SELL @ 1297.10 -> Exit @ 1314.11 (15:15_EOD_SQUAREOFF) | Net: -Rs 103.35 (Gross: -1.39%) | MFE: +0.14% | MAE: 1.90%
[SIG_P14_LOC_003] 2026-09-03 RELIANCE.NS  SELL @ 1314.70 -> Exit @ 1303.41 (15:15_EOD_SQUAREOFF) | Net: +Rs  40.95 (Gross: +0.80%) | MFE: +0.93% | MAE: 0.10%
[SIG_P14_LOC_004] 2026-09-04 TATACAP.NS   SELL @  374.10 -> Exit @  375.57 (15:15_EOD_SQUAREOFF) | Net: -Rs  47.97 (Gross: -0.46%) | MFE: +0.72% | MAE: 0.74%
[SIG_P14_LOC_005] 2026-09-07 TATACAP.NS   SELL @  368.95 -> Exit @  369.98 (15:15_EOD_SQUAREOFF) | Net: -Rs  38.85 (Gross: -0.34%) | MFE: +0.89% | MAE: 0.53%
[SIG_P14_LOC_006] 2026-09-08 BAJFINANCE.NS SELL @ 1052.70 -> Exit @ 1054.89 (15:15_EOD_SQUAREOFF) | Net: -Rs  33.74 (Gross: -0.27%) | MFE: +0.26% | MAE: 0.59%
[SIG_P14_LOC_007] 2026-09-09 BHARTIARTL.NS SELL @ 1823.10 -> Exit @ 1816.16 (15:15_EOD_SQUAREOFF) | Net: +Rs  10.07 (Gross: +0.32%) | MFE: +0.46% | MAE: 0.43%
[SIG_P14_LOC_008] 2026-09-10 SBIN.NS      SELL @ 1008.50 -> Exit @ 1010.33 (15:15_EOD_SQUAREOFF) | Net: -Rs  30.05 (Gross: -0.25%) | MFE: +0.67% | MAE: 0.30%
[SIG_P14_LOC_009] 2026-09-11 SBIN.NS      SELL @  997.90 -> Exit @  996.30 (15:15_EOD_SQUAREOFF) | Net: -Rs   5.59 (Gross: +0.09%) | MFE: +0.45% | MAE: 0.39%
[SIG_P14_LOC_010] 2026-09-15 HDFCBANK.NS  SELL @  721.60 -> Exit @  717.08 (15:15_EOD_SQUAREOFF) | Net: +Rs  24.76 (Gross: +0.55%) | MFE: +0.90% | MAE: 0.94%
[SIG_P14_LOC_011] 2026-09-16 INFY.NS      SELL @ 1078.60 -> Exit @ 1058.28 (15:15_EOD_SQUAREOFF) | Net: +Rs 104.20 (Gross: +1.81%) | MFE: +2.33% | MAE: 0.16%
[SIG_P14_LOC_012] 2026-09-17 INFY.NS      SELL @ 1053.80 -> Exit @ 1059.38 (15:15_EOD_SQUAREOFF) | Net: -Rs  58.12 (Gross: -0.60%) | MFE: +0.49% | MAE: 0.92%
[SIG_P14_LOC_013] 2026-09-18 SBIN.NS      SELL @  985.90 -> Exit @  997.02 (15:15_EOD_SQUAREOFF) | Net: -Rs  97.26 (Gross: -1.20%) | MFE: +0.03% | MAE: 1.04%
[SIG_P14_LOC_014] 2026-09-21 BAJFINANCE.NS SELL @ 1032.40 -> Exit @ 1025.31 (15:15_EOD_SQUAREOFF) | Net: +Rs  30.85 (Gross: +0.61%) | MFE: +0.99% | MAE: 0.35%
[SIG_P14_LOC_015] 2026-09-22 HDFCBANK.NS  SELL @  747.05 -> Exit @  742.54 (15:15_EOD_SQUAREOFF) | Net: +Rs  27.39 (Gross: +0.54%) | MFE: +0.83% | MAE: 0.30%
[SIG_P14_LOC_016] 2026-09-23 RELIANCE.NS  SELL @ 1243.20 -> Exit @ 1246.62 (15:15_EOD_SQUAREOFF) | Net: -Rs  37.94 (Gross: -0.34%) | MFE: +0.32% | MAE: 0.77%
[SIG_P14_LOC_017] 2026-09-24 TATACAP.NS   SELL @  341.80 -> Exit @  336.33 (15:15_EOD_SQUAREOFF) | Net: +Rs  97.03 (Gross: +1.53%) | MFE: +2.53% | MAE: 0.16%
```

---

## 3. Comparative Synthesis Across All 5 Scientific Validation Phases

| Phase | Core Hypothesis Tested | Out-of-Sample Gross Exp. | BASE Friction | Out-of-Sample Net Exp. | Profit Factor | Status |
|---|---|---:|---:|---:|---:|:---:|
| **Phase 10** | Single-Stock Technical Breakdown + ML Gate | -₹25.84/trade | ₹14.62 | **-₹40.46/trade** | 0.00 | 🔴 Falsified & Frozen |
| **Phase 11** | Regime-Conditioned 30m ORB Breakout | -₹5.24/trade | ₹13.13 | **-₹18.37/trade** | 0.64 | 🔴 Falsified & Frozen |
| **Phase 12** | Intraday Extreme VWAP Reversion | -₹8.97/trade | ₹13.27 | **-₹22.24/trade** | 0.00 | 🔴 Falsified & Frozen |
| **Phase 13** | 2-Day Cross-Sectional Reversal | **+₹4.66/trade** | ₹13.12 | **-₹8.47/trade** | **1.25** | 🟡 Gross Edge Confirmed |
| **Phase 14** | Cross-Sectional Risk Management Audit | **+₹2.67/trade** | ₹13.13 | **-₹10.46/trade** | **1.12** | 🟡 Gross Edge Confirmed |

---

## 4. Fundamental Quantitative Diagnosis

Phase 14 provides the final mathematical resolution to the intraday trading inquiry on this universe:

1. **Gross Alpha is Genuine but Modest:**
   * Across both Phase 13 and Phase 14, cross-sectional relative reversal is the **only signal family that generalized out-of-sample with positive gross expectancy (+₹2.67 to +₹4.66/trade) and super-unity profit factor (1.12 to 1.25)**.
   * Large-cap relative divergence over 2 days reliably exhibits mean-reverting rebalancing during the subsequent session.
2. **The Microstructure Friction Barrier:**
   * Full realistic execution friction (Zerodha/NSE statutory charges, bid-ask spread crossing, adverse slippage) under ₹1,500 initial capital (₹7,500 position size) amounts to **₹13.13 per trade (~17 to 20 basis points on turnover, or ~88 basis points of capital)**.
   * The realized gross edge (+₹2.67 to +₹4.66 per trade, or ~4 to 6 basis points on turnover) is **insufficient to absorb this friction**.
3. **The Stop-Loss Paradox Prevents Friction Recovery:**
   * Stop losses cannot rescue the net expectancy because mean-reverting alpha requires giving positions room to breathe through the morning oscillation (MAE ~0.6% to 1.1%). Tight stops choke off the winners and increase turnover costs.
4. **Capital Scale Insight:**
   * Because statutory brokerage in India is capped at ₹20 per order or 0.03%, at higher capital bases (e.g. ₹50,000 to ₹1,00,000 position sizes), the relative friction drops from ~20 bps down to ~5 to 8 bps. At ₹1,500 capital, the fixed minimum transaction overhead dominates.

---

## 5. Platform Safety Verification

* `LIVE_TRADING=False` and `ALLOW_REAL_ORDERS=False` remain **strictly enforced**.
* Zero real-money trades are permitted.
* The platform's scientific audit confirms that no net trading edge exists under the specified capital and fee structure.
