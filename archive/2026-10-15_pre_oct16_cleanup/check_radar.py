import urllib.request
import json

try:
    res = json.loads(urllib.request.urlopen('http://localhost:8000/api/state').read().decode())
    print("=" * 75)
    print(f"RADAR STATUS at {res.get('last_scan_time', 'N/A')}")
    print(f"Hurdle: {res.get('profit_threshold_pct')}% | Capital: INR {res.get('available_capital')} | Positions: {len(res.get('positions', {}))}")
    print("=" * 75)
    print(f"{'Symbol':<14} | {'Price':>8} | {'Pred Ret':>9} | {'Hurdle':>7} | {'Conf':>6} | {'Signal':<6} | {'Status'}")
    print("-" * 75)
    for s in res.get("last_signals", []):
        sym = s.get("symbol", "")
        p = s.get("current_price", 0.0)
        ret = s.get("predicted_return_pct", 0.0)
        hurdle = s.get("profit_threshold_pct", 0.0)
        conf = s.get("confidence", 0.0)
        sig = s.get("signal", "HOLD")
        bl = s.get("blacklisted", False)
        status = "BLACKLISTED" if bl else ("READY" if conf >= 45.0 else f"WAITING (Conf {conf:.1f}% < 45%)")
        print(f"{sym:<14} | INR {p:>5.2f} | {ret:>+8.3f}% | {hurdle:>6.2f}% | {conf:>5.1f}% | {sig:<6} | {status}")
    print("=" * 75)
except Exception as e:
    print(f"Error checking radar: {e}")
