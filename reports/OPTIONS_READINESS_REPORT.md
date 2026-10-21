# ALPHANSE V3 — NSE CE/PE OPTIONS INTELLIGENCE READINESS REPORT (PHASE 4)

**Evaluation Date:** Tuesday, October 13, 2026 (Post-Market)  
**Target Market Session:** Wednesday, October 14, 2026  
**Derivatives Market:** National Stock Exchange of India (NSE F&O)  
**Broker Integration:** Kotak Neo Trade API (Native `neo_client.option_chain` & `expiries`)

---

## 1. Verified Live Option Chain Discovery (Preflight Test Evidence)

During preflight verification, the authenticated Kotak Neo Trade API (`UCC: 116K1`) was queried using its official SDK methods:

### Exchange Contract Query
- **Command:** `neo_client.option_chain('nse_fo', 'NIFTY', expiry='2026-10-19')`
- **Underlying Spot Observed:** NIFTY 50 Spot = **₹22,721.95** (LTP)
- **Active Market Lot:** **65 units**
- **Verified Active Strikes & Live Quotes:**

| Contract Symbol | Type | Strike | Moneyness | LTP (₹) | Lot Size | Min Capital Required (₹) | Volume (Contracts) | Open Interest |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `NIFTY26O1922700CE` | **CE** | 22700 | **ATM** | ₹229.90 | 65 | ₹14,943.50 | 32,299,670 | 3,928,015 |
| `NIFTY26O1922750CE` | **CE** | 22750 | **OTM** | ₹193.60 | 65 | ₹12,584.00 | 11,714,885 | 949,130 |
| `NIFTY26O1922800CE` | **CE** | 22800 | **OTM** | ₹163.70 | 65 | ₹10,640.50 | 27,338,350 | 3,719,885 |
| `NIFTY26O1922700PE` | **PE** | 22700 | **ATM** | ₹99.00 | 65 | ₹6,435.00 | 16,169,400 | 4,150,575 |
| `NIFTY26O1922650PE` | **PE** | 22650 | **OTM** | ₹84.05 | 65 | ₹5,463.25 | 7,704,710 | 1,228,565 |
| `NIFTY26O1922600PE` | **PE** | 22600 | **OTM** | ₹72.50 | 65 | ₹4,712.50 | 29,492,190 | 4,655,820 |

---

## 2. Capital Sizing & The ₹1,500 Paper Account Constraint

### The Mathematical Reality of NSE Options
1. **Contract Lot Size:** NIFTY options trade in standardized lots of 65 units (or BankNifty 15/30 units).
2. **Capital Formula for Long Option Buyer:**
   $$\text{Required Capital} = \text{Option Premium (LTP)} \times \text{Market Lot Size}$$
   - For an ATM NIFTY CE at ₹229.90: $229.90 \times 65 = \mathbf{₹14,943.50}$.
   - For an ATM NIFTY PE at ₹99.00: $99.00 \times 65 = \mathbf{₹6,435.00}$.
   - For an OTM NIFTY PE at ₹20.00: $20.00 \times 65 = \mathbf{₹1,300.00}$.
3. **Strict Risk Enforcement under ₹1,500 Starting Bankroll:**
   - Any option contract where $\text{Premium} \times \text{Lot Size} > \text{Available Cash}$ (₹1,500.00) MUST be **rejected** with:
     `REJECTED: INSUFFICIENT_CASH (Premium ₹X * Lot Y = ₹Z > Bankroll ₹1,500.00)`.
   - Deep OTM options with small premiums ($< ₹23.00 \times 65 = ₹1,495.00$) are technically purchasable under ₹1,500, but carry extreme theta decay risk.
   - Therefore, the options engine enforces a **Moneyness & Delta Quality Filter**: contracts with Delta $< 0.15$ or bid/ask spread $> 8\%$ are rejected as non-viable.

---

## 3. CE/PE Options Signal Logic

```
[Underlying Model Inference (NIFTY 50 / Equity)]
                        │
       ┌────────────────┴────────────────┐
       ▼                                 ▼
Bullish Prediction               Bearish Prediction
(Spec > 0 & Tree >= +2 bps)      (Spec < 0 & Tree <= -2 bps)
       │                                 │
       ▼                                 ▼
Filter Eligible CE Contracts     Filter Eligible PE Contracts
(ATM / Near OTM)                 (ATM / Near OTM)
       │                                 │
       └────────────────┬────────────────┘
                        ▼
           [Contract Validation Gate]
             1. Expiry valid (Current weekly/monthly)
             2. Lot Size * LTP <= Available Paper Cash (₹1,500)
             3. Liquidity: Volume > 5,000 contracts, Spread < 5%
             4. Expected Underlying Move * Delta > Roundtrip Fees
                        │
                        ▼
             [Paper Order Dispatch]
             BUY CE or BUY PE (1 Lot)
             Max Loss = 100% of Premium Paid
```

---

## 4. Strategy Mode Isolation

To preserve pristine accounting, the engine strictly separates:
- `CASH_EQUITY`: Intraday cash equities mode (INFY, RELIANCE, BAJFINANCE, AXISBANK, TATASTEEL, NIFTYBEES). Whole shares under available cash. No naked shorting.
- `OPTIONS_PAPER`: NSE European options buying mode (NIFTY CE/PE). Contract lots under available cash. No naked option writing/selling.

Both modes share the same single-process architecture, risk limits, and statutory accounting engine.
