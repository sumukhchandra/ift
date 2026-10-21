# 🔬 AlphaNSE Strategy V2.1 — Cross-Asset Leader Portfolio Audit

**Strategy Architecture:** V2.1 Multi-Timeframe (15m Trend + 5m Mom) + Relative Strength Leader Selection  
**Execution Window:** `09:30 – 12:45 IST` (Strict Cutoff: Eliminates late-day 15:15 auction chop)  
**Target / Stop Loss:** **`+1.50%`** Target / **`-0.75%`** Stop Loss (2.0:1 Reward:Risk)  
**Universe:** 8 Liquid NSE Equities within ₹1,500 share price (`HDFCBANK`, `SBIN`, `RELIANCE`, `INFY`, `AXISBANK`, `TATASTEEL`, `ICICIBANK`, `BAJFINANCE`)  
**Execution Broker:** `RealisticSimulatedBroker` (Base Friction: 3 bps spread, 4 bps slippage)  
**Sandbox Limits:** Capital: **`₹1,500.00`** | Max Positions: **`1`** | Leverage: **`0`** | Daily Loss Limit: **`₹30.00`**  

---

## 1. Portfolio Performance Summary

| Performance Metric | Strategy V1 (1m Scalp) | Strategy V2 (Multi-TF Single) | Strategy V2.1 (Leader Portfolio) |
| :--- | :---: | :---: | :---: |
| **Universe Tested** | Single Asset (INFY) | 4 Assets Independent | **8-Asset Cross-Sectional Leader Portfolio** |
| **Entry Window** | 09:20 - 14:45 | 09:30 - 14:45 | **09:30 - 12:45 IST (Strict Cutoff)** |
| **Paper Trades Executed** | 23 | 12 | **6** |
| **Sample Adequacy (>= 15 Trades)** | PASSED (23 trades) | INSUFFICIENT (12 trades) | **INSUFFICIENT (6 trades)** |
| **Winning Trades / Losing** | 2W / 21L | 3W / 9L | **1W / 5L** |
| **Win Rate (%)** | 8.7% | 25.0% | **16.67%** |
| **Gross Theoretical P&L** | ₹-15.83 | ₹-27.22 | **₹-15.42** |
| **Total Friction Paid** | ₹36.16 | ₹38.79 | **₹18.64** |
| **Net Realized P&L** | ₹-51.99 | ₹-66.01 | **₹-34.06** |
| **Net Expectancy / Trade** | ₹-2.26 | ₹-5.50 | **₹-5.68 / trade** |
| **Profit Factor** | 0.26 | 0.57 | **0.57** |
| **Max Drawdown (₹ / %)** | ₹45.60 (3.04%) | ₹73.96 (4.93%) | **₹25.58 (1.71%)** |
| **Average Holding Time** | 10.6 mins | 171.2 mins | **208.0 mins** |

---

## 2. Decision Tree Evaluation

```text
Strategy V2.1 Portfolio Test
        │
        └── Net Expectancy <= 0 (FAILED: ₹-5.68/trade)
                │
                ▼
        DO NOT TRADE LIVE -> Modify Strategy / Structural Iteration
```

## 3. Trade-by-Trade Execution Ledger

| # | Symbol | Entry Time | Exit Time | Qty | Gross P&L | Friction | Net P&L | Holding Mins |
| :-: | :---: | :---: | :---: | :-: | :---: | :---: | :---: | :-: |
| 01 | **TATASTEEL** | 2026-09-18 10:45:00.350000 | 2026-09-18 14:34:00.350000 | 8 | ₹-12.40 | ₹3.83 | **₹-16.23** | 229.0m |
| 02 | **SBIN** | 2026-09-21 09:49:00.350000 | 2026-09-21 15:15:00.350000 | 1 | ₹+1.35 | ₹2.81 | **₹-1.46** | 326.0m |
| 03 | **HDFCBANK** | 2026-09-22 10:08:00.350000 | 2026-09-22 13:00:00.350000 | 1 | ₹-6.56 | ₹1.89 | **₹-8.45** | 172.0m |
| 04 | **TATASTEEL** | 2026-09-23 10:27:00.350000 | 2026-09-23 12:09:00.350000 | 7 | ₹+18.76 | ₹3.79 | **₹+14.97** | 102.0m |
| 05 | **RELIANCE** | 2026-09-23 12:27:00.350000 | 2026-09-23 15:15:00.350000 | 1 | ₹-5.23 | ₹3.16 | **₹-8.39** | 168.0m |
| 06 | **TATASTEEL** | 2026-09-24 09:31:00.350000 | 2026-09-24 13:42:00.350000 | 7 | ₹-11.34 | ₹3.16 | **₹-14.50** | 251.0m |
