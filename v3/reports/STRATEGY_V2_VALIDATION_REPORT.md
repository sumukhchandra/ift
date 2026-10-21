# 🚀 AlphaNSE Strategy V2 — Multi-Timeframe Trend & Momentum Audit

**Strategy Type:** Multi-Timeframe (15m Trend + 5m Momentum + 1m Volume Trigger)  
**Target / Stop Loss:** **`+1.50%`** Target / **`-0.75%`** Stop Loss (2.0:1 Reward:Risk)  
**Execution Mode:** `RealisticSimulatedBroker` (Base Friction: 3 bps spread, 4 bps slippage)  
**Gatekeeper:** `EdgeFrictionGate` (Required: $\text{Gross Edge} > \text{Friction} + \text{Safety Margin}$)  
**Capital Sandbox:** ₹1,500 Max Capital | Max 1 Position | Zero Leverage | No Shorts | ₹30 Daily Loss Limit  

---

## 1. Cross-Asset Performance Comparison Matrix

| Performance Metric | INFY | SBIN | HDFCBANK | RELIANCE | Combined Portfolio |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Signals Generated** | 0 | 4 | 4 | 4 | 12 |
| **Edge Gate Accepted** | 0 | 4 | 4 | 4 | 12 |
| **Paper Trades Executed** | 0 | 4 | 4 | 4 | **12** |
| **Win Rate (%)** | 0.0% | 25.0% | 50.0% | 0.0% | **25.0%** |
| **Gross Theoretical P&L** | ₹+0.00 | ₹+1.40 | ₹+4.08 | ₹-32.70 | **₹-27.22** |
| **Spread Cost Paid** | ₹0.00 | ₹2.40 | ₹3.52 | ₹2.96 | ₹8.88 |
| **Adverse Slippage** | ₹0.00 | ₹3.80 | ₹5.60 | ₹4.74 | ₹14.14 |
| **Brokerage & Taxes** | ₹0.00 | ₹4.24 | ₹6.26 | ₹5.27 | ₹15.77 |
| **Total Friction Paid** | ₹0.00 | ₹10.44 | ₹15.38 | ₹12.97 | **₹38.79** |
| **Net Realized P&L** | ₹+0.00 | ₹-9.04 | ₹-11.30 | ₹-45.67 | **₹-66.01** |
| **Net Expectancy / Trade** | ₹+0.00 | ₹-2.26 | ₹-2.82 | ₹-11.42 | **₹-5.50** |
| **Profit Factor** | 0.0 | 1.17 | 1.2 | 0.03 | **0.57** |
| **Max Drawdown (₹ / %)** | ₹0.0 | ₹13.95 | ₹31.69 | ₹39.59 | ₹73.96 (4.9%) |
| **Avg Holding Time** | 0.0m | 161.2m | 181.2m | 171.2m | 171.2m |

---

## 2. Head-to-Head Comparison: V1 (Micro-Momentum) vs V2 (Multi-Timeframe Trend)

| Feature / Metric | Strategy V1 (1m EMA Crossover) | Strategy V2 (15m Trend + 5m Mom + 1m Trigger) |
| :--- | :---: | :---: |
| **Higher Timeframe Filter** | None (Noise prone) | **15m EMA 10/30 Alignment** |
| **Target / Stop Geometry** | +0.85% / -0.40% | **+1.50% / -0.75% (2.0:1 R:R)** |
| **Hurdle Clearance Room** | ~0.60% net room | **~1.25% net headroom over friction** |
| **Sample Adequacy (>= 15 Trades)** | FAILED (10 trades in 3 sessions) | INSUFFICIENT (12 trades) |
| **Net Expectancy / Trade** | -₹4.18 / trade | **₹-5.50 / trade** |
