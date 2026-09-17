import time
import datetime
import sqlite3
import pandas as pd
import numpy as np

# --- Layer 1: Data ---
def fetch_mock_data():
    print("[Layer 1] Fetching data via CCXT/Binance/CoinGecko APIs...")
    # Simulating data fetch from Binance and CoinGecko
    dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq='h')
    df = pd.DataFrame({
        'open': np.random.uniform(60000, 65000, 100),
        'high': np.random.uniform(65000, 66000, 100),
        'low': np.random.uniform(59000, 60000, 100),
        'close': np.random.uniform(60000, 65000, 100),
        'volume': np.random.uniform(100, 1000, 100)
    }, index=dates)
    
    print("[Layer 1] Fetching Reddit sentiment via PRAW...")
    sentiment_score = np.random.uniform(0.1, 0.9)
    print(f" -> Mock Sentiment Score: {sentiment_score:.2f}")
    return df, sentiment_score

# --- Layer 2: Indicators & Storage ---
def calculate_indicators(df):
    print("[Layer 2] Calculating indicators using pandas...")
    df['SMA_10'] = df['close'].rolling(window=10, min_periods=10).mean()

    delta = df['close'].diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.rolling(window=14, min_periods=14).mean()
    avg_loss = losses.rolling(window=14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df['RSI_14'] = 100 - (100 / (1 + rs))

    ema_fast = df['close'].ewm(span=12, adjust=False).mean()
    ema_slow = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD_12_26_9'] = ema_fast - ema_slow
    df['MACDs_12_26_9'] = df['MACD_12_26_9'].ewm(span=9, adjust=False).mean()
    df['MACDh_12_26_9'] = df['MACD_12_26_9'] - df['MACDs_12_26_9']
    
    print("[Layer 2] Saving to SQLite database...")
    conn = sqlite3.connect('crypto_trading.db')
    df.to_sql('market_data', conn, if_exists='replace')
    conn.close()
    return df

# --- Layer 3: Prediction Model ---
def run_prediction_models(df):
    print("[Layer 3] Running prediction models (Mocking LSTM/LightGBM/Prophet)...")
    # In reality, this would load a Keras/LightGBM model from Google Colab training
    latest_rsi = df['RSI_14'].iloc[-1]
    prediction = "BULLISH" if latest_rsi < 30 else ("BEARISH" if latest_rsi > 70 else "NEUTRAL")
    confidence = np.random.uniform(0.5, 0.99)
    print(f" -> Model Prediction: {prediction} (Confidence: {confidence:.2f})")
    return prediction

# --- Layer 4: Risk & Execution ---
def execute_trade(prediction):
    print("[Layer 4] Executing trade logic via Freqtrade/Jesse on Binance Testnet...")
    if prediction == "BULLISH":
        action = "BUY 0.01 BTC"
        print(f" -> Executing: {action}")
    elif prediction == "BEARISH":
        action = "SELL 0.01 BTC"
        print(f" -> Executing: {action}")
    else:
        action = "HOLD"
        print(f" -> Executing: {action}")
    
    # Log trade to db
    conn = sqlite3.connect('crypto_trading.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS trades (timestamp TEXT, action TEXT)')
    cursor.execute('INSERT INTO trades VALUES (?, ?)', (str(datetime.datetime.now()), action))
    conn.commit()
    conn.close()
    return action

# --- Layer 5: Personal AI Assistant ---
def query_ai_assistant(action, sentiment):
    print("[Layer 5] Consulting AI Assistant (Ollama/Groq)...")
    prompt = f"The trading bot decided to {action}. Reddit sentiment is {sentiment:.2f}. What do you think?"
    print(f" -> Prompt sent to AI: '{prompt}'")
    
    mock_responses = [
        "This looks like a solid move based on current RSI levels.",
        "Sentiment is a bit weak, ensure your stop-losses are tight.",
        "A reasonable execution given the model's confidence."
    ]
    ai_response = np.random.choice(mock_responses)
    print(f" -> AI Assistant says: '{ai_response}'")
    return ai_response

# --- Layer 6: Alerts ---
def send_telegram_alert(action, ai_response):
    print("[Layer 6] Sending alert via python-telegram-bot...")
    message = f"🚨 Trade Alert: {action}\n🤖 AI Insight: {ai_response}"
    print(f" -> Mock Telegram Message Sent:\n{message}")

# --- Main Pipeline ---
def run_simulation():
    print("="*50)
    print("🚀 STARTING CRYPTO STACK SIMULATION")
    print("="*50)
    
    df, sentiment = fetch_mock_data()
    time.sleep(1)
    
    df_with_indicators = calculate_indicators(df)
    time.sleep(1)
    
    prediction = run_prediction_models(df_with_indicators)
    time.sleep(1)
    
    action = execute_trade(prediction)
    time.sleep(1)
    
    ai_response = query_ai_assistant(action, sentiment)
    time.sleep(1)
    
    send_telegram_alert(action, ai_response)
    
    print("="*50)
    print("✅ SIMULATION COMPLETE. To view Layer 7 (Dashboard), run: streamlit run dashboard.py")
    print("☁️ For Layer 8 (Deployment), push this to Oracle Cloud Always Free VM.")

if __name__ == "__main__":
    run_simulation()
