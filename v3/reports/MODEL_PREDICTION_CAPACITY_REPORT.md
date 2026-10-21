# AlphaNSE V3 — Model Prediction Capacity & Real Stock Benchmark Report

**Session Date:** `Thursday, October 08, 2026`  
**Report Generated:** `2026-10-08 10:40:40 IST`  
**Benchmark Methodology:** Zero-lookahead Walk-Forward Prediction vs Real Intraday 1-Minute NSE Tape  
**Overall Fleet Directional Accuracy:** **57.4%** (224 correct of 390 forecasts)  

---

## 1. Model Capacity Scorecard

| Model ID | Symbol | Asset Name | Total Predictions | Directional Accuracy % | High-Conviction Hit Rate % | Mean Absolute Error (₹) | Mean Error (bps) |
|---|---|---|:---:|:---:|:---:|:---:|:---:|
| `SMC_4CONF_920` | `^NSEI` | NIFTY 50 | 65 | **56.9%** | **56.9%** | ₹5.93 | 2.6 bps |
| `V2_15M` | `INFY.NS` | Infosys | 65 | **61.5%** | **61.5%** | ₹0.52 | 5.2 bps |
| `HYPO001` | `TATACAP.NS` | Tata Capital | 65 | **63.1%** | **63.1%** | ₹0.15 | 4.8 bps |
| `HYPO002` | `BAJFINANCE.NS` | Bajaj Finance | 65 | **52.3%** | **40.7%** | ₹0.67 | 7.0 bps |
| `HYPO003` | `AXISBANK.NS` | Axis Bank | 65 | **46.1%** | **46.1%** | ₹0.88 | 7.1 bps |
| `V3_60M` | `RELIANCE.NS` | Reliance | 65 | **64.6%** | **63.0%** | ₹0.51 | 4.3 bps |

---

## 2. Sample Predictions vs Actual Real Market Closes

| Model | Bar Time | Initial Price (₹) | Predicted Price (₹) | Actual Next Close (₹) | Predicted Dir | Actual Dir | Match | Price Error (₹) |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `SMC_4CONF_920` | `2026-10-08 10:38:00` | ₹22,436.85 | ₹22,436.18 | ₹22,427.00 | DOWN | DOWN | ✅ | ₹9.18 |
| `SMC_4CONF_920` | `2026-10-08 10:39:00` | ₹22,427.00 | ₹22,426.38 | ₹22,426.85 | DOWN | DOWN | ✅ | ₹0.47 |
| `V2_15M` | `2026-10-08 10:38:00` | ₹1,007.95 | ₹1,007.92 | ₹1,007.40 | DOWN | DOWN | ✅ | ₹0.52 |
| `V2_15M` | `2026-10-08 10:39:00` | ₹1,007.40 | ₹1,007.38 | ₹1,007.60 | DOWN | UP | ❌ | ₹0.22 |
| `HYPO001` | `2026-10-08 10:38:00` | ₹317.10 | ₹317.07 | ₹317.15 | DOWN | UP | ❌ | ₹0.08 |
| `HYPO001` | `2026-10-08 10:39:00` | ₹317.15 | ₹317.13 | ₹317.15 | DOWN | FLAT | ✅ | ₹0.02 |
| `HYPO002` | `2026-10-08 10:38:00` | ₹957.00 | ₹956.90 | ₹957.60 | DOWN | UP | ❌ | ₹0.70 |
| `HYPO002` | `2026-10-08 10:39:00` | ₹957.60 | ₹957.50 | ₹957.65 | DOWN | UP | ❌ | ₹0.15 |
| `HYPO003` | `2026-10-08 10:38:00` | ₹1,246.50 | ₹1,246.49 | ₹1,247.90 | DOWN | UP | ❌ | ₹1.41 |
| `HYPO003` | `2026-10-08 10:39:00` | ₹1,247.90 | ₹1,247.88 | ₹1,246.70 | DOWN | DOWN | ✅ | ₹1.18 |
| `V3_60M` | `2026-10-08 10:38:00` | ₹1,188.70 | ₹1,188.53 | ₹1,188.20 | DOWN | DOWN | ✅ | ₹0.33 |
| `V3_60M` | `2026-10-08 10:39:00` | ₹1,188.20 | ₹1,188.05 | ₹1,188.00 | DOWN | DOWN | ✅ | ₹0.05 |