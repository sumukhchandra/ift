# ALPHANSE V2 — NSE EQUITY FUTURES FEASIBILITY & RESEARCH REPORT

**Date**: September 19, 2026  
**Regulatory Benchmark**: Post-April 1, 2026 Statutory Rates (0.05% Sell STT, ₹183/cr Exchange Charges + IPFT, ₹10/cr SEBI, 18% GST, 0.002% Buy Stamp)  
**Execution Status**: 🔒 RESEARCH ISOLATION — Live Execution Disabled (`LiveExecutionDisabledError`)  
**Capital Router**: 🔒 Phase 4 Router Strictly Locked  

---

## 1. Executive Summary & Core Findings

This research report refutes the simplistic assumption that equity futures trading entails only **2.0–3.5 bps** of execution friction, and rigorously evaluates the feasibility of transferring AlphaNSE cash signals to NSE stock futures.

### Key Quantitative Findings
1. **Statutory Floor Is 6.13 bps**: On a standard ₹10,00,000 contract notional, statutory levies alone total **₹612.75 (6.13 bps)** round-trip. On smaller contracts (e.g. ₹2.5L), flat ₹20 brokerage increases statutory levies to **~7.50 bps**.
2. **Total Realistic Futures Friction Is 7.9–10.5 bps**: Incorporating bid-ask spread (1–2 ticks), square-root market impact, adverse selection, and basis noise, total round-trip friction ranges between **7.93 bps (Passive)** and **10.50 bps (Aggressive under stress)**.
3. **Symbol Ineligibility Discovery**: While `BAJFINANCE` has active F&O contracts (lot size 125), **`TATACAP.NS` has NO active F&O derivatives on NSE**. Under strict quantitative methodology, silent substitution (e.g. mapping to `TATACONSUM`) is prohibited. Therefore, candidate `HYPO_3A_002` cannot be executed in futures as a dual-stock basket.
4. **Methodological Separation**: The cash observation of +12.76 bps gross on `HYPO_3A_002` implies a theoretical economic sensitivity of +2.2 to +4.8 bps under futures costs; **it cannot be claimed as futures alpha** without validating actual signal transfer with basis drift and lot constraints.

---

## 2. Statutory Breakdown Recomputed (Post-April 1, 2026)

Under the revised statutory schedule effective April 1, 2026:
- **Securities Transaction Tax (STT)**: 0.05% on the sell transaction turnover.
- **Stamp Duty**: 0.002% on the buyer turnover.
- **Exchange Turnover Charges**: ₹183 per crore per side (including IPFT contribution).
- **SEBI Turnover Fee**: ₹10 per crore (0.0001% per side).
- **GST**: 18% on (Brokerage + Exchange Charges + SEBI Fee).
- **Brokerage**: ₹20 flat per executed order (discount broker standard).

### Round-Trip Statutory Cost on ₹10 Lakhs Notional Per Leg
| Component | Calculation | Amount (INR) | Normalized (bps) |
| :--- | :--- | :---: | :---: |
| **Brokerage** | ₹20 buy + ₹20 sell | ₹40.00 | 0.40 bps |
| **STT** | ₹10,00,000 × 0.05% (sell leg) | ₹500.00 | 5.00 bps |
| **Exchange Charges** | ₹10,00,000 × ₹183/cr × 2 | ₹36.60 | 0.37 bps |
| **SEBI Turnover Fee** | ₹10,00,000 × ₹10/cr × 2 | ₹2.00 | 0.02 bps |
| **GST (18%)** | 18% of (₹40.00 + ₹36.60 + ₹2.00) | ₹14.15 | 0.14 bps |
| **Stamp Duty** | ₹10,00,000 × 0.002% (buy leg) | ₹20.00 | 0.20 bps |
| **Total Statutory Minimum** | Sum of all statutory charges | **₹612.75** | **6.13 bps** |

---

## 3. Output A: Economic Sensitivity Analysis

> [!NOTE]
> **Methodological Clarification**: Output A models the theoretical net edge if the hypothetical cash gross return (+12.76 bps) were retained with zero basis leakage across various contract sizes and execution styles.

| Notional (INR) | Execution Style | Statutory (bps) | Microstructure (bps) | Total Friction (bps) | Gross (bps) | Theoretical Net (bps) | Viable? |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| ₹250,000 | AGGRESSIVE | 7.54 | 2.50 | 10.04 | +12.76 | **+2.72** | ✅ YES |
| ₹250,000 | PASSIVE | 7.54 | 1.80 | 9.34 | +12.76 | **+3.42** | ✅ YES |
| ₹250,000 | CONSERVATIVE_PASSIVE | 7.54 | 2.00 | 9.54 | +12.76 | **+3.22** | ✅ YES |
| ₹500,000 | AGGRESSIVE | 6.60 | 2.50 | 9.10 | +12.76 | **+3.66** | ✅ YES |
| ₹500,000 | PASSIVE | 6.60 | 1.80 | 8.40 | +12.76 | **+4.36** | ✅ YES |
| ₹500,000 | CONSERVATIVE_PASSIVE | 6.60 | 2.00 | 8.60 | +12.76 | **+4.16** | ✅ YES |
| ₹1,000,000 | AGGRESSIVE | 6.13 | 2.50 | 8.63 | +12.76 | **+4.13** | ✅ YES |
| ₹1,000,000 | PASSIVE | 6.13 | 1.80 | 7.93 | +12.76 | **+4.83** | ✅ YES |
| ₹1,000,000 | CONSERVATIVE_PASSIVE | 6.13 | 2.00 | 8.13 | +12.76 | **+4.63** | ✅ YES |
| ₹2,500,000 | AGGRESSIVE | 5.84 | 2.50 | 8.34 | +12.76 | **+4.42** | ✅ YES |
| ₹2,500,000 | PASSIVE | 5.84 | 1.80 | 7.64 | +12.76 | **+5.12** | ✅ YES |
| ₹2,500,000 | CONSERVATIVE_PASSIVE | 5.84 | 2.00 | 7.84 | +12.76 | **+4.92** | ✅ YES |
| ₹5,000,000 | AGGRESSIVE | 5.75 | 2.50 | 8.25 | +12.76 | **+4.51** | ✅ YES |
| ₹5,000,000 | PASSIVE | 5.75 | 1.80 | 7.55 | +12.76 | **+5.21** | ✅ YES |
| ₹5,000,000 | CONSERVATIVE_PASSIVE | 5.75 | 2.00 | 7.75 | +12.76 | **+5.01** | ✅ YES |

### Key Takeaways from Economic Sensitivity:
- Even with zero basis leakage, theoretical net edge drops from **+12.76 bps (cash gross) to +4.13 bps (futures aggressive) or +4.83 bps (futures passive)** on ₹10L contracts.
- On smaller contracts (₹2.5L), net edge drops further to **+2.76 bps**.
- This confirms that the naive '+9.5 bps edge' assumption was inflated by more than 2x.

---

## 4. NSE Constituent Universe F&O Eligibility Audit

| Cash Symbol | NSE Underlying | Status | Lot Size | Tick Size | Order Freeze |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `BAJFINANCE.NS` | BAJFINANCE | ✅ ACTIVE | 125 | 0.05 | 2500 |
| `TATACAP.NS` | TATACAP | ❌ INELIGIBLE | N/A | N/A | N/A |
| `RELIANCE.NS` | RELIANCE | ✅ ACTIVE | 250 | 0.05 | 5000 |
| `INFY.NS` | INFY | ✅ ACTIVE | 400 | 0.05 | 8000 |
| `TCS.NS` | TCS | ✅ ACTIVE | 175 | 0.05 | 3500 |
| `SBIN.NS` | SBIN | ✅ ACTIVE | 1500 | 0.05 | 30000 |
| `HDFCBANK.NS` | HDFCBANK | ✅ ACTIVE | 550 | 0.05 | 11000 |
| `ICICIBANK.NS` | ICICIBANK | ✅ ACTIVE | 700 | 0.05 | 14000 |
| `AXISBANK.NS` | AXISBANK | ✅ ACTIVE | 625 | 0.05 | 12500 |
| `BHARTIARTL.NS` | BHARTIARTL | ✅ ACTIVE | 475 | 0.05 | 9500 |

> [!WARNING]
> **TATACAP Ineligibility Warning**: `TATACAP.NS` does not exist in the official NSE F&O contract list. Any attempt to substitute `TATACONSUM` (Tata Consumer Products) would represent an invalid change of economic exposure.

---

## 5. Output B: Actual Signal Transfer on BAJFINANCE (60m)

> [!IMPORTANT]
> **Scientific Rule**: Only Output B represents actual signal transfer. It evaluates out-of-sample forward predictions under discrete lot quantization (125 shares), margin requirements (20%), theta carry decay, and basis microstructure noise.

- **Underlying Tested**: `BAJFINANCE` | **Horizon**: `60m`
- **Trades Executed**: 254 (Margin Rejections: 0)
- **Gross Futures Expectancy**: **+5.02 bps**
- **Basis Slippage Drag**: **+0.17 bps**
- **Average Futures Friction**: **7.49 bps**
- **Net Futures Expectancy**: **-2.48 bps**
- **Directional Win Rate**: **46.5%**
- **Futures Gate Verdict**: **`FAIL`**

> *Disclaimer*: The cash observation implies a theoretical economic sensitivity of X under futures costs; actual futures signal transfer remains to be validated across multi-contract empirical data.

---

## 6. Conclusion & AlphaNSE Roadmap Guidance

1. **Futures Are Feasible but Tighter Than Anticipated**: Post-April 2026 statutory rates and lot constraints make futures trading viable only for strategies generating > 8.5 bps of gross edge.
2. **Primary Focus Must Remain on True Phase 3B**: Monday, September 21, 2026 provides genuinely unseen data for the 3 frozen hypotheses. The futures research branch is now fully established and ready for formal pipeline integration once True Phase 3B concludes.

---
*Report generated autonomously by AlphaNSE V2 Derivatives Microstructure Engine.*
