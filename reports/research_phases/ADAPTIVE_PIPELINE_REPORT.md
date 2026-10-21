# ALPHANSE V2 — ADAPTIVE DAILY RETRAINING & TRADING REPORT

**Generated**: 2026-09-24 08:46:12 IST  
**Sessions Evaluated**: 4  
**Capital Router**: 🔒 STRICTLY LOCKED  
**Live Execution**: 🔒 PHYSICALLY DISABLED (`LiveExecutionDisabledError`)  

---

## 1. Executive Performance Summary

| Metric | Target Standard | Observed Result | Status |
| :--- | :---: | :---: | :---: |
| **Average Net Profit / Trade** | $\ge ₹0.80$ | **₹-2.01** | ❌ FAIL |
| **Total Evaluated Trades** | $\ge 30$ / day | **188** (47.0 / day) | ✅ PASS |
| **Directional Win Rate** | $> 51.5\%$ | **23.4%** | ❌ FAIL |
| **Cumulative Net PnL (₹5k Portfolio)** | $> ₹0.00$ | **₹-378.61** | ❌ FAIL |

---

## 2. Session-by-Session Adaptive Retraining Ledger

| Session Date | Model Version | Regime at Open | Pre-Market Cutoff | Trades | Net PnL (₹) | Avg Profit/Trade | Win Rate | Ending Capital |
| :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **2026-09-21** | `AlphaNSE_Adaptive_20260921_v1` | `NORMAL_VOL` | `2026-09-18` | 43 | ₹-76.91 | ₹-1.79 | 25.6% | ₹4923.11 |
| **2026-09-22** | `AlphaNSE_Adaptive_20260922_v1` | `NORMAL_VOL` | `2026-09-21` | 49 | ₹-106.08 | ₹-2.16 | 22.4% | ₹4817.04 |
| **2026-09-23** | `AlphaNSE_Adaptive_20260923_v1` | `NORMAL_VOL` | `2026-09-22` | 35 | ₹-51.32 | ₹-1.47 | 20.0% | ₹4765.73 |
| **2026-09-24** | `AlphaNSE_Adaptive_20260924_v1` | `NORMAL_VOL` | `2026-09-23` | 61 | ₹-144.30 | ₹-2.37 | 24.6% | ₹4621.42 |

---

## 3. Cryptographic Model & Lineage Audit Manifest

Every session retrains strictly on data available prior to market open, freezing a verifiable model:

| Session | Model Hash (SHA-256) | Dataset Hash (SHA-256) | Training Rows | Val IC |
| :--- | :--- | :--- | :---: | :---: |
| `2026-09-21` | `ee3a724ade5c877f6568...` | `62c14fe79e4bb551500a...` | 48009 | 0.0681 |
| `2026-09-22` | `2ecdbb19944091805ad2...` | `3bd599dcd7bd17aa414f...` | 48811 | 0.0830 |
| `2026-09-23` | `f9edf69b45996d946705...` | `c3327a106298428b69fc...` | 49609 | 0.0621 |
| `2026-09-24` | `656100130c8ecb7725cc...` | `eeabd8d8a6360325b828...` | 50407 | 0.0880 |

---

## 4. Methodological Invariants Enforced

1. **Zero Lookahead Guarantee**: For every session Day D, training data strictly ends at Day D-1 15:25 IST.
2. **Pre-Market Model Freezing**: Model weights are frozen prior to market open and remain unchanged during intraday trading.
3. **Dynamic Cost Realism**: All trades account for Zerodha statutory taxes (STT, stamp duty, turnover charges, SEBI, GST), half-spread, and impact slippage.
4. **Integer Position Sizing**: Whole shares sized dynamically on ₹5,000 cash balance via `IntegerPositionSizer`.

---
*Report generated autonomously by AlphaNSE V2 Adaptive Daily Pipeline Engine.*
