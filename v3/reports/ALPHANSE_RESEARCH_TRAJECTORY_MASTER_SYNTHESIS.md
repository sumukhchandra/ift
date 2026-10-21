# AlphaNSE V2 Quantitative Research Trajectory: Master Scientific Synthesis (Phases 10–16)

**Date:** 2026-10-02  
**Platform Version:** AlphaNSE V2 / V3 Hardened Quantitative Engine  
**Operational Status:** `PHASE_16_SWING_RESEARCH_ACTIVE` — Paper-Only / Research Mode  
**Live Safety Locks:** `LIVE_TRADING=False` | `ALLOW_REAL_ORDERS=False` (Strictly Enforced)

---

## Executive Overview

Over the course of 16 rigorous scientific validation phases, AlphaNSE transitioned from indicator-based technical heuristics to cross-sectional portfolio mechanics and, ultimately, structural economic remodeling.

Every single candidate hypothesis was audited under a **strict non-negotiable one-shot protocol**:
1. Pre-registration of rules and parameter freeze strictly on the **Research Set (June 29 – August 31, 2026)**.
2. One-shot out-of-sample evaluation on the **Locked September Test Set (September 1 – 25, 2026)**.
3. Modeling of full realistic execution friction (`ExecutionRegime.BASE` on ₹1,500 capital: slippage, bid-ask spread crossing, microstructure rejection, and complete Zerodha/NSE statutory charges).

---

## 1. Complete Trajectory Comparison Matrix (Phases 10 to 16)

| Phase | Hypothesis & Model Architecture | Research Net Expectancy | OOS Trades / Cycles | OOS Win Rate | OOS Gross Expectancy | BASE Friction | OOS Net Expectancy | OOS Profit Factor | Definitive Scientific Verdict |
|:---:|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **10** | Single-Stock 15m Breakdown + $L_2$ Logistic Gate | +₹2.50 | 5 trades | **0.0%** | -₹25.84/trd | ₹14.62/trd | **-₹40.46/trd** | 0.00 | 🔴 **Falsified & Frozen** (OOS Ranking Inversion) |
| **11** | Regime-Conditioned 30m ORB Breakout | -₹23.42 | 19 trades | **21.1%** | -₹5.24/trd | ₹13.13/trd | **-₹18.37/trd** | 0.64 | 🔴 **Falsified & Frozen** (Impulse Exhaustion) |
| **12** | Intraday Extreme VWAP Reversion ($Z \ge 2.5\sigma$) | -₹23.04 | 7 trades | **0.0%** | -₹8.97/trd | ₹13.27/trd | **-₹22.24/trd** | 0.00 | 🔴 **Falsified & Frozen** (Friction-Reversion Trap) |
| **13** | 2-Day Cross-Sectional Reversal (`CS_DIR_REV_2D`) | +₹2.24 | 17 trades | **41.2%** | **+₹4.66/trd** | ₹13.12/trd | **-₹8.47/trd** | **1.25** | 🟡 **Gross Edge Confirmed** (Tail-Loss Erosion) |
| **14** | Cross-Sectional Risk Management / Stop Audit | +₹6.92 | 17 trades | **41.2%** | **+₹2.67/trd** | ₹13.13/trd | **-₹10.46/trd** | **1.12** | 🟡 **Stop-Loss Paradox** (Stops Degrade Alpha) |
| **15** | Alpha Persistence & Economic Scalability Audit | +₹6.92 | 17 trades | **41.2%** | **+3.5 bps** | 5.9 bps floor | **-2.5 bps** | 1.12 | 🔴 **Scale Infeasible** (Friction Floor Exceeds Gross) |
| **16** | Multi-Day Swing Reversal (`SWING_REV_3D_MACRO`) | **+0.31%/cycle (+4.08% net)** | **5 cycles** | **N/A (Cash)** | **0.00%** | **0.00%** | **0.00%** | **N/A** | 🟢 **Economically Viable** (OOS Active Net Unverified) |

---

## 2. Key Forensic Discoveries Across the Research Arc

### Discovery 1: The Failure of Intraday Single-Stock Heuristics (Phases 10–12)
* **Phase 10:** Adding an $L_2$ logistic regression hurdle on technical features (RSI, ADX, candle body, ATR distance) resulted in **complete out-of-sample inversion**: 5/5 model-gated September trades lost, while all 5 actual September winners were rejected.
* **Phase 11:** 30-minute opening range breakouts suffered from **adverse selection**: 78.9% of trades failed to achieve even +0.45% MFE because entering after a 30m expansion buys/sells at the local extrema of an already exhausted morning impulse.
* **Phase 12:** Fading extreme intraday VWAP deviations ($Z \ge 2.5\sigma$) revealed the **Friction-Reversion Trap**: when reversions occurred, gross price moves were only +13 to +22 bps (+₹9.50 to +₹16.00), which were smaller than the ₹16.96 to ₹17.62 transaction cost. When trends continued, stop losses incurred severe -₹35 to -₹45 losses.

### Discovery 2: The Intraday Structural Friction Barrier (Phases 13–15)
* **Phase 13:** Switching the hypothesis from predicting absolute single-stock noise to cross-sectional ranking across the 10 liquid constituents produced the first positive out-of-sample gross alpha (+₹4.66/trade, Profit Factor = 1.25).
* **Phase 14:** Attempting to prune tail losses with stops revealed the **Stop-Loss Paradox**: cross-sectional mean reversion naturally experiences morning noise (MAE ~0.6% to 1.1%). Tight stops choked off recovering winners and degraded research net expectancy from +₹6.92 down to -₹4.13.
* **Phase 15:** Scaling analysis proved that across all capital levels (from ₹1,500 to ₹2,00,000), the gross cross-sectional drift was constant at **+3.5 basis points of turnover**, while the asymptotic statutory friction floor (STT, exchange fees, SEBI, GST, spread, slippage) is **5.9 basis points of turnover**. **The intraday strategy was mathematically incapable of achieving net profitability at ANY capital scale.**

### Discovery 3: Multi-Day Swing Economic Solvency (Phase 16)
* By expanding the holding horizon from intraday (1 session) to **multi-day swing holding (3 trading days)**:
  * Turnover was slashed by 67%.
  * Average gross move expanded from intraday noise (~35 bps) to **+58 basis points per cycle**.
  * Roundtrip delivery friction (~35 bps) consumed only **37% of the gross profit**, yielding **+0.31% net per cycle (+4.08% cumulative net)** and a **70% win rate** on the Research Set.
* In the locked September test set, the pre-registered NIFTY 50 EMA cash filter activated across all 5 cycles, successfully preserving 100% of capital (0.00% drawdown) while the benchmark crashed **-4.6%** and multi-day momentum strategies lost **-10.74%**.

---

## 3. Current Platform Architecture & Operational Status

```text
Platform Engineering State:
├── DhanHQ v2.2.0 API Handshake       🟢 Verified (Read-Only Test Engine Active)
├── Market Data Risk Guards           🟢 11/11 Passing (Clock drift, circuit limits, depth locks)
├── Realistic Microstructure Broker   🟢 6/6 Passing (Spread, slippage, statutory taxes, EOD invariants)
└── Multi-Phase Audit Trails          🟢 100% Documented in v3/reports/

Strategy Deployment State:
├── Intraday Indicator Strategies     🔴 Permanently Rejected & Frozen (Phases 10–12)
├── Intraday Cross-Sectional Models   🔴 Permanently Rejected & Frozen (Phases 13–15)
├── Multi-Day Swing Strategy          🟡 PHASE_16_SWING_RESEARCH_ACTIVE (Paper-Only)
└── Real-Money Execution Gates        🔒 STRICTLY LOCKED (LIVE_TRADING=False, ALLOW_REAL_ORDERS=False)
```

---

## 4. Next Scientific Phase Charter: Forward Paper Validation

Before any consideration of live execution can occur, `SWING_REV_3D_MACRO` must accumulate out-of-sample forward paper sessions where the broad market turns bullish/neutral and active 3-day swing positions are executed.

### Tracked Forward Metrics:
1. **Gross Price Move per Cycle:** Must exceed 50 basis points.
2. **Delivery Friction Consumption:** Must remain below 40% of gross move.
3. **Out-of-Sample Net Win Rate:** Must stabilize above 55%.
4. **Out-of-Sample Profit Factor:** Must exceed 1.50 after all delivery costs.

**Final Mandate:**  
AlphaNSE will remain strictly in paper-trading / research mode until the forward validation criteria are empirically satisfied.
