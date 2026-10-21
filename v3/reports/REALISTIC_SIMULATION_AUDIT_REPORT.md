# 🔬 AlphaNSE V3 — Realistic Execution Simulation & Friction Audit

**Execution Engine:** `RealisticSimulatedBroker` (Air-Gapped / Zero Order Capability)  
**Asset Replayed:** `INFY` (2,166 1-Minute Historical Bars)  
**Sandbox Constraints:** Capital: **`₹1,500.00`** | Max Positions: **`1`** | Daily Loss Limit: **`₹30.00`**  
**Friction Modeled:** Bid/Ask Spread, Volatility-Adjusted Slippage, Statutory Taxes (STT/GST), Brokerage  

---

## 1. Multi-Scenario Stress Test Matrix

| Performance Metric | Optimistic Scenario | Base Scenario | Conservative Scenario | Severe Scenario |
| :--- | :---: | :---: | :---: | :---: |
| **Total Trades Executed** | 23 | 23 | 18 | 6 |
| **Winning Trades / Losing Trades** | 2W / 21L | 0W / 23L | 0W / 18L | 0W / 6L |
| **Win Rate (%)** | 8.7% | 0.0% | 0.0% | 0.0% |
| **Gross Theoretical P&L** | ₹-15.83 | ₹-40.92 | ₹-92.69 | ₹-100.84 |
| **Spread Cost Paid** | ₹+7.06 | ₹+14.14 | ₹+22.06 | ₹+14.76 |
| **Slippage Impact Paid** | ₹+4.07 | ₹+22.18 | ₹+70.63 | ₹+85.78 |
| **Brokerage Fees** | ₹+14.14 | ₹+14.15 | ₹+11.06 | ₹+3.69 |
| **Statutory Taxes (STT/GST/SEBI)** | ₹+10.89 | ₹+10.89 | ₹+8.49 | ₹+2.84 |
| **Total Friction Paid** | ₹+36.16 | ₹+61.36 | ₹+112.24 | ₹+107.07 |
| **Net Realized P&L** | ₹-51.99 | ₹-102.28 | ₹-204.93 | ₹-207.91 |
| **Average Trade (Net)** | ₹-2.26 | ₹-4.45 | ₹-11.38 | ₹-34.65 |
| **Median Trade (Net)** | ₹-2.49 | ₹-4.69 | ₹-11.71 | ₹-34.58 |
| **Net Expectancy Per Trade** | ₹-2.26 | ₹-4.45 | ₹-11.38 | ₹-34.65 |
| **Profit Factor** | 0.26 | 0.07 | 0.0 | 0.0 |
| **Max Drawdown (₹ / %)** | ₹45.6 (3.04%) | ₹69.58 (4.63%) | ₹112.74 (7.52%) | ₹107.37 (7.16%) |
| **Sharpe Ratio** | -31.82 | -67.54 | -102.06 | -166.19 |
| **Sortino Ratio** | -116.45 | -67.54 | -102.06 | -166.19 |
| **Average Holding Time** | 10.6 mins | 10.6 mins | 10.9 mins | 1.2 mins |
| **Total Turnover** | ₹+47157.21 | ₹+47156.48 | ₹+36840.49 | ₹+12284.84 |
| **Cost / Gross Profit Ratio** | 999.0% | 999.0% | 999.0% | 999.0% |
| **Largest Winner (Net)** | ₹+1.82 | ₹-0.66 | ₹-6.58 | ₹-30.36 |
| **Largest Loss (Net)** | ₹-3.54 | ₹-5.56 | ₹-14.08 | ₹-39.41 |
| **Longest Losing Streak** | 16 trades | 23 trades | 18 trades | 6 trades |
| **Net ROI on ₹1,500 (%)** | -3.47% | -6.82% | -13.66% | -13.86% |

---

## 2. Friction Waterfall: Gross to Net Decay

```text
Gross Theoretical Profit:  ₹  -40.92
  - Bid/Ask Spread Paid:   ₹   14.14
  - Adverse Slippage:      ₹   22.18
  - Brokerage Charges:     ₹   14.15
  - Statutory Taxes:       ₹   10.89
-----------------------------------------
NET REALIZED PROFIT:       ₹ -102.28
Net Expectancy Per Trade:  ₹   -4.45
```

## 3. Scientific Conclusions

1. **The Friction Reality:** Micro-capital trading (₹1,500) suffers disproportionately from minimum fee thresholds and spread crossing.
2. **Expectancy Verdict:** Look strictly at Net Expectancy Per Trade. If Net Expectancy is negative or near-zero under Base/Conservative scenarios, the strategy lacks an out-of-sample statistical edge.
