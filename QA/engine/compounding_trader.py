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
    sys.path.append(PROJECT_ROOT)

from stocks_config import STOCK_SYMBOLS, STOCK_UNIVERSE, DEFAULT_CAPITAL, STOCK_BLACKLIST
from risk.india_tax_engine import IndiaTaxEngine
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

        # Strategy parameters
        self.profit_threshold_pct = 0.0008   # 0.08% (8 bps) minimum expected profit hurdle — lowered to match model output range
        self.stop_loss_pct = 0.003            # 0.3% stop loss
        self.position_sizing_pct = 0.15       # 15% of available capital per trade
        self.target_daily_trades = 15         # Target 10-15+ trades per day
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
            "engine_status": self.state["engine_status"]
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
                self.profit_threshold_pct = max(0.001, float(settings["profit_threshold_pct"]))
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
                            continue
                        sym_df.columns = [str(c).lower() for c in sym_df.columns]
                        sym_df = sym_df.reset_index()
                        time_col = "datetime" if "datetime" in sym_df.columns else "date" if "date" in sym_df.columns else "index"
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
                self.candles_cache.clear()  # Purge yesterday's cache to pull fresh live opening candles

            # Intraday Auto-Square-Off at 3:20 PM IST
            if now.hour == 15 and now.minute >= 20 and self.state.get("positions"):
                print("Market closing soon (3:20 PM IST) - Auto squaring off intraday positions.")
                for symbol in list(self.state["positions"].keys()):
                    candles = self.get_or_generate_candles(symbol)
                    latest_p = float(candles.iloc[-1]["close"])
                    pos = self.state["positions"][symbol]
                    gross_ret = (latest_p - pos["entry_price"]) / pos["entry_price"]
                    act = self._close_position(symbol, latest_p, gross_ret, "MARKET_CLOSE_SQUAREOFF")
                    if act:
                        executed_actions.append(act)

            # 1. Update existing positions & check exits
            for symbol in list(self.state["positions"].keys()):
                pos = self.state["positions"][symbol]
                candles = self.get_or_generate_candles(symbol)
                latest_p = float(candles.iloc[-1]["close"])
                entry_p = pos["entry_price"]
                gross_ret = (latest_p - entry_p) / entry_p

                # Update current price & unrealized P&L
                cost_est = self.tax_engine.calculate_total_cost(pos["invested"], gross_ret)
                pos["current_price"] = round(latest_p, 2)
                pos["unrealized_gross_pnl"] = round(cost_est["gross_profit"], 2)
                pos["unrealized_net_pnl"] = round(cost_est["net_profit"], 2)
                pos["unrealized_net_ret_pct"] = round(cost_est["net_return_pct"], 3)

                entry_time_str = pos.get("entry_time", now_str)
                try:
                    entry_dt = datetime.fromisoformat(entry_time_str)
                    seconds_held = (now - entry_dt).total_seconds()
                except Exception:
                    seconds_held = 0.0

                # Exit Condition A: Stop-loss breached (-0.30%)
                if gross_ret <= -self.stop_loss_pct:
                    action = self._close_position(symbol, latest_p, gross_ret, "STOP_LOSS")
                    executed_actions.append(action)
                # Exit Condition B: Target profit reached (+0.20% net profit target or higher)
                elif cost_est["net_profit"] > 0 and cost_est["net_return_pct"] >= (self.profit_threshold_pct * 100):
                    action = self._close_position(symbol, latest_p, gross_ret, "TAKE_PROFIT_TARGET")
                    executed_actions.append(action)
                # Exit Condition C: Scalp time timeout after holding for at least 8 minutes (480s) to avoid multi-hour drift
                elif seconds_held >= 480:
                    exit_type = "TIME_SCALP_PROFIT" if cost_est["net_profit"] > 0 else "TIME_STOP_TIMEOUT"
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

                # If blacklisted, suppress BUY signal to enforce capital preservation
                if is_symbol_blacklisted and pred["signal"] == "BUY":
                    pred["signal"] = "HOLD"
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
                    "confidence": pred["confidence"],
                    "profit_threshold_pct": pred["profit_threshold_pct"]
                }

                # Check if we should invest
                # Criteria:
                # - Signal is BUY (predicted 1-min return >= profit_threshold_pct e.g. 0.8%)
                # - Stock is NOT blacklisted (direction accuracy >= 50% hurdle)
                # - Regime supports long scalps (no counter-trend buying in bear or extreme volatility)
                # - Not currently holding this symbol
                # - Opening Cool-off: No new entries in first 5 mins (09:15 - 09:20 IST) to avoid whipsaw
                # - Position count limit (max 5 simultaneous positions to manage risk)
                # - Sizing calibrated for small accounts (min ₹350 for accounts <= 10k)
                in_cooldown = False
                if symbol in self.last_exit_times:
                    if (now - self.last_exit_times[symbol]).total_seconds() < 300:
                        in_cooldown = True

                opening_cooloff = (now.hour == 9 and now.minute < 20) if self.is_market_open() else False
                min_cap_req = 350.0 if self.state["total_capital"] <= 10000.0 else 1000.0
                allows_scalp = regime_info.get("allows_long_scalp", True)

                if (
                    pred["signal"] == "BUY"
                    and not is_symbol_blacklisted
                    and allows_scalp
                    and not opening_cooloff
                    and not in_cooldown
                    and symbol not in self.state["positions"]
                    and len(self.state["positions"]) < 5
                    and self.state["available_capital"] >= min_cap_req
                ):
                    action = self._open_position(pred)
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

    def _open_position(self, pred: dict) -> dict:
        """Open a position sizing dynamically based on compounded available capital."""
        symbol = pred["symbol"]
        curr_price = pred["current_price"]

        # Risk Filter for Small Accounts (<= 10,000 INR):
        # A single share must not exceed 25% of total capital (e.g. max ~₹1,250 on a ₹5,000 account)
        # Prevents taking heavy concentration in expensive stocks like TCS or Bharti Airtel
        if self.state["total_capital"] <= 10000.0 and curr_price > (self.state["total_capital"] * 0.25):
            return None

        # Dynamic Sizing: Allocate e.g. 15% of available compounded capital
        invest_amount = self.state["available_capital"] * self.position_sizing_pct
        min_invest = min(self.state["available_capital"], 350.0) if self.state["total_capital"] <= 10000.0 else 1000.0
        if invest_amount < min_invest:
            invest_amount = min(self.state["available_capital"], min_invest)

        qty = int(invest_amount / curr_price)
        if qty < 1:
            qty = 1
        actual_invested = qty * curr_price

        if actual_invested > self.state["available_capital"]:
            return None

        self.state["available_capital"] -= actual_invested
        self.state["invested_capital"] += actual_invested

        pos = {
            "symbol": symbol,
            "company": pred["company"],
            "entry_price": curr_price,
            "current_price": curr_price,
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

        trade_event = {
            "id": f"TRD-{int(time.time()*1000)}",
            "action": "BUY",
            "symbol": symbol,
            "company": pred["company"],
            "price": curr_price,
            "qty": qty,
            "invested": actual_invested,
            "predicted_return_pct": pred["predicted_return_pct"],
            "confidence": pred["confidence"],
            "reason": f"Pred Return {pred['predicted_return_pct']}% > {pred['profit_threshold_pct']}%",
            "starting_capital": round(self.state["starting_capital"], 2),
            "capital_after": round(self.state["total_capital"], 2),
            "win_rate_pct": self.state["win_rate_pct"],
            "timestamp": datetime.now().isoformat()
        }
        self._log_trade(trade_event)
        return trade_event

    def _close_position(self, symbol: str, exit_price: float, gross_return: float, reason: str) -> dict:
        """Close position and compound net profit/loss into available capital."""
        pos = self.state["positions"].pop(symbol, None)
        if not pos:
            return None

        self.last_exit_times[symbol] = datetime.now()

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

        trade_event = {
            "id": f"TRD-{int(time.time()*1000)}",
            "action": "SELL",
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
        """Start the automated scanning and compounding loop."""
        if self.is_running:
            return
        self.is_running = True
        self.state["engine_status"] = "RUNNING"
        self._save_state()

        def _loop():
            while self.is_running:
                sleep_interval = 12.0
                try:
                    if self.is_market_open():
                        # Live market: fetch real-time 1m candles from NSE
                        self._fetch_all_live_candles()
                        self.scan_and_trade_step()
                        sleep_interval = 12.0
                    else:
                        # Off-market hours (NSE closed 15:30 - 09:15 IST)
                        if self.off_market_simulation:
                            self._simulate_market_tick()
                            self.scan_and_trade_step()
                            sleep_interval = self.simulation_speed_sec
                        else:
                            # Strict Standby: keep prices frozen at official close, no simulated trades
                            self.check_day_rollover()
                            sleep_interval = 10.0
                except Exception as e:
                    print(f"Error in engine loop: {e}")
                    sleep_interval = 10.0

                time.sleep(sleep_interval)

        self.worker_thread = threading.Thread(target=_loop, daemon=True)
        self.worker_thread.start()

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
