import yfinance as yf
import pandas as pd
import os
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import requests
from bs4 import BeautifulSoup

def get_tickers_from_local_files():
    """
    Reads nasdaq-listed.csv, nyse-listed.csv, and other-listed.csv files 
    directly from the local project folder to create a comprehensive master ticker list.
    """
    print("Reading master ticker list from local files (NASDAQ, NYSE, and Other Listed)...")
    
    required_files = ['nasdaq-listed.csv', 'nyse-listed.csv', 'other-listed.csv']
    if not all(os.path.exists(f) for f in required_files):
        print(f"\n--- ERROR --- Could not find one or more required files: {', '.join(required_files)}")
        print("Please ensure you have all three CSV files in the same folder as this script.")
        return []
        
    try:
        df_nasdaq = pd.read_csv('nasdaq-listed.csv')
        df_nasdaq.dropna(subset=['Symbol'], inplace=True)
        nasdaq_tickers = df_nasdaq[~df_nasdaq['Symbol'].str.contains(r'\$', na=False)]['Symbol'].tolist()

        df_nyse = pd.read_csv('nyse-listed.csv')
        df_nyse.dropna(subset=['ACT Symbol'], inplace=True)
        nyse_tickers = df_nyse[~df_nyse['ACT Symbol'].str.contains(r'\$', na=False)]['ACT Symbol'].tolist()

        df_other = pd.read_csv('other-listed.csv')
        df_other.dropna(subset=['ACT Symbol'], inplace=True)
        other_tickers = df_other[~df_other['ACT Symbol'].str.contains(r'\$', na=False)]['ACT Symbol'].tolist()

        combined_list = nasdaq_tickers + nyse_tickers + other_tickers
        unique_tickers = list(set(combined_list))
        random.shuffle(unique_tickers)
        
        print(f"Successfully loaded and processed {len(unique_tickers)} unique tickers from all sources.")
        return unique_tickers
        
    except Exception as e:
        print(f"An error occurred while reading local ticker files: {type(e).__name__} - {e}")
        return []

def fetch_data_with_finviz(ticker):
    """ Fallback function to get data by scraping the Finviz website. """
    try:
        url = f"https://finviz.com/quote.ashx?t={ticker}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')
        table = soup.find('table', class_='snapshot-table2')
        if not table: return None

        data = {cols[i].text.strip(): cols[i+1].text.strip() for row in table.find_all('tr') for i, cols in enumerate(row.find_all('td')) if i % 2 == 0}

        def parse_finviz_number(val_str):
            if val_str == '-': return 0
            val_str = val_str.upper().replace('%', '')
            if 'B' in val_str: return float(val_str.replace('B', '')) * 1e9
            if 'M' in val_str: return float(val_str.replace('M', '')) * 1e6
            if 'K' in val_str: return float(val_str.replace('K', '')) * 1e3
            return float(val_str)

        short_percent = parse_finviz_number(data.get('Short Float', '0'))
        float_shares = parse_finviz_number(data.get('Shs Float', '0'))
        
        if not short_percent or not float_shares: return None

        return {
            'Ticker': ticker,
            'ShortInterestPercent': short_percent,
            'DaysToCover': parse_finviz_number(data.get('Short Ratio', '0')),
            'Float_Shares': float_shares,
            'MarketCap': parse_finviz_number(data.get('Market Cap', '0')),
            'CurrentPrice': parse_finviz_number(data.get('Price', '0')),
            'AvgVolume10Day': parse_finviz_number(data.get('Avg Volume', '0')),
        }
    except Exception:
        return None

def fetch_data_with_yfinance(ticker):
    """ Primary function to get data using the yfinance library. """
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
            'DaysToCover': info.get('shortRatio', 0),
            'Float_Shares': float_shares,
            'MarketCap': info.get('marketCap', 0),
            'CurrentPrice': info.get('currentPrice', info.get('previousClose', 0)),
            'AvgVolume10Day': info.get('averageDailyVolume10Day', 0),
        }
    except Exception:
        return None

def fetch_stock_data(ticker):
    """ Main fetch function that tries yfinance first, then falls back to Finviz. """
    data = fetch_data_with_yfinance(ticker)
    if data:
        return data
    
    return fetch_data_with_finviz(ticker)

if __name__ == '__main__':
    all_tickers = get_tickers_from_local_files() 
    if not all_tickers:
        print("\nCould not retrieve ticker list. Exiting program.")
    else:
        print("\n--- Starting Bulk Data Fetch (with Finviz Fallback) ---")
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
            df = df[['Ticker', 'ShortInterestPercent', 'DaysToCover', 'Float_Shares', 
                     'MarketCap', 'CurrentPrice', 'AvgVolume10Day']]
            date_str = datetime.now().strftime("%Y-%m-%d")
            filename = f'full_market_data_US_Exchanges_{date_str}.csv'
            df.to_csv(filename, index=False)
            print(f"\nSuccessfully saved data for {len(df)} stocks to '{filename}'")
            print("This file contains all stocks that had available short interest and float data.")
            print("\nTop 5 rows of the new data file:")
            print(df.head())

