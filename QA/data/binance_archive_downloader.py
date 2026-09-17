import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import zipfile
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from io import BytesIO
import pyarrow as pa
import pyarrow.parquet as pq
import tempfile

class BinanceArchiveDownloader:
    def __init__(self, raw_dir='data/raw'):
        self.raw_dir = raw_dir
        os.makedirs(self.raw_dir, exist_ok=True)
        
        # Setup requests session with retry logic
        self.session = requests.Session()
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[ 502, 503, 504 ])
        self.session.mount('http://', HTTPAdapter(max_retries=retries))
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        
        self.manifest_path = os.path.join(self.raw_dir, 'manifest.parquet')
        self.manifest = []
        if os.path.exists(self.manifest_path):
            try:
                self.manifest = pd.read_parquet(self.manifest_path).to_dict('records')
            except:
                pass
            
    def update_manifest(self, record):
        self.manifest.append(record)
        df = pd.DataFrame(self.manifest)
        df.to_parquet(self.manifest_path, engine='pyarrow', compression='zstd')
        
    def _get_path(self, market_type, data_type, symbol, interval=None):
        if market_type == 'spot':
            base = os.path.join(self.raw_dir, 'spot', data_type)
        else:
            base = os.path.join(self.raw_dir, 'futures', market_type, data_type)
        
        if interval:
            base = os.path.join(base, interval)
        
        os.makedirs(base, exist_ok=True)
        return base

    def download_monthly_klines(self, symbol, interval, year, month, market_type='spot'):
        month_str = f"{month:02d}"
        filename = f"{symbol}-{interval}-{year}-{month_str}"
        
        if market_type == 'spot':
            url = f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/{interval}/{filename}.zip"
        else:
            url = f"https://data.binance.vision/data/futures/{market_type}/monthly/klines/{symbol}/{interval}/{filename}.zip"
            
        target_dir = self._get_path(market_type, 'klines', symbol, interval)
        target_parquet = os.path.join(target_dir, f"{filename}.parquet")
        
        if os.path.exists(target_parquet):
            return True
            
        print(f"Downloading {url}...")
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code != 200:
                print(f"Failed to download {url}. Status code: {response.status_code}")
                return False
                
            with zipfile.ZipFile(BytesIO(response.content)) as z:
                csv_filename = z.namelist()[0]
                with z.open(csv_filename) as f:
                    columns = [
                        'open_time', 'open', 'high', 'low', 'close', 'volume',
                        'close_time', 'quote_asset_volume', 'number_of_trades',
                        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                    ]
                    df = pd.read_csv(f, names=columns)
                    
                    # Force numeric types and handle headers
                    for col in ['open', 'high', 'low', 'close', 'volume', 'quote_asset_volume', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    for col in ['open_time', 'close_time', 'number_of_trades']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    
                    df = df.dropna(subset=['open_time', 'close'])
                    
                    # Convert types for efficiency
                    for col in ['open', 'high', 'low', 'close', 'volume', 'quote_asset_volume', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume']:
                        df[col] = df[col].astype('float32')
                    for col in ['open_time', 'close_time', 'number_of_trades']:
                        df[col] = df[col].astype('int64')
                    
                    df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
                    df['symbol'] = symbol
                    df['data_version'] = '1.0'
                    df['downloaded_at'] = pd.Timestamp.utcnow()
                    
                    self.validate_klines(df, filename)
                    
                    df.to_parquet(target_parquet, engine='pyarrow', compression='zstd')
                    self.update_manifest({
                        'filename': filename, 'symbol': symbol, 'interval': interval,
                        'type': 'klines', 'market': market_type, 'year': year, 'month': month,
                        'row_count': len(df), 'downloaded_at': datetime.utcnow().isoformat()
                    })
            return True
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            return False

    def validate_klines(self, df, filename):
        duplicates = df['open_time'].duplicated().sum()
        if duplicates > 0:
            print(f"[!] WARNING: Found {duplicates} duplicate timestamps in {filename}")
        diffs = df['open_time'].diff().dropna()
        if not diffs.empty:
            most_common_diff = diffs.value_counts().idxmax()
            missing = (diffs > most_common_diff).sum()
            if missing > 0:
                print(f"[!] WARNING: Found {missing} gaps in {filename}")

    def download_monthly_trades(self, symbol, year, month, market_type='spot', data_type='aggTrades'):
        month_str = f"{month:02d}"
        filename = f"{symbol}-{data_type}-{year}-{month_str}"
        
        if market_type == 'spot':
            url = f"https://data.binance.vision/data/spot/monthly/{data_type}/{symbol}/{filename}.zip"
        else:
            url = f"https://data.binance.vision/data/futures/{market_type}/monthly/{data_type}/{symbol}/{filename}.zip"
            
        target_dir = self._get_path(market_type, data_type, symbol)
        target_parquet = os.path.join(target_dir, f"{filename}.parquet")
        
        if os.path.exists(target_parquet):
            return True
            
        print(f"Downloading {url}...")
        try:
            with tempfile.TemporaryDirectory() as tmpdirname:
                zip_path = os.path.join(tmpdirname, "temp.zip")
                with self.session.get(url, stream=True, timeout=120) as r:
                    if r.status_code != 200:
                        print(f"Failed to download {url}. Status: {r.status_code}")
                        return False
                    with open(zip_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=65536): 
                            f.write(chunk)
                            
                with zipfile.ZipFile(zip_path, 'r') as z:
                    csv_filename = z.namelist()[0]
                    z.extract(csv_filename, tmpdirname)
                    csv_path = os.path.join(tmpdirname, csv_filename)
                    
                    if data_type == 'aggTrades':
                        columns = ['agg_trade_id', 'price', 'quantity', 'first_trade_id', 'last_trade_id', 'transact_time', 'is_buyer_maker', 'is_best_match']
                    elif data_type == 'fundingRate':
                        columns = ['calc_time', 'funding_interval_hours', 'last_funding_rate']
                    else:
                        columns = None # Let pandas infer
                        
                    writer = None
                    total_rows = 0
                    for chunk in pd.read_csv(csv_path, names=columns, chunksize=1000000):
                        if data_type == 'aggTrades':
                            chunk['price'] = pd.to_numeric(chunk['price'], errors='coerce')
                            chunk['quantity'] = pd.to_numeric(chunk['quantity'], errors='coerce')
                            chunk = chunk.dropna(subset=['price', 'quantity'])
                            chunk['timestamp'] = pd.to_datetime(pd.to_numeric(chunk['transact_time'], errors='coerce'), unit='ms', utc=True)
                            # Ensure all columns are converted to types that Parquet handles well
                            if 'agg_trade_id' in chunk.columns:
                                chunk['agg_trade_id'] = chunk['agg_trade_id'].astype(str)
                            if 'first_trade_id' in chunk.columns:
                                chunk['first_trade_id'] = chunk['first_trade_id'].astype(str)
                            if 'last_trade_id' in chunk.columns:
                                chunk['last_trade_id'] = chunk['last_trade_id'].astype(str)
                        elif data_type == 'fundingRate':
                            chunk['last_funding_rate'] = pd.to_numeric(chunk['last_funding_rate'], errors='coerce')
                            chunk = chunk.dropna(subset=['last_funding_rate'])
                            chunk['timestamp'] = pd.to_datetime(pd.to_numeric(chunk['calc_time'], errors='coerce'), unit='ms', utc=True)
                        
                        if chunk.empty: continue
                        chunk['symbol'] = symbol
                        table = pa.Table.from_pandas(chunk, preserve_index=False)
                        if writer is None:
                            writer = pq.ParquetWriter(target_parquet, table.schema, compression='zstd')
                        writer.write_table(table)
                        total_rows += len(chunk)
                        
                    if writer: writer.close()
                    
                    self.update_manifest({
                        'filename': filename, 'symbol': symbol, 'type': data_type,
                        'market': market_type, 'year': year, 'month': month,
                        'row_count': total_rows, 'downloaded_at': datetime.utcnow().isoformat()
                    })
            return True
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            return False

    def download_daily_data(self, symbol, data_type, year, month, day, market_type='um'):
        # Used for metrics and forceOrders which are daily only
        date_str = f"{year}-{month:02d}-{day:02d}"
        filename = f"{symbol}-{data_type}-{date_str}"
        url = f"https://data.binance.vision/data/futures/{market_type}/daily/{data_type}/{symbol}/{filename}.zip"
        
        target_dir = self._get_path(market_type, data_type, symbol)
        target_parquet = os.path.join(target_dir, f"{filename}.parquet")
        
        if os.path.exists(target_parquet):
            return True
            
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code != 200:
                return False
                
            with zipfile.ZipFile(BytesIO(response.content)) as z:
                csv_filename = z.namelist()[0]
                with z.open(csv_filename) as f:
                    df = pd.read_csv(f)
                    if data_type == 'metrics':
                        df['timestamp'] = pd.to_datetime(df['create_time'], unit='ms', utc=True)
                    elif data_type == 'forceOrders':
                        df['timestamp'] = pd.to_datetime(df['time'], unit='ms', utc=True)
                    
                    df['symbol'] = symbol
                    df.to_parquet(target_parquet, engine='pyarrow', compression='zstd')
            return True
        except:
            return False

    def download_bulk(self, symbols, years, months, market_types=['spot', 'um']):
        for symbol in symbols:
            for year in years:
                for month in months:
                    for market in market_types:
                        # Klines
                        self.download_monthly_klines(symbol, '5m', year, month, market)
                        self.download_monthly_klines(symbol, '1h', year, month, market)
                        
                        # AggTrades
                        self.download_monthly_trades(symbol, year, month, market, 'aggTrades')
                        
                        if market != 'spot':
                            # Funding Rate (Monthly)
                            self.download_monthly_trades(symbol, year, month, market, 'fundingRate')
                            
                            # Metrics & ForceOrders (Daily)
                            # We'll just download all days for the month
                            last_day = (datetime(year, month, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                            for day in range(1, last_day.day + 1):
                                self.download_daily_data(symbol, 'metrics', year, month, day, market)
                                self.download_daily_data(symbol, 'forceOrders', year, month, day, market)

if __name__ == "__main__":
    downloader = BinanceArchiveDownloader()
    # Example: 1 month for BTC and ETH
    downloader.download_bulk(['BTCUSDT', 'ETHUSDT'], [2024], [1])
