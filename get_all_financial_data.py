import yfinance as yf
import pandas as pd
import requests
import io
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import os
import random # Import the random module for shuffling

# --- FINAL, FOOLPROOF METHOD: READ LOCAL CSV FILES ---
def get_tickers_from_local_files():
    """
    Reads the nasdaq-listed.csv and nyse-listed.csv files directly from the
    local project folder. This is the most reliable method.
    """
    print("Reading master ticker list from local CSV files (nasdaq-listed.csv, nyse-listed.csv)...")
    
    nasdaq_file = 'nasdaq-listed.csv'
    nyse_file = 'nyse-listed.csv'
    
    if not os.path.exists(nasdaq_file) or not os.path.exists(nyse_file):
        print("\n--- ERROR ---")
        print(f"Could not find '{nasdaq_file}' or '{nyse_file}' in the current directory.")
        print("Please ensure you have downloaded both CSV files and placed them in the same folder as this script.")
        return []
        
    all_tickers = []
    
    try:
        df_nasdaq = pd.read_csv(nasdaq_file)
        df_nasdaq.dropna(subset=['Symbol'], inplace=True)
        df_nasdaq_clean = df_nasdaq[~df_nasdaq['Symbol'].str.contains(r'\$', na=False)]
        nasdaq_tickers = df_nasdaq_clean['Symbol'].tolist()

        df_nyse = pd.read_csv(nyse_file)
        df_nyse.dropna(subset=['ACT Symbol'], inplace=True)
        df_nyse_clean = df_nyse[~df_nyse['ACT Symbol'].str.contains(r'\$', na=False)]
        other_tickers = df_nyse_clean['ACT Symbol'].tolist()

        # FIX: Combine and SHUFFLE the list instead of sorting it.
        unique_tickers = list(set(nasdaq_tickers + other_tickers))
        random.shuffle(unique_tickers) # This is the key change
        all_tickers = unique_tickers
        
        print(f"Successfully loaded and processed {len(all_tickers)} unique tickers from local files.")
        return all_tickers
        
    except Exception as e:
        print(f"An error occurred while reading or parsing the local ticker files: {type(e).__name__} - {e}")
        return []

# --- Function to fetch data for a SINGLE ticker ---
def fetch_stock_data(ticker):
    """
    Fetches the required financial metrics for a single stock ticker.
    Returns a dictionary or None if data is incomplete or an error occurs.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        short_percent = info.get('shortPercentOfFloat')
        float_shares = info.get('floatShares')

        if short_percent is None or float_shares is None or float_shares == 0:
            return None

        return {
            'Ticker': ticker,
            'ShortInterestPercent': round(short_percent * 100, 2),
            'DaysToCover': round(info.get('shortRatio', 0), 2),
            'Float_Shares': float_shares,
            'MarketCap': info.get('marketCap', 0),
            'CurrentPrice': info.get('currentPrice', info.get('previousClose', 0)),
            'AvgVolume10Day': info.get('averageDailyVolume10Day', 0),
        }
    except Exception:
        return None

# --- Main execution block ---
if __name__ == '__main__':
    all_tickers = get_tickers_from_local_files() 
    
    if not all_tickers:
        print("\nCould not retrieve ticker list. Exiting program.")
    else:
        print("\n--- Starting Bulk Data Fetch for Squeeze Metrics ---")
        print("This will screen thousands of stocks and may take a significant amount of time.")
        print("Progress bar is shown below:")

        all_stock_data = []
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            future_to_ticker = {executor.submit(fetch_stock_data, ticker): ticker for ticker in all_tickers}
            
            for future in tqdm(as_completed(future_to_ticker), total=len(all_tickers), desc="Screening Stocks"):
                result = future.result()
                if result:
                    all_stock_data.append(result)

        print("\n--- Data Fetching Complete ---")
        
        if not all_stock_data:
            print("No stocks with valid short squeeze data were found.")
        else:
            df = pd.DataFrame(all_stock_data)

            df = df[[
                'Ticker', 'ShortInterestPercent', 'DaysToCover', 'Float_Shares', 
                'MarketCap', 'CurrentPrice', 'AvgVolume10Day'
            ]]

            date_str = datetime.now().strftime("%Y-%m-%d")
            filename = f'full_market_data_US_Exchanges_{date_str}.csv'
            
            df.to_csv(filename, index=False)
            
            print(f"\nSuccessfully saved data for {len(df)} stocks to '{filename}'")
            print("This file contains all stocks that had available short interest and float data.")
            print("\nTop 5 rows of the new data file:")
            print(df.head())

