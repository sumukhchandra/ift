# 🟢 AlphaNSE V3 — Session 13 Real Market Trading Operational Readiness Report

**Trading Session:** `Session 13 (Friday, October 09, 2026)`  
**Operational Status:** `STANDBY_FOR_OPEN` (Pre-Market Readiness Confirmed)  
**Broker Gateway:** 🟢 **Kotak Neo Trade API (UCC: 116K1 Authenticated)**  
**Execution Mode:** **LIVE REAL-MONEY ORDERS (Dual-Key Gates Unlocked)**  
**Brokerage Plan:** **Kotak Neo Trade Free Plan (₹0.00 Brokerage on Intraday)**  

---

## 1. Executive Summary: Transition to Real Market Execution

Per your direct authorization, the system has officially transitioned from historical replay / paper simulations to **genuine real market execution**:

1. **Dual-Key Live Authorization:**
   * `LIVE_TRADING = True` (Active in `.env`)
   * `ALLOW_REAL_ORDERS = True` (Active in `.env`)
   * Status: **UNLOCKED — Real order dispatch enabled to Kotak Neo gateway**.
2. **Broker Connectivity Verified:**
   * Gateway: Kotak Neo Trade API (`neo_api_client`)
   * UCC: `116K1` (+919398794121)
   * MPIN & Dynamic TOTP: Authenticated & Session Token Acquired
   * Available Balance / Limits: ₹1,500.00
3. **Execution Engine:**
   * Script: [`scripts/run_session13_kotak_live_trader.py`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/scripts/run_session13_kotak_live_trader.py)
   * Launcher: [`start_session13_live_trading.bat`](file:///c:/Users/sumuk/.gemini/antigravity-ide/scratch/ift/start_session13_live_trading.bat)

---

## 2. Institutional Risk Safeguards (0.3% Max Risk Rule)

All strict capital preservation rules are locked directly into the execution adapter:

| Parameter | Configuration | Enforcement Mechanism |
|---|:---:|---|
| **Allocated Capital** | **₹1,500.00** | Scaled strictly per model (Fleet total: ₹9,000.00) |
| **Max Loss Per Trade** | **₹4.50 (0.30%)** | Immediate hard market exit order dispatched to Kotak Neo |
| **Profit Target** | **+₹15.00 (+1.0%)** | Dynamic limit/market harvest order locked into cash |
| **Daily Loss Circuit Breaker** | **₹15.00 (1.0%)** | Hard kill-switch: stops all trading for the day if hit |
| **Max Concurrent Positions** | **1 Position** | Fail-closed position limit per model |
| **EOD Mandatory Square-Off** | **15:15:00 IST** | 100% Cash liquidation before 15:30 IST close |

---

## 3. Asset Universe & Kotak Neo Scrip Mappings

| Universe Symbol | Asset Name | Assigned Strategy | Kotak Neo Trading Symbol | Exchange Segment | Product Code |
|---|---|---|---|:---:|:---:|
| `INFY.NS` | Infosys | 15m Momentum Rider | `INFY-EQ` | `nse_cm` | `MIS` |
| `RELIANCE.NS` | Reliance Industries | 60m Multi-Factor Trend | `RELIANCE-EQ` | `nse_cm` | `MIS` |
| `BAJFINANCE.NS` | Bajaj Finance | High-Beta Squeeze | `BAJFINANCE-EQ` | `nse_cm` | `MIS` |
| `AXISBANK.NS` | Axis Bank | 15m Dip Buyer | `AXISBANK-EQ` | `nse_cm` | `MIS` |
| `TATACAP.NS` | Tata Capital | Shelf Defense | `TATACAP-EQ` | `nse_cm` | `MIS` |
| `^NSEI` | NIFTY 50 Index | SMC Straddle / Trend | `NIFTYBEES-EQ` | `nse_cm` | `MIS` |

---

## 4. Operational Schedule for Today (Friday, Oct 09, 2026)

* **01:30 – 09:14 IST:** `STANDBY_FOR_OPEN` (Daemon armed, monitoring countdown clock).
* **09:15:00 IST:** **NSE Opening Bell** — Live data feed connects; technical indicators initiate.
* **09:20 – 15:15 IST:** Continuous autonomous trade execution; orders routed directly to Kotak Neo account `116K1`.
* **15:15:00 IST:** Mandatory intraday square-off sentinel liquidates any open position.
* **15:30:00 IST:** Market close and final P&L reconciliation.
