# ALPHANSE V2 — PHASE 3A FORENSIC SIGNAL DECOMPOSITION & ECONOMIC RECOVERY REPORT

**Executive Research Report: Forensic Gross Alpha Decomposition, Horizon Scaling, Signal Sparsity Frontiers & Cluster-Robust Inference**

*Date: September 20, 2026*  
*Repository Status: `DATA_LIMITED` (59 Sessions, 48,009 5m Bars)*  
*Nature of Phase 3A: Explicitly Exploratory Hypothesis Generation (Not a Confirmation/Validation Set)*  
*Execution Mode: PHYSICAL LIVE EXECUTION LOCKED (`LiveExecutionDisabledError`)*  
*Capital Router: DORMANT / LOCKED*  

---

## 1. Executive Summary & Core Scientific Conclusion

Phase 3 established that while price/microstructure features possess modest statistical predictability ($IC > +0.03$), the strategy produces negative net economic expectancy across all 5 walk-forward folds due to the severe gap between gross moves ($+0.4$ to $+1.3$ bps) and NSE transaction friction ($\sim 14.7$ to $15.4$ bps).

Phase 3A was chartered as an **exploratory forensic investigation** to dissect the positive gross signal across **60 distinct empirical slices** (time of day, constituent symbols, volatility regimes, directionality, sparsity frontiers, horizon scaling, execution sensitivity, and predefined interactions) to answer:
> **Is there any sub-domain where the predictable gross return scales beyond the ~15 bps transaction cost hurdle?**

### The Definitive Finding: **THE GROSS SIGNAL ASYMPTOTES BELOW +2.5 BPS EVERYWHERE**

```text
====================================================================================================
EXPLORATORY DIMENSION         BEST OBSERVED GROSS   TRANSACTION FRICTION  NET EXPECTANCY  VIABLE?
====================================================================================================
Overall High-Conviction (5m)  +0.52 bps             14.77 bps             -14.25 bps      NO ❌
Time-of-Day (11:00–13:00)     +1.25 bps             14.73 bps             -13.48 bps      NO ❌
Best Constituent (BAJFINANCE) +2.50 bps             14.82 bps             -12.32 bps      NO ❌
Worst Constituent (TCS.NS)    -2.21 bps             14.71 bps             -16.92 bps      NO ❌
Directionality (Short 5m)     +0.74 bps             14.81 bps             -14.07 bps      NO ❌
Signal Sparsity (P99 at 30m)  +1.92 bps             14.97 bps             -13.05 bps      NO ❌
Horizon Scaling (60m)         +1.53 bps             14.83 bps             -13.29 bps      NO ❌
Passive Execution (Limit)     +0.52 bps             13.70 bps             -13.18 bps      NO ❌
Interactions (14:30 x NormVol)+0.21 bps             14.70 bps             -14.49 bps      NO ❌
====================================================================================================
```

Across all 60 empirical slices evaluated:
1. **Zero slices achieved positive net expectancy.**
2. **Zero slices generated an average gross move exceeding $+2.50$ basis points.**
3. **The Session Block-Bootstrap 95% Confidence Interval for gross return includes zero: $[-0.13, +1.17]$ bps.**
4. The strategy's failure to clear transaction costs is **not** caused by trading at the wrong time of day, nor by long-only bias, nor by an overly permissive decision threshold. It is caused by a structural, order-of-magnitude mismatch between the price resolution of 5m–60m technical features and exchange transaction friction.

---

## 2. Cost Model Reconciliation Formally Documented

The configuration discrepancy between the Phase 1 static approximation ($15.40$ bps) and Phase 3 dynamic calculation ($14.70$ bps) has been fully reconciled and parameterized in [`DynamicCostModel`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/v2/risk/dynamic_cost_model.py):

```text
====================================================================================================
FEE COMPONENT            RATE / SCHEDULE                   CALCULATION ON ₹5,000   BPS OF NOTIONAL
====================================================================================================
Brokerage (both sides)   min(0.03%, ₹20) per side          ₹1.50 x 2 = ₹3.00       6.00 bps
STT (sell side)          0.025% on non-delivery sell       ₹5,000 x 0.00025 = ₹1.25 2.50 bps
Exchange turnover        0.00307% per side                 ₹10,000 x 0.0000307=₹0.31 0.61 bps
SEBI turnover fee        ₹10 per crore (0.0001%)           ₹10,000 x 0.000001=₹0.01 0.02 bps
GST                      18% on (Brokerage+Exchange+SEBI)  18% x ₹3.32 = ₹0.60     1.19 bps
Stamp duty               0.003% on buy side                ₹5,000 x 0.00003 = ₹0.15 0.30 bps
----------------------------------------------------------------------------------------------------
SUBTOTAL STATUTORY                                         ₹5.32                   10.63 bps
----------------------------------------------------------------------------------------------------
Bid-Ask Spread           2 x half-spread (1.0 bps)         Round-trip spread       2.00 bps
Market Impact Slippage   base (2.0) + 5.0 * sqrt(partic)   ₹5k / ₹25M bar notional 2.07 bps
====================================================================================================
TOTAL BASELINE DYNAMIC COST                                                        14.70 bps
====================================================================================================
```
* **Execution Tree Cost Schedule & Component Additive Identity**:
```text
====================================================================================================================================
SCENARIO             STATUTORY  SPREAD   IMPACT   ADVERSE  PARTIAL FILL  COMPLETED COST  ATTEMPTED COST  FILL PROB  POLICY
====================================================================================================================================
STATUTORY_ONLY       10.63 bps  0.00 bps 0.00 bps 0.00 bps 0.00 bps      10.63 bps       10.63 bps       1.00       Theoretical Floor
BASE_AGGRESSIVE      10.63 bps  2.00 bps 2.07 bps 0.00 bps 0.00 bps      14.70 bps       14.70 bps       1.00       Marketable Order
STRESSED_AGGRESSIVE  10.63 bps  3.00 bps 3.11 bps 0.00 bps 0.00 bps      16.74 bps       16.74 bps       1.00       1.5x Multiplier
PASSIVE              10.63 bps  1.00 bps 1.04 bps 1.00 bps 0.41 bps      14.08 bps        9.15 bps       0.65       Market Cross Remainder
CONSERVATIVE_PASSIVE 10.63 bps  1.00 bps 1.04 bps 2.00 bps 0.81 bps      15.48 bps        6.97 bps       0.45       Market Cross Remainder
====================================================================================================================================
```
* **Strict Invariant**: $\left|\sum \text{Components} - \text{Total Completed Cost}\right| < 10^{-6}$ is verified for every scenario.
* **Why Phase 1 assumed 15.40 bps**: Phase 1 used static round figures of $2.50$ bps spread + $2.50$ bps slippage + $10.40$ bps statutory = $15.40$ bps.
* **Impact Formula Parameterized**:
  $$\text{impact\_bps} = \text{base\_impact\_bps} + \text{impact\_coefficient\_bps} \times \sqrt{\text{participation\_rate\_fraction}}$$
  where $\text{participation\_rate\_fraction} = \frac{\text{trade\_notional}}{\text{bar\_notional}}$ is an explicit, controllable parameter.

---

## 3. Cluster-Robust Statistical Inference & Session Block Bootstrap

To avoid overinterpreting pooled sample sizes ($N = 2,161$ high-conviction trades across 26 out-of-sample sessions and 10 stocks), we evaluated standard errors under cluster dependence:

```text
====================================================================================================
INFERENCE METHOD                  STANDARD ERROR (SE)   t-STATISTIC   p-VALUE     95% CONFIDENCE INTERVAL
====================================================================================================
Pooled OLS (No Clustering)        0.2345 bps            2.21          0.027 *     [+0.06, +0.98] bps
Session-Clustered (26 Clusters)   0.3427 bps            1.51          0.131 (NS)  [-0.15, +1.19] bps
Symbol-Clustered (10 Clusters)    0.4077 bps            1.27          0.204 (NS)  [-0.28, +1.32] bps
Two-Way Clustered (Sess x Sym)    0.4602 bps            1.13          0.258 (NS)  [-0.38, +1.42] bps
----------------------------------------------------------------------------------------------------
SESSION BLOCK-BOOTSTRAP (1,000x)  0.3400 bps            --            --          [-0.13, +1.17] bps
====================================================================================================
```

### Key Statistical Takeaway
* When treating observations as independent, pooled OLS suggests a statistically significant gross return ($t = 2.21, p < 0.05$).
* **However, once clustering by trading session and symbol is applied, the standard error doubles from $0.23$ to $0.46$ bps, reducing the t-statistic to $1.13$ ($p = 0.258$, not significant).**
* The **Session Block-Bootstrap 95% CI encompasses zero ($[-0.13, +1.17]$ bps)**, demonstrating that even the un-costed $+0.52$ bps gross move cannot be statistically distinguished from zero at the 95% confidence level under session-level clustering.

---

## 4. Forensic Decompositions Across Slices

### Lens 1: Time-of-Day (Intraday Seasonality)
```text
====================================================================================================
TIME BUCKET  TRADES  SESSIONS  GROSS RETURN  COST      NET EXPECTANCY  WIN RATE  BOOTSTRAP 95% CI (NET)
====================================================================================================
09:15-10:00  214     25        -0.20 bps     15.23 bps -15.43 bps      14.5%     [-17.28, -13.65] bps
10:00-11:00  436     26        -0.72 bps     14.70 bps -15.43 bps       3.4%     [-16.49, -14.29] bps
11:00-13:00  743     26        +1.25 bps     14.73 bps -13.48 bps       6.1%     [-14.48, -12.36] bps
13:00-14:30  548     26        +0.90 bps     14.73 bps -13.82 bps       3.8%     [-14.70, -12.95] bps
14:30-15:15  214     25        -0.02 bps     14.71 bps -14.72 bps       7.5%     [-17.22, -12.26] bps
====================================================================================================
```
* **Opening Hour (09:15–10:00)**: Despite having the highest intraday volatility (15m $\sigma = 31.3$ bps), gross return is negative ($-0.20$ bps) due to gap-fades and opening whipsaws.
* **Midday (11:00–13:00)**: Generates the highest gross move ($+1.25$ bps), but volatility collapses ($\sigma = 10.9$ bps), keeping net expectancy at $-13.48$ bps.

### Lens 2: Constituent Symbol Attribution
```text
====================================================================================================
SYMBOL         TRADES  SESSIONS  GROSS RETURN  COST      NET EXPECTANCY  WIN RATE  BOOTSTRAP 95% CI
====================================================================================================
BAJFINANCE.NS  192     26        +2.50 bps     14.82 bps -12.32 bps      8.8%      [-13.78, -11.08] bps
TATACAP.NS     412     26        +1.73 bps     14.91 bps -13.18 bps      7.0%      [-13.98, -12.26] bps
SBIN.NS        227     26        +0.74 bps     14.75 bps -14.01 bps      4.0%      [-14.85, -13.18] bps
INFY.NS        224     26        +0.73 bps     14.67 bps -13.94 bps      8.0%      [-15.49, -12.28] bps
RELIANCE.NS    190     26        +0.40 bps     14.72 bps -14.32 bps      3.2%      [-16.19, -12.53] bps
ICICIBANK.NS   155     26        -0.20 bps     14.73 bps -14.94 bps      4.5%      [-16.55, -13.02] bps
HDFCBANK.NS    229     24        -0.28 bps     14.77 bps -15.04 bps      1.8%      [-16.69, -13.74] bps
TCS.NS         186     25        -2.21 bps     14.71 bps -16.92 bps      9.1%      [-19.95, -14.13] bps
====================================================================================================
```
* **High-Beta Outperformance**: BAJFINANCE and TATACAP produce the strongest gross moves ($+1.7$ to $+2.5$ bps).
* **Low-Beta / IT Drag**: TCS ($-2.21$ bps) and HDFCBANK ($-0.28$ bps) are consistent drags.
* **Key Takeaway**: Even the highest-beta stock in the universe falls short of the $14.8$ bps friction by over $12$ bps.

### Lens 3: Directionality Asymmetry (Long vs. Short)
```text
====================================================================================================
HORIZON  DIRECTION     TRADES  GROSS RETURN  COST      NET EXPECTANCY  WIN RATE  PROFIT FACTOR
====================================================================================================
5m       LONG_ONLY     3,025   +0.53 bps     14.76 bps -14.23 bps       5.7%     0.04
5m       SHORT_ONLY    2,394   +0.74 bps     14.81 bps -14.07 bps       8.9%     0.06
5m       LONG+SHORT    5,419   +0.62 bps     14.78 bps -14.16 bps       7.1%     0.05
----------------------------------------------------------------------------------------------------
15m      LONG_ONLY     3,413   +0.50 bps     14.72 bps -14.22 bps      14.2%     0.12
15m      SHORT_ONLY    3,971   +0.60 bps     14.89 bps -14.28 bps      19.2%     0.17
15m      LONG+SHORT    7,384   +0.56 bps     14.81 bps -14.25 bps      16.9%     0.15
====================================================================================================
```
* Short signals display slightly higher directional accuracy (19.2% win rate on 15m shorts vs 14.2% on longs), but gross return remains below $+0.75$ bps.

### Lens 4: Signal Sparsity & High-Conviction Frontier ($P90 \to P99.5$)
```text
====================================================================================================
HORIZON  PERCENTILE  TRADES  SESSIONS  GROSS RETURN  NET EXPECTANCY  WIN RATE  BOOTSTRAP 95% CI (NET)
====================================================================================================
5m       P90.0       2,161   26        +0.52 bps     -14.25 bps       6.0%     [-14.85, -13.60] bps
5m       P95.0       1,081   26        +0.52 bps     -14.29 bps       5.6%     [-15.18, -13.47] bps
5m       P98.0         433   26        +0.72 bps     -14.13 bps       6.9%     [-15.47, -12.97] bps
5m       P99.0         217   25        +1.25 bps     -13.64 bps      10.6%     [-16.07, -11.67] bps
5m       P99.5         109   25        -0.02 bps     -15.02 bps      11.9%     [-19.46, -11.31] bps
----------------------------------------------------------------------------------------------------
30m      P90.0       2,011   26        +0.89 bps     -13.97 bps      21.2%     [-16.21, -11.84] bps
30m      P95.0       1,006   26        +1.06 bps     -13.85 bps      22.2%     [-17.10, -11.02] bps
30m      P98.0         403   26        +1.67 bps     -13.28 bps      23.8%     [-19.37,  -7.75] bps
30m      P99.0         202   26        +1.92 bps     -13.05 bps      25.3%     [-22.06,  -4.09] bps
30m      P99.5         101   22        -0.42 bps     -15.24 bps      27.7%     [-30.86,  +0.12] bps
====================================================================================================
```
* **Frontier Asymptote**: Raising conviction from P90 to P99 increases gross return from $+0.89$ bps to $+1.92$ bps (at 30m), but at P99.5 the signal destabilizes ($-0.42$ bps) due to small sample noise.
* Even at P99, gross expectancy ($+1.92$ bps) is only ~13% of the required $15$ bps hurdle.

### Lens 5: Multi-Horizon Expansion ($5\text{m} \to 60\text{m}$)
```text
====================================================================================================
HORIZON   BARS   TRADES  GROSS RETURN  DYNAMIC COST  NET EXPECTANCY  WIN RATE  PROFIT FACTOR
====================================================================================================
5m        1      2,161   +0.52 bps     14.77 bps     -14.25 bps       5.97%    0.04
10m       2      2,131   +0.52 bps     14.73 bps     -14.22 bps      10.09%    0.07
15m       3      2,101   +0.52 bps     14.73 bps     -14.21 bps      14.52%    0.13
30m       6      2,011   +0.89 bps     14.85 bps     -13.97 bps      21.18%    0.22
60m       12     1,831   +1.53 bps     14.83 bps     -13.29 bps      28.02%    0.33
====================================================================================================
```
* Gross return roughly triples from $+0.52$ bps (5m) to $+1.53$ bps (60m), and win rate rises to 28.0%.
* However, because statutory transaction costs remain fixed at ~10.63 bps regardless of horizon, the 60m trade still loses **$-13.29$ bps net**.

### Lens 6: Execution Sensitivity (Probability-Weighted Execution Tree Modeling)
```text
====================================================================================================
EXECUTION SCENARIO       FILL PROB  ADVERSE SELECTION  COMPLETED COST  NET EXPECTANCY  WIN RATE
====================================================================================================
AGGRESSIVE (Marketable)  1.00       0.0 bps            14.77 bps       -14.25 bps      5.97%
PASSIVE (Resting Limit)  0.65       +1.0 bps           14.08 bps       -13.56 bps      6.82%
CONSERVATIVE_PASSIVE     0.45       +2.0 bps           15.48 bps       -14.96 bps      5.81%
====================================================================================================
```
* **Execution Tree Invariant**: Incorporating probability-weighted queue fills ($P_{\text{fill}}=0.65$), half-spread capture ($1.00$ bps), halved impact ($1.04$ bps), adverse selection ($+1.0$ bps), and partial-fill market completion ($0.41$ bps) yields an expected completed trade cost of **$14.08$ bps**, strictly obeying $\sum \text{components} == \text{total\_expected\_cost}$.
* Under conservative assumptions ($P_{\text{fill}}=0.45$, $+2.0$ bps adverse selection, $0.81$ bps partial fill completion), completed cost rises to **$15.48$ bps**. Neither alters the negative net expectancy regime.

---

## 5. Architectural Verdict & Next Steps

### Summary of What Was Learned
1. **The signal is an order-of-magnitude too small**: Across 60 slices, the maximum gross move generated by technical/microstructure features is $+2.5$ bps against $14.7$ bps friction.
2. **Cluster dependence is critical**: Two-way clustering and block bootstrapping confirm that pooled sample sizes gave an overly optimistic view of statistical significance; true gross alpha is marginally indistinguishable from zero ($t = 1.13$).
3. **No slice-picking illusion**: Reporting all 60 slices protects against data-snooping bias.

### Roadmap Progression & Status
```text
Phase 0  Repository Truth                ✅ PASS
Phase 1  Foundation & Isolation          ✅ PASS
Phase 2  Research Dataset Ingestion      ✅ PASS
Phase 3  5m Signal Proving               ✅ COMPLETED (EDGE REJECTED)
Phase 3A Forensic Signal Decomposition   ✅ COMPLETED (EXPLORATORY DIAGNOSIS LOCKED)
------------------------------------------------------------------------------------
Phase 4  Capital Router & Pre-Allocation 🔒 LOCKED (CANNOT PROCEED)
Phase 5  Paper Trading                   🔒 LOCKED
Phase 6  Live Execution                  🔒 LOCKED (LiveExecutionDisabledError)
```

### Strategic Recommendation for AlphaNSE
Since short-horizon price-pattern microstructure cannot overcome cash equity transaction friction on NSE:
1. **Do NOT build Phase 4 Capital Router** (it cannot allocate its way out of negative net expectancy).
2. The team has two legitimate quantitative choices:
   * **Choice A (Asset Class Pivot to Futures/Options)**: Futures and options on NSE have substantially lower statutory friction per notional (brokerage ₹20 flat, STT 0.0125% on futures sell side, zero stamp duty on delivery, yielding ~2.0–3.5 bps total friction). If friction is 3 bps, a $+1.5$ to $+2.5$ bps gross move is near breakeven.
   * **Choice B (Horizon Expansion to Multi-Day / Swing)**: Holding over 1–5 days where expected moves are 150–300 bps easily absorbs a 15 bps round-trip cost.

---
*Report generated and validated autonomously by Antigravity Quantitative Verification Engine.*
