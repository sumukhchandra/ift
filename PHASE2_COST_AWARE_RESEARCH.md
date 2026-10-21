# AlphaNSE V3 — Phase 2: Cost-Aware 5–15 Minute Strategy Research
**Strict Chronological Multi-Horizon Investigation, Friction Decomposition, and Sequential Paper Evaluation**

- **Target Session:** Tuesday, 20 October 2026
- **Safety Status:** `LIVE_TRADING=False` | `ALLOW_REAL_ORDERS=False` (Strict Research Freeze)
- **Primary Execution Broker:** Kotak Neo (Trade Free Plan)
- **Capital Reference:** ₹1,500.00 Cash Equity (No Leverage, No Shorting, Max 1 Concurrent Position)
- **Daily Loss Limit:** ₹30.00
- **Intraday Square-Off:** 15:15:00 IST
- **Predecessor Evidence:** [MODEL_REPAIR_SPRINT_EVIDENCE.md](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/MODEL_REPAIR_SPRINT_EVIDENCE.md)
- **Audit Report Artifact:** [reports/live/phase2_cost_aware_research_report.json](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/phase2_cost_aware_research_report.json)

---

## 1. Executive Summary & Problem Formulation

In the preceding Model Repair Sprint ([MODEL_REPAIR_SPRINT_EVIDENCE.md](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/MODEL_REPAIR_SPRINT_EVIDENCE.md)), we repaired the 1-minute prediction pipeline, eliminating negative rank correlation and repairing the feature-target alignment (achieving +0.0240 Spearman IC on Stationary Ridge). However, out-of-sample backtesting exposed a fundamental economic barrier: **at a 1-minute frequency, the average price move is only 3.8 to 5.1 bps, whereas realistic execution friction on Indian equities is at least 8.54 bps (and 14.70 bps under conservative audit parameters)**. As a result, no 1-minute model can overcome execution drag on small capital.

**Phase 2 Objective:**
Investigate whether expanding the prediction horizon to **5-minute, 10-minute, and 15-minute discrete, non-overlapping bars** expands gross price movement sufficiently to clear realistic round-trip costs and generate robust, positive net expectancy under realistic execution constraints.

### Key Empirical Findings
1. **Volatility Amplitude Successfully Expands Across Horizons:**
   - **1-Minute Bar:** Mean move = 4.12 bps | 90th percentile = 9.20 bps (insufficient vs 8.54 bps friction).
   - **5-Minute Bar:** Mean move = 9.48 bps | 90th percentile = 20.82 bps.
   - **10-Minute Bar:** Mean move = 12.44 bps | 90th percentile = 26.95 bps.
   - **15-Minute Bar:** Mean move = **15.89 bps** | 90th percentile = **34.74 bps** (reaching 46.53 bps on high-beta liquid names).
   - *Verdict:* The 15-minute horizon successfully solves the physical amplitude bottleneck, providing price movements up to 4.1× the realistic Kotak Neo friction.

2. **Predictive Statistical Power Improves at Longer Horizons:**
   - On the untouched 6-session out-of-sample test set (1,530 non-overlapping 15m bars across liquid equities):
     - **Directional Accuracy:** Shallow LightGBM achieves **52.83%** (95% Wilson CI: `[50.30%, 55.34%]`), comfortably above the 50.0% coin-flip baseline and passing Gate 1 (>= 52.0%).
     - **Rank IC:** Spearman Rank Correlation reaches **+0.0756**, exceeding the Gate 2 requirement (+0.0300) by 2.5×.
     - **Prediction Bias:** Stationary at **+0.09 bps**, passing Gate 3 (< 2.0 bps).

3. **The Alpha Extraction Bottleneck & Cost-Hurdle Filtering:**
   - While the market moves 15.89 bps on average, the conditional gross return extracted by the statistical models is between **+0.53 bps and +2.09 bps** across candidate bars.
   - Realistic round-trip friction on Kotak Neo is **8.54 bps** (statutory taxes of 3.54 bps + spread/slippage of 5.00 bps). Conservative audit friction is **14.70 bps**.
   - When enforcing Directive 7's mandatory **Regime and Cost-Hurdle Filter** (requiring expected gross return to exceed estimated round-trip costs plus safety margin $\ge 10.0\text{ bps}$):
     - The validation set correctly indicated that expected edge does not reliably exceed 10.0 bps.
     - Consequently, the execution engine **refused to enter any low-conviction or sub-hurdle positions**.
     - Across the 6 unseen out-of-sample test sessions, exactly **0 trades were executed**.
     - **Total Net P&L:** **₹0.00** | **Total Fees Paid:** **₹0.00** | **Ending Bankroll:** **₹1,500.00** (100% capital preserved, 0.00 bps drawdown).

4. **Institutional Governance Decision:**
   - **Definitive Verdict: REJECT LIVE PROMOTION — RETAIN SHADOW/RESEARCH MODE (NO-GO).**
   - While statistical gates passed, Gate 5 (post-friction positive net expectancy in backtesting) cannot be fulfilled until alpha extraction exceeds the 8.54 bps cost hurdle. In strict accordance with Directive 11, real-order execution remains completely prohibited.

---

## 2. Safety & Risk Architecture Verification

Prior to any execution, the environment configuration and process isolation were audited:

```
[SAFETY AUDIT CONFIRMATION]
========================================================================================
Process Status:         🔴 NO ACTIVE TRADER PROCESS (PID: None)
Configuration Flags:    LIVE_TRADING=False
                        ALLOW_REAL_ORDERS=False
Capital Limit:          ₹1,500.00 Cash Equity (Enforced by KotakNeoAdapter & RiskManager)
Position Limit:         Maximum 1 concurrent open position
Daily Loss Limit:       ₹30.00 (Trading automatically halts upon breaching)
Short Selling:          Strictly PROHIBITED (Cash segment intraday long only)
Intraday Cutoff:        15:15:00 IST (Forced square-off)
Data Integrity:         Deterministic discrete bar aggregation; zero overlapping bars
========================================================================================
```

---

## 3. Recalculated Round-Trip Transaction Costs

Every transaction cost assumption was derived from actual regulatory schedules for Indian cash equity intraday trading on NSE, cross-referenced with Kotak Securities Trade Free Plan and the conservative audit baseline.

### 3.1 Cost Schedule Comparison Table
*Reference Capital: ₹1,500.00 cash deployed in 1 intraday roundtrip equity trade.*

| Cost Component | Regulatory / Broker Schedule | Kotak Neo Trade Free (Realistic) | Conservative Audit Baseline | Traditional Flat-Fee Broker (e.g. ₹20/order) |
| :--- | :--- | :---: | :---: | :---: |
| **Brokerage** | Kotak Neo: ₹0 for Intraday Cash Equity | **₹0.00** (0.00 bps) | **₹0.00** (0.00 bps) | ₹40.00 (266.67 bps) |
| **Securities Transaction Tax (STT)** | 0.025% on Sell Turnover | **₹0.38** (2.50 bps) | **₹0.38** (2.50 bps) | ₹0.38 (2.50 bps) |
| **NSE Exchange Turnover Charges** | 0.00345% of Turn (Roundtrip = 0.0061%) | **₹0.09** (0.61 bps) | **₹0.09** (0.61 bps) | ₹0.09 (0.61 bps) |
| **SEBI Regulatory Turnover Fee** | ₹10 per crore (0.0001% of Turnover) | **₹0.003** (0.02 bps) | **₹0.003** (0.02 bps) | ₹0.003 (0.02 bps) |
| **GST (Goods & Services Tax)** | 18% on (Brokerage + Exchange + SEBI) | **₹0.017** (0.11 bps) | **₹0.017** (0.11 bps) | ₹7.22 (48.13 bps) |
| **Stamp Duty** | 0.003% on Buy Turnover (State Stamp) | **₹0.045** (0.30 bps) | **₹0.045** (0.30 bps) | ₹0.045 (0.30 bps) |
| **Subtotal Statutory Taxes & Levies** | Guaranteed statutory minimum | **₹0.53** (**3.54 bps**) | **₹0.53** (**3.54 bps**) | **₹47.74** (**318.25 bps**) |
| **Half-Spread & Market Impact** | High-liquidity Large-Cap Nifty 50 shares | **₹0.45** (3.00 bps) | **₹1.05** (7.00 bps) | ₹0.45 (3.00 bps) |
| **Execution Fill Slippage** | 15m bar close/open execution slippage | **₹0.30** (2.00 bps) | **₹0.62** (4.16 bps) | ₹0.30 (2.00 bps) |
| **Total Round-Trip Friction** | **Complete all-in trading friction** | **₹1.28** (**8.54 bps**) | **₹2.20** (**14.70 bps**) | **₹48.49** (**323.25 bps**) |

![Cost Decomposition Breakdown](file:///C:/Users/sumuk/.gemini/antigravity-ide/brain/ae1836cb-3969-43d0-a098-e3cd7e77b9d5/phase2_cost_decomposition_breakdown.png)

### 3.2 Key Cost Insights
1. **Kotak Neo Trade Free Advantage:** Because Kotak Neo charges ₹0 brokerage on intraday cash equity, the fixed friction collapses from 323 bps down to **8.54 bps**.
2. **Statutory Floor:** The absolute statutory minimum tax floor is **3.54 bps** (₹0.53 on ₹1,500). Even with perfect limit order execution and zero spread, any strategy must clear 3.54 bps to break even.
3. **Execution Realistic Hurdle:** With a realistic 3 bps half-spread and 2 bps slippage on liquid stocks, the total friction is **8.54 bps**. Adding a conservative safety margin of 3.5 bps yields an entry hurdle of **$\ge 12.0\text{ bps}$**.

---

## 4. Chronological Partitioning & Non-Overlapping Bar Resampling

To guarantee zero lookahead leakage, zero overlapping-label bias, and complete independence of evaluation samples:

### 4.1 Discrete Non-Overlapping Bar Construction
Unlike rolling 1-minute aggregations where adjacent samples share $(H-1)$ minutes of identical price path, Phase 2 implements **discrete non-overlapping resampling** strictly aligned to the official 09:15:00 IST open:
$$\text{Bar}_k = [09:15 + k \cdot H, \; 09:15 + (k+1) \cdot H)$$
- **5-Minute Bars:** $H=5$ min $\rightarrow$ 75 discrete bars per symbol per session.
- **10-Minute Bars:** $H=10$ min $\rightarrow$ 37 discrete bars per symbol per session.
- **15-Minute Bars:** $H=15$ min $\rightarrow$ 25 discrete bars per symbol per session.
- **Target Construction:** Target return is the return of the *immediately following* independent bar:
  $$y_{t} = \frac{\text{Close}_{t+1} - \text{Open}_{t+1}}{\text{Open}_{t+1}} \times 10,000 \quad (\text{bps})$$
- **Feature Alignment:** All technical, order-flow imbalance (OFI), and volatility features are computed exclusively on completed history prior to $\text{Open}_{t+1}$. No future ticks or overlapping intervals are visible to the models.

### 4.2 Chronological Partitioning Schedule
- **In-Sample Training (8 Sessions):** `2026-09-18` through `2026-09-30` (32,000+ raw 1m candles; 2,340 15m bars).
- **Validation & Hurdle Tuning (2 Sessions):** `2026-10-01` and `2026-10-05` (8,700+ raw 1m candles; 585 15m bars). Used strictly for hyperparameter selection and cost-hurdle calibration.
- **Untouched Out-of-Sample Test (6 Sessions):** `2026-10-06`, `2026-10-07`, `2026-10-08`, `2026-10-09`, `2026-10-13`, and `2026-10-14` (25,300+ raw 1m candles; 1,530 non-overlapping 15m bars across liquid equities). Untouched until final evaluation.

---

## 5. Multi-Horizon Volatility & Price Amplitude Analysis

![Horizon Volatility Comparison](file:///C:/Users/sumuk/.gemini/antigravity-ide/brain/ae1836cb-3969-43d0-a098-e3cd7e77b9d5/phase2_horizon_volatility_comparison.png)

### 5.1 Distribution of Price Movement Across Time Horizons
Evaluating across all liquid universe symbols on unseen test sessions:

| Horizon | Sample Size ($N$ bars) | Mean Absolute Move | Median Move | 75th Percentile | 90th Percentile | Max Move | Ratio to Realistic Friction (8.54 bps) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1-Minute** (Sprint 1) | 25,320 | 4.12 bps | 2.85 bps | 5.30 bps | 9.20 bps | 78.40 bps | 0.48× (Sub-friction) |
| **5-Minute** (Phase 2) | 4,926 | 9.48 bps | 6.84 bps | 12.75 bps | 20.82 bps | 102.23 bps | 1.11× (Marginal) |
| **10-Minute** (Phase 2) | 2,396 | 12.44 bps | 8.87 bps | 16.54 bps | 26.95 bps | 152.03 bps | 1.46× (Favorable) |
| **15-Minute** (Phase 2) | **1,530** | **15.89 bps** | **11.23 bps** | **21.40 bps** | **34.74 bps** | **171.88 bps** | **1.86× (4.07× at P90)** |

### 5.2 Volatility Analysis Findings
- At the 1-minute horizon, 88% of all candles move less than the 8.54 bps round-trip friction. Trading 1-minute bars is mathematically guaranteed negative expectancy.
- At the 15-minute horizon, the 90th percentile price move expands to **34.74 bps**. On high-beta constituents (INFY, TATASTEEL, BAJFINANCE), 15m moves regularly exceed **45 to 60 bps**, proving that the market generates ample gross opportunity to overcome all execution friction.

---

## 6. Multi-Horizon Model Benchmark & Candidate Comparison

We benchmarked four distinct model architectures across all three horizons on the untouched 6-session out-of-sample test partition:
1. **Zero-Return Baseline:** Always predicts 0.0 bps return ($y_t = 0$).
2. **Persistence Baseline:** Predicts the immediately preceding bar's return ($y_t = y_{t-1}$).
3. **Stationary Ridge Regressor:** L2-regularized linear model ($\alpha=200.0$) on stationary standardized features.
4. **Shallow LightGBM:** Gradient-boosted decision tree ($N=80$, depth=3, leaves=7, Huber objective, $\lambda=20.0$).

![Candidate Metrics by Horizon](file:///C:/Users/sumuk/.gemini/antigravity-ide/brain/ae1836cb-3969-43d0-a098-e3cd7e77b9d5/phase2_candidate_metrics_by_horizon.png)

### 6.1 Comprehensive Benchmark Evaluation Table

| Horizon | Candidate Model | Evaluation Samples ($N$) | Directional Accuracy [95% Wilson CI] | MAE (bps) | RMSE (bps) | Prediction Bias (bps) | Rank IC (Spearman) | Gross Exp (bps) | Net Exp (Kotak 8.54 bps) | Net Exp (Audit 14.70 bps) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **5-Min** | Zero Baseline | 4,926 | 0.0% [N/A] | 9.48 | 13.82 | -0.24 | 0.0000 | 0.00 | -8.54 | -14.70 |
| | Persistence | 4,926 | 48.29% [46.85, 49.73] | 14.03 | 20.05 | +0.10 | -0.0371 | -0.16 | -8.70 | -14.86 |
| | Stationary Ridge | 4,926 | 51.69% [50.27, 53.11] | 9.47 | 13.79 | -0.30 | +0.0472 | +0.40 | -8.14 | -14.30 |
| | Shallow LightGBM | 4,926 | 50.81% [49.39, 52.23] | 9.48 | 13.82 | -0.32 | +0.0465 | +0.04 | -8.50 | -14.66 |
| **10-Min** | Zero Baseline | 2,396 | 0.0% [N/A] | 12.44 | 17.85 | -0.17 | 0.0000 | 0.00 | -8.54 | -14.70 |
| | Persistence | 2,396 | 48.88% [46.83, 50.93] | 18.18 | 25.63 | +0.19 | -0.0164 | +0.19 | -8.35 | -14.51 |
| | Stationary Ridge | 2,396 | 50.56% [48.53, 52.58] | 12.45 | 17.83 | -0.05 | +0.0162 | +0.07 | -8.47 | -14.63 |
| | Shallow LightGBM | 2,396 | **53.56%** [51.53, 55.57] | 12.44 | 17.84 | -0.08 | +0.0405 | +0.61 | -7.93 | -14.09 |
| **15-Min** | Zero Baseline | 1,530 | 0.0% [N/A] | 15.89 | 22.74 | -0.05 | 0.0000 | 0.00 | -8.54 | -14.70 |
| | Persistence | 1,530 | 49.36% [46.81, 51.91] | 22.81 | 32.92 | +0.12 | -0.0135 | +0.41 | -8.13 | -14.29 |
| | Stationary Ridge | 1,530 | 52.23% [49.70, 54.75] | 15.84 | 22.68 | +0.05 | +0.0687 | +0.78 | -7.76 | -13.92 |
| | **Shallow LightGBM** | **1,530** | **52.83%** [50.30, 55.34] | **15.87** | **22.73** | **+0.09** | **+0.0756** | **+0.53** | **-8.01** | **-14.17** |

### 6.2 Key Statistical Insights
1. **Strong Outperformance over Baselines:** Both Ridge and LightGBM thoroughly defeat the Persistence Baseline (which exhibits negative Rank IC and sub-50% accuracy across all horizons due to mean-reverting bid-ask bounce).
2. **Horizon Scaling of Rank IC:** Rank IC steadily climbs from +0.0465 at 5m to **+0.0756** at 15m for LightGBM (+0.0687 for Ridge). This confirms that longer bar aggregations filter out microstructure tick noise and allow real predictive momentum to register.
3. **Statistical Significance:** With $N = 1,530$ independent samples, LightGBM's Rank IC of $+0.0756$ has a Student's $t$-statistic of $t = \frac{r\sqrt{N-2}}{\sqrt{1-r^2}} = \frac{0.0756\sqrt{1528}}{\sqrt{1-0.0756^2}} \approx 2.96$ ($p = 0.0031$), rejecting the null hypothesis of zero correlation at the 99% confidence level.

---

## 7. Cost-Hurdle Filtering & Sequential Paper Trading Simulation

### 7.1 Mathematical Derivation of Cost-Aware Entry Filter
In compliance with Directive 7, an entry filter was developed exclusively on the training and validation sessions.
A trade is permitted **if and only if**:
$$\mathbb{E}[\text{Gross Return}] \ge \text{Total Estimated Friction} + \text{Safety Margin}$$
- Under Kotak Neo Trade Free:
  $$\text{Hurdle} \ge 8.54\text{ bps (friction)} + 3.46\text{ bps (safety margin)} = \mathbf{12.00\text{ bps}}$$
- Under Conservative Audit:
  $$\text{Hurdle} \ge 14.70\text{ bps (friction)} + 3.30\text{ bps (safety margin)} = \mathbf{18.00\text{ bps}}$$

### 7.2 Validation Tuning & Shrinkage Behavior
When analyzing the validation partition:
- In financial returns with low SNR ($\text{IC} \approx 0.07$), regression models naturally shrink conditional predictions toward the population mean to minimize MSE/Huber loss.
- For 15m bars, while the actual market move exceeds 34.7 bps in 10% of cases, the *conditional mean prediction* of the model ranges between -0.26 bps and +0.76 bps.
- Even if selecting the top decile of predicted alpha bars ($P \ge 90\text{th}$ percentile), the realized out-of-sample mean gross return is **+2.09 bps**.
- Because $+2.09\text{ bps} < 8.54\text{ bps}$, **no signal clears the cost hurdle**.

### 7.3 Sequential Backtest Results Under Realistic Execution Constraints
Parameters:
- Capital: ₹1,500.00 cash-only
- Open positions: Maximum 1
- Sizing: Exact whole shares ($\le \text{bankroll}$)
- Intraday square-off: 15:15:00 IST
- Daily loss limit: ₹30.00
- Short selling: Prohibited

| Strategy Configuration | Total Trades | Win Rate [95% CI] | Gross Exp (bps) | Net Exp (bps) | Total Net P&L (₹) | Total Fees Paid (₹) | Ending Bankroll (₹) | Max Drawdown |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **5m LightGBM (Hurdle $\ge$ 10 bps)** | 0 | 0.0% [N/A] | 0.00 | 0.00 | ₹0.00 | ₹0.00 | ₹1,500.00 | 0.00 bps |
| **5m LightGBM (Hurdle $\ge$ 12 bps)** | 0 | 0.0% [N/A] | 0.00 | 0.00 | ₹0.00 | ₹0.00 | ₹1,500.00 | 0.00 bps |
| **10m LightGBM (Hurdle $\ge$ 10 bps)** | 0 | 0.0% [N/A] | 0.00 | 0.00 | ₹0.00 | ₹0.00 | ₹1,500.00 | 0.00 bps |
| **10m LightGBM (Hurdle $\ge$ 12 bps)** | 0 | 0.0% [N/A] | 0.00 | 0.00 | ₹0.00 | ₹0.00 | ₹1,500.00 | 0.00 bps |
| **15m LightGBM (Hurdle $\ge$ 10 bps)** | 0 | 0.0% [N/A] | 0.00 | 0.00 | ₹0.00 | ₹0.00 | ₹1,500.00 | 0.00 bps |
| **15m LightGBM (Hurdle $\ge$ 12 bps)** | 0 | 0.0% [N/A] | 0.00 | 0.00 | ₹0.00 | ₹0.00 | ₹1,500.00 | 0.00 bps |
| **15m LightGBM (Hurdle $\ge$ 15 bps)** | 0 | 0.0% [N/A] | 0.00 | 0.00 | ₹0.00 | ₹0.00 | ₹1,500.00 | 0.00 bps |
| **15m LightGBM (Hurdle $\ge$ 18 bps)** | 0 | 0.0% [N/A] | 0.00 | 0.00 | ₹0.00 | ₹0.00 | ₹1,500.00 | 0.00 bps |

### 7.4 Session-by-Session Paper Trading Breakdown
*Evaluation of Top Candidate (15-Minute Horizon with Cost-Aware Hurdle $\ge 12.0\text{ bps}$) across 6 unseen test sessions:*

| Session Date | Day | Signals Evaluated | Signals Rejected by Cost Hurdle | Trades Executed | Win Rate | Gross Gain (₹) | Fees Paid (₹) | Net P&L (₹) | Ending Bankroll (₹) | Risk Halt Triggered |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **2026-10-06** | Tue | 255 | 255 (100.0%) | 0 | 0.0% | ₹0.00 | ₹0.00 | ₹0.00 | ₹1,500.00 | None (Normal) |
| **2026-10-07** | Wed | 255 | 255 (100.0%) | 0 | 0.0% | ₹0.00 | ₹0.00 | ₹0.00 | ₹1,500.00 | None (Normal) |
| **2026-10-08** | Thu | 255 | 255 (100.0%) | 0 | 0.0% | ₹0.00 | ₹0.00 | ₹0.00 | ₹1,500.00 | None (Normal) |
| **2026-10-09** | Fri | 255 | 255 (100.0%) | 0 | 0.0% | ₹0.00 | ₹0.00 | ₹0.00 | ₹1,500.00 | None (Normal) |
| **2026-10-13** | Mon | 255 | 255 (100.0%) | 0 | 0.0% | ₹0.00 | ₹0.00 | ₹0.00 | ₹1,500.00 | None (Normal) |
| **2026-10-14** | Tue | 255 | 255 (100.0%) | 0 | 0.0% | ₹0.00 | ₹0.00 | ₹0.00 | ₹1,500.00 | None (Normal) |
| **TOTAL** | — | **1,530** | **1,530 (100.0%)** | **0** | **0.0%** | **₹0.00** | **₹0.00** | **₹0.00** | **₹1,500.00** | **0 / 6 Sessions** |

### 7.5 Honest Reporting of Zero Trades (Directive 10 Compliance)
Directive 10 mandates: *"Paper-test the selected candidate on new sessions without changing its parameters mid-test. Report zero trades honestly when no valid opportunity occurs."*
- Rather than forcing trades by artificially lowering the hurdle to sub-friction levels (which would bleed capital at -6.45 bps per trade), the system's cost-aware gating correctly identified that predicted gross alpha did not provide an institutional safety margin over friction.
- Capital preservation is an active risk management triumph: **₹1,500.00 bankroll remains 100% intact**.

---

## 8. Institutional Acceptance Gate Matrix

| Acceptance Gate | Required Threshold | Empirical Value | Gate Status | Evidence Reference |
| :--- | :--- | :---: | :---: | :--- |
| **Gate 1: Directional Accuracy** | $\ge 52.0\%$ on unseen OOS test set | **52.83%** [50.30%, 55.34%] | <span style="color:green;font-weight:bold;">PASS</span> | 15m LightGBM across 1,530 independent test bars |
| **Gate 2: Rank Information Coefficient** | $\text{Spearman IC} \ge +0.0300$ | **+0.0756** ($p = 0.0031$) | <span style="color:green;font-weight:bold;">PASS</span> | Statistically significant positive monotonic correlation |
| **Gate 3: Absolute Prediction Bias** | $|\text{Mean Bias}| < 2.0\text{ bps}$ | **+0.09 bps** | <span style="color:green;font-weight:bold;">PASS</span> | Perfectly calibrated centering around 0.0 bps |
| **Gate 4: Volatility Expansion** | P90 Price Move $> 2\times$ Friction ($> 17.08\text{ bps}$) | **34.74 bps** ($4.07\times$ friction) | <span style="color:green;font-weight:bold;">PASS</span> | 15m bars provide ample physical room for alpha |
| **Gate 5: Sequential Post-Friction Net Expectancy** | Net Expectancy $> 0.0\text{ bps}$ post-friction in backtest | **+0.00 bps** (0 trades executed) | <span style="color:red;font-weight:bold;">FAIL</span> | Signal strength insufficient to clear $12.0\text{ bps}$ hurdle |
| **Gate 6: Zero Real Order Mandate** | Real orders prohibited in research | `LIVE_TRADING=False` confirmed | <span style="color:green;font-weight:bold;">PASS</span> | Verified in `.env` and runtime adapters |

---

## 9. Final Governance Decision & Strategic Roadmap

### 9.1 Definitive Decision: NO-GO for Real-Money Execution
```
========================================================================================
                      FINAL PHASE 2 GOVERNANCE VERDICT
                                  🔴 NO-GO
        RETAIN SHADOW / RESEARCH MODE — REAL-MONEY ORDERS STRICTLY PROHIBITED
========================================================================================
Rationale:
1. Although statistical prediction quality has dramatically improved (52.8% Dir Acc, 
   +0.0756 Rank IC, +34.7 bps P90 market move on 15m bars), the net expected edge 
   extracted per bar (+0.53 to +2.09 bps) does not yet exceed the 8.54 bps Kotak Neo friction.
2. In compliance with Directive 11, positive correlation and directional accuracy alone 
   DO NOT justify live capital deployment.
3. The cost-hurdle risk guard successfully prevented 1,530 sub-marginal entries, preserving 
   100% of the ₹1,500 bankroll. Real capital will only be permitted when Gate 5 passes 
   with positive net expectancy after all transaction friction.
========================================================================================
```

### 9.2 Clear Next Steps for Phase 3 Research
1. **Explore Higher-Volatility Regimes & Conditional Catalysts:**
   - Filter universe dynamically for stocks exhibiting relative volume surge ($V / \text{SMA}_{20}(V) > 2.5$) and elevated intraday ATR ($> 50\text{ bps}$), where realized 15m moves expand to $60–100\text{ bps}$.
2. **Asymmetric Payoff Strategies:**
   - Instead of 1-bar horizon holding, implement trailing profit targets with 2:1 reward-to-risk ratio (e.g. +25 bps profit target vs -10 bps stop loss), allowing the positive Rank IC (+0.0756) to capture right-tail expansions.
3. **Multi-Horizon Ensembling:**
   - Combine 5m microstructure order-flow imbalance (OFI) with 15m trend structure to filter for high-conviction momentum breakouts.

---

## 10. Reproducibility & Audit Log Trail

To reproduce all results, tables, and charts reported in this document from scratch:

```bash
# 1. Run complete regression test suite
python run_tests.py

# 2. Run multi-horizon data pipeline, cost models, and backtesting engine
python v3/research/phase2_cost_aware_research.py

# 3. Generate visualization charts
python v3/research/generate_phase2_charts.py

# 4. Verify trader daemon remains safely dormant
python check_status.py
```

### Generated Artifacts
- **Structured Data JSON:** [reports/live/phase2_cost_aware_research_report.json](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/reports/live/phase2_cost_aware_research_report.json)
- **Volatility Comparison Chart:** [phase2_horizon_volatility_comparison.png](file:///C:/Users/sumuk/.gemini/antigravity-ide/brain/ae1836cb-3969-43d0-a098-e3cd7e77b9d5/phase2_horizon_volatility_comparison.png)
- **Candidate Benchmark Chart:** [phase2_candidate_metrics_by_horizon.png](file:///C:/Users/sumuk/.gemini/antigravity-ide/brain/ae1836cb-3969-43d0-a098-e3cd7e77b9d5/phase2_candidate_metrics_by_horizon.png)
- **Cost Decomposition Chart:** [phase2_cost_decomposition_breakdown.png](file:///C:/Users/sumuk/.gemini/antigravity-ide/brain/ae1836cb-3969-43d0-a098-e3cd7e77b9d5/phase2_cost_decomposition_breakdown.png)
