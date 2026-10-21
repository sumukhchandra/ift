# ALPHANSE V3 — SESSION READINESS REPORT & RUNBOOK
**Target Trading Session: Wednesday, October 14, 2026 (09:15:00 IST – 15:30:00 IST)**  
**Generated At:** Tuesday, October 13, 2026 (Post-Market Preflight)  
**Broker Integration:** Kotak Securities Neo Trade API (`UCC: 116K1`)  
**Execution Environment:** Fail-Closed Paper Execution (Physical live orders locked)

---

## 1. EXECUTIVE SUMMARY & PREFLIGHT VERDICT

| Component | Status | Verification Evidence |
| :--- | :---: | :--- |
| **Kotak Neo API Session** | 🟢 **ACTIVE** | UCC `116K1` authenticated; MPIN validated; dynamic TOTP generation via `pyotp` active. |
| **Market Feeds (Parallel)** | 🟢 **VERIFIED** | Fast parallel quote feed active across all universe instruments (`INFY`, `RELIANCE`, `BAJFINANCE`, `AXISBANK`, `TATASTEEL`, `NIFTYBEES`). |
| **Exchange Options Chain** | 🟢 **DISCOVERED** | Native `neo_client.option_chain('nse_fo', 'NIFTY')` discovered genuine live strikes (ATM 22700 CE/PE) and standard 65-unit lot size. |
| **Model Weight Provenance** | 🟢 **FROZEN** | 6 Specialist Linear models loaded from `active_model_weights.json`; 3-Tree ML Ensemble (CatBoost, LightGBM, XGBoost) loaded from `QA/models/saved_models_1m/`. |
| **Fail-Closed Inference** | 🟢 **ENFORCED** | Deceptive 50% fallbacks eliminated; returns `prediction_valid: False` and `confidence: 0.0` when candle history < 15 or model error occurs. |
| **Replay Data Isolation** | 🟢 **ISOLATED** | Oct 9 historical replay records moved to `reports/replay/`; live chart in `reports/live/` cleared and armed in standby mode. |
| **Single Daemon Process** | 🟢 **ENFORCED** | Windows `is_pid_alive` singleton lock active; duplicate process collision blocked. |
| **Statutory Accounting** | 🟢 **AUDITED** | Roundtrip cost engine models Trade Free ₹0 brokerage, official NSE exchange turnover, SEBI charges, GST, and stamp duty. |
| **Overall Readiness Verdict** | 🟢 **READY FOR WEDNESDAY, OCT 14 OPEN** | Engine armed in `STANDBY_FOR_OPEN` with countdown timer to 09:15:00 IST. |

---

## 2. PRE-SESSION VERIFICATION AUDIT TRAIL

### A. Credentials & Broker API Security
- **API Environment:** Production (`environment="prod"`).
- **Credentials Masking:** Keys and tokens loaded exclusively via environment variables (`.env`).
- **Physical Safety Lock:**
  - `LIVE_TRADING=False` (Strict fail-closed paper execution).
  - `ALLOW_REAL_ORDERS=False` (Dual-key hardware lock prevents live exchange order submission).
- **Session Auto-Refresh:** Session proactively re-authenticates every 45 minutes using dynamic TOTP generation.

### B. Strategy Mode Separation
AlphaNSE V3 strictly isolates cash equities from exchange-traded derivatives:

1. **`CASH_EQUITY` Mode:**
   - **Instruments:** INFY, RELIANCE, BAJFINANCE, AXISBANK, TATASTEEL, NIFTYBEES.
   - **Position Sizing:** Whole integer shares strictly under available cash (`₹1,500.00`).
   - **Short Selling:** Disabled by default under cash-only account rules (requires explicit `--allow-short-selling` flag).
   - **Ledger:** `reports/live/paper_trading_ledger.json`.

2. **`OPTIONS_PAPER` Mode:**
   - **Instruments:** NSE European Index Options (`NIFTY` CE / PE).
   - **Contract Lot Size:** Standard 65 units (NSE contract specification).
   - **Position Sizing:** Whole option lots. If $\text{Premium} \times 65 > \text{Available Bankroll}$ (₹1,500), the trade is **strictly rejected** with `INSUFFICIENT_CASH`.
   - **Short Selling / Option Writing:** **Strictly disabled** (`SELLING_DISABLED`). Long option buyer exposure only.
   - **Contractual Risk Cap:** Maximum loss is strictly capped at 100% of the premium paid.
   - **Ledger:** `reports/live/options_paper_ledger.json`.

---

## 3. FAIL-CLOSED INFERENCE AUDIT

In accordance with Phase 3 Section D:
- **Missing History:** If candle count $< 15$, `OneMinPredictor` returns:
  ```json
  {
    "prediction_valid": false,
    "confidence": 0.0,
    "raw_breakout_prob": 0.0,
    "signal": "HOLD",
    "direction": "UNCERTAIN",
    "error": "INSUFFICIENT_HISTORY: Only X candles available, minimum 15 required"
  }
  ```
- **Inference Failure:** If tree models or classifier fail, returns `prediction_valid: false`, `confidence: 0.0`.
- **Concurrence Gate:** `live_trader.py` checks `if not ml_out.get("prediction_valid", False): continue`, strictly preventing unbuffered or failed inferences from generating tradable signals.

---

## 4. PAPER TRADING STARTING STATE (OCTOBER 14, 2026)

| Parameter | Configured Value | Verification Status |
| :--- | :---: | :--- |
| **Starting Account Bankroll** | **₹1,500.00** | Clean starting balance; verified in `runtime_state.json` and `paper_trading_ledger.json`. |
| **Active Open Positions** | **0** | Clean flat book; 0 overnight carryover into October 14. |
| **Today's Realized P&L** | **₹0.00** | Pristine accounting baseline. |
| **Closed Trades Today** | **0** | Zero synthetic or fabricated trades. |
| **Maximum Daily Loss Cap** | **₹15.00 (1.0%)** | Circuit breaker kill switch triggers if balance drops below ₹1,485.00. |
| **Maximum Allowed Positions** | **1** | Enforces single concurrent position under ₹1,500 ceiling. |
| **Mandatory Square-Off** | **15:15:00 IST** | Hard intraday square-off sentinel liquidates any open position to 100% cash. |

---

## 5. STANDARD OPERATING PROCEDURE (SOP) FOR WEDNESDAY, OCT 14

### Step 1: Pre-Market Health Verification (08:45 – 09:05 IST)
Run connection test to ensure Kotak Neo session and credentials are fresh:
```bash
python run_live_trader.py --test-conn
```
*Expected Output:*
```
• UCC: 116K1
• Consumer Key Configured: Yes
• Mobile Number Configured: Yes
• Authentication Result: True
• Client Initialized: True
```

### Step 2: Inspect Live Model Predictions & Market Feeds (09:05 – 09:14 IST)
Verify that pre-market quote feeds and model inference pipelines are operational:
```bash
python run_live_trader.py --inspect-signals
```

### Step 3: Launch Production Trading Engine (09:14:30 IST)

**Option A — Cash Equity Intraday Mode (Recommended Default):**
```bash
python run_live_trader.py --mode CASH_EQUITY
```

**Option B — NSE CE/PE Options Paper Mode:**
```bash
python run_live_trader.py --mode OPTIONS_PAPER
```

*Expected Terminal Display:*
```
[09:14:50 IST] ⏳ [STANDBY_FOR_OPEN] Next Session: 2026-10-14 09:15:00 IST (in 00h 00m 10s). Armed & waiting...
[2026-10-14 09:15:00 IST] ─── CYCLE #1 (Market: 🟢 OPEN) ───
```

### Step 4: Real-Time Monitoring & Reporting
To monitor balance, active trades, and ledger in real time:
```bash
python view_paper_trades.py
```
To view the interactive real vs predicted price chart:
Open `reports/live/real_vs_predicted_chart.html` in any web browser.

---

## 6. INVARIANTS & SAFETY GUARANTEES

1. **Zero Fabrication:** If market data is unavailable, models fail, or economic edge is insufficient, the system records `HOLD` and executes zero trades.
2. **Whole Shares / Lots Only:** Fractional shares and fractional option contracts are strictly prohibited.
3. **No Overleveraging:** Bankroll exposure is strictly capped at ₹1,500.00.
4. **No Naked Shorting:** Cash mode requires explicit enablement for short selling; Options mode strictly forbids option writing.
5. **No Overnight Risk:** Every position is guaranteed to be squared off by 15:15:00 IST.
