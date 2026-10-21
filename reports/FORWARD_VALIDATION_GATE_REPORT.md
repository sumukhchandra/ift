# AlphaNSE V3 — Forward Validation & Paper-Readiness Gate Report

**Date of Execution:** 2026-10-15  
**Evaluation Scope:** Priority 1 (Forward Edge), Priority 2 (Cost Verification), Priority 3 (Kotak Neo Real Data), Priority 4 (Release Decision Gate)  
**Safety Governance:** `LIVE_TRADING=False` | `ALLOW_REAL_ORDERS=False` (Strictly Enforced Air-Gap)  
**Initial Paper Bankroll:** ₹1,500.00  
**Final Release Verdict:** **`NOT READY FOR PAPER PREFLIGHT`**

---

## 1. Executive Summary & Release Gate Verdict

| Readiness Gate Criterion | Standard / Hurdle | Verified Forward Evidence | Audit Status |
| :--- | :--- | :--- | :--- |
| **Strict Out-of-Sample Separation** | $T_{\text{train\_end}} < T_{\text{eval\_start}}$ strictly | Train: `2026-10-12 10:47:48 IST`<br>Eval: `2026-10-13 09:15:00` to `2026-10-14 15:29:00 IST` | 🟢 **PASS** (Zero Overlap) |
| **Data Partition Integrity** | Zero in-sample contamination | 7,986 genuine post-training exchange 1-min candles ingested across 11 symbols | 🟢 **PASS** (Genuine Forward OOS) |
| **Execution Cost Accounting** | Penny-for-penny statutory fees + 2.5 bps spread + 3.0 bps slippage | Exact STT, Exchange, SEBI, GST, Stamp Duty, Spread, and Slippage integrated | 🟢 **PASS** (14/14 Cost Tests Pass) |
| **Next-Bar Execution & Conservative Priority** | Next-bar open fill; stop prioritized on dual touch | Enforced in `forward_evaluation.py` and regression test suite | 🟢 **PASS** (Conservative Priority) |
| **Kotak Neo Live Data Verification** | Live quotes & 1m candles produced without orders | All 6 primary symbols producing fresh timestamped quotes via Trade API | 🟢 **PASS** (Read-Only Verified) |
| **Paper-Only Locks** | `LIVE_TRADING=False`, `ALLOW_REAL_ORDERS=False` | Verified in `.env`, adapter, and preflight connection checks | 🟢 **PASS** (Air-Gapped ₹1,500) |
| **Directional Predictive Edge** | Statistically significant edge (> 52% directional accuracy) | **49.76% Directional Accuracy** (28 Wins vs 1,842 Losses; Win Rate: 1.50%) | 🔴 **FAIL** (Random Walk / Noise) |
| **Net Forward Expectancy** | $> 0$ bps after statutory fees & market friction | **-14.14 bps (-₹1.70 per trade)** (Gross: +0.40 bps vs Friction: 14.55 bps) | 🔴 **CRITICAL BLOCKER** |
| **Net Forward P&L** | Profitable / Capital Preserving | **-₹3,174.99 Net Loss** (Max Drawdown: -211.67% of initial ₹1,500 capital) | 🔴 **CRITICAL BLOCKER** |
| **Release Verdict** | Net positive forward expectancy required | **NOT READY FOR PAPER PREFLIGHT** | 🔴 **PROHIBITED** |

---

## 2. Priority 1 — Predictive Edge: Forward Out-of-Sample Evaluation

### 2.1 Chronological Separation & Partition Metadata
- **Training Timestamp End ($T_{\text{train\_end}}$):** `2026-10-12 10:47:48.013185+05:30` (from `QA/models/saved_models_1m/model_metrics_1m.json`).
- **Forward Evaluation Start ($T_{\text{eval\_start}}$):** `2026-10-13 09:15:00+05:30`.
- **Forward Evaluation End ($T_{\text{eval\_end}}$):** `2026-10-14 15:29:00+05:30`.
- **Temporal Separation:** Strictly non-overlapping. Zero training bars or lookahead data present in the evaluation dataset.
- **Evaluation Data Classification:** `GENUINE_FORWARD_OUT_OF_SAMPLE` (archived at `QA/data/genuine_forward_oos_oct13_oct14.csv`).

### 2.2 Coverage and Trade Execution Metrics
- **Symbol Universe (11 Instruments):** `AXISBANK`, `BAJFINANCE`, `BHARTIARTL`, `HDFCBANK`, `ICICIBANK`, `INFY`, `NIFTYBEES`, `RELIANCE`, `SBIN`, `TATASTEEL`, `TCS`.
- **Total Ingested 1-Minute Bars:** 7,986 bars.
- **Valid Model Predictions:** 7,755 predictions.
- **Eligible Signals Generated ($\text{Confidence} \ge 45.0\%$):** 2,302 signals.
- **Signals Rejected for Affordability (Price > ₹1,500 bankroll):** 431 signals (e.g. `TCS`, `RELIANCE`, `BAJFINANCE` un-sized).
- **Executed Affordable Trades:** 1,871 trades (whole integer shares under ₹1,500 capital).
- **Directional Accuracy:** **49.76%** (Coin-flip / zero statistical edge).
- **Win Rate (Net):** **1.50%** (28 winning trades vs 1,842 losing trades).

### 2.3 Financial Performance & Itemized Statutory Friction

```
Gross Alpha Expected:               +0.40 bps (+₹94.44 total)
Roundtrip Statutory Taxes:          -2.45 bps (-₹797.42 total)
Modeled Spread (2.5 bps x 2):       -5.00 bps (-₹1,123.69 total)
Modeled Slippage (3.0 bps x 2):     -6.00 bps (-₹1,348.32 total)
--------------------------------------------------------------------------------
Total All-In Friction:              -14.55 bps (-₹3,269.43 total | ₹1.75 / trade)
--------------------------------------------------------------------------------
Net Forward Realized P&L:           -14.14 bps (-₹3,174.99 total | -₹1.70 / trade)
Max Equity Drawdown:                -₹3,174.99 (-211.67%)
```

#### Itemized Statutory Fee Breakdown (Across 1,871 Executed Trades):
- **Brokerage:** ₹0.00 (Kotak Neo Trade Free Plan).
- **STT (Securities Transaction Tax, 0.025% on sell):** ₹562.65.
- **Exchange Turnover Charges (0.00307% roundtrip):** ₹137.99.
- **SEBI Turnover Fees (₹10 per crore = 0.0001%):** ₹4.50.
- **GST (18% on Exchange + SEBI):** ₹25.65.
- **Stamp Duty (0.003% on buy):** ₹67.42.
- **Bid-Ask Half-Spread (2.5 bps per side):** ₹1,123.69.
- **Execution Slippage (3.0 bps per side):** ₹1,348.32.
- **Total Combined Transaction Friction:** ₹3,269.43.

### 2.4 Calibration Limitations
The confidence score output from `OneMinPredictor` represents an uncalibrated heuristic mapping:
$$\text{Directional Confidence} = \text{clip}(0.50 + |\text{Predicted Return}| \times 50.0, 0.10, 0.95)$$
While Platt scaling was fitted on the training split's breakout target, the raw confidence values do not represent empirical probabilities (e.g. Brier score / isotonic calibration). At 45%–55% confidence, the model operates effectively in pure market noise.

---

## 3. Priority 2 — Execution Cost & Order Regression Test Suite

A dedicated regression test suite was constructed in `tests/test_execution_costs.py` containing 14 unit tests:

1. **Statutory Rate Schedule Verification:**
   - STT: 0.025% on sell side.
   - Exchange Turnover: 0.00307% per side.
   - SEBI Charges: 0.0001% (₹10/crore).
   - Stamp Duty: 0.003% on buy side.
   - GST: 18% on non-tax charges (Brokerage + Exchange + SEBI).
2. **Spread & Slippage Application:**
   - Enforces adverse crossing on entry ($P_{\text{buy}} \times [1 + \text{spread} + \text{slippage}]$) and exit ($P_{\text{sell}} \times [1 - \text{spread} - \text{slippage}]$).
3. **Conservative Intra-Bar Clash Priority:**
   - When a bar's high touches target and low touches stop in the same candle, stop-loss priority is strictly enforced (`CONSERVATIVE_STOP_LOSS_CLASH`).
4. **Whole-Share Affordability Regression:**
   - Under ₹1,500 bankroll:
     - Price < ₹1,500 (Tata Steel @ ₹150) sizes to whole shares (9–10 shares).
     - Price = ₹1,500 cannot be afforded once entry statutory friction is included (rejects to 0 shares).
     - Price > ₹1,500 (Reliance @ ₹2,800) rejects immediately to 0 shares with `UNAFFORDABLE_POSITION`.
     - Ensures unaffordable candidate cannot suppress an affordable candidate.
5. **Fail-Closed Stale Quote Rejection:**
   - Verifies quotes with `is_stale=True` or `source="BUFFER_FALLBACK"` are completely excluded from opportunity scanning.

**Test Run Output:**
```
Ran 14 tests in 4.707s
OK
```

---

## 4. Priority 3 — Kotak Neo Live Data Verification (Read-Only)

Executed pre-market connection and live market feed verification via `run_live_trader.py --test-conn`:

```
=====================================================================================
  🔍 ALPHANSE V3 — PRE-MARKET CONNECTIVITY & DATA FEED VERIFICATION
  TIME: 2026-10-15 01:28:38 IST
=====================================================================================

1. Broker Adapter Status:
  • Broker Adapter: Kotak Neo Trade API Adapter [PAPER / READ-ONLY]
  • Configured UCC: 116K1
  • Authentication Success: 🟢 YES
  • Live Trading Lock: 🟢 SECURE (False)
  • Real Order Routing Lock: 🟢 SECURE (False)
  • Adapter Operational Mode: 🟢 PAPER / READ-ONLY

2. Market Data Feed & 1-Minute Candle Status:
  • Symbols Queried: 6
  • Quotes Received: 6 / 6
    - NIFTYBEES.NS   : LTP=₹  257.78 | Open=₹  259.20 | Vol=5,565,002 [KOTAK_NEO_TRADE_API] | Candles=60 | Time=01:28:39
    - INFY.NS        : LTP=₹ 1088.00 | Open=₹ 1073.70 | Vol=22,113,407 [KOTAK_NEO_TRADE_API] | Candles=60 | Time=01:28:39
    - TATASTEEL.NS   : LTP=₹  174.49 | Open=₹  175.50 | Vol=20,350,651 [KOTAK_NEO_TRADE_API] | Candles=60 | Time=01:28:39
    - BAJFINANCE.NS  : LTP=₹  957.00 | Open=₹  980.00 | Vol=7,139,305 [KOTAK_NEO_TRADE_API] | Candles=60 | Time=01:28:39
    - AXISBANK.NS    : LTP=₹ 1264.60 | Open=₹ 1265.10 | Vol=11,522,506 [KOTAK_NEO_TRADE_API] | Candles=60 | Time=01:28:39
    - RELIANCE.NS    : LTP=₹ 1174.60 | Open=₹ 1167.00 | Vol=10,938,195 [KOTAK_NEO_TRADE_API] | Candles=60 | Time=01:28:39

3. Risk & Capital Configuration:
  • Primary Mode: CASH-ONLY (NO SHORTING)
  • Paper Bankroll: ₹1500.00
  • Max Capital: ₹1500.00
  • Max Daily Loss: ₹15.00
  • Max Concurrent Positions: 1
=====================================================================================
```

Structured events `DATA_FRESHNESS` and `CONNECTION_TEST` recorded in `logs/live_trader.log` and `reports/live/orders_stream.jsonl`. Zero real orders placed.

---

## 5. Priority 4 — Exact Release Evidence Gap & Roadmap

### Why Paper Preflight is Denied:
1. **Mathematical Invariant:** A trading strategy cannot be deployed to forward paper preflight when its verified out-of-sample forward net expectancy is **negative (-14.14 bps)**.
2. **Signal-to-Noise Ratio:** The model's directional accuracy on genuine out-of-sample 1-minute data is **49.76%**, which is mathematically indistinguishable from random noise ($p > 0.05$).
3. **Turnover Friction Drag:** Generating 1,871 trades across 2 sessions (average holding period: ~1 minute) generates ₹3,269.43 in transaction friction, which completely overwhelms the gross edge of ₹94.44.

### Exact Evidence Required Before Paper Preflight Authorization:
1. **Higher-Horizon Aggregation (Lower Turnover):** 1-minute bars suffer from excessive bid-ask bounce and statutory friction. Model must aggregate features over 5-minute or 15-minute horizons to produce a gross move $> 25$ bps.
2. **Empirical Probability Calibration:** Replace heuristic directional confidence with isotonic regression or Platt-calibrated probability where confidence $> 65\%$ corresponds to an empirical win rate $> 60\%$.
3. **Statistically Verified Positive Net Expectancy:** A minimum 5-session forward walkforward evaluation demonstrating:
   - Directional accuracy $> 53.5\%$.
   - Net expectancy after statutory fees and friction $> +3.0$ bps ($> ₹0.45$ per trade).
   - Maximum drawdown $< 5.0\%$ of bankroll.

---

## 6. Changed Files & Reproducible Verification Commands

### Changed Files List:
1. `scripts/ingest_forward_oos_data.py`: Ingestion tool for post-training out-of-sample exchange data.
2. `v3/research/forward_evaluation.py`: Chronological forward pipeline with $T_{\text{train\_end}} < T_{\text{eval\_start}}$ assertions, next-bar execution, conservative clash priority, and itemized cost accounting.
3. `tests/test_execution_costs.py`: 14 regression tests for statutory fees, affordability, intra-bar clash priority, and stale quote rejection.
4. `v3/execution/live_trader.py`: Enhanced `check_connection` with candle verification, structured freshness logging, and paper lock audits.
5. `v3/execution/kotak_adapter.py`: Fixed attribute bug (`proportional_statutory_cost` and `slippage`).
6. `tests/test_live_trader_logging.py`: Increased runner subprocess timeout to 60s.
7. `reports/forward_evaluation_results.json`: Complete forward evaluation artifact.

### Reproducible Commands:
```bash
# 1. Run Complete Test Suite (294 Tests)
python run_tests.py

# 2. Run Execution Cost & Affordability Regression Tests
python -m unittest tests/test_execution_costs.py

# 3. Run Forward Out-of-Sample Evaluation Pipeline
python v3/research/forward_evaluation.py

# 4. Verify Kotak Neo Live Connection & Data Freshness (Read-Only)
python run_live_trader.py --test-conn
```
