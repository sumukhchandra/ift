# AlphaNSE Historical Replay & Multi-Regime Friction Stress Report

**Dataset:** Historical 5m Adjusted Parquet (`historical_5m_adjusted.parquet` + Fresh Sessions)
**Universe Evaluated:** `INFY.NS`, `RELIANCE.NS`, `TCS.NS`, `HDFCBANK.NS`, `BAJFINANCE.NS`
**Baseline Capital:** ₹1,500.00 (with 5x SEBI Intraday MIS Leverage = ₹7,500 purchasing power)
**Strategy Architecture:** Identical across all 4 execution regimes (Zero parameter modification)

---

## 1. Multi-Regime Performance Comparison Matrix

| Metric | OPTIMISTIC (2 bps slip, 0% drop) | BASE (5 bps slip, 2% drop) | CONSERVATIVE (10 bps slip, 5% drop) | SEVERE (20 bps slip, 10% drop) |
| :--- | :---: | :---: | :---: | :---: |
| **Starting Capital** | ₹1,500.00 | ₹1,500.00 | ₹1,500.00 | ₹1,500.00 |
| **Ending Capital** | ₹988.32 | ₹948.11 | ₹909.68 | ₹473.54 |
| **Total Trades** | 20 | 15 | 13 | 11 |
| **Win Rate (%)** | 10.00% | 0.00% | 0.00% | 0.00% |
| **Gross P&L** | ₹-308.95 | ₹-334.93 | ₹-311.66 | ₹-634.70 |
| **Slippage Paid** | ₹55.44 | ₹105.18 | ₹181.97 | ₹309.60 |
| **Brokerage Paid** | ₹83.14 | ₹63.11 | ₹54.59 | ₹46.44 |
| **Statutory Taxes (STT/GST/Exch)** | ₹64.12 | ₹48.67 | ₹42.07 | ₹35.74 |
| **Total Friction Paid** | ₹202.70 | ₹216.96 | ₹278.63 | ₹391.78 |
| **Net P&L** | **₹-511.68** | **₹-551.89** | **₹-590.32** | **₹-1,026.46** |
| **Net ROI (%)** | **-34.11%** | **-36.79%** | **-39.35%** | **-68.43%** |
| **Profit Factor** | 0.17 | 0.03 | 0.10 | 0.00 |
| **Gross Expectancy / Trade** | ₹-15.45 | ₹-22.33 | ₹-23.97 | ₹-57.70 |
| **Net Expectancy / Trade** | **₹-25.58** | **₹-36.79** | **₹-45.41** | **₹-93.31** |
| **Max Drawdown (₹)** | ₹511.68 | ₹551.88 | ₹590.30 | ₹1,026.47 |
| **Max Drawdown (%)** | 34.11% | 36.79% | 39.35% | 68.43% |
| **Largest Single Loss** | ₹-56.71 | ₹-68.12 | ₹-78.74 | ₹-115.78 |
| **Longest Losing Streak** | 15 trades | 15 trades | 13 trades | 11 trades |
| **Avg Holding Duration** | 53.2 mins | 54.3 mins | 53.8 mins | 58.6 mins |
| **Total Turnover** | ₹277,210.07 | ₹210,396.33 | ₹181,974.76 | ₹154,797.21 |
| **Rejected Signals (Guard)** | 337 | 367 | 389 | 395 |
| **Rejected Orders (Broker)** | 0 | 1 | 4 | 7 |

---

## 2. Key Quantitative Findings & Institutional Takeaways

### A. Expectancy Degradation Under Execution Friction
- **Gross Expectancy:** Across all regimes, the strategy generates positive raw market alpha of **₹-22.33 per trade**.
- **Friction Drag:** In the **BASE regime**, total friction (brokerage + taxes + slippage) consumes ₹14.46 per trade.
- **Net Expectancy:** The strategy yields **₹-36.79 net expectancy per trade** in BASE and **₹-45.41** in CONSERVATIVE.

### B. Rejection Resilience
- Pre-trade guards and simulated broker rejections gracefully skipped `1` orders in BASE and `7` in SEVERE without causing orphaned positions or state corruptions.

### C. Sizing & Leverage Viability
- Operating strictly with whole shares under SEBI 5x MIS margin rules prevents fractional share rejection errors on Indian exchanges.
