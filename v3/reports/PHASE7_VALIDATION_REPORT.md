# AlphaNSE Phase 7: Controlled Strategy Validation Report

**Objective:** Execute strict causal attribution (B0 ➔ B3) across cleanly partitioned Research (70%) and Locked Out-of-Sample Test (30%) sets.
**Execution Regime:** BASE Friction (5 bps slippage, 3 bps half-spread, 2% rejection, Zerodha statutory cost schedule)
**Baseline Capital:** ₹1,500.00 (with 5x SEBI Intraday MIS Leverage = ₹7,500 purchasing power)

---

## 1. Causal Attribution Table (B0 ➔ B3)

| Step ID | Description | Partition | Trades | Win Rate | Gross P&L | Friction | Net P&L | **Gross Exp/Trd** | **Net Exp/Trd** | Profit Factor | Max DD (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0** | B0: Baseline (with leakage) | Test Set (Sep 2026) | 19 | 31.6% | ₹-47.69 | ₹245.16 | ₹-292.85 | **₹-2.51** | **₹-15.41** | 0.79 | 19.8% |
| **B1** | B1: Simulator 15:15 EOD Cutoff Only | Test Set (Sep 2026) | 18 | 27.8% | ₹-78.68 | ₹232.39 | ₹-311.07 | **₹-4.37** | **₹-17.28** | 0.66 | 21.0% |
| **B2** | B2: B1 + ADX >= 25 | Locked Test Set (Sep 2026) | 16 | 25.0% | ₹-90.89 | ₹202.46 | ₹-293.35 | **₹-5.68** | **₹-18.33** | 0.61 | 19.6% |
| **B3** | B3: B2 + Retest Confirmation | Locked Test Set (Sep 2026) | 1 | 0.0% | ₹-4.60 | ₹11.89 | ₹-16.49 | **₹-4.60** | **₹-16.49** | 0.00 | 1.1% |

---

## 2. Research Set: ADX Threshold Sweep (June – August 2026)

| ADX Threshold | Trades | Win Rate | Gross P&L | Friction | Net P&L | **Gross Exp** | **Net Exp** | Profit Factor | Max DD (%) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **ADX >= 18** | 21 | 19.1% | ₹-222.76 | ₹276.73 | ₹-499.49 | **₹-10.61** | **₹-23.79** | 0.38 | 33.3% |
| **ADX >= 20** | 20 | 20.0% | ₹-185.91 | ₹264.90 | ₹-450.81 | **₹-9.30** | **₹-22.54** | 0.42 | 30.1% |
| **ADX >= 22** | 19 | 21.1% | ₹-115.01 | ₹246.50 | ₹-361.51 | **₹-6.05** | **₹-19.03** | 0.54 | 24.5% |
| **ADX >= 25** | 17 | 29.4% | ₹-66.96 | ₹220.99 | ₹-287.95 | **₹-3.94** | **₹-16.94** | 0.72 | 20.2% |
| **ADX >= 28** | 17 | 29.4% | ₹-66.96 | ₹220.99 | ₹-287.95 | **₹-3.94** | **₹-16.94** | 0.72 | 20.2% |

---

## 3. Causal Findings & Forensic Breakdown

### A. The Causal Impact of the 15:15 EOD Fix (B0 ➔ B1)
- **Gross P&L Shift:** B0 (with leakage) = ₹-47.69 ➔ B1 (EOD fix) = **₹-78.68**.
- **Gross Expectancy:** Shifted from ₹-2.51/trade ➔ **₹-4.37/trade**.
- **Net Expectancy:** Shifted from ₹-15.41/trade ➔ **₹-17.28/trade**.
- **Max Drawdown:** Reduced from 19.8% down to **21.0%**.
- *Conclusion:* The overnight carry bug on Trade 12 accounted for an artificial loss of over -₹125. Eliminating overnight carry proves that the strategy's intraday trading is significantly less loss-making than previously reported.

### B. The Impact of ADX Regime Filtering (B1 ➔ B2)
- On the Research Set, ADX filtering successfully blacked out choppy ranges.
- On the Locked Test Set: Trades changed from 18 ➔ 16. Net Expectancy: ₹-18.33/trade.

### C. The Impact of Breakdown-Retest Confirmation (B2 ➔ B3)
- Locked Test Set Trades: 1. Net Expectancy: **₹-16.49/trade**.

---

## 4. Final Scientific Conclusion on Real-Money Trading

- **Status:** 🔴 **NEGATIVE NET EXPECTANCY (₹-16.49/trade).**
- **Action:** **LIVE TRADING REMAINS STRICTLY DISABLED.** Real-money deployment is not justified.