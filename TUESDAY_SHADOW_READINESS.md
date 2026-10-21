# ALPHANSE V3 — TUESDAY SHADOW SESSION READINESS GATE & DATA FRESHNESS AUDIT
**Target Session:** Tuesday, 20 October 2026 (09:15:00 to 15:30:00 IST)  
**Pre-Session Audit Timestamp:** 2026-10-19T18:55:00 IST  
**Auditor:** Quantitative Researcher, ML Validation Specialist & Independent Forensic Auditor  
**System Mode:** **STRICT SHADOW MODE ONLY** (`LIVE_TRADING=False`, `ALLOW_REAL_ORDERS=False`)  
**Operating Bankroll:** ₹1,500.00 Paper Cash Simulation (Max 1 Open Position, ₹30.00 Daily Loss Cap)  
**Automated Test Suite Result:** **353 / 353 PASSED (100.0%)** (Exit Code 0, Duration: 84.632s)

---

## 1. Executive Gate Status & Subsystem Verdicts

| Subsystem Dimension | Verdict | Evidentiary Basis | Operational Mandate |
| :--- | :---: | :--- | :--- |
| **1. Software Test Suite** | **PASS** | 353 / 353 unit and regression tests passing with exit code 0 across 62 test modules. Suite execution duration: 84.632s. | Clean execution baseline established. Zero regressions. |
| **2. Broker API Authentication** | **PASS** | Kotak Neo Trade API session successfully authenticated (UCC: `116K1`) via TOTP / session handshake. | API communication verified. |
| **3. Market Data Freshness (Current Clock)** | **REJECTED (EXPECTED / SAFE)** | Regular NSE cash market closed at 15:30 IST. Quotes returned during evening tests (18:07–18:54 IST) have exchange timestamps (`lstup_time`) of `15:58:35` to `15:59:56 IST` with quote age ~140–175 minutes. Correctly classified as `MARKET_CLOSED_EOD_LTP` (`is_stale=True`). | **Rejected from candle aggregation.** No live inference permitted outside 09:15–15:30 IST. |
| **4. Live Data Ingestion & Candle Construction** | **PASS** | `OneMinuteCandleAggregator` strictly consumes non-stale session observations. `live_trader.py:1632` sets `include_forming=False`, ensuring production inference exclusively consumes sealed 1m bars. Sub-minute buffers (<45s) fail closed. | No timeframe sampling mismatch. |
| **5. Runtime Process Lifecycle & Mutex** | **PASS** | Background process spawned (PID 27812), remained alive through 46 standby cycles, logged heartbeats, prevented duplicate instances, and stopped cleanly on `python check_status.py --stop`. | Clean single-instance background daemon verified. |
| **6. Pre-Trade Time Gate & Risk Limits** | **PASS** | `KotakLiveBrokerAdapter` enforces `enforce_time_gate=True` unconditionally in production. Hard 15:15 IST square-off, max 1 open position, ₹30.00 daily loss cap enforced. | Real money orders physically blocked. Capital safe. |
| **7. Model Predictive Alpha & Edge** | **FAIL (NO REAL CAPITAL)** | Canonical out-of-sample evaluation ($N=8,262$) demonstrates negative rank IC ($-0.0238$) and negative net expectancy ($-15.01\text{ bps}$) after realistic friction. Model fails all 5 promotion gates. | **STRICT SHADOW MODE ONLY. Real-money trading prohibited.** |

> # **FINAL OPERATIONAL VERDICT: GO — SHADOW OBSERVATION ONLY**
> # **MODEL PROMOTION VERDICT: SHADOW ONLY — MODEL EDGE NOT ESTABLISHED**

---

## 2. Forensic Market Data Freshness Audit: Post-Market vs Live Data

### Critical Distinction: Authentication Success vs Data Freshness
A successful broker connection test conducted after market hours (e.g. 18:07–18:54 IST) confirms API credentials and network routing, but **does not prove market data freshness**. 

Forensic inspection of the raw quote payloads returned by the Kotak Neo Trade API (`self.neo_client.quotes`) revealed:
1. Kotak Neo transmits the exchange timestamp in the field `lstup_time` (Unix epoch seconds string).
2. The returned `lstup_time` values across all 6 symbols were `1792405715` to `1792405796`, corresponding to **15:58:35 to 15:59:56 IST** (the EOD post-market closing run on Monday, 19 October 2026).
3. The previous implementation fell back to `now_ts` (`resp_time.astimezone(IST).strftime("%H:%M:%S")`), which improperly stamped post-market EOD quotes with the local computer clock time.
4. **Remediation Completed:** `v3/execution/kotak_adapter.py` now parses `lstup_time`, calculates the exact `quote_age_seconds`, validates market hours (`09:15 <= now <= 15:30 IST`), and stamps quotes with `validation_status = "MARKET_CLOSED_EOD_LTP"` and `is_stale = True`. Downstream, `live_trader.py` and `candle_aggregator.py` reject stale quotes from candle formation.

### Raw Capture Records Audit (`reports/live/market_data_raw_capture.jsonl`)

The table below reflects contemporaneous capture records with genuine broker timestamps, measured latencies, quote ages, and SHA-256 payload hashes:

| Line | Symbol | Request Timestamp (IST) | Response Timestamp (IST) | Exchange Timestamp (IST) | Quote Age | Nature / Type | Status | Payload SHA-256 Hash |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 49 | `NIFTYBEES.NS` | 2026-10-19 18:37:15.828 | 2026-10-19 18:37:16.195 | 2026-10-19 15:59:52 | 9,444.2s (~157m) | EOD_LAST_TRADED_PRICE | REJECTED (STALE) | `2fd1577c0478ce14...` |
| 50 | `INFY.NS` | 2026-10-19 18:37:15.828 | 2026-10-19 18:37:16.195 | 2026-10-19 15:59:36 | 9,460.2s (~158m) | EOD_LAST_TRADED_PRICE | REJECTED (STALE) | `5c30472cbf886028...` |
| 51 | `TATASTEEL.NS` | 2026-10-19 18:37:15.828 | 2026-10-19 18:37:16.195 | 2026-10-19 15:58:35 | 9,521.2s (~159m) | EOD_LAST_TRADED_PRICE | REJECTED (STALE) | `47eb48f441fd4b95...` |
| 52 | `BAJFINANCE.NS` | 2026-10-19 18:37:15.828 | 2026-10-19 18:37:16.195 | 2026-10-19 15:59:54 | 9,442.2s (~157m) | EOD_LAST_TRADED_PRICE | REJECTED (STALE) | `9125f386bf2a0726...` |
| 53 | `AXISBANK.NS` | 2026-10-19 18:37:15.828 | 2026-10-19 18:37:16.195 | 2026-10-19 15:59:01 | 9,495.2s (~158m) | EOD_LAST_TRADED_PRICE | REJECTED (STALE) | `4668b912a43cef3b...` |
| 54 | `RELIANCE.NS` | 2026-10-19 18:37:15.828 | 2026-10-19 18:37:16.195 | 2026-10-19 15:59:56 | 9,440.2s (~157m) | EOD_LAST_TRADED_PRICE | REJECTED (STALE) | `945ed10b5288def8...` |
| 55 | `NIFTYBEES.NS` | 2026-10-19 18:54:36.182 | 2026-10-19 18:54:36.942 | 2026-10-19 15:59:52 | 10,484.9s (~175m) | EOD_LAST_TRADED_PRICE | REJECTED (STALE) | `532eee2642087023...` |
| 56 | `INFY.NS` | 2026-10-19 18:54:36.182 | 2026-10-19 18:54:36.942 | 2026-10-19 15:59:36 | 10,500.9s (~175m) | EOD_LAST_TRADED_PRICE | REJECTED (STALE) | `82dc0181f8d1e665...` |
| 57 | `TATASTEEL.NS` | 2026-10-19 18:54:36.182 | 2026-10-19 18:54:36.942 | 2026-10-19 15:58:35 | 10,561.9s (~176m) | EOD_LAST_TRADED_PRICE | REJECTED (STALE) | `1c97fd3a32df87f6...` |
| 58 | `BAJFINANCE.NS` | 2026-10-19 18:54:36.182 | 2026-10-19 18:54:36.942 | 2026-10-19 15:59:54 | 10,482.9s (~175m) | EOD_LAST_TRADED_PRICE | REJECTED (STALE) | `7525710a6ae3844e...` |
| 59 | `AXISBANK.NS` | 2026-10-19 18:54:36.182 | 2026-10-19 18:54:36.942 | 2026-10-19 15:59:01 | 10,535.9s (~176m) | EOD_LAST_TRADED_PRICE | REJECTED (STALE) | `ddf13919249818ee...` |
| 60 | `RELIANCE.NS` | 2026-10-19 18:54:36.182 | 2026-10-19 18:54:36.942 | 2026-10-19 15:59:56 | 10,480.9s (~175m) | EOD_LAST_TRADED_PRICE | REJECTED (STALE) | `97061823151b848e...` |

---

## 3. Runtime Daemon Lifecycle & Mutex Verification Evidence

Command executed to test live daemon lifecycle:
```powershell
python run_live_trader.py --mode CASH_EQUITY
```
- **Execution Timestamp:** `2026-10-19 18:37:14 IST`
- **Spawned OS PID:** `27812`
- **Execution Mode:** `CASH_EQUITY` (`shadow_mode=True`)
- **Lifecycle State:** `STANDBY_FOR_OPEN`
- **Target Open Time:** `Tuesday, Oct 20 at 09:15:00 IST` (Countdown active)
- **Heartbeat Status:** Verified healthy across Cycles #1 through #46 (written to `logs/live_trader.log` and `reports/live/runtime_state.json`).
- **Network Resilience:** Daemon survived transient Wi-Fi re-route at 18:41:53 IST, safely held state, re-authenticated with Kotak Neo at 18:42:08 IST, and resumed standby loop without dropping state.
- **Singleton Lock:** Executing `python launch_background.py` while PID 27812 was active resulted in immediate fail-closed termination:
  `❌ [BLOCKED] Another AlphaNSE Live Trader instance is already running! (Existing PID: 27812)`
- **Graceful Shutdown:** Executing `python check_status.py --stop` cleanly sent `SIGTERM`, exited the loop, cleared PID, and restored status to `NOT RUNNING`.

---

## 4. Tuesday Market Session Verification Rules (09:15:00 to 15:30:00 IST)

During the regular session on Tuesday, 20 October 2026, the engine will enforce the following invariant verification gates:

1. **Exchange Timestamp Plausibility:**
   - Every incoming tick must carry an exchange timestamp matching `2026-10-20 HH:MM:SS`.
   - $\text{Quote Age} = t_{\text{response}} - t_{\text{exchange}}$. Any observation with $\text{Quote Age} > 5.0\text{s}$ is marked `is_stale=True` and rejected.
   - Future timestamps with drift $> 2.0\text{s}$ trigger `CORRUPTED_FUTURE_TIMESTAMP` rejection.
2. **Candle Aggregator Invariant:**
   - Quotes flow into `OneMinuteCandleAggregator.process_quote(sym, q)`.
   - Sub-minute ticks form intra-minute bars; rollover at $:00$ seconds seals completed bars.
   - Buffer inference consumes strictly `include_forming=False`. Incomplete bars are segregated.
   - Any buffer with $\Delta t < 45\text{s}$ fails closed via `validate_buffer_timeframe`.
3. **Observation-Only Mandate:**
   - Because canonical out-of-sample edge is negative ($-15.01\text{ bps}$ net), thresholds are **never loosened**.
   - Zero trades and ₹0.00 P&L are valid and expected. No synthetic orders will be forced.
4. **Paper Capital Boundaries:**
   - Starting balance: ₹1,500.00.
   - Max concurrent positions: 1.
   - Hard daily loss limit: ₹30.00 (circuit breaker triggers at equity $\le ₹1,470.00$).
   - Mandatory EOD square-off: 15:15:00 IST.

---

## 5. Pre-Market GO / NO-GO Decision Matrix

| Gate Dimension | Gate Criteria | Audit Finding | Verdict |
| :--- | :--- | :--- | :---: |
| **G1: Broker Authentication** | Kotak Neo API handshake valid with active session | Authenticated UCC `116K1` on REST quotes endpoint. | **GO** |
| **G2: Read-Only Safety Locks** | `LIVE_TRADING=False` and `ALLOW_REAL_ORDERS=False` hard locked | Dual-key flags confirmed `False` in `.env`, memory, and adapter. | **GO** |
| **G3: Data Freshness Gate** | Post-market quotes rejected; live quotes required during session | EOD quotes properly marked `is_stale=True`; live session gate active. | **GO** |
| **G4: Candle Aggregation Integrity** | Completed 1m bars only; no timeframe mismatch | `OneMinuteCandleAggregator` enforces sealed bars; 15/15 tests pass. | **GO** |
| **G5: Runtime Isolation** | Singleton daemon; clean PID tracking; no orphans | Verified background daemon lifecycle; PID clean; mutex verified. | **GO** |
| **G6: Risk Limits & EOD Square-Off** | ₹1,500 bankroll; ₹30 loss cap; 15:15 cutoff | Adapter enforces risk floor and 15:15 cutoff unconditionally. | **GO** |
| **G7: Model Predictive Edge** | Net positive expectancy after realistic statutory friction | **FAILED:** Net expectancy is **-15.01 bps**. Fails all 5 gates. | **NO-GO FOR REAL MONEY** |

### Authoritative Operational Mandate
AlphaNSE V3 is cleared for **SHADOW RUN ONLY** for the Tuesday, 20 October 2026 session. Real money trading remains **STRICTLY BLOCKED**.
