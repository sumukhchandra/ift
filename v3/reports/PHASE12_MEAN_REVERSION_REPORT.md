# AlphaNSE Phase 12: Intraday Extreme Mean Reversion Report

**Date:** 2026-10-02  
**Author:** AlphaNSE Quantitative Research & Platform Engineering  
**Protocol Status:** Executed under Strict Non-Negotiable One-Shot Evaluation Protocol  
**Safety Gate Status:** `LIVE_TRADING=False` | `ALLOW_REAL_ORDERS=False` (Strictly Enforced)

---

## Executive Summary

Phase 12 evaluated the **Opposite Market Behavior Hypothesis**:
> *Do unusually large short-term intraday price extensions away from volume-weighted average price (VWAP) represent temporary liquidity depletion that subsequently reverts toward the session mean, providing a tradable edge?*

Following the non-negotiable research rule, parameter combinations were tested strictly on the **Research Set (June 29 – August 31, 2026)**, the best parameter configuration (`MR_Z25_FULL_VWAP`) was frozen, and evaluated **EXACTLY ONCE** out-of-sample on the **Locked September Test Set (September 1 – 25, 2026)** under `ExecutionRegime.BASE` on ₹1,500 capital (₹7,500 purchasing power).

### Definitive Phase 12 Verdict
**HYPOTHESIS FALSIFIED & REJECTED AS POSITIVE TRADING EDGE.**

| Metric | Research Set (`MR_Z25_FULL_VWAP` Frozen) | Locked September Test Set | Status |
|---|---:|---:|:---:|
| **Trades Evaluated** | 27 | **7** | Out-of-Sample |
| **Win Rate** | 11.1% | **0.0%** | (0 Wins / 7 Losses) |
| **Gross Expectancy** | -₹10.15/trade | **-₹8.97/trade** | **Negative Gross Edge** |
| **Transaction Friction (BASE)** | ₹12.89/trade | **₹13.27/trade** | 88 bps of capital |
| **Net Expectancy** | -₹23.04/trade | **-₹22.24/trade** | **Net Loss per Trade** |
| **Profit Factor** | 0.25 | **0.0** | Sub-unity (Zero Wins) |
| **Maximum Drawdown** | ₹614.15 | **₹154.70** | Monotonic Decline |

---

## 1. Research Set Evaluation & Parameter Selection (June 29 – Aug 31)

Six candidate configurations were evaluated across deviation hurdles ($Z \in \{2.0, 2.5\}$) and exit modes (`FULL_VWAP`, `HALFWAY_VWAP`, `FIXED_1ATR`):

| Config Name | Z-Threshold | Target Mode | Trades | Win Rate | Gross Exp. | Friction | Net Exp. | Profit Factor | Max DD |
|---|:---:|:---:|---:|---:|---:|---:|---:|---:|---:|
| `MR_Z20_FULL_VWAP` | 2.0 | Full VWAP | 76 | 5.3% | -₹10.85 | ₹12.87 | -₹23.72 | 0.13 | ₹1,784.05 |
| `MR_Z20_HALFWAY` | 2.0 | 50% Retracement | 76 | 2.6% | -₹10.71 | ₹12.65 | -₹23.36 | 0.08 | ₹1,753.67 |
| `MR_Z20_1ATR` | 2.0 | 1.0x ATR Target | 76 | 1.3% | -₹11.13 | ₹12.86 | -₹23.98 | 0.02 | ₹1,816.38 |
| `MR_Z25_FULL_VWAP` (FROZEN) | 2.5 | Full VWAP | 27 | **11.1%** | **-₹10.15** | ₹12.89 | **-₹23.04** | **0.25** | **₹614.15** |
| `MR_Z25_HALFWAY` | 2.5 | 50% Retracement | 27 | 11.1% | -₹10.70 | ₹12.94 | -₹23.64 | 0.23 | ₹619.93 |
| `MR_Z25_1ATR` | 2.5 | 1.0x ATR Target | 27 | 3.7% | -₹10.56 | ₹12.87 | -₹23.43 | 0.07 | ₹621.37 |

**Pre-Registration Selection:**
`MR_Z25_FULL_VWAP` generated the lowest loss per trade (-₹23.04) and lowest maximum drawdown (₹614.15). In accordance with protocol, it was **frozen without modification** for the locked September test.

---

## 2. Locked September Out-of-Sample Performance (September 1 – 25)

The frozen configuration was executed once against the 410 fifteen-minute bars (19 trading sessions) of the locked September test set.

### Equity Progression & P&L Summary
* **Total P&L Generated:** -₹155.68 on ₹1,500 capital (-10.4% return).
* **Gross P&L:** -₹62.79.
* **Total Friction Incurred:** ₹92.89.
* **Expectancy:** -₹22.24 net loss per trade.

### Complete Trade Forensics Log
```text
[SIG_MR_LOC_001] 2026-09-02 BAJFINANCE.NS SELL @ 1042.80 (Z=+2.59) -> Exit @ 1040.55 (TARGET_HIT    ) | Net: -Rs  0.96 | MFE: +0.48% | MAE: 0.07%
[SIG_MR_LOC_003] 2026-09-03 ICICIBANK.NS BUY  @ 1437.60 (Z=-2.85) -> Exit @ 1439.79 (TIME_DECAY_45M) | Net: -Rs  9.25 | MFE: +0.45% | MAE: 0.02%
[SIG_MR_LOC_002] 2026-09-03 BHARTIARTL.NS BUY  @ 1861.80 (Z=-2.56) -> Exit @ 1864.19 (TARGET_HIT    ) | Net: -Rs  8.12 | MFE: +0.25% | MAE: 0.06%
[SIG_MR_LOC_005] 2026-09-09 AXISBANK.NS  SELL @ 1243.80 (Z=+2.99) -> Exit @ 1248.26 (STOP_LOSS     ) | Net: -Rs 45.15 | MFE: +0.01% | MAE: 0.42%
[SIG_MR_LOC_006] 2026-09-09 ICICIBANK.NS SELL @ 1398.00 (Z=+2.94) -> Exit @ 1398.97 (TIME_DECAY_45M) | Net: -Rs 22.33 | MFE: +0.21% | MAE: 0.11%
[SIG_MR_LOC_007] 2026-09-11 HDFCBANK.NS  SELL @  691.45 (Z=+3.01) -> Exit @  693.54 (STOP_LOSS     ) | Net: -Rs 38.26 | MFE: +0.14% | MAE: 0.31%
[SIG_MR_LOC_008] 2026-09-25 BHARTIARTL.NS BUY  @ 1788.20 (Z=-2.84) -> Exit @ 1784.64 (STOP_LOSS     ) | Net: -Rs 31.59 | MFE: +0.12% | MAE: 0.12%
```

---

## 3. Forensic Root Cause: The Friction–Reversion Trap

The forensic audit of the September trades uncovered a fundamental structural impediment to intraday mean reversion in cash equities:

### 1. The Gross Magnitude is Smaller Than Transaction Friction
Look closely at `SIG_MR_LOC_001` and `SIG_MR_LOC_002`:
* In both trades, the mean reversion hypothesis **worked as intended**; the stock reverted all the way back to VWAP and triggered `TARGET_HIT`.
* **BAJFINANCE (SIG 001):** Price moved from ₹1,042.80 to ₹1,040.55 (+0.22% gross move = +₹16.00 gross profit). But total friction (brokerage, STT, exchange fees, GST, spread, slippage) was **₹16.96**. Realized Net P&L: **-₹0.96**.
* **BHARTIARTL (SIG 002):** Price moved from ₹1,861.80 to ₹1,864.19 (+0.13% gross move = +₹9.50 gross profit). Total friction was **₹17.62**. Realized Net P&L: **-₹8.12**.
* **Conclusion:** In liquid large-caps, a $2.5\sigma$ stretch away from VWAP often represents only **15 to 25 basis points** of price distance. Fading this move cannot overcome the **23 basis points** roundtrip friction hurdle under ₹1,500 capital.

### 2. Extreme Extensions Frequently Signal Strong Institutional Trends
* When an Indian heavyweight stock extends beyond $Z \ge +2.8$ (e.g. AXISBANK at $+2.99\sigma$ or HDFCBANK at $+3.01\sigma$), it is driven by persistent institutional order flow (FII block orders, index rebalancing).
* In these cases, the stock did not revert; it continued trending, triggering full stop losses (-₹38.26 to -₹45.15 net).
* **The Asymmetric Trap:**
  * When mean reversion succeeds: **Net P&L is -₹1.00 to -₹8.00** (friction exceeds gain).
  * When mean reversion fails: **Net P&L is -₹35.00 to -₹45.00** (full stop loss + friction).
  * **Expected value is mathematically guaranteed to be negative.**

---

## 4. Synthesis of Three Consecutive Empirical Falsifications

AlphaNSE has now systematically tested three distinct behavioral hypotheses under strict one-shot out-of-sample protocols:

```text
Hypothesis 1 (Phase 10)
Technical Indicators + ML Hurdle
Gross: -₹25.84/trade | Net: -₹40.46/trade
Status: 🔴 REJECTED (Negative-Control Benchmark)
        ↓
Hypothesis 2 (Phase 11)
Regime-Conditioned Opening Range Breakout (ORB)
Gross: -₹5.24/trade | Net: -₹18.37/trade
Status: 🔴 REJECTED (Negative-Control Benchmark)
        ↓
Hypothesis 3 (Phase 12)
Intraday Extreme Mean Reversion (VWAP Deviations)
Gross: -₹8.97/trade | Net: -₹22.24/trade
Status: 🔴 REJECTED (Negative-Control Benchmark)
```

### The Unifying Structural Reality
1. **Intraday Market Microstructure:** Large-cap Indian equities (Reliance, HDFC Bank, TCS, Bharti Airtel) on 5m/15m timeframes possess neither large enough directional follow-through on breakouts to absorb friction, nor wide enough mean-reverting band deviations to profitably fade.
2. **Capitalization Hurdle:** Under ₹1,500 initial capital with 5x leverage (₹7,500 order size), statutory minimum fees + spread + slippage impose a fixed hurdle of **~20 to 25 basis points** per trade. Intraday price displacements on 5m/15m timeframes average only **15 to 40 basis points**.
3. **Safety Status:** Dual switches `LIVE_TRADING=False` and `ALLOW_REAL_ORDERS=False` remain fail-closed. Real-money trading is firmly locked.
