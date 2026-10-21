#!/usr/bin/env python3
"""
AlphaNSE -> DhanHQ Read-Only Connection Test
Phase 1 Validation: Proves authentication and read-only connectivity.

Safety Architecture:
- Dual-Key Fail-Closed Safety Gate: LIVE_TRADING and ALLOW_REAL_ORDERS
- ZERO order placement calls (place_order, place_slice_order, etc.)
- ZERO cancellation calls (cancel_order, cancel_all, etc.)
- 100% read-only querying of funds, positions, holdings, order books, and pre-trade margin calculations.
"""

import os
import sys
import json
from typing import Any, Dict
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Try importing official DhanHQ v2.1.0+ SDK
try:
    from dhanhq import DhanContext, dhanhq
except ImportError:
    print("[ERROR] 'dhanhq' library not found.")
    print("Please install via: uv pip install -U dhanhq python-dotenv")
    sys.exit(1)

# AlphaNSE Universe Security ID Mapping on Dhan (NSE Equity Segment)
ALPHANSE_SECURITY_MAP = {
    "INFY": {"security_id": "1594", "name": "Infosys Ltd", "approx_price": 1850.0},
    "RELIANCE": {"security_id": "2885", "name": "Reliance Industries", "approx_price": 2950.0},
    "TCS": {"security_id": "11536", "name": "Tata Consultancy Services", "approx_price": 4100.0},
    "HDFCBANK": {"security_id": "1333", "name": "HDFC Bank Ltd", "approx_price": 1650.0},
    "BAJFINANCE": {"security_id": "317", "name": "Bajaj Finance Ltd", "approx_price": 6800.0},
}


def format_json(data: Any) -> str:
    """Pretty prints JSON or dictionary structures."""
    try:
        return json.dumps(data, indent=2, default=str)
    except Exception:
        return str(data)


def check_dual_key_safety() -> bool:
    """Verifies the dual-key fail-closed safety condition."""
    live_trading = os.getenv("LIVE_TRADING", "False").strip().lower() == "true"
    allow_real_orders = os.getenv("ALLOW_REAL_ORDERS", "False").strip().lower() == "true"
    
    # Dual-Key Fail-Closed Condition: BOTH must be True
    is_live_authorized = live_trading and allow_real_orders
    return is_live_authorized


def run_readonly_test():
    # Load .env from project root
    load_dotenv()

    client_id = os.getenv("DHAN_CLIENT_ID")
    access_token = os.getenv("DHAN_ACCESS_TOKEN")
    
    is_live_authorized = check_dual_key_safety()

    print("\n" + "=" * 70)
    print("      AlphaNSE -> DhanHQ API (v2.1.0+) READ-ONLY AUDIT")
    print("=" * 70)
    print(f"Safety Mode: LIVE_TRADING = {os.getenv('LIVE_TRADING', 'False')}")
    print(f"Safety Mode: ALLOW_REAL_ORDERS = {os.getenv('ALLOW_REAL_ORDERS', 'False')}")
    if not is_live_authorized:
        print("[LOCKED] Dual-Key Gate: FAIL-CLOSED. Order dispatch is strictly disabled.")
    else:
        print("[WARN] DUAL-KEY GATE UNLOCKED. (Warning: This script will STILL NOT place orders).")

    if not client_id or not access_token or "YOUR_" in client_id or "YOUR_" in access_token or "your_" in client_id or "your_" in access_token:
        print("\n[CONFIG ERROR] Valid credentials not found in '.env' file!")
        print("-" * 70)
        print("Setup Instructions:")
        print("1. Copy '.env.example' to '.env'")
        print("2. Log into Dhan Web -> My Profile -> DhanHQ Trading APIs")
        print("3. Generate your Client ID and Personal Access Token (valid for 24h)")
        print("4. Add them to '.env':")
        print("     DHAN_CLIENT_ID=1000000000")
        print("     DHAN_ACCESS_TOKEN=eyJhbGciOi...")
        print("5. Re-run this script: uv run python v3/execution/dhan_readonly_test.py")
        print("-" * 70)
        return False

    # Mask credentials for terminal display security
    masked_token = f"{access_token[:8]}...{access_token[-6:]}" if len(access_token) > 16 else "***"
    masked_client = f"{client_id[:3]}***{client_id[-2:]}" if len(client_id) > 5 else "***"
    print(f"Client ID:    {masked_client}")
    print(f"Access Token: {masked_token}")
    print("-" * 70)

    try:
        # Initialize DhanContext (DhanHQ v2.1.0 pattern)
        context = DhanContext(client_id, access_token)
        dhan = dhanhq(context)
        print("[OK] DhanContext initialized successfully.")
    except Exception as e:
        print(f"[FATAL] Failed to initialize DhanContext: {e}")
        return False

    # ---------------------------------------------------------
    # 1. Funds & Margin Limits
    # ---------------------------------------------------------
    print("\n[CHECKPOINT 1/5] Querying Available Funds & Margins...")
    try:
        funds = dhan.get_fund_limits()
        print("Response:")
        print(format_json(funds))
        if isinstance(funds, dict) and funds.get("status") == "success":
            avail = funds.get("data", {}).get("availabelBalance", "N/A")
            print(f"[OK] Funds check passed. Available Balance: Rs. {avail}")
        elif isinstance(funds, dict) and funds.get("status") == "failure":
            remarks = funds.get("remarks", {})
            err_msg = remarks.get("error_message", "Unknown failure")
            print(f"[WARN] Dhan API Returned Error: {err_msg}")
            if "expired" in err_msg.lower() or "token" in err_msg.lower():
                print("-> Note: Dhan Web access tokens expire after 24 hours. Please generate a fresh token.")
            return False
    except Exception as e:
        print(f"[ERROR] Exception fetching funds: {e}")
        return False

    # ---------------------------------------------------------
    # 2. Intraday / Derivatives Positions
    # ---------------------------------------------------------
    print("\n[CHECKPOINT 2/5] Querying Open Positions...")
    try:
        positions = dhan.get_positions()
        print("Response:")
        print(format_json(positions))
        print("[OK] Positions query completed.")
    except Exception as e:
        print(f"[ERROR] Exception fetching positions: {e}")

    # ---------------------------------------------------------
    # 3. Demat Holdings
    # ---------------------------------------------------------
    print("\n[CHECKPOINT 3/5] Querying Demat Holdings...")
    try:
        holdings = dhan.get_holdings()
        print("Response:")
        print(format_json(holdings))
        print("[OK] Holdings query completed.")
    except Exception as e:
        print(f"[ERROR] Exception fetching holdings: {e}")

    # ---------------------------------------------------------
    # 4. Daily Order Book
    # ---------------------------------------------------------
    print("\n[CHECKPOINT 4/5] Querying Today's Order Book...")
    try:
        orders = dhan.get_order_list()
        print("Response:")
        print(format_json(orders))
        print("[OK] Order book query completed.")
    except Exception as e:
        print(f"[ERROR] Exception fetching order list: {e}")

    # ---------------------------------------------------------
    # 5. Dynamic Quote & Pre-Trade Margin/Cost Calculator
    # ---------------------------------------------------------
    print("\n[CHECKPOINT 5/5] Testing Dynamic Quote & Pre-Trade Margin Calculator...")
    try:
        infy_meta = ALPHANSE_SECURITY_MAP["INFY"]
        sec_id_int = int(infy_meta["security_id"])
        
        # Step A: Query Live Quote API directly from Dhan
        print(f"-> Fetching dynamic market quote for {infy_meta['name']} (ID: {sec_id_int})...")
        quote_resp = dhan.quote_data({"NSE_EQ": [sec_id_int]})
        print("Quote Response:")
        print(format_json(quote_resp))
        
        # Extract live LTP dynamically
        dynamic_price = infy_meta["approx_price"]
        is_dynamic = False
        if isinstance(quote_resp, dict) and quote_resp.get("status") == "success":
            data = quote_resp.get("data", {})
            # Dhan quote structure: data["NSE_EQ"][str(sec_id_int)]["last_price"]
            nse_data = data.get("NSE_EQ", {}).get(str(sec_id_int), {}) or data.get(str(sec_id_int), {})
            ltp = nse_data.get("last_price") or nse_data.get("ltp") or nse_data.get("close")
            if ltp and float(ltp) > 0:
                dynamic_price = float(ltp)
                is_dynamic = True
                print(f"[OK] Live quote successfully obtained: LTP = Rs. {dynamic_price}")
        
        if not is_dynamic:
            print(f"[NOTE] Live market closed or quote unavailable; using fallback reference price: Rs. {dynamic_price}")

        # Step B: Feed dynamic price into Margin Calculator
        print(f"-> Calculating pre-trade margin for 1 Share Intraday (MIS) at Rs. {dynamic_price}:")
        calc_result = dhan.margin_calculator(
            security_id=infy_meta["security_id"],
            exchange_segment=dhan.NSE,
            transaction_type=dhan.BUY,
            quantity=1,
            product_type=dhan.INTRA,
            price=dynamic_price
        )
        print("Margin & Cost Calculator Response:")
        print(format_json(calc_result))
        print("[OK] Dynamic quote and margin calculator check completed.")

        # Step C: Evaluate Pre-Trade Guard Decision
        print("\n-> Running Pre-Trade Guard Evaluation on Quote Packet:")
        from v3.execution.market_data_guards import MarketDataGuard
        guard = MarketDataGuard(max_staleness_seconds=5.0, max_daily_loss=30.0, max_capital=1500.0)
        
        # When running offline/outside market hours, note bypass status
        is_open, open_msg = guard.is_market_open()
        if not is_open:
            print(f"   [NOTICE] {open_msg}")
            guard_pass, guard_msg, _ = guard.evaluate_pre_trade_gates(
                security_id=infy_meta["security_id"],
                quote_packet=quote_resp,
                current_daily_loss=0.0,
                proposed_trade_value=dynamic_price,
                bypass_market_hours=True
            )
            decision_label = "PASS (Bypass Off-Hours)" if guard_pass else "REJECT"
            print(f"   [GUARD DECISION] {decision_label}: {guard_msg}")
        else:
            guard_pass, guard_msg, _ = guard.evaluate_pre_trade_gates(
                security_id=infy_meta["security_id"],
                quote_packet=quote_resp,
                current_daily_loss=0.0,
                proposed_trade_value=dynamic_price,
                bypass_market_hours=False
            )
            decision_label = "PASS" if guard_pass else "REJECT"
            print(f"   [GUARD DECISION] {decision_label}: {guard_msg}")

    except Exception as e:
        print(f"[WARN] Dynamic quote / margin calculator check returned: {e}")

    print("\n" + "=" * 70)
    print("               AUDIT SUMMARY: READ-ONLY TEST FINISHED")
    print("=" * 70)
    print("No orders were dispatched. Capital at risk remains Rs. 0.00.")
    print("=" * 70 + "\n")
    return True


if __name__ == "__main__":
    run_readonly_test()
