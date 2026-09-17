import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go

# --- Layer 7: Dashboard ---
st.set_page_config(page_title="Crypto AI Bot Dashboard", layout="wide")
st.title("📈 Crypto Trading Bot Dashboard (Layer 7)")
st.markdown("This dashboard reads live data and trades from your local SQLite database (Layer 2) populated by your AI stack.")

# Fetch data from SQLite
def load_data():
    try:
        conn = sqlite3.connect('crypto_trading.db')
        df = pd.read_sql('SELECT * FROM market_data', conn)
        trades = pd.read_sql('SELECT * FROM trades', conn)
        conn.close()
        return df, trades
    except Exception as e:
        st.warning("No data found yet. Run `python simulate_layers.py` first!")
        return None, None

df, trades = load_data()

if df is not None:
    st.subheader("Market Data & Indicators")
    st.dataframe(df.tail(10))
    
    st.subheader("Recent Trades (Layer 4)")
    st.dataframe(trades)

    # Basic Candlestick chart mock using Plotly
    st.subheader("Price Action")
    fig = go.Figure(data=[go.Candlestick(x=df['index'],
                    open=df['open'],
                    high=df['high'],
                    low=df['low'],
                    close=df['close'])])
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.markdown("**Powered by:** Binance (Data), pandas-ta (Indicators), Streamlit (Dashboard), SQLite (Storage).")
