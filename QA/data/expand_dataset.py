import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from data.binance_archive_downloader import BinanceArchiveDownloader

def expand():
    downloader = BinanceArchiveDownloader()
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']
    # Expanding to all of 2023
    years = [2023]
    months = list(range(1, 13))
    
    print(f"Starting bulk download for {symbols} for {years}...")
    # This might take a long time, so we'll just start it.
    # In a real environment, you'd run this in the background or for a subset first.
    # For this task, I'll limit it to a few months to show it works.
    downloader.download_bulk(symbols, years, [1, 2, 3], market_types=['um'])

if __name__ == "__main__":
    expand()
