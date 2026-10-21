# AlphaNSE V1 — Forensic Architecture Map

**Audited System**: AlphaNSE Intraday Quantitative Trading Engine  
**Audit Date**: September 19, 2026  
**Auditor**: Senior Quantitative Software Architect  
**Operational Status**: Phase 0 Complete — Audit & Architectural Mapping Baseline  
**Active Capital**: ₹4,999.21 Cash | 0 Open Positions | ₹0 Overnight Margin  

---

## 1. Executive Summary

This document establishes the authoritative, forensically verified architecture map of the **AlphaNSE V1** trading system as it currently exists in the repository. Every component, path, process, data dependency, and state structure documented herein was derived from direct inspection of the codebase. No planned V2 components, hypothetical brokers, or unverified datasets have been assumed.

### High-Level Architectural Reality
AlphaNSE V1 was originally prototyped as a cryptocurrency perpetuals trading system (evidenced by remaining artifacts referencing Binance WebSockets, funding rates, VPIN, 2-hour trade timeouts, and TDS assumptions) and subsequently retrofitted for Indian National Stock Exchange (NSE) cash equity trading.

In its current operational state, the system executes an automated 1-minute scanning loop using **FastAPI** (`QA/server/api.py`) and a core trader engine (`QA/engine/compounding_trader.py`). It relies on:
1. **yfinance polling via REST** for 1-minute OHLCV market data across 10 liquid NSE equities.
2. An **offline-trained 1-minute machine learning stack** (`QA/models/saved_models_1m/`) comprising an ensemble of regressors (LightGBM, XGBoost, CatBoost), a quantile regressor (P75), and a Platt-calibrated Gradient Boosting breakout classifier.
3. An Indian tax and fee computation engine (`QA/risk/india_tax_engine.py`) modeling Zerodha intraday equity costs.
4. A dynamic per-stock directional confidence tracker (`QA/models/stock_confidence_tracker.py`) that applies historical and rolling win-rate gates.
5. In-memory simulated paper order execution logged to flat JSON/JSONL files (`QA/logs/compounding_state.json` and `compounding_trades.jsonl`).
6. A dual frontend architecture: a legacy multi-page static web application (`QA/frontend/static/`) served via FastAPI, and a Streamlit surveillance dashboard (`QA/frontend/app.py`).
7. Autonomous background supervisors (`QA/engine/ai_agent_supervisor.py` and `QA/monitoring/continuous_supervisor.py`).

---

## 2. Repository Structure

```text
ift/
├── .gitignore                          # Git ignore configuration
├── allow_firewall_local_network.bat     # Windows firewall batch script for port exposure
├── check_engine_status.py              # CLI diagnostic script for querying engine status
├── check_predictor_signals.py          # CLI diagnostic script for testing 1-min predictions
├── gemini crypto.ipynb                 # Legacy Jupyter research notebook for crypto prototyping
├── optimized_threshold.txt             # Flat file caching optimized profit threshold
├── README.md                           # Top-level documentation
├── start_background_daemon.vbs         # VBScript runner for headless daemon background execution
├── start_continuous_trader.bat         # Batch launcher for supervisor + API server
├── start_trader.bat                    # Batch launcher for core trader
├── crypto/                             # LEGACY CRYPTO PROTOTYPE DIRECTORY
│   ├── dashboard.py                    # Legacy crypto Streamlit dashboard
│   ├── README.md                       # Crypto prototype documentation
│   ├── requirements.txt                # Crypto prototype dependencies (ccxt, etc.)
│   └── simulate_layers.py              # Crypto multi-layer orderbook simulation
└── QA/                                 # PRIMARY ACTIVE REPOSITORY ROOT
    ├── analyze_correlations.py         # Utility: Cross-asset return correlations
    ├── auto_retrain.py                 # Utility: Scheduled daily retraining loop
    ├── autonomous_trader.py            # Legacy standalone trader prototype
    ├── background_market_monitor.py    # Background market status poller
    ├── compare_actuals.py              # Utility: Compares predicted vs actual candle closes
    ├── emergency_preprocess.py         # Utility: Emergency dataset normalization
    ├── final_merge_prep.py             # Utility: Data pipeline preprocessing
    ├── GEMINI.md                       # Workspace custom instructions and operational memory
    ├── global_opportunity_finder.py    # Utility: Multi-stock scanner prototype
    ├── high_growth_scan.py             # Utility: High-growth stock scanner
    ├── live_monitor.py                 # Utility: Terminal-based live terminal monitor
    ├── live_prediction_simulation.py   # Utility: Real-time simulation of model outputs
    ├── market_24h_scan.py              # Utility: Crypto 24h market scanner (legacy)
    ├── market_scan.py                  # Utility: Stock market scanner
    ├── microstructure_pattern_analyzer.py # Microstructure pattern research
    ├── nse_auto_trader.py              # Predecessor automated trading engine
    ├── optimize_threshold.py           # Threshold grid search optimization
    ├── prediction_lab.py               # Standalone interactive prediction terminal
    ├── remaining_issues.txt            # Audit notes from earlier debugging session
    ├── requirements.txt                # Production Python dependencies
    ├── scalp_monitor_5m.py             # 5-minute scalp monitoring utility
    ├── sequence_lab.py                 # Sequence model experiment runner
    ├── simulate_yesterday.py           # Replay simulation on previous day's data
    ├── stocks_config.py                # Core configuration: Universe, blacklist, timing, risk
    ├── stock_simulator.py              # Synthetic stock price path simulator
    ├── unicode_scan_results.txt        # Diagnostic log from encoding audit
    ├── volatility_alert.py             # Utility: Volatility spike alerter
    ├── backtesting/                    # HISTORICAL BACKTESTING ENGINE
    │   ├── backtest.py                 # Core backtester with execution realism & meta-labeling
    │   ├── full_system_backtest.py     # End-to-end backtest pipeline runner
    │   ├── metrics.py                  # Quant metrics (Sharpe, Sortino, Max Drawdown, Win Rate)
    │   ├── monte_carlo.py              # Monte Carlo path permutation simulator
    │   ├── multi_regime.py             # Multi-regime return segmentation
    │   ├── multi_regime_backtest.py    # Backtest partitioned across market regimes
    │   └── stress_test.py              # Extreme volatility and liquidity stress tester
    ├── data/                           # MARKET DATA STORAGE & INGESTION
    │   ├── append_recent_features.py   # Appends new intraday features to parquet store
    │   ├── binance_archive_downloader.py # LEGACY: Binance monthly zip downloader
    │   ├── cross_asset_engine.py       # Cross-asset feature calculation
    │   ├── expand_dataset.py           # Dataset expansion utility
    │   ├── fetch_multi_asset_data.py   # Multi-asset historical downloader
    │   ├── fetch_recent_update.py      # Incremental daily update fetcher
    │   ├── fetch_stock_data.py         # Main yfinance historical batch fetcher
    │   ├── fetch_trend_data.py         # Trend data fetcher
    │   ├── friday_session_features.csv # ACTIVE DATASET: Friday 2026-09-18 harvested features
    │   ├── news_sentiment_engine.py    # Unused placeholder sentiment engine
    │   └── whale_flow_monitor.py       # Order flow monitor prototype
    ├── engine/                         # CORE EXECUTION & SUPERVISION
    │   ├── ai_agent_supervisor.py      # Tri-surface autonomous diagnostic & tuning supervisor
    │   └── compounding_trader.py       # Main production trading engine (1-min loop)
    ├── events/                         # MACROECONOMIC EVENTS
    │   └── macro_event_manager.py      # Calendar event risk dampener
    ├── execution/                      # EXECUTION & MARKET IMPACT MODELING
    │   ├── execution_quality_monitor.py# Execution quality tracking (slippage vs spread)
    │   ├── latency_simulator.py        # Network and broker execution delay simulator
    │   ├── market_impact_model.py      # Square-root temporary & permanent impact model
    │   └── regime_router.py            # Execution routing based on market state
    ├── features/                       # FEATURE ENGINEERING PIPELINES
    │   ├── build_final_master.py       # Orchestrates master dataset feature matrix build
    │   ├── feature_pipeline.py         # Standardized technical feature computation
    │   ├── historical_pipeline.py      # Batch feature pipeline for historical bars
    │   ├── macro_features.py           # Macroeconomic calendar distance features
    │   ├── master_feature_pipeline.py  # Consolidated feature pipeline (30+ indicators)
    │   ├── microstructure.py           # Microstructure indicators (OFI, VPIN, Microprice)
    │   ├── process_multi_asset.py      # Inter-market lead-lag feature processing
    │   ├── process_trend_data.py       # Trend feature transformations
    │   ├── regime.py                   # Market regime feature computation
    │   └── technical.py                # Core technical indicators (RSI, ATR, BB)
    ├── frontend/                       # USER INTERFACES & DASHBOARDS
    │   ├── app.py                      # Active Streamlit surveillance dashboard
    │   └── static/                     # Static web assets served by FastAPI
    │       ├── app.html                # Trading desk view
    │       ├── app.js                  # Frontend WebSocket client and DOM controller
    │       ├── index.html              # Marketing/overview landing page
    │       ├── lab.html                # Simulation & Model verification laboratory
    │       ├── styles.css              # Frontend styling
    │       └── website.html            # Documentation and overview portal
    ├── labels/                         # TARGET LABELING PIPELINES
    │   ├── micro_horizon_labels.py     # Short-horizon forward return labeling
    │   ├── probability_labels.py       # Binary breakout and threshold labeling
    │   └── triple_barrier.py           # Triple-barrier labeling (de Prado)
    ├── logs/                           # RUNTIME PERSISTENCE, TELEMETRY & LOGS
    │   ├── ai_agent_telemetry.json     # Supervisor state, thought stream, action plans
    │   ├── closing_sentinel_ticks.jsonl# Harvested tick logs from 15:00-15:30 closing window
    │   ├── compounding_state.json      # Master trader persistence (capital, positions, NAV)
    │   ├── compounding_trades.jsonl    # Immutable trade execution ledger
    │   ├── dataset_friday_session_1m.jsonl # Harvested 1-minute bars from Friday session
    │   ├── friday_final_session_dossier.json # Session summary dossier
    │   ├── stock_confidence_tracker.json # Rolling hit-rate history & per-symbol multipliers
    │   ├── trader_state.json           # Legacy trader state cache
    │   ├── agent_audits/               # Multi-agent diagnostic audit logs
    │   └── live_metrics/               # Runtime process logs (supervisor, uvicorn, sentinel)
    ├── models/                         # ML MODEL DEFINITIONS, TRAINING & ARTIFACTS
    │   ├── expected_return_regressor.py# Regressor training and inference abstractions
    │   ├── feature_registry.py         # Feature column registry for model schemas
    │   ├── final_ensemble_engine.py    # Multi-model ensemble inference combiner
    │   ├── kalman_price_filter.py      # 1D Kalman filter for price denoising
    │   ├── lstm_orderflow_model.py     # PyTorch LSTM order flow prototype
    │   ├── meta_labeling.py            # Secondary meta-model filter (de Prado)
    │   ├── microprice_model.py         # Stoikov microprice calculator
    │   ├── microstructure_forecaster.py# Microstructure feature forecaster
    │   ├── model_audit.py              # Model calibration and performance audit script
    │   ├── one_min_predictor.py        # ACTIVE 1-minute predictor ensemble class
    │   ├── stock_confidence_tracker.py # Active dynamic confidence and blacklist tracker
    │   ├── train_ensemble.py           # Ensemble model training script
    │   ├── train_regime_specialists.py # Specialist models trained per market regime
    │   ├── train_xgboost.py            # Standalone XGBoost training script
    │   ├── saved_models/               # 5-minute legacy model artifacts (XGB, LGBM, CatBoost)
    │   ├── saved_models_1m/            # ACTIVE 1-minute model artifacts (joblib + JSON)
    │   └── saved_models_sim/           # Simulation sandbox model artifacts
    ├── monitoring/                     # HEALTH CHECKS, HARVESTERS & WATCHDOGS
    │   ├── close_session_sentinel.py   # EOD 15:00-15:30 closing telemetry sentinel
    │   ├── continuous_supervisor.py    # Active background daemon process watchdog
    │   ├── feature_drift.py            # Feature drift detection utility
    │   ├── friday_session_harvester.py # 1-minute live data harvester
    │   ├── live_dashboard.py           # Rich terminal live dashboard
    │   └── live_server_monitor.py      # Server HTTP ping and health monitor
    ├── paper_trading/                  # SIMULATED TRADING INFRASTRUCTURE
    │   ├── executor.py                 # Paper trade executor (contains crypto restrictions)
    │   └── paper_wallet.py             # In-memory balance and position tracker
    ├── regimes/                        # MARKET REGIME CLASSIFICATION
    │   └── regime_classifier.py        # GMM classifier (crypto legacy) + classify_micro_regime (active)
    ├── research/                       # RESEARCH SCRIPTS & EXPERIMENTAL AUDITS
    │   ├── confidence_analysis.py      # Rolling confidence threshold evaluation
    │   ├── crisis_simulator.py         # Flash crash and liquidity shock simulations
    │   ├── feature_importance_shap.py  # SHAP value tree explainer
    │   ├── tax_bleed_simulator.py      # Friction and fee bleed Monte Carlo simulator
    │   └── validate_leakage.py         # Information leakage and look-ahead validator
    ├── risk/                           # RISK CONTROLLERS & TAX CALCULATORS
    │   ├── dynamic_position_sizer.py   # Fractional Kelly and volatility-adjusted sizer
    │   ├── global_risk_controller.py   # Portfolio-level circuit breakers & drawdown halts
    │   ├── india_tax_engine.py         # Real Zerodha intraday equity cost model
    │   ├── inr_accounting_engine.py    # INR bookkeeper with tax withholding
    │   ├── position_sizing.py          # Baseline position sizing formulas
    │   ├── post_tax_expectancy_filter.py # Trade hurdle filter enforcing positive post-tax EV
    │   └── trade_ranking_engine.py     # Cross-symbol trade priority ranker
    ├── sampling/                       # SAMPLING METHODOLOGIES
    │   └── event_sampling.py           # CUSUM filter and dollar-bar event sampling
    ├── scripts/                        # OPERATIONAL UTILITIES & RUNNERS
    │   ├── build_and_train_live_1m.py  # End-to-end 1-minute model pipeline retrainer
    │   ├── check_radar.py              # CLI symbol radar checker
    │   └── predict_universe_offmarket.py # Generates off-market next-day opening predictions
    ├── server/                         # FASTAPI APPLICATION & WEBSOCKET HUB
    │   └── api.py                      # FastAPI server implementation
    ├── storage/                        # DATABASE CONNECTORS
    │   └── mongo_store.py              # MongoDB tick and order store (partially configured)
    ├── synthetic/                      # SYNTHETIC DATA GENERATION
    │   ├── bootstrap_generator.py      # Stationary bootstrap resampling
    │   ├── generate_and_label_synthetic.py # Synthetic data generation with labels
    │   └── monte_carlo_regime_simulator.py # Regime-switching Markov chain simulator
    ├── validation/                     # STATISTICAL VALIDATION
    │   ├── oos_regime_test.py          # Out-of-sample regime test runner
    │   ├── purged_cv.py                # Purged and embargoed K-Fold cross-validation
    │   ├── validate_leakage.py         # Feature timestamp leakage checker
    │   └── validate_market_data.py     # Tick anomaly and candle validator
    └── websocket/                      # LIVE STREAMING PROTOCOLS
        ├── binance_stream.py           # LEGACY: Binance WebSocket client
        └── orderbook_collector.py      # LEGACY: L2 order book WebSocket collector
```

---

## 3. Runtime Architecture

AlphaNSE V1 does not operate as a distributed microservice mesh. Instead, it runs as a small set of cooperating processes on a single Windows host:

```text
[Windows Host OS]
  │
  ├── Process 1: Continuous Supervisor Watchdog (PID background)
  │     └─ `QA/monitoring/continuous_supervisor.py`
  │          └─ Health checks Uvicorn API server on port 8000
  │          └─ Restarts API server if process terminates or hangs
  │
  ├── Process 2: FastAPI Server & In-Process Trader Engine
  │     └─ `QA/server/api.py` (running under Uvicorn on 0.0.0.0:8000)
  │          ├─ In-Process Instance: `CompoundingTrader` (`QA/engine/compounding_trader.py`)
  │          │    └─ Worker Thread: `_trading_loop()` (executes every 60s during market hours)
  │          ├─ In-Process Instance: `AIAgentSupervisor` (`QA/engine/ai_agent_supervisor.py`)
  │          │    └─ Worker Thread: `_surveillance_loop()` (audits telemetry every 60s)
  │          ├─ In-Memory Model Cache: `OneMinPredictor` (`QA/models/one_min_predictor.py`)
  │          ├─ In-Memory Confidence State: `StockConfidenceTracker`
  │          ├─ In-Memory State & Order Book: `compounding_state.json`
  │          ├─ WebSocket Broadcaster: pushes ticks, predictions, and trades to connected UIs
  │          └─ Static File Server: hosts HTML/JS/CSS frontend
  │
  └── Process 3: Streamlit Live Surveillance Dashboard
        └─ `QA/frontend/app.py` (running on 0.0.0.0:8501)
             └─ Polls `http://localhost:8000/api/state`, `/api/signals`, `/api/trades`
```

### Detailed Runtime Execution Flow

```text
[Timer: 60-Second Loop in CompoundingTrader Thread]
                    │
                    ▼
[Market Hours Check] ──(Outside 09:15-15:30 IST)──► [Sleep / Freeze State]
                    │ (Inside Market Hours)
                    ▼
[Data Ingestion: REST Polling via yfinance]
   Fetch latest 1-minute OHLCV bars for 10 universe stocks
   Latency: 15 to 45 seconds per batch
                    │
                    ▼
[Verify Prior Minute Predictions]
   Compare t-1 predicted return against t_0 actual close
   Update `StockConfidenceTracker` (hit vs miss)
   Save verification records to `compounding_state.json`
                    │
                    ▼
[Feature Engineering: Full Recomputation]
   `extract_features_1m()` in `OneMinPredictor`
   Computes all 30 indicators from scratch over full candle window
   Complexity: O(N) per stock per minute
                    │
                    ▼
[Micro-Regime Classification]
   `classify_micro_regime()` in `QA/regimes/regime_classifier.py`
   Evaluates EMA 5/20 slope, momentum, ATR expansion
   Outputs: Regime (BULL/BEAR/SIDEWAYS), Hurdle Multiplier, allows_long_scalp
                    │
                    ▼
[ML Inference: 1-Minute Ensemble Stack]
   Regressors (LGBM, XGB, CatBoost) -> Mean expected return
   Quantile Regressor -> P75 upper bound return
   Platt-Calibrated Classifier -> Probability of breakout (return >= 10 bps)
   Dynamic Confidence Multiplier applied from `StockConfidenceTracker`
                    │
                    ▼
[Filter 1: Confidence & Blacklist Gate]
   Check if stock is in static blacklist (`SBIN`, `AXISBANK`, `ICICIBANK`, `HDFCBANK`, `BAJFINANCE`)
   or dynamic blacklist (rolling accuracy < 45-50% in `StockConfidenceTracker`)
   If blacklisted: Suppress BUY -> force HOLD
                    │
                    ▼
[Filter 2: Hurdle & Regime Gate]
   Predicted return must exceed `effective_threshold` (adjusted by regime hurdle)
   Market regime must permit long scalps (`allows_long_scalp == True`)
   Opening cooldown (09:15-09:20) and symbol exit cooldown (300s) must be clear
                    │
                    ▼
[Filter 3: Capital & Single-Share Price Cap Gate]
   `total_capital <= 10000` AND `curr_price > total_capital * 0.25`
   If stock price > ₹1,249.80: REJECT ORDER (Hard Block)
                    │
                    ▼
[Position Sizing: Integer Share Sizing]
   Target allocation = 15% of available capital
   `qty = int(invest_amount / curr_price)`
   If `qty < 1`: default to 1 share
   If `actual_invested > available_capital`: REJECT ORDER
                    │
                    ▼
[Simulated Order Execution]
   Deduct `actual_invested` from `available_capital`
   Add position to `positions` dict in memory
   Write immutable record to `compounding_trades.jsonl`
   Flush updated portfolio state to `compounding_state.json`
                    │
                    ▼
[Broadcast Event via WebSockets]
   Push `TICK_UPDATE`, `TRADE_EXECUTED`, `PREDICTION_VERIFIED` to WebSocket clients
```

---

## 4. Data Flow

### Primary Ingestion Path
```text
Yahoo Finance API (REST: https://query1.finance.yahoo.com)
     │  (Synchronous HTTP GET via yfinance library)
     ▼
CompoundingTrader (`candles_cache` dictionary in memory)
     │  (Pandas DataFrame: columns ['timestamp', 'open', 'high', 'low', 'close', 'volume'])
     ▼
OneMinPredictor (`extract_features_1m`)
     │  (Full DataFrame copy, sorted by timestamp, 30 engineered features generated)
     ▼
Model Inference
```

### Persistence Path
```text
In-Memory State (`self.state` dict in CompoundingTrader)
     │
     ├── Atomic Write ──► `QA/logs/compounding_state.json` (Full snapshot: NAV, positions, verifications)
     │
     └── Append Line  ──► `QA/logs/compounding_trades.jsonl` (Audit trail of every BUY/SELL execution)
```

---

## 5. Model Flow

```text
Raw 1-Minute Candles (10 NSE Equities)
            │
            ▼
[extract_features_1m] ── 30 Technical, Microstructure & Cyclical Features:
            ├─ Returns: ret_1m, ret_3m, ret_5m, ret_10m, accel_1m
            ├─ Volatility: micro_atr_14, parkinson_vol, parkinson_vol_rolling, atr_vol_ratio
            ├─ Technicals: micro_rsi_7, micro_rsi_14, bb_pct_b, bb_bandwidth, ema_cross_5_20, ema_cross_velocity
            ├─ Microstructure: micro_vwap_dist, rolling_vwap_dist, orderflow_imbalance, vol_surge_ratio, vol_spike_zscore, wick_pressure, upper_wick_ratio, lower_wick_ratio
            ├─ Cross-Asset: nifty_ret_1m, nifty_lead_lag
            └─ Cyclical/Identity: time_sin, time_cos, session_phase, stock_id_hash
            │
            ├──────────────────────────┬──────────────────────────┐
            ▼                          ▼                          ▼
[Ensemble Regressors]       [Quantile Regressor]      [Breakout Classifier]
- LightGBM (MAE)            - LGBMRegressor           - GradientBoosting
- XGBoost (Squared Error)     (alpha=0.75)              (Platt-calibrated
- CatBoost (MAE)                                         via CalibratedClassifierCV)
            │                          │                          │
            ▼                          ▼                          ▼
   Mean Expected Return        P75 Return Bound           Calibrated Probability
   (e.g., +0.082%)             (e.g., +0.145%)            (e.g., 58.2%)
            │                                                     │
            └──────────────────────────┬──────────────────────────┘
                                       ▼
                       [Stock Confidence Multiplier]
                       P_final = P_raw * confidence_multiplier
                                       │
                                       ▼
                       [Signal Decision Threshold]
                       BUY if Expected Return >= Dynamic Hurdle
                       AND Calibrated Confidence >= 45%
```

---

## 6. Risk Flow

Risk in AlphaNSE V1 is distributed across several disparate files, with some duplication and conflicts:

1. **Portfolio Capital Constraints** (`QA/engine/compounding_trader.py`):
   - Total Capital: ₹4,999.21.
   - Available vs. Invested Capital reconciliation on restart.
   - Max 5 concurrent open positions.
   - Minimum trade allocation: ₹350 (accounts $\le$ ₹10,000) or ₹1,000.

2. **Price Cap Filter** (`QA/engine/compounding_trader.py` lines 675–676):
   - Single-share price cap: $0.25 \times \text{total\_capital} = ₹1,249.80$.
   - Hard-blocks 50% of the active universe on small accounts.

3. **Stop-Loss & Take-Profit Rules** (`QA/engine/compounding_trader.py`):
   - Hard stop-loss: 0.30% gross loss.
   - Profit exit hurdle: Expected return $\ge 0.08\%$ (8 bps) net of all costs.
   - Max hold time: 15 candles (15 minutes) before forced time-decay liquidation.

4. **Tax & Cost Deduction Filter** (`QA/risk/india_tax_engine.py`):
   - Computes Zerodha intraday equity costs: 0.03% (capped at ₹20) brokerage per side, 0.025% sell-side STT, exchange turnover fees (0.00307%), SEBI fees (0.0001%), 18% GST on fees, 0.003% buy-side stamp duty, 2.5 bps slippage, and 25% short-term capital gains tax buffer.

5. **Legacy Risk Components (Unused by Active Engine)**:
   - `QA/risk/global_risk_controller.py`: Contains crypto 10% daily drawdown circuit breaker.
   - `QA/risk/dynamic_position_sizer.py`: Fractional Kelly sizer (superseded by trader's internal 15% rule).
   - `QA/risk/post_tax_expectancy_filter.py`: 15 bps minimum net filter.

---

## 7. Execution Flow

Execution in AlphaNSE V1 is purely simulated and strictly internal:

1. **No External Broker Connection**:
   - There is no active API connection to Zerodha Kite Connect, Angel One SmartAPI, Upstox, or Dhan.
   - Orders are simulated objects instantiated in Python memory.

2. **Order Structure**:
   - Each trade receives an internal string ID: `TRD-{int(time.time()*1000)}`.
   - Action: `BUY` or `SELL`.
   - Executed at the current bar's closing price (zero market impact, fixed 2.5 bps modeled slippage).

3. **Fill Assumptions**:
   - Immediate 100% full fill at quoted price.
   - No partial fills, order rejections, exchange throttling, or queue latency modeled during live scanning.

4. **Idempotency & Duplicate Protection**:
   - **CRITICAL DEFECT**: There are **no client order IDs**, **no idempotency keys**, and **no deduplication mechanisms**.
   - If the trading process crashes mid-execution or restarts during a network retry, order state cannot be reconciled against an external broker.

---

## 8. State Persistence & Crash Recovery

### What Survives a Process Crash / Machine Restart:
* **Total Portfolio Capital**: Stored in `QA/logs/compounding_state.json`.
* **Active Open Positions**: Stored in `compounding_state.json` (`entry_price`, `qty`, `invested`, `entry_time`).
* **Cumulative Realized PnL & NAV Curve**: Up to 100 historical NAV points stored in `compounding_state.json`.
* **Trade History**: Appended to `QA/logs/compounding_trades.jsonl`.
* **Stock Confidence History**: Last 50 verification outcomes per stock saved in `QA/logs/stock_confidence_tracker.json`.
* **Supervisor Thoughts & Action Plans**: Saved in `QA/logs/ai_agent_telemetry.json`.

### What Is Lost on Process Crash / Restart:
* **WebSocket Client Connections**: All active browser client sockets are severed.
* **In-Memory Candle Cache**: `candles_cache` is cleared, forcing fresh REST fetches on startup.
* **Pending Predictions**: `pending_predictions` dictionary is lost unless reconstructed from logs.
* **Exit Cooldown Timers**: `last_exit_times` dictionary is lost, allowing immediate re-entry after restart.

### Watchdog Supervision (`continuous_supervisor.py`):
* Polls `http://localhost:8000/api/health` every 15 seconds.
* If 3 consecutive health checks fail, kills any orphaned Python Uvicorn process and restarts `start_continuous_trader.bat`.
* Reconciles invested capital against open positions on boot (`calc_invested = sum(pos['invested'])`).

---

## 9. API & Server Architecture

The API layer is built on **FastAPI** (`QA/server/api.py`), exposed over Uvicorn on port 8000.

### Reusable Production Endpoints
* `GET /api/health` — Liveness and timestamp check.
* `GET /api/state` — Returns total capital, available capital, open positions, unrealized PnL, NAV curve.
* `GET /api/signals` — Returns current 1-minute ML predictions, hurdle rates, regimes, and signals across universe.
* `GET /api/predictions/verification` — Returns rolling accuracy, hit rates, and recent prediction-vs-actual records.
* `GET /api/stocks/profiles` — Returns per-stock directional accuracy, confidence multipliers, and blacklist status.
* `GET /api/trades` — Returns historical trades for the active session.
* `GET /api/trades/history` — Returns complete trade history across all sessions with symbol and date filters.
* `GET /api/market-status` — Returns NSE market hours status (open, pre-open, closed).
* `POST /api/control` — Accepts `start`, `pause`, `emergency_close`, `scan_now`.
* `POST /api/settings` — Updates parameters (`profit_threshold_pct`, `stop_loss_pct`, `position_sizing_pct`).
* `WebSocket /ws` — High-speed real-time event streaming (`TICK_UPDATE`, `TRADE_EXECUTED`, `PREDICTION_VERIFIED`).

---

## 10. Monitoring & Telemetry

* **Streamlit Dashboard** (`QA/frontend/app.py`): Running on port 8501, provides visual cards for NAV, PnL, active positions, radar signals, execution history, and confidence trackers.
* **Static Web Dashboard** (`QA/frontend/static/`): Multi-page HTML5/Vanilla JS interface connecting to FastAPI via WebSocket and REST.
* **Log Files**:
  * `QA/logs/live_metrics/server_uvicorn.log`: API server stdout/stderr.
  * `QA/logs/live_metrics/supervisor.log`: Process watchdog health checks.
  * `QA/logs/live_metrics/closing_model_sentinel.json`: EOD closing tick surveillance.

---

## 11. Testing & Validation

### Current State of Test Suite:
* **CRITICAL FINDING: ZERO UNIT TESTS EXIST.**
* There is no `tests/` directory, no `pytest` configurations, and no automated continuous integration (CI) tests.
* The only testing code consists of offline scripts:
  * `QA/backtesting/backtest.py`: Standalone backtest script (fails because `data/processed/labeled_data.parquet` is missing).
  * `QA/validation/oos_regime_test.py`: Out-of-sample script (fails because parquet data is missing).
  * `QA/validation/validate_leakage.py`: Standalone lookahead leakage checker.

---

## 12. Component Inventory Table

| Component | File(s) | Purpose | Inputs | Outputs | Runtime Role | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CompoundingTrader** | `QA/engine/compounding_trader.py` | Core 1-min loop, order execution, sizing, compounding | yfinance 1m bars, model predictions | Trade logs, state JSON, WS events | Primary Trader Engine | **ACTIVE** |
| **OneMinPredictor** | `QA/models/one_min_predictor.py` | 1-minute ML ensemble inference and feature pipeline | 1m OHLCV candle DataFrame | Predicted return, breakout prob, signal | Primary Model Stack | **ACTIVE** |
| **IndiaTaxEngine** | `QA/risk/india_tax_engine.py` | Calculates Zerodha intraday equity taxes & fees | Capital, gross return, slippage | Detailed cost breakdown dict, net profit | Core Cost Engine | **ACTIVE** |
| **StockConfidenceTracker**| `QA/models/stock_confidence_tracker.py` | Tracks per-symbol prediction hit-rates & blacklists | Realized direction vs prediction | Confidence multiplier (0.0 to 1.5), blacklist | Risk & Alpha Gate | **ACTIVE** |
| **FastAPI Hub** | `QA/server/api.py` | REST API, WebSocket distribution, static frontend host | HTTP requests, trader event callbacks | JSON payloads, WS stream, HTML/JS | Primary Server | **ACTIVE** |
| **ContinuousSupervisor** | `QA/monitoring/continuous_supervisor.py` | Process supervisor & watchdog restart monitor | HTTP health pings to port 8000 | Process start/restart commands, log alerts | System Watchdog | **ACTIVE** |
| **Streamlit App** | `QA/frontend/app.py` | Visual operator surveillance dashboard | FastAPI REST API endpoints | Web UI on port 8501 | Primary Frontend | **ACTIVE** |
| **AIAgentSupervisor** | `QA/engine/ai_agent_supervisor.py` | Tri-surface surveillance and auto-tuning | Trader state, accuracy metrics | Auto-tuned params, action plans | Background Daemon | **PARTIALLY_ACTIVE** |
| **MicroRegimeClassifier**| `QA/regimes/regime_classifier.py` | Deterministic micro-regime identification | 1-min candle DataFrame | Regime name, hurdle multiplier | Strategy Filter | **ACTIVE** |
| **GMM RegimeClassifier** | `QA/regimes/regime_classifier.py` | Gaussian Mixture Model regime clustering | Crypto funding rate, VPIN | Regime string | Legacy Classifier | **LEGACY** |
| **PaperExecutor** | `QA/paper_trading/executor.py` | Paper trade execution engine | Features DataFrame | Paper trade log CSVs | Execution Engine | **BROKEN** (Crypto-gated) |
| **Backtester** | `QA/backtesting/backtest.py` | Historical strategy backtester | Parquet labeled dataset | Performance metrics | Backtest Engine | **BROKEN** (Missing data) |
| **OOS Regime Test** | `QA/validation/oos_regime_test.py` | 2023 vs 2024 out-of-sample validation | Parquet labeled dataset | Classification reports | Model Validation | **BROKEN** (Missing data) |
| **BinanceStream** | `QA/websocket/binance_stream.py` | Binance WebSocket depth & trade streaming | Binance WS connection | Raw crypto tick frames | Market Feed | **LEGACY** |
| **MongoStore** | `QA/storage/mongo_store.py` | MongoDB tick and order collection store | PyMongo connection, tick dicts | Database writes | Database Storage | **UNUSED** |
| **CloseSessionSentinel**| `QA/monitoring/close_session_sentinel.py` | 15:00-15:30 closing window telemetry harvester | Live trading state & yfinance ticks | `closing_sentinel_ticks.jsonl` | Monitoring Harvest | **ACTIVE** |

---

## 13. Reusable V1 Components for V2

The following components represent proven, functional engineering assets that should be retained and migrated into V2:

1. **`IndiaTaxEngine` (`QA/risk/india_tax_engine.py`)**:
   - Highly accurate Zerodha intraday equity cost model (brokerage, STT, exchange, SEBI, GST, stamp duty, slippage).
   - Direct drop-in component for V2 transaction-cost-aware expected value filters.
2. **FastAPI & WebSocket Server Architecture (`QA/server/api.py`)**:
   - Robust endpoint structure, CORS handling, threadsafe WebSocket event broadcasting, and Pydantic validation.
   - Clean separation of UI distribution from execution.
3. **State Persistence Patterns (`QA/logs/compounding_state.json` & `compounding_trades.jsonl`)**:
   - Atomic state file flushing and append-only trade journaling ensure crash resilience.
4. **Continuous Process Watchdog (`QA/monitoring/continuous_supervisor.py`)**:
   - Reliable HTTP-based process supervision and auto-restart behavior.
5. **Deterministic Micro-Regime Logic (`classify_micro_regime` in `QA/regimes/regime_classifier.py`)**:
   - Lightweight, deterministic EMA slope and ATR expansion calculation without heavy dependencies.
6. **Frontend Dashboards (`QA/frontend/app.py` & `QA/frontend/static/`)**:
   - Comprehensive telemetry views, NAV curves, and radar boards ready to bind to V2 streams.

---

## 14. Problematic Components

1. **`compounding_trader.py` Single-Share Price Cap (Lines 675–676)**:
   - Hardcoded `curr_price > total_capital * 0.25` prevents trading any stock priced above ₹1,249 on small accounts, locking out 50% of the universe.
2. **`OneMinPredictor.extract_features_1m()`**:
   - Recomputes all 30 indicators across the entire historical candle history on every single 1-minute tick ($\mathcal{O}(N)$ computational overhead).
3. **`OneMinPredictor` Breakout Classifier (`breakout_classifier_1m.joblib`)**:
   - Test breakout recall is **4.55%**, failing to detect 95.45% of actual $\ge 10\text{ bps}$ upward price movements.
4. **`stock_confidence_tracker.py` Aggressive Suppression**:
   - Stocks falling below 45% rolling directional accuracy are blacklisted with a zero multiplier, shutting down trading across 80% of the universe during midday chop.
5. **yfinance Polling Latency**:
   - Ingesting 1-minute data via synchronous REST scraping introduces 15–45 second delays, making 1-minute candle scalping fundamentally unviable.

---

## 15. Legacy Components (Crypto & Unused)

1. **`crypto/` directory**: Entire prototype folder (`crypto/dashboard.py`, `crypto/simulate_layers.py`) is completely disconnected from NSE equity trading.
2. **`QA/paper_trading/executor.py`**: Contains hardcoded check restricting assets to `['BTCUSDT', 'ETHUSDT', 'SYNTH_BTC']`.
3. **`QA/websocket/binance_stream.py` & `orderbook_collector.py`**: Connects to Binance WebSocket endpoints (`wss://stream.binance.com:9443`).
4. **`RegimeClassifier` in `QA/regimes/regime_classifier.py`**: Expects `funding_rate` and `vpin` columns.
5. **`gemini crypto.ipynb`**: Legacy Jupyter notebook.

---

## 16. Current Performance Bottlenecks

```text
+----------------------------+-------------------------------------+---------------------------------------------------------+
| Pipeline Stage             | Measured / Observed Latency         | Root Cause                                              |
+----------------------------+-------------------------------------+---------------------------------------------------------+
| Market Data Ingestion      | 15,000 ms – 45,000 ms               | Synchronous yfinance REST polling over 10 symbols       |
| Feature Extraction         | 80 ms – 150 ms per symbol           | Full O(N) recomputation over entire candle window       |
| Model Inference            | 45 ms – 90 ms per symbol            | Sequential inference across 4 separate tree models      |
| Execution Routing          | < 1 ms                              | In-memory simulated dictionary updates                  |
| State Persistence          | 5 ms – 15 ms                        | Disk JSON serialization                                 |
+----------------------------+-------------------------------------+---------------------------------------------------------+
```

*The 15–45 second data polling latency consumes up to 75% of the 60-second candle interval, leaving virtually zero time for micro-alpha execution.*

---

## 17. Architectural Risks

1. **Lookahead Bias in Dynamic Blacklists**:
   - Rolling accuracy windows calculated without purge/embargo boundaries leak immediate post-event outcomes into signal filtering.
2. **Missing Order Idempotency**:
   - Absence of client order IDs and broker reconciliation creates catastrophic double-fill risk if live execution is connected.
3. **Timeframe Mismatch vs. Friction**:
   - 1-minute expected return (2–5 bps) is smaller than the round-trip transaction friction (8–15 bps), resulting in guaranteed negative expectancy over large sample sizes.
4. **Data Starvation**:
   - The repository contains only 1 partial session of stored 1-minute bars, preventing statistical validation of strategy edge.
