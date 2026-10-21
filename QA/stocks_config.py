from QA.nifty50_constituents import (
    NIFTY_50_CONSTITUENTS,
    is_nifty50_constituent,
    get_full_nifty50_universe
)

# Full Official 50-Stock NIFTY 50 Universe
FULL_NIFTY_50_UNIVERSE = get_full_nifty50_universe()

# --- Active Stock Focus Universe (High-Liquidity Constituents) ---------------
STOCK_UNIVERSE = {
    # Original 5
    "RELIANCE.NS": "Reliance Industries",
    "HDFCBANK.NS": "HDFC Bank",
    "BHARTIARTL.NS": "Bharti Airtel",
    "ICICIBANK.NS": "ICICI Bank",
    "TATASTEEL.NS": "Tata Steel",
    # Added 5 (high-liquidity Nifty 50)
    "INFY.NS": "Infosys",
    "TCS.NS": "TCS",
    "SBIN.NS": "State Bank of India",
    "AXISBANK.NS": "Axis Bank",
    "BAJFINANCE.NS": "Bajaj Finance",
    # Benchmark Index Instrument
    "^NSEI": "NIFTY 50 Index",
}

STOCK_SYMBOLS = list(STOCK_UNIVERSE.keys())

# --- Active Trading Universe & Blacklist (Phase 1 Fix 2) ---------------------
# Dynamic model scoring evaluates all 10 liquid universe stocks.
# Static blacklist is cleared to enable top-momentum breakouts (e.g. AXISBANK, TATACAP, BAJFINANCE).
STOCK_BLACKLIST = set()

# Symbols actively approved for live trade execution
ACTIVE_TRADING_SYMBOLS = STOCK_SYMBOLS

# --- Trading Thresholds ------------------------------------------------------
MIN_NET_PROFIT_PCT = 0.015         # 1.5% minimum net profit target
MAX_GROSS_LOSS_PCT = 0.003         # 0.3% max gross loss before stop-loss triggers (Strict Mandate)
DEFAULT_CAPITAL = 100000            # Default starting capital (INR) -- overridable from UI

# --- Position Sizing (dynamic, confidence-based) -----------------------------
# Percentage of AVAILABLE (uninvested) capital to allocate per trade
# Calibrated for 100% own-capital spot compounding without leverage drag
POSITION_SIZING = {
    "high":   0.95,   # Confidence > 0.8  -> 95% of available capital
    "medium": 0.85,   # Confidence 0.7-0.8 -> 85%
    "low":    0.60,   # Confidence 0.6-0.7 -> 60%
}

# --- Scanning & Timing -------------------------------------------------------
SCAN_INTERVAL_SECONDS = 180         # Scan market every 3 minutes
MARKET_OPEN_HOUR = 9                # NSE opens at 9:15 AM IST
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15              # NSE closes at 3:30 PM IST
MARKET_CLOSE_MINUTE = 30

# --- Auto-Retrain ------------------------------------------------------------
RETRAIN_HOUR = 9                    # Daily auto-retrain at 9:00 AM IST
RETRAIN_MINUTE = 0
ACCURACY_RETRAIN_THRESHOLD = 0.55   # Retrain if rolling accuracy drops below 55%
ROLLING_ACCURACY_WINDOW = 20        # Number of recent trades to compute rolling accuracy
DATA_FETCH_PERIOD = "90d"           # Fetch 90 days historical data for larger training set
DATA_FETCH_INTERVAL = "5m"          # 5-minute candles

# --- Tax Configuration -------------------------------------------------------
PROFIT_TAX_PCT = 0.25               # 25% short-term capital gains tax (user chose higher buffer)
