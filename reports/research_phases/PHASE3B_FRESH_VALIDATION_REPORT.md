# ALPHANSE V2 — PHASE 3B CANDIDATE HYPOTHESIS FALSIFICATION REPORT

**Evaluation Mode**: `FRESH_VALIDATION` (Fresh Validation)  
**Evaluation Date**: September 24, 2026  
**Capital Router Status**: 🔒 STRICTLY LOCKED  
**Live Execution Status**: 🔒 PHYSICALLY DISABLED (`LiveExecutionDisabledError`)  

---

## 1. Executive Summary

Phase 3B was executed as a pre-registered **falsification test** across the three frozen candidate hypotheses generated during Phase 3A forensic exploration.

### Candidate Comparison Summary Table

| Candidate ID | Horizon | Scenario | Gross (bps) | Cost (bps) | Base Net | Stress Net | 95% CI (Net) | Win Rate | Worst Fold | Pos Folds | Trades | Sessions | Gate Verdict |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **HYPO_3A_001_30M_MIDDAY_TREND** | 30m | BASE_AGGRESSIVE | +6.90 | 14.70 | -7.80 | -9.83 | [-7.80, -7.80] | 33.3% | -7.80 bps | 0/1 | 24 | 2 | **INCONCLUSIVE** |
| **HYPO_3A_002_60M_HIGH_BETA** | 60m | PASSIVE | +41.39 | 14.08 | +27.31 | +25.58 | [+27.31, +27.31] | 64.0% | +27.31 bps | 1/1 | 25 | 2 | **INCONCLUSIVE** |
| **HYPO_3A_003_15M_SHORT_SPARSITY** | 15m | CONSERVATIVE_PASSIVE | +0.00 | 15.48 | +0.00 | +0.00 | [-999.00, -999.00] | 0.0% | -999.00 bps | 0/0 | 0 | 0 | **INCONCLUSIVE_NO_ELIGIBLE_TRADES** |

---

## 2. Detailed 11-Point Edge Gate Criteria Breakdown

### Candidate: `HYPO_3A_001_30M_MIDDAY_TREND`
* **Horizon**: 30m | **Scenario**: BASE_AGGRESSIVE | **Trades**: 24 | **Sessions**: 2
* **Net Expectancy**: Base = **-7.80 bps** | Stressed = **-9.83 bps**
* **Session Block-Bootstrap 95% CI**: [-7.80, -7.80] bps
* **Gate Verdict**: **INCONCLUSIVE** (`INCONCLUSIVE`)

| # | Criterion | Passed? | Metric Details |
| :-: | :--- | :---: | :--- |
| 1 | 1. Mean Baseline Net Expectancy > 0 | ❌ FAIL | Observed = -7.80 bps (Threshold > 0.00 bps) |
| 2 | 2. Mean Stressed Net Expectancy >= 0 | ❌ FAIL | Observed = -9.83 bps (Threshold >= 0.00 bps under 1.5x friction) |
| 3 | 3. Session Bootstrap 95% CI Lower Bound > 0 | ❌ FAIL | Observed 95% CI = [-7.80, -7.80] bps |
| 4 | 4. Positive Net Expectancy in >= 60% Folds | ❌ FAIL | Positive Folds = 0/1 (0.0%, Threshold >= 60%) |
| 5 | 5. No Catastrophic Fold (Worst Fold >= -Cost) | ✅ PASS | Worst Fold Net = -7.80 bps (Threshold >= -14.70 bps) |
| 6 | 6. Maximum Drawdown < 5.0% | ✅ PASS | Observed Max Drawdown = 2.02% (Threshold < 5.0%) |
| 7 | 7. Directional Win Rate > 51.5% | ❌ FAIL | Observed Win Rate = 33.33% (Threshold > 51.5%) |
| 8 | 8. Out-of-Sample IC >= 0.030 | ✅ PASS | Observed Pearson IC = 0.1080 (Threshold >= 0.0300) |
| 9 | 9. Sample Trade Count >= 30 | ❌ FAIL | Observed Trades = 24 (Threshold >= 30) |
| 10 | 10. Sample Session Count >= 10 | ❌ FAIL | Observed Sessions = 2 (Threshold >= 10) |
| 11 | 11. Multi-Fold Coverage >= 3 Folds | ❌ FAIL | Observed Folds = 1 (Threshold >= 3) |

### Candidate: `HYPO_3A_002_60M_HIGH_BETA`
* **Horizon**: 60m | **Scenario**: PASSIVE | **Trades**: 25 | **Sessions**: 2
* **Net Expectancy**: Base = **+27.31 bps** | Stressed = **+25.58 bps**
* **Session Block-Bootstrap 95% CI**: [+27.31, +27.31] bps
* **Gate Verdict**: **INCONCLUSIVE** (`INCONCLUSIVE`)

| # | Criterion | Passed? | Metric Details |
| :-: | :--- | :---: | :--- |
| 1 | 1. Mean Baseline Net Expectancy > 0 | ✅ PASS | Observed = +27.31 bps (Threshold > 0.00 bps) |
| 2 | 2. Mean Stressed Net Expectancy >= 0 | ✅ PASS | Observed = +25.58 bps (Threshold >= 0.00 bps under 1.5x friction) |
| 3 | 3. Session Bootstrap 95% CI Lower Bound > 0 | ✅ PASS | Observed 95% CI = [+27.31, +27.31] bps |
| 4 | 4. Positive Net Expectancy in >= 60% Folds | ✅ PASS | Positive Folds = 1/1 (100.0%, Threshold >= 60%) |
| 5 | 5. No Catastrophic Fold (Worst Fold >= -Cost) | ✅ PASS | Worst Fold Net = +27.31 bps (Threshold >= -14.08 bps) |
| 6 | 6. Maximum Drawdown < 5.0% | ✅ PASS | Observed Max Drawdown = 1.72% (Threshold < 5.0%) |
| 7 | 7. Directional Win Rate > 51.5% | ✅ PASS | Observed Win Rate = 64.00% (Threshold > 51.5%) |
| 8 | 8. Out-of-Sample IC >= 0.030 | ❌ FAIL | Observed Pearson IC = -0.2483 (Threshold >= 0.0300) |
| 9 | 9. Sample Trade Count >= 30 | ❌ FAIL | Observed Trades = 25 (Threshold >= 30) |
| 10 | 10. Sample Session Count >= 10 | ❌ FAIL | Observed Sessions = 2 (Threshold >= 10) |
| 11 | 11. Multi-Fold Coverage >= 3 Folds | ❌ FAIL | Observed Folds = 1 (Threshold >= 3) |

### Candidate: `HYPO_3A_003_15M_SHORT_SPARSITY`
* **Horizon**: 15m | **Scenario**: CONSERVATIVE_PASSIVE | **Trades**: 0 | **Sessions**: 0
* **Net Expectancy**: Base = **+0.00 bps** | Stressed = **+0.00 bps**
* **Session Block-Bootstrap 95% CI**: [-999.00, -999.00] bps
* **Gate Verdict**: **INCONCLUSIVE** (`INCONCLUSIVE_NO_ELIGIBLE_TRADES`)

| # | Criterion | Passed? | Metric Details |
| :-: | :--- | :---: | :--- |
| Sample Size | Sample Size | ❌ FAIL | Insufficient trades (0 < 30) |

---

## 3. Methodological Invariants Enforced

1. **No Candidate Tuning / Replacement**: The candidate set was strictly locked to `HYPO_3A_001`, `HYPO_3A_002`, and `HYPO_3A_003`. All definition hashes matched their frozen records.
2. **Execution Tree Cost Model**: Passive and conservative passive scenarios incorporated probability-weighted queue fill, half-spread capture, adverse selection, and partial-fill completion penalties.
3. **Physical Safety Gate**: Capital Router and Live Execution remain 100% locked.

---
*Report generated autonomously by AlphaNSE V2 Phase 3B Falsification Engine.*
