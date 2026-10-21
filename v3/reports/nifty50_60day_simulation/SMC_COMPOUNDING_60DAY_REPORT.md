# 🚀 NIFTY 50 60-Day Compounding Simulation Report: SMC 4-Conf + 9:20 Straddle
**Strategy:** `SMC 4-Confirmation + 9:20 Straddle (Compounding Mode)` | **Instrument:** `^NSEI (NIFTY 50 Index)` | **Days:** `60 Sessions`

> 🎯 **Compounding Multiplier:** Starting with **`₹10,000.00`**, geometric compounding grew the account to **`₹43,874.14`** (**`+338.74% ROI`**) vs `₹24,584.87` on fixed sizing (**`2.32x alpha`**).

## 1. Key Performance Comparison: Compounding vs Fixed Sizing

| Metric | Fixed Sizing (No Reinvestment) | **Compounding Sizing (Reinvesting Profits)** | Compounding Edge |
| :--- | :---: | :---: | :---: |
| **Starting Capital** | ₹10,000.00 | **₹10,000.00** | — |
| **Ending Capital** | ₹24,584.87 | **₹43,874.14** | **+₹19,289.27** |
| **Total Net Profit** | ₹14,584.87 | **₹33,874.14** | **+2.32x More Profit** |
| **Net Return (ROI)** | +145.85% | **+338.74%** | **+192.89%** |
| **Win Rate** | 74.5% | **74.5%** | 35 Wins / 12 Losses |
| **5% Daily Target Hits** | 24 sessions | **24 sessions (40.0%)** | Daily Compounding Lock |
| **Max Drawdown** | 0.93% | **2.51%** | Strict 2% Daily Circuit Breaker |
| **Sharpe Ratio** | 9.00 | **21.17** | Institutional Grade |

---

## 2. Daily Compounding Mechanics (How 5% Daily Lock Works)

1. **Dynamic Position Sizing:** As capital grows from ₹10,000 → ₹15,000 → ₹25,000+, position sizing automatically scales using 95% of the updated equity.
2. **5.0% Daily Target Lock:** When the day's net gain reaches **+5.0%** (e.g. via SMC 1:2.5 RR runner or 9:20 straddle theta decay), the engine triggers the **Compounding Lock**: positions are squared off and trading ceases for that session, eliminating afternoon giveback.
3. **2.0% Circuit Breaker:** On adverse gap/breakout days, daily losses are strictly capped at 2.0%, protecting the compounded curve from drawdowns.

---

## 3. Sample Day-by-Day Compounded Progression (Recent 20 Sessions)

| Day # | Date | Day | Starting Equity | Action / Mode | Daily Net (₹) | Daily Return | 5% Target Hit? | **Ending Compounded Equity** |
| :---: | :---: | :--- | :---: | :--- | :---: | :---: | :---: | :---: |
| #41 | `2026-08-27` | Thu | ₹22,287.29 | `9:20_SHORT_STRADDLE` | ₹+808.84 | +3.63% | ✅ Win | **₹23,096.13** |
| #42 | `2026-08-28` | Fri | ₹23,096.13 | `9:20_SHORT_STRADDLE` | ₹+1,154.81 | +5.00% | 🎯 YES (+5%) | **₹24,250.94** |
| #43 | `2026-08-31` | Mon | ₹24,250.94 | `9:20_SHORT_STRADDLE` | ₹+1,212.55 | +5.00% | 🎯 YES (+5%) | **₹25,463.48** |
| #44 | `2026-09-01` | Tue | ₹25,463.48 | `9:20_SHORT_STRADDLE` | ₹+924.10 | +3.63% | ✅ Win | **₹26,387.59** |
| #45 | `2026-09-02` | Wed | ₹26,387.59 | `HOLD_CASH` | ₹+0.00 | +0.00% | ⚪ Flat | **₹26,387.59** |
| #46 | `2026-09-03` | Thu | ₹26,387.59 | `9:20_SHORT_STRADDLE` | ₹+1,319.38 | +5.00% | 🎯 YES (+5%) | **₹27,706.97** |
| #47 | `2026-09-04` | Fri | ₹27,706.97 | `9:20_SHORT_STRADDLE` | ₹+1,385.35 | +5.00% | 🎯 YES (+5%) | **₹29,092.31** |
| #48 | `2026-09-07` | Mon | ₹29,092.31 | `9:20_SHORT_STRADDLE` | ₹+1,454.62 | +5.00% | 🎯 YES (+5%) | **₹30,546.93** |
| #49 | `2026-09-08` | Tue | ₹30,546.93 | `9:20_SHORT_STRADDLE` | ₹+1,527.35 | +5.00% | 🎯 YES (+5%) | **₹32,074.28** |
| #50 | `2026-09-09` | Wed | ₹32,074.28 | `9:20_SHORT_STRADDLE` | ₹+1,603.71 | +5.00% | 🎯 YES (+5%) | **₹33,677.99** |
| #51 | `2026-09-10` | Thu | ₹33,677.99 | `9:20_SHORT_STRADDLE` | ₹+1,683.90 | +5.00% | 🎯 YES (+5%) | **₹35,361.89** |
| #52 | `2026-09-11` | Fri | ₹35,361.89 | `HOLD_CASH` | ₹+0.00 | +0.00% | ⚪ Flat | **₹35,361.89** |
| #53 | `2026-09-15` | Tue | ₹35,361.89 | `HOLD_CASH` | ₹+0.00 | +0.00% | ⚪ Flat | **₹35,361.89** |
| #54 | `2026-09-16` | Wed | ₹35,361.89 | `9:20_SHORT_STRADDLE` | ₹+1,283.33 | +3.63% | ✅ Win | **₹36,645.22** |
| #55 | `2026-09-17` | Thu | ₹36,645.22 | `9:20_SHORT_STRADDLE` | ₹+1,329.91 | +3.63% | ✅ Win | **₹37,975.13** |
| #56 | `2026-09-18` | Fri | ₹37,975.13 | `9:20_SHORT_STRADDLE` | ₹+1,898.76 | +5.00% | 🎯 YES (+5%) | **₹39,873.88** |
| #57 | `2026-09-21` | Mon | ₹39,873.88 | `9:20_SHORT_STRADDLE` | ₹+1,993.69 | +5.00% | 🎯 YES (+5%) | **₹41,867.58** |
| #58 | `2026-09-22` | Tue | ₹41,867.58 | `SMC_BEARISH_REVERSAL` | ₹-82.68 | -0.20% | ❌ Loss | **₹41,784.89** |
| #59 | `2026-09-23` | Wed | ₹41,784.89 | `9:20_SHORT_STRADDLE` | ₹+2,089.24 | +5.00% | 🎯 YES (+5%) | **₹43,874.14** |
| #60 | `2026-09-24` | Thu | ₹43,874.14 | `HOLD_CASH` | ₹+0.00 | +0.00% | ⚪ Flat | **₹43,874.14** |

*Full 60-day day-by-day record saved in [`SMC_COMPOUNDING_60DAY_DAY_BY_DAY.csv`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v3/reports/nifty50_60day_simulation/SMC_COMPOUNDING_60DAY_DAY_BY_DAY.csv)*
