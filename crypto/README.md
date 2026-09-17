# 🚀 Free Crypto Trading Stack Simulation

This project simulates the complete, 100% free crypto trading stack utilizing the 8 layers. Since we cannot automatically create your API keys or deploy to the cloud directly here, this simulation executes a mock pipeline of how these tools interact locally on your machine.

## 🛠️ The 8 Layers Included

1. **Layer 1 (Data):** Simulates fetching data from Binance and CoinGecko (via CCXT/API wrappers) and scraping Reddit sentiment via PRAW.
2. **Layer 2 (Indicators & Storage):** Uses `pandas-ta` for 100+ technical indicators and `SQLite` for zero-setup local storage of market data and trades.
3. **Layer 3 (Prediction Model):** Simulates AI price prediction (LSTM/LightGBM/Prophet) by analyzing the indicator data.
4. **Layer 4 (Risk & Execution):** Simulates a trade engine (like Freqtrade/Jesse) executing logic based on the AI predictions.
5. **Layer 5 (Personal AI Assistant):** Simulates sending the trade rationale to an LLM (Groq/Ollama) for insights and confirmations.
6. **Layer 6 (Alerts):** Simulates triggering a Telegram bot alert (`python-telegram-bot`) with the trade action and AI insight.
7. **Layer 7 (Dashboard):** Provides a Streamlit app to visualize the real-time data and trades stored in your SQLite database.
8. **Layer 8 (Deployment):** Prints instructions for deploying this to an Oracle Cloud Always Free VM or similar free-tier hosting.

## 🏃‍♂️ How to Run the Simulation

**1. Install Dependencies**
```bash
pip install -r requirements.txt
```

**2. Run the Core Stack Simulation (Layers 1-6 & 8)**
```bash
python simulate_layers.py
```
*This will fetch mock data, calculate indicators, make an AI prediction, simulate a trade, log it to SQLite, consult an AI, and simulate a Telegram alert.*

**3. Launch the Dashboard (Layer 7)**
```bash
streamlit run dashboard.py
```
*This will open a local web app where you can view your "live" mock data, charts, and the trades executed by your bot.*

## 📈 Taking it to Production

When you are ready to use real money or the Binance Testnet:
- Sign up for Groq (Layer 5) for a free API key.
- Create a Telegram bot using BotFather (Layer 6).
- Set up an Oracle Cloud VM (Layer 8) to run it 24/7.
- Replace the mock data generation in `simulate_layers.py` with actual API calls to CCXT/Binance.