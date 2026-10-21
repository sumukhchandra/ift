import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stocks_config import STOCK_SYMBOLS, STOCK_UNIVERSE, DEFAULT_CAPITAL, MIN_NET_PROFIT_PCT, MAX_GROSS_LOSS_PCT
from models.final_ensemble_engine import FinalEnsembleEngine
from risk.india_tax_engine import IndiaTaxEngine
from data.fetch_stock_data import add_stock_features, _flatten_columns, fetch_nifty_index_features
import yfinance as yf

class MasterProfitOptimizer:
    """
    The 'Money Maker' - Integrates all champion models into a single
    coordinated execution strategy to maximize net profits.
    """
    def __init__(self, initial_capital=100000.0):
        self.capital = initial_capital
        self.available_capital = initial_capital
        self.positions = {}
        self.trade_history = []
        self.tax_engine = IndiaTaxEngine()

        # Model Directory
        self.model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "saved_models")
        self.engine = None # Lazy load

    def _ensure_engine(self):
        if self.engine is None:
            try:
                self.engine = FinalEnsembleEngine(model_dir=self.model_dir)
            except Exception as e:
                print(f"Model load error: {e}")
                return False
        return True

    def simulate_day(self, date_str=None):
        """Simulates one trading day using the coordinated specialist approach."""
        if not self._ensure_engine(): return None

        # 1. Fetch Data
        print(f"Simulating Session: {date_str or 'Recent'}")
        raw_frames = []
        for symbol in STOCK_SYMBOLS:
            try:
                df = yf.download(symbol, period="5d", interval="5m", auto_adjust=False, progress=False)
                if df.empty: continue
                df = _flatten_columns(df.reset_index())
                time_col = "datetime" if "datetime" in df.columns else "date" if "date" in df.columns else "index"
                df = df.rename(columns={time_col: "timestamp", "adj close": "adj_close"})
                df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
                df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
                df["symbol"] = symbol
                raw_frames.append(df)
            except: continue

        if not raw_frames: return None
        combined = pd.concat(raw_frames, ignore_index=True)
        nifty_df = fetch_nifty_index_features(period="5d", interval="5m")
        feature_df = add_stock_features(combined, nifty_df=nifty_df)

        # Target just the most recent trading day
        last_date = feature_df["timestamp"].max().date()
        df_day = feature_df[feature_df["timestamp"].dt.date == last_date].copy()

        timestamps = sorted(df_day["timestamp"].unique())

        for ts in timestamps:
            group = df_day[df_day["timestamp"] == ts]
            price_map = group.set_index("symbol")["close"].to_dict()

            # --- 1. EXIT LOGIC (The Guard) ---
            for symbol in list(self.positions.keys()):
                if symbol not in price_map: continue
                curr_price = float(price_map[symbol])
                pos = self.positions[symbol]
                gross_ret = (curr_price - pos["entry_price"]) / pos["entry_price"]

                if gross_ret < -MAX_GROSS_LOSS_PCT:
                    # Stop Loss
                    res = self.tax_engine.calculate_total_cost(pos["invested"], gross_ret)
                    self.available_capital += (pos["invested"] + res["net_profit"])
                    self.trade_history.append({"symbol": symbol, "result": "STOP_LOSS", "pnl": res["net_profit"], "ts": ts})
                    del self.positions[symbol]
                elif gross_ret > 0:
                    # Take Profit
                    is_prof, bd = self.tax_engine.is_exit_profitable(pos["invested"], gross_ret, min_net_pct=MIN_NET_PROFIT_PCT)
                    if is_prof:
                        self.available_capital += (pos["invested"] + bd["net_profit"])
                        self.trade_history.append({"symbol": symbol, "result": "TAKE_PROFIT", "pnl": bd["net_profit"], "ts": ts})
                        del self.positions[symbol]

            # --- 2. ENTRY LOGIC (The Specialist Swarm) ---
            for symbol in STOCK_SYMBOLS:
                if symbol in self.positions: continue
                if self.available_capital < 1000: break

                # Get data for model
                symbol_data = df_day[df_day["symbol"] == symbol].sort_values("timestamp")
                window = symbol_data[symbol_data["timestamp"] <= ts].tail(50)
                if len(window) < 50: continue

                curr_price = float(window["close"].iloc[-1])

                # SPECIALIST ROUTING
                # 1. Time-based Specialists
                hour = ts.hour
                minute = ts.minute
                confidence = 0.0

                decision = self.engine.evaluate_state(window)
                prob = float(decision["final_probability"])
                exp_ret = float(decision.get("expected_return", 0))

                # Boost confidence based on specialist windows (SMC / HYPO logic)
                if 9 <= hour <= 10: # Morning specialist window
                    confidence = prob * 1.1
                elif 11 <= hour <= 13: # Midday specialist window
                    confidence = prob * 1.2
                else:
                    confidence = prob

                # Entry Gates
                if confidence >= 0.65 and exp_ret > 0.001:
                    # Position Sizing based on confidence
                    if confidence > 0.85: pct = 0.15 # High Confidence
                    elif confidence > 0.75: pct = 0.10 # Med Confidence
                    else: pct = 0.05 # Low Confidence

                    alloc = self.available_capital * pct
                    viable, cost_bd = self.tax_engine.is_trade_viable(alloc, exp_ret, min_net_pct=MIN_NET_PROFIT_PCT)

                    if viable:
                        self.positions[symbol] = {
                            "entry_price": curr_price,
                            "invested": alloc,
                            "entry_time": ts
                        }
                        self.available_capital -= alloc

        # EOD Close
        for symbol, pos in self.positions.items():
            last_price = df_day[df_day["symbol"] == symbol]["close"].iloc[-1]
            gross_ret = (last_price - pos["entry_price"]) / pos["entry_price"]
            res = self.tax_engine.calculate_total_cost(pos["invested"], gross_ret)
            self.available_capital += (pos["invested"] + res["net_profit"])
            self.trade_history.append({"symbol": symbol, "result": "EOD_CLOSE", "pnl": res["net_profit"], "ts": "EOD"})
            del self.positions[symbol]

        return self.available_capital - self.capital

if __name__ == "__main__":
    optimizer = MasterProfitOptimizer(initial_capital=100000.0)
    profit = optimizer.simulate_day()
    print(f"\nFINAL RESULT FOR TEST SESSION:")
    print(f"Net Profit: Rs.{profit:.2f}")
    print(f"Total Trades: {len(optimizer.trade_history)}")
    for t in optimizer.trade_history:
        print(f"{t['ts']} | {t['symbol']} | {t['result']} | PnL: Rs.{t['pnl']:.2f}")
