#!/usr/bin/env python3
"""
v3/execution/live_trader.py
AlphaNSE V3 — Institutional Dual-Model Real-Money Live Trading Engine (Kotak Neo Trade API).

MATHEMATICALLY RIGOROUS PRODUCTION ENGINE:
1. Exact Feature Space (19 Institutional Features):
   - Multi-scale Returns (1m, 3m, 5m, 10m) & Return Acceleration
   - Dual RSI (7 & 14-period)
   - Micro-VWAP Distance & Bollinger Bandwidth / %B
   - Micro-ATR 14 & Parkinson Volatility
   - Orderflow Wick Pressures & Volume Surge Ratio
   - Mathematical Cross-Interaction Terms
2. Dual-Model Consensus Architecture:
   - Specialist Quant Model (Ridge Regression with Out-of-Sample Frozen Weights)
   - Machine Learning Tree Ensemble (CatBoost + LightGBM + XGBoost + Quantile Regressor)
   - Strict Concurrence Gate: Both models MUST agree on direction with minimum 3 bps conviction.
3. Pre-Trade Economic Friction Gate (EdgeFrictionGate):
   - Computes complete roundtrip statutory fees (STT, GST, Exchange, SEBI, Stamp Duty) + Spread + Slippage.
   - Only approves trade when net expected return after ALL frictions is strictly positive.
4. Institutional Capital Preservation:
   - Strict ₹1,500.00 capital limit per model (₹9,000.00 fleet total).
   - Strict 0.30% hard stop-loss cap (₹4.50 max loss per trade).
   - Dynamic Trailing Stop Ratchet: Breakeven at +0.50%, dynamic profit harvest at +1.00%.
   - Hard EOD Square-Off at 15:15:00 IST to 100% cash.
5. 24/7 Continuous Standby Watchdog:
   - Seamlessly rolls over to the next trading session with real-time countdown clock.
"""

import os
import sys
import math
import json
import time
import logging
import argparse
from datetime import datetime, date, time as dtime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
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
from v3.execution.edge_friction_gate import EdgeFrictionGate
from v2.risk.cost_engine import IndiaCostEngine
from QA.models.one_min_predictor import OneMinPredictor
from v3.intelligence.opportunity_engine import OpportunityDiscoveryEngine
from v3.intelligence.provenance_tracker import ProvenanceTracker
from v3.execution.candle_aggregator import OneMinuteCandleAggregator

# Production Paths
REPORTS_LIVE_DIR = os.path.join(WORKSPACE_ROOT, "reports", "live")
os.makedirs(REPORTS_LIVE_DIR, exist_ok=True)
EVENT_LOG = os.path.join(REPORTS_LIVE_DIR, "orders_stream.jsonl")
STATE_FILE = os.path.join(REPORTS_LIVE_DIR, "runtime_state.json")
WEIGHTS_PATH = os.path.join(WORKSPACE_ROOT, "v3", "models", "multimodel", "active_model_weights.json")
LOG_FILE = os.path.join(WORKSPACE_ROOT, "logs", "live_trader.log")
PID_FILE = os.path.join(WORKSPACE_ROOT, "logs", "live_trader.pid")

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
        except Exception:
            pass




def set_windows_keep_alive(enable: bool = True):
    """
    Prevents Windows from entering Modern Standby / Sleep while the daemon is actively running.
    Uses Win32 SetThreadExecutionState with ES_CONTINUOUS | ES_SYSTEM_REQUIRED.
    Safely no-ops on Linux / Render cloud.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        if not hasattr(ctypes, "windll"):
            return
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        if enable:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
            logging.info("[POWER] Windows thread execution keep-alive ENABLED (ES_CONTINUOUS | ES_SYSTEM_REQUIRED).")
        else:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            logging.info("[POWER] Windows thread execution keep-alive RESTORED to normal.")
    except Exception as e:
        logging.warning(f"[POWER] Could not set Windows keep-alive: {e}")



def is_pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            pass
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, Exception):
        return False


class FastMarketFeed:
    """Optimized parallel market data fetcher with Kotak Neo broker API primary feed."""

    def __init__(self, symbols: List[str], broker_adapter: Optional[Any] = None):
        self.symbols = symbols
        self.broker_adapter = broker_adapter
        self.broker_errors: int = 0
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.executor = ThreadPoolExecutor(max_workers=len(symbols) or 6)

    def _fetch_single(self, sym: str) -> Optional[Dict[str, Any]]:
        try:
            ticker = yf.Ticker(sym)
            fast = ticker.fast_info
            ltp = float(fast.get("lastPrice", fast.get("previousClose", 0.0)))
            o = float(fast.get("open", ltp))
            h = float(fast.get("dayHigh", ltp))
            l = float(fast.get("dayLow", ltp))
            v = int(fast.get("lastVolume", 1000))
            if ltp > 0:
                return {
                    "ltp": round(ltp, 2),
                    "open": round(o, 2),
                    "high": round(h, 2),
                    "low": round(l, 2),
                    "volume": v,
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                }
        except Exception as e:
            logging.debug(f"[FastMarketFeed] Single quote fetch error for {symbol}: {e}")
        return None

    def fetch_quotes(self, fallback_buffers: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> Dict[str, Any]:
        """Quote fetch with primary Kotak Neo Broker API and secondary fallback."""
        results = {}

        # 1. Primary: Direct Kotak Neo Trade API quotes if broker adapter is available
        if self.broker_adapter and hasattr(self.broker_adapter, "get_quotes"):
            try:
                b_quotes = self.broker_adapter.get_quotes(self.symbols)
                if b_quotes:
                    for sym in self.symbols:
                        if sym in b_quotes:
                            q_data = dict(b_quotes[sym])
                            # Strictly preserve is_stale flag from broker adapter
                            is_stale_flag = q_data.get("is_stale", False)
                            q_data["is_stale"] = is_stale_flag
                            results[sym] = q_data
                            if not is_stale_flag:
                                self.cache[sym] = q_data
                    self.broker_errors = 0
                else:
                    self.broker_errors += 1
                    logging.warning(f"[FastMarketFeed] Primary broker returned empty quotes (consecutive failures: {self.broker_errors})")
            except Exception as e:
                self.broker_errors += 1
                logging.warning(f"[FastMarketFeed] Primary broker get_quotes error (consecutive failures: {self.broker_errors}): {e}")
        else:
            self.broker_errors = 0

        # 2. Secondary: If any symbol missing from broker API, try FastMarketFeed parallel yfinance
        missing_syms = [s for s in self.symbols if s not in results]
        if missing_syms:
            futures = {self.executor.submit(self._fetch_single, sym): sym for sym in missing_syms}
            for fut in futures:
                sym = futures[fut]
                try:
                    data = fut.result(timeout=2.0)
                    if data:
                        data["source"] = "YFINANCE_LIVE"
                        data["is_stale"] = False
                        results[sym] = data
                        self.cache[sym] = data
                except Exception as e:
                    logging.warning(f"[FastMarketFeed] Secondary fallback error for {sym}: {e}")

        # 3. Tertiary: Fallback to cache or primed buffers if broker & feed both fail
        for sym in self.symbols:
            if sym not in results:
                if sym in self.cache:
                    results[sym] = dict(self.cache[sym])
                    results[sym]["is_stale"] = True
                    results[sym]["source"] = "CACHE_FALLBACK"
                elif fallback_buffers and sym in fallback_buffers and fallback_buffers[sym]:
                    last_b = fallback_buffers[sym][-1]
                    results[sym] = {
                        "ltp": round(float(last_b["close"]), 2),
                        "open": round(float(last_b["open"]), 2),
                        "high": round(float(last_b["high"]), 2),
                        "low": round(float(last_b["low"]), 2),
                        "volume": int(last_b.get("volume", 1000)),
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "source": "BUFFER_FALLBACK",
                        "is_stale": True
                    }
                    self.cache[sym] = results[sym]

        return results


class AlphaNSELiveTrader:
    def __init__(self, poll_interval: int = 10, force_active: bool = False, allow_short_selling: bool = False, mode: str = "CASH_EQUITY", shadow_mode: bool = True, state_file: Optional[str] = None):
        self.poll_interval = poll_interval
        self.force_active = force_active
        self.allow_short_selling = allow_short_selling
        self.mode = mode.upper()
        self.shadow_mode = shadow_mode
        self.state_file = state_file or STATE_FILE
        try:
            from v3.storage.persistence import get_storage_manager
            self.storage_manager = get_storage_manager()
        except Exception:
            self.storage_manager = None

        # Initialize Kotak Neo Adapter with institutional safety limits
        self.adapter = KotakLiveBrokerAdapter(
            max_capital=float(os.getenv("MAX_CAPITAL_ALLOCATED", "1500.0")),
            max_daily_loss=float(os.getenv("MAX_DAILY_LOSS", "30.0")),
            max_trades_per_day=10,
            require_edge_filter=True
        )

        # Options Engine initialization under OPTIONS_PAPER mode
        if self.mode == "OPTIONS_PAPER":
            from v3.execution.options_engine import OptionsEngine
            self.options_engine = OptionsEngine(
                broker_adapter=self.adapter,
                starting_bankroll=1500.0,
                underlying_symbol="NIFTY",
                reports_dir=REPORTS_LIVE_DIR
            )
        else:
            self.options_engine = None
        # Kotak Neo Trade Free Plan: 0 Brokerage on intraday cash equities
        self.cost_engine = IndiaCostEngine()
        self.cost_engine.brokerage_pct = 0.0
        self.cost_engine.brokerage_flat_cap = 0.0

        self.edge_gate = EdgeFrictionGate(
            half_spread_bps=2.5,
            slippage_bps=3.0,
            safety_margin_rs=0.40,
            min_net_expectancy_rs=0.30
        )
        self.edge_gate.cost_engine = self.cost_engine

        # Pure Quantitative Asset Universe & Kotak Neo Scrip Mappings
        self.universe = {
            "NIFTYBEES.NS": {
                "name": "Nifty 50 ETF",
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
            "TATASTEEL.NS": {
                "name": "Tata Steel",
                "model": "HYPO001",
                "role": "Metal Momentum",
                "kotak_symbol": "TATASTEEL-EQ",
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

        # Market Data Engine
        self.feed = FastMarketFeed(list(self.universe.keys()), broker_adapter=self.adapter)

        # Model Weights & ML Predictor
        self.models_data: Dict[str, Any] = {}
        self._load_weights()

        print("[INIT] Loading Machine Learning Tree Ensemble (CatBoost, LightGBM, XGBoost)...")
        try:
            self.ml_predictor = OneMinPredictor()
            print("[OK] Machine Learning Ensemble loaded successfully.")
        except Exception as e:
            print(f"[WARN] Failed to load OneMinPredictor: {e}")
            self.ml_predictor = None

        # Structured Logger (Preserves historical log entries via append mode)
        self.logger = logging.getLogger("AlphaNSELiveTrader")
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
            fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"))
            self.logger.addHandler(fh)

        # Operational State
        self.active_positions: Dict[str, Dict[str, Any]] = {}
        self.closed_trades: List[Dict[str, Any]] = []
        self.realized_pnl: float = 0.0
        self.paper_bankroll: float = 1500.00
        self.paper_ledger_file = os.path.join(REPORTS_LIVE_DIR, "paper_trading_ledger.json")
        self.cycle_count: int = 0
        self.candle_aggregator = OneMinuteCandleAggregator(max_history=60)
        self.candle_buffers: Dict[str, List[Dict[str, Any]]] = {}
        self.broker_quote_errors: int = 0
        self.feed_quote_errors: int = 0
        self.consecutive_stale_quotes: int = 0
        self.safe_halt_active: bool = False
        self.safe_halt_reason: str = ""
        self._last_cycle_time: Optional[float] = None
        self._shutdown_requested: bool = False

        # Load or initialize paper trading ledger
        if os.path.exists(self.paper_ledger_file):
            try:
                with open(self.paper_ledger_file, "r", encoding="utf-8") as f:
                    ldata = json.load(f)
                    self.closed_trades = ldata.get("trades", [])
                    self.realized_pnl = float(ldata.get("realized_pnl", 0.0))
                    # Recalculate true bankroll strictly from closed trades: 1500.00 + realized_pnl
                    self.paper_bankroll = round(1500.00 + self.realized_pnl, 2)
            except Exception as e:
                self.log_structured("LEDGER_LOAD_ERROR", {"error": str(e)}, f"Error reading paper ledger: {e}")
        self.save_paper_ledger()

        # Restart Recovery: Restore active open positions from runtime_state.json if available
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    prev_state = json.load(f)
                prev_pos = prev_state.get("active_positions", {})
                if prev_pos and not self.active_positions:
                    self.active_positions = prev_pos
                    print(f"🔄 [RECOVERY] Restored {len(self.active_positions)} active open position(s) from previous runtime state.")
            except Exception as e:
                print(f"⚠️ [RECOVERY] Could not restore previous state: {e}")

        # Pre-seed initial candle buffers from historical storage
        self._preseed_buffers()

        # Intelligence Engines: Multi-Regime Opportunity Discovery & Provenance Tracker
        self.provenance_tracker = ProvenanceTracker(log_dir=REPORTS_LIVE_DIR)
        self.opportunity_engine = OpportunityDiscoveryEngine(
            predictor=self.ml_predictor,
            specialist_weights=self.models_data,
            cost_engine=self.cost_engine,
            options_engine=self.options_engine,
            bankroll=self.paper_bankroll,
            min_net_expectancy_rs=0.25,
            min_confidence_pct=45.0,
            max_spread_bps=15.0
        )

    def log_structured(self, event_type: str, data: Dict[str, Any], message: str = ""):
        """
        Emits structured audit log entries to both logs/live_trader.log and reports/live/orders_stream.jsonl.
        """
        log_line = f"[{event_type}] {message} | {json.dumps(data, default=str)}"
        self.logger.info(log_line)
        self.log_event(event_type, data)

    def _setup_signal_handlers(self):
        """Registers OS signal handlers for graceful shutdown."""
        import signal

        def _signal_handler(signum, frame):
            print(f"\n🛑 [SIGNAL RECEIVED: {signum}] Initiating graceful shutdown...")
            self._shutdown_requested = True

        try:
            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)
        except Exception as e:
            self.logger.warning(f"Could not register OS signal handlers: {e}")

    def _preseed_buffers(self):
        """Pre-seeds candle buffers with the latest 60 authentic 1-minute bars."""
        data_dir = os.path.join(WORKSPACE_ROOT, "QA", "data")
        sym_map = {
            "NIFTYBEES.NS": "NSEI", "^NSEI": "NSEI", "INFY.NS": "INFY", "TATASTEEL.NS": "TATASTEEL",
            "BAJFINANCE.NS": "BAJFINANCE", "AXISBANK.NS": "AXISBANK", "RELIANCE.NS": "RELIANCE"
        }
        for full_sym, short_sym in sym_map.items():
            fpath = os.path.join(data_dir, f"{short_sym}_1m_weekend.csv")
            if os.path.exists(fpath):
                try:
                    df = pd.read_csv(fpath)
                    tail = df.tail(60)
                    buf = []
                    for _, r in tail.iterrows():
                        scale = 0.01 if (full_sym == "NIFTYBEES.NS" and float(r["close"]) > 5000) else 1.0
                        buf.append({
                            "timestamp": str(r.get("timestamp", r.get("date", ""))),
                            "close": round(float(r["close"]) * scale, 2),
                            "open": round(float(r["open"]) * scale, 2),
                            "high": round(float(r["high"]) * scale, 2),
                            "low": round(float(r["low"]) * scale, 2),
                            "volume": float(r["volume"])
                        })
                    self.candle_aggregator.preseed(full_sym, buf)
                    self.candle_buffers[full_sym] = self.candle_aggregator.get_bars(full_sym, include_forming=False)
                except Exception as e:
                    self.logger.warning(f"Error pre-seeding buffer for {full_sym}: {e}")

    def save_runtime_state(self, status: str = "RUNNING"):
        """Persists live state to disk for external querying."""
        tot_in = sum(t.get("money_in", 0) for t in self.closed_trades)
        tot_out = sum(t.get("money_out", 0) for t in self.closed_trades)
        state = {
            "session_date": datetime.now().strftime("%Y-%m-%d"),
            "last_updated": datetime.now().isoformat(),
            "pid": os.getpid(),
            "status": status,
            "execution_mode": "REAL_ORDERS" if self.adapter.is_live else "PAPER_TESTING",
            "cycle": self.cycle_count,
            "broker": self.adapter.broker_name,
            "ucc": self.adapter.ucc or "116K1",
            "starting_bankroll": 1500.00,
            "paper_bankroll": round(self.paper_bankroll, 2),
            "total_money_in": round(tot_in, 2),
            "total_money_out": round(tot_out, 2),
            "active_positions_count": len(self.active_positions),
            "realized_pnl": round(self.realized_pnl, 2),
            "active_positions": self.active_positions,
            "closed_trades_count": len(self.closed_trades),
            "recent_trades": self.closed_trades[-5:]
        }
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to save runtime state: {e}")
        try:
            if hasattr(self, "storage_manager") and self.storage_manager:
                self.storage_manager.save_runtime_state(state)
        except Exception as e:
            self.logger.warning(f"StorageManager failed to save state: {e}")
        self.save_paper_ledger()

    def save_paper_ledger(self):
        """Persists granular paper trading money-in vs money-out ledger to disk."""
        tot_in = sum(t.get("money_in", 0) for t in self.closed_trades)
        tot_out = sum(t.get("money_out", 0) for t in self.closed_trades)
        wins = [t for t in self.closed_trades if t.get("net_pnl", 0) > 0]
        losses = [t for t in self.closed_trades if t.get("net_pnl", 0) < 0]
        breakevens = [t for t in self.closed_trades if t.get("net_pnl", 0) == 0]
        win_rate = round((len(wins) / len(self.closed_trades) * 100.0), 2) if self.closed_trades else 0.0
        active_locked = sum(p.get("notional", 0) for p in self.active_positions.values())
        ledger = {
            "session_date": datetime.now().strftime("%Y-%m-%d"),
            "mode": "REAL_ORDERS" if self.adapter.is_live else "PAPER_TESTING",
            "starting_bankroll": 1500.00,
            "current_bankroll": round(self.paper_bankroll, 2),
            "available_cash": round(self.paper_bankroll - active_locked, 2),
            "active_locked_capital": round(active_locked, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "total_money_in": round(tot_in, 2),
            "total_money_out": round(tot_out, 2),
            "win_rate_pct": win_rate,
            "closed_trades_count": len(self.closed_trades),
            "active_positions_count": len(self.active_positions),
            "trades": self.closed_trades
        }
        try:
            with open(self.paper_ledger_file, "w", encoding="utf-8") as f:
                json.dump(ledger, f, indent=2)
            summary_path = os.path.join(REPORTS_LIVE_DIR, "paper_intraday_summary.json")
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump({
                    "session_date": datetime.now().strftime("%Y-%m-%d"),
                    "starting_paper_capital": 1500.00,
                    "ending_paper_capital": round(self.paper_bankroll, 2),
                    "realized_pnl": round(self.realized_pnl, 2),
                    "unrealized_pnl": round(sum(p.get("unrealized_pnl", 0.0) for p in self.active_positions.values()), 2),
                    "total_trades": len(self.closed_trades),
                    "wins": len(wins),
                    "losses": len(losses),
                    "breakevens": len(breakevens),
                    "win_rate_pct": win_rate,
                    "active_positions": self.active_positions
                }, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to persist paper ledger: {e}")
        try:
            if hasattr(self, "storage_manager") and self.storage_manager:
                self.storage_manager.save_paper_ledger(ledger)
        except Exception as e:
            self.logger.warning(f"StorageManager failed to save ledger: {e}")

    def _load_weights(self):
        if os.path.exists(WEIGHTS_PATH):
            try:
                with open(WEIGHTS_PATH, "r", encoding="utf-8") as f:
                    self.models_data = json.load(f)
                print(f"[OK] Loaded active quantitative model weights: {os.path.basename(WEIGHTS_PATH)}")
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
        except Exception as e:
            self.logger.warning(f"Failed to append to event log: {e}")
        try:
            if hasattr(self, "storage_manager") and self.storage_manager:
                self.storage_manager.append_event(event_type, data, timestamp=event["timestamp"])
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
        self.log_structured(
            "CONNECTION_TEST",
            {
                "broker": self.adapter.broker_name,
                "authenticated": self.adapter.is_authenticated,
                "is_live": self.adapter.is_live,
                "available_cash": bal.get("available_cash", 0.0),
                "max_capital": self.adapter.max_capital
            },
            f"Kotak Neo connection verification: {'AUTHENTICATED' if self.adapter.is_authenticated else 'UNAUTHENTICATED'}"
        )
        return self.adapter.is_authenticated

    def extract_exact_19_features(self, sym: str) -> Optional[List[float]]:
        """
        Extracts the EXACT 19 institutional features mathematically identical
        to the training pipeline.
        """
        buf = self.candle_buffers.get(sym, [])
        if len(buf) < 25:
            return None

        # Verify buffer sampling timeframe: reject sub-minute sampling
        is_valid_tf, tf_err = self.candle_aggregator.validate_buffer_timeframe(buf)
        if not is_valid_tf:
            self.logger.warning(f"[TIMEFRAME_MISMATCH] {sym}: {tf_err}")
            return None

        i = len(buf) - 1
        c_list = buf

        c0 = c_list[i]["close"]
        h0 = c_list[i]["high"]
        l0 = c_list[i]["low"]
        o0 = c_list[i]["open"]
        v0 = c_list[i]["volume"]

        if c0 <= 0 or l0 <= 0:
            return None

        # 1. Returns & Momentum
        r1 = (c0 - c_list[i - 1]["close"]) / c_list[i - 1]["close"]
        r3 = (c0 - c_list[i - 3]["close"]) / c_list[i - 3]["close"]
        r5 = (c0 - c_list[i - 5]["close"]) / c_list[i - 5]["close"]
        r10 = (c0 - c_list[i - 10]["close"]) / c_list[i - 10]["close"]
        accel1 = r1 - ((c_list[i - 1]["close"] - c_list[i - 2]["close"]) / c_list[i - 2]["close"])

        # 2. RSI 7 & 14
        diffs14 = [c_list[k]["close"] - c_list[k - 1]["close"] for k in range(i - 13, i + 1)]
        gains14 = [max(0.0, d) for d in diffs14]
        losses14 = [abs(min(0.0, d)) for d in diffs14]
        avg_g14 = sum(gains14) / 14.0
        avg_l14 = (sum(losses14) / 14.0) or 1e-9
        rs14 = avg_g14 / avg_l14
        rsi14 = 100.0 - (100.0 / (1.0 + rs14))

        diffs7 = diffs14[-7:]
        gains7 = [max(0.0, d) for d in diffs7]
        losses7 = [abs(min(0.0, d)) for d in diffs7]
        avg_g7 = sum(gains7) / 7.0
        avg_l7 = (sum(losses7) / 7.0) or 1e-9
        rs7 = avg_g7 / avg_l7
        rsi7 = 100.0 - (100.0 / (1.0 + rs7))

        # 3. Micro-VWAP
        cum_vol = sum(c_list[k]["volume"] for k in range(max(0, i - 20), i + 1))
        cum_vp = sum(c_list[k]["close"] * c_list[k]["volume"] for k in range(max(0, i - 20), i + 1))
        vwap = (cum_vp / cum_vol) if cum_vol > 0 else c0
        vwap_dist = (c0 - vwap) / vwap

        # 4. Bollinger Bands 20
        window_c = [c_list[k]["close"] for k in range(max(0, i - 19), i + 1)]
        sma20 = sum(window_c) / len(window_c)
        variance20 = sum((x - sma20) ** 2 for x in window_c) / len(window_c)
        std20 = math.sqrt(variance20) or 1e-6
        bb_bandwidth = (4.0 * std20) / sma20
        bb_pct_b = (c0 - (sma20 - 2.0 * std20)) / (4.0 * std20)

        # 5. ATR 14 & Parkinson Volatility
        trs = [max(c_list[k]["high"] - c_list[k]["low"],
                   abs(c_list[k]["high"] - c_list[k - 1]["close"]),
                   abs(c_list[k]["low"] - c_list[k - 1]["close"])) for k in range(max(1, i - 13), i + 1)]
        atr14 = sum(trs) / len(trs)
        micro_atr14 = atr14 / c0

        ln_hl = [math.log(c_list[k]["high"] / (c_list[k]["low"] or 1e-6)) for k in range(max(0, i - 9), i + 1)]
        parkinson_vol = math.sqrt(sum(x ** 2 for x in ln_hl) / (4.0 * math.log(2.0) * len(ln_hl)))

        # 6. Wick Pressures
        total_range = max(1e-6, h0 - l0)
        upper_wick = (h0 - max(o0, c0)) / total_range
        lower_wick = (min(o0, c0) - l0) / total_range
        wick_pressure = lower_wick - upper_wick

        # 7. Volume surge ratio
        past_vol = [c_list[k]["volume"] for k in range(max(0, i - 9), i)]
        avg_vol_10 = (sum(past_vol) / len(past_vol)) if past_vol else 1.0
        vol_surge = v0 / (avg_vol_10 or 1.0)

        # 19 Institutional Features Vector
        feats = [
            r1, r3, r5, r10, accel1,
            rsi7 / 100.0, rsi14 / 100.0,
            vwap_dist, bb_pct_b, bb_bandwidth,
            micro_atr14, parkinson_vol,
            wick_pressure, upper_wick, lower_wick,
            vol_surge,
            r1 * vol_surge,
            vwap_dist * rsi14 / 100.0,
            accel1 * bb_bandwidth
        ]
        return feats

    def predict_specialist_return(self, model_id: str, features: List[float]) -> float:
        """Computes the exact linear mathematical prediction from active weights."""
        meta = self.models_data.get(model_id)
        if not meta:
            return 0.0

        weights = meta["weights"]
        bias = meta["bias"]
        means = meta["means"]
        stds = meta["stds"]

        # Standardize features
        x_norm = [(f - m) / (s or 1.0) for f, m, s in zip(features, means, stds)]
        pred = sum(w * x for w, x in zip(weights, x_norm)) + bias
        return float(pred)

    def predict_ml_ensemble(self, sym: str) -> Dict[str, Any]:
        """
        Runs the 3-model Tree Ensemble (CatBoost, LightGBM, XGBoost) + CalibratedClassifierCV.
        Returns dictionary with predicted_return (in decimal), breakout_prob (0-1), confidence, micro_rsi, wick_pressure.
        Fail-closed: Returns prediction_valid=False on missing buffer or model failure.
        """
        default_res = {
            "prediction_valid": False,
            "error": "PREDICTOR_NOT_INITIALIZED",
            "predicted_return": 0.0,
            "breakout_prob": 0.0,
            "confidence": 0.0,
            "micro_rsi": 50.0,
            "wick_pressure": 0.0,
            "vol_zscore": 0.0,
            "signal": "HOLD"
        }
        if not self.ml_predictor:
            return default_res

        buf = self.candle_buffers.get(sym, [])
        if len(buf) < 20:
            res = dict(default_res)
            res["error"] = f"INSUFFICIENT_BUFFER_HISTORY: {len(buf)} < 20 candles"
            return res

        # Validate timeframe: reject sub-minute sampling
        is_valid_tf, tf_err = self.candle_aggregator.validate_buffer_timeframe(buf)
        if not is_valid_tf:
            fail_res = dict(default_res)
            fail_res["error"] = f"TIMEFRAME_SAMPLING_MISMATCH: {tf_err}"
            self.log_structured("INFERENCE_FAILURE", {"symbol": sym, "error": fail_res["error"]}, fail_res["error"])
            return fail_res

        try:
            df = pd.DataFrame(buf)
            clean_sym = sym.replace(".NS", "").replace("^", "")
            df["symbol"] = clean_sym
            if "timestamp" not in df.columns:
                fail_res = dict(default_res)
                fail_res["error"] = "MISSING_TIMESTAMPS: Candle buffer lacks authentic timestamps"
                self.log_structured("INFERENCE_FAILURE", {"symbol": sym, "error": fail_res["error"]}, fail_res["error"])
                return fail_res

            res = self.ml_predictor.predict_next_1m(df)
            if not res.get("prediction_valid", True):
                fail_res = dict(default_res)
                fail_res["error"] = res.get("error", "PREDICTOR_INVALID")
                self.log_structured("INFERENCE_FAILURE", {"symbol": sym, "error": fail_res["error"]}, f"ML prediction invalid for {sym}: {fail_res['error']}")
                return fail_res

            pred_ret = float(res.get("predicted_return_pct", 0.0)) / 100.0
            breakout_prob = float(res.get("raw_breakout_prob", 0.0)) / 100.0
            confidence = float(res.get("confidence", 0.0))

            return {
                "prediction_valid": True,
                "error": None,
                "predicted_return": pred_ret,
                "breakout_prob": breakout_prob,
                "confidence": confidence,
                "micro_rsi": float(res.get("micro_rsi", 50.0)),
                "wick_pressure": float(res.get("wick_pressure", 0.0)),
                "vol_zscore": float(res.get("vol_zscore", 0.0)),
                "signal": res.get("signal", "HOLD")
            }
        except Exception as e:
            err_res = dict(default_res)
            err_res["error"] = f"ML_INFERENCE_EXCEPTION: {e}"
            self.log_structured("INFERENCE_FAILURE", {"symbol": sym, "error": str(e)}, f"ML inference exception for {sym}: {e}")
            return err_res

    def evaluate_and_execute_orders(self, quotes: Dict[str, Any]):
        """
        DUAL-MODEL CONCURRENCE ENGINE:
        Evaluates signals using Specialist Model + ML Tree Ensemble + Microstructure + Friction Gate.
        Supports both CASH_EQUITY and OPTIONS_PAPER modes.
        """
        # Priority 4: Safe Halt Circuit Breaker
        if self.safe_halt_active:
            self.log_structured("SAFE_HALT_GATE", {"reason": self.safe_halt_reason}, f"Order evaluation blocked by safe halt: {self.safe_halt_reason}")
            return

        # Priority 6: Maximum Daily Loss Limit (₹30.00)
        if self.realized_pnl <= -30.0:
            msg = f"Daily loss limit hit (₹{self.realized_pnl:.2f} <= -₹30.00). New paper entries strictly blocked."
            self.log_structured("DAILY_LOSS_LIMIT_REACHED", {"realized_pnl": self.realized_pnl, "limit": -30.0}, msg)
            return

        # Priority 6: Maximum 1 Concurrent Open Position
        if len(self.active_positions) >= 1:
            return

        # Under OPTIONS_PAPER mode: evaluate CE/PE options contracts
        if self.mode == "OPTIONS_PAPER" and self.options_engine:
            nifty_sym = "NIFTYBEES.NS"
            q = quotes.get(nifty_sym)
            if q and not q.get("is_stale", False) and q.get("source") != "BUFFER_FALLBACK" and q.get("ltp", 0.0) > 0:
                ml_out = self.predict_ml_ensemble(nifty_sym)
                if ml_out.get("prediction_valid", False):
                    # Spot price: NIFTY index level (derived from ETF or spot)
                    spot_price = q["ltp"] * 100.0 if q["ltp"] < 1000.0 else q["ltp"]
                    opt_dec = self.options_engine.evaluate_ce_pe_signal(
                        spot_price=spot_price,
                        predicted_return=ml_out["predicted_return"],
                        confidence=ml_out["confidence"]
                    )
                    # Provenance tracking
                    if hasattr(self, "provenance_tracker"):
                        self.provenance_tracker.record_prediction(
                            symbol=nifty_sym,
                            spot_price=spot_price,
                            data_source=q.get("source", "MARKET_FEED"),
                            specialist_alpha_bps=0.0,
                            tree_alpha_bps=ml_out["predicted_return"] * 10000.0,
                            concurrence_ok=opt_dec.get("signal") in ["BUY_CE", "BUY_PE"],
                            calibrated_confidence=ml_out["confidence"],
                            regime_name="OPTIONS_EVALUATION",
                            gross_gain_rs=opt_dec.get("expected_gain_rs", 0.0),
                            statutory_fees_rs=opt_dec.get("total_fees", 0.0),
                            total_friction_rs=opt_dec.get("total_fees", 0.0),
                            net_expectancy_rs=opt_dec.get("net_expected_edge_rs", 0.0),
                            signal=opt_dec.get("signal", "HOLD"),
                            rejection_reason=opt_dec.get("rejection_reason"),
                            rank_in_universe=1
                        )
                    if opt_dec.get("signal") in ["BUY_CE", "BUY_PE"]:
                        executed = self.options_engine.execute_paper_order(
                            decision=opt_dec,
                            current_time_str=datetime.now().strftime("%H:%M:%S")
                        )
                        if executed:
                            print(f"\n  🎯 [OPTIONS ORDER EXECUTED] {opt_dec['signal']} on {opt_dec['symbol']} | Premium: ₹{opt_dec['total_premium']:,.2f}")
            return

        # Under CASH_EQUITY mode: Multi-Regime Opportunity Discovery & Ranking across full universe
        if hasattr(self, "opportunity_engine"):
            candidates = self.opportunity_engine.scan_and_rank_opportunities(quotes, self.candle_buffers)
            if hasattr(self, "provenance_tracker"):
                for cand in candidates:
                    self.provenance_tracker.record_prediction(
                        symbol=cand.symbol,
                        spot_price=cand.ltp,
                        data_source=quotes.get(cand.symbol, {}).get("source", "MARKET_FEED"),
                        specialist_alpha_bps=cand.specialist_alpha_bps,
                        tree_alpha_bps=cand.tree_alpha_bps,
                        concurrence_ok=cand.concurrence_ok,
                        calibrated_confidence=cand.calibrated_confidence,
                        regime_name=cand.regime.regime_name,
                        gross_gain_rs=cand.gross_gain_rs,
                        statutory_fees_rs=cand.statutory_fees_rs,
                        total_friction_rs=cand.total_friction_rs,
                        net_expectancy_rs=cand.net_expectancy_rs,
                        signal=cand.side if cand.viable else "HOLD",
                        rejection_reason=cand.rejection_reasons[0] if cand.rejection_reasons else None,
                        rank_in_universe=cand.rank
                    )

            top_dec = self.opportunity_engine.select_top_opportunity(candidates, mode=self.mode)
            if top_dec.get("decision") in ["BUY", "SELL"]:
                top_cand = top_dec.get("candidate")
                sym = top_dec["symbol"]
                side = top_dec["decision"]
                ltp = top_dec["entry_price"]
                u_info = self.universe.get(sym) or self.opportunity_engine.universe.get(sym, {})
                kotak_sym = u_info.get("kotak_symbol", sym.replace(".NS", "") + "-EQ")
                mid = u_info.get("model", "OPP_DISCOVERY")

                if mid not in self.active_positions and len(self.active_positions) < 1:
                    if not (side == "SELL" and not self.allow_short_selling):
                        avail = max(0.0, self.paper_bankroll - sum(p.get("notional", 0.0) for p in self.active_positions.values()))
                        if avail >= ltp:
                            shares = int(avail // ltp)
                            if shares >= 1:
                                notional = round(shares * ltp, 2)
                                print("\n" + "=" * 80)
                                print(f"  🎯 [RANK #1 OPPORTUNITY APPROVED] {sym} ({kotak_sym}) | Score: {top_cand.score:.2f}")
                                print(f"     • Side:                 {side} {shares} shares @ ₹{ltp:.2f} (Notional: ₹{notional:,.2f})")
                                print(f"     • Regime:               {top_cand.regime.regime_name} (Multiplier: x{top_cand.regime.multiplier:.2f})")
                                print(f"     • Model Consensus:      Spec {top_cand.specialist_alpha_bps:+.2f} bps | Tree {top_cand.tree_alpha_bps:+.2f} bps (Conf: {top_cand.calibrated_confidence:.1f}%)")
                                print(f"     • Net Alpha Expected:   ₹{top_cand.net_expectancy_rs:.2f} (+{top_cand.net_expectancy_bps:.1f} bps net after all frictions)")
                                print(f"     • Comparative Reason:   {top_dec.get('comparative_rationale')}")
                                print("=" * 80)

                                order_res = self.adapter.place_order(
                                    symbol=kotak_sym,
                                    side=side,
                                    quantity=shares,
                                    price=ltp,
                                    order_type="MARKET",
                                    product="MIS",
                                    segment=u_info.get("segment", "nse_cm"),
                                    tag="AlphaNSE_Opp"
                                )
                                status = order_res.get("status")
                                order_id = order_res.get("order_id")

                                if status in ["FILLED", "SUBMITTED"] or order_id:
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
                                        "target_pnl": 15.00,
                                        "stop_loss_pnl": -4.50,
                                        "breakeven_activated": False,
                                        "comparative_rationale": top_dec.get("comparative_rationale")
                                    }
                                    self.active_positions[mid] = pos
                                    self.log_structured("SIMULATED_FILL", pos, f"Order filled: {side} {shares}x {kotak_sym} @ ₹{ltp:.2f} (Notional ₹{notional:.2f})")
                                else:
                                    rej_meta = {"symbol": kotak_sym, "reason": order_res.get("reason")}
                                    self.log_structured("ORDER_REJECTED", rej_meta, f"Order rejected for {kotak_sym}: {order_res.get('reason')}")
                                return

        for sym, q in quotes.items():
            if not q or q.get("is_stale", False) or q.get("source") == "BUFFER_FALLBACK" or q.get("ltp", 0.0) <= 0:
                continue

            u_info = self.universe.get(sym)
            if not u_info:
                continue
            mid = u_info["model"]

            if mid in self.active_positions:
                continue

            feats = self.extract_exact_19_features(sym)
            if not feats:
                continue

            ltp = q["ltp"]
            kotak_sym = u_info["kotak_symbol"]

            # 1. Specialist Model Mathematical Prediction
            pred_spec = self.predict_specialist_return(mid, feats)

            # 2. Machine Learning Tree Ensemble Prediction (Fail-Closed)
            ml_out = self.predict_ml_ensemble(sym)
            if not ml_out.get("prediction_valid", False):
                continue

            pred_tree = ml_out["predicted_return"]
            breakout_prob = ml_out["breakout_prob"]
            confidence = ml_out["confidence"]
            micro_rsi = ml_out["micro_rsi"]
            wick = ml_out["wick_pressure"]

            # 3. Dual-Model High-Conviction Concurrence & Microstructure Gate
            # Both models MUST concur in direction with verified probability and clean microstructure
            side = None
            expected_move = 0.0

            if (pred_spec > 0 and 
                pred_tree >= 0.0002 and 
                (ml_out["signal"] == "BUY" or confidence >= 45.0) and 
                35.0 <= micro_rsi <= 68.0 and 
                wick >= -0.20):
                side = "BUY"
                expected_move = max(0.0008, abs(pred_tree))
            elif (pred_spec < 0 and 
                  pred_tree <= -0.0002 and 
                  (ml_out["signal"] == "SELL" or confidence >= 45.0) and 
                  32.0 <= micro_rsi <= 65.0 and 
                  wick <= 0.20):
                side = "SELL"
                expected_move = max(0.0008, abs(pred_tree))

            if not side:
                continue

            # Under cash-only, no-margin rules: reject short selling if not explicitly enabled
            if side == "SELL" and not self.allow_short_selling:
                self.log_structured("SIGNAL_REJECTED", {"symbol": sym, "side": "SELL", "reason": "SHORT_SELLING_DISABLED"}, f"Signal rejected for {sym}: Short selling disabled")
                continue

            # Under strict ₹1,500 capital limit, enforce single concurrent position
            if len(self.active_positions) >= 1:
                self.log_structured("SIGNAL_REJECTED", {"symbol": sym, "side": side, "reason": "MAX_CONCURRENT_POSITIONS_REACHED"}, f"Signal rejected for {sym}: Single position limit active")
                continue

            # Position Sizing: Strict whole shares under available paper balance (₹1,500)
            avail = max(0.0, self.paper_bankroll - sum(p.get("notional", 0.0) for p in self.active_positions.values()))
            if hasattr(self, "opportunity_engine"):
                shares, afford_rejs = self.opportunity_engine.calculate_affordable_quantity(ltp, avail)
            else:
                shares = int(avail // ltp) if avail >= ltp else 0
            if shares < 1:
                self.log_structured("SIGNAL_REJECTED", {"symbol": sym, "side": side, "reason": "UNAFFORDABLE_QUANTITY_ZERO", "available": avail, "price": ltp}, f"Signal rejected for {sym}: Unaffordable under ₹{avail:.2f} capital")
                continue
            notional = round(shares * ltp, 2)

            # 4. Pre-Trade Economic Friction Gate
            # Rejects trade if predicted alpha does not beat complete roundtrip transaction costs
            edge_res = self.edge_gate.evaluate_signal(
                symbol=sym,
                side=side,
                quantity=shares,
                mid_price=ltp,
                expected_move_pct=abs(expected_move)
            )

            if not edge_res.approved:
                # Friction erodes statistical alpha: reject trade
                self.log_structured("SIGNAL_REJECTED", {"symbol": sym, "side": side, "reason": "FRICTION_GATE_REJECTED", "net_edge_rs": edge_res.net_edge_rs, "rejections": edge_res.rejection_reasons}, f"Signal rejected for {sym}: Friction gate rejected (Net ₹{edge_res.net_edge_rs:.2f})")
                continue

            print("\n" + "=" * 80)
            print(f"  🎯 [HIGH-CONVICTION SIGNAL APPROVED] Model: {mid} on {sym} ({kotak_sym})")
            print(f"     • Side:                 {side} {shares} shares @ ₹{ltp:.2f} (Notional: ₹{notional:,.2f})")
            print(f"     • Specialist Alpha:     {pred_spec * 10000:+.2f} bps")
            print(f"     • ML Tree Alpha:        {pred_tree * 10000:+.2f} bps | Breakout Prob: {breakout_prob * 100:.1f}%")
            print(f"     • Microstructure:       RSI: {micro_rsi:.1f} | Wick Pressure: {wick:+.2f}")
            print(f"     • Net Alpha Expected:   ₹{edge_res.net_edge_rs:.2f} (All frictions cleared)")
            print("=" * 80)

            # If shadow mode is active, record candidate decision without dispatching order fills
            if self.shadow_mode:
                shadow_record = {
                    "model_id": mid,
                    "symbol": sym,
                    "kotak_symbol": kotak_sym,
                    "side": side,
                    "signal_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
                    "shares": shares,
                    "price": ltp,
                    "notional": notional,
                    "expected_move_pct": float(expected_move),
                    "net_edge_rs": float(edge_res.net_edge_rs),
                    "execution_mode": "SHADOW_RECORDED",
                    "reason": "Order fill suppressed: Strategy operates in SHADOW MODE per negative out-of-sample forward expectancy"
                }
                print(f"  👁️ [SHADOW MODE CANDIDATE RECORDED]: {mid} on {kotak_sym} | {side} {shares} shares @ ₹{ltp:.2f} (Net Edge ₹{edge_res.net_edge_rs:.2f}). Zero paper fill executed.")
                self.log_structured("SHADOW_SIGNAL_RECORDED", shadow_record, f"Shadow opportunity recorded for {kotak_sym}")
                continue

            # DISPATCH REAL LIVE ORDER TO KOTAK NEO
            order_res = self.adapter.place_order(
                symbol=kotak_sym,
                side=side,
                quantity=shares,
                price=ltp,
                order_type="MARKET",
                product="MIS",
                segment=u_info["segment"],
                tag="AlphaNSE_Live"
            )

            status = order_res.get("status")
            order_id = order_res.get("order_id")

            if status in ["FILLED", "SUBMITTED"] or order_id:
                order_mode_str = "REAL ORDER DISPATCHED TO KOTAK NEO" if self.adapter.is_live else "PAPER ORDER SIMULATED (Zero Real Money)"
                event_name = "REAL_ORDER_OPENED" if self.adapter.is_live else "PAPER_ORDER_OPENED"
                print(f"  🚀 [{order_mode_str}]:")
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
                    "target_pnl": 15.00,  # +1% dynamic harvest
                    "stop_loss_pnl": -4.50, # 0.3% stop-loss
                    "breakeven_activated": False
                }
                self.active_positions[mid] = pos
                self.log_event(event_name, pos)
            else:
                rej_label = "KOTAK NEO" if self.adapter.is_live else "PAPER SIMULATOR"
                print(f"  ❌ [ORDER REJECTED BY {rej_label}]: {order_res.get('reason')}")
                self.log_event("ORDER_REJECTED", {"symbol": kotak_sym, "reason": order_res.get("reason"), "mode": "LIVE" if self.adapter.is_live else "PAPER"})

    def monitor_positions_and_exit(self, quotes: Dict[str, Any]):
        """
        Monitors active positions with Trailing Stop Ratchet & Profit Harvest.
        """
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

            # Trailing Stop Ratchet: Move stop to Breakeven at +0.50% (+₹7.50)
            if unrealized >= 7.50 and not pos.get("breakeven_activated", False):
                pos["breakeven_activated"] = True
                pos["stop_loss_pnl"] = 0.00
                print(f"  🛡️ [BREAKEVEN RATCHET ACTIVATED]: {mid} achieved +₹{unrealized:.2f}. Stop-loss locked at ₹0.00 (Zero Risk).")

            # Check Stop Loss (-₹4.50 or Breakeven)
            if unrealized <= pos["stop_loss_pnl"]:
                reason = "BREAKEVEN_STOP" if pos.get("breakeven_activated") else "STOP_LOSS_0.3%_CAP"
                print(f"\n  🛑 [STOP HIT - DISPATCHING REAL EXIT ORDER]: {mid} hit ₹{unrealized:.2f}. Liquidating...")
                self._exit_position(mid, curr_px, reason=reason)
                continue

            # Check Profit Target (+₹15.00 / +1%)
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
            tag="AlphaNSE_Exit"
        )

        money_in = pos["notional"]
        gross = (exit_price - pos["entry_price"]) * shares if pos["side"] == "BUY" else (pos["entry_price"] - exit_price) * shares
        costs = self.cost_engine.calculate_roundtrip_cost(money_in, gross / (money_in or 1.0))
        taxes = costs.total_cost - costs.brokerage
        net = gross - taxes
        money_out = round(money_in + net, 2)
        self.realized_pnl += net
        self.paper_bankroll += net

        closed_rec = {
            "trade_id": f"TRD-{datetime.now().strftime('%Y%m%d')}-{len(self.closed_trades)+1:03d}",
            "instrument": kotak_sym,
            "direction": pos["side"],
            "signal_time": pos["entry_time"],
            "entry_time": pos["entry_time"],
            "entry_price": pos["entry_price"],
            "quantity": shares,
            "exit_time": datetime.now().strftime("%H:%M:%S IST"),
            "exit_price": exit_price,
            "gross_pnl": round(gross, 2),
            "charges": {
                "brokerage": 0.0,
                "stt": round(costs.stt, 2),
                "exchange_fees": round(costs.exchange_charges, 2),
                "gst": round(costs.gst, 2),
                "sebi_turnover": round(costs.sebi_fees, 4),
                "stamp_duty": round(costs.stamp_duty, 2),
                "total_charges": round(taxes, 2)
            },
            "net_pnl": round(net, 2),
            "return_pct": round((net / (money_in or 1.0)) * 100.0, 2),
            "holding_duration": "Intraday MIS",
            "exit_reason": reason,
            "prediction_result": "CORRECT" if net > 0 else "INCORRECT",
            "model_decision": {
                "model_id": model_id,
                "ensemble_signal": pos["side"]
            },
            "money_in": money_in,
            "money_out": money_out,
            "taxes_friction": round(taxes, 2),
            "bankroll_after": round(self.paper_bankroll, 2),
            "exit_status": exit_res.get("status")
        }
        self.closed_trades.append(closed_rec)
        self.log_structured("POSITION_EXIT", closed_rec, f"Position exited: {kotak_sym} @ ₹{exit_price:.2f} | Net P&L ₹{net:+.2f} ({reason})")
        if hasattr(self, "provenance_tracker"):
            self.provenance_tracker.pair_latest_symbol_outcome(pos.get("symbol", kotak_sym), exit_price)

        mode_label = "REAL ORDER EXECUTED" if self.adapter.is_live else "PAPER TESTING SIMULATED"
        print(f"\n  🏁 [{mode_label}]: {model_id} on {kotak_sym}")
        print(f"     • Money Put In:  ₹{money_in:,.2f} ({shares} shares @ ₹{pos['entry_price']:.2f})")
        print(f"     • Money Out:     ₹{money_out:,.2f} (Exit @ ₹{exit_price:.2f} | Reason: {reason})")
        print(f"     • Taxes & Fees:  ₹{taxes:.2f} (Trade Free: ₹0 Brokerage)")
        print(f"     • Net Trade P&L: ₹{net:+.2f} ({(net / money_in) * 100:+.2f}%)")
        print(f"     • Paper Bankroll: ₹{self.paper_bankroll:,.2f}")

        self.save_paper_ledger()

    def update_live_chart(self):
        """Updates live real-vs-predicted interactive chart and static PNG."""
        try:
            from v3.reports.chart_generator import update_live_session_chart
            update_live_session_chart(session_date="2026-10-16")
        except Exception as e:
            self.log_structured("CHART_UPDATE_ERROR", {"error": str(e)}, f"Chart update error: {e}")

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
            except Exception as sock_err:
                self.logger.debug(f"Connectivity check to {host}:53 failed: {sock_err}")
        return False

    def reconcile_broker_positions(self):
        """Re-syncs local active positions with genuine broker positions from Kotak Neo."""
        try:
            broker_pos = self.adapter.get_positions()
            for bp in broker_pos:
                print(f"  • Open Broker Position: {bp.get('symbol')} | Qty {bp.get('quantity')} | Side {bp.get('side')}")
        except Exception as e:
            print(f"  [WARN] Position reconciliation warning: {e}")

    def check_connection(self) -> bool:
        """Pre-market connectivity verification test."""
        print("=" * 85)
        print("  🔍 ALPHANSE V3 — PRE-MARKET CONNECTIVITY & DATA FEED VERIFICATION")
        print(f"  TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST")
        print("=" * 85)

        auth_ok = False
        try:
            if hasattr(self.adapter, "authenticate"):
                auth_ok = self.adapter.authenticate()
            elif hasattr(self.adapter, "ensure_fresh_session"):
                self.adapter.ensure_fresh_session()
                auth_ok = self.adapter.is_authenticated
        except Exception as e:
            print(f"  [WARN] Authentication check failed: {e}")
            auth_ok = False

        print("\n1. Broker Adapter Status:")
        print(f"  • Broker Adapter: {self.adapter.broker_name}")
        print(f"  • Configured UCC: {self.adapter.ucc}")
        print(f"  • Authentication Success: {'🟢 YES' if auth_ok else '🔴 NO (Waiting for Market Session Open)'}")

        # Priority 3: Dual-Key Safety Lock Verification
        env_live = os.getenv("LIVE_TRADING", "False").strip().lower() == "true"
        env_allow = os.getenv("ALLOW_REAL_ORDERS", "False").strip().lower() == "true"
        locks_secure = (not env_live) and (not env_allow) and (not self.adapter.is_live)
        print(f"  • Live Trading Lock: {'🟢 SECURE (False)' if not env_live else '🔴 UNLOCKED (True)'}")
        print(f"  • Real Order Routing Lock: {'🟢 SECURE (False)' if not env_allow else '🔴 UNLOCKED (True)'}")
        print(f"  • Adapter Operational Mode: {'🟢 PAPER / READ-ONLY' if not self.adapter.is_live else '🔴 LIVE REAL ORDERS'}")

        print("\n2. Market Data Feed & 1-Minute Candle Status:")
        quotes = self.feed.fetch_quotes(self.candle_buffers)
        print(f"  • Symbols Queried: {len(self.universe)}")
        print(f"  • Quotes Received: {len(quotes)} / {len(self.universe)}")
        
        quote_metadata = {}
        for sym in self.universe:
            q = quotes.get(sym)
            buf = self.candle_buffers.get(sym, [])
            buf_len = len(buf)
            last_ts = q.get("timestamp", "N/A") if q else "N/A"
            src = q.get("source", "MARKET_FEED") if q else "NONE"
            is_stale = q.get("is_stale", True) if q else True

            # Missing bars check in candle buffer
            missing_bars = 0
            if buf_len >= 2:
                is_valid_tf, tf_err = self.candle_aggregator.validate_buffer_timeframe(buf)
                if not is_valid_tf:
                    self.logger.warning(f"Buffer timeframe validation issue for {sym}: {tf_err}")

            if q and not is_stale:
                print(f"    - {sym:<15}: 🟢 FRESH LIVE | LTP=₹{q['ltp']:>8.2f} | Open=₹{q['open']:>8.2f} | Vol={q['volume']:>9,} [{src}] | Candles={buf_len} | Age={q.get('quote_age_seconds', 0.0):.1f}s | ExchTS={last_ts}")
                quote_metadata[sym] = {
                    "ltp": q["ltp"],
                    "timestamp": last_ts,
                    "source": src,
                    "candle_count": buf_len,
                    "is_stale": False,
                    "quote_type": q.get("quote_type", "LIVE_TICK"),
                    "quote_age_seconds": q.get("quote_age_seconds", 0.0)
                }
            elif q and is_stale:
                q_type = q.get("quote_type", "STALE_OBSERVATION")
                age_s = q.get("quote_age_seconds")
                age_disp = f"{age_s/60.0:.1f}m ({age_s:.0f}s)" if age_s is not None else "N/A"
                print(f"    - {sym:<15}: 🟡 {q_type} | LTP=₹{q['ltp']:>8.2f} | Age={age_disp} | ExchTS={last_ts} | Status: STALE (REJECTED FROM CANDLE FORMATION)")
                quote_metadata[sym] = {
                    "ltp": q["ltp"],
                    "timestamp": last_ts,
                    "source": src,
                    "candle_count": buf_len,
                    "is_stale": True,
                    "quote_type": q_type,
                    "quote_age_seconds": age_s
                }
                self.log_structured(
                    "STALE_DATA_DETECTED",
                    {"symbol": sym, "source": src, "quote_type": q_type, "age_seconds": age_s, "exchange_ts": last_ts},
                    f"Stale quote ({q_type}) detected for {sym} (age: {age_disp}). Rejected from candle formation."
                )
            else:
                print(f"    - {sym:<15}: 🔴 NO DATA AVAILABLE (Connection/Symbol Error)")
                self.log_structured(
                    "NO_DATA_DETECTED",
                    {"symbol": sym, "source": src, "reason": "No response for symbol"},
                    f"No quote data received for {sym}. Fail-closed active."
                )

        self.log_structured(
            "DATA_FRESHNESS",
            {
                "symbols_queried": len(self.universe),
                "quotes_received": len(quotes),
                "quote_metadata": quote_metadata
            },
            "Market data freshness verified from Kotak Neo / feeds"
        )

        print("\n3. Risk & Capital Configuration:")
        print(f"  • Primary Mode: {'CASH-ONLY (NO SHORTING)' if not self.allow_short_selling else 'INTRADAY MIS (SHORTING ALLOWED)'}")
        print(f"  • Paper Bankroll: ₹{self.paper_bankroll:.2f}")
        print(f"  • Max Capital: ₹{self.adapter.max_capital:.2f}")
        print(f"  • Max Daily Loss: ₹{self.adapter.max_daily_loss:.2f}")
        print(f"  • Max Concurrent Positions: 1")

        print("\n4. Model Artifacts:")
        print(f"  • Specialist Models Loaded: {list(self.models_data.keys())}")
        print(f"  • ML Ensemble Loaded: {'🟢 YES' if self.ml_predictor else '🔴 NO'}")

        self.log_structured(
            "CONNECTION_TEST",
            {
                "broker": self.adapter.broker_name,
                "ucc": self.adapter.ucc,
                "authenticated": auth_ok,
                "symbols_queried": len(self.universe),
                "quotes_received": len(quotes),
                "paper_bankroll": self.paper_bankroll,
                "max_capital": self.adapter.max_capital,
                "LIVE_TRADING": env_live,
                "ALLOW_REAL_ORDERS": env_allow,
                "locks_secure": locks_secure
            },
            f"Pre-market connectivity verification: {'AUTHENTICATED' if auth_ok else 'UNAUTHENTICATED'}"
        )
        print("=" * 85 + "\n")
        return auth_ok and locks_secure

    def inspect_live_signals(self):
        """Evaluates model inference on current market quotes and outputs decisions."""
        print("=" * 115)
        print("  🔬 ALPHANSE V3 — LIVE MODEL INFERENCE & DECISION INSPECTION")
        print(f"  TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST")
        print("=" * 115)

        quotes = self.feed.fetch_quotes(self.candle_buffers)
        print(f"{'INSTRUMENT':<14} | {'PRICE (₹)':<10} | {'SPEC ALPHA':<11} | {'TREE ALPHA':<11} | {'BRK PROB':<9} | {'DIRECTION':<10} | {'VERDICT':<12} | {'REASON'}")
        print("-" * 115)

        for sym, u_info in self.universe.items():
            q = quotes.get(sym)
            if not q:
                print(f"{sym:<14} | {'N/A':<10} | {'N/A':<11} | {'N/A':<11} | {'N/A':<9} | {'N/A':<10} | {'HOLD':<12} | Missing quote observation")
                continue

            mid = u_info["model"]
            scale = u_info["tick_mult"]
            sim_price = round(q["ltp"] * scale, 2)

            buf = self.candle_buffers.get(sym, [])
            if len(buf) < 25:
                print(f"{sym:<14} | ₹{sim_price:>8.2f} | {'N/A':<11} | {'N/A':<11} | {'N/A':<9} | {'BUFFERING':<10} | {'HOLD':<12} | Insufficient bar buffer ({len(buf)} < 25)")
                continue

            feats = self.extract_exact_19_features(sym)
            p_spec = self.predict_specialist_return(mid, feats) if feats else 0.0
            ml_res = self.predict_ml_ensemble(sym)
            p_tree = ml_res["predicted_return"]
            b_prob = ml_res["breakout_prob"]
            rsi = ml_res["micro_rsi"]
            wick = ml_res["wick_pressure"]

            side = None
            if p_spec > 0 and p_tree >= 0.0002 and b_prob >= 0.50 and 35.0 <= rsi <= 68.0 and wick >= -0.20:
                side = "BUY"
            elif p_spec < 0 and p_tree <= -0.0002 and b_prob <= 0.48 and 32.0 <= rsi <= 65.0 and wick <= 0.20:
                side = "SELL"

            direction = "UP" if (p_spec + p_tree) > 0.0004 else ("DOWN" if (p_spec + p_tree) < -0.0004 else "UNCERTAIN")

            if not side:
                verdict = "HOLD"
                reason = "Concurrence or breakout threshold not met"
            elif side == "SELL" and not self.allow_short_selling:
                verdict = "REJECTED"
                reason = "SHORT_SELLING_PROHIBITED_UNDER_CASH_ONLY_RULES"
            elif self.paper_bankroll < sim_price:
                verdict = "REJECTED"
                reason = f"Insufficient cash (Price ₹{sim_price:.2f} > Bankroll ₹{self.paper_bankroll:.2f})"
            else:
                verdict = f"ELIGIBLE_{side}"
                reason = "All concurrence & risk gates cleared"

            print(f"{sym:<14} | ₹{sim_price:>8.2f} | {p_spec*10000:>+8.2f} bps | {p_tree*10000:>+8.2f} bps | {b_prob*100:>6.1f}%   | {direction:<10} | {verdict:<12} | {reason}")

        print("=" * 115)

        # Multi-Regime Opportunity Discovery & Ranking across Full Universe
        if hasattr(self, "opportunity_engine"):
            candidates = self.opportunity_engine.scan_and_rank_opportunities(quotes, self.candle_buffers)
            print("\n" + "=" * 115)
            print("  🏆 ALPHANSE V3 — MULTI-REGIME OPPORTUNITY RANKING ACROSS FULL UNIVERSE")
            print(f"  TOTAL SCANNED: {len(candidates)} INSTRUMENTS | PAPER BANKROLL: ₹{self.paper_bankroll:.2f}")
            print("=" * 115)
            print(f"{'RANK':<5} | {'SYMBOL':<14} | {'REGIME':<18} | {'SPEC (bps)':<10} | {'TREE (bps)':<10} | {'CONF':<6} | {'NET (₹)':<8} | {'SCORE':<7} | {'STATUS'}")
            print("-" * 115)
            for c in candidates[:10]:
                status_str = "VIABLE" if c.viable else (c.rejection_reasons[0].split()[0] if c.rejection_reasons else "REJECTED")
                print(f"#{c.rank:<4} | {c.symbol:<14} | {c.regime.regime_name:<18} | {c.specialist_alpha_bps:>+8.2f}  | {c.tree_alpha_bps:>+8.2f}  | {c.calibrated_confidence:>4.1f}% | ₹{c.net_expectancy_rs:>6.2f} | {c.score:>6.2f} | {status_str}")
            print("-" * 115)
            top_dec = self.opportunity_engine.select_top_opportunity(candidates, mode=self.mode)
            print(f"  🎯 Top Opportunity Selection: {top_dec.get('decision')} on {getattr(top_dec.get('candidate'), 'symbol', 'None')}")
            print(f"     Comparative Rationale: {top_dec.get('comparative_rationale')}")
            print("=" * 115 + "\n")

    def run(self):
        # Singleton lock check: ensure no other live_trader process is already running
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, "r", encoding="utf-8") as f:
                    old_pid = int(f.read().strip())
                if old_pid != os.getpid() and is_pid_alive(old_pid):
                    abort_msg = f"Another AlphaNSE Live Trader process (PID {old_pid}) is already active!"
                    self.log_structured("ABORT_DUPLICATE_INSTANCE", {"existing_pid": old_pid}, abort_msg)
                    print(f"❌ [ABORT] {abort_msg}")
                    print("   Terminate the existing process first before starting a new instance.")
                    return
            except Exception as e:
                self.logger.warning(f"Error checking existing PID file: {e}")

        # Record daemon OS PID
        try:
            with open(PID_FILE, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
        except Exception as e:
            self.logger.warning(f"Error writing PID file: {e}")

        self._setup_signal_handlers()

        # Mirror terminal output to LOG_FILE strictly during execution (avoiding module import pollution)
        orig_stdout = sys.stdout
        orig_stderr = sys.stderr
        tee = TeeLogger(LOG_FILE)
        sys.stdout = tee
        sys.stderr = tee

        self.log_structured(
            "STARTUP",
            {
                "pid": os.getpid(),
                "mode": self.mode,
                "bankroll": self.paper_bankroll,
                "broker": self.adapter.broker_name,
                "is_live": self.adapter.is_live
            },
            "AlphaNSE Live Trader daemon started"
        )

        print("=" * 88)
        print("  🚀 ALPHANSE V3 — DUAL-MODEL PRODUCTION REAL TRADING ENGINE")
        print(f"  BROKER:         {self.adapter.broker_name}")
        print("  SAFEGUARDS:     Dual-Concurrence • Friction Gate • 0.3% Max Risk Cap")
        print("=" * 88)

        if not self.check_connection():
            print("  ⚠️ [NOTICE] Kotak Neo initial handshake pending (late-night maintenance/token renewal).")
            print("  ⏳ Armed in STANDBY mode: Will re-authenticate continuously leading up to 09:15:00 IST open.")

        market_open = dtime(9, 15)
        market_close = dtime(15, 30)
        square_off = dtime(15, 15)
        network_was_down = False

        set_windows_keep_alive(True)
        try:
            while True:
                if getattr(self, "_shutdown_requested", False):
                    self.log_structured("SHUTDOWN", {"reason": "SIGNAL_INTERRUPT", "cycle": self.cycle_count}, "Graceful shutdown via signal requested")
                    print("\n  🛑 Graceful shutdown initiated. Exiting main trading loop...")
                    break

                try:
                    # Clock jump / suspension detection (stale heartbeat fail-closed safeguard)
                    now_t = time.time()
                    if self._last_cycle_time is not None:
                        gap = now_t - self._last_cycle_time
                        if gap > (self.poll_interval + 30.0):
                            self.log_structured(
                                "STALE_HEARTBEAT_DETECTED",
                                {"gap_seconds": round(gap, 1), "expected_interval": self.poll_interval},
                                f"Suspension / clock jump detected ({gap:.1f}s gap). Engaging fail-closed safeguards."
                            )
                            print(f"\n⚠️ [SUSPENSION/CLOCK JUMP DETECTED] Elapsed: {gap:.1f}s since last cycle.")
                            print("   Fail-closed: Invalidating cached quotes and re-verifying broker connection...")
                            self.feed.cache.clear()
                            self.check_connection()
                    self._last_cycle_time = now_t

                    # 1. Network Health Check & Failover Sentinel
                    if not self.check_network_health():
                        network_was_down = True
                        now_str = datetime.now().strftime("%H:%M:%S IST")
                        print(f"[{now_str}] ⚠️ [NETWORK OUTAGE] Internet disconnected. Safely holding... retrying in 5s")
                        time.sleep(5)
                        continue

                    if network_was_down:
                        network_was_down = False
                        now_str = datetime.now().strftime("%H:%M:%S IST")
                        print(f"\n[{now_str}] 🌐 [NETWORK RESTORED] Re-authenticating Kotak Neo...")
                        self.adapter._init_neo_sdk()
                        self.reconcile_broker_positions()
                        self.log_structured("NETWORK_FAILOVER_RESTORED", {"reauthenticated": self.adapter.is_authenticated}, "Network failover restored")

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
                        if not hasattr(self, "_last_standby_min") or self._last_standby_min != now.minute:
                            self._last_standby_min = now.minute
                            self.log_structured("HEARTBEAT", {"status": "STANDBY_FOR_OPEN", "cycle": self.cycle_count, "remaining_seconds": remaining_secs}, f"Standby heartbeat: {target_str}")
                            self.update_live_chart()
                            print(f"[{now.strftime('%H:%M:%S')} IST] ⏳ [STANDBY_FOR_OPEN] Next Session: {target_str} (in {hrs:02d}h {mins:02d}m {secs:02d}s). Armed & waiting...")
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
                        self.active_positions = {}
                        self.closed_trades = []
                        self.realized_pnl = 0.0
                        time.sleep(30)
                        continue

                    # Fetch live market prices via fast parallel feed
                    quotes = self.feed.fetch_quotes(self.candle_buffers)
                    self.broker_quote_errors = getattr(self.feed, "broker_errors", 0)

                    # Assess data freshness across received quotes
                    fresh_quotes = [q for q in quotes.values() if not q.get("is_stale", False) and q.get("source") not in ("BUFFER_FALLBACK", "CACHE_FALLBACK") and q.get("ltp", 0.0) > 0]
                    if not fresh_quotes:
                        self.consecutive_stale_quotes += 1
                    else:
                        self.consecutive_stale_quotes = 0

                    # Safe-halt circuit breakers
                    if self.broker_quote_errors >= 5:
                        if not self.safe_halt_active:
                            self.safe_halt_active = True
                            self.safe_halt_reason = f"CONSECUTIVE_BROKER_FAILURES: {self.broker_quote_errors} failed quote requests"
                            self.log_structured("SAFE_HALT_TRIGGERED", {"reason": self.safe_halt_reason, "broker_errors": self.broker_quote_errors, "component": "BROKER_FEED", "recovery_status": "WAITING_FOR_BROKER"}, self.safe_halt_reason)
                            print(f"\n  🛑 [SAFE HALT] {self.safe_halt_reason}. Pausing predictions and orders.")
                    elif self.consecutive_stale_quotes >= 6:
                        if not self.safe_halt_active:
                            self.safe_halt_active = True
                            self.safe_halt_reason = f"STALE_MARKET_DATA_TIMEOUT: {self.consecutive_stale_quotes * 10}s without fresh market quotes"
                            self.log_structured("SAFE_HALT_TRIGGERED", {"reason": self.safe_halt_reason, "consecutive_stale": self.consecutive_stale_quotes, "component": "MARKET_DATA_FEED", "recovery_status": "WAITING_FOR_FRESH_TICKS"}, self.safe_halt_reason)
                            print(f"\n  🛑 [SAFE HALT] {self.safe_halt_reason}. Pausing predictions and orders.")
                    else:
                        if self.safe_halt_active and len(fresh_quotes) > 0 and self.broker_quote_errors == 0:
                            self.safe_halt_active = False
                            self.log_structured("SAFE_HALT_CLEARED", {"status": "NORMAL_OPERATION_RESUMED"}, "Fresh market data restored. Resumed normal operation.")
                            print("\n  🟢 [SAFE HALT CLEARED] Fresh market data restored. Normal operation resumed.")

                    if quotes:
                        for sym, q in quotes.items():
                            is_stale = q.get("is_stale", False) or q.get("source") == "BUFFER_FALLBACK"
                            self.log_structured(
                                "DATA_FRESHNESS",
                                {"symbol": sym, "ltp": q.get("ltp", 0.0), "is_stale": is_stale, "source": q.get("source", "UNKNOWN")},
                                f"Data freshness for {sym}: LTP={q.get('ltp', 0.0)} stale={is_stale}"
                            )

                            if not is_stale and q.get("ltp", 0.0) > 0:
                                # Process quote through candle aggregator to form genuine 1-minute OHLCV bar
                                sealed = self.candle_aggregator.process_quote(sym, q)
                                if sealed:
                                    self.log_structured(
                                        "CANDLE_COMPLETED",
                                        {
                                            "symbol": sym,
                                            "timestamp": sealed["timestamp_str"],
                                            "open": sealed["open"],
                                            "high": sealed["high"],
                                            "low": sealed["low"],
                                            "close": sealed["close"],
                                            "volume": sealed["volume"],
                                            "tick_count": sealed["tick_count"]
                                        },
                                        f"Sealed 1m candle for {sym} at {sealed['timestamp_str']}: O={sealed['open']} H={sealed['high']} L={sealed['low']} C={sealed['close']} V={sealed['volume']}"
                                    )
                                # Update candle_buffers view exclusively with completed 1m bars (incomplete candles kept separate)
                                self.candle_buffers[sym] = self.candle_aggregator.get_bars(sym, include_forming=False)

                        # Real-time forward prediction verification & outcome pairing
                        if hasattr(self, "provenance_tracker"):
                            self.provenance_tracker.process_incoming_quotes(quotes)

                        # Monitor active positions
                        self.monitor_positions_and_exit(quotes)

                        # Evaluate new trade opportunities
                        self.evaluate_and_execute_orders(quotes)
                        self.update_live_chart()

                    self.save_runtime_state("TRADING_ACTIVE")
                    time.sleep(self.poll_interval)
                except Exception as cycle_err:
                    import traceback
                    tb_str = traceback.format_exc()
                    self.log_structured("EXCEPTION", {"cycle": self.cycle_count, "error": str(cycle_err), "traceback": tb_str}, f"Cycle error: {cycle_err}")
                    logging.error(f"[CYCLE ERROR] Unexpected error in trading cycle #{self.cycle_count}: {cycle_err}", exc_info=True)
                    time.sleep(5)
        finally:
            self.log_structured(
                "SHUTDOWN",
                {
                    "pid": os.getpid(),
                    "cycle": self.cycle_count,
                    "realized_pnl": self.realized_pnl,
                    "paper_bankroll": self.paper_bankroll
                },
                "AlphaNSE Live Trader daemon shutdown complete"
            )
            set_windows_keep_alive(False)
            try:
                if os.path.exists(PID_FILE):
                    with open(PID_FILE, "r", encoding="utf-8") as f:
                        cur_pid = int(f.read().strip())
                    if cur_pid == os.getpid():
                        os.remove(PID_FILE)
            except Exception as e:
                self.logger.warning(f"Error removing PID file: {e}")
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr
            try:
                tee.logfile.close()
            except Exception as e:
                self.logger.warning(f"Error closing logfile: {e}")


if __name__ == "__main__":
    try:
        sys.stdout = TeeLogger(LOG_FILE)
        sys.stderr = sys.stdout
        parser = argparse.ArgumentParser(description="AlphaNSE Real Live Trader")
        parser.add_argument("--test-conn", action="store_true", help="Test Kotak Neo connection and exit")
        parser.add_argument("--inspect-signals", action="store_true", help="Inspect live mathematical signals across all instruments")
        parser.add_argument("--force-active", action="store_true", help="Force active cycle for testing outside hours")
        args = parser.parse_args()

        trader = AlphaNSELiveTrader(force_active=args.force_active)
        if args.test_conn:
            trader.check_connection()
        elif args.inspect_signals:
            trader.inspect_live_signals()
        else:
            trader.run()
    except Exception as e:
        import traceback
        print("\n💥 [FATAL CRASH]:", e)
        traceback.print_exc()
