# 🚀 AlphaNSE Strategy V2.2 — Multi-Asset Portfolio Validation Report

**Strategy Architecture:** V2.2 (15m Trend + 5m Mom + 1m Trigger) + Relative Strength Leader Selection  
**Structural Upgrade:** Max **`2`** Concurrent / Sequential Opportunities (Resolving Opportunity Lock)  
**Execution Window:** `09:30 – 12:45 IST` (Strict Cutoff)  
**Target / Stop Loss:** **`+1.50%`** Target / **`-0.75%`** Stop Loss (2.0:1 Reward:Risk)  
**Universe:** 8 Liquid NSE Equities (`HDFCBANK`, `SBIN`, `RELIANCE`, `INFY`, `AXISBANK`, `TATASTEEL`, `ICICIBANK`, `BAJFINANCE`)  
**Execution Broker:** `RealisticSimulatedBroker` (Base Regime: 3 bps spread, 4 bps slippage)  
**Sandbox Limits:** Capital: **`₹1,500.00`** | Max Positions: **`2`** | Leverage: **`1.0x`** | Daily Loss Limit: **`₹30.00`**  

---

## 1. Evolution Matrix: V1 vs V2 vs V2.1 vs V2.2

| Performance Metric | Strategy V1 (1m Scalp) | Strategy V2 (Single Stock) | Strategy V2.1 (1 Pos Leader) | Strategy V2.2 (Max 2 Opps) |
| :--- | :---: | :---: | :---: | :---: |
| **Opportunity Capacity** | 1 Position | 1 Position | 1 Position | **Max 2 Opportunities** |
| **Entry Cutoff Window** | 09:20 - 14:45 | 09:30 - 14:45 | 09:30 - 12:45 | **09:30 - 12:45 IST** |
| **Paper Trades Executed** | 23 | 12 | 6 | **7** |
| **Sample Adequacy (>= 15 Trades)** | PASSED (23 trades) | INSUFFICIENT (12 trades) | INSUFFICIENT (6 trades) | **INSUFFICIENT (7 trades)** |
| **Winning Trades / Losing** | 2W / 21L | 3W / 9L | 1W / 5L | **3W / 4L** |
| **Win Rate (%)** | 8.7% | 25.0% | 16.67% | **42.86%** |
| **Gross Theoretical P&L** | ₹-15.83 | ₹-27.22 | ₹-15.42 | **₹+25.79** |
| **Total Friction Paid** | ₹36.16 | ₹38.79 | ₹18.64 | **₹15.42** |
| **Net Realized P&L** | ₹-51.99 | ₹-66.01 | ₹-34.06 | **₹+10.37** |
| **Net Expectancy / Trade** | ₹-2.26 | ₹-5.50 | ₹-5.68 | **₹+1.48 / trade** |
| **Profit Factor** | 0.26 | 0.57 | 0.57 | **3.01** |
| **Max Drawdown (₹ / %)** | ₹45.60 (3.04%) | ₹73.96 (4.93%) | ₹25.58 (1.71%) | **₹13.82 (0.92%)** |
| **Average Holding Time** | 10.6 mins | 171.2 mins | 208.0 mins | **200.0 mins** |

---

## 2. Decision Tree Evaluation

```text
Strategy V2.2 Portfolio Test
        │
        └── Net Expectancy > 0 BUT Sample < 15 (TENTATIVE POSITIVE)
                │
                ▼
        Continue Forward Paper Trading to Reach >= 15 Trades
```

## 3. Trade-by-Trade Execution Ledger

| # | Symbol | Entry Time | Exit Time | Qty | Gross P&L | Friction | Net P&L | Holding Mins |
| :-: | :---: | :---: | :---: | :-: | :---: | :---: | :---: | :-: |
| 01 | **HDFCBANK** | 2026-09-18 10:50:00.350000 | 2026-09-18 14:07:00.350000 | 1 | ₹+10.35 | ₹1.93 | **₹+8.42** | 197.0m |
| 02 | **TATASTEEL** | 2026-09-18 10:45:00.350000 | 2026-09-18 14:34:00.350000 | 4 | ₹-6.32 | ₹2.03 | **₹-8.35** | 229.0m |
| 03 | **SBIN** | 2026-09-21 09:49:00.350000 | 2026-09-21 15:15:00.350000 | 1 | ₹+1.58 | ₹2.58 | **₹-1.00** | 326.0m |
| 04 | **HDFCBANK** | 2026-09-22 10:08:00.350000 | 2026-09-22 13:00:00.350000 | 1 | ₹-6.52 | ₹1.85 | **₹-8.37** | 172.0m |
| 05 | **TATASTEEL** | 2026-09-23 10:27:00.350000 | 2026-09-23 12:09:00.350000 | 3 | ₹+8.16 | ₹1.51 | **₹+6.65** | 102.0m |
| 06 | **SBIN** | 2026-09-23 12:10:00.350000 | 2026-09-23 15:15:00.350000 | 1 | ₹+1.45 | ₹2.41 | **₹-0.96** | 185.0m |
| 07 | **AXISBANK** | 2026-09-25 10:54:00.350000 | 2026-09-25 14:03:00.350000 | 1 | ₹+17.09 | ₹3.11 | **₹+13.98** | 189.0m |
