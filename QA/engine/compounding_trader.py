"""
Compounding Automated Trading Engine for Indian Stock Market (NSE).

- Evaluates 1-minute price predictions for top liquid NSE stocks.
- Enters trades when predicted 1-minute profit > 0.8% (configurable).
- Aims for 10 to 15+ trades per day.
- Reinvests all realized profits for geometric compounding.
- Supports manual money adjustments (deposit, withdraw, re-base capital).
- Real Indian market tax & fee accounting via IndiaTaxEngine.
- Dual execution: Live NSE market scanning + 1-Minute Replay Simulation.
"""

import os
import sys
import json
import time
import threading
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import yfinance as yf

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from QA.risk.india_tax_engine import IndiaTaxEngine
except ImportError:
    from risk.india_tax_engine import IndiaTaxEngine

try:
    from QA.stocks_config import STOCK_SYMBOLS, STOCK_UNIVERSE, DEFAULT_CAPITAL, STOCK_BLACKLIST
    from QA.models.one_min_predictor import OneMinPredictor
    from QA.models.stock_confidence_tracker import StockConfidenceTracker
    from QA.regimes.regime_classifier import classify_micro_regime
except ImportError:
    from stocks_config import STOCK_SYMBOLS, STOCK_UNIVERSE, DEFAULT_CAPITAL, STOCK_BLACKLIST
    from models.one_min_predictor import OneMinPredictor
    from models.stock_confidence_tracker import StockConfidenceTracker
    from regimes.regime_classifier import classify_micro_regime

STATE_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(STATE_DIR, exist_ok=True)
STATE_FILE = os.path.join(STATE_DIR, "compounding_state.json")
TRADE_LOG_FILE = os.path.join(STATE_DIR, "compounding_trades.jsonl")


class CompoundingTrader:
    """Manages 1-minute stock prediction, order execution, money adjustments, and daily compounding."""

    def __init__(self, starting_capital: float = 100000.0):
        self.tax_engine = IndiaTaxEngine()
        self.predictor = OneMinPredictor()
        self.confidence_tracker = StockConfidenceTracker()
        self.stock_blacklist = set(STOCK_BLACKLIST)
        self.lock = threading.RLock()
        self.is_running = False
        self.worker_thread = None
        self.subscribers = []  # WebSocket callbacks

        # Strategy parameters - Calibrated for 100% Own-Capital Spot Compounding (Zero Leverage)
        # SIMULATION v2 RESULT: Single trade needs 7.18% gross OR two trades 3.5%+4.0% gross to hit 5% net account
        self.target_session_profit_pct = 0.05 # 5.0% session net profit target (Daily Compounding Lock)
        self.take_profit_target_pct = 0.035   # 3.5% net profit take-profit hurdle (per trade exit target)
        self.profit_threshold_pct = 0.0010    # 0.10% (10 bps) predicted 1-minute hurdle (entry signal trigger)
        self.stop_loss_pct = 0.007            # 0.7% stop loss (Reward-to-Risk = 5.0 : 1)
        self.trailing_stop_activation_pct = 0.015 # At +1.5% gain, activate dynamic trailing stop
        self.trailing_stop_lock_pct = 0.005   # Lock in +0.5% net minimum (above friction) when trailing triggers
        self.position_sizing_pct = 0.95       # 95% single-runner concentration for full capital deployment
        self.max_concurrent_positions = 1     # 1 concentrated high-conviction runner at a time (no idle cash drag)
        self.max_hold_seconds = 7200          # 120 minutes (2hrs) max holding — wider window for 3.5-7% swings
        self.target_daily_trades = 2          # Max 2 high-conviction trades per session (less churn)
        self.simulation_speed_sec = 2.0       # Candle tick frequency in simulation mode
        self.off_market_simulation = False    # By default, do NOT simulate ticks when NSE is closed; freeze in standby

        # Cache for stock candles & anti-churn cooldown
        self.candles_cache = {}
        self.pending_predictions = {}
        self.last_exit_times = {}             # symbol -> datetime of last exit for 5m cooldown

        self._load_or_init_state(starting_capital)

    def _load_or_init_state(self, starting_capital: float):
        """Load state from JSON or initialize fresh."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    self.state = json.load(f)
                # Reconcile invested capital against open positions to prevent leaks
                calc_invested = sum(pos.get("invested", 0.0) for pos in self.state.get("positions", {}).values())
                self.state["invested_capital"] = calc_invested
                self.state["available_capital"] = max(0.0, self.state["total_capital"] - calc_invested)
                if len(self.state.get("compounding_curve", [])) > 100:
                    self.state["compounding_curve"] = self.state["compounding_curve"][-100:]
                if "prediction_verifications" not in self.state:
                    self.state["prediction_verifications"] = []
                if "prediction_accuracy" not in self.state:
                    self.state["prediction_accuracy"] = {
                        "total_verified": 0,
                        "exact_range_hits": 0,
                        "exact_range_hit_rate_pct": 0.0,
                        "direction_correct_count": 0,
                        "direction_accuracy_pct": 0.0,
                        "mean_abs_return_error_pct": 0.0,
                        "mean_price_error_pct": 0.0,
                        "buy_signals_verified": 0,
                        "buy_signals_positive": 0,
                        "buy_signal_win_rate_pct": 0.0,
                        "buy_signals_profit_hits": 0
                    }
                # Auto-rollover daily counters if day has changed
                today_str = datetime.now().strftime("%Y-%m-%d")
                if self.state.get("last_trade_date") != today_str:
                    self.state["last_trade_date"] = today_str
                    self.state["daily_trades_count"] = 0
                    self.state["session_starting_capital"] = self.state.get("total_capital", starting_capital)
                    self.state["session_realized_net_pnl"] = 0.0
                    self.state["session_return_pct"] = 0.0
                    if self.state.get("engine_status") == "SESSION_TARGET_ACHIEVED":
                        self.state["engine_status"] = "RUNNING"
                    self.candles_cache.clear()
                self._save_state()
                return
            except Exception as e:
                print(f"Error loading state file: {e}. Reinitializing.")

        self.state = {
            "starting_capital": starting_capital,
            "total_capital": starting_capital,
            "available_capital": starting_capital,
            "invested_capital": 0.0,
            "total_net_profit": 0.0,
            "total_gross_profit": 0.0,
            "total_tax_paid": 0.0,
            "total_brokerage_paid": 0.0,
            "compounding_multiplier": 1.0,
            "session_starting_capital": starting_capital,
            "session_realized_net_pnl": 0.0,
            "session_return_pct": 0.0,
            "target_session_profit_pct": self.target_session_profit_pct * 100,
            "daily_trades_count": 0,
            "target_daily_trades": self.target_daily_trades,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate_pct": 0.0,
            "positions": {},       # symbol -> position dict
            "compounding_curve": [
                {
                    "timestamp": datetime.now().isoformat(),
                    "total_capital": starting_capital,
                    "net_profit": 0.0,
                    "trade_num": 0
                }
            ],
            "capital_adjustments": [],  # Deposit / Withdraw log
            "last_signals": [],
            "last_scan_time": None,
            "last_trade_date": datetime.now().strftime("%Y-%m-%d"),
            "engine_status": "RUNNING",  # Start in active autonomous mode
            "prediction_verifications": [],
            "prediction_accuracy": {
                "total_verified": 0,
                "exact_range_hits": 0,
                "exact_range_hit_rate_pct": 0.0,
                "direction_correct_count": 0,
                "direction_accuracy_pct": 0.0,
                "mean_abs_return_error_pct": 0.0,
                "mean_price_error_pct": 0.0,
                "buy_signals_verified": 0,
                "buy_signals_positive": 0,
                "buy_signal_win_rate_pct": 0.0,
                "buy_signals_profit_hits": 0
            }
        }
        self._save_state()

    def is_market_open(self) -> bool:
        """Check if Indian Stock Market (NSE) is currently open (Mon-Fri, 9:15 AM - 3:30 PM IST)."""
        now = datetime.now()
        # Monday is 0 and Sunday is 6
        if now.weekday() >= 5:
            return False
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_open <= now <= market_close

    def check_day_rollover(self):
        """Reset daily trade count and clear candle cache when day rolls over (e.g. at midnight/standby)."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        if self.state.get("last_trade_date") == today_str:
            return
        with self.lock:
            if self.state.get("last_trade_date") != today_str:
                self.state["last_trade_date"] = today_str
                self.state["daily_trades_count"] = 0
                self.state["session_starting_capital"] = self.state.get("total_capital", 0.0)
                self.state["session_realized_net_pnl"] = 0.0
                self.state["session_return_pct"] = 0.0
                if self.state.get("engine_status") == "SESSION_TARGET_ACHIEVED":
                    self.state["engine_status"] = "RUNNING"
                self.candles_cache.clear()
                self._save_state()

    def get_market_status(self) -> dict:
        """Returns detailed market timing, countdown, and autonomous trading schedule."""
        self.check_day_rollover()
        now = datetime.now()
        is_open = self.is_market_open()
        
        if now.weekday() >= 5:
            next_open = "Monday at 09:15 AM IST"
        elif now.time() < datetime.strptime("09:15", "%H:%M").time():
            next_open = "Today at 09:15 AM IST"
        elif now.time() > datetime.strptime("15:30", "%H:%M").time():
            tomorrow_name = (now + timedelta(days=1)).strftime("%A")
            next_open = f"Tomorrow ({tomorrow_name}) at 09:15 AM IST" if now.weekday() < 4 else "Monday at 09:15 AM IST"
        else:
            next_open = "Currently Live & Trading (NSE Open)"

        return {
            "is_open": is_open,
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S IST"),
            "next_market_open": next_open,
            "market_mode": "LIVE_NSE_MARKET" if is_open else "OFF_MARKET_STANDBY",
            "auto_trade_from_tomorrow": True,
            "engine_status": self.state["engine_status"],
            "session_target_profit_pct": self.target_session_profit_pct * 100,
            "session_return_pct": self.state.get("session_return_pct", 0.0),
            "session_realized_net_pnl": self.state.get("session_realized_net_pnl", 0.0),
            "session_target_achieved": self.state.get("engine_status") == "SESSION_TARGET_ACHIEVED"
        }

    def _save_state(self):
        """Persist state to disk safely and compactly."""
        try:
            temp_file = STATE_FILE + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(self.state, f, default=str)
            os.replace(temp_file, STATE_FILE)
        except Exception as e:
            try:
                with open(STATE_FILE, "w") as f:
                    json.dump(self.state, f, default=str)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Manual Money Adjustment API
    # -------------------------------------------------------------------------

    def deposit_capital(self, amount: float, note: str = "Manual Deposit") -> dict:
        """Manually deposit money into trading account."""
        with self.lock:
            if amount <= 0:
                return {"success": False, "message": "Deposit amount must be greater than zero."}

            self.state["total_capital"] += amount
            self.state["available_capital"] += amount
            adjustment = {
                "id": f"DEP-{int(time.time()*1000)}",
                "type": "DEPOSIT",
                "amount": amount,
                "note": note,
                "timestamp": datetime.now().isoformat(),
                "balance_after": self.state["total_capital"]
            }
            self.state["capital_adjustments"].append(adjustment)
            self._save_state()
            self._notify_subscribers("CAPITAL_ADJUSTED", adjustment)
            return {
                "success": True,
                "message": f"Successfully deposited INR {amount:,.2f}.",
                "adjustment": adjustment,
                "state": self.get_summary()
            }

    def withdraw_capital(self, amount: float, note: str = "Manual Withdrawal") -> dict:
        """Manually withdraw money from uninvested available capital."""
        with self.lock:
            if amount <= 0:
                return {"success": False, "message": "Withdrawal amount must be greater than zero."}
            if amount > self.state["available_capital"]:
                return {
                    "success": False,
                    "message": f"Insufficient available cash. Available: INR {self.state['available_capital']:,.2f}"
                }

            self.state["total_capital"] -= amount
            self.state["available_capital"] -= amount
            adjustment = {
                "id": f"WTH-{int(time.time()*1000)}",
                "type": "WITHDRAWAL",
                "amount": amount,
                "note": note,
                "timestamp": datetime.now().isoformat(),
                "balance_after": self.state["total_capital"]
            }
            self.state["capital_adjustments"].append(adjustment)
            self._save_state()
            self._notify_subscribers("CAPITAL_ADJUSTED", adjustment)
            return {
                "success": True,
                "message": f"Successfully withdrew INR {amount:,.2f}.",
                "adjustment": adjustment,
                "state": self.get_summary()
            }

    def set_capital_base(self, new_capital: float, note: str = "Reset Base Capital") -> dict:
        """Override total capital base when no positions are open."""
        with self.lock:
            if new_capital <= 0:
                return {"success": False, "message": "Capital must be greater than zero."}
            if self.state["positions"]:
                return {"success": False, "message": "Cannot re-base capital while positions are open. Close positions first."}

            diff = new_capital - self.state["total_capital"]
            self.state["starting_capital"] = new_capital
            self.state["total_capital"] = new_capital
            self.state["available_capital"] = new_capital
            self.state["invested_capital"] = 0.0

            adjustment = {
                "id": f"SET-{int(time.time()*1000)}",
                "type": "REBASE",
                "amount": diff,
                "note": note,
                "timestamp": datetime.now().isoformat(),
                "balance_after": new_capital
            }
            self.state["capital_adjustments"].append(adjustment)
            self._save_state()
            self._notify_subscribers("CAPITAL_ADJUSTED", adjustment)
            return {"success": True, "message": f"Capital re-based to INR {new_capital:,.2f}.", "state": self.get_summary()}

    # -------------------------------------------------------------------------
    # Configuration & Settings
    # -------------------------------------------------------------------------

    def update_settings(self, settings: dict) -> dict:
        """Update trading parameters dynamically."""
        with self.lock:
            if "profit_threshold_pct" in settings:
                val = float(settings["profit_threshold_pct"])
                self.profit_threshold_pct = val / 100.0 if val > 0.01 else max(0.0005, val)
            if "stop_loss_pct" in settings:
                self.stop_loss_pct = max(0.001, float(settings["stop_loss_pct"]))
            if "position_sizing_pct" in settings:
                self.position_sizing_pct = min(0.50, max(0.02, float(settings["position_sizing_pct"])))
            if "target_daily_trades" in settings:
                self.target_daily_trades = int(settings["target_daily_trades"])
                self.state["target_daily_trades"] = self.target_daily_trades
            if "simulation_speed_sec" in settings:
                self.simulation_speed_sec = max(0.5, float(settings["simulation_speed_sec"]))
            if "off_market_simulation" in settings:
                self.off_market_simulation = bool(settings["off_market_simulation"])

            self._save_state()
            return {
                "success": True,
                "profit_threshold_pct": self.profit_threshold_pct,
                "stop_loss_pct": self.stop_loss_pct,
                "position_sizing_pct": self.position_sizing_pct,
                "target_daily_trades": self.target_daily_trades,
                "simulation_speed_sec": self.simulation_speed_sec,
                "off_market_simulation": self.off_market_simulation
            }

    # -------------------------------------------------------------------------
    # Market Data Feeds (Live + Synthetic/Replay)
    # -------------------------------------------------------------------------

    def _fetch_all_live_candles(self):
        """Batch download real 1-minute live candles from NSE for all universe stocks in a single request."""
        try:
            raw_df = yf.download(STOCK_SYMBOLS, period="1d", interval="1m", progress=False, threads=True)
            if raw_df is not None and not raw_df.empty:
                for symbol in STOCK_SYMBOLS:
                    try:
                        if isinstance(raw_df.columns, pd.MultiIndex):
                            if symbol in raw_df.columns.get_level_values(1):
                                sym_df = raw_df.xs(symbol, axis=1, level=1).copy()
                            elif symbol in raw_df.columns.get_level_values(0):
                                sym_df = raw_df.xs(symbol, axis=1, level=0).copy()
                            else:
                                continue
                        else:
                            sym_df = raw_df.copy()
                        sym_df = sym_df.reset_index()
                        sym_df.columns = [str(c).lower() for c in sym_df.columns]
                        time_col = "datetime" if "datetime" in sym_df.columns else "date" if "date" in sym_df.columns else "index"
                        if time_col not in sym_df.columns and "timestamp" not in sym_df.columns:
                            time_col = sym_df.columns[0]
                        sym_df = sym_df.rename(columns={time_col: "timestamp"})
                        sym_df["symbol"] = symbol
                        sym_df = sym_df.dropna(subset=["open", "high", "low", "close"])
                        if len(sym_df) >= 5:
                            self.candles_cache[symbol] = sym_df
                    except Exception:
                        pass
        except Exception as e:
            print(f"Batch live candle fetch notice: {e}")

    def get_or_generate_candles(self, symbol: str, n_candles: int = 50) -> pd.DataFrame:
        """Fetch real 1-minute live candles from NSE or generate realistic micro-candles."""
        if symbol in self.candles_cache and len(self.candles_cache[symbol]) >= 5:
            return self.candles_cache[symbol]

        # During live market hours (9:15 AM - 3:30 PM IST), pull live 1m ticks directly from NSE via yfinance
        if self.is_market_open():
            try:
                df = yf.download(symbol, period="1d", interval="1m", progress=False, threads=False)
                if not df.empty and len(df) >= 5:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = [c[0].lower() for c in df.columns]
                    else:
                        df.columns = [str(c).lower() for c in df.columns]
                    df = df.reset_index()
                    time_col = "datetime" if "datetime" in df.columns else "date" if "date" in df.columns else "index"
                    df = df.rename(columns={time_col: "timestamp"})
                    df["symbol"] = symbol
                    df = df.dropna(subset=["open", "high", "low", "close"])
                    self.candles_cache[symbol] = df
                    return df
            except Exception as e:
                print(f"Live NSE fetch failed for {symbol}: {e}. Falling back.")

        # Check local historical/weekend dataset first before attempting slow external fetch
        short_sym = symbol.replace(".NS", "")
        local_csv = os.path.join(PROJECT_ROOT, "data", f"{short_sym}_1m_weekend.csv")
        if os.path.exists(local_csv):
            try:
                df = pd.read_csv(local_csv)
                if not df.empty and len(df) >= 20:
                    df["symbol"] = symbol
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    df = df.dropna(subset=["open", "high", "low", "close"]).sort_values("timestamp")
                    self.candles_cache[symbol] = df
                    return df
            except Exception:
                pass

        try:
            df = yf.download(symbol, period="5d", interval="1m", progress=False, threads=False)
            if not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [c[0].lower() for c in df.columns]
                else:
                    df.columns = [str(c).lower() for c in df.columns]
                df = df.reset_index()
                time_col = "datetime" if "datetime" in df.columns else "date" if "date" in df.columns else "index"
                df = df.rename(columns={time_col: "timestamp"})
                df["symbol"] = symbol
                df = df.dropna(subset=["open", "high", "low", "close"])
                self.candles_cache[symbol] = df
                return df
        except Exception as e:
            pass

        # Fallback realistic 1-minute candle generator calibrated to actual NSE prices
        base_prices = {
            "RELIANCE.NS": 1256.0, "TCS.NS": 2315.0, "HDFCBANK.NS": 721.0,
            "ICICIBANK.NS": 1354.0, "INFY.NS": 1085.0, "SBIN.NS": 980.0,
            "BHARTIARTL.NS": 1833.0, "BAJFINANCE.NS": 1014.0, "AXISBANK.NS": 1235.0,
            "TATACAP.NS": 356.0
        }
        p = base_prices.get(symbol, 1000.0)
        now = datetime.now() - timedelta(minutes=n_candles)
        rows = []
        for i in range(n_candles):
            t = now + timedelta(minutes=i)
            # Add stochastic drift + micro-volatility
            ret = np.random.normal(0.0001, 0.0018)
            close = p * (1 + ret)
            high = max(p, close) * (1 + abs(np.random.normal(0, 0.001)))
            low = min(p, close) * (1 - abs(np.random.normal(0, 0.001)))
            vol = int(np.random.uniform(5000, 45000))
            rows.append({
                "timestamp": t,
                "open": p,
                "high": high,
                "low": low,
                "close": close,
                "volume": vol,
                "symbol": symbol
            })
            p = close

        df = pd.DataFrame(rows)
        self.candles_cache[symbol] = df
        return df

    # -------------------------------------------------------------------------
    # Core 1-Minute Scan & Execution
    # -------------------------------------------------------------------------

    def scan_and_trade_step(self) -> dict:
        """
        Executes one 1-minute trading cycle:
        1. Checks day rollover (resets daily trade counter for tomorrow).
        2. Updates open positions against latest market prices.
        3. Checks exits (Stop-Loss or Profit Target > 0.8%).
        4. Scans all 10 NSE stocks using 1-minute prediction models.
        5. If predicted profit > profit_threshold_pct (0.8%), enters BUY position.
        6. Reinvests/compounds capital.
        """
        with self.lock:
            signals = []
            executed_actions = []
            now = datetime.now()
            now_str = now.isoformat()
            today_str = now.strftime("%Y-%m-%d")

            # Day rollover: reset daily trades count for fresh trading day
            if self.state.get("last_trade_date") != today_str:
                self.state["last_trade_date"] = today_str
                self.state["daily_trades_count"] = 0
                self.state["session_starting_capital"] = self.state.get("total_capital", 0.0)
                self.state["session_realized_net_pnl"] = 0.0
                self.state["session_return_pct"] = 0.0
                if self.state.get("engine_status") == "SESSION_TARGET_ACHIEVED":
                    self.state["engine_status"] = "RUNNING"
                self.candles_cache.clear()  # Purge yesterday's cache to pull fresh live opening candles

            # Intraday Auto-Square-Off at 3:20 PM IST
            if now.hour == 15 and now.minute >= 20 and self.state.get("positions"):
                print("Market closing soon (3:20 PM IST) - Auto squaring off intraday positions.")
                for symbol in list(self.state["positions"].keys()):
                    candles = self.get_or_generate_candles(symbol)
                    latest_p = float(candles.iloc[-1]["close"])
                    pos = self.state["positions"][symbol]
                    # direction-aware gross_return (handled inside _close_position)
                    act = self._close_position(symbol, latest_p, 0.0, "MARKET_CLOSE_SQUAREOFF")
                    if act:
                        executed_actions.append(act)

            # 1. Update existing positions & check exits
            for symbol in list(self.state["positions"].keys()):
                pos = self.state["positions"][symbol]
                candles = self.get_or_generate_candles(symbol)
                latest_p = float(candles.iloc[-1]["close"])
                entry_p = pos["entry_price"]
                direction = pos.get("direction", "LONG")

                # Direction-aware gross return for cost estimation
                if direction == "SHORT":
                    gross_ret = (entry_p - latest_p) / entry_p  # positive when price falls
                else:
                    gross_ret = (latest_p - entry_p) / entry_p  # positive when price rises

                # Update current price & unrealized P&L
                cost_est = self.tax_engine.calculate_total_cost(pos["invested"], gross_ret)
                pos["current_price"] = round(latest_p, 2)
                pos["unrealized_gross_pnl"] = round(cost_est["gross_profit"], 2)
                pos["unrealized_net_pnl"] = round(cost_est["net_profit"], 2)
                pos["unrealized_net_ret_pct"] = round(cost_est["net_return_pct"], 3)

                # Track best price achieved during hold for trailing stop
                if direction == "SHORT":
                    # SHORT: profit when price drops — track lowest price (best short profit)
                    if "lowest_price" not in pos or latest_p < pos["lowest_price"]:
                        pos["lowest_price"] = latest_p
                    best_p = pos.get("lowest_price", latest_p)
                    max_gain_pct = (entry_p - best_p) / entry_p if entry_p > 0 else 0.0
                    pullback_from_peak_pct = (latest_p - best_p) / entry_p if entry_p > 0 else 0.0
                else:
                    # LONG: profit when price rises — track highest price
                    if "highest_price" not in pos or latest_p > pos["highest_price"]:
                        pos["highest_price"] = latest_p
                    best_p = pos.get("highest_price", latest_p)
                    max_gain_pct = (best_p - entry_p) / entry_p if entry_p > 0 else 0.0
                    pullback_from_peak_pct = (best_p - latest_p) / best_p if best_p > 0 else 0.0

                entry_time_str = pos.get("entry_time", now_str)
                try:
                    entry_dt = datetime.fromisoformat(entry_time_str)
                    seconds_held = (now - entry_dt).total_seconds()
                except Exception:
                    seconds_held = 0.0

                # Exit Condition A: Hard Stop-Loss
                # LONG: price rose against us (-0.7%). SHORT: price rose against us (also -0.7% gross).
                if gross_ret <= -self.stop_loss_pct:
                    action = self._close_position(symbol, latest_p, gross_ret, "STOP_LOSS")
                    executed_actions.append(action)
                # Exit Condition B: Take-Profit Target (3.5% net)
                elif cost_est["net_profit"] > 0 and cost_est["net_return_pct"] >= (self.take_profit_target_pct * 100):
                    action = self._close_position(symbol, latest_p, gross_ret, "TAKE_PROFIT_TARGET")
                    executed_actions.append(action)
                # Exit Condition C: Dynamic Trailing Stop Ratchet
                # Activated when best gain >= 1.5%; exit if it reverses 0.35% from peak
                elif max_gain_pct >= self.trailing_stop_activation_pct and pullback_from_peak_pct >= 0.0035 and cost_est["net_profit"] > 0:
                    action = self._close_position(symbol, latest_p, gross_ret, "TRAILING_STOP_PROFIT_LOCK")
                    executed_actions.append(action)
                # Exit Condition D: Max Holding Time (120 minutes)
                elif seconds_held >= self.max_hold_seconds:
                    exit_type = "TIME_EXPIRATION_PROFIT" if cost_est["net_profit"] > 0 else "TIME_EXPIRATION_TIMEOUT"
                    action = self._close_position(symbol, latest_p, gross_ret, exit_type)
                    executed_actions.append(action)

            # 2. Scan all NSE stocks for 1-minute entry opportunities
            resolved_verifications = []
            for symbol in STOCK_SYMBOLS:
                candles = self.get_or_generate_candles(symbol)
                latest_candle = candles.iloc[-1]
                latest_ts_str = latest_candle["timestamp"].isoformat() if hasattr(latest_candle["timestamp"], "isoformat") else str(latest_candle["timestamp"])

                # Verify pending prediction if new candle has arrived
                if symbol in self.pending_predictions:
                    pending = self.pending_predictions[symbol]
                    if pending.get("candle_ts") != latest_ts_str:
                        actual_close = float(latest_candle["close"])
                        actual_high = float(latest_candle["high"])
                        actual_low = float(latest_candle["low"])
                        entry_p = pending["entry_price"]
                        pred_p = pending["predicted_price_1m"]
                        pred_ret = pending["predicted_return_pct"]
                        actual_ret = ((actual_close - entry_p) / (entry_p + 1e-9)) * 100.0

                        exact_range_reached = bool(actual_low <= pred_p <= actual_high)
                        exact_close_hit = bool(abs(actual_close - pred_p) / (actual_close + 1e-9) <= 0.001)
                        price_error = abs(actual_close - pred_p)
                        price_error_pct = (price_error / (actual_close + 1e-9)) * 100.0
                        return_error_pct = abs(actual_ret - pred_ret)
                        direction_correct = bool((pred_ret >= 0 and actual_ret >= 0) or (pred_ret < 0 and actual_ret < 0))
                        target_hit = bool(actual_ret >= pending["profit_threshold_pct"]) if pending["signal"] == "BUY" else None

                        verif_record = {
                            "symbol": symbol,
                            "company": pending["company"],
                            "predicted_at": pending["timestamp"],
                            "resolved_at": latest_ts_str,
                            "entry_price": round(entry_p, 2),
                            "predicted_price": round(pred_p, 2),
                            "actual_price": round(actual_close, 2),
                            "actual_high": round(actual_high, 2),
                            "actual_low": round(actual_low, 2),
                            "exact_range_reached": exact_range_reached,
                            "exact_close_hit": exact_close_hit,
                            "price_error": round(price_error, 2),
                            "price_error_pct": round(price_error_pct, 3),
                            "predicted_return_pct": round(pred_ret, 3),
                            "actual_return_pct": round(actual_ret, 3),
                            "return_error_pct": round(return_error_pct, 3),
                            "direction_correct": direction_correct,
                            "signal": pending["signal"],
                            "confidence": pending["confidence"],
                            "target_hit": target_hit
                        }
                        self.state["prediction_verifications"].append(verif_record)
                        resolved_verifications.append(verif_record)
                        self.confidence_tracker.update(symbol, direction_correct)

                regime_info = classify_micro_regime(candles)
                adjusted_hurdle = self.profit_threshold_pct * regime_info.get("hurdle_multiplier", 1.0)
                conf_mult = self.confidence_tracker.get_multiplier(symbol)
                is_symbol_blacklisted = (symbol in self.stock_blacklist) or self.confidence_tracker.is_blacklisted(symbol)

                pred = self.predictor.predict_next_1m(
                    candles,
                    profit_threshold=adjusted_hurdle,
                    confidence_multiplier=conf_mult
                )

                # Attach regime and per-stock intelligence
                stock_prof = self.confidence_tracker.get_profile(symbol)
                pred["regime"] = regime_info["regime"]
                pred["regime_desc"] = regime_info["description"]
                pred["blacklisted"] = is_symbol_blacklisted
                pred["stock_accuracy_pct"] = stock_prof["directional_accuracy_pct"]
                pred["stock_tier"] = stock_prof["tier"]

                # SMC 4-Confirmation & 9:20 Confluence Tagging (Model 06 Integration)
                try:
                    from v3.models.smc_straddle_model import SMC4ConfStraddleEngine
                    if len(candles) >= 15:
                        smc_eng = SMC4ConfStraddleEngine()
                        smc_status = smc_eng.evaluate_smc_confirmations(candles)
                        pred["smc_setup_quality"] = smc_status.setup_quality
                        pred["smc_sweep"] = smc_status.c1_liquidity_sweep
                        pred["smc_choch"] = smc_status.c2_choch
                        pred["smc_ob"] = smc_status.c3_order_block
                        pred["smc_fvg"] = smc_status.c4_fvg
                        pred["smc_vwap_filter"] = smc_status.f1_vwap_filter
                        pred["smc_ema9_filter"] = smc_status.f2_ema9_filter
                        if smc_status.all_4_confirmations:
                            pred["confidence"] = min(99.0, round(pred["confidence"] * 1.15, 1))
                            pred["smc_confluence"] = "FULL_4_CONF"
                        elif smc_status.hq_3_confirmation:
                            pred["confidence"] = min(99.0, round(pred["confidence"] * 1.08, 1))
                            pred["smc_confluence"] = "HQ_3_CONF"
                        else:
                            pred["smc_confluence"] = "NONE"
                except Exception:
                    pred["smc_confluence"] = "UNAVAILABLE"

                # If blacklisted, suppress ALL signals to enforce capital preservation
                if is_symbol_blacklisted and pred["signal"] in ("BUY", "SELL"):
                    pred["signal"] = "HOLD"
                    pred["direction"] = "FLAT"
                    pred["suppressed_reason"] = f"Blacklisted ({stock_prof['reason']})"

                signals.append(pred)

                # Store pending prediction for resolution on next candle
                self.pending_predictions[symbol] = {
                    "timestamp": now_str,
                    "candle_ts": latest_ts_str,
                    "symbol": symbol,
                    "company": pred["company"],
                    "entry_price": pred["current_price"],
                    "predicted_price_1m": pred["predicted_price_1m"],
                    "predicted_return_pct": pred["predicted_return_pct"],
                    "signal": pred["signal"],
                    "direction": pred.get("direction", "FLAT"),
                    "confidence": pred["confidence"],
                    "profit_threshold_pct": pred["profit_threshold_pct"]
                }

                # Gate checks apply to BOTH long (BUY) and short (SELL) entries
                in_cooldown = False
                if symbol in self.last_exit_times:
                    if (now - self.last_exit_times[symbol]).total_seconds() < 300:
                        in_cooldown = True

                opening_cooloff = (now.hour == 9 and now.minute < 20) if self.is_market_open() else False
                min_cap_req = 100.0
                allows_scalp = regime_info.get("allows_long_scalp", True)
                session_target_met = (self.state.get("engine_status") == "SESSION_TARGET_ACHIEVED")

                can_enter = (
                    not is_symbol_blacklisted
                    and not opening_cooloff
                    and not in_cooldown
                    and not session_target_met
                    and symbol not in self.state["positions"]
                    and len(self.state["positions"]) < self.max_concurrent_positions
                    and self.state["available_capital"] >= min_cap_req
                )

                # LONG entry: BUY when price expected to RISE
                if pred["signal"] == "BUY" and allows_scalp and can_enter:
                    action = self._open_position(pred, direction="LONG")
                    if action:
                        executed_actions.append(action)

                # SHORT entry: SELL when price expected to FALL
                # NSE intraday short selling: sell now, buy back same session
                elif pred["signal"] == "SELL" and can_enter:
                    action = self._open_position(pred, direction="SHORT")
                    if action:
                        executed_actions.append(action)

            # Trim verifications history to recent 250 items
            if len(self.state["prediction_verifications"]) > 250:
                self.state["prediction_verifications"] = self.state["prediction_verifications"][-250:]

            # Broadcast resolved verifications
            if resolved_verifications:
                for vr in resolved_verifications:
                    self._notify_subscribers("PREDICTION_VERIFIED", vr)

            # Update state metadata
            self.state["last_signals"] = signals
            self.state["last_scan_time"] = now_str
            self._update_aggregate_metrics()
            self._save_state()

            result = {
                "timestamp": now_str,
                "signals": signals,
                "actions": executed_actions,
                "state": self.get_summary()
            }
            self._notify_subscribers("TICK_UPDATE", result)
            return result

    def _open_position(self, pred: dict, direction: str = "LONG") -> dict:
        """
        Open a LONG or SHORT position.
        LONG:  BUY now, SELL later when price rises.
        SHORT: SELL now (intraday short), BUY back when price falls.
               NSE allows same-day short selling on all liquid NSE stocks.
        """
        symbol = pred["symbol"]
        curr_price = pred["current_price"]

        if self.state["available_capital"] < curr_price:
            return None

        # Allocate up to 95% of available capital for full momentum deployment
        invest_amount = self.state["available_capital"] * self.position_sizing_pct
        qty = int(invest_amount / curr_price)
        if qty < 1 and self.state["available_capital"] >= curr_price:
            qty = 1

        actual_invested = qty * curr_price
        if actual_invested > self.state["available_capital"]:
            qty = int(self.state["available_capital"] / curr_price)
            actual_invested = qty * curr_price

        if qty < 1 or actual_invested <= 0:
            return None

        self.state["available_capital"] -= actual_invested
        self.state["invested_capital"] += actual_invested

        pos = {
            "symbol": symbol,
            "company": pred["company"],
            "direction": direction,           # "LONG" or "SHORT"
            "entry_price": curr_price,
            "current_price": curr_price,
            "highest_price": curr_price,     # for LONG trailing stop: best price seen
            "lowest_price": curr_price,      # for SHORT trailing stop: best (lowest) price seen
            "qty": qty,
            "invested": actual_invested,
            "entry_time": datetime.now().isoformat(),
            "predicted_return_pct": pred["predicted_return_pct"],
            "confidence": pred["confidence"],
            "bars_held": 0,
            "unrealized_net_pnl": 0.0,
            "unrealized_net_ret_pct": 0.0
        }
        self.state["positions"][symbol] = pos

        entry_action = "SHORT_SELL" if direction == "SHORT" else "BUY"
        trade_event = {
            "id": f"TRD-{int(time.time()*1000)}",
            "action": entry_action,
            "direction": direction,
            "symbol": symbol,
            "company": pred["company"],
            "price": curr_price,
            "qty": qty,
            "invested": actual_invested,
            "predicted_return_pct": pred["predicted_return_pct"],
            "confidence": pred["confidence"],
            "reason": f"{direction} | Pred Return {pred['predicted_return_pct']}% vs thresh {pred['profit_threshold_pct']}%",
            "starting_capital": round(self.state["starting_capital"], 2),
            "capital_after": round(self.state["total_capital"], 2),
            "win_rate_pct": self.state["win_rate_pct"],
            "timestamp": datetime.now().isoformat()
        }
        self._log_trade(trade_event)
        return trade_event

    def _close_position(self, symbol: str, exit_price: float, gross_return: float, reason: str) -> dict:
        """
        Close LONG or SHORT position and compound net profit/loss.
        For SHORT: gross_return = (entry_price - exit_price) / entry_price  (positive when price fell)
        """
        pos = self.state["positions"].pop(symbol, None)
        if not pos:
            return None

        self.last_exit_times[symbol] = datetime.now()

        direction = pos.get("direction", "LONG")
        entry_p = pos["entry_price"]
        # Recalculate gross_return based on direction to ensure correctness
        if direction == "SHORT":
            gross_return = (entry_p - exit_price) / entry_p  # profit when price drops
        else:
            gross_return = (exit_price - entry_p) / entry_p  # profit when price rises

        invested = pos["invested"]
        cost_breakdown = self.tax_engine.calculate_total_cost(invested, gross_return)
        net_profit = cost_breakdown.get("net_profit", 0.0)
        gross_profit = cost_breakdown.get("gross_profit", 0.0)
        tax_paid = cost_breakdown.get("tax", 0.0)
        brokerage = cost_breakdown.get("brokerage", 0.0)

        # Compounding: return principal + net profit into available & total capital
        realized_capital = invested + net_profit
        self.state["available_capital"] += realized_capital
        self.state["invested_capital"] -= invested
        self.state["total_capital"] = self.state["available_capital"] + self.state["invested_capital"]

        # Track session PnL & Daily 5% Target Lock
        self.state["session_realized_net_pnl"] = round(self.state.get("session_realized_net_pnl", 0.0) + net_profit, 2)
        sess_start_cap = self.state.get("session_starting_capital", self.state["total_capital"] - net_profit)
        if sess_start_cap > 0:
            session_ret_pct = self.state["session_realized_net_pnl"] / sess_start_cap
            self.state["session_return_pct"] = round(session_ret_pct * 100, 2)
            if session_ret_pct >= self.target_session_profit_pct:
                self.state["engine_status"] = "SESSION_TARGET_ACHIEVED"
                print(f"🎯 [TARGET HIT] 5.0% Daily Compounding Target Reached (+{session_ret_pct*100:.2f}%)! Capital locked in vault for tomorrow.")

        # Aggregate profit tracking
        self.state["total_net_profit"] += net_profit
        self.state["total_gross_profit"] += gross_profit
        self.state["total_tax_paid"] += tax_paid
        self.state["total_brokerage_paid"] += brokerage
        self.state["daily_trades_count"] += 1

        if net_profit > 0:
            self.state["winning_trades"] += 1
        else:
            self.state["losing_trades"] += 1

        # Record compounding growth step
        trade_num = self.state["daily_trades_count"]
        self.state["compounding_curve"].append({
            "timestamp": datetime.now().isoformat(),
            "total_capital": round(self.state["total_capital"], 2),
            "net_profit": round(net_profit, 2),
            "trade_num": trade_num,
            "symbol": symbol,
            "reason": reason
        })
        if len(self.state["compounding_curve"]) > 100:
            self.state["compounding_curve"] = self.state["compounding_curve"][-100:]

        direction = pos.get("direction", "LONG")
        close_action = "BUY_COVER" if direction == "SHORT" else "SELL"
        trade_event = {
            "id": f"TRD-{int(time.time()*1000)}",
            "action": close_action,
            "direction": direction,
            "symbol": symbol,
            "company": pos["company"],
            "entry_price": pos["entry_price"],
            "exit_price": round(exit_price, 2),
            "qty": pos["qty"],
            "invested": round(invested, 2),
            "gross_return_pct": round(gross_return * 100, 3),
            "net_profit": round(net_profit, 2),
            "net_return_pct": round(cost_breakdown["net_return_pct"], 3),
            "tax_paid": round(tax_paid, 2),
            "brokerage": round(brokerage, 2),
            "reason": reason,
            "starting_capital": round(self.state["starting_capital"], 2),
            "capital_after": round(self.state["total_capital"], 2),
            "win_rate_pct": self.state["win_rate_pct"],
            "timestamp": datetime.now().isoformat()
        }
        self._log_trade(trade_event)
        return trade_event

    def emergency_close_all(self) -> list:
        """Close all open positions immediately at current market prices."""
        with self.lock:
            actions = []
            for symbol in list(self.state["positions"].keys()):
                candles = self.get_or_generate_candles(symbol)
                latest_p = float(candles.iloc[-1]["close"])
                pos = self.state["positions"][symbol]
                gross_ret = (latest_p - pos["entry_price"]) / pos["entry_price"]
                action = self._close_position(symbol, latest_p, gross_ret, "EMERGENCY_MANUAL_CLOSE")
                if action:
                    actions.append(action)
            self._update_aggregate_metrics()
            self._save_state()
            self._notify_subscribers("EMERGENCY_CLOSE", actions)
            return actions

    def manual_order(self, symbol: str, action: str, amount: float = 10000.0) -> dict:
        """Execute a manual buy or sell on demand."""
        with self.lock:
            candles = self.get_or_generate_candles(symbol)
            curr_p = float(candles.iloc[-1]["close"])

            if action.upper() == "BUY":
                if symbol in self.state["positions"]:
                    return {"success": False, "message": f"Already holding {symbol}."}
                if amount > self.state["available_capital"]:
                    return {"success": False, "message": f"Insufficient cash (INR {self.state['available_capital']:,.2f})."}

                pred = self.predictor.predict_next_1m(candles, profit_threshold=self.profit_threshold_pct)
                pred["current_price"] = curr_p
                # Temporarily set sizing
                orig_sizing = self.position_sizing_pct
                self.position_sizing_pct = min(1.0, amount / self.state["available_capital"])
                event = self._open_position(pred)
                self.position_sizing_pct = orig_sizing

                self._update_aggregate_metrics()
                self._save_state()
                return {"success": True, "action": event, "state": self.get_summary()}

            elif action.upper() == "SELL":
                if symbol not in self.state["positions"]:
                    return {"success": False, "message": f"No open position in {symbol} to sell."}
                pos = self.state["positions"][symbol]
                gross_ret = (curr_p - pos["entry_price"]) / pos["entry_price"]
                event = self._close_position(symbol, curr_p, gross_ret, "MANUAL_SELL")
                self._update_aggregate_metrics()
                self._save_state()
                return {"success": True, "action": event, "state": self.get_summary()}

            return {"success": False, "message": f"Unknown action: {action}"}

    # -------------------------------------------------------------------------
    # Background Execution Loop (Live / Simulation)
    # -------------------------------------------------------------------------

    def start_engine(self):
        """Start the automated scanning and compounding loop.
        RETIRED / FROZEN: Operational background execution loop disabled.
        Authoritative orchestrator is now AlphaNSE Unified Ensemble.
        """
        self.is_running = False
        self.state["engine_status"] = "FROZEN_ARCHIVE"
        self._save_state()
        print("[RETIRED] CompoundingTrader background loop disabled. Authoritative orchestrator: AlphaNSE Unified Ensemble.")
        return

    def pause_engine(self):
        """Pause the automated engine."""
        self.is_running = False
        self.state["engine_status"] = "PAUSED"
        self._save_state()
        self._notify_subscribers("ENGINE_PAUSED", {})

    def _simulate_market_tick(self):
        """Simulate next 1-minute candle tick across universe to enable continuous 24/7 testing."""
        for symbol in STOCK_SYMBOLS:
            df = self.get_or_generate_candles(symbol)
            if not df.empty:
                last_row = df.iloc[-1]
                p = float(last_row["close"])
                # Generate realistic intraday tick: 20% chance of strong breakout (>0.8% return)
                is_breakout = np.random.random() < 0.22
                if is_breakout:
                    drift = np.random.uniform(0.0085, 0.018)  # 0.85% to 1.8% breakout (exceeds 0.8% threshold)
                else:
                    drift = np.random.normal(0.0001, 0.0020)

                new_close = p * (1 + drift)
                new_high = max(p, new_close) * (1 + abs(np.random.normal(0, 0.001)))
                new_low = min(p, new_close) * (1 - abs(np.random.normal(0, 0.001)))
                new_vol = int(np.random.uniform(12000, 75000) * (2.8 if is_breakout else 1.0))
                new_ts = pd.to_datetime(last_row["timestamp"]) + timedelta(minutes=1)

                new_candle = pd.DataFrame([{
                    "timestamp": new_ts,
                    "open": p,
                    "high": new_high,
                    "low": new_low,
                    "close": new_close,
                    "volume": new_vol,
                    "symbol": symbol
                }])
                self.candles_cache[symbol] = pd.concat([df.iloc[1:], new_candle], ignore_index=True)

    # -------------------------------------------------------------------------
    # Metrics & Helpers
    # -------------------------------------------------------------------------

    def _update_aggregate_metrics(self):
        """Recompute win rate, compounding multiplier, and portfolio capital."""
        total_trades = self.state["winning_trades"] + self.state["losing_trades"]
        if total_trades > 0:
            self.state["win_rate_pct"] = round((self.state["winning_trades"] / total_trades) * 100, 1)
        else:
            self.state["win_rate_pct"] = 0.0

        if self.state["starting_capital"] > 0:
            self.state["compounding_multiplier"] = round(self.state["total_capital"] / self.state["starting_capital"], 3)
        else:
            self.state["compounding_multiplier"] = 1.0

        self._update_prediction_accuracy_metrics()

    def _update_prediction_accuracy_metrics(self):
        """Compute running accuracy metrics over recent prediction verifications."""
        verifs = self.state.get("prediction_verifications", [])
        if not verifs:
            return

        total = len(verifs)
        exact_hits = sum(1 for v in verifs if v.get("exact_range_reached"))
        exact_close_hits = sum(1 for v in verifs if v.get("exact_close_hit"))
        dir_correct = sum(1 for v in verifs if v.get("direction_correct"))
        mean_ret_err = float(np.mean([v.get("return_error_pct", 0.0) for v in verifs]))
        mean_price_err_pct = float(np.mean([v.get("price_error_pct", 0.0) for v in verifs]))

        buy_signals = [v for v in verifs if v.get("signal") == "BUY"]
        buy_total = len(buy_signals)
        buy_wins = sum(1 for v in buy_signals if v.get("actual_return_pct", 0.0) > 0)
        buy_target_hits = sum(1 for v in buy_signals if v.get("target_hit") is True)

        self.state["prediction_accuracy"] = {
            "total_verified": total,
            "exact_range_hits": exact_hits,
            "exact_range_hit_rate_pct": round((exact_hits / max(1, total)) * 100, 1),
            "exact_close_hits": exact_close_hits,
            "exact_close_hit_rate_pct": round((exact_close_hits / max(1, total)) * 100, 1),
            "direction_correct_count": dir_correct,
            "direction_accuracy_pct": round((dir_correct / max(1, total)) * 100, 1),
            "mean_abs_return_error_pct": round(mean_ret_err, 3),
            "mean_price_error_pct": round(mean_price_err_pct, 3),
            "buy_signals_verified": buy_total,
            "buy_signals_positive": buy_wins,
            "buy_signal_win_rate_pct": round((buy_wins / max(1, buy_total)) * 100, 1) if buy_total > 0 else 0.0,
            "buy_signals_profit_hits": buy_target_hits
        }

    def get_summary(self) -> dict:
        """Return full clean state dictionary for REST/WebSocket clients."""
        self.check_day_rollover()
        return {
            "starting_capital": round(self.state["starting_capital"], 2),
            "total_capital": round(self.state["total_capital"], 2),
            "available_capital": round(self.state["available_capital"], 2),
            "invested_capital": round(self.state["invested_capital"], 2),
            "total_net_profit": round(self.state["total_net_profit"], 2),
            "total_gross_profit": round(self.state["total_gross_profit"], 2),
            "total_tax_paid": round(self.state["total_tax_paid"], 2),
            "total_brokerage_paid": round(self.state["total_brokerage_paid"], 2),
            "compounding_multiplier": self.state["compounding_multiplier"],
            "daily_trades_count": self.state["daily_trades_count"],
            "target_daily_trades": self.target_daily_trades,
            "daily_target_progress_pct": min(100.0, round((self.state["daily_trades_count"] / max(1, self.target_daily_trades)) * 100, 1)),
            "winning_trades": self.state["winning_trades"],
            "losing_trades": self.state["losing_trades"],
            "win_rate_pct": self.state["win_rate_pct"],
            "positions_count": len(self.state["positions"]),
            "positions": self.state["positions"],
            "engine_status": self.state["engine_status"],
            "profit_threshold_pct": round(self.profit_threshold_pct * 100, 2),
            "stop_loss_pct": round(self.stop_loss_pct * 100, 2),
            "position_sizing_pct": round(self.position_sizing_pct * 100, 1),
            "simulation_speed_sec": self.simulation_speed_sec,
            "off_market_simulation": self.off_market_simulation,
            "is_market_open": self.is_market_open(),
            "last_scan_time": self.state["last_scan_time"],
            "capital_adjustments": self.state["capital_adjustments"][-10:],
            "compounding_curve": self.state["compounding_curve"][-50:],
            "prediction_accuracy": self.state.get("prediction_accuracy", {}),
            "recent_verifications": list(reversed(self.state.get("prediction_verifications", [])[-25:])),
            "blacklisted_stocks": list(self.stock_blacklist),
            "stock_profiles": self.confidence_tracker.get_all_profiles()
        }

    def _log_trade(self, trade_event: dict):
        """Append trade event to JSONL file."""
        with open(TRADE_LOG_FILE, "a") as f:
            f.write(json.dumps(trade_event, default=str) + "\n")

    def get_trade_history(self, limit: int = 100, date_filter: str = "session", reverse: bool = True) -> list:
        """Retrieve trade history with consistent fields for reporting.
        date_filter:
          - 'session' or 'today': returns only trades executed in the current active session (after cleared_today_at)
          - 'all': returns all historical trades across all dates
          - 'YYYY-MM-DD': returns trades for that specific date
        reverse: True by default to return NEWEST trades first.
        """
        if not os.path.exists(TRADE_LOG_FILE):
            return []

        today_str = datetime.now().strftime("%Y-%m-%d")
        if date_filter in ("session", "today"):
            target_date = today_str
            cleared_today_at = self.state.get("cleared_today_at")
        elif date_filter == "all":
            target_date = None
            cleared_today_at = None
        else:
            target_date = date_filter
            cleared_today_at = None

        trades = []
        with open(TRADE_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip():
                    try:
                        tr = json.loads(line)
                        ts = tr.get("timestamp", "")
                        if target_date and not ts.startswith(target_date):
                            continue
                        if cleared_today_at and ts <= cleared_today_at:
                            continue
                        if "starting_capital" not in tr:
                            tr["starting_capital"] = round(self.state.get("starting_capital", 100000.0), 2)
                        if "win_rate_pct" not in tr:
                            tr["win_rate_pct"] = self.state.get("win_rate_pct", 0.0)
                        if "capital_after" not in tr:
                            tr["capital_after"] = round(self.state.get("total_capital", 100000.0), 2)
                        if "invest_amount" not in tr and "invested" in tr:
                            tr["invest_amount"] = tr["invested"]
                        trades.append(tr)
                    except Exception:
                        pass
        selected = trades[-limit:] if limit > 0 else trades
        if reverse:
            return list(reversed(selected))
        return selected

    def get_trade_dates_summary(self) -> list:
        """Scan trade logs and return summary metrics for each distinct trading date for Settings History."""
        if not os.path.exists(TRADE_LOG_FILE):
            return []

        from collections import defaultdict
        date_groups = defaultdict(lambda: {
            "total_trades": 0, "buys": 0, "sells": 0, "wins": 0, "losses": 0,
            "net_pnl": 0.0, "taxes": 0.0, "brokerage": 0.0
        })

        with open(TRADE_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip():
                    try:
                        tr = json.loads(line)
                        ts = tr.get("timestamp", "")
                        d = ts.split("T")[0] if "T" in ts else ts.split(" ")[0]
                        if not d or len(d) < 8:
                            continue

                        dg = date_groups[d]
                        dg["total_trades"] += 1
                        if tr.get("action") == "BUY":
                            dg["buys"] += 1
                        elif tr.get("action") == "SELL":
                            dg["sells"] += 1
                            pnl = tr.get("net_profit", 0.0)
                            dg["net_pnl"] += pnl
                            dg["taxes"] += tr.get("tax_paid", 0.0)
                            dg["brokerage"] += tr.get("brokerage", 0.0)
                            if pnl > 0:
                                dg["wins"] += 1
                            else:
                                dg["losses"] += 1
                    except Exception:
                        pass

        today_str = datetime.now().strftime("%Y-%m-%d")
        results = []
        for d, dg in sorted(date_groups.items(), key=lambda x: x[0], reverse=True):
            sells = dg["sells"]
            win_rate = round((dg["wins"] / sells * 100), 1) if sells > 0 else 0.0
            results.append({
                "date": d,
                "is_today": d == today_str,
                "total_trades": dg["total_trades"],
                "buys": dg["buys"],
                "sells": dg["sells"],
                "wins": dg["wins"],
                "losses": dg["losses"],
                "win_rate_pct": win_rate,
                "net_pnl": round(dg["net_pnl"], 2),
                "taxes": round(dg["taxes"], 2),
                "brokerage": round(dg["brokerage"], 2),
                "frictions_total": round(dg["taxes"] + dg["brokerage"], 2)
            })
        return results

    def start_new_session(self) -> dict:
        """Starts a fresh trading session, clearing previous session trade logs from active view while preserving all historical logs."""
        with self.lock:
            now_str = datetime.now().isoformat()
            today_str = datetime.now().strftime("%Y-%m-%d")
            self.state["daily_trades_count"] = 0
            self.state["winning_trades"] = 0
            self.state["losing_trades"] = 0
            self.state["win_rate_pct"] = 0.0
            self.state["last_trade_date"] = today_str
            self.state["cleared_today_at"] = now_str
            self.candles_cache.clear()
            self._save_state()
            payload = {"date": today_str, "cleared_at": now_str, "state": self.get_summary()}
            self._notify_subscribers("SESSION_RESET", payload)
            self._notify_subscribers("TODAY_TRADES_CLEARED", payload)
            return {
                "success": True,
                "message": f"New trading session started. Active session logs cleared. Day reset fresh.",
                "date": today_str,
                "cleared_at": now_str,
                "state": self.get_summary()
            }

    def clear_today_trades(self) -> dict:
        """Reset today's active trades count and daily trade counter for a fresh start."""
        return self.start_new_session()

    # -------------------------------------------------------------------------
    # WebSocket Event Pub/Sub
    # -------------------------------------------------------------------------

    def register_subscriber(self, callback):
        self.subscribers.append(callback)

    def unregister_subscriber(self, callback):
        if callback in self.subscribers:
            self.subscribers.remove(callback)

    def _notify_subscribers(self, event_type: str, data: dict):
        for sub in list(self.subscribers):
            try:
                sub(event_type, data)
            except Exception:
                pass
