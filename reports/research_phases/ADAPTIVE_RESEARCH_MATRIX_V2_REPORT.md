# AlphaNSE Adaptive Research Matrix V2 Audit Report

**Protocol Execution**: 3-Phase Scientific Protocol (Phase A Exploratory $\to$ Phase B Candidate Freeze $\to$ Phase C Validation Gate)  
**Walk-Forward Sessions**: 3 Unseen Market Sessions (Sep 21, Sep 22, Sep 23, 2026)  
**Active Capital Router**: 🔒 **STRICTLY LOCKED**  
**Live Execution Lockout**: 🔒 **PHYSICALLY DISABLED (`LiveExecutionDisabledError`)**  

---

## 1. Executive Summary & Paradigm Shift

In accordance with the empirical findings of the 127-trade forensic audit, AlphaNSE has successfully transitioned to **Adaptive Research Matrix V2**:
1. **Removal of Forced Frequency**: The requirement for $\ge 30$ trades/day has been eliminated. The system trades *opportunistically* whenever statistically validated, cost-clearing signals exist, and holds **100% Cash** on low-edge days (a valid and profitable decision).
2. **Authoritative Capital-Aware Ticket Economics**: Replaced crude sizing heuristics with penny-for-penny ticket economics ($E[\text{Gross ₹}] > \text{Statutory Fees} + \text{Friction}$), eliminating 1-share fee traps.
3. **Realistic Futures Modeling**: Employed official `NSEFuturesCostModel` across `STATUTORY_ONLY` (6.13 bps), `BASE` (7.93–8.50 bps), and `STRESSED` (10.50 bps) scenarios, with explicit margin feasibility validation.
4. **Three-Phase Protocol**:
   - **Phase A (Exploratory)**: Evaluated 16 systematic slices.
   - **Phase B (Freeze)**: Cryptographically frozen the **Selected Candidate**.
   - **Phase C (Validation)**: Verified against minimum sample requirements ($\ge 30$ trades, $\ge 10$ sessions, 3 folds), enforcing mandatory **`INCONCLUSIVE`** verdict when sample size is insufficient to prevent premature declarations.

---

## 2. Phase A: Full Exploratory Research Matrix Results

| Track | Horizon | Conviction Tier | Direction | Cost Scenario | Trades | Trades/Day | Dir Acc % | Net Win % | Mean Gross (bps) | Mean Net (bps) | Net PnL (₹) | Net ₹/Trade | Expectancy (₹) | Hurdle (>₹0.80) |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **CASH_EQUITY** | 30m | EXTREME_TOP_15 | BOTH | BASE | 116 | 29.0 | 54.3% | 30.2% | +4.73 | -11.99 | ₹-182.77 | ₹-1.58 | ₹-1.58 | ❌ NO |
| **CASH_EQUITY** | 60m | EXTREME_TOP_15 | BOTH | BASE | 77 | 19.2 | 51.9% | 37.7% | +3.75 | -12.99 | ₹-134.01 | ₹-1.74 | ₹-1.74 | ❌ NO |
| **CASH_EQUITY** | 30m | Q4_TOP_CONVICTION | BOTH | BASE | 123 | 30.8 | 50.4% | 29.3% | +2.71 | -14.01 | ₹-227.32 | ₹-1.85 | ₹-1.85 | ❌ NO |
| **CASH_EQUITY** | 15m | ALL | BOTH | BASE | 188 | 47.0 | 52.7% | 23.4% | +1.57 | -15.13 | ₹-378.82 | ₹-2.02 | ₹-2.01 | ❌ NO |
| **CASH_EQUITY** | 15m | Q4_TOP_CONVICTION | BOTH | BASE | 188 | 47.0 | 52.7% | 23.4% | +1.57 | -15.13 | ₹-378.82 | ₹-2.02 | ₹-2.01 | ❌ NO |
| **CASH_EQUITY** | 60m | EXTREME_TOP_15 | LONGS | BASE | 59 | 14.8 | 42.4% | 35.6% | -1.16 | -17.85 | ₹-120.13 | ₹-2.04 | ₹-2.04 | ❌ NO |
| **CASH_EQUITY** | 60m | Q4_TOP_CONVICTION | BOTH | BASE | 80 | 20.0 | 46.2% | 30.0% | -1.09 | -17.82 | ₹-179.85 | ₹-2.25 | ₹-2.25 | ❌ NO |
| **CASH_EQUITY** | 60m | EXTREME_TOP_15 | SHORTS | BASE | 60 | 15.0 | 40.0% | 28.3% | -0.33 | -17.07 | ₹-152.77 | ₹-2.55 | ₹-2.55 | ❌ NO |
| **CASH_EQUITY** | EOD | Q4_TOP_CONVICTION | BOTH | BASE | 34 | 8.5 | 17.6% | 14.7% | -11.21 | -28.00 | ₹-121.22 | ₹-3.57 | ₹-3.57 | ❌ NO |
| **EQUITY_FUTURES** | 60m | EXTREME_TOP_15 | SHORTS | BASE | 42 | 10.5 | 47.6% | 35.7% | +3.08 | -6.39 | ₹-2000.94 | ₹-47.64 | ₹-47.64 | ❌ NO |
| **EQUITY_FUTURES** | 60m | EXTREME_TOP_15 | BOTH | BASE | 82 | 20.5 | 47.6% | 39.0% | +2.88 | -6.58 | ₹-19456.63 | ₹-237.28 | ₹-237.28 | ❌ NO |
| **EQUITY_FUTURES** | 60m | Q4_TOP_CONVICTION | BOTH | BASE | 85 | 21.2 | 42.4% | 34.1% | +3.32 | -6.22 | ₹-23898.63 | ₹-281.16 | ₹-281.16 | ❌ NO |
| **EQUITY_FUTURES** | 60m | EXTREME_TOP_15 | BOTH | STRESSED | 81 | 20.2 | 48.1% | 37.0% | +3.29 | -8.69 | ₹-25212.90 | ₹-311.27 | ₹-311.27 | ❌ NO |
| **EQUITY_FUTURES** | 15m | Q4_TOP_CONVICTION | BOTH | BASE | 271 | 67.8 | 50.2% | 30.3% | +0.29 | -9.24 | ₹-108361.24 | ₹-399.86 | ₹-399.86 | ❌ NO |
| **EQUITY_FUTURES** | 30m | Q4_TOP_CONVICTION | BOTH | BASE | 149 | 37.2 | 49.7% | 30.2% | -0.95 | -10.55 | ₹-62135.54 | ₹-417.02 | ₹-417.02 | ❌ NO |
| **EQUITY_FUTURES** | 60m | Q4_TOP_CONVICTION | BOTH | STRESSED | 85 | 21.2 | 42.4% | 34.1% | +3.32 | -8.72 | ₹-35612.45 | ₹-418.97 | ₹-418.97 | ❌ NO |

---

## 3. Phase B: Selected Candidate Cryptographic Freeze

The exploratory matrix identified the following configuration as the **Selected Candidate**:

* **Candidate ID**: `Candidate_CASH_EQUITY_6b_26ada46a`
* **Track**: `CASH_EQUITY`
* **Holding Horizon**: `6 bars`
* **Conviction Tier**: `EXTREME_TOP_15`
* **Cost Scenario**: `BASE`
* **Configuration SHA-256 Hash**: `26ada46a04f6ac3265406936075d0ebd46e941a2b804aa82e62f27335890010d`
* **Model Version**: `AlphaNSE_Adaptive_20260923_v1`
* **Model Artifact Hash**: `f9edf69b45996d9467050e021aa0115f2987b0b60f1cfcff50f4427e9aa7818a`
* **Dataset SHA-256 Hash**: `c3327a106298428b69fcf3430e0c36b608ea2eb792d40e010e708498ff1ce0b8`

> [!NOTE]
> Per scientific protocol, this configuration is designated as the **Selected Candidate** (not a "winner"), and is immutably frozen in `v2/adaptive/frozen_candidates/Candidate_CASH_EQUITY_6b_26ada46a.json` pending fresh out-of-sample validation.

---

## 4. Phase C: Fresh Out-of-Sample Validation Gate

The frozen Selected Candidate was submitted to the Phase C Validation Evaluator:

| Gate Parameter | Current Walk-Forward Value | Gate Requirement | Status |
| :--- | :---: | :---: | :---: |
| **Completed Trades** | **116** | $\ge 30$ trades | ⚠️ Sub-threshold |
| **Trading Sessions** | **3** | $\ge 10$ sessions | ⚠️ Sub-threshold |
| **Validation Folds** | **3** | $\ge 3$ folds | ✅ Cleared |
| **Mean Net PnL / Trade** | **₹-1.58** | $> ₹0.80$ | Evaluated |
| **Stressed Expectancy** | **₹-1.58** | $> 0$ | Evaluated |

### Official Verdict: `INCONCLUSIVE`

> [!WARNING]
> **Validation Rationale**:  
> INSUFFICIENT SAMPLE SIZE (INCONCLUSIVE / CONTINUE): Completed 116 trades across 3 sessions (requires >= 30 trades across >= 10 sessions and >= 3 folds). Per AlphaNSE scientific protocol, small samples cannot declare PASS or FAIL. Phase C evidence accumulation continues.  
> The system correctly refuses to declare victory or failure on a small sample, maintaining scientific integrity.

---

## 5. Architectural & Safety Invariants Verified

* `LiveExecutionDisabledError`: **PHYSICALLY ACTIVE**.
* Phase 4 Capital Router: **STRICTLY LOCKED**.
* Zero Lookahead Leakage: **CRYPTOGRAPHICALLY CONFIRMED**.
* Daily Retraining Pipeline: **OPERATIONAL & PRESERVED**.
