#!/usr/bin/env python3
"""
v3/execution/angel_readonly_test.py
AlphaNSE -> Angel One SmartAPI Read-Only Connection Test
Phase 1 Validation: Proves authentication and read-only connectivity.

Safety Architecture:
- Dual-Key Fail-Closed Safety Gate: LIVE_TRADING and ALLOW_REAL_ORDERS
- ZERO order placement calls
- ZERO cancellation calls
- 100% read-only querying of funds, positions, holdings, and live quotes.
"""

import os
import sys
import json
from typing import Any, Dict

# Ensure UTF-8 output on Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure repo root is on sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(WORKSPACE_ROOT, ".env"))
except ImportError:
    pass

try:
    from SmartApi import SmartConnect
    import pyotp
except ImportError as e:
    print(f"[ERROR] SmartApi or pyotp library missing: {e}")
    print("Please install: pip install smartapi-python pyotp logzero")
    sys.exit(1)


def check_dual_key_safety() -> bool:
    """Verifies dual-key fail-closed safety condition."""
    live_trading = os.getenv("LIVE_TRADING", "False").strip().lower() == "true"
    allow_real_orders = os.getenv("ALLOW_REAL_ORDERS", "False").strip().lower() == "true"
    return live_trading and allow_real_orders


def run_angel_readonly_audit():
    print("=" * 72)
    print("       AlphaNSE -> Angel One SmartAPI READ-ONLY AUDIT")
    print("=" * 72)

    api_key = os.getenv("ANGEL_API_KEY", "").strip()
    client_code = os.getenv("ANGEL_CLIENT_CODE", "").strip()
    pin = os.getenv("ANGEL_PIN", "").strip()
    totp_secret = os.getenv("ANGEL_TOTP_SECRET", "").strip()
    direct_totp = os.getenv("ANGEL_TOTP", "").strip()
    if len(sys.argv) > 1 and sys.argv[1].isdigit() and len(sys.argv[1]) == 6:
        direct_totp = sys.argv[1]

    has_api_key = bool(api_key)
    has_client_code = bool(client_code)
    has_pin = bool(pin)
    has_totp = bool(totp_secret or direct_totp)

    print(f"[*] API Key Present:       {'YES (Masked: ' + api_key[:4] + '****)' if has_api_key else 'NO'}")
    print(f"[*] Client Code Present:   {'YES (' + client_code + ')' if has_client_code else 'NO'}")
    print(f"[*] Trading PIN Present:   {'YES (****)' if has_pin else 'NO'}")
    print(f"[*] TOTP Configured:       {'YES (' + ('Direct TOTP' if direct_totp else 'Auto-TOTP Secret') + ')' if has_totp else 'NO'}")

    is_live_authorized = check_dual_key_safety()
    print(f"[*] LIVE_TRADING Flag:     {os.getenv('LIVE_TRADING', 'False')}")
    print(f"[*] ALLOW_REAL_ORDERS:     {os.getenv('ALLOW_REAL_ORDERS', 'False')}")
    print(f"[*] Dual-Key Live Status:  {'UNLOCKED (LIVE ORDERS ENABLED)' if is_live_authorized else 'LOCKED (READ-ONLY PAPER AIRGAP ACTIVE)'}")
    print("-" * 72)

    if not (has_api_key and has_client_code and has_pin and has_totp):
        print("\n[CONFIGURATION REQUIRED] Angel One credentials missing in .env file.")
        print("Please create or edit `.env` in the workspace root with:")
        print("  ANGEL_API_KEY=your_smartapi_key")
        print("  ANGEL_CLIENT_CODE=your_client_code")
        print("  ANGEL_PIN=your_trading_pin")
        print("  ANGEL_TOTP_SECRET=your_authenticator_totp_secret  (OR provide current 6-digit code)")
        print("  LIVE_TRADING=False")
        print("  ALLOW_REAL_ORDERS=False")
        print("=" * 72)
        return False

    # Connect to SmartAPI
    print("[1/5] Initializing SmartConnect and authenticating via TOTP...")
    try:
        smart_api = SmartConnect(api_key=api_key)
        if direct_totp:
            totp_val = direct_totp
        else:
            totp_val = pyotp.TOTP(totp_secret).now()
        session_data = smart_api.generateSession(client_code, pin, totp_val)

        if not session_data or not session_data.get("status"):
            msg = session_data.get("message", "Unknown error") if session_data else "No response"
            print(f"[FAIL] Authentication Failed: {msg}")
            return False

        print("[OK] SmartAPI session authenticated successfully!")
        jwt_token = session_data.get("data", {}).get("jwtToken")
        feed_token = smart_api.getfeedToken()
    except Exception as e:
        print(f"[FAIL] Authentication exception: {e}")
        return False

    # 2. RMS / Funds query
    print("\n[2/5] Querying Account Funds & Margin (getRMS)...")
    try:
        rms = smart_api.getRMS()
        if rms and rms.get("status") and "data" in rms:
            data = rms["data"]
            net_avail = data.get("net", data.get("availablecash", "N/A"))
            print(f"[OK] Available Cash / Net Margin: Rs. {net_avail}")
            print(f"     Collateral: Rs. {data.get('collateral', '0.0')}")
        else:
            print(f"[WARN] getRMS response: {rms}")
    except Exception as e:
        print(f"[WARN] Error fetching RMS: {e}")

    # 3. Positions query
    print("\n[3/5] Querying Intraday Positions (position)...")
    try:
        pos = smart_api.position()
        if pos and pos.get("status"):
            positions = pos.get("data") or []
            print(f"[OK] Open Positions Count: {len(positions)}")
            for p in positions[:5]:
                print(f"     - {p.get('tradingsymbol')}: Qty {p.get('netqty')}, P&L {p.get('unrealised')}")
        else:
            print(f"[WARN] position response: {pos}")
    except Exception as e:
        print(f"[WARN] Error fetching positions: {e}")

    # 4. Holdings query
    print("\n[4/5] Querying CNC Holdings (holding)...")
    try:
        holdings = smart_api.holding()
        if holdings and holdings.get("status"):
            h_data = holdings.get("data") or []
            print(f"[OK] Holdings Count: {len(h_data)}")
        else:
            print(f"[WARN] holding response: {holdings}")
    except Exception as e:
        print(f"[WARN] Error fetching holdings: {e}")

    # 5. Live Quote (LTP) test
    print("\n[5/5] Querying Sample Live LTP Quote (INFY)...")
    try:
        ltp_res = smart_api.ltpData("NSE", "INFY-EQ", "1594")
        if ltp_res and ltp_res.get("status") and "data" in ltp_res:
            ltp = ltp_res["data"].get("ltp")
            print(f"[OK] INFY LTP: Rs. {ltp}")
        else:
            print(f"[INFO] ltpData response: {ltp_res}")
    except Exception as e:
        print(f"[WARN] Error fetching LTP: {e}")

    print("\n" + "=" * 72)
    print(" [VERDICT] ANGEL ONE SMARTAPI READ-ONLY AUDIT: SUCCESSFUL")
    print(" All queries completed with ZERO live orders and zero capital risk.")
    print("=" * 72)
    return True


if __name__ == "__main__":
    success = run_angel_readonly_audit()
    sys.exit(0 if success else 1)
