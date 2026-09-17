import pandas as pd
import requests
import os
from datetime import datetime, timedelta

def fetch_recent_data(symbol, interval='1h', days=5):
    print(f"Fetching last {days} days of {symbol} {interval} data...")
    limit = days * 24 if interval == '1h' else days * 24 * 12
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    
    res = requests.get(url).json()
    df = pd.DataFrame(res, columns=['ot','o','h','l','c','v','ct','qv','nt','tbb','tbq','i'])
    for col in ['o','h','l','c','v','tbb','qv','tbq']: df[col] = df[col].astype(float)
    df['timestamp'] = pd.to_datetime(df['ot'], unit='ms')
    df['symbol'] = symbol
    df = df.rename(columns={'o':'open','h':'high','l':'low','c':'close','v':'volume','tbb':'taker_buy_base_asset_volume', 'nt':'number_of_trades', 'qv':'quote_asset_volume', 'tbq':'taker_buy_quote_asset_volume'})
    return df[['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume']]

def update_dataset():
    universe = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']
    all_recent = []
    for symbol in universe:
        df = fetch_recent_data(symbol)
        all_recent.append(df)
    
    new_data = pd.concat(all_recent, ignore_index=True)
    
    raw_path = 'QA/data/raw/klines/recent_institutional.parquet'
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    new_data.to_parquet(raw_path)
    print(f"Saved recent data to {raw_path}")

if __name__ == "__main__":
    update_dataset()
