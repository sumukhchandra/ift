# AlphaNSE V2 — Quantitative Architecture Migration Plan

**System Target**: AlphaNSE V2 Quantitative Production Trading Platform  
**Document Type**: Architectural Specification & Implementation Roadmap  
**Status**: Phase 0 Complete — Migration Blueprint Authorized  
**Author**: Senior Quantitative Software Architect  
**Date**: September 19, 2026  

---

## 1. V1 → V2 Architecture Mapping

The migration from AlphaNSE V1 to AlphaNSE V2 transforms an experimental, single-loop, yfinance-polled 1-minute prototype into a high-reliability, transaction-cost-aware, event-driven 5-minute quantitative trading platform.

```text
======================================================================================================
V1 CURRENT ARCHITECTURE                                  V2 TARGET ARCHITECTURE
======================================================================================================
[yfinance REST Polling] (15-45s latency)          ──►    [Direct Broker WebSocket / Fast Tick Aggregator]
          │                                                                │
          ▼                                                                ▼
[Full O(N) Feature Recomputation]                 ──►    [IncrementalFeatureEngine: O(1) Bounded Updates]
          │                                                                │
          ▼                                                                ▼
[1-Minute Regressors + 4.55% Recall Classifier]   ──►    [5-Minute Cost-Aware Expected Net Value Ensemble]
          │                                                                │
          ▼                                                                ▼
[Static/Dynamic Blacklist Aggressive Shutoff]     ──►    [Point-in-Time Alpha Weighting + Soft Damping]
          │                                                                │
          ▼                                                                ▼
[Hardcoded 25% Price Cap (₹1,250 on ₹5k)]         ──►    [Risk-Based Integer Share Sizer (No Price Caps)]
          │                                                                │
          ▼                                                                ▼
[In-Memory Order Creation (No Idempotency)]       ──►    [Stateful Order Machine with Client UUID & Idemp]
          │                                                                │
          ▼                                                                ▼
[Zero Unit Tests / Broken Backtests]              ──►    [Strict CI Test Suite: Purged CV, Equivalence, etc.]
          │                                                                │
          ▼                                                                ▼
[Single Runtime Loop (Crash stops everything)]    ──►    [Dual State Machines: Research Lifecycle vs Safety]
======================================================================================================
```

---

## 2. Keep / Modify / Replace / Remove Matrix

| Subsystem | V1 File / Component | Disposition | V2 Destination / Action | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Tax Engine** | `QA/risk/india_tax_engine.py` | **KEEP & REUSE** | `v2/risk/cost_engine.py` | Highly accurate Zerodha intraday equity cost model. Only requires minor interface standardization. |
| **API Server** | `QA/server/api.py` | **MODIFY** | `v2/server/api_hub.py` | Retain FastAPI and WebSocket architecture; refactor endpoints to read from V2 state stores. |
| **Persistence** | `QA/logs/compounding_state.json` | **MODIFY** | `v2/persistence/state_manager.py` | Retain atomic JSON flushing and JSONL trade logging; add schema versioning and checksums. |
| **Supervisor** | `QA/monitoring/continuous_supervisor.py`| **MODIFY** | `v2/supervision/watchdog.py` | Enhance health check probe to inspect streaming feed heartbeat, memory leaks, and thread liveness. |
| **Frontend** | `QA/frontend/app.py` & `static/` | **MODIFY** | `v2/frontend/` | Rewire Streamlit cards and WebSocket listeners to V2 5-minute data models and telemetry feeds. |
| **Micro-Regime**| `classify_micro_regime` | **MODIFY** | `v2/regimes/intraday_regime.py` | Adapt EMA 5/20 slope and ATR expansion parameters from 1-minute to 5-minute bar windows. |
| **Feature Engine**| `OneMinPredictor.extract_features_1m` | **REPLACE** | `v2/features/incremental_engine.py` | Replace full $\mathcal{O}(N)$ recomputation with $\mathcal{O}(1)$ streaming stateful circular buffers. |
| **ML Models** | `QA/models/saved_models_1m/` | **REPLACE** | `v2/models/five_min_ensemble/` | Shift from 1m to 5m horizon; replace low-recall classifier with calibrated cost-aware EV regression. |
| **Position Sizer**| `compounding_trader.py` (L675-690) | **REPLACE** | `v2/risk/integer_position_sizer.py` | Remove hardcoded ₹1,250 price cap; implement volatility-based integer share allocation. |
| **Order Executor**| `QA/paper_trading/executor.py` | **REPLACE** | `v2/execution/order_state_machine.py` | Remove crypto BTCUSDT restrictions; implement UUID idempotency, order states, and reconciliation. |
| **Backtester** | `QA/backtesting/backtest.py` | **REPLACE** | `v2/backtest/event_driven_backtest.py` | Build event-driven replay engine with no-lookahead assertions and transaction fee realism. |
| **Crypto Code** | `crypto/` directory | **REMOVE** | **DELETE** | Completely obsolete crypto prototyping code disconnected from NSE Indian equities. |
| **Binance Feed**| `QA/websocket/binance_stream.py` | **REMOVE** | **DELETE** | Unused Binance WebSocket connector. |
| **GMM Regimes** | `RegimeClassifier` (GMM) | **REMOVE** | **DELETE** | Legacy model demanding `funding_rate` and `vpin` columns. |

---

## 3. Phase Dependency Graph

The migration must adhere to a strict topological dependency sequence. Upstream components must be validated before downstream components are constructed:

```text
Phase 1: Foundation & Data Architecture
    │
    ▼
Phase 2: Streaming Ingestion & Aggregation
    │
    ▼
Phase 3: Incremental Feature Engine & Equivalence Gate
    │
    ▼
Phase 4: 5-Minute Predictive Models & Training Pipeline
    │
    ▼
Phase 5: Transaction-Cost-Aware Risk & Integer Position Sizer
    │
    ▼
Phase 6: Order State Machine & Idempotent Execution Engine
    │
    ▼
Phase 7: Event-Driven Replay Simulation & Backtesting Engine
    │
    ▼
Phase 8: Walk-Forward Validation & Edge Sufficiency Gate
    │
    ▼
Phase 9: Shadow Pre-Allocation & Paper Trading Engine
    │
    ▼
Phase 10: Limited-Live Production Execution & Capital Router
```

---

## 4. Data Migration Strategy

1. **Retain Friday Harvester Data**:
   - `QA/data/friday_session_features.csv` and `dataset_friday_session_1m.jsonl` are archived as golden test fixtures for regression testing the incremental feature engine.
2. **Standardize Timezone & Schema**:
   - All timestamps must be explicitly encoded as ISO-8601 with timezone offset (`YYYY-MM-DDTHH:MM:SS+05:30`).
   - Standardized column schema: `[timestamp, symbol, open, high, low, close, volume]`.
3. **5-Minute Resampling Pipeline**:
   - Build a robust bar aggregator that converts tick or 1-minute streaming feeds into standard 5-minute bars (`09:15-09:20`, `09:20-09:25`, ..., `15:25-15:30`).
   - Enforce NSE session boundaries (drop any anomalous pre-market ticks before 09:15:00 or after 15:30:00).

---

## 5. Model Migration Strategy

1. **Horizon Shift: 1-Minute → 5-Minute**:
   - **Problem in V1**: Average 1-minute move is 2–5 bps; round-trip fees are 8–15 bps. Win rate required for breakeven exceeds 75%.
   - **V2 Solution**: Target 5-minute forward return ($t+1$ bar, $t+2$ bars). Average 5-minute move is 15–40 bps. Gross expected value comfortably surpasses fee hurdles.
2. **Breakout Classifier Overhaul**:
   - V1 classifier has **4.55% recall** (misses 95% of breakout scalps).
   - In V2, train a multi-horizon probability estimator using Purged K-Fold Cross Validation with explicit class-weighting or Focal Loss.
3. **Platt Calibration Validation**:
   - Enforce Brier score validation ($< 0.15$) and expected calibration error (ECE) verification before deploying any probability model.
4. **Expected Net Value (EV) Formulation**:
   $$\text{Expected Net Return} = \mathbb{E}[R_{\text{gross}}] - \text{IndiaTaxEngine.total\_cost\_pct}(K)$$
   Trades enter only when $\text{Expected Net Return} > \text{Hurdle}_{\text{regime}}$.

---

## 6. Feature Engine Migration (Incremental vs. Full Equivalence)

### Problem in V1
V1 computes all 30 features by taking the entire historical DataFrame and running rolling operations (`.rolling(14).mean()`, `.ewm(span=20).mean()`) on every tick ($\mathcal{O}(N)$ computational complexity).

### V2 Target: `IncrementalFeatureEngine`
The V2 engine maintains an in-memory bounded circular state buffer ($\mathcal{O}(1)$ updates per tick):

1. **Circular Buffers**:
   - Fixed deque of size 60 for 5-minute bars (5 hours of lookback).
2. **Stateful Indicators**:
   - EMA updated via recursive formula: $EMA_t = \alpha \cdot P_t + (1 - \alpha) \cdot EMA_{t-1}$.
   - True Range, Micro-ATR, and RSI maintained via rolling Welford/Wilder state accumulators.
   - Volume surge and z-scores computed over sliding window deques.

### Automated Equivalence Test (Mandatory Gate)
Before deployment, an automated test suite must run:
$$\max \left| \text{Feature}_{\text{full}}(t) - \text{Feature}_{\text{incremental}}(t) \right| < 10^{-7}$$
across all 30 features over 5,000 continuous test bars.

---

## 7. Risk Engine Migration

1. **Eliminate the ₹1,250 Single-Share Price Cap**:
   - Remove lines 675–676 in `compounding_trader.py`.
   - Replace with a **Risk-Based Integer Share Sizer**:
     $$Q = \left\lfloor \frac{\text{Capital} \times f_{\text{risk}}}{\text{Price} \times \text{ATR}_{\text{stop}}} \right\rfloor$$
     Where $Q$ is constrained to:
     $$\text{Capital Invested} = Q \times \text{Price} \le \text{Max Capital Per Trade}$$
2. **Portfolio Circuit Breakers**:
   - Daily Max Loss Halt: If portfolio realizes $-2.0\%$ of starting daily capital, halt all new trade entries for the rest of the day.
   - Per-Trade Stop-Loss: Dynamic ATR-based stop (typically $1.5 \times \text{ATR}_{14}$) instead of fixed 0.30%.
3. **Hysteresis & Cooldown**:
   - Anti-churn hold period: Minimum 2 bars (10 minutes) holding time unless hard stop-loss is breached.
   - Re-entry lockout: 15-minute cooldown on the same symbol after a stop-out.

---

## 8. Execution Engine Migration (Idempotency & Safety)

1. **Client Order ID Format**:
   - Every order generated must carry an immutable UUIDv4 client order ID:
     `NSE-V2-{YYYYMMDD}-{SYMBOL}-{UUID4[:8]}`
2. **Idempotent Order State Machine**:
   ```text
   [PENDING_SUBMIT] ──► [SUBMITTED] ──► [ACKNOWLEDGED] ──► [FILLED]
          │                     │                 │
          ▼                     ▼                 ▼
      [REJECTED]            [EXPIRED]         [CANCELLED]
   ```
3. **Crash Recovery Reconciliation**:
   - On boot, the engine queries open state and active positions.
   - In paper mode: Reconciles internal ledger against open position dictionary.
   - In live mode (future): Reconciles local state against broker orderbook before issuing any new commands.
4. **Duplicate Order Prevention**:
   - Submissions checked against an in-memory hash set of active client order IDs.
   - If an order is in `SUBMITTED` or `PENDING` state for a given symbol, no secondary order may be generated.

---

## 9. Monitoring & Telemetry Migration

1. **Unified Health Probe**:
   - Replace basic ping with a comprehensive `/api/health/full` endpoint exposing:
     - WebSocket stream latency (milliseconds since last tick).
     - Incremental feature engine health (buffer status, NaNs detected).
     - Model prediction status (latest inference time, confidence score).
     - Execution machine state (open orders, unconfirmed fills).
     - Memory usage (RSS MB) and CPU load.
2. **Drift & Anomaly Alerts**:
   - Automatic alert logged if model prediction distribution drifts significantly from training baseline (Kolmogorov-Smirnov test).

---

## 10. Comprehensive Testing Requirements

Phase 0 identified zero unit tests. V2 requires an end-to-end automated test matrix:

```text
+------------------------------------+---------------------------------------------------------------+
| Test Category                      | Test Case Description                                         |
+------------------------------------+---------------------------------------------------------------+
| 1. No-Lookahead Test               | Verify future bars (t+1, t+2) are strictly excluded from X_t  |
| 2. Incremental Equivalence Test    | Assert O(1) streaming features == O(N) batch features         |
| 3. Cost Engine Precision Test      | Verify penny-for-penny match against Zerodha live contract note|
| 4. Integer Sizing Bound Test       | Verify Q >= 1, Q * Price <= Max Allocation, no negative sizes |
| 5. Duplicate Submission Test       | Attempt rapid duplicate order fires; verify 100% rejection    |
| 6. Crash Recovery Reconciliation   | Kill process mid-trade; assert zero state corruption on reboot |
| 7. Cooldown & Hysteresis Test      | Assert minimum hold time and exit cooldown are obeyed         |
| 8. Drawdown Circuit Breaker Test   | Inject simulated consecutive losses; verify hard trading halt |
| 9. Paper/Live Isolation Test       | Assert paper environment cannot dispatch real broker API calls|
| 10. Purged CV Split Test           | Verify zero train/test overlap in time-series splits          |
+------------------------------------+---------------------------------------------------------------+
```

---

## 11. Dual State Machines: Research Lifecycle vs. Runtime Safety

A critical architectural flaw in V1 was conflating research-level data issues with real-time operational faults. V2 explicitly separates these into two orthogonal state machines:

### State Machine 1: Research & Development Lifecycle
*(Manages model validation, code maturity, and promotion)*
```text
DEVELOPMENT
    │
    ▼
RESEARCH
    │
    ▼
BACKTEST
    │
    ▼
DATA_VALIDATION (Gated by DATA_BLOCKED check)
    │
    ▼
MODEL_VALIDATION (Walk-forward, Purged CV, Edge Gate)
    │
    ▼
SHADOW (Pre-allocation simulation alongside live feeds)
    │
    ▼
PAPER (Real-time simulated execution with cost accounting)
    │
    ▼
LIMITED_LIVE (Micro-capital execution with strict risk bounds)
    │
    ▼
LIVE PRODUCTION (Full autonomous capital deployment)
```

### State Machine 2: Runtime Operational Safety
*(Manages real-time intraday fault tolerance during live or paper operation)*
```text
           ┌──────────────────────┐
           │     NORMAL TRADING   │
           └──────────┬───────────┘
                      │
       ┌──────────────┼──────────────┐
       │ (Tick stale) │ (NaN output) │ (Broker error)
       ▼              ▼              ▼
┌──────────────┐┌──────────────┐┌──────────────────┐
│SAFE_DATA_HALT││SAFE_MODEL_HAL││SAFE_EXECUTION_HAL│
└──────┬───────┘└──────┬───────┘└────────┬─────────┘
       │               │                 │
       └──────────────┼─────────────────┘
                      │ (Fault resolved & validated)
                      ▼
               [AUTO-RECOVERY] ──► Back to NORMAL TRADING
```

*Crucial Rule: A transient missing live tick triggers `SAFE_DATA_HALT` and auto-recovers when ticks resume. It does NOT regress the system to `DATA_BLOCKED` or abort the research lifecycle.*

---

## 12. Rollback Strategy

1. **Git Baseline Tag**:
   - The current Friday working version is tagged as `alpha-nse-v1-baseline`.
   - Any V2 phase can be rolled back immediately by checking out the baseline tag.
2. **Dual-Path Operation**:
   - V2 code is implemented in dedicated modular packages (`v2/` or modular QA subdirectories) without mutating the verified V1 trading loop until V2 passes all integration gates.
3. **State File Versioning**:
   - V2 state files use `v2_state.json` and `v2_trades.jsonl`, leaving V1 logs completely intact.

---

## 13. Prioritized Blocker List (P0 to P4)

| Priority | Blocker Problem | Direct Evidence | Affected Component | Impact | Recommended Resolution | Dependencies |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P0** | **Historical Data Starvation** | Only 1 partial session (1,090 rows) on disk; master parquet missing | Data & Model Validation | Cannot certify models, pass edge gates, or validate backtests | Ingest 60–180 days of 5m historical data via broker/vendor | None |
| **P0** | **Zero Unit Tests** | No `tests/` directory; backtests crash on missing parquet files | Entire System | Zero regression protection; high bug risk during refactoring | Build automated test suite covering features, sizing, costs | None |
| **P1** | **Single-Share Price Cap** | Lines 675–676 in `compounding_trader.py` hard-blocks price > ₹1,250 | Risk / Sizing | 50% of universe barred from trading on ₹5,000 capital | Implement Risk-Based Integer Sizer based on ATR stop distance | Phase 5 |
| **P1** | **Timeframe / Fee Friction Mismatch** | 1m expected move (2–5 bps) < round-trip costs (8–15 bps) | Strategy / Models | Guaranteed negative expectancy over long runs | Shift core strategy horizon from 1-minute to 5-minute bars | Data |
| **P1** | **Missing Order Idempotency** | Orders use non-idempotent `TRD-{timestamp}`; no deduplication | Execution Engine | Catastrophic double-order submission risk on crash/retry | Implement UUIDv4 client order IDs & state machine | None |
| **P2** | **Full Feature Recomputation** | `extract_features_1m` recomputes 30 features across full history | Feature Engine | CPU spike; limits multi-symbol scaling | Implement `IncrementalFeatureEngine` with O(1) circular buffers | Phase 3 |
| **P2** | **Low Breakout Recall (4.55%)** | `model_metrics_1m.json`: Recall = 4.55%, F1 = 7.81% | Model Stack | Misses 95.45% of valid profitable breakouts | Retrain with focal loss / balanced class weights on 5m data | 5m Data |
| **P3** | **Aggressive Confidence Blacklist** | 8 out of 10 stocks blacklisted during midday Friday chop | Confidence Tracker | Complete trading stagnation during market consolidation | Replace binary blacklist with smooth Bayesian shrinkage | Phase 4 |
| **P3** | **yfinance REST Latency** | Synchronous REST scrape takes 15–45 seconds per batch | Market Ingestion | Leaves zero execution window within candle interval | Migrate to streaming WebSocket or fast async connection | Phase 2 |
| **P4** | **Legacy Crypto Code Artifacts** | `crypto/`, `executor.py` BTC checks, `RegimeClassifier` VPIN/funding | Repository Cleanliness | Confuses architectural boundaries and auditability | Cleanly excise crypto directories and dead prototypes | Phase 1 |
