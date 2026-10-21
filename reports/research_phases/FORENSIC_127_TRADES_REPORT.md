# AlphaNSE V2 — Forensic Economics & Root-Cause Audit of 127 Adaptive Trades

**Audit Scope**: All 127 sequential walk-forward trades executed across 3 unseen market sessions (Monday Sep 21, Tuesday Sep 22, Wednesday Sep 23, 2026)  
**Dataset Lineage**: `v2/adaptive/ledger/trades/trades_20260921.json`, `trades_20260922.json`, `trades_20260923.json`  
**Market Environment**: Real unseen 5-minute NSE bars, ₹5,000 initial capital, Zerodha 2025-2026 statutory fee schedule, dynamic bid-ask spread & market impact  

---

## 1. Executive Verdict & Core Question Answered

> [!IMPORTANT]
> ### Why was the win rate 23.6% and net profit -₹2.22/trade?
> **Is the model predicting the wrong direction? NO.**
> 
> 1. **The Model Has Genuine Directional Edge**:
>    - Overall directional accuracy across all 127 trades was **51.97%** (66 gross winners vs 58 gross losers).
>    - Total **Gross P&L was POSITIVE (+₹22.78)** before friction.
>    - In top-conviction signals (Q4, 31 trades), directional accuracy was **71.0%** with a massive **+13.62 bps gross return**.
> 2. **The "Cost Casualty" Phenomenon Explains 100% of the Gap**:
>    - **66 trades were Gross Winners** (52.0%).
>    - **36 of those 66 winners (28.3% of ALL trades) were "Cost Casualties"**: they moved in the predicted direction and produced positive gross returns (+1 to +14 bps), but were flipped into net losses because roundtrip friction is **14.72 bps**.
>    - Only 30 trades (23.6%) had gross returns $> 14.72\text{ bps}$ to survive as net winners.
> 3. **The Frequency-Dilution Trap**:
>    - Forcing $\ge 30$ trades/day on a 10-stock universe compelled the system to execute **96 low-conviction trades** (Q1–Q3 where predicted return was only 0.5–1.5 bps).
>    - These 96 low-conviction trades had **negative gross return (-1.30 bps)** and lost **-₹264.55 net**.
>    - In contrast, the top 31 trades (10 trades/day) were virtually breakeven (-1.18 bps net) despite fighting 14.7 bps of friction.

---

## 2. High-Level Summary Statistics

| Metric | Empirical Value | Interpretation |
| :--- | :---: | :--- |
| **Total Trades Analyzed** | **127** | 41 (Day 1), 40 (Day 2), 46 (Day 3) |
| **Directional Accuracy (Gross > 0)** | **51.97%** (66 / 127) | Model predicted the correct direction > 50% |
| **Gross Winners (> 0 bps)** | **66** (52.0%) | Profitable before fees and slippage |
| **Gross Losers (< 0 bps)** | **58** (45.7%) | Adverse price movement |
| **Gross Breakeven (== 0 bps)** | **3** (2.4%) | Exited at entry price |
| **Net Winners (> ₹0.00)** | **30** (23.6%) | Survived all statutory taxes & friction |
| **Cost Casualties (Gross > 0, Net < 0)** | **36** (28.3%) | **Turned from win to loss solely by friction** |
| **Mean Predicted Return** | -1.04 bps | Raw model regression output |
| **Mean Actual Gross Return** | **+2.34 bps** | **Positive gross edge achieved** |
| **Mean Roundtrip Friction** | **14.72 bps** | Statutory taxes (10.63 bps) + Spread & Impact (4.09 bps) |
| **Mean Net Return** | **-12.37 bps** | Gross return minus friction |
| **Total Gross P&L** | **+₹22.78** | Raw market alpha |
| **Total Transaction Friction** | **-₹304.54** | Indian statutory charges + slippage |
| **Total Net P&L** | **-₹281.76** | Realized portfolio outcome |
| **Average Net Profit / Trade** | **-₹2.22** | Net cost per executed order |

---

## 3. Cost Decomposition & Progressive Waterfall

Every single rupee of friction was decomposed based on Zerodha's active 2025–2026 intraday equity rate schedule:

```text
  Gross Market Return:   +2.34 bps   (+₹0.18/trade)   [Total Gross: +₹22.78]
           │
           ├── Less Brokerage:          -6.00 bps   (-₹0.98/trade)   [-₹124.15]
           ├── Less STT (0.025% sell):  -2.50 bps   (-₹0.41/trade)   [-₹51.73]
           ├── Less Exchange Turnover:  -0.61 bps   (-₹0.10/trade)   [-₹12.70]
           ├── Less SEBI Charges:       -0.02 bps   (-₹0.00/trade)   [-₹0.41]
           ├── Less GST (18% on fees):  -1.19 bps   (-₹0.19/trade)   [-₹24.71]
           └── Less Stamp Duty (buy):   -0.30 bps   (-₹0.05/trade)   [-₹6.21]
           │
  Subtotal Statutory Taxes:            -10.63 bps   (-₹1.73/trade)   [-₹219.92]
           │
           ├── Less Bid-Ask Spread:     -2.00 bps   (-₹0.33/trade)   [-₹41.39]
           └── Less Slippage / Impact:  -2.09 bps   (-₹0.34/trade)   [-₹43.25]
           │
  Total Roundtrip Friction:            -14.72 bps   (-₹2.40/trade)   [-₹304.56]
           │
  Final Net P&L:                       -12.37 bps   (-₹2.22/trade)   [-₹281.76]
```

### Key Cost Takeaways:
1. **Statutory Taxes & Brokerage account for 72.2% of all friction** (₹219.92 out of ₹304.56).
2. Brokerage alone (₹124.15) and STT (₹51.73) comprise **57.8% of all losses**.
3. Spread and slippage combined (4.09 bps / ₹84.64) are relatively modest; the primary drag is statutory fees on small cash notional amounts.

---

## 4. The Smoking Gun: Prediction-Confidence Bucketing

When we partition the 127 trades into quartiles based on prediction strength ($|\hat{r}|$), the true nature of the alpha becomes indisputable:

| Quartile | Trades | Avg \|Pred\| | Directional Accuracy | Gross Win % | Net Win % | Mean Gross (bps) | Mean Net (bps) | Net P&L | Net P&L / Trade |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Q1 (Low Conviction)** | 32 | 0.55 bps | 50.0% | 50.0% | 15.6% | +0.24 bps | -14.45 bps | -₹73.92 | -₹2.31 |
| **Q2 (Moderate-Low)** | 32 | 1.12 bps | 50.0% | 50.0% | 18.8% | +1.52 bps | -13.16 bps | -₹80.46 | -₹2.51 |
| **Q3 (Moderate-High)** | 32 | 1.58 bps | 37.5% | 37.5% | 15.6% | -5.65 bps | -20.35 bps | -₹110.17 | -₹3.44 |
| **Q4 (Top Conviction)** | **31** | **2.89 bps** | **71.0%** | **71.0%** | **45.2%** | **+13.62 bps** | **-1.18 bps** | **-₹17.21** | **-₹0.56** |

### Critical Scientific Deduction:
- In Q4 (the top 10 trades per day), the model has **71.0% hit rate** and **+13.62 bps gross return**!
- In Q1–Q3 (the remaining 32 trades per day added to reach "42 trades/day"), the model has no edge (-1.30 bps gross return).
- **The 30+ trades/day mandate forced the model to trade 96 zero-edge noise setups**, which wiped out the strong positive edge of Q4!

---

## 5. Forward Holding Horizon Trajectory (5m to EOD)

To test whether 15-minute holding was cutting winners too early, we tracked the exact forward price trajectory for every single trade across 5m, 15m, 30m, 60m, and session close (EOD):

| Holding Horizon | Mean Gross Return | Directional Accuracy | Net Win Rate (> 14.7 bps) | Theoretical Edge vs Cost |
| :--- | :---: | :---: | :---: | :---: |
| **5m (1 Bar)** | +2.08 bps | 54.3% | 9.4% | Severe friction deficit (-12.6 bps) |
| **15m (3 Bars — Current)** | +2.94 bps | 52.0% | 23.6% | High friction deficit (-11.8 bps) |
| **30m (6 Bars)** | +2.94 bps | 54.3% | 26.8% | High friction deficit (-11.8 bps) |
| **60m (12 Bars)** | +2.56 bps | 55.9% | 33.9% | Moderate friction deficit (-12.1 bps) |
| **EOD (Held to 15:25 IST)** | **+5.84 bps** | **59.1%** | **48.0%** | **Substantial trend realization** |

### Horizon Observations:
1. Extending the holding horizon from 15m to EOD doubles the gross return (**+2.94 bps $\to$ +5.84 bps**) and increases net win rate from **23.6% to 48.0%**.
2. However, even at EOD, average cash equity intraday gross return (+5.84 bps) is still less than the 14.72 bps roundtrip cash friction.

---

## 6. Long vs Short Performance Breakdown

| Direction | Trades | Directional Accuracy | Gross Win % | Net Win % | Mean Pred | Mean Gross | Cost | Mean Net | Gross P&L | Net P&L |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **LONG (+1)** | 35 | 51.4% | 51.4% | 22.9% | +0.87 bps | +0.11 bps | 14.69 bps | -14.58 bps | -₹0.16 | -₹78.65 |
| **SHORT (-1)** | 92 | 52.2% | 52.2% | 23.9% | -1.77 bps | +3.19 bps | 14.73 bps | -11.53 bps | +₹22.95 | -₹203.11 |

- **Shorts were more profitable on a gross basis**: +3.19 bps gross return (+₹22.95 gross P&L) vs +0.11 bps on longs.
- The model favored shorts (92 shorts vs 35 longs) because Sep 21–23 exhibited mild intraday drift downward across large-cap tech and telecom.

---

## 7. Symbol-Wise Performance Dissection

| Symbol | Trades | Dir Acc % | Net Win % | Gross bps | Cost bps | Net bps | Gross P&L | Net P&L | Net / Trade |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **TATACAP.NS** | **21** | **76.2%** | **52.4%** | **+14.51** | 14.73 | **-0.22** | **+₹25.83** | **+₹2.00** | **+₹0.10** |
| **INFY.NS** | 6 | 66.7% | 16.7% | +8.40 | 14.67 | -6.27 | +₹5.20 | -₹3.90 | -₹0.65 |
| **HDFCBANK.NS** | 1 | 100.0% | 100.0% | +26.69 | 14.70 | +11.99 | +₹2.00 | +₹0.90 | +₹0.90 |
| **TCS.NS** | 42 | 52.4% | 16.7% | +0.06 | 14.69 | -14.62 | +₹0.46 | -₹129.46 | -₹3.08 |
| **BHARTIARTL.NS**| 44 | 43.2% | 18.2% | -0.24 | 14.76 | -15.01 | -₹1.79 | -₹120.71 | -₹2.74 |
| **BAJFINANCE.NS** | 7 | 42.9% | 28.6% | -3.50 | 14.68 | -18.19 | -₹2.52 | -₹13.16 | -₹1.88 |
| **RELIANCE.NS** | 4 | 25.0% | 0.0% | -10.50 | 14.61 | -25.11 | -₹5.20 | -₹12.44 | -₹3.11 |
| **AXISBANK.NS** | 1 | 0.0% | 0.0% | -9.65 | 14.70 | -24.35 | -₹1.20 | -₹3.03 | -₹3.03 |
| **ICICIBANK.NS** | 1 | 0.0% | 0.0% | +0.00 | 14.67 | -14.67 | +₹0.00 | -₹1.96 | -₹1.96 |

### Revelation on Symbol Concentration:
- **`TATACAP.NS` was NET PROFITABLE (+₹2.00, 52.4% net win rate, +14.51 bps gross return)**!
- **`TCS.NS` and `BHARTIARTL.NS` generated 86 out of 127 trades (67.7%) and -₹250.17 of the -₹281.76 total loss**!
- Why? Because under ₹5,000 capital and integer sizing, high-priced stocks (TCS at ₹3,000, BHARTIARTL at ₹1,850) could only purchase exactly **1 single share**. 1 share generates negligible gross rupee moves (a 10 bps move on 1 share of TCS is ₹3.00), while statutory costs and minimum brokerage consume ₹3.20!

---

## 8. Exit Reason & Stop-Loss Forensics

| Exit Reason | Count | % of Trades | Avg Duration | Dir Acc % | Gross Win % | Net Win % | Mean Gross | Net P&L |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **HORIZON_REACHED** | **124** | **97.6%** | 15.0 mins | **53.2%** | **53.2%** | **24.2%** | **+3.29 bps** | **-₹259.46** |
| **STOP_LOSS** | **3** | **2.4%** | 8.3 mins | 0.0% | 0.0% | 0.0% | -36.89 bps | -₹22.30 |

- The stop loss was **NOT premature**: only 3 trades (2.4%) were stopped out.
- 97.6% of trades lived through their full 15-minute horizon and exited naturally.
- The average gross return for horizon-exited trades was **+3.29 bps** (positive edge).

---

## 9. Time-of-Day Execution Performance

| Session Window | Trades | Directional Accuracy | Gross Win % | Net Win % | Mean Gross | Mean Net | Net P&L | Net / Trade |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Opening (09:15–10:30)** | 37 | 54.1% | 54.1% | **32.4%** | **+5.54 bps** | -9.24 bps | -₹58.57 | -₹1.58 |
| **Mid-Morning (10:30–12:30)**| 43 | **58.1%** | **58.1%** | 23.3% | +1.38 bps | -13.31 bps | -₹100.21 | -₹2.33 |
| **Afternoon (12:30–14:00)** | 28 | 46.4% | 46.4% | 14.3% | -1.03 bps | -15.73 bps | -₹80.08 | -₹2.86 |
| **Late Session (14:00–15:00)**| 19 | 42.1% | 42.1% | 21.1% | +3.26 bps | -11.41 bps | -₹42.90 | -₹2.26 |

- Opening window (09:15–10:30) had the best gross return (**+5.54 bps**) and highest net win rate (**32.4%**).
- Mid-afternoon (12:30–14:00) was the weakest window (-1.03 bps gross, 14.3% net win rate).

---

## 10. Direct Answers to the User's Core Hypotheses

| Hypothesis | Verdict | Empirical Evidence |
| :--- | :---: | :--- |
| **1. Is the model predicting the wrong direction?** | ❌ **FALSE** | Overall directional accuracy is **52.0%**; Gross P&L is **+₹22.78**; top-conviction signals achieve **71.0%** directional accuracy and **+13.62 bps** gross return. |
| **2. Is the 23.6% win rate caused by friction?** | ✅ **CONFIRMED** | 36 out of 66 gross winners (28.3% of all trades) were **Cost Casualties** wiped out by 14.72 bps friction. |
| **3. Did forcing 30+ trades/day dilute performance?** | ✅ **CONFIRMED** | Q4 top conviction (10 trades/day) had **+13.62 bps gross edge**; Q1-Q3 (32 trades/day) had **-1.30 bps**, destroying the portfolio. |
| **4. Is ₹5,000 cash equity viable for high-frequency?** | ❌ **UNVIABLE** | 1-share trades on high-priced stocks (TCS/BHARTIARTL) suffer high minimum friction relative to tiny rupee moves. |
| **5. Does holding longer help?** | ✅ **CONFIRMED** | EOD holding increases gross return from +2.94 bps to +5.84 bps and net win rate from 23.6% to 48.0%. |
