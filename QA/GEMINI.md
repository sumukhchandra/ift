# Gemini Quantitative Trading Engine: System Definition & Mandates

## Core Mission
To build an adaptive, institutional-style quantitative crypto trading engine focused on probabilistic prediction, regime-aware execution, and capital preservation.

## Strategic Pivot: Net-Edge Survival
**Primary Strategy:** Low-Frequency, High-Conviction Quantitative Swing Trading.
*   **Target Asset Class:** Institutional liquidity pairs ONLY (`BTCUSDT`, `ETHUSDT`).
*   **Objective:** Optimize for post-tax, post-frictions "Net Edge" rather than trade count.
*   **Trade Profile:** 1-5 elite trades per day with >2.5% move targets and multi-hour holding horizons.

## Two-Layer System Architecture
### Layer 1: Statistical Quantitative Engine (Active)
*   **Focus:** Directional Alpha and Magnitude Estimation ("Should we trade?").
*   **Intelligence:** Regime-aware ensembles, Expected Return Regressors, and Trade Ranking.
*   **Timeline:** Currently under 30-day Reality Validation (Architecture Freeze).

### Layer 2: Microstructure Intelligence (Planned)
*   **Focus:** Execution Alpha and Slippage Optimization ("How should we execute?").
*   **Intelligence:** L2 Orderbook dynamics, Microprice models, and Kalman filtering.
*   **Timeline:** Research and infrastructure planning phase.

## Core Objectives
### 1. Probabilistic Price & Magnitude Prediction
*   Predict **Probability(Up)**, **Probability(Down)**, and **Expected Return Magnitude**.

### 2. Fully Automated Decision Engine
*   **Asset Selection:** BTC/ETH ONLY.
*   **Direction:** ML Probability Engine.
*   **Ranking:** TradeRankingEngine (Net Edge Score).
*   **Sizing:** Dynamic Risk Sizing + Frequency Penalties.
*   **Execution:** Orderflow + Liquidity-aware Slippage simulation.
*   **Accounting:** INR Ledger tracking TDS and tax liability.

## Fiscal & Execution Frictions (India Context)
1.  **Tax-Aware Alpha:** All trade decisions filtered through `IndiaTaxEngine` (30% Profit Tax, 1% TDS). 
2.  **Minimum Expectancy:** Reject any trade where `Expected_Net_Return < 15 bps` or `Expected_Gross_Move < 1.5%`.
3.  **TDS Survival:** Penalize high trade frequency to prevent capital lockup in TDS deductions.
4.  **Liquid Assets Only:** Strictly avoid illiquid altcoins to minimize spread-cross costs.

## Core Development Laws
1.  **Stability First:** Fixing infrastructure issues takes precedence over adding intelligence.
2.  **Fiscal Discipline:** Optimized post-tax expectancy is the ONLY valid performance metric. Raw PnL is a vanity metric.
3.  **Risk Priority:** Never trade without active Global Risk Controls (Drawdown, Exposure, Volatility Cutoffs).
4.  **Execution is Alpha:** Slippage and latency are primary performance metrics.
5.  **No Architecture Leakage:** Research (Layer 2) must remain strictly isolated from Production (Layer 1) during validation.
6.  **Scale Disciplined:** Gradual capital scaling only after sustained post-tax profitability in paper trading.

---

## Current Status: STAGING / PRE-PRODUCTION VALIDATION
**Immediate Objective:** 30-Day Live Paper Trading Validation (Tax-Aware).

### Current Mandates
1.  **Architecture Freeze:** STOP adding major new architectures or random indicators.
2.  **Reality Validation:** Prioritize live expectancy, Sharpe stability, and calibration over backtest accuracy.
3.  **Strict Monitoring:** Daily tracking of expectancy, drift, and regime routing accuracy.
4.  **Adaptive Retraining:** Only retrain based on structural triggers (PSI/Calibration collapse), not on a fixed schedule or local underperformance.

### Key Performance Metrics
*   **Expectancy:** Average PnL per trade after ALL costs.
*   **Sharpe Stability:** Rolling Sharpe consistency across regimes.
*   **Calibration:** Brier Score < 0.25; no overconfident probabilities.

---

## Phase 2 Roadmap: High-Frequency Microstructure & Execution Alpha
**Objective:** Transition from statistical quantitative trading to short-horizon predictive execution intelligence.

### 1. Short-Horizon Price Forecasting Engine
*   **Microprice Model:** Implement liquidity-weighted fair value estimation.
*   **Kalman Price Filter:** Real-time noise reduction and fair-price estimation.
*   **Probabilistic Range Forecasting:** Predict expected price zones (low/mid/high) with confidence intervals instead of exact points.

### 2. Orderbook Intelligence
*   **L2 Depth Analysis:** Extract bid/ask imbalance, book slope, liquidity walls, and queue pressure.
*   **VPIN & OFI:** High-frequency Volume-Synchronized Probability of Informed Trading and Order Flow Imbalance.

### 3. Execution Alpha Engine
*   **Smart Routing:** Dynamic switching between Market and Limit orders based on liquidity pressure.
*   **Spread Awareness:** Optimize execution timing to minimize spread-cross costs and slippage.

## Multi-Phase Institutional Roadmap
### Phase 1: Stabilize Everything (1–2 Weeks)
*   **Focus:** Fix all broken imports, path issues, and async bugs.
*   **Data Integrity:** Audit for leakage (especially `future_return_t1`), duplicates, and NaNs.
*   **Scope:** BTC + ETH ONLY; 5m/15m trend strategies.

### Phase 2: Realistic Market Simulation (2–4 Weeks)
*   **Crisis Simulation:** Model flash crashes, liquidity collapses, and whale dumping.
*   **Advanced Frictions:** Implement dynamic slippage `f(size, liquidity)` and tax-bleed compounding models.
*   **War-Gaming:** Stress test system survival across crash and sideways regimes.

### Phase 3: Improve Real Edge (1–3 Months)
*   **Magnitude Alpha:** Improve Expected Return Regressor calibration.
*   **Net-Edge Optimizer:** Upgrade Trade Ranking Engine with frequency controls and dynamic profit thresholds.

### Phase 4: Long Paper Trading (3–6 Months)
*   **Validation:** 24/7 run to prove sustained post-tax expectancy and stable Sharpe.
*   **Weekly Audit:** Systematic check of feature drift and probability collapse.

### Phase 5: Micro Live Capital (6–12 Months)
*   **Micro-Live:** Deployment of ₹500–₹5000 to validate real execution vs. paper.

### Phase 6: Advanced HFT Research (1–3 Years)
*   **Expansion:** Layer 2 microstructure alpha, smart routing, and multi-strategy portfolios.

---

## Technical Standards
*   **Validation:** ALWAYS use Purged Walk-Forward CV.
*   **Modeling:** Ensemble (XGB/LGBM/CB) + Expected Return Regressor + LSTM Orderflow + Meta-Labeling.
*   **Ranking:** TradeRankingEngine (Synthesizes Prob, Return, Confidence, and Fiscal Drag).
*   **Logging:** All decisions and trades must be logged to `logs/live_metrics/`.
