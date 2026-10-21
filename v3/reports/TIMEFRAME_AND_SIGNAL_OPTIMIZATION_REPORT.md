# AlphaNSE Phase 6: Timeframe, Regime & Signal Optimization Report

**Objective:** Isolate true positive gross market alpha before testing survival against realistic execution friction.
**Execution Regime:** BASE Friction (5 bps slippage, 3 bps half-spread, 2% rejection, Zerodha statutory cost schedule)
**Baseline Capital:** ₹1,500.00 (with 5x SEBI Intraday MIS Leverage = ₹7,500 purchasing power)

---

## 1. Candidate Comparison Matrix

| Candidate | Timeframe | Trades | Win Rate | Gross P&L | Total Friction | Net P&L | Net ROI | Profit Factor | **Gross Exp/Trd** | **Net Exp/Trd** | Max DD (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **5m Raw Momentum (Control)** | 5min | 15 | 0.0% | ₹-334.93 | ₹216.97 | ₹-551.89 | -36.8% | 0.03 | **₹-22.33** | **₹-36.79** | 36.8% |
| **15m Trend + Volume Filter** | 15min | 7 | 14.3% | ₹-49.92 | ₹104.31 | ₹-154.23 | -10.3% | 0.71 | **₹-7.13** | **₹-22.03** | 16.1% |
| **15m Trend Pullback Reversion** | 15min | 8 | 0.0% | ₹-293.93 | ₹119.12 | ₹-413.03 | -27.5% | 0.00 | **₹-36.74** | **₹-51.63** | 27.5% |
| **60m Structural Momentum** | 60min | 3 | 33.3% | ₹-378.75 | ₹44.24 | ₹-423.00 | -28.2% | 0.07 | **₹-126.25** | **₹-141.00** | 29.1% |

---

## 2. Quantitative Insights & Comparative Analysis

### CAND_A: 5m Raw Momentum (Control) (5min)
- **Gross Alpha Status:** 🔴 NEGATIVE GROSS ALPHA (₹-22.33 / trade)
- **Net Viability Status:** 🔴 DESTROYED BY FRICTION (₹-36.79 / trade)
- **Friction Impact:** Incurred ₹216.97 in friction across 15 trades (average ₹14.46 per trade).
- **Holding Duration:** Average holding duration was 54.3 minutes.

### CAND_B: 15m Trend + Volume Filter (15min)
- **Gross Alpha Status:** 🔴 NEGATIVE GROSS ALPHA (₹-7.13 / trade)
- **Net Viability Status:** 🔴 DESTROYED BY FRICTION (₹-22.03 / trade)
- **Friction Impact:** Incurred ₹104.31 in friction across 7 trades (average ₹14.90 per trade).
- **Holding Duration:** Average holding duration was 109.3 minutes.

### CAND_C: 15m Trend Pullback Reversion (15min)
- **Gross Alpha Status:** 🔴 NEGATIVE GROSS ALPHA (₹-36.74 / trade)
- **Net Viability Status:** 🔴 DESTROYED BY FRICTION (₹-51.63 / trade)
- **Friction Impact:** Incurred ₹119.12 in friction across 8 trades (average ₹14.89 per trade).
- **Holding Duration:** Average holding duration was 105.0 minutes.

### CAND_D: 60m Structural Momentum (60min)
- **Gross Alpha Status:** 🔴 NEGATIVE GROSS ALPHA (₹-126.25 / trade)
- **Net Viability Status:** 🔴 DESTROYED BY FRICTION (₹-141.00 / trade)
- **Friction Impact:** Incurred ₹44.24 in friction across 3 trades (average ₹14.75 per trade).
- **Holding Duration:** Average holding duration was 340.0 minutes.
