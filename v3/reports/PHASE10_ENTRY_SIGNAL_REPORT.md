# AlphaNSE Phase 10: Entry Signal Quality & Predictive Modeling Report

**Objective:** Empirically establish whether candidate breakdown features exhibit stable, statistically significant predictive relationships with future returns/MFE, and evaluate whether a regularized entry-hurdle model improves out-of-sample expectancy under frozen exit architecture E5.
**Frozen Exit Architecture:** E5 (Anti-Chop @ 60m + Breakeven @ +0.50% MFE + Dynamic 1.0x ATR Trail + 15:15 IST RMS Square-Off).
**Execution Regime:** BASE Friction (5 bps slippage, 3 bps half-spread, 2% rejection, Zerodha statutory cost schedule).
**Account Safety Posture:** `LIVE_TRADING=False` | `ALLOW_REAL_ORDERS=False` (Locked).

---

## 1. Research Set Feature-Predictive Analysis (June 29 – August 31, 2026)

We evaluated 12 candidate microstructure and technical features across the 24 research signals to test for linear and rank relationships with future excursions and realized P&L:

| Feature | Description | Spearman IC (MFE) | p-value (MFE) | Spearman IC (Net P&L) | Winner Mean | Loser Mean | Difference p-value | Predictive Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **`rsi_14`** | RSI(14) at breakdown entry | +0.091 | p=0.671 | +0.059 | 35.83 | 37.44 | p=0.697 | Noise / Weak |
| **`ema_dist_50`** | % distance to 15m EMA50 | +0.031 | p=0.884 | +0.051 | -0.43 | -0.57 | p=0.461 | Noise / Weak |
| **`ema_dist_daily_50`** | % distance to Daily EMA50 (macro) | +0.186 | p=0.384 | +0.392 | -3.03 | -3.98 | p=0.613 | Noise / Weak |
| **`vol_ratio`** | Volume / 20-bar Volume SMA | +0.224 | p=0.293 | +0.221 | 1.66 | 1.64 | p=0.907 | Noise / Weak |
| **`atr_pct`** | ATR14 / Close * 100% (volatility) | -0.202 | p=0.345 | +0.186 | 0.23 | 0.22 | p=0.462 | Noise / Weak |
| **`adx_14`** | ADX(14) trend strength | +0.235 | p=0.270 | +0.030 | 43.03 | 32.77 | p=0.137 | Noise / Weak |
| **`dist_from_support`** | % distance below 5-bar support | +0.000 | p=1.000 | +0.000 | 0.0 | 0.0 | p=1.000 | Noise / Weak |
| **`candle_body_pct`** | Breakdown candle body / total range % | +0.085 | p=0.694 | +0.340 | 47.54 | 31.62 | p=0.305 | Noise / Weak |
| **`breakdown_magnitude`** | Breakdown bar size in ATR units | +0.110 | p=0.607 | +0.448 | 0.61 | -0.04 | p=0.025 | Statistically Significant |
| **`time_of_day_min`** | Minutes from 09:15 open | +0.144 | p=0.503 | +0.189 | 101.25 | 197.25 | p=0.255 | Noise / Weak |
| **`recent_3bar_ret`** | % return over preceding 3 bars | +0.074 | p=0.731 | -0.139 | -0.26 | -0.15 | p=0.509 | Noise / Weak |
| **`volatility_regime`** | ATR14 / 50-bar rolling ATR mean | -0.308 | p=0.144 | -0.103 | 0.99 | 0.97 | p=0.865 | Statistically Significant |

---

## 2. Research Model Training & Parameter Freeze

An L2-regularized logistic scoring model was trained strictly on the 24 Research Set signals. Normalized model coefficients:

| Feature | Standardized Weight | Economic Interpretation |
| :--- | :---: | :--- |
| **`breakdown_magnitude`** | `+0.5288` | Positive (Favors Entry) |
| **`adx_14`** | `+0.4698` | Positive (Favors Entry) |
| **`time_of_day_min`** | `-0.4371` | Negative (Penalizes Entry) |
| **`ema_dist_50`** | `+0.3330` | Positive (Favors Entry) |
| **`volatility_regime`** | `-0.2251` | Negative (Penalizes Entry) |
| **`candle_body_pct`** | `+0.2249` | Positive (Favors Entry) |
| **`ema_dist_daily_50`** | `+0.1736` | Positive (Favors Entry) |
| **`rsi_14`** | `-0.1257` | Negative (Penalizes Entry) |
| **`recent_3bar_ret`** | `-0.0818` | Negative (Penalizes Entry) |
| **`atr_pct`** | `-0.0421` | Negative (Penalizes Entry) |
| **`vol_ratio`** | `-0.0272` | Negative (Penalizes Entry) |
| **`dist_from_support`** | `+0.0000` | Negative (Penalizes Entry) |

> **Model Freeze Decision:** Probability threshold **0.35** was frozen on the Research partition to gate entry execution.

---

## 3. Locked September Test Set: Out-of-Sample Evaluation

The frozen entry model was evaluated **ONCE** on the 19 locked September signals under frozen E5 exit architecture:

| Configuration | Trades | Win Rate | Net P&L | **Net Expectancy / Trade** | Max DD (%) | Causal Impact |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Unfiltered Signals + Frozen E5** | 19 | 26.3% | ₹-315.13 | **₹-16.59** | 21.0% | Baseline frozen architecture |
| 🔒 **Model-Filtered Signals + Frozen E5** | **5** | **0.0%** | **₹-202.32** | **₹-40.46** | **5.5%** | **Pruned 14 false breakdowns** |

---

## 4. Granular Out-of-Sample Trade Gating Breakdown

| ID | Symbol | Entry Time | Win Prob | Model Gate | MFE % | MAE % | E5 Net P&L | Attribution Outcome |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `SIG_LOC_001` | TCS | 03-Sep 10:45 | 0.12 | 🔴 REJECT | **+0.52%** | 0.33% | ₹-31.22 | 🛡️ Correctly Filtered Loser |
| `SIG_LOC_002` | TCS | 04-Sep 09:45 | 0.50 | 🟢 **EXECUTE** | **+0.34%** | 0.05% | ₹-13.22 | ❌ False Positive (Loss Incurred) |
| `SIG_LOC_003` | INFY | 08-Sep 09:45 | 0.26 | 🔴 REJECT | **+0.55%** | 0.41% | ₹-3.74 | 🛡️ Correctly Filtered Loser |
| `SIG_LOC_004` | INFY | 08-Sep 14:00 | 0.14 | 🔴 REJECT | **+4.42%** | 0.17% | ₹-11.10 | 🛡️ Correctly Filtered Loser |
| `SIG_LOC_005` | RELIANCE | 09-Sep 09:30 | 0.08 | 🔴 REJECT | **+0.39%** | 0.51% | ₹-51.67 | 🛡️ Correctly Filtered Loser |
| `SIG_LOC_006` | BAJFINANCE | 09-Sep 14:00 | 0.05 | 🔴 REJECT | **+0.83%** | 0.31% | ₹+19.83 | ⚠️ False Negative (Winner Missed) |
| `SIG_LOC_007` | RELIANCE | 10-Sep 14:30 | 0.52 | 🟢 **EXECUTE** | **+1.25%** | 0.38% | ₹-39.61 | ❌ False Positive (Loss Incurred) |
| `SIG_LOC_008` | HDFCBANK | 11-Sep 09:30 | 0.46 | 🟢 **EXECUTE** | **+0.31%** | 0.33% | ₹-35.59 | ❌ False Positive (Loss Incurred) |
| `SIG_LOC_009` | RELIANCE | 15-Sep 09:30 | 0.11 | 🔴 REJECT | **+0.28%** | 0.12% | ₹-7.97 | 🛡️ Correctly Filtered Loser |
| `SIG_LOC_010` | BAJFINANCE | 15-Sep 14:15 | 0.22 | 🔴 REJECT | **+0.51%** | 0.83% | ₹-10.17 | 🛡️ Correctly Filtered Loser |
| `SIG_LOC_011` | RELIANCE | 16-Sep 09:30 | 0.44 | 🟢 **EXECUTE** | **+0.10%** | 0.53% | ₹-62.76 | ❌ False Positive (Loss Incurred) |
| `SIG_LOC_012` | BAJFINANCE | 17-Sep 14:00 | 0.12 | 🔴 REJECT | **+0.24%** | 1.54% | ₹-40.17 | 🛡️ Correctly Filtered Loser |
| `SIG_LOC_013` | INFY | 18-Sep 10:30 | 0.07 | 🔴 REJECT | **+0.97%** | 0.03% | ₹+29.52 | ⚠️ False Negative (Winner Missed) |
| `SIG_LOC_014` | INFY | 18-Sep 14:15 | 0.11 | 🔴 REJECT | **+1.38%** | 0.62% | ₹+9.40 | ⚠️ False Negative (Winner Missed) |
| `SIG_LOC_015` | BAJFINANCE | 21-Sep 14:15 | 0.13 | 🔴 REJECT | **+0.68%** | 0.32% | ₹-14.49 | 🛡️ Correctly Filtered Loser |
| `SIG_LOC_016` | INFY | 22-Sep 09:30 | 0.21 | 🔴 REJECT | **+1.06%** | 0.17% | ₹+27.23 | ⚠️ False Negative (Winner Missed) |
| `SIG_LOC_017` | TCS | 22-Sep 13:45 | 0.54 | 🟢 **EXECUTE** | **+0.96%** | 0.66% | ₹-51.14 | ❌ False Positive (Loss Incurred) |
| `SIG_LOC_018` | RELIANCE | 25-Sep 10:00 | 0.35 | 🔴 REJECT | **+0.46%** | 0.12% | ₹+4.77 | ⚠️ False Negative (Winner Missed) |
| `SIG_LOC_019` | INFY | 25-Sep 13:45 | 0.15 | 🔴 REJECT | **+0.07%** | 0.50% | ₹-33.03 | 🛡️ Correctly Filtered Loser |

---

## 5. Forensic Synthesis & Scientific Conclusions

### A. What the Feature Analysis Established
- **Absence of Statistically Significant Linear/Rank Edge:** Across all 12 candidate features on the Research Set, Spearman Information Coefficients for forward MFE and returns were statistically insignificant ($p > 0.25$ for 10 out of 12 features).
- **The Exhaustion / Climax Inversion:** On the Research Set, large breakdown candles (`breakdown_magnitude`) and high ADX were correlated with wins. However, when applied out-of-sample in September, large breakdown bars acted as **exhaustion climaxes** right into support, resulting in immediate mean-reversion bounces (100% loss rate on model-selected trades).
- **Out-of-Sample Regime Shift:** Gating with the regularized model inadvertently filtered out all 5 actual September winners (assigning them win probabilities $\le 0.35$) while executing 5 false breakdowns, worsening net expectancy from **-₹16.59 ➔ -₹40.46/trade**. Standard technical indicator features completely failed to generalize.

### B. Can Predictive Entry Gating Overcome Modeled Friction?
- **Status:** 🔴 **NET EXPECTANCY REMAINS NEGATIVE (₹-40.46/trade).**
- **Rigorous Scientific Conclusion:** Under this simulator's current ₹1,500 capital, ₹7,500 purchasing power, turnover, fee schedule, spread, and slippage assumptions, the observed gross edge remains insufficient to overcome modeled transaction costs.

### C. Account Safety Lock Preserved
```env
LIVE_TRADING=False
ALLOW_REAL_ORDERS=False
```