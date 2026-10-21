# AlphaNSE Phase 9: Controlled Exit-Ablation Study & Counterfactual Attribution

**Objective:** Empirically evaluate whether reforming exit architecture rescues favorable excursions and converts the strategy to positive net expectancy without modifying entry signals.
**Dataset Partitions:** Research Set (Jun 29 – Aug 31, 24 signals) | Locked Out-of-Sample Test Set (Sep 1 – Sep 25, 19 signals).
**Execution Regime:** BASE Friction (5 bps slippage, 3 bps half-spread, 2% rejection, Zerodha statutory cost schedule).
**Account Safety Posture:** `LIVE_TRADING=False` | `ALLOW_REAL_ORDERS=False` (Locked).

---

## 1. Research Set Exit Ablation Sweep (June 29 – August 31, 2026)

Evaluated across the 24 research signals to identify and freeze the optimal exit architecture prior to touching the September locked test set:

| Variant | Description | Trades | Win Rate | Gross P&L | Friction | Net P&L | **Gross Exp** | **Net Exp** | Profit Factor | Max DD (%) | Avg Hold | Rescued |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **E0** | Current Exit (1.5x ATR SL, 2.5x ATR TP) | 24 | 20.8% | ₹-206.86 | ₹313.16 | ₹-520.02 | **₹-8.62** | **₹-21.67** | 0.40 | 34.7% | 82m | **0** |
| **E1** | Profit-Lock (BE at +0.50% MFE) | 24 | 20.8% | ₹-221.91 | ₹313.17 | ₹-535.08 | **₹-9.25** | **₹-22.30** | 0.38 | 35.7% | 82m | **0** |
| **E2** | Tiered Profit Trail (+0.50%->BE, +0.75%->+0.25%, etc.) | 24 | 16.7% | ₹-239.26 | ₹313.18 | ₹-552.44 | **₹-9.97** | **₹-23.02** | 0.33 | 36.8% | 82m | **0** |
| **E3** | Dynamic ATR Trail (Trail lowest_low + 1.0x ATR) | 24 | 16.7% | ₹-221.36 | ₹313.17 | ₹-534.53 | **₹-9.22** | **₹-22.27** | 0.36 | 35.6% | 82m | **0** |
| **E4** | Time-Aware Anti-Chop (Kill if MFE < 0.25% @ 60m) | 24 | 16.7% | ₹-194.81 | ₹313.05 | ₹-507.86 | **₹-8.12** | **₹-21.16** | 0.37 | 33.9% | 60m | **0** |
| **E5** | MFE-Aware Hybrid (Chop Exit + Lock + ATR Trail) | 24 | 16.7% | ₹-193.36 | ₹313.05 | ₹-506.41 | **₹-8.06** | **₹-21.10** | 0.37 | 33.8% | 59m | **0** |

> **Architecture Freeze Decision:** Variant **E5** achieved the superior risk-adjusted net expectancy on the Research partition and is frozen for out-of-sample evaluation on September.

---

## 2. Locked September Test Set: Exit Ablation Comparison

Evaluated across all 19 identical out-of-sample breakdown signals under strict BASE friction:

| Variant | Description | Trades | Win Rate | Gross P&L | Friction | Net P&L | **Gross Exp** | **Net Exp** | Profit Factor | Max DD (%) | Avg Hold | Rescued |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **E0** | Current Exit (1.5x ATR SL, 2.5x ATR TP) | 19 | 26.3% | ₹-121.97 | ₹244.15 | ₹-366.12 | **₹-6.42** | **₹-19.27** | 0.58 | 24.7% | 107m | **0** |
| **E1** | Profit-Lock (BE at +0.50% MFE) | 19 | 26.3% | ₹-98.52 | ₹244.13 | ₹-342.65 | **₹-5.19** | **₹-18.03** | 0.63 | 23.1% | 107m | **0** |
| **E2** | Tiered Profit Trail (+0.50%->BE, +0.75%->+0.25%, etc.) | 19 | 21.1% | ₹-136.81 | ₹244.15 | ₹-380.96 | **₹-7.20** | **₹-20.05** | 0.48 | 25.6% | 107m | **0** |
| **E3** | Dynamic ATR Trail (Trail lowest_low + 1.0x ATR) | 19 | 31.6% | ₹-63.77 | ₹244.03 | ₹-307.80 | **₹-3.36** | **₹-16.20** | 0.75 | 20.8% | 104m | **1** |
| **E4** | Time-Aware Anti-Chop (Kill if MFE < 0.25% @ 60m) | 19 | 21.1% | ₹-129.28 | ₹244.17 | ₹-373.45 | **₹-6.80** | **₹-19.66** | 0.54 | 24.9% | 98m | **0** |
| 🔒 **E5** | MFE-Aware Hybrid (Chop Exit + Lock + ATR Trail) | 19 | 26.3% | ₹-71.08 | ₹244.05 | ₹-315.13 | **₹-3.74** | **₹-16.59** | 0.71 | 21.0% | 95m | **1** |

---

## 3. Trade-by-Trade Counterfactual Matrix (All 19 Locked Trades)

Directly answers: *What would each candidate exit architecture have produced for each trade?*

| ID | Symbol | Entry Px | Peak MFE | Peak MAE | E0 (Base) Net | E1 (Lock) Net | E2 (Tiered) Net | E3 (ATR) Net | E4 (Chop) Net | E5 (Hybrid) Net | Best Variant |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `SIG_LOC_001` | TCS | ₹2,337.2 | **+0.52%** | 0.33% | ₹+3.66 | ₹+3.66 | ₹+3.66 | ₹+3.66 | ₹-31.22 | ₹-31.22 | **E0 (₹+3.66)** |
| `SIG_LOC_002` | TCS | ₹2,324.0 | **+0.34%** | 0.05% | ₹-13.22 | ₹-13.22 | ₹-13.22 | ₹-13.22 | ₹-13.22 | ₹-13.22 | **E0 (₹-13.22)** |
| `SIG_LOC_003` | INFY | ₹1,087.3 | **+0.55%** | 0.41% | ₹-8.61 | ₹-8.61 | ₹-8.61 | ₹-3.74 | ₹-8.61 | ₹-3.74 | **E3 (₹-3.74)** |
| `SIG_LOC_004` | INFY | ₹1,083.1 | **+4.42%** | 0.17% | ₹-14.10 | ₹-14.10 | ₹-14.10 | ₹-14.10 | ₹-11.10 | ₹-11.10 | **E4 (₹-11.10)** |
| `SIG_LOC_005` | RELIANCE | ₹1,288.0 | **+0.39%** | 0.51% | ₹-51.67 | ₹-51.67 | ₹-51.67 | ₹-51.67 | ₹-51.67 | ₹-51.67 | **E0 (₹-51.67)** |
| `SIG_LOC_006` | BAJFINANCE | ₹1,045.5 | **+0.83%** | 0.31% | ₹+19.83 | ₹+19.83 | ₹+19.83 | ₹+19.83 | ₹+19.83 | ₹+19.83 | **E0 (₹+19.83)** |
| `SIG_LOC_007` | RELIANCE | ₹1,269.2 | **+1.25%** | 0.38% | ₹-39.61 | ₹-39.61 | ₹-39.61 | ₹-39.61 | ₹-39.61 | ₹-39.61 | **E0 (₹-39.61)** |
| `SIG_LOC_008` | HDFCBANK | ₹685.2 | **+0.31%** | 0.33% | ₹-35.59 | ₹-35.59 | ₹-35.59 | ₹-35.59 | ₹-35.59 | ₹-35.59 | **E0 (₹-35.59)** |
| `SIG_LOC_009` | RELIANCE | ₹1,256.5 | **+0.28%** | 0.12% | ₹-7.97 | ₹-7.97 | ₹-7.97 | ₹-7.97 | ₹-7.97 | ₹-7.97 | **E0 (₹-7.97)** |
| `SIG_LOC_010` | BAJFINANCE | ₹1,010.7 | **+0.51%** | 0.83% | ₹-14.79 | ₹-14.79 | ₹-14.79 | ₹-10.17 | ₹-14.79 | ₹-10.17 | **E3 (₹-10.17)** |
| `SIG_LOC_011` | RELIANCE | ₹1,248.2 | **+0.10%** | 0.53% | ₹-64.75 | ₹-64.75 | ₹-64.75 | ₹-64.75 | ₹-62.76 | ₹-62.76 | **E4 (₹-62.76)** |
| `SIG_LOC_012` | BAJFINANCE | ₹1,012.6 | **+0.24%** | 1.54% | ₹-40.17 | ₹-40.17 | ₹-40.17 | ₹-40.17 | ₹-40.17 | ₹-40.17 | **E0 (₹-40.17)** |
| `SIG_LOC_013` | INFY | ₹1,051.9 | **+0.97%** | 0.03% | ₹+29.52 | ₹+29.52 | ₹+29.52 | ₹+29.52 | ₹+29.52 | ₹+29.52 | **E0 (₹+29.52)** |
| `SIG_LOC_014` | INFY | ₹1,044.9 | **+1.38%** | 0.62% | ₹-46.92 | ₹-23.45 | ₹-23.45 | ₹+9.40 | ₹-46.92 | ₹+9.40 | **E3 (₹+9.40)** |
| `SIG_LOC_015` | BAJFINANCE | ₹1,025.7 | **+0.68%** | 0.32% | ₹-14.49 | ₹-14.49 | ₹-14.49 | ₹-14.49 | ₹-14.49 | ₹-14.49 | **E0 (₹-14.49)** |
| `SIG_LOC_016` | INFY | ₹1,030.1 | **+1.06%** | 0.17% | ₹+34.72 | ₹+34.72 | ₹-3.59 | ₹+27.23 | ₹+34.72 | ₹+27.23 | **E0 (₹+34.72)** |
| `SIG_LOC_017` | TCS | ₹2,106.0 | **+0.96%** | 0.66% | ₹-51.14 | ₹-51.14 | ₹-51.14 | ₹-51.14 | ₹-51.14 | ₹-51.14 | **E0 (₹-51.14)** |
| `SIG_LOC_018` | RELIANCE | ₹1,221.4 | **+0.46%** | 0.12% | ₹+4.77 | ₹+4.77 | ₹+4.77 | ₹+4.77 | ₹+4.77 | ₹+4.77 | **E0 (₹+4.77)** |
| `SIG_LOC_019` | INFY | ₹995.2 | **+0.07%** | 0.50% | ₹-55.59 | ₹-55.59 | ₹-55.59 | ₹-55.59 | ₹-33.03 | ₹-33.03 | **E4 (₹-33.03)** |

---

## 4. Key Case Studies: Forensic Insights Across Individual Trades

### Case 1: The Rescued Winner — `SIG_LOC_014` (INFY on Sep 18)
- **Signal & Excursion:** Entered SHORT at 14:15 at ₹1,044.90. Reached peak MFE of **+1.38%** (low ₹1,030.50), followed by an adverse pullback (MAE 0.62%).
- **E0 Baseline Outcome:** **-₹46.92** (`STOP_LOSS`). The rigid 2.5x ATR target was not reached; price pulled back and hit the initial 1.5x ATR stop, turning a 138-bps favorable excursion into a full loss.
- **E3 / E5 Counterfactual Outcome:** **+₹9.40 NET PROFIT** (`TRAILING_PROFIT_STOP`). The 1.0x ATR trailing stop ratcheted down with the move, locking in positive net alpha after paying full BASE friction.
- **Forensic Confirmation:** Directly proves the hypothesis that a portion of strategy losses arose from target greed and static stops rather than flawed directional prediction.

### Case 2: The Horizon Illusion — `SIG_LOC_004` (INFY on Sep 8)
- **Signal & Excursion:** Entered SHORT at 14:00 at ₹1,083.10. Phase 8 recorded an unconstrained 12-bar MFE of **+4.42%** (low ₹1,035.20).
- **Forensic Audit:** Detailed bar-by-bar tracing reveals that during the intraday session (14:00 to 15:15 IST), the stock only drifted between ₹1,081.00 and ₹1,083.50 (intraday MFE was only **+0.18%**). The +4.42% move was an **overnight opening gap** the following morning (Sep 9 at 09:15).
- **Outcome Under All Intraday Exits:** Under mandatory 15:15 IST RMS square-off, the position was flattened at ₹1,082.00 for net **-₹14.10** (pure statutory friction).
- **Forensic Takeaway:** In an intraday MIS framework, unconstrained multi-day forward horizons create a false impression of missed profit. The trade was fundamentally a dead-chop intraday session.

### Case 3: The Anti-Chop Protection — `SIG_LOC_019` (INFY on Sep 25)
- **Signal & Excursion:** Entered SHORT at 13:45 at ₹995.20. Price stagnated with peak MFE of only **+0.07%** before drifting upwards into an adverse move (MAE 0.50%).
- **E0 Baseline Outcome:** **-₹55.59** (`STOP_LOSS`). Sat through 6 bars of adverse drift before stopping out.
- **E4 / E5 Counterfactual Outcome:** **-₹33.03** (`TIME_DECAY_CHOP_EXIT`). Recognizing that MFE failed to exceed +0.25% after 4 bars (60 mins), the engine executed an early chop abort, saving **₹22.56** in avoidable drawdown.

---

## 5. Causal Analysis & Scientific Conclusions

### A. Causal Impact of the Frozen Exit Architecture
- **Gross Expectancy:** Shifted from ₹-6.42 (E0) ➔ **₹-3.74** (E5).
- **Net Expectancy:** Shifted from ₹-19.27 (E0) ➔ **₹-16.59** (E5).
- **Win Rate:** Shifted from 26.3% ➔ **26.3%**.
- **Max Drawdown:** Shifted from 24.7% ➔ **21.0%**.
- **Trades Rescued:** **1 trades** converted from losers to winners.

### B. Can Exit Reform Overcome Transaction Friction?
- **Status:** 🔴 **NET EXPECTANCY REMAINS NEGATIVE (₹-16.59/trade).**
- **Forensic Insight:** While dynamic trailing and chop filters substantially reduced drawdown and rescued high-MFE trades, the average winning excursion across large-cap intraday equities (+0.70% to +1.20%) remains too narrow relative to the ₹14.50 statutory friction hurdle on ₹1,500 capital.
- **Required Direction:** Capital scale (e.g. ₹10,000+ where statutory costs drop from ~100 bps down to ~15 bps) or higher-horizon holding periods are mathematically required to achieve net profitability.

### C. Account Safety Lock Preserved
```env
LIVE_TRADING=False
ALLOW_REAL_ORDERS=False
```