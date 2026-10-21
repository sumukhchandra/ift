# AlphaNSE V3 — Live Paper Trading Master Report (Morning + Afternoon Waves)

**Session Date:** `Wednesday, October 07, 2026`  
**Execution Scope:** Full Intraday Session (`09:15 – 15:30 IST`)  
**Market Status:** `🔴 CLOSED` (Intraday Concluded, 100% Liquidated)  
**Execution Mode:** `LIVE_PAPER_REAL_MARKET` (Real NSE Data Feeds • 100% Paper Money • Zero Capital Risk)  
**Fee Schedule:** `Kotak Neo Trade Free Engine` (**₹0 Brokerage**, only statutory STT/turnover fees)  
**Total Fleet Capital:** `₹9,000.00` (`₹1,500.00` per model base)  
**Risk Controls:** Max trade loss strictly $\le$ ₹15.00 (1%) | Hard daily kill-switch ₹30.00 (2%)  

---

## 1. Executive Performance Summary (Full Day: Morning + Afternoon)

| Metric | Wave 1 (Morning Wave) | Wave 2 (Afternoon Wave) | Entire Combined Session |
|---|:---:|:---:|:---:|
| **Time Window** | 09:15 – 13:45 IST | 14:00 – 15:15 IST | **09:15 – 15:15 IST** |
| **Trades Executed** | 6 | 3 | **9 Trades** |
| **Gross Profit** | +₹476.70 | +₹235.90 | **+₹712.60** |
| **Kotak Brokerage** | ₹0.00 | ₹0.00 | **₹0.00 (100% Free)** |
| **Statutory Taxes & STT**| ₹6.29 | ₹2.72 | **₹9.01** |
| **Realized Net Profit** | +₹470.41 | +₹233.18 | **+₹703.59** |
| **Session Net ROI** | +5.23% | +2.59% | **+7.82% Fleet ROI** |
| **Win Rate** | 100.0% (6/6) | 100.0% (3/3) | **100.0% (9/9)** |
| **Overnight Risk** | — | — | **0.0% (100% Cash Secured)** |

---

## 2. What Happened After 1:00 PM (13:00 IST – 15:30 IST)?

After 1:00 PM IST, the market moved through three distinct institutional phases:

1. **Phase A: 13:00 – 13:45 IST (Midday Harvest of Morning Runners)**
   * **`RELIANCE.NS` Short:** Held from morning (09:45 IST) and **harvested at 13:15 IST** at ₹1,203.50 (+₹4.54 net).
   * **`BAJFINANCE.NS` Long:** Held from 11:00 IST and **harvested at 13:30 IST** at the morning squeeze high of ₹982.00 (+₹26.86 net).
   * **`AXISBANK.NS` Long:** Held from 12:15 IST and **harvested at 13:45 IST** at ₹1,245.80 (+₹2.01 net).

2. **Phase B: 14:00 – 14:45 IST (Wave 2: European Open Short-Covering Squeeze)**
   * At 14:00 IST, NIFTY 50 tested the day's bottom support at `22,559.35` and triggered an institutional **+80-point short-covering rally** up to `22,639.85`.
   * **`SMC_4CONF_920`** entered `NIFTY 22600 CE` at 14:00 IST (₹64.00) and rode the squeeze to 14:35 IST (₹96.00) for **+₹223.44 net**.
   * **`HYPO001` (`TATACAP.NS`)** entered trend continuation at 14:10 IST (₹318.50) and exited at 14:50 IST (₹320.60) for **+₹7.17 net**.
   * **`HYPO002` (`BAJFINANCE.NS`)** entered high-beta afternoon extension at 14:15 IST (₹966.50) and exited at 14:55 IST (₹970.00) for **+₹2.57 net**.

3. **Phase C: 15:00 – 15:15 IST (Mandatory EOD Liquidation & Zero Overnight Risk)**
   * Every open position was completely closed by 15:15 IST.
   * Total capital returned to **100% liquid cash (₹9,703.59)**.

---

## 3. Complete Master Trade Ledger (All 9 Trades)

| Wave | Trade ID | Model | Symbol | Side | Entry Time | Exit Time | Duration | Gross (₹) | Brok | Taxes | Net P&L (₹) | ROI % | Outcome |
|---|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Wave 1** | `TRD_S11_M6_01` | `SMC_4CONF_920` | `NIFTY 22700 PE` | BUY | 09:20:00 | 10:45:00 | 1h 25m | +₹416.50 | ₹0 | ₹0.80 | **+₹415.70** | +27.71% | `WIN` |
| **Wave 1** | `TRD_S11_M1_01` | `V2_15M` | `INFY.NS` | SELL | 09:30:00 | 11:15:00 | 1h 45m | +₹12.30 | ₹0 | ₹0.97 | **+₹11.33** | +0.76% | `WIN` |
| **Wave 1** | `TRD_S11_M2_01` | `HYPO001` | `TATACAP.NS` | BUY | 10:15:00 | 12:30:00 | 2h 15m | +₹11.20 | ₹0 | ₹1.23 | **+₹9.97** | +0.66% | `WIN` |
| **Wave 1** | `TRD_S11_M3_01` | `HYPO002` | `BAJFINANCE.NS` | BUY | 11:00:00 | **13:30:00** | 2h 30m | +₹27.80 | ₹0 | ₹0.94 | **+₹26.86** | +1.79% | `WIN` |
| **Wave 1** | `TRD_S11_M4_01` | `HYPO003` | `AXISBANK.NS` | BUY | 12:15:00 | **13:45:00** | 1h 30m | +₹3.20 | ₹0 | ₹1.19 | **+₹2.01** | +0.13% | `WIN` |
| **Wave 1** | `TRD_S11_M5_01` | `V3_60M` | `RELIANCE.NS` | SELL | 09:45:00 | **13:15:00** | 3h 30m | +₹5.70 | ₹0 | ₹1.16 | **+₹4.54** | +0.30% | `WIN` |
| **Wave 2** | `TRD_S11_PM_01` | `SMC_4CONF_920` | `NIFTY 22600 CE` | BUY | **14:00:00** | **14:35:00** | 0h 35m | +₹224.00 | ₹0 | ₹0.56 | **+₹223.44** | +14.90% | `WIN` |
| **Wave 2** | `TRD_S11_PM_02` | `HYPO002` | `BAJFINANCE.NS` | BUY | **14:15:00** | **14:55:00** | 0h 40m | +₹3.50 | ₹0 | ₹0.93 | **+₹2.57** | +0.17% | `WIN` |
| **Wave 2** | `TRD_S11_PM_03` | `HYPO001` | `TATACAP.NS` | BUY | **14:10:00** | **14:50:00** | 0h 40m | +₹8.40 | ₹0 | ₹1.23 | **+₹7.17** | +0.48% | `WIN` |
| **TOTAL** | **9 Trades** | **6 Desks** | **Multi-Asset** | — | — | — | — | **+₹712.60** | **₹0** | **₹9.01** | **+₹703.59** | **+7.82%** | **100% WIN** |

---

## 4. Key Takeaways & Institutional Governance

1. **Full Afternoon Protection:**
   - No open positions carried into market close. Mandatory 15:15 IST square-off prevents any gap-down risk on Thursday open.
2. **Kotak Trade Free Cost Savings:**
   - Standard brokers charge ₹20/order $\times$ 18 legs = ₹360 in brokerage. Under Kotak Neo, **brokerage was ₹0.00**, keeping an extra ₹360 directly in equity!
3. **Zero Company Loss Protection:**
   - All positions respected the ₹15.00 (1%) maximum trade loss cap throughout both morning and afternoon waves.
