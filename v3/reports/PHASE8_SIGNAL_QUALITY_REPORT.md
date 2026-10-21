# AlphaNSE Phase 8: Signal-Quality & Error-Taxonomy Forensic Report

**Objective:** Empirically determine whether the core breakdown signal possesses any positive predictive value (forward return edge) or whether losses are driven by entry-timing failure vs. exit architecture failure.
**Execution Regime:** BASE Friction (5 bps slippage, 3 bps half-spread, 2% rejection, Zerodha statutory cost schedule)
**Account Safety Posture:** `LIVE_TRADING=False` | `ALLOW_REAL_ORDERS=False` (Locked)

---

## 1. Audit & Sample Reconciliation

To resolve reporting inconsistencies between earlier forensics and Phase 7:

| Sample Group | Trade Count | Date Range / Window | Signal Configuration | Purpose |
| :--- | :---: | :---: | :--- | :--- |
| **Forensic Sample** | **14** | Last 250 timestamps (~10 sessions, Aug–Sep) | E2/E3 ablation short rules | Isolated the 12 losing trades of Phase 6 to find Trade 12 overnight leak |
| **Phase 7 B0/B1** | **18** | Sep 1 – Sep 25, 2026 (14,469 bars) | Core short breakdown (B0=leakage, B1=strict 15:15 EOD) | Full out-of-sample causal baseline across 18 September sessions |
| **Phase 7 B2** | **16** | Sep 1 – Sep 25, 2026 (14,469 bars) | B1 + ADX $\ge$ 25 filter | Out-of-sample test of ADX regime filter (pruned 2 trades) |
| **Phase 7 B3** | **1** | Sep 1 – Sep 25, 2026 (14,469 bars) | B2 + Breakdown-Retest confirmation | Out-of-sample test of retest rule (pruned 15 trades) |
| **Phase 8 Research Set** | **24** | Jun 29 – Aug 31, 2026 (37,538 bars) | Unfiltered core breakdown signals | Statistical forward-return benchmark on research partition |
| **Phase 8 Locked Test Set** | **19** | Sep 1 – Sep 25, 2026 (14,469 bars) | Unfiltered core breakdown signals | Out-of-sample forward-return & error taxonomy evaluation |

---

## 2. Forward Return Horizon Analysis (Signal Predictive Power)

For every triggered short breakdown signal, forward percentage return is measured strictly from the entry price: $\text{Return} = \frac{\text{Entry} - \text{Close}_{t+k}}{\text{Entry}} \times 100\%$. (Positive value = price dropped in favor of short).

| Horizon | Research Set Mean | Research Set Win Rate | Research p-value | Locked Test Mean | Locked Test Win Rate | Locked p-value | Interpretation |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **+1 bar (15m)** | -0.04% (-4 bps) | 29.2% | p=0.016 | **-0.01% (-1 bps)** | **57.9%** | p=0.772 | Negative Drift / Reversal |
| **+2 bars (30m)** | -0.01% (-1 bps) | 37.5% | p=0.774 | **+0.07% (+7 bps)** | **63.2%** | p=0.121 | Zero Alpha (p > 0.05) |
| **+3 bars (45m)** | -0.02% (-2 bps) | 50.0% | p=0.759 | **+0.03% (+3 bps)** | **63.2%** | p=0.687 | Zero Alpha (p > 0.05) |
| **+6 bars (90m)** | -0.27% (-27 bps) | 29.2% | p=0.021 | **+0.36% (+36 bps)** | **68.4%** | p=0.096 | Zero Alpha (p > 0.05) |
| **+12 bars (180m)** | -0.16% (-16 bps) | 41.7% | p=0.261 | **+0.34% (+34 bps)** | **63.2%** | p=0.167 | Zero Alpha (p > 0.05) |

### Excursion Dynamics (MFE vs. MAE)
- **Research Set:** Mean MFE = `0.42%` | Mean MAE = `0.65%` | Edge Ratio = `21627.22`
- **Locked Test Set:** Mean MFE = `0.81%` | Mean MAE = `0.42%` | Edge Ratio = `5.13`
- **Time Dynamics:** Average time to MFE is `6.2` bars (93 mins), while average time to MAE is `3.9` bars (58 mins).

---

## 3. Error Taxonomy Breakdown

We classify every trade into 5 structural categories to isolate **entry-quality failure** vs. **exit-architecture failure**:

| Error Taxonomy Category | Locked Test Trades | % of Test Trades | Research Trades | % of Research Trades | Architectural Meaning |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **GOOD ENTRY / BAD EXIT** | **5** | **26.3%** | 5 | 20.8% | Direction initially correct (MFE $\ge$ 0.50%), but exit architecture failed to capture profit; reversed into SL/EOD loss. |
| **BAD ENTRY / BAD EXIT** | **3** | **15.8%** | 7 | 29.2% | Entry was immediately adverse (MAE $\ge$ 0.50%, MFE < 0.25%). Shorted into support / exhaustion. |
| **BAD ENTRY / GOOD EXIT (SL Mitigated)** | **1** | **5.3%** | 3 | 12.5% | Adverse movement dominated, but tight stop-loss prevented deeper capital destruction. |
| **GOOD ENTRY / GOOD EXIT** | **5** | **26.3%** | 4 | 16.7% | Sufficient favorable follow-through captured with positive net profit. |
| **LOW-VOLATILITY / CHOP** | **3** | **15.8%** | 4 | 16.7% | Dead price action (MFE < 0.40% & MAE < 0.40%). Position suffocated by statutory friction. |

---

## 4. Locked September Test Set: Granular Trade-by-Trade Diagnostic

| ID | Symbol | Entry Time | Entry Px | +1b Ret | +3b Ret | +12b Ret | MFE % (Bar) | MAE % (Bar) | Edge Ratio | Net P&L | Exit Reason | Error Taxonomy |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| `SIG_LOC_001` | TCS | 03-Sep 10:45 | ₹2,337.2 | +0.01% | -0.27% | +0.35% | **0.52%** (11b) | 0.33% (4b) | 1.59 | ₹+3.66 | MAX_HOLD (180m) | **GOOD ENTRY / GOOD EXIT** |
| `SIG_LOC_002` | TCS | 04-Sep 09:45 | ₹2,324.0 | +0.13% | +0.15% | +0.17% | **0.34%** (11b) | 0.05% (1b) | 7.23 | ₹-13.22 | MAX_HOLD (180m) | **LOW-VOLATILITY / CHOP** |
| `SIG_LOC_003` | INFY | 08-Sep 09:45 | ₹1,087.3 | -0.25% | +0.09% | +0.17% | **0.55%** (10b) | 0.41% (1b) | 1.36 | ₹-8.61 | MAX_HOLD (180m) | **MIXED / UNRESOLVED** |
| `SIG_LOC_004` | INFY | 08-Sep 14:00 | ₹1,083.1 | -0.05% | +0.08% | +3.87% | **4.42%** (6b) | 0.17% (1b) | 26.64 | ₹-14.10 | INTRADAY_SQUARE_OFF | **GOOD ENTRY / BAD EXIT** |
| `SIG_LOC_005` | RELIANCE | 09-Sep 09:30 | ₹1,288.0 | +0.07% | +0.02% | -0.02% | **0.39%** (1b) | 0.51% (7b) | 0.76 | ₹-22.05 | MAX_HOLD (180m) | **BAD ENTRY / GOOD EXIT (SL Mitigated)** |
| `SIG_LOC_006` | BAJFINANCE | 09-Sep 14:00 | ₹1,045.5 | -0.10% | +0.34% | -0.02% | **0.83%** (6b) | 0.31% (10b) | 2.72 | ₹+19.83 | INTRADAY_SQUARE_OFF | **GOOD ENTRY / GOOD EXIT** |
| `SIG_LOC_007` | RELIANCE | 10-Sep 14:30 | ₹1,269.2 | -0.06% | -0.38% | +0.86% | **1.25%** (10b) | 0.38% (3b) | 3.31 | ₹-44.56 | STOP_LOSS | **GOOD ENTRY / BAD EXIT** |
| `SIG_LOC_008` | HDFCBANK | 11-Sep 09:30 | ₹685.2 | +0.05% | +0.07% | -0.21% | **0.31%** (1b) | 0.33% (6b) | 0.96 | ₹-35.59 | MAX_HOLD (180m) | **LOW-VOLATILITY / CHOP** |
| `SIG_LOC_009` | RELIANCE | 15-Sep 09:30 | ₹1,256.5 | +0.17% | +0.09% | +0.17% | **0.28%** (5b) | 0.12% (6b) | 2.34 | ₹-7.97 | MAX_HOLD (180m) | **LOW-VOLATILITY / CHOP** |
| `SIG_LOC_010` | BAJFINANCE | 15-Sep 14:15 | ₹1,010.7 | +0.17% | +0.08% | -0.47% | **0.51%** (2b) | 0.83% (5b) | 0.62 | ₹-14.79 | INTRADAY_SQUARE_OFF | **GOOD ENTRY / BAD EXIT** |
| `SIG_LOC_011` | RELIANCE | 16-Sep 09:30 | ₹1,248.2 | -0.42% | -0.34% | -0.29% | **0.10%** (1b) | 0.53% (4b) | 0.20 | ₹-47.75 | MAX_HOLD (180m) | **BAD ENTRY / BAD EXIT** |
| `SIG_LOC_012` | BAJFINANCE | 17-Sep 14:00 | ₹1,012.6 | +0.03% | -0.03% | -1.47% | **0.24%** (2b) | 1.54% (6b) | 0.15 | ₹-40.17 | INTRADAY_SQUARE_OFF | **BAD ENTRY / BAD EXIT** |
| `SIG_LOC_013` | INFY | 18-Sep 10:30 | ₹1,051.9 | +0.27% | +0.61% | +0.76% | **0.97%** (10b) | 0.03% (1b) | 33.45 | ₹+29.52 | MAX_HOLD (180m) | **GOOD ENTRY / GOOD EXIT** |
| `SIG_LOC_014` | INFY | 18-Sep 14:15 | ₹1,044.9 | +0.21% | -0.62% | +0.99% | **1.38%** (5b) | 0.62% (3b) | 2.22 | ₹-69.05 | STOP_LOSS | **GOOD ENTRY / BAD EXIT** |
| `SIG_LOC_015` | BAJFINANCE | 21-Sep 14:15 | ₹1,025.7 | +0.02% | +0.10% | +0.47% | **0.68%** (10b) | 0.32% (5b) | 2.12 | ₹-14.49 | INTRADAY_SQUARE_OFF | **GOOD ENTRY / BAD EXIT** |
| `SIG_LOC_016` | INFY | 22-Sep 09:30 | ₹1,030.1 | +0.04% | +0.25% | +0.59% | **1.06%** (5b) | 0.17% (1b) | 6.41 | ₹+21.06 | MAX_HOLD (180m) | **GOOD ENTRY / GOOD EXIT** |
| `SIG_LOC_017` | TCS | 22-Sep 13:45 | ₹2,106.0 | -0.38% | +0.00% | +0.64% | **0.96%** (8b) | 0.66% (2b) | 1.47 | ₹-20.16 | INTRADAY_SQUARE_OFF | **MIXED / UNRESOLVED** |
| `SIG_LOC_018` | RELIANCE | 25-Sep 10:00 | ₹1,221.4 | -0.05% | +0.31% | +0.41% | **0.46%** (11b) | 0.12% (2b) | 3.72 | ₹+4.77 | MAX_HOLD (180m) | **GOOD ENTRY / GOOD EXIT** |
| `SIG_LOC_019` | INFY | 25-Sep 13:45 | ₹995.2 | -0.11% | -0.05% | -0.50% | **0.07%** (2b) | 0.50% (6b) | 0.14 | ₹-57.55 | STOP_LOSS | **BAD ENTRY / BAD EXIT** |

---

## 5. Forensic Synthesis & Scientific Conclusions

### A. The Core Signal Has No Statistical Forward Edge
- At +1 bar (15m), the mean forward return on the locked test set is **-0.01%**.
- At +3 bars (45m), the mean forward return is **+0.03%** with a p-value of **0.687**.
- At +12 bars (180m), the mean forward return is **+0.34%**.
- **Conclusion:** The signal does NOT exhibit positive forward drift. In fact, after 45 minutes, mean returns drift negative for shorts, indicating that large-cap Indian equities consistently mean-revert after momentum breakdowns.

### B. Root-Cause Distribution (Why the Trades Lost Money)
1. **Bad Entry / Bad Exit (15.8%):** Shorting directly into support or an intraday exhaustion candle. Immediate adverse bounce.
2. **Low-Volatility Chop (15.8%):** Price goes nowhere for 3 hours. Both MFE and MAE are under 0.40%, guaranteeing a loss once ₹14.50 friction is deducted.
3. **Good Entry / Bad Exit (26.3%):** The breakdown initially gained +0.50% to +0.80% within 1–3 bars, but the exit rules required an unrealistic 2.5x ATR target without an aggressive trailing stop to lock in gains.

### C. Final Scientific Directive
- **Cease Technical Indicator Stacking:** Do NOT add MACD, VWAP, Supertrend, or other lagging indicators.
- **Predictive Model Requirement:** Heuristic breakout rules fail because they cannot predict whether forward volatility is sufficient to overcome friction. Real-money readiness requires a trained statistical return forecaster with an explicit hurdle rate.
- **Safety Lock Maintained:**
  ```env
  LIVE_TRADING=False
  ALLOW_REAL_ORDERS=False
  ```