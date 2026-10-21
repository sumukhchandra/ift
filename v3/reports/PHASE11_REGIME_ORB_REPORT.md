# AlphaNSE Phase 11: Regime-Conditioned Opening Range Breakout (ORB) Report

**Date:** 2026-10-02  
**Author:** AlphaNSE Quantitative Research & Platform Engineering  
**Protocol Status:** Executed under Strict Non-Negotiable One-Shot Evaluation Protocol  
**Safety Gate Status:** `LIVE_TRADING=False` | `ALLOW_REAL_ORDERS=False` (Strictly Enforced)

---

## Executive Summary

Phase 11 evaluated the **Market Behavior Hypothesis**:
> *Does early-session price expansion (09:15–09:45 IST) conditioned on broad market regime (NIFTY 50 Macro Trend + Morning Direction) produce persistent intraday directional drift sufficient to overcome realistic transaction friction?*

Following the non-negotiable research rule, the hypothesis and exit architectures were evaluated strictly on the **Research Set (June 29 – August 31, 2026)**, the best parameter set was frozen, and evaluated **EXACTLY ONCE** out-of-sample on the **Locked September Test Set (September 1 – 25, 2026)** with full BASE execution friction (slippage, spread, and statutory taxes on ₹1,500 capital / ₹7,500 purchasing power).

### Definitive Phase 11 Verdict
**HYPOTHESIS FALSIFIED & REJECTED AS POSITIVE TRADING EDGE.**

| Metric | Research Set (V3 Frozen) | Locked September Test Set | Status |
|---|---:|---:|:---:|
| **Trades Evaluated** | 38 | 19 | Verified Out-of-Sample |
| **Win Rate** | 18.4% | **21.1%** | (4 Wins / 15 Losses) |
| **Gross Expectancy** | -₹10.61/trade | **-₹5.24/trade** | **Negative Edge** |
| **Transaction Friction (BASE)** | ₹12.81/trade | **₹13.13/trade** | 88 bps of capital |
| **Net Expectancy** | -₹23.42/trade | **-₹18.37/trade** | **Loss per Trade** |
| **Profit Factor** | 0.42 | **0.64** | Sub-unity (< 1.0) |
| **Maximum Drawdown** | ₹859.04 | **₹312.46** | Capital Erosion |

**Key Conclusion:**
Early-session opening range breakouts (ORB) conditioned on broad market regime do **not** generate positive gross expectancy in large-cap Indian equities. The core gross edge remains **negative (-₹5.24/trade)**, meaning transaction costs are not the sole culprit: the entry mechanism itself suffers from systematic adverse selection.

---

## 1. Research Set Architecture & Parameter Freeze (June 29 – Aug 31)

On the 46 trading days of the Research Set, three exit architectures were ablated across 38 regime-aligned breakout signals:

| Variant | Logic | Trades | Win Rate | Gross Exp. | Friction | Net Exp. | Profit Factor | Max DD |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **V1_EOD** | Hold to 15:15 IST Square-Off | 38 | 31.6% | -₹10.74 | ₹12.90 | -₹23.65 | 0.62 | ₹895.84 |
| **V2_FIXED_BRACKET** | 1.0x ATR SL / 2.0x ATR TP | 38 | 26.3% | -₹11.37 | ₹13.03 | -₹24.40 | 0.42 | ₹903.66 |
| **V3_E5_HYBRID** (FROZEN) | Anti-Chop @ 60m + BE Lock + ATR Trail | 38 | 18.4% | **-₹10.61** | ₹12.81 | **-₹23.42** | 0.42 | **₹859.04** |

**Selection Rationale:**
`V3_E5_HYBRID` achieved the lowest net loss per trade (-₹23.42) and lowest maximum drawdown (₹859.04) by pruning stagnant trades via anti-chop time-stops. In accordance with protocol, `V3_E5_HYBRID` was **frozen without modification** for the locked September test.

---

## 2. Locked September Out-of-Sample Performance (September 1 – 25)

The frozen configuration was executed once against the 410 fifteen-minute bars (19 trading sessions) of the locked September test set.

### Equity Progression & P&L Summary
* **Total P&L Generated:** -₹348.97 on ₹1,500 capital (-23.3% return).
* **Gross P&L:** -₹99.50.
* **Total Friction Incurred:** ₹249.47.
* **Expectancy:** -₹18.37 net loss per trade.

### Complete Trade Forensics Log
```text
[SIG_LOC_001] 2026-09-01 BAJFINANCE.NS SELL @ 1051.50 -> Exit @ 1054.30 (ANTI_CHOP_60M_TIMEOUT ) | Net: -Rs 36.53 | MFE: +0.05% | MAE: 0.33%
[SIG_LOC_002] 2026-09-01 HDFCBANK.NS  SELL @  700.10 -> Exit @  703.02 (STOP_LOSS             ) | Net: -Rs 48.86 | MFE: +0.05% | MAE: 0.40%
[SIG_LOC_005] 2026-09-02 BHARTIARTL.NS SELL @ 1861.20 -> Exit @ 1860.30 (ANTI_CHOP_60M_TIMEOUT ) | Net: -Rs 14.07 | MFE: +0.33% | MAE: 0.07%
[SIG_LOC_007] 2026-09-02 SBIN.NS      SELL @ 1022.30 -> Exit @ 1024.99 (STOP_LOSS             ) | Net: -Rs 36.53 | MFE: +0.02% | MAE: 0.21%
[SIG_LOC_011] 2026-09-04 TCS.NS       SELL @ 2325.80 -> Exit @ 2305.75 (15:15_EOD_SQUAREOFF   ) | Net: +Rs 42.81 | MFE: +1.00% | MAE: 0.18%
[SIG_LOC_008] 2026-09-04 BHARTIARTL.NS SELL @ 1860.50 -> Exit @ 1865.01 (STOP_LOSS             ) | Net: -Rs 36.64 | MFE: +0.08% | MAE: 0.34%
[SIG_LOC_017] 2026-09-07 RELIANCE.NS  SELL @ 1316.20 -> Exit @ 1320.23 (STOP_LOSS             ) | Net: -Rs 36.16 | MFE: +0.20% | MAE: 0.25%
[SIG_LOC_019] 2026-09-07 TATACAP.NS   SELL @  368.20 -> Exit @  369.46 (STOP_LOSS             ) | Net: -Rs 43.24 | MFE: +0.12% | MAE: 0.34%
[SIG_LOC_023] 2026-09-08 BHARTIARTL.NS SELL @ 1833.50 -> Exit @ 1835.31 (ANTI_CHOP_60M_TIMEOUT ) | Net: -Rs 25.00 | MFE: +0.19% | MAE: 0.05%
[SIG_LOC_025] 2026-09-08 ICICIBANK.NS SELL @ 1411.60 -> Exit @ 1411.55 (ANTI_CHOP_60M_TIMEOUT ) | Net: -Rs 19.80 | MFE: +0.15% | MAE: 0.11%
[SIG_LOC_028] 2026-09-10 HDFCBANK.NS  SELL @  687.20 -> Exit @  687.76 (ANTI_CHOP_60M_TIMEOUT ) | Net: -Rs 24.60 |余额: MFE: +0.14% | MAE: 0.26%
[SIG_LOC_030] 2026-09-10 TCS.NS       SELL @ 2196.70 -> Exit @ 2199.62 (ANTI_CHOP_60M_TIMEOUT ) | Net: -Rs 25.73 | MFE: +0.28% | MAE: 0.08%
[SIG_LOC_031] 2026-09-11 RELIANCE.NS  SELL @ 1258.40 -> Exit @ 1258.84 (ANTI_CHOP_60M_TIMEOUT ) | Net: -Rs 19.79 | MFE: +0.41% | MAE: 0.02%
[SIG_LOC_033] 2026-09-15 BAJFINANCE.NS SELL @ 1021.00 -> Exit @ 1012.63 (TAKE_PROFIT           ) | Net: +Rs 39.90 | MFE: +0.91% | MAE: 0.05%
[SIG_LOC_038] 2026-09-15 SBIN.NS      SELL @  985.50 -> Exit @  980.27 (TAKE_PROFIT           ) | Net: +Rs 20.06 | MFE: +0.60% | MAE: 0.05%
[SIG_LOC_042] 2026-09-16 TATACAP.NS   SELL @  348.00 -> Exit @  349.95 (STOP_LOSS             ) | Net: -Rs 58.19 | MFE: +0.19% | MAE: 0.50%
[SIG_LOC_041] 2026-09-16 INFY.NS      SELL @ 1070.10 -> Exit @ 1063.66 (TAKE_PROFIT           ) | Net: +Rs 26.30 | MFE: +0.80% | MAE: 0.05%
[SIG_LOC_047] 2026-09-18 RELIANCE.NS  SELL @ 1240.80 -> Exit @ 1242.94 (ANTI_CHOP_60M_TIMEOUT ) | Net: -Rs 32.28 | MFE: +0.19% | MAE: 0.10%
[SIG_LOC_046] 2026-09-18 ICICIBANK.NS SELL @ 1344.50 -> Exit @ 1345.14 (ANTI_CHOP_60M_TIMEOUT ) | Net: -Rs 20.64 | MFE: +0.10% | MAE: 0.08%
```

---

## 3. Forensic Root Cause: The Mechanics of ORB Failure

Why did Regime-Conditioned ORB fail out-of-sample?

1. **Exhaustion of the Initial Impulse:**
   * In 15 of 19 trades (78.9%), the Maximum Favorable Excursion (MFE) failed to reach even **+0.45%**.
   * By the time the 30-minute bar closed below the opening range low (09:45–10:15 IST), institutional participants had already positioned, and the move was exhausted.
2. **Mean-Reversion Dynamics:**
   * As proven by our earlier Research-Set cross-sectional test ($k=2, h=1$, Excess IC = **-0.0307**, $p = 0.0039$), short-term momentum in liquid Indian equities reliably mean-reverts over 15–30 minute windows.
   * Breakout entries act as the liquidity counterparty to mean-reverting market makers.
3. **Asymmetric Friction Impact:**
   * The 4 winning trades gained an average of **+₹32.27 net** (+0.83% gross move).
   * The 15 losing trades lost an average of **-₹31.87 net** (-0.24% gross move + ₹13.13 friction).
   * A 21.1% win rate requires a reward-to-risk ratio of at least **3.8:1** to break even, whereas the realized reward-to-risk ratio was only **1.01:1**.

---

## 4. Platform Status & Safety Posture

| Component | Status | Empirical Outcome |
|---|---|---|
| Dual Safety Locks | 🟢 **ACTIVE** | `LIVE_TRADING=False`, `ALLOW_REAL_ORDERS=False` |
| Broker Engine | 🟢 **VERIFIED** | Full statutory costs, spread, slippage accurately computed |
| Strategy Phase 10 | 🔴 **FROZEN / REJECTED** | Indicator breakdown + ML hurdle rejected |
| Strategy Phase 11 | 🔴 **FROZEN / REJECTED** | Regime-conditioned 30m ORB rejected |
| Real-Money Readiness | 🚫 **LOCKED** | **No statistical or economic edge demonstrated** |

**Recommendation:**  
All Phase 11 artifacts are permanently frozen as negative-control benchmarks. Under no circumstances should live execution switches be enabled. Future research must evaluate whether non-breakout regimes (such as multi-day swing holding, volatility compression/expansion, or index calendar anomalies) possess positive expectancy before considering intraday momentum.
