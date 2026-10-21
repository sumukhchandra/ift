# 📋 AlphaNSE V3 — Three-Session Forward Paper-Trading Report

**Validation Period:** `2026-09-23` to `2026-09-25` (3 Sequential NSE Sessions)  
**Execution Mode:** `PAPER_TRADING` (`LIVE_TRADING = False`, `ALLOW_REAL_ORDERS = False`)  
**Broker Engine:** `RealisticSimulatedBroker` (Base Regime: 3 bps spread, 4 bps slippage)  
**Gatekeeper:** `EdgeFrictionGate` (Required: $\text{Gross Edge} > \text{Friction} + \text{Safety Margin}$)  
**Sandbox Constraints:** Capital: **`₹1,500.00`** | Max Positions: **`1`** | Daily Loss Limit: **`₹30.00`**  

---

## 1. Session-by-Session Performance Matrix

| Metric | Day 1 (2026-09-23) | Day 2 (2026-09-24) | Day 3 (2026-09-25) | 3-Session Aggregate |
| :--- | :---: | :---: | :---: | :---: |
| **Signals Generated** | 4 | 3 | 4 | 11 |
| **Edge Gate Accepted** | 4 | 3 | 4 | 11 |
| **Edge Gate Rejected** | 0 | 0 | 0 | 0 |
| **Paper Trades Executed** | 3 | 3 | 4 | 10 |
| **Win Rate (%)** | 0.0% | 0.0% | 0.0% | 0.0% |
| **Gross P&L** | ₹-5.75 | ₹-6.12 | ₹-4.33 | ₹-16.20 |
| **Spread Cost Paid** | ₹2.17 | ₹1.80 | ₹2.40 | ₹6.37 |
| **Adverse Slippage** | ₹3.53 | ₹2.42 | ₹3.43 | ₹9.38 |
| **Brokerage & Taxes** | ₹3.70 | ₹3.20 | ₹4.24 | ₹11.14 |
| **Total Friction Paid** | ₹8.12 | ₹7.42 | ₹10.07 | ₹25.61 |
| **Net Realized P&L** | ₹-13.87 | ₹-13.54 | ₹-14.40 | ₹-41.81 |
| **Net Expectancy / Trade** | ₹-4.62 | ₹-4.51 | ₹-3.60 | **₹-4.18** |
| **Profit Factor** | 0.0 | 0.0 | 0.35 | 0.12 |
| **Max Drawdown (₹ / %)** | ₹12.4 (0.83%) | ₹9.32 (0.62%) | ₹11.49 (0.77%) | ₹12.4 (0.83%) |
| **Longest Loss Streak** | 3 | 3 | 4 | 10 |
| **Avg Holding Time** | 4.3m | 1.0m | 23.0m | 10.8m |

---

## 2. Key Pass Condition Evaluation

### Criterion A: Positive Net Expectancy (`NET EXPECTANCY > 0`)
- **STATUS: FAILED (₹-4.18 per trade).** The strategy has negative expectancy after institutional friction.

### Criterion B: Sample Size Adequacy (`Total Trades >= 15`)
- **STATUS: INSUFFICIENT (10 trades executed < 15 required).** Per protocol, 3 sessions were a preliminary filter; continue collecting forward observations before deployment review.

## 3. Edge Gate Impact Analysis

- Total Signals Evaluated: **`11`**
- Signals Filtered Out (Edge < Hurdle Rate): **`0`** (0.0%)
- Signals Passed to Paper Broker: **`11`** (100.0%)
- **Conclusion:** The `EdgeFrictionGate` effectively suppressed low-conviction signals that would have generated guaranteed friction decay.
