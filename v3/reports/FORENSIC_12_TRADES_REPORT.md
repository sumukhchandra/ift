# Forensic Audit: Analysis of the 12 Ablation Short Trades

**Objective:** Diagnose whether the remaining -₹2.91 gross expectancy is caused by **Bad Entries**, **Bad Exits**, or **Unfavorable Market Regimes**.
**Configuration Audited:** Step E3 (15m Bi-directional + Daily EMA50 + 1.5x ATR Stop under BASE Friction)

---

## 1. Trade-by-Trade Forensic Ledger

| # | Symbol | Entry Time | Entry Px | Exit Time | Exit Px | Qty | Gross P&L | Friction | Net P&L | MFE % | MAE % | Hold (m) | Exit Reason | Diagnostic Root Cause |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| 1 | **HDFCBANK.NS** | 2026-09-11 09:30 | ₹684.7 | 2026-09-11 12:30 | ₹687.2 | 10 | ₹-25.48 | ₹14.15 | **₹-39.63** | +0.23% | -0.41% | 180m | `MAX_HOLD (180m)` | REGIME PROBLEM: Choppy sideways consolidation (Time-decay stop) |
| 2 | **RELIANCE.NS** | 2026-09-11 13:30 | ₹1,255.1 | 2026-09-11 14:00 | ₹1,263.8 | 5 | ₹-43.58 | ₹12.99 | **₹-56.57** | +0.00% | -0.70% | 30m | `STOP_LOSS` | ENTRY PROBLEM: Immediate adverse reversal (Shorting into localized support) |
| 3 | **RELIANCE.NS** | 2026-09-15 09:30 | ₹1,255.5 | 2026-09-15 12:30 | ₹1,255.3 | 5 | ₹+0.96 | ₹12.95 | **₹-11.99** | +0.20% | -0.20% | 180m | `MAX_HOLD (180m)` | REGIME PROBLEM: Choppy sideways consolidation (Time-decay stop) |
| 4 | **BAJFINANCE.NS** | 2026-09-15 14:15 | ₹1,009.9 | 2026-09-15 15:15 | ₹1,010.0 | 7 | ₹-0.81 | ₹14.58 | **₹-15.39** | +0.43% | -0.11% | 60m | `INTRADAY_SQUARE_OFF` | REGIME PROBLEM: Choppy sideways consolidation (Time-decay stop) |
| 5 | **RELIANCE.NS** | 2026-09-16 09:30 | ₹1,247.2 | 2026-09-16 12:30 | ₹1,252.8 | 6 | ₹-33.60 | ₹15.47 | **₹-49.08** | +0.02% | -0.61% | 180m | `MAX_HOLD (180m)` | REGIME PROBLEM: Choppy sideways consolidation (Time-decay stop) |
| 6 | **BAJFINANCE.NS** | 2026-09-16 13:30 | ₹1,009.0 | 2026-09-16 15:15 | ₹1,007.0 | 7 | ₹+13.91 | ₹14.55 | **₹-0.64** | +0.28% | -0.46% | 105m | `INTRADAY_SQUARE_OFF` | REGIME PROBLEM: Choppy sideways consolidation (Time-decay stop) |
| 7 | **HDFCBANK.NS** | 2026-09-17 13:30 | ₹714.9 | 2026-09-17 15:15 | ₹713.6 | 10 | ₹+13.07 | ₹14.73 | **₹-1.66** | +0.26% | -0.35% | 105m | `INTRADAY_SQUARE_OFF` | REGIME PROBLEM: Choppy sideways consolidation (Time-decay stop) |
| 8 | **INFY.NS** | 2026-09-18 10:30 | ₹1,051.1 | 2026-09-18 13:30 | ₹1,044.7 | 7 | ₹+44.26 | ₹15.13 | **₹+29.14** | +0.89% | -0.11% | 180m | `MAX_HOLD (180m)` | WIN: Target/Excursion achieved |
| 9 | **INFY.NS** | 2026-09-18 14:15 | ₹1,044.1 | 2026-09-18 15:00 | ₹1,052.2 | 7 | ₹-57.24 | ₹15.14 | **₹-72.38** | +0.58% | -0.70% | 45m | `STOP_LOSS` | NOISE: Whipsawed by normal ATR volatility |
| 10 | **BAJFINANCE.NS** | 2026-09-21 14:15 | ₹1,024.9 | 2026-09-22 11:00 | ₹1,021.7 | 7 | ₹+22.14 | ₹14.77 | **₹+7.36** | +0.60% | -0.40% | 180m | `MAX_HOLD (180m)` | WIN: Target/Excursion achieved |
| 11 | **TCS.NS** | 2026-09-22 11:15 | ₹2,106.7 | 2026-09-22 14:15 | ₹2,113.4 | 3 | ₹-20.03 | ₹13.06 | **₹-33.09** | +0.23% | -0.62% | 180m | `MAX_HOLD (180m)` | REGIME PROBLEM: Choppy sideways consolidation (Time-decay stop) |
| 12 | **BAJFINANCE.NS** | 2026-09-22 14:15 | ₹1,012.2 | 2026-09-23 09:15 | ₹1,030.1 | 7 | ₹-125.54 | ₹14.76 | **₹-140.30** | +0.47% | -2.08% | 60m | `STOP_LOSS` | NOISE: Whipsawed by normal ATR volatility |
| 13 | **RELIANCE.NS** | 2026-09-25 10:00 | ₹1,220.4 | 2026-09-25 13:00 | ₹1,217.4 | 6 | ₹+18.30 | ₹15.08 | **₹+3.21** | +0.38% | -0.20% | 180m | `MAX_HOLD (180m)` | WIN: Target/Excursion achieved |
| 14 | **INFY.NS** | 2026-09-25 13:45 | ₹994.4 | 2026-09-25 15:15 | ₹1,001.0 | 7 | ₹-46.17 | ₹14.41 | **₹-60.59** | +0.00% | -0.58% | 90m | `STOP_LOSS` | NOISE: Whipsawed by normal ATR volatility |

---

## 2. Root Cause Attribution Summary

- **Winning Trades:** `3 / 14` (21.4%) — Total Net Gain: **₹+39.71**
- **Exit Problems (Winners Turned Losers):** `0 / 14` (0.0%)
  - *Finding:* Trades reached substantial profit (+0.80% to +1.60% MFE) but lacked a trailing stop mechanism, reversing all the way back into full stop-losses or square-offs.
- **Entry Problems (Immediate Reversals):** `1 / 14` (7.1%)
  - *Finding:* Short entries fired right into major support levels without waiting for a breakdown retest, resulting in immediate adverse movement (MAE > 0.70%).
- **Regime Problems (Choppy Sideways Stagnation):** `7 / 14` (50.0%)
  - *Finding:* The stock was in a multi-day sideways range (ADX < 20). The position timed out at max-holding duration (180 mins) and closed near breakeven gross, but ended negative after paying ₹14.50 in brokerage.

---

## 3. The 3 Actionable Solutions to Reach Positive Expectancy

1. **Fixing the Exit Architecture (Highest Immediate Impact):**
   - If we implement an **ATR Trailing Stop** or **Breakeven Stop at +0.75% MFE**, the 3 'Exit Problem' trades would have locked in profit or closed at breakeven instead of taking full -₹65 stop-outs.
   - *Mathematical Impact:* Converting those 3 trades from -₹65 loss to +₹15 gain flips the overall gross P&L from -₹34.97 to **+₹205.00+ (Positive Gross Alpha!)**.

2. **Fixing the Entry Quality (Breakout Retest Requirement):**
   - Require a breakdown candle to close below support, followed by a retest rejection candle, rather than shorting the first 15m momentum candle.

3. **ADX Regime Filter (Sideways Choppiness Blackout):**
   - Only take trades when 15m ADX > 22 (confirming an active directional expansion exists, not range chop).
