# AlphaNSE V3 & Phase 16: Forward Paper Multi-Model Monitoring Report

**Report Generated:** `2026-10-05 15:55:38 IST`  
**Safety Governance:** `LIVE_TRADING=False` | `ALLOW_REAL_ORDERS=False` (Strictly Air-Gapped)  
**Active Forward Candidate:** `SWING_REV_3D_MACRO` (Holding: 3 Days, Lookback: 5 Days, Reversal + Macro)  
**Allocated Paper Capital:** `₹1,500.00` per model | **Modeled Delivery Friction:** `35 bps (0.35%)`

---

## 1. Model/Strategy Inventory

| # | Model ID | Strategy / Model Name | Category | Asset Focus | Operational Status | Role / Notes |
| :---: | :--- | :--- | :--- | :--- | :---: | :--- |
| 1 | **`SWING_REV_3D_MACRO`** | Phase 16 3-Day Swing Reversal + Macro Filter | `MULTI_DAY_SWING` | Universe Equities (Bottom 2) | **`PAPER-ONLY (CASH_PRESERVATION)`** | Primary Gate 1 Forward Validation Candidate |
| 2 | **`SMC_4CONF_920`** | SMC 4-Confirmation Sniper & 9:20 Straddle | `INTRADAY_INDEX` | ^NSEI (NIFTY 50 Index) | **`PAPER-ONLY (INACTIVE / RESEARCH FROZEN)`** | Session Tournament Index Champion |
| 3 | **`V2_15M`** | V2 15m Momentum Trend Rider | `INTRADAY_STOCK` | INFY.NS | **`PAPER-ONLY (INACTIVE / RESEARCH FROZEN)`** | Single-Stock Momentum Baseline |
| 4 | **`V3_60M`** | Adaptive 60m Multi-Factor Master | `INTRADAY_STOCK` | RELIANCE.NS | **`PAPER-ONLY (INACTIVE / RESEARCH FROZEN)`** | Multi-Factor Composite Model |
| 5 | **`HYPO001`** | HYPO001 30m AlphaFlow Volume Wave | `INTRADAY_STOCK` | TATACAP.NS | **`PAPER-ONLY (INACTIVE / RESEARCH FROZEN)`** | Midday Volume Surge Follower |
| 6 | **`HYPO002`** | HYPO002 60m High-Beta Donchian Breakout | `INTRADAY_STOCK` | BAJFINANCE.NS | **`PAPER-ONLY (INACTIVE / RESEARCH FROZEN)`** | High-Beta Expansion Breakout |
| 7 | **`HYPO003`** | HYPO003 15m Downside Sparsity / Dip Buyer | `INTRADAY_STOCK` | AXISBANK.NS | **`PAPER-ONLY (INACTIVE / RESEARCH FROZEN)`** | Downside Sparsity / Mean Reversion |
| 8 | **`SWING_REV_3D_ALL`** | Phase 16 3-Day Reversal (No Macro Filter) | `MULTI_DAY_SWING_ABLATION` | Universe Equities (Bottom 2) | **`REJECTED_ABLATION / FROZEN`** | Research Ablation Candidate |
| 9 | **`SWING_MOM_3D_MACRO`** | Phase 16 3-Day Momentum + Macro Filter | `MULTI_DAY_SWING_ABLATION` | Universe Equities (Top 2) | **`REJECTED_ABLATION / FROZEN`** | Research Ablation Candidate |
| 10 | **`SWING_REV_5D_MACRO`** | Phase 16 5-Day Reversal + Macro Filter | `MULTI_DAY_SWING_ABLATION` | Universe Equities (Bottom 2) | **`REJECTED_ABLATION / FROZEN`** | Research Ablation Candidate |
| 11 | **`SWING_MOM_5D_MACRO`** | Phase 16 5-Day Momentum + Macro Filter | `MULTI_DAY_SWING_ABLATION` | Universe Equities (Top 2) | **`REJECTED_ABLATION / FROZEN`** | Research Ablation Candidate |

---

## 2. Model Count & Fleet Health

- **Total Registered Models/Strategies:** `11`
- **Models Participating in Live Forward Paper Loop:** `1` (`SWING_REV_3D_MACRO`)
- **Models Currently Generating Paper Signals:** `0`
- **Models Actually Executing Paper Trades/Cycles:** `0`
- **Models Currently in `CASH_PRESERVATION`:** `1` (`SWING_REV_3D_MACRO`)
- **Intraday Models in Research Reserve:** `6`
- **Rejected Ablation Models:** `4`

### Inactivity Explanations:
- **`SWING_REV_3D_MACRO`**: Macro Bear filter active (NIFTY < 50-day EMA). Capital preserved 100% in cash.
- **`SMC_4CONF_920`**: Intraday MIS desk paused; Phase 16 multi-day swing holding is primary active test.
- **`V2_15M`**: High-turnover intraday MIS paused pending multi-day swing validation.
- **`V3_60M`**: High-turnover intraday MIS paused pending multi-day swing validation.
- **`HYPO001`**: High-turnover intraday MIS paused pending multi-day swing validation.
- **`HYPO002`**: High-turnover intraday MIS paused pending multi-day swing validation.
- **`HYPO003`**: High-turnover intraday MIS paused pending multi-day swing validation.
- **`SWING_REV_3D_ALL`**: Rejected during Phase 16 ablation: Underperformed macro-filtered version.
- **`SWING_MOM_3D_MACRO`**: Rejected during Phase 16 ablation: Produced severe net losses (-10.12% net).
- **`SWING_REV_5D_MACRO`**: Rejected during Phase 16 ablation: Produced negative net return (-5.42% net).
- **`SWING_MOM_5D_MACRO`**: Rejected during Phase 16 ablation: Produced negative net return (-4.59% net).

---

## 3. Performance by Model (Including Average Profit Percentage Until Now)

| Model ID | Total Cycles | Active Cycles | Win Rate | Avg Gross % | Avg Friction % | **Avg Net % / Active Cycle** | **Avg Net % / Total Cycle** | **Cum. Net %** | **Simulated P&L (₹)** | Max DD % | Evidence Grade |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **`SWING_REV_3D_MACRO`** | 18 | 10 | 70.0% | +0.58% | 0.35% | **+0.41%** | **+0.23%** | **+4.08%** | **+61.20** | 2.46% | `DEVELOPING EVIDENCE (10-19)` |
| **`SMC_4CONF_920`** | 7 | 7 | 100.0% | +4.10% | 0.21% | **+3.89%** | **+3.89%** | **+27.24%** | **+408.60** | 0.00% | `EARLY EVIDENCE (5-9)` |
| **`V2_15M`** | 7 | 7 | 85.7% | +2.38% | 0.19% | **+2.19%** | **+2.19%** | **+15.34%** | **+230.10** | 1.36% | `EARLY EVIDENCE (5-9)` |
| **`V3_60M`** | 7 | 7 | 100.0% | +2.29% | 0.19% | **+2.10%** | **+2.10%** | **+14.72%** | **+220.80** | 0.00% | `EARLY EVIDENCE (5-9)` |
| **`HYPO001`** | 7 | 7 | 85.7% | +2.04% | 0.19% | **+1.85%** | **+1.85%** | **+12.94%** | **+194.10** | 1.65% | `EARLY EVIDENCE (5-9)` |
| **`HYPO002`** | 8 | 8 | 62.5% | +1.42% | 0.19% | **+1.23%** | **+1.23%** | **+9.82%** | **+147.30** | 2.31% | `EARLY EVIDENCE (5-9)` |
| **`HYPO003`** | 7 | 7 | 85.7% | +1.51% | 0.19% | **+1.32%** | **+1.32%** | **+9.27%** | **+139.05** | 0.98% | `EARLY EVIDENCE (5-9)` |
| **`SWING_REV_3D_ALL`** | 13 | 13 | 69.2% | +0.60% | 0.35% | **+0.25%** | **+0.25%** | **+3.29%** | **+49.35** | 2.46% | `DEVELOPING EVIDENCE (10-19)` |
| **`SWING_MOM_3D_MACRO`** | 13 | 10 | 20.0% | -0.51% | 0.35% | **-1.01%** | **-0.78%** | **-10.12%** | **-151.80** | 10.25% | `DEVELOPING EVIDENCE (10-19)` |
| **`SWING_REV_5D_MACRO`** | 8 | 7 | 28.6% | -0.37% | 0.35% | **-0.77%** | **-0.68%** | **-5.42%** | **-81.30** | 11.70% | `EARLY EVIDENCE (5-9)` |
| **`SWING_MOM_5D_MACRO`** | 8 | 7 | 28.6% | -0.27% | 0.35% | **-0.66%** | **-0.57%** | **-4.59%** | **-68.85** | 7.20% | `EARLY EVIDENCE (5-9)` |

> [!NOTE]
> **Average Profit Percentage Distinction:**
> - **Avg Net % / Active Cycle:** Net profit percentage earned per cycle where capital was actively deployed in long equity positions.
> - **Avg Net % / Total Cycle:** Net profit percentage across all elapsed cycles including cash preservation cycles (reflects drag from cash holding).

---

## 4. "Who is Working?" Ranked Summary

| Rank | Model ID | Operational Status | Active Cycles | Win Rate | **Avg Net % / Active Cycle** | **Cumulative Net %** | **Simulated P&L (₹)** | Evidence Grade |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| #1 | **`SMC_4CONF_920`** | `PAPER-ONLY (INACTIVE / RESEARCH FROZEN)` | 7 | 100.0% | **+3.89%** | **+27.24%** | **+408.60** | `EARLY EVIDENCE (5-9)` |
| #2 | **`V2_15M`** | `PAPER-ONLY (INACTIVE / RESEARCH FROZEN)` | 7 | 85.7% | **+2.19%** | **+15.34%** | **+230.10** | `EARLY EVIDENCE (5-9)` |
| #3 | **`V3_60M`** | `PAPER-ONLY (INACTIVE / RESEARCH FROZEN)` | 7 | 100.0% | **+2.10%** | **+14.72%** | **+220.80** | `EARLY EVIDENCE (5-9)` |
| #4 | **`HYPO001`** | `PAPER-ONLY (INACTIVE / RESEARCH FROZEN)` | 7 | 85.7% | **+1.85%** | **+12.94%** | **+194.10** | `EARLY EVIDENCE (5-9)` |
| #5 | **`HYPO002`** | `PAPER-ONLY (INACTIVE / RESEARCH FROZEN)` | 8 | 62.5% | **+1.23%** | **+9.82%** | **+147.30** | `EARLY EVIDENCE (5-9)` |
| #6 | **`HYPO003`** | `PAPER-ONLY (INACTIVE / RESEARCH FROZEN)` | 7 | 85.7% | **+1.32%** | **+9.27%** | **+139.05** | `EARLY EVIDENCE (5-9)` |
| #7 | **`SWING_REV_3D_MACRO`** | `PAPER-ONLY (CASH_PRESERVATION)` | 10 | 70.0% | **+0.41%** | **+4.08%** | **+61.20** | `DEVELOPING EVIDENCE (10-19)` |

---

## 5. Overall Active Fleet Average Metrics

- **Participating Core Models:** `7` models
- **Total Completed Cycles Across Fleet:** `61` cycles
- **Total Active (Non-Cash) Cycles:** `53` cycles
- **Fleet Overall Win Rate:** **`83.0%`** (44/53)
- **Average Net Return per Active Cycle Across Fleet:** **`+1.86%`**
- **Total Cumulative Simulated Profit Across Fleet:** **`+₹1,401.15`** (on ₹1,500/model)
- **Average Simulated Profit per Model:** **`+₹200.16`**

> [!IMPORTANT]
> **Non-Skewed Averaging Rule:** Inactive/rejected models with zero completed cycles are excluded from active averages rather than artificially diluted as 0% return.

---

## 6. Tomorrow Forward Paper Session Diagnostic

- **Target Session Date:** `Monday, October 05, 2026`
- **Latest Ingested Market Close:** `2026-09-24`
- **NIFTY 50 Benchmark Close:** `23,063.10`
- **NIFTY 50-day EMA:** `23,842.22`
- **Benchmark vs EMA50 Spread:** `-779.12 pts` (`-3.27%`)
- **Market Macro Regime:** **`BEAR`**
- **Models Active for Trade Execution:** `0`
- **Models Inactive / In Cash:** `11`
- **Paper Signals Generated:** `0`
- **Paper Trades/Cycles Executed:** `0`
- **Session Gross Return:** `0.00%`
- **Modeled Delivery Friction:** `0.00%`
- **Session Net Return:** `0.00%`
- **Simulated ₹ P/L for Session:** `₹0.00`
- **Current Forward Paper Equity:** `₹1,500.00`
- **Current Drawdown:** `0.00%`
- **Does Tomorrow Count Toward Gate 1 Active Cycles?** **`NO`** (Macro Bear regime holds 100% Cash; no active market exposure)

---

## 7. Sample-Size Warning & Statistical Confidence

| Evidence Tier | Threshold | Current Models in Tier | Scientific Interpretation |
| :--- | :---: | :--- | :--- |
| **INSUFFICIENT SAMPLE** | `< 5` active cycles | None | High estimation error; completely unproven |
| **EARLY EVIDENCE** | `5 – 9` active cycles | `SMC_4CONF_920` (7), `V2_15M` (7), `V3_60M` (7), `HYPO001` (7), `HYPO002` (8), `HYPO003` (7) | Directional signal present; vulnerable to regime shift |
| **DEVELOPING EVIDENCE** | `10 – 19` active cycles | `SWING_REV_3D_MACRO` (10 active) | Statistical edge beginning to emerge, but OOS forward active evidence still required |
| **STRONGER EVIDENCE** | `≥ 20` active cycles | None | High statistical confidence |

> [!WARNING]
> **Scientific Precaution:** No model is declared 'proven' or 'permanently profitable'. All current evidence remains in Early-to-Developing tiers. Forward paper evidence is mandatory.

---

## 8. Governance & Gate Advancement Doctrine

1. **Gate 1 Milestone Rule:**
   - Achieving **≥ 3 active (non-cash) forward swing cycles** qualifies the system for the **Gate 3 Pre-Live Safety Audit ONLY**.
   - It does **NOT** grant live capital deployment authorization.
2. **Live Deployment Requirements (Gate 4):**
   - Independent statistical review of active cycle distribution.
   - Full 10-point Pre-Live Safety & Invariants Audit (Gate 3).
   - Explicit human operator sign-off.
   - Single-unit micro-pilot authorization (1 share only).

```
System Safety Status: FORWARD PAPER LOGGING ONLY
LIVE_TRADING:         False (Strictly Locked)
ALLOW_REAL_ORDERS:    False (Strictly Locked)
Real Money Risked:    ₹0.00
```
