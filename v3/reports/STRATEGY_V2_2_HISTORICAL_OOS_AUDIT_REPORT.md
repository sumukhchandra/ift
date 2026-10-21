# 🔬 AlphaNSE Strategy V2.2 — Historical Out-of-Sample Replay Audit Report

**Date of Execution:** 2026-10-05  
**Data Window Analyzed:** September 28, 2026 – October 1, 2026 (Sessions 6, 7, 8, 9)  
**Strict Analytic Classification:** **HISTORICAL OUT-OF-SAMPLE REPLAY**  
*(Note: These 1-minute historical candles were ingested and replayed after the fact. They are strictly segregated from real-time live forward paper observations).*

---

## 1. Executive Sample Separation Audit

| Category | Trades ($N$) | Status | Operational Interpretation |
| :--- | :---: | :---: | :--- |
| **Category A: Baseline Historical Replay** | **7** | Complete | Sep 18 – Sep 25, 2026 initial portfolio test |
| **Category A: OOS Historical Replay** | **2** | Complete | Sep 28 – Oct 01, 2026 out-of-sample replay test |
| **Total Category A (Historical / Replay)** | **9** | **N = 9** | Evaluates historical model robustness; **NOT live proof** |
| **Category B: Genuine Live Forward-Paper** | **0** | **INCOMPLETE** | **0 real-time market session trades logged** |

> [!IMPORTANT]
> **Forward-Validation Screening Gate ($N \ge 15–30+$):** **UNSATISFIED.**  
> The 2 new trades generated during the Sep 28–Oct 01 historical replay belong strictly to Category A. They provide valuable out-of-sample stress-testing evidence for the Strategy Audit, but do **NOT** count toward the genuine real-time live forward-paper requirement ($N_{\text{Live}} = 0$).

---

## 2. Historical Out-of-Sample Replay Results (Sep 28 – Oct 01)

### Execution Ledger (Trades #08 & #09)
| # | Symbol | Entry Time | Exit Time | Qty | Entry Px | Exit Px | Gross | Friction | Net P&L | Hold | Exit Trigger |
| :-: | :---: | :---: | :---: | :-: | :---: | :---: | :---: | :---: | :---: | :-: | :--- |
| **08** | **AXISBANK** | 2026-09-30 09:50 | 2026-09-30 12:41 | 1 | ₹1,216.44 | ₹1,233.70 | +₹17.26 | ₹3.34 | **+₹13.92** | 171m | `TAKE_PROFIT_TARGET_HIT (+1.50%)` |
| **09** | **AXISBANK** | 2026-10-01 09:51 | 2026-10-01 12:44 | 1 | ₹1,236.54 | ₹1,226.04 | -₹10.50 | ₹3.11 | **-₹13.61** | 173m | `STOP_LOSS_HIT (-0.79%)` |

* **Session 6 (Sep 28, Mon) & Session 7 (Sep 29, Tue):** **0 trades.** Market leaders did not satisfy all 4 criteria (15m Trend + 5m Momentum + 1m Trigger + RS Leader) simultaneously inside the 09:30–12:45 IST window.
* **Session 8 (Sep 30, Wed):** 1 trade (`AXISBANK` winner: +₹13.92 net).
* **Session 9 (Oct 01, Thu):** 1 trade (`AXISBANK` loser: -₹13.61 net).

---

## 3. Quantitative Scorecard Breakdown

| Metric | Baseline Replay (Sep 18–25) | OOS Replay (Sep 28–Oct 01) | Cumulative Historical (All 9) |
| :--- | :---: | :---: | :---: |
| **Trades ($N$)** | 7 | 2 | **9** |
| **Wins / Losses** | 3W / 4L | 1W / 1L | **4W / 5L** |
| **Win Rate** | 42.86% | 50.00% | **44.44%** |
| **Gross P&L** | +₹25.79 | +₹6.76 | **+₹32.55** |
| **Total Friction Paid** | ₹15.42 | ₹6.45 | **₹21.87** |
| **Friction / Gross Drag** | 59.8% | **95.4%** | **67.2%** |
| **Net Realized P&L** | +₹10.37 | **+₹0.31** | **+₹10.68** |
| **Net Expectancy / Trade**| +₹1.48 | **+₹0.16** | **+₹1.19 / trade** |
| **Profit Factor** | 3.01 | 1.64 | **2.02** |
| **Max Drawdown** | ₹13.82 (0.92%) | ₹14.85 (0.98%) | **₹14.85 (0.99%)** |
| **Avg Holding Time** | 200.0 mins | 172.0 mins | **193.8 mins** |

---

## 4. Deep Forensic & Outlier-Dependence Findings

### 1. Friction Grind is Severe
In the new out-of-sample window, gross profit was **+₹6.76**, but all-in friction (spread + slippage + brokerage + turnover taxes) was **₹6.45**. Friction consumed **95.4%** of gross profit, reducing net P&L to an essentially flat **+₹0.31**.

### 2. High Concentration in a Single Ticker (`AXISBANK`)
* Across the 9 historical trades, `AXISBANK` produced two full target wins:
  * Trade #07: +₹13.98
  * Trade #08: +₹13.92
  * Trade #09: -₹13.61
  * **AXISBANK Net P&L:** **+₹14.29**
* **Performance of all other 7 universe stocks (`HDFCBANK`, `TATASTEEL`, `SBIN`, etc.):**
  * **Net P&L:** **-₹3.61**
* This proves that V2.2's net profitability is currently driven by a single high-beta banking leader.

---

## 5. Live-Readiness Governance Status

```text
Category A (Historical Replay) : N = 9 Trades (Expectancy: +₹1.19/trade | PF: 2.02)
Category B (Live Forward Paper): N = 0 Trades (UNSATISFIED)

LIVE_TRADING                   : False [LOCKED]
ALLOW_REAL_ORDERS              : False [LOCKED]
_is_live_authorized            : False [FAIL-CLOSED]
Real Capital at Risk           : ₹0.00
```

**Approval Verdict:** The strategy remains strictly in **Category B paper-forward validation mode**. No live orders will be authorized.
