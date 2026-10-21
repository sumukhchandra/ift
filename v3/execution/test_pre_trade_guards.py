import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from v3.execution.market_data_guards import MarketDataGuard, IST


def build_mock_quote(
    security_id: str = "1594",
    ltp: float = 1850.0,
    upper_circuit: float = 2035.0,
    lower_circuit: float = 1665.0,
    timestamp_offset_seconds: float = 0.0,
    missing_circuit: bool = False,
    depth_zero_sellers: bool = False,
    reference_dt: datetime = None
) -> dict:
    if reference_dt is None:
        reference_dt = datetime.now(IST)
    
    quote_dt = reference_dt + timedelta(seconds=timestamp_offset_seconds)
    ts_str = quote_dt.strftime("%Y-%m-%d %H:%M:%S")

    inst_data = {
        "last_price": ltp,
        "last_trade_time": ts_str,
        "ohlc": {"open": 1845.0, "high": 1860.0, "low": 1840.0, "close": 1850.0},
        "depth": {
            "buy": [{"quantity": 100, "price": 1849.5}],
            "sell": [{"quantity": 0 if depth_zero_sellers else 100, "price": 1850.5}]
        }
    }

    if not missing_circuit:
        inst_data["circuit_limit"] = {
            "upper_circuit_limit": upper_circuit,
            "lower_circuit_limit": lower_circuit
        }

    return {
        "status": "success",
        "data": {
            "NSE_EQ": {
                security_id: inst_data
            }
        }
    }


def run_falsification_suite():
    print("\n" + "=" * 75)
    print("      AlphaNSE Pre-Trade Guard Falsification & Stress Test Suite")
    print("=" * 75)
    
    guard = MarketDataGuard(
        max_staleness_seconds=5.0,
        clock_drift_tolerance_seconds=2.0,
        max_daily_loss=30.0,
        max_capital=1500.0
    )

    # Use a fixed reference time on a weekday at 10:30 AM IST (market open)
    simulated_now = datetime(2026, 10, 5, 10, 30, 0, tzinfo=IST) # Monday 10:30 AM

    test_cases = [
        # 1. Stale Quote (12s old > 5s limit)
        (
            "1. Stale Quote (> 5.0s)",
            lambda: guard.evaluate_pre_trade_gates(
                security_id="1594",
                quote_packet=build_mock_quote(timestamp_offset_seconds=-12.0, reference_dt=simulated_now),
                current_daily_loss=0.0,
                proposed_trade_value=1200.0,
                current_dt=simulated_now
            ),
            False
        ),
        # 2. Future Timestamp (+8s in future)
        (
            "2. Future Timestamp (+8.0s clock drift)",
            lambda: guard.evaluate_pre_trade_gates(
                security_id="1594",
                quote_packet=build_mock_quote(timestamp_offset_seconds=+8.0, reference_dt=simulated_now),
                current_daily_loss=0.0,
                proposed_trade_value=1200.0,
                current_dt=simulated_now
            ),
            False
        ),
        # 3. Security ID Mismatch (Asked for 1594, packet contains 2885)
        (
            "3. Security ID Mismatch (Expected 1594, got 2885)",
            lambda: guard.evaluate_pre_trade_gates(
                security_id="1594",
                quote_packet=build_mock_quote(security_id="2885", reference_dt=simulated_now),
                current_daily_loss=0.0,
                proposed_trade_value=1200.0,
                current_dt=simulated_now
            ),
            False
        ),
        # 4. Missing Circuit Limit Data (Fail-Closed)
        (
            "4. Missing Circuit Limit Data (Fail-Closed)",
            lambda: guard.evaluate_pre_trade_gates(
                security_id="1594",
                quote_packet=build_mock_quote(missing_circuit=True, reference_dt=simulated_now),
                current_daily_loss=0.0,
                proposed_trade_value=1200.0,
                current_dt=simulated_now
            ),
            False
        ),
        # 5. Price Locked at Upper Circuit
        (
            "5. Price Locked at Upper Circuit (LTP >= 2035)",
            lambda: guard.evaluate_pre_trade_gates(
                security_id="1594",
                quote_packet=build_mock_quote(ltp=2035.0, upper_circuit=2035.0, reference_dt=simulated_now),
                current_daily_loss=0.0,
                proposed_trade_value=1200.0,
                current_dt=simulated_now
            ),
            False
        ),
        # 6. Price Locked at Lower Circuit
        (
            "6. Price Locked at Lower Circuit (LTP <= 1665)",
            lambda: guard.evaluate_pre_trade_gates(
                security_id="1594",
                quote_packet=build_mock_quote(ltp=1665.0, lower_circuit=1665.0, reference_dt=simulated_now),
                current_daily_loss=0.0,
                proposed_trade_value=1200.0,
                current_dt=simulated_now
            ),
            False
        ),
        # 7. Market Depth Locked (Zero Sellers)
        (
            "7. Market Depth Locked (Zero Sellers in book)",
            lambda: guard.evaluate_pre_trade_gates(
                security_id="1594",
                quote_packet=build_mock_quote(depth_zero_sellers=True, reference_dt=simulated_now),
                current_daily_loss=0.0,
                proposed_trade_value=1200.0,
                current_dt=simulated_now
            ),
            False
        ),
        # 8. Daily Loss Limit Breach (Rs. 30.50 >= Rs. 30.00)
        (
            "8. Daily Loss Limit Breach (Rs. 30.50 >= Rs. 30.00)",
            lambda: guard.evaluate_pre_trade_gates(
                security_id="1594",
                quote_packet=build_mock_quote(reference_dt=simulated_now),
                current_daily_loss=30.50,
                proposed_trade_value=1200.0,
                current_dt=simulated_now
            ),
            False
        ),
        # 9. Capital Cap Breach (Rs. 1,501 > Rs. 1,500)
        (
            "9. Capital Cap Breach (Rs. 1,501.00 > Rs. 1,500.00)",
            lambda: guard.evaluate_pre_trade_gates(
                security_id="1594",
                quote_packet=build_mock_quote(reference_dt=simulated_now),
                current_daily_loss=0.0,
                proposed_trade_value=1501.0,
                current_dt=simulated_now
            ),
            False
        ),
        # 10. Outside Market Hours (Sunday 11:00 AM)
        (
            "10. Outside Market Hours (Sunday 11:00 AM)",
            lambda: guard.evaluate_pre_trade_gates(
                security_id="1594",
                quote_packet=build_mock_quote(reference_dt=datetime(2026, 10, 4, 11, 0, 0, tzinfo=IST)),
                current_daily_loss=0.0,
                proposed_trade_value=1200.0,
                current_dt=datetime(2026, 10, 4, 11, 0, 0, tzinfo=IST)
            ),
            False
        ),
        # 11. Happy Path (Fresh quote, within hours, inside limits)
        (
            "11. Happy Path (Fresh quote, within limits, market open)",
            lambda: guard.evaluate_pre_trade_gates(
                security_id="1594",
                quote_packet=build_mock_quote(timestamp_offset_seconds=-1.0, reference_dt=simulated_now),
                current_daily_loss=5.0,
                proposed_trade_value=1200.0,
                current_dt=simulated_now
            ),
            True
        ),
    ]

    passed_all = True
    for title, test_fn, expected_pass in test_cases:
        passed, msg, ltp = test_fn()
        expected_label = "PASS" if expected_pass else "REJECT"
        actual_label = "PASS" if passed else "REJECT"

        if passed == expected_pass:
            print(f"  [OK] {title:<52} -> {actual_label} ({msg})")
        else:
            print(f"  [FAIL] {title:<52} -> Expected {expected_label} but got {actual_label} ({msg})")
            passed_all = False

    print("-" * 75)
    if passed_all:
        print("[SUCCESS] All 11 stress & falsification test cases PASSED perfectly!")
        print("          All invalid conditions successfully trigger strict REJECT.")
    else:
        print("[ERROR] Some guard test cases failed.")
    print("=" * 75 + "\n")
    return passed_all


if __name__ == "__main__":
    run_falsification_suite()
