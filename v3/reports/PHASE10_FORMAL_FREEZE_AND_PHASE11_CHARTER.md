# Phase 10 Formal Freeze & Phase 11 Research Charter

**Date:** 2026-10-02  
**Status:** Phase 10 Frozen & Rejected as Current Edge | Phase 11 Charter Initialized  
**Safety Status:** `LIVE_TRADING=False` | `ALLOW_REAL_ORDERS=False` (Strictly Enforced)

---

## 1. Phase 10 Formal Freeze & Rejection Record

The empirical evaluation of Phase 10 is officially closed. All artifacts are locked as a permanent **negative-control benchmark** for the AlphaNSE quantitative platform.

### Artifact Status Tree
```text
Phase 10 (Indicator-Based Breakdown + L2 Logistic Hurdle)
├── Research Dataset (June 29 – Aug 31, 2026)      FROZEN
├── Locked September Test Set (Sep 1 – Sep 25, 2026) LOCKED (Unmodified)
├── E5 Hybrid Exit Architecture                     FROZEN (Benchmark Exit Engine)
├── L2 Logistic Feature Model                       REJECTED (Negative-Control Benchmark)
├── Technical Indicator Feature Gate                REJECTED (No Generalizable Edge)
└── 15m Breakdown Strategy Family                   REJECTED AS CURRENT TRADING EDGE
```

### Forensic Summary of Out-of-Sample Failure
* **Feature Correlation:** None of the 12 candidate technical indicator features demonstrated statistically significant correlation ($p > 0.05$) with forward drift or MFE on the Research Set.
* **Out-of-Sample Ranking Inversion:**
  * **E5 Unfiltered September:** 19 trades, 26.3% win rate, -₹3.74 gross expectancy, **-₹16.59 net expectancy**.
  * **E5 + Model Hurdle September:** 5 trades, 0.0% win rate, -₹25.84 gross expectancy, **-₹40.46 net expectancy**.
  * The model systematically filtered out all 5 winning September trades and accepted 5 consecutive losers.
* **Core Takeaway:** Technical indicators derived from past price candles (RSI, ADX, EMA distances, bar body proportions) on single-stock breakdown setups in large-cap Indian equities suffer from severe regime instability and late-cycle entry exhaustion.

---

## 2. Non-Negotiable Methodological Protocol for Future Phases

To prevent data snooping, p-hacking, and parameter overfitting, all future research phases will strictly enforce the linear, falsifiable workflow:

```text
       Step 1: Research Period (June 29 – August 31, 2026)
                                 │
                                 ▼
       Step 2: Market Behavior Hypothesis Definition
                                 │
                                 ▼
       Step 3: Strategy & Feature Construction (Research Only)
                                 │
                                 ▼
       Step 4: Parameter Freeze & Pre-Registration
                                 │
                                 ▼
       Step 5: Locked September Test Set (September 1 – 25, 2026)
                                 │
                                 ▼
       Step 6: One-Shot Out-of-Sample Evaluation
```

**Cardinal Rules:**
1. Zero adjustments or re-tunings based on September performance.
2. Complete transaction friction (slippage, spread, statutory fees, rejection) must be modeled under `ExecutionRegime.BASE` on ₹1,500 capital (₹7,500 purchasing power).
3. If an experiment produces negative net expectancy out-of-sample, it is recorded, frozen, and rejected.

---

## 3. Preliminary Research-Set Investigation of Market Behaviors

Exploratory analysis was conducted strictly on the **Research Set (June 29 – August 31, 2026, 1,134 15-minute bars across 10 liquid constituent stocks + `^NSEI`)**:

### A. Intraday Move Distribution
* **Mean Daily High-Low Range:** 1.85% (Median: 1.64%, 90th percentile: 3.08%).
* **Mean Absolute Open-to-Close:** 0.95% (Median: 0.74%).
* **Substantial Moves:** 63.0% of days experience $|Open - Close| \ge 0.50\%$; 40.0% of days experience $|Open - Close| \ge 1.00\%$.
* **Implication:** Price displacement sufficient to overcome the ~0.23% (23 bps) roundtrip friction exists in the universe, but mid-session indicator breakdowns entered too late in the daily move.

### B. Cross-Sectional Relative Strength Information Coefficient (IC)
* Tested lookbacks $k \in \{2, 4, 8, 12, 16, 25\}$ 15m bars against forward horizons $h \in \{1, 2, 4, 8\}$ bars.
* **Key Finding:** Short lookbacks exhibit **statistically significant negative IC** (Short-term Mean Reversion):
  * $k=2$ (30m), $h=1$ (15m): Excess IC = **-0.0307** ($t = -2.89$, $p = 0.0039$).
  * $k=4$ (60m), $h=2$ (30m): Excess IC = **-0.0267** ($t = -2.47$, $p = 0.0137$).
* **Economic Magnitude:** The raw cross-sectional spread between top 2 relative winners and bottom 2 relative losers is only **+0.003% to -0.008%**, which is roughly $30\times$ to $70\times$ smaller than roundtrip friction. Pure continuous cross-sectional rebalancing cannot overcome friction.

### C. 30-Minute Opening Range Breakout (ORB) Conditioned on Regime
* **Raw 30m ORB:** 401 trades, Mean return: -0.020%, Win rate: 49.6%.
* **Regime-Conditioned ORB:**
  * When NIFTY is Bullish (Above Daily EMA50 + Positive Morning OR), Long top 1-2 Relative Strength breakouts:
    * 28 trades, Mean gross return: **+0.065%**, Win rate: **53.6%**.
  * When NIFTY is Bearish (Below Daily EMA50 + Negative Morning OR), Short bottom 1-2 Relative Weakness breakdowns:
    * 12 trades, Mean gross return: **+0.014%**, Win rate: **50.0%**.
* **Friction Obstacle:** +0.065% gross is positive, but still below the ~0.23% roundtrip friction hurdle under ₹1,500 capital.

---

## 4. Current Platform Safety Status

| Safety Guard | Configured Value | Verification Status |
|---|---|---|
| `LIVE_TRADING` | `False` | 🟢 Enforced in `.env` |
| `ALLOW_REAL_ORDERS` | `False` | 🟢 Enforced in `.env` |
| Dhan API Handshake | Read-Only Engine Ready | 🟢 Zero order placement capabilities |
| Pre-Trade Risk Checks | 11/11 Passing | 🟢 Enforces clock drift, circuit limit, depth lock |
| EOD Square-Off Invariants | 6/6 Passing | 🟢 Strictly zero overnight position carry |

**Conclusion:** Real-money trading remains completely locked until a scientifically sound, statistically robust out-of-sample net edge is demonstrated.
