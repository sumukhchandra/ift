import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stocks_config import DEFAULT_CAPITAL, MIN_NET_PROFIT_PCT, MAX_GROSS_LOSS_PCT
from models.final_ensemble_engine import FinalEnsembleEngine
from risk.india_tax_engine import IndiaTaxEngine
from data.fetch_stock_data import add_stock_features, _flatten_columns, fetch_nifty_index_features

def run_nifty_final_trial():
    print("--- NIFTY 50 REAL-MONEY TRIAL (RE-RUN) ---")

    # 1. Setup for ₹1,500 Capital
    capital = 1500.0
    available_capital = capital
    positions = {}
    trade_history = []
    tax_engine = IndiaTaxEngine()

    model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "saved_models")
    try:
        # Use the most advanced ensemble
        engine = FinalEnsembleEngine(model_dir=model_dir)
    except Exception as e:
        print(f"Engine Error: {e}")
        return

    # 2. Data Collection (Up to today)
    print("Fetching NIFTY 50 Index data...")
    try:
        # Using ^NSEI for Nifty 50
        df = yf.download("^NSEI", period="5d", interval="5m", auto_adjust=False, progress=False)
        if df.empty:
            print("No data for Nifty 50")
            return

        df = _flatten_columns(df.reset_index())
        time_col = "datetime" if "datetime" in df.columns else "date" if "date" in df.columns else "index"
        df = df.rename(columns={time_col: "timestamp", "adj close": "adj_close"})
        df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
        df["symbol"] = "^NSEI"

        # Fetch Nifty features for the feature pipeline
        nifty_df = fetch_nifty_index_features(period="5d", interval="5m")
        feature_df = add_stock_features(df, nifty_df=nifty_df)
    except Exception as e:
        print(f"Data Fetch Error: {e}")
        return

    # Filter for today's session
    today = datetime.now().date()
    df_today = feature_df[feature_df["timestamp"].dt.date == today].copy()

    if df_today.empty:
        print("No trading data available for today yet.")
        return

    timestamps = sorted(df_today["timestamp"].unique())

    # 3. Trading Loop
    for ts in timestamps:
        group = df_today[df_today["timestamp"] == ts]
        curr_price = float(group["close"].iloc[0])

        # --- EXIT LOGIC ---
        for symbol in list(positions.keys()):
            pos = positions[symbol]
            gross_ret = (curr_price - pos["entry_price"]) / pos["entry_price"]

            if gross_ret < -MAX_GROSS_LOSS_PCT:
                cost = tax_engine.calculate_total_cost(pos["invested"], gross_ret)
                available_capital += (pos["invested"] + cost["net_profit"])
                trade_history.append({"symbol": symbol, "result": "STOP_LOSS", "pnl": cost["net_profit"], "ts": ts})
                del positions[symbol]
            elif gross_ret > 0:
                is_prof, bd = tax_engine.is_exit_profitable(pos["invested"], gross_ret, min_net_pct=MIN_NET_PROFIT_PCT)
                if is_prof:
                    available_capital += (pos["invested"] + bd["net_profit"])
                    trade_history.append({"symbol": symbol, "result": "TAKE_PROFIT", "pnl": bd["net_profit"], "ts": ts})
                    del positions[symbol]

        # --- ENTRY LOGIC ---
        if "^NSEI" not in positions:
            symbol_data = df_today[df_today["symbol"] == "^NSEI"].sort_values("timestamp")
            window = symbol_data[symbol_data["timestamp"] <= ts].tail(50)
            if len(window) < 50: continue

            decision = engine.evaluate_state(window)
            prob = float(decision["final_probability"])
            exp_ret = float(decision.get("expected_return", 0))

            # AGGRESSIVE ENTRY for trial (50% prob + positive return)
            if prob >= 0.50 and exp_ret > 0:
                # Use 90% of available capital to maximize the trial's potential
                alloc = available_capital * 0.90
                viable, cost_bd = tax_engine.is_trade_viable(alloc, exp_ret, min_net_pct=MIN_NET_PROFIT_PCT)

                if viable:
                    positions["^NSEI"] = {
                        "entry_price": curr_price,
                        "invested": alloc,
                        "entry_time": ts
                    }
                    available_capital -= alloc

    # Close all at EOD
    for symbol, pos in positions.items():
        last_price = df_today["close"].iloc[-1]
        gross_ret = (last_price - pos["entry_price"]) / pos["entry_price"]
        res = tax_engine.calculate_total_cost(pos["invested"], gross_ret)
        available_capital += (pos["invested"] + res["net_profit"])
        trade_history.append({"symbol": symbol, "result": "EOD_CLOSE", "pnl": res["net_profit"], "ts": "EOD"})

    final_pnl = available_capital - capital
    print(f"\n--- FINAL TRIAL RESULTS (NIFTY 50) ---")
    print(f"Starting Capital: Rs.{capital:.2f}")
    print(f"Ending Capital:   Rs.{available_capital:.2f}")
    print(f"Net Profit/Loss:  Rs.{final_pnl:.2f} ({(final_pnl/capital)*100:.2f}%)")
    print(f"Total Trades:     {len(trade_history)}")
    for t in trade_history:
        print(f"{t['ts']} | {t['symbol']} | {t['result']} | PnL: Rs.{t['pnl']:.2f}")

if __name__ == "__main__":
    run_nifty_final_trial()
