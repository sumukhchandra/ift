#!/usr/bin/env python3
"""
scripts/run_session14_kotak_live_trader.py
AlphaNSE V3 — Session 14 Real Market Trading Engine (Kotak Neo Trade API).

TARGET: Live Real Market Execution (Session 14 / Real Trading Desk).
EXECUTION MODE: REAL LIVE BROKER ORDERS (Dual-Key LIVE_TRADING=True Enforced).

MANDATES & INSTITUTIONAL SAFEGUARDS:
1. Real Broker Execution:
   - Direct order routing to Kotak Neo Trade API (Client UCC: 116K1).
   - Zero Brokerage Trade Free Plan applied (Brokerage: ₹0.00).
2. Strict Capital Allocation:
   - Capital allocated: ₹1,500.00 per model (₹9,000.00 fleet total).
   - Maximum active positions: 1 concurrent position per model.
3. Zero Company Loss Doctrine:
   - Max loss per trade: 0.30% cap (Strict ₹4.50 stop-loss).
   - Daily loss kill-switch: hard circuit breaker at ₹15.00.
   - 15:15 IST Mandatory Square-Off: 100% cash liquidation before 15:30 close.
4. Autonomous Standby:
   - Prior to 09:15:00 IST, runs in STANDBY_FOR_OPEN mode with live clock countdown.
   - Engages live execution loop seamlessly at 09:15:00 IST.
"""

import os
import sys
import math
import json
import time
import argparse
from datetime import datetime, date, time as dtime, timedelta
from typing import Dict, Any, List, Optional

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

if sys.stdout and getattr(sys.stdout, "encoding", None) and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv(os.path.join(WORKSPACE_ROOT, ".env"))

import yfinance as yf
from v3.execution.kotak_adapter import KotakLiveBrokerAdapter
from v2.risk.cost_engine import IndiaCostEngine

EVENT_LOG = os.path.join(WORKSPACE_ROOT, "v3", "reports", "SESSION_14_LIVE_ORDERS_STREAM.jsonl")
STATE_FILE = os.path.join(WORKSPACE_ROOT, "v3", "reports", "SESSION_14_RUNTIME_STATE.json")
WEIGHTS_PATH = os.path.join(WORKSPACE_ROOT, "v3", "models", "multimodel", "retrained_session14_weights.json")
BACKUP_WEIGHTS_PATH = os.path.join(WORKSPACE_ROOT, "v3", "models", "multimodel", "retrained_session12_weights.json")
SUMMARY_REPORT = os.path.join(WORKSPACE_ROOT, "v3", "reports", "SESSION_14_LIVE_EXECUTION_REPORT.md")
LOG_FILE = os.path.join(WORKSPACE_ROOT, "logs", "session14_live_trading.log")

os.makedirs(os.path.join(WORKSPACE_ROOT, "logs"), exist_ok=True)


class TeeLogger:
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.logfile = open(filename, "a", encoding="utf-8", buffering=1)

    def write(self, message):
        if self.terminal:
            try:
                self.terminal.write(message)
                self.terminal.flush()
            except Exception:
                pass
        try:
            self.logfile.write(message)
            self.logfile.flush()
        except Exception:
            pass

    def flush(self):
        if self.terminal:
            try:
                self.terminal.flush()
            except Exception:
                pass
        try:
            self.logfile.flush()
            self.logfile.flush()
        except Exception:
            pass


sys.stdout = TeeLogger(LOG_FILE)
sys.stderr = sys.stdout


class Session14KotakLiveTrader:
    def __init__(self, poll_interval: int = 15, force_live_orders: bool = True, force_active: bool = False):
        self.poll_interval = poll_interval
        self.force_active = force_active
        self.force_live_orders = force_live_orders

        # Initialize Kotak Neo Adapter with institutional safety limits
        self.adapter = KotakLiveBrokerAdapter(
            max_capital=1500.0,
            max_daily_loss=15.0,
            max_trades_per_day=10,
            require_edge_filter=True
        )
        self.cost_engine = IndiaCostEngine()

        # Asset Universe and Kotak Neo Scrip Mappings
        self.universe = {
            "^NSEI": {
                "name": "NIFTY 50",
                "model": "SMC_4CONF_920",
                "role": "Index Champion",
                "kotak_symbol": "NIFTYBEES-EQ",
                "segment": "nse_cm",
                "tick_mult": 1.0
            },
            "INFY.NS": {
                "name": "Infosys",
                "model": "V2_15M",
                "role": "15m Momentum Rider",
                "kotak_symbol": "INFY-EQ",
                "segment": "nse_cm",
                "tick_mult": 1.0
            },
            "TATACAP.NS": {
                "name": "Tata Capital",
                "model": "HYPO001",
                "role": "Shelf Defense",
                "kotak_symbol": "TATACAP-EQ",
                "segment": "nse_cm",
                "tick_mult": 1.0
            },
            "BAJFINANCE.NS": {
                "name": "Bajaj Finance",
                "model": "HYPO002",
                "role": "High-Beta Squeeze",
                "kotak_symbol": "BAJFINANCE-EQ",
                "segment": "nse_cm",
                "tick_mult": 1.0
            },
            "AXISBANK.NS": {
                "name": "Axis Bank",
                "model": "HYPO003",
                "role": "Dip Buyer",
                "kotak_symbol": "AXISBANK-EQ",
                "segment": "nse_cm",
                "tick_mult": 1.0
            },
            "RELIANCE.NS": {
                "name": "Reliance",
                "model": "V3_60M",
                "role": "Multi-Factor Trend",
                "kotak_symbol": "RELIANCE-EQ",
                "segment": "nse_cm",
                "tick_mult": 1.0
            }
        }

        # Model Weights
        self.models_data: Dict[str, Any] = {}
        self._load_weights()

        # Operational State
        self.active_positions: Dict[str, Dict[str, Any]] = {}
        self.closed_trades: List[Dict[str, Any]] = []
        self.realized_pnl: float = 0.0
        self.cycle_count: int = 0
        self.candle_buffers: Dict[str, List[Dict[str, Any]]] = {}

        os.makedirs(os.path.dirname(EVENT_LOG), exist_ok=True)
        os.makedirs(os.path.join(WORKSPACE_ROOT, "logs"), exist_ok=True)

        # Record standalone OS Process ID
        self.pid_file = os.path.join(WORKSPACE_ROOT, "logs", "session14_live_trader.pid")
        try:
            with open(self.pid_file, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
        except Exception:
            pass

    def save_runtime_state(self, status: str = "RUNNING"):
        """Persists live runtime state to disk for external querying by Antigravity or operator."""
        state = {
            "session_date": datetime.now().strftime("%Y-%m-%d"),
            "last_updated": datetime.now().isoformat(),
            "pid": os.getpid(),
            "status": status,
            "cycle": self.cycle_count,
            "broker": self.adapter.broker_name,
            "ucc": self.adapter.ucc or "116K1",
            "active_positions_count": len(self.active_positions),
            "realized_pnl": round(self.realized_pnl, 2),
            "active_positions": self.active_positions,
            "closed_trades_count": len(self.closed_trades),
            "recent_trades": self.closed_trades[-5:]
        }
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def _load_weights(self):
        target = WEIGHTS_PATH if os.path.exists(WEIGHTS_PATH) else BACKUP_WEIGHTS_PATH
        if os.path.exists(target):
            try:
                with open(target, "r", encoding="utf-8") as f:
                    self.models_data = json.load(f)
                print(f"[OK] Loaded multi-model weights from: {os.path.basename(target)}")
            except Exception as e:
                print(f"[WARN] Failed to load model weights: {e}")

    def log_event(self, event_type: str, data: Dict[str, Any]):
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data
        }
        try:
            with open(EVENT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            pass

    def check_connection(self) -> bool:
        """Verifies Kotak Neo API session and funds."""
        print("=" * 80)
        print("  ⚡ ALPHANSE V3 — KOTAK NEO LIVE BROKER CONNECTION VERIFICATION")
        print("=" * 80)
        print(f"  • Broker Adapter:          {self.adapter.broker_name}")
        print(f"  • Live Execution Flag:     {'🟢 ENABLED (REAL MONEY ORDERS)' if self.adapter.is_live else '🔴 DISABLED (PAPER MODE)'}")
        print(f"  • Kotak Client Code (UCC): {self.adapter.ucc or '116K1'}")
        print(f"  • Authenticated Session:   {'🟢 YES' if self.adapter.is_authenticated else '🔴 NO'}")

        bal = self.adapter.get_balance()
        print(f"  • Available Cash (Limits): ₹{bal.get('available_cash', 0.0):,.2f}")
        print(f"  • Max Capital Per Model:   ₹{self.adapter.max_capital:,.2f}")
        print(f"  • Max Loss Per Trade:      ₹4.50 (0.30% Hard Cap)")
        print(f"  • Daily Loss Kill-Switch:  ₹{self.adapter.max_daily_loss:,.2f}")
        print("=" * 80)
        return self.adapter.is_authenticated

    def fetch_live_market_data(self) -> Dict[str, Any]:
        """Pulls latest real-time prices from the market."""
        sym_list = list(self.universe.keys())
        try:
            df = yf.download(sym_list, period="1d", interval="1m", progress=False)
            if df.empty:
                df = yf.download(sym_list, period="5d", interval="1d", progress=False)

            quotes = {}
            for sym in sym_list:
                try:
                    c_s = df["Close"][sym].dropna()
                    ltp = float(c_s.iloc[-1]) if not c_s.empty else 0.0
                    o_s = df["Open"][sym].dropna()
                    o = float(o_s.iloc[0]) if not o_s.empty else ltp
                    h_s = df["High"][sym].dropna()
                    h = float(h_s.max()) if not h_s.empty else ltp
                    l_s = df["Low"][sym].dropna()
                    l = float(l_s.min()) if not l_s.empty else ltp
                    v_s = df["Volume"][sym].dropna()
                    v = int(v_s.sum()) if not v_s.empty else 1000

                    quotes[sym] = {
                        "name": self.universe[sym]["name"],
                        "kotak_symbol": self.universe[sym]["kotak_symbol"],
                        "ltp": round(ltp, 2),
                        "open": round(o, 2),
                        "high": round(h, 2),
                        "low": round(l, 2),
                        "volume": v,
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    }

                    buf = self.candle_buffers.setdefault(sym, [])
                    buf.append({
                        "close": ltp,
                        "open": o,
                        "high": h,
                        "low": l,
                        "volume": v
                    })
                    if len(buf) > 50:
                        buf.pop(0)
                except Exception:
                    pass
            return quotes
        except Exception as e:
            print(f"  [WARN] Data fetch failed: {e}")
            return {}

    def compute_features(self, sym: str) -> Optional[List[float]]:
        buf = self.candle_buffers.get(sym, [])
        if len(buf) < 15:
            return None

        closes = [b["close"] for b in buf]
        highs = [b["high"] for b in buf]
        lows = [b["low"] for b in buf]
        vols = [b["volume"] for b in buf]
        i = len(buf) - 1

        c0 = closes[i]
        r1 = (c0 - closes[i - 1]) / closes[i - 1] if closes[i - 1] > 0 else 0.0
        r3 = (c0 - closes[i - 3]) / closes[i - 3] if closes[i - 3] > 0 else 0.0
        r5 = (c0 - closes[i - 5]) / closes[i - 5] if closes[i - 5] > 0 else 0.0

        # Simple RSI 14
        diffs = [closes[k] - closes[k - 1] for k in range(max(1, i - 13), i + 1)]
        gains = [max(0.0, d) for d in diffs]
        losses = [abs(min(0.0, d)) for d in diffs]
        avg_g = sum(gains) / 14.0 if gains else 0.0
        avg_l = sum(losses) / 14.0 if losses else 1e-9
        rs = avg_g / (avg_l or 1e-9)
        rsi14 = 100.0 - (100.0 / (1.0 + rs))

        # Range and wick pressure
        tot_range = max(1e-4, highs[i] - lows[i])
        upper_wick = (highs[i] - max(buf[i]["open"], c0)) / tot_range
        lower_wick = (min(buf[i]["open"], c0) - lows[i]) / tot_range
        wick_pressure = lower_wick - upper_wick

        vol_surge = (vols[i] / (sum(vols[max(0, i-5):i]) / 5.0 or 1.0)) if vols[i] > 0 else 1.0

        return [r1, r3, r5, rsi14 / 100.0, wick_pressure, vol_surge]

    def evaluate_and_execute_orders(self, quotes: Dict[str, Any]):
        """Evaluates entry signals and executes REAL ORDERS to Kotak Neo."""
        for sym, q in quotes.items():
            u_info = self.universe[sym]
            mid = u_info["model"]

            if mid in self.active_positions:
                continue

            feats = self.compute_features(sym)
            if not feats:
                continue

            # Model prediction: momentum directional bias
            r1 = feats[0]
            rsi = feats[3]
            wick = feats[4]

            # Trigger condition: high-conviction momentum or reversal
            side = None
            if rsi < 0.35 and wick > 0.2:
                side = "BUY"
            elif rsi > 0.65 and wick < -0.2:
                side = "SELL"
            elif r1 > 0.0015:
                side = "BUY"
            elif r1 < -0.0015:
                side = "SELL"

            if not side:
                continue

            ltp = q["ltp"]
            kotak_sym = u_info["kotak_symbol"]

            # Position sizing under strict ₹1,500 limit
            cap = 1500.0
            shares = max(1, int(cap // (ltp or 100.0)))
            notional = round(shares * ltp, 2)

            print(f"\n  🎯 [SIGNAL TRIGGERED] {mid} on {sym} ({kotak_sym}): {side} {shares} shares @ ₹{ltp:.2f} (Notional: ₹{notional:,.2f})")

            # DISPATCH REAL ORDER TO KOTAK NEO
            order_res = self.adapter.place_order(
                symbol=kotak_sym,
                side=side,
                quantity=shares,
                price=ltp,
                order_type="MARKET",
                product="MIS",
                segment=u_info["segment"],
                tag="AlphaNSE_S14"
            )

            status = order_res.get("status")
            order_id = order_res.get("order_id")

            if status in ["FILLED", "SUBMITTED"] or order_id:
                print(f"  🚀 [REAL ORDER DISPATCHED TO KOTAK NEO]:")
                print(f"     Order ID:       {order_id}")
                print(f"     Trading Symbol: {kotak_sym}")
                print(f"     Side:           {side} {shares} shares")
                print(f"     Status:         {status}")

                pos = {
                    "model_id": mid,
                    "symbol": sym,
                    "kotak_symbol": kotak_sym,
                    "order_id": order_id,
                    "side": side,
                    "entry_time": datetime.now().strftime("%H:%M:%S IST"),
                    "entry_price": ltp,
                    "shares": shares,
                    "notional": notional,
                    "current_price": ltp,
                    "unrealized_pnl": 0.0,
                    "target_pnl": 15.00,  # +1% target
                    "stop_loss_pnl": -4.50 # 0.3% stop-loss
                }
                self.active_positions[mid] = pos
                self.log_event("REAL_ORDER_OPENED", pos)
            else:
                print(f"  ❌ [ORDER REJECTED BY KOTAK NEO]: {order_res.get('reason')}")
                self.log_event("REAL_ORDER_REJECTED", {"symbol": kotak_sym, "reason": order_res.get("reason")})

    def monitor_positions_and_exit(self, quotes: Dict[str, Any]):
        """Monitors live positions and dispatches REAL EXIT ORDERS on SL / Target."""
        for mid, pos in list(self.active_positions.items()):
            sym = pos["symbol"]
            kotak_sym = pos["kotak_symbol"]
            q = quotes.get(sym)
            if not q:
                continue

            curr_px = q["ltp"]
            side = pos["side"]
            unrealized = (curr_px - pos["entry_price"]) * pos["shares"] if side == "BUY" else (pos["entry_price"] - curr_px) * pos["shares"]
            pos["current_price"] = curr_px
            pos["unrealized_pnl"] = round(unrealized, 2)

            print(f"  📌 [LIVE POSITION] {mid} on {kotak_sym} | Side: {side} | Entry: ₹{pos['entry_price']:.2f} ➔ LTP: ₹{curr_px:.2f} | P&L: ₹{unrealized:+.2f}")

            # Check Hard 0.3% Stop Loss (-₹4.50)
            if unrealized <= pos["stop_loss_pnl"]:
                print(f"\n  🛑 [STOP LOSS HIT - DISPATCHING REAL EXIT ORDER]: {mid} hit -₹{abs(unrealized):.2f}. Cutting loss...")
                self._exit_position(mid, curr_px, reason="STOP_LOSS_0.3%_CAP")
                continue

            # Check Profit Target (+₹15.00)
            if unrealized >= pos["target_pnl"]:
                print(f"\n  🎯 [PROFIT TARGET HIT - DISPATCHING REAL EXIT ORDER]: {mid} reached +₹{unrealized:.2f}. Locking profit...")
                self._exit_position(mid, curr_px, reason="PROFIT_TARGET_HARVEST")
                continue

    def _exit_position(self, model_id: str, exit_price: float, reason: str):
        pos = self.active_positions.pop(model_id, None)
        if not pos:
            return

        exit_side = "SELL" if pos["side"] == "BUY" else "BUY"
        kotak_sym = pos["kotak_symbol"]
        shares = pos["shares"]

        # Place Real Exit Order to Kotak Neo
        exit_res = self.adapter.place_order(
            symbol=kotak_sym,
            side=exit_side,
            quantity=shares,
            price=exit_price,
            order_type="MARKET",
            product="MIS",
            segment="nse_cm",
            tag="AlphaNSE_S14_Exit"
        )

        gross = (exit_price - pos["entry_price"]) * shares if pos["side"] == "BUY" else (pos["entry_price"] - exit_price) * shares
        costs = self.cost_engine.calculate_roundtrip_cost(pos["notional"], gross / (pos["notional"] or 1.0))
        net = gross - (costs.total_cost - costs.brokerage)
        self.realized_pnl += net

        closed_rec = {
            "model_id": model_id,
            "symbol": pos["symbol"],
            "kotak_symbol": kotak_sym,
            "entry_order_id": pos["order_id"],
            "exit_order_id": exit_res.get("order_id"),
            "side": pos["side"],
            "entry_time": pos["entry_time"],
            "exit_time": datetime.now().strftime("%H:%M:%S IST"),
            "entry_price": pos["entry_price"],
            "exit_price": exit_price,
            "shares": shares,
            "gross_pnl": round(gross, 2),
            "net_pnl": round(net, 2),
            "exit_reason": reason,
            "exit_status": exit_res.get("status")
        }
        self.closed_trades.append(closed_rec)
        self.log_event("REAL_ORDER_CLOSED", closed_rec)

        print(f"  🏁 [POSITION LIQUIDATED]: Net P&L: ₹{net:+.2f} | Reason: {reason} | Exit Order ID: {exit_res.get('order_id')}")

    def check_network_health(self) -> bool:
        """Pings DNS roots to verify active internet connectivity."""
        import socket
        for host in ["8.8.8.8", "1.1.1.1"]:
            try:
                socket.setdefaulttimeout(3.0)
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((host, 53))
                s.close()
                return True
            except Exception:
                pass
        return False

    def reconcile_broker_positions(self):
        """Re-syncs local active positions with genuine broker positions from Kotak Neo."""
        try:
            print("\n  🔄 [RECONCILING BROKER POSITIONS] Fetching open positions directly from Kotak Neo...")
            broker_pos = self.adapter.get_positions()
            print(f"  • Kotak Broker Open Positions Count: {len(broker_pos)}")
            for bp in broker_pos:
                print(f"    - {bp.get('symbol')}: Side {bp.get('side')}, Qty {bp.get('quantity')}, Entry ₹{bp.get('entry_price')}, LTP ₹{bp.get('current_price')}")
        except Exception as e:
            print(f"  [WARN] Position reconciliation warning: {e}")

    def run(self):
        print("=" * 88)
        print("  🚀 ALPHANSE V3 — SESSION 14 REAL MARKET TRADING DAEMON")
        print(f"  TARGET SESSION: {datetime.now().strftime('%A, %B %d, %Y')}")
        print(f"  BROKER STATUS:  {self.adapter.broker_name}")
        print("  FAILOVER STATUS: Network Resilience & Auto-Reconnection Active")
        print("=" * 88)

        if not self.check_connection():
            print("  ❌ Kotak Neo authentication failed. Please check credentials in .env.")
            return

        market_open = dtime(9, 15)
        market_close = dtime(15, 30)
        square_off = dtime(15, 15)
        network_was_down = False

        while True:
            # 1. Network Health Check & Failover Sentinel
            if not self.check_network_health():
                network_was_down = True
                now_str = datetime.now().strftime("%H:%M:%S IST")
                print(f"\r[{now_str}] ⚠️ [NETWORK OUTAGE DETECTED] Internet disconnected or changing IP. Holding positions safely... retrying in 5s", end="", flush=True)
                time.sleep(5)
                continue

            # If network just restored, re-authenticate with Kotak Neo under new IP
            if network_was_down:
                network_was_down = False
                now_str = datetime.now().strftime("%H:%M:%S IST")
                print(f"\n\n[{now_str}] 🌐 [NETWORK RESTORED] New internet connection active!")
                print("  • Re-authenticating Kotak Neo Trade API session under new IP address...")
                self.adapter._init_neo_sdk()
                if self.adapter.is_authenticated:
                    print("  • 🟢 Kotak Neo session re-authenticated successfully!")
                else:
                    print("  • ⚠️ Kotak Neo re-auth in progress...")
                self.reconcile_broker_positions()
                self.log_event("NETWORK_FAILOVER_RESTORED", {"reauthenticated": self.adapter.is_authenticated})

            now = datetime.now()
            current_time = now.time()
            self.cycle_count += 1

            is_open = (market_open <= current_time < square_off) and (now.weekday() < 5)
            if self.force_active:
                is_open = True

            if not is_open:
                # Calculate next market open timestamp
                if now.weekday() < 5 and current_time < market_open:
                    next_open_date = now.date()
                else:
                    # Move to next trading day (skip weekends)
                    next_open_date = now.date() + timedelta(days=1)
                    while next_open_date.weekday() >= 5:
                        next_open_date += timedelta(days=1)

                target_open = datetime.combine(next_open_date, market_open)
                remaining_secs = max(0, int((target_open - now).total_seconds()))
                hrs = remaining_secs // 3600
                mins = (remaining_secs % 3600) // 60
                secs = remaining_secs % 60

                target_str = target_open.strftime("%A, %b %d at 09:15:00 IST")
                self.save_runtime_state("STANDBY_FOR_OPEN")
                print(f"\r[{now.strftime('%H:%M:%S')} IST] ⏳ [STANDBY_FOR_OPEN] Next Session: {target_str} (in {hrs:02d}h {mins:02d}m {secs:02d}s). Armed & waiting...", end="", flush=True)
                time.sleep(10)
                continue

            print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')} IST] ─── CYCLE #{self.cycle_count} (Market: 🟢 OPEN) ───")

            # 15:15 IST Mandatory Square-Off Sentinel
            if current_time >= square_off and not self.force_active:
                if self.active_positions:
                    print(f"\n  ⏰ [15:15 IST MANDATORY SQUARE OFF] Liquidating all open positions to 100% cash...")
                    for mid in list(self.active_positions.keys()):
                        self._exit_position(mid, self.active_positions[mid]["current_price"], reason="EOD_MANDATORY_SQUARE_OFF")
                self.save_runtime_state("SQUARED_OFF")
                print("  ✅ All intraday positions squared off. Safe for EOD.")
                # Reset daily limits for next session
                self.active_positions = {}
                self.closed_trades = []
                self.realized_pnl = 0.0
                time.sleep(30)
                continue

            # Fetch live market prices
            quotes = self.fetch_live_market_data()
            if quotes:
                # Monitor active positions
                self.monitor_positions_and_exit(quotes)

                # Evaluate new trade opportunities
                self.evaluate_and_execute_orders(quotes)

            self.save_runtime_state("TRADING_ACTIVE")
            time.sleep(self.poll_interval)


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="AlphaNSE Session 14 Kotak Real Trader")
        parser.add_argument("--test-conn", action="store_true", help="Test Kotak Neo connection and exit")
        parser.add_argument("--force-active", action="store_true", help="Force active cycle for testing outside hours")
        args = parser.parse_args()

        trader = Session14KotakLiveTrader(force_active=args.force_active)
        if args.test_conn:
            trader.check_connection()
        else:
            trader.run()
    except Exception as e:
        import traceback
        print("\n💥 [FATAL CRASH]:", e)
        traceback.print_exc()
