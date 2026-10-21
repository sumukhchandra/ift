# AlphaNSE V3 — Session 6 Multi-Model Pre-Market Readiness Report

> [!IMPORTANT]
> **CLASSIFICATION: FRESH FORWARD VALIDATION (SESSION 5 ONWARD)**  
> **SYSTEM**: AlphaNSE V3 Multi-Model Ensemble Architecture  
> **PROFITABILITY CLAIM**: False (Unproven experimental hypothesis)  
> **SAFETY**: Broker execution remains physically disabled; Capital router locked; Paper/Shadow only.

## 1. Session Provenance & Data Invariants

- **Target Session Date**: `2026-09-28`
- **Data Cutoff (D-1)**: `2026-09-25T15:25:00+05:30`
- **Zero-Lookahead Guarantee**: Strictly `< 2026-09-28 00:00:00 IST`
- **Dataset SHA-256 Hash**: `9f24d861f7633b85ad052076de3d0d021d4e5382e16e11ca67d09fbb1e290dd2`
- **Feature Schema Hash**: `cdc70e950012b43a`
- **Master Model Version**: `AlphaNSE_V3_MultiModel_20260928_v1`
- **Master SHA-256 Hash**: `ae5ef88845dc18a327bd264f4eab853217ba96ce63034c19b7462993137407f5`
- **Pre-Market Regime**: `NORMAL_VOL`

## 2. Model Status Summary

| Model ID | Research Identity | Horizon | Direction | In-Sample IC | Training Rows | Model SHA-256 Hash | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- | :---: |
| **V2_15M** | Baseline Ridge return regressor targeting 15m forward return | 15m | LONG_AND_SHORT | +0.0498 | 45,361 | `9df76ca0e77820ec...` | **FROZEN** |
| **HYPO001** | Midday trend following regressor targeting 30m forward return | 30m | LONG_AND_SHORT | +0.0610 | 43,438 | `bbdc186b7660254f...` | **FROZEN** |
| **HYPO002** | Extended horizon high-beta momentum regressor targeting 60m forward return | 60m | LONG_AND_SHORT | +0.0812 | 39,592 | `0504811cd1698410...` | **FROZEN** |
| **HYPO003** | Opportunistic downside exhaustion regressor targeting 15m short return | 15m | SHORT_SPARSITY | +0.0498 | 45,361 | `9df76ca0e77820ec...` | **FROZEN** |
| **V3_60M** | Adaptive cost-aware Ridge return regressor targeting 60m forward return | 60m | LONG_AND_SHORT | +0.0812 | 39,592 | `f90642acca20ad7c...` | **FROZEN** |

- **Total Models Registered**: 5
- **Valid Models Active**: 5/5
- **Ensemble Readiness**: `READY`
- **Failure Isolation**: Verified (no silent substitutions)

## 3. Ensemble Decision Engine Specifications

| Parameter | Setting | Operational Principle |
| :--- | :--- | :--- |
| **Consensus Mechanism** | Horizon-Aware Directional Agreement | Separate 15m, 30m, and 60m horizons; no blind averaging |
| **Agreement Tracking** | 0/5 to 5/5 agreement | Explicit attribution of supporting vs contradicting models |
| **Economic Hurdle** | ≥ ₹0.80 Net Profit per Trade | Expected gross ₹ must exceed all-in transaction friction + ₹0.80 |
| **Statutory Costing** | IndiaCostEngine Zerodha Schedule | Brokerage + STT + Exchange + SEBI + Stamp + GST |
| **Execution Friction** | DynamicCostModel Aggressive | Spread + Slippage + Market Impact |
| **Capital Sizing** | Whole-Share Integer Sizing | Sized within ₹5,000 paper capital (Max 95% allocation) |
| **Trading Windows** | 09:15–12:00 & 14:00–14:25 IST | Lunch Blackout (12:00–14:00), 14:25 Entry Cutoff, 15:25 Flattening |
| **Cash Policy** | Cash is valid and intentional | If expected net return < ₹0.80, HOLD CASH (0 trades) |
| **Mid-Session Policy** | STRICT FREEZE | Zero retraining, zero parameter adjustments during session |

## 4. Operational Safety Invariants

- [x] `LiveExecutionDisabledError` physically active in codebase.
- [x] `CapitalRouter` locked to paper simulation mode.
- [x] Zero broker order transmission.
- [x] Historical V2 evidence sealed and untouched (188 trades, -₹378.61).
- [x] Phase 3B historical candidate records preserved.
- [x] Multi-model artifacts isolated under `v3/models/multimodel/`.
