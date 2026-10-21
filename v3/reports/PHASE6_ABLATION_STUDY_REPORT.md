# AlphaNSE Phase 6: Controlled Ablation Study Report

**Objective:** Empirically isolate the marginal impact of macro trend filters, bi-directional shorting, ATR stops, and profit hurdles.
**Execution Friction:** BASE Regime (5 bps slippage, 3 bps half-spread, 2% rejection, Zerodha statutory cost schedule)
**Baseline Capital:** ₹1,500.00 (with 5x SEBI Intraday MIS Leverage = ₹7,500 purchasing power)
**Methodology:** True walk-forward out-of-sample testing on unseen historical sessions.

---

## 1. Primary Ablation Steps (E1 ➔ E4)

| Step | Configuration | Trades (L/S) | Win Rate | Gross P&L | Friction | Net P&L | **Gross Exp/Trd** | **Net Exp/Trd** | Profit Factor | Max DD (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline (B)** | Candidate B (Baseline) | 7 (7L/0S) | 14.3% | ₹-49.92 | ₹104.31 | ₹-154.23 | **₹-7.13** | **₹-22.03** | 0.71 | 16.1% |
| **Step E1** | E1: B + Daily EMA50 Filter | 0 (0L/0S) | 0.0% | ₹+0.00 | ₹0.00 | ₹+0.00 | **₹+0.00** | **₹+0.00** | 0.00 | 0.0% |
| **Step E2** | E2: E1 + Short Positions | 12 (0L/12S) | 33.3% | ₹-34.97 | ₹174.26 | ₹-209.26 | **₹-2.91** | **₹-17.44** | 0.79 | 13.9% |
| **Step E3 (Best ATR)** | E3: ATR 1.5x Stop | 12 (0L/12S) | 33.3% | ₹-34.97 | ₹174.26 | ₹-209.26 | **₹-2.91** | **₹-17.44** | 0.79 | 13.9% |
| **Step E4 (Best Hurdle)** | E4: Hurdle ₹10 | 12 (0L/12S) | 33.3% | ₹-34.97 | ₹174.26 | ₹-209.26 | **₹-2.91** | **₹-17.44** | 0.79 | 13.9% |

---

## 2. Parameter Sweep Details

### A. ATR Dynamic Stop Sweep (E3 Parameter Analysis)
| ATR Multiplier | Trades | Win Rate | Gross P&L | Total Cost | Net P&L | Gross Exp | Net Exp | Max DD (%) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| E3: ATR 0.75x Stop | 12 | 25.0% | ₹-47.00 | ₹174.30 | ₹-221.31 | ₹-3.92 | **₹-18.44** | 14.8% |
| E3: ATR 1.0x Stop | 12 | 25.0% | ₹-36.79 | ₹174.29 | ₹-211.09 | ₹-3.07 | **₹-17.59** | 14.1% |
| E3: ATR 1.25x Stop | 12 | 33.3% | ₹-49.98 | ₹174.28 | ₹-224.28 | ₹-4.16 | **₹-18.69** | 14.9% |
| E3: ATR 1.5x Stop | 12 | 33.3% | ₹-34.97 | ₹174.26 | ₹-209.26 | ₹-2.91 | **₹-17.44** | 13.9% |
| E3: ATR 2.0x Stop | 12 | 33.3% | ₹-34.97 | ₹174.26 | ₹-209.26 | ₹-2.91 | **₹-17.44** | 13.9% |

### B. Expected Gross Profit Hurdle Sweep (E4 Parameter Analysis)
| Hurdle Level | Trades | Win Rate | Gross P&L | Total Cost | Net P&L | Gross Exp | Net Exp | Max DD (%) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| E4: Hurdle ₹10 | 12 | 33.3% | ₹-34.97 | ₹174.26 | ₹-209.26 | ₹-2.91 | **₹-17.44** | 13.9% |
| E4: Hurdle ₹15 | 12 | 33.3% | ₹-34.97 | ₹174.26 | ₹-209.26 | ₹-2.91 | **₹-17.44** | 13.9% |
| E4: Hurdle ₹20 | 12 | 33.3% | ₹-34.97 | ₹174.26 | ₹-209.26 | ₹-2.91 | **₹-17.44** | 13.9% |
| E4: Hurdle ₹30 | 12 | 33.3% | ₹-34.97 | ₹174.26 | ₹-209.26 | ₹-2.91 | **₹-17.44** | 13.9% |
| E4: Hurdle ₹40 | 12 | 33.3% | ₹-34.97 | ₹174.26 | ₹-209.26 | ₹-2.91 | **₹-17.44** | 13.9% |

---

## 3. Directional Asymmetry: Long vs. Short Expectancy

| Step | Long Trades | Long Net Exp | Short Trades | Short Net Exp |
| :--- | :---: | :---: | :---: | :---: |
| **E2 (Bi-Directional)** | 0 | ₹+0.00 | 12 | ₹-17.44 |
| **E3 (ATR Stop)** | 0 | ₹+0.00 | 12 | ₹-17.44 |
| **E4 (Profit Hurdle)** | 0 | ₹+0.00 | 12 | ₹-17.44 |

---

## 4. Key Takeaways & Scientific Conclusions

1. **Isolated Component Contributions:**
   - **Baseline (Candidate B):** Net Expectancy = ₹-22.03 / trade.
   - **E1 (Macro Daily EMA50):** Net Expectancy = ₹+0.00 / trade.
   - **E2 (+ Shorting):** Net Expectancy = ₹-17.44 / trade.
   - **E3 (+ ATR Stop):** Net Expectancy = ₹-17.44 / trade.
   - **E4 (+ Profit Hurdle):** Net Expectancy = ₹-17.44 / trade.

2. **Is Real-Money Trading Justified?**
   - **Edge Status:** 🔴 Net Expectancy remains negative (₹-17.44/trade). Live trading remains locked.
