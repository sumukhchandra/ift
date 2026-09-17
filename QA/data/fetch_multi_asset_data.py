import pandas as pd
import requests
import os
import time
from datetime import datetime, timedelta

def fetch_klines(symbol, interval='5m', limit=1000):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    data = response.json()
    
    df = pd.DataFrame(data, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    
    for col in ['open', 'high', 'low', 'close', 'volume', 'quote_asset_volume', 'taker_buy_base_asset_volume']:
        df[col] = df[col].astype(float)
        
    df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
    df['symbol'] = symbol
    return df

def main():
    universe = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']
    all_data = []
    
    print(f"Fetching fresh data for: {', '.join(universe)}")
    
    for symbol in universe:
        print(f"  - Fetching {symbol}...")
        try:
            df = fetch_klines(symbol)
            all_data.append(df)
            time.sleep(0.5) # Rate limit safety
        except Exception as e:
            print(f"    Error fetching {symbol}: {e}")
            
    if all_data:
        master_df = pd.concat(all_data, ignore_index=True)
        os.makedirs('QA/data/raw/live_update', exist_ok=True)
        path = 'QA/data/raw/live_update/multi_asset_raw.parquet'
        master_df.to_parquet(path)
        print(f"\nSaved {len(master_df)} rows to {path}")
    else:
        print("No data fetched.")

if __name__ == "__main__":
    main()
