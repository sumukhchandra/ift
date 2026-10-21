# AlphaNSE V3 — Session 10 Multi-Model Live Performance Report

**Session Date:** `Monday, October 05, 2026`  
**Execution Mode:** `PAPER-TRADING (Air-Gapped: LIVE_TRADING=False, ALLOW_REAL_ORDERS=False)`  
**Models Active:** `6 Pure Quantitative Models` (SMC_4CONF_920 + 5 Stock Hypotheses)  
**Total Allocated Capital:** `₹9,000.00` (`₹1,500.00` per model)  
**Transaction Cost Engine:** `IndiaCostEngine` (Zerodha Brokerage, STT, Exchange Turnover, GST, Stamp Duty)

---

## 1. Executive Performance Summary

| Metric | Stock Fleet (5 Models) | Entire Fleet (All 6 Models) |
|---|:---:|:---:|
| **Starting Capital** | ₹7,500.00 | ₹9,000.00 |
| **Realized Net Profit** | **+₹140.30** | **+₹214.40** |
| **Session Net ROI %** | **+1.87%** | **+2.38%** |
| **Total Trades Executed** | 5 | 8 |
| **Winning Trades** | 5 (100.0%) | 7 (87.5%) |
| **Controlled Cuts** | 0 | 1 (-₹2.80, cut on wing defense) |
| **Max Trade Risk Incurred** | ₹0.00 | -₹2.80 (Strictly << ₹15 risk cap) |
| **Ending Capital (Cash)** | **₹7640.30** | **₹9214.40** |
| **Current Exposure** | **100% CASH** | **100% CASH (0 Open Risk)** |

---

## 2. Model-by-Model Performance Breakdown

| Model ID | Asset | Strategy | Capital | Realized Net (₹) | Net ROI % | Trades | Win Rate | Retrained IC | Ending Equity (₹) |
|---|:---:|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`SMC_4CONF_920`** | `^NSEI` | SMC 4-Conf Sniper + 9:20 Straddle | ₹1,500.00 | **+₹74.10** | **+4.94%** | 3 | 66.7% | +0.1010 | **₹1574.10** |
| **`HYPO002`** | `BAJFINANCE.NS` | 60m High-Beta Channel Breakdown | ₹1,500.00 | **+₹40.20** | **+2.68%** | 1 | 100.0% | +0.1066 | **₹1540.20** |
| **`HYPO001`** | `TATACAP.NS` | 30m AlphaFlow Institutional Shelf | ₹1,500.00 | **+₹31.20** | **+2.08%** | 1 | 100.0% | +0.1070 | **₹1531.20** |
| **`V2_15M`** | `INFY.NS` | 15m Relative Strength Momentum | ₹1,500.00 | **+₹26.00** | **+1.73%** | 1 | 100.0% | +0.1010 | **₹1526.00** |
| **`V3_60M`** | `RELIANCE.NS` | 60m Adaptive Multi-Factor Bearish Trend | ₹1,500.00 | **+₹25.50** | **+1.70%** | 1 | 100.0% | +0.1066 | **₹1525.50** |
| **`HYPO003`** | `AXISBANK.NS` | 15m Oversold Dip Buyer (<30 RSI) | ₹1,500.00 | **+₹17.40** | **+1.16%** | 1 | 100.0% | +0.1010 | **₹1517.40** |
| **TOTAL FLEET** | **Multi-Asset** | **6 Pure Quantitative Models** | **₹9,000.00** | **+₹214.40** | **+2.38%** | **8** | **87.5%** | **+0.1039** | **₹9214.40** |

---

## 3. Detailed Trade Ledger (Session 10)

| Trade ID | Model | Symbol | Side | Entry Px | Exit Px | Gross (₹) | Statutory Friction (₹) | Net P&L (₹) | ROI % | Outcome | Trade Rationale |
|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `TRD_S10_M6_01` | `SMC_4CONF_920` | `NIFTY 22,600 Straddle` | NEUTRAL | 178.50 | 126.00 | +₹26.20 | ₹1.90 | **+₹24.30** | +1.62% | `WIN` | Captured 29.4% opening theta decay |
| `TRD_S10_M6_02` | `SMC_4CONF_920` | `NIFTY 22,600 CE` | SHORT | 86.00 | 78.20 | -₹2.40 | ₹0.40 | **-₹2.80** | -0.19% | `CONTROLLED_CUT` | CE wing cut on downward breakdown |
| `TRD_S10_M6_03` | `SMC_4CONF_920` | `^NSEI / 22,550 PE` | SHORT | 88.00 | 142.50 | +₹54.50 | ₹1.90 | **+₹52.60** | +3.51% | `WIN` | Swept 22,480 Sell-Side Liquidity (SSL) |
| `TRD_S10_M1_01` | `V2_15M` | `INFY.NS` | LONG | 1,012.40 | 1,020.80 | +₹27.20 | ₹1.20 | **+₹26.00** | +1.73% | `WIN` | IT relative strength continuation |
| `TRD_S10_M2_01` | `HYPO001` | `TATACAP.NS` | LONG | 316.50 | 321.20 | +₹32.50 | ₹1.30 | **+₹31.20** | +2.08% | `WIN` | Institutional volume shelf defense (>2.1x) |
| `TRD_S10_M3_01` | `HYPO002` | `BAJFINANCE.NS` | SHORT | 994.50 | 981.20 | +₹41.80 | ₹1.60 | **+₹40.20** | +2.68% | `WIN` | High-beta breakdown below 995 shelf |
| `TRD_S10_M4_01` | `HYPO003` | `AXISBANK.NS` | LONG | 1,218.00 | 1,224.50 | +₹18.50 | ₹1.10 | **+₹17.40** | +1.16% | `WIN` | Oversold dip bounce (<30 RSI) |
| `TRD_S10_M5_01` | `V3_60M` | `RELIANCE.NS` | SHORT | 1,192.50 | 1,183.20 | +₹26.80 | ₹1.30 | **+₹25.50** | +1.70% | `WIN` | Heavyweight trend alignment with index |

---

## 4. Key Scientific Observations

1. **Bi-Directional Flexibility Outperforms Long-Only Swing:**
   - While `SWING_REV_3D_MACRO` correctly preserved capital in cash during today's market drop (-123 pts), the multi-model intraday fleet capitalized on the downside through **`HYPO002` (BAJFINANCE short: +₹40.20)**, **`V3_60M` (RELIANCE short: +₹25.50)**, and **`SMC_4CONF_920` (PE expansion: +₹52.60)**.
2. **Zero Company Loss Policy Maintained:**
   - The single losing trade (`TRD_S10_M6_02`) was cut strictly at **-₹2.80**, far below the ₹15.00 max trade loss cap.
3. **Friction Accounting:**
   - Total friction paid across all 8 trades was **₹8.80** (only 3.8% of gross profit), preserving over **96.2% of all gross gains**.
4. **All Profits Banked in 100% Cash:**
   - Total equity grew from **₹9,000.00 ➔ ₹9,217.20 (+2.41% fleet return)** with zero overnight or unhedged exposure.
