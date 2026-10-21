import json
import os
import sys
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Add path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stocks_config import STOCK_SYMBOLS, STOCK_UNIVERSE, DEFAULT_CAPITAL, MIN_NET_PROFIT_PCT, MAX_GROSS_LOSS_PCT
from models.final_ensemble_engine import FinalEnsembleEngine
from risk.india_tax_engine import IndiaTaxEngine
from data.fetch_stock_data import add_stock_features, _flatten_columns, fetch_nifty_index_features
import yfinance as yf

def run_yesterday_simulation():
    print("--- Starting Yesterday's Session Simulation ---")

    # 1. Setup
    capital = DEFAULT_CAPITAL
    available_capital = capital
    positions = {}
    trade_history = []
    tax_engine = IndiaTaxEngine()

    # Setup Engine
    model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "saved_models")
    try:
        engine = FinalEnsembleEngine(model_dir=model_dir)
    except Exception as e:
        print(f"Error loading models: {e}")
        return

    # 2. Fetch Data (Yesterday)
    # To simulate yesterday, we fetch 5d of data to have enough for features
    print("Fetching market data...")
    raw_frames = []
    for symbol in STOCK_SYMBOLS:
        try:
            df = yf.download(symbol, period="5d", interval="5m", auto_adjust=False, progress=False)
            if df.empty: continue
            df = _flatten_columns(df.reset_index())
            time_col = "datetime" if "datetime" in df.columns else "date" if "date" in df.columns else "index"
            df = df.rename(columns={time_col: "timestamp", "adj close": "adj_close"})
            required = ["timestamp", "open", "high", "low", "close", "volume"]
            df = df[required].copy()
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
            df["symbol"] = symbol
            raw_frames.append(df)
        except: continue

    if not raw_frames:
        print("No data fetched.")
        return

    combined = pd.concat(raw_frames, ignore_index=True)
    nifty_df = fetch_nifty_index_features(period="5d", interval="5m")
    feature_df = add_stock_features(combined, nifty_df=nifty_df)

    # Filter for yesterday's date only
    yesterday = (datetime.now() - timedelta(days=1)).date()
    df_yesterday = feature_df[feature_df["timestamp"].dt.date == yesterday].copy()

    if df_yesterday.empty:
        print("No data available for yesterday's session.")
        return

    # 3. Simulation Loop
    timestamps = sorted(df_yesterday["timestamp"].unique())

    for ts in timestamps:
        group = df_yesterday[df_yesterday["timestamp"] == ts]
        price_map = group.set_index("symbol")["close"].to_dict()

        # --- CHECK EXITS ---
        for symbol in list(positions.keys()):
            if symbol not in price_map: continue
            curr_price = float(price_map[symbol])
            pos = positions[symbol]
            gross_ret = (curr_price - pos["entry_price"]) / pos["entry_price"]

            if gross_ret < -MAX_GROSS_LOSS_PCT:
                # Stop Loss
                cost = tax_engine.calculate_total_cost(pos["invested"], gross_ret)
                net_profit = cost["net_profit"]
                available_capital += (pos["invested"] + net_profit)
                trade_history.append({"symbol": symbol, "result": "STOP_LOSS", "net_pnl": net_profit})
                del positions[symbol]
            elif gross_ret > 0:
                # Take Profit
                is_prof, breakdown = tax_engine.is_exit_profitable(pos["invested"], gross_ret, min_net_pct=MIN_NET_PROFIT_PCT)
                if is_prof:
                    net_profit = breakdown["net_profit"]
                    available_capital += (pos["invested"] + net_profit)
                    trade_history.append({"symbol": symbol, "result": "TAKE_PROFIT", "net_pnl": net_profit})
                    del positions[symbol]

        # --- CHECK ENTRIES ---
        for symbol in STOCK_SYMBOLS:
            if symbol in positions: continue
            if available_capital < 1000: break

            symbol_data = df_yesterday[df_yesterday["symbol"] == symbol].sort_values("timestamp")
            current_window = symbol_data[symbol_data["timestamp"] <= ts].tail(50)
            if len(current_window) < 50: continue

            curr_price = float(current_window["close"].iloc[-1])
            decision = engine.evaluate_state(current_window)
            prob = float(decision["final_probability"])
            exp_ret = float(decision.get("expected_return", 0))

            if prob >= 0.60 and exp_ret > 0.001:
                # Basic sizing: 10% of available capital
                alloc = available_capital * 0.10
                viable, cost_bd = tax_engine.is_trade_viable(alloc, exp_ret, min_net_pct=MIN_NET_PROFIT_PCT)

                if viable:
                    positions[symbol] = {
                        "entry_price": curr_price,
                        "invested": alloc,
                        "entry_time": ts
                    }
                    available_capital -= alloc

    # 4. Final Tally
    # Close all remaining positions at end of day
    for symbol, pos in positions.items():
        # Get last price of the day
        last_price = df_yesterday[df_yesterday["symbol"] == symbol]["close"].iloc[-1]
        gross_ret = (last_price - pos["entry_price"]) / pos["entry_price"]
        cost = tax_engine.calculate_total_cost(pos["invested"], gross_ret)
        net_profit = cost["net_profit"]
        available_capital += (pos["invested"] + net_profit)
        trade_history.append({"symbol": symbol, "result": "EOD_CLOSE", "net_pnl": net_profit})

    final_pnl = available_capital - capital
    print(f"\n--- Simulation Results for {yesterday} ---")
    print(f"Starting Capital: Rs.{capital:.2f}")
    print(f"Ending Capital:   Rs.{available_capital:.2f}")
    print(f"Net Profit/Loss:   Rs.{final_pnl:.2f} ({ (final_pnl/capital)*100 :.2f}%)")
    print(f"Total Trades:      {len(trade_history)}")

    for trade in trade_history:
        print(f"Trade {trade['symbol']}: {trade['result']} | PnL: Rs.{trade['net_pnl']:.2f}")

if __name__ == "__main__":
    run_yesterday_simulation()
