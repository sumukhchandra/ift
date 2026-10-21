# AlphaNSE V3 — Historical Baseline Replay Report

> [!WARNING]
> **CLASSIFICATION: HISTORICAL REPLAY / BASELINE**  
> **NOT FRESH VALIDATION**  
> **NOT LIVE PERFORMANCE**  
> **NOT PROFITABILITY PROOF**  
> This replay is strictly an offline engineering sanity check. Session 5 onward constitutes actual fresh forward validation.

## 1. Executive Summary

| Metric | V2 (15m Horizon, ATR Sized) | V3 (60m Horizon, Rupee Net-Edge) |
| :--- | :--- | :--- |
| **Horizon** | 15 minutes (3 bars) | 60 minutes (12 bars) |
| **Total Trades** | 188 trades | 0 trades |
| **Total Gross P&L** | +₹59.20 | ₹0.00 |
| **Total Net P&L** | -₹378.61 | ₹0.00 |
| **Ending Capital** | ₹4,621.39 | ₹5000.00 |
| **Status** | Negative Edge (-₹2.01/trade) | Capital-Preserving Experiment |

## 2. Session-by-Session Breakdown

| Session Date | Trades | Gross P&L (₹) | Net P&L (₹) | Win Rate | Ending Capital (₹) | Mode |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-09-21 | 0 | ₹+0.00 | ₹+0.00 | 0.0% | ₹5000.00 | CASH HELD |
| 2026-09-22 | 0 | ₹+0.00 | ₹+0.00 | 0.0% | ₹5000.00 | CASH HELD |
| 2026-09-23 | 0 | ₹+0.00 | ₹+0.00 | 0.0% | ₹5000.00 | CASH HELD |
| 2026-09-24 | 0 | ₹+0.00 | ₹+0.00 | 0.0% | ₹5000.00 | CASH HELD |

## 3. Engineering Invariants Verified

1. **Zero Lookahead**: Every session retrained exclusively on data <= D-1.
2. **Lunch Blackout**: Zero entries executed between 12:00 and 14:00 IST.
3. **14:25 Entry Cutoff**: Zero entries initiated after 14:25 IST.
4. **Rupee Net-Edge Hurdle**: Sub-hurdle candidates rejected to preserve capital.
5. **V2 Isolation**: V2 code and ledgers completely untouched.
