"""
QA/nifty50_constituents.py
Authoritative, official constituent registry for the NSE NIFTY 50 Index.
Used to validate universe eligibility, filter non-constituent equities,
and define the active specialist trading focus basket.
"""

from typing import Dict, List, Set, Optional

# Official 50 Constituent Equities of the NSE NIFTY 50 Index (with .NS Yahoo suffix)
NIFTY_50_CONSTITUENTS: Dict[str, Dict[str, str]] = {
    "ADANIENT.NS": {"name": "Adani Enterprises Ltd.", "sector": "Metals & Mining", "series": "EQ"},
    "ADANIPORTS.NS": {"name": "Adani Ports and Special Economic Zone Ltd.", "sector": "Services", "series": "EQ"},
    "APOLLOHOSP.NS": {"name": "Apollo Hospitals Enterprise Ltd.", "sector": "Healthcare", "series": "EQ"},
    "ASIANPAINT.NS": {"name": "Asian Paints Ltd.", "sector": "Consumer Durables", "series": "EQ"},
    "AXISBANK.NS": {"name": "Axis Bank Ltd.", "sector": "Financial Services", "series": "EQ"},
    "BAJAJ-AUTO.NS": {"name": "Bajaj Auto Ltd.", "sector": "Automobile", "series": "EQ"},
    "BAJFINANCE.NS": {"name": "Bajaj Finance Ltd.", "sector": "Financial Services", "series": "EQ"},
    "BAJAJFINSV.NS": {"name": "Bajaj Finserv Ltd.", "sector": "Financial Services", "series": "EQ"},
    "BEL.NS": {"name": "Bharat Electronics Ltd.", "sector": "Capital Goods", "series": "EQ"},
    "BPCL.NS": {"name": "Bharat Petroleum Corporation Ltd.", "sector": "Oil, Gas & Consumable Fuels", "series": "EQ"},
    "BHARTIARTL.NS": {"name": "Bharti Airtel Ltd.", "sector": "Telecommunication", "series": "EQ"},
    "BRITANNIA.NS": {"name": "Britannia Industries Ltd.", "sector": "Fast Moving Consumer Goods", "series": "EQ"},
    "CIPLA.NS": {"name": "Cipla Ltd.", "sector": "Healthcare", "series": "EQ"},
    "COALINDIA.NS": {"name": "Coal India Ltd.", "sector": "Oil, Gas & Consumable Fuels", "series": "EQ"},
    "DRREDDY.NS": {"name": "Dr. Reddy's Laboratories Ltd.", "sector": "Healthcare", "series": "EQ"},
    "EICHERMOT.NS": {"name": "Eicher Motors Ltd.", "sector": "Automobile", "series": "EQ"},
    "GRASIM.NS": {"name": "Grasim Industries Ltd.", "sector": "Construction Materials", "series": "EQ"},
    "HCLTECH.NS": {"name": "HCL Technologies Ltd.", "sector": "Information Technology", "series": "EQ"},
    "HDFCBANK.NS": {"name": "HDFC Bank Ltd.", "sector": "Financial Services", "series": "EQ"},
    "HDFCLIFE.NS": {"name": "HDFC Life Insurance Company Ltd.", "sector": "Financial Services", "series": "EQ"},
    "HEROMOTOCO.NS": {"name": "Hero MotoCorp Ltd.", "sector": "Automobile", "series": "EQ"},
    "HINDALCO.NS": {"name": "Hindalco Industries Ltd.", "sector": "Metals & Mining", "series": "EQ"},
    "HINDUNILVR.NS": {"name": "Hindustan Unilever Ltd.", "sector": "Fast Moving Consumer Goods", "series": "EQ"},
    "ICICIBANK.NS": {"name": "ICICI Bank Ltd.", "sector": "Financial Services", "series": "EQ"},
    "ITC.NS": {"name": "ITC Ltd.", "sector": "Fast Moving Consumer Goods", "series": "EQ"},
    "INDUSINDBK.NS": {"name": "IndusInd Bank Ltd.", "sector": "Financial Services", "series": "EQ"},
    "INFY.NS": {"name": "Infosys Ltd.", "sector": "Information Technology", "series": "EQ"},
    "JSWSTEEL.NS": {"name": "JSW Steel Ltd.", "sector": "Metals & Mining", "series": "EQ"},
    "KOTAKBANK.NS": {"name": "Kotak Mahindra Bank Ltd.", "sector": "Financial Services", "series": "EQ"},
    "LT.NS": {"name": "Larsen & Toubro Ltd.", "sector": "Construction", "series": "EQ"},
    "M&M.NS": {"name": "Mahindra & Mahindra Ltd.", "sector": "Automobile", "series": "EQ"},
    "MARUTI.NS": {"name": "Maruti Suzuki India Ltd.", "sector": "Automobile", "series": "EQ"},
    "NTPC.NS": {"name": "NTPC Ltd.", "sector": "Power", "series": "EQ"},
    "NESTLEIND.NS": {"name": "Nestle India Ltd.", "sector": "Fast Moving Consumer Goods", "series": "EQ"},
    "ONGC.NS": {"name": "Oil & Natural Gas Corporation Ltd.", "sector": "Oil, Gas & Consumable Fuels", "series": "EQ"},
    "POWERGRID.NS": {"name": "Power Grid Corporation of India Ltd.", "sector": "Power", "series": "EQ"},
    "RELIANCE.NS": {"name": "Reliance Industries Ltd.", "sector": "Oil, Gas & Consumable Fuels", "series": "EQ"},
    "SBILIFE.NS": {"name": "SBI Life Insurance Company Ltd.", "sector": "Financial Services", "series": "EQ"},
    "SBIN.NS": {"name": "State Bank of India", "sector": "Financial Services", "series": "EQ"},
    "SHRIRAMFIN.NS": {"name": "Shriram Finance Ltd.", "sector": "Financial Services", "series": "EQ"},
    "SUNPHARMA.NS": {"name": "Sun Pharmaceutical Industries Ltd.", "sector": "Healthcare", "series": "EQ"},
    "TCS.NS": {"name": "Tata Consultancy Services Ltd.", "sector": "Information Technology", "series": "EQ"},
    "TATACONSUM.NS": {"name": "Tata Consumer Products Ltd.", "sector": "Fast Moving Consumer Goods", "series": "EQ"},
    "TATAMOTORS.NS": {"name": "Tata Motors Ltd.", "sector": "Automobile", "series": "EQ"},
    "TATASTEEL.NS": {"name": "Tata Steel Ltd.", "sector": "Metals & Mining", "series": "EQ"},
    "TECHM.NS": {"name": "Tech Mahindra Ltd.", "sector": "Information Technology", "series": "EQ"},
    "TITAN.NS": {"name": "Titan Company Ltd.", "sector": "Consumer Durables", "series": "EQ"},
    "TRENT.NS": {"name": "Trent Ltd.", "sector": "Consumer Services", "series": "EQ"},
    "ULTRACEMCO.NS": {"name": "UltraTech Cement Ltd.", "sector": "Construction Materials", "series": "EQ"},
    "WIPRO.NS": {"name": "Wipro Ltd.", "sector": "Information Technology", "series": "EQ"},
}

# Authoritative NIFTY 50 Index and ETF benchmarks
NIFTY_INDEX_BENCHMARKS: Dict[str, str] = {
    "^NSEI": "NIFTY 50 Benchmark Index",
    "NIFTYBEES.NS": "Nippon India Nifty 50 BeES ETF"
}

def is_nifty50_constituent(symbol: str) -> bool:
    """Verifies whether an instrument belongs to the official NIFTY 50 universe."""
    clean = symbol.upper()
    if clean in NIFTY_50_CONSTITUENTS or clean in NIFTY_INDEX_BENCHMARKS:
        return True
    # Check stripped symbol without .NS
    ns_sym = f"{clean}.NS"
    return ns_sym in NIFTY_50_CONSTITUENTS

def get_full_nifty50_universe() -> List[str]:
    """Returns all 50 constituent symbols."""
    return sorted(list(NIFTY_50_CONSTITUENTS.keys()))

# Active Specialist Execution Focus Basket:
# Constituents with verified specialist regression weights and high-density 1m historical training data.
ACTIVE_FOCUS_BASKET: Dict[str, Dict[str, str]] = {
    "INFY.NS": {"name": "Infosys", "model": "V2_15M", "kotak": "INFY-EQ"},
    "RELIANCE.NS": {"name": "Reliance", "model": "V3_60M", "kotak": "RELIANCE-EQ"},
    "BAJFINANCE.NS": {"name": "Bajaj Finance", "model": "HYPO002", "kotak": "BAJFINANCE-EQ"},
    "AXISBANK.NS": {"name": "Axis Bank", "model": "HYPO003", "kotak": "AXISBANK-EQ"},
    "TATASTEEL.NS": {"name": "Tata Steel", "model": "HYPO001", "kotak": "TATASTEEL-EQ"},
    "NIFTYBEES.NS": {"name": "Nifty 50 ETF", "model": "SMC_4CONF_920", "kotak": "NIFTYBEES-EQ"}
}
