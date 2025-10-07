import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import glob
import sys

# --- Data Fetching Functions (copied from get_all_financial_data.py) ---

def fetch_data_with_finviz(ticker):
    """ Fallback function to get data by scraping the Finviz website. """
    try:
        url = f"https://finviz.com/quote.ashx?t={ticker}"
        headers = {'User-Agent': 'Mozilla/5.0'}
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
        return {'Ticker': ticker, 'ShortInterestPercent': short_percent, 'DaysToCover': parse_finviz_number(data.get('Short Ratio', '0')), 'Float_Shares': float_shares, 'MarketCap': parse_finviz_number(data.get('Market Cap', '0')), 'CurrentPrice': parse_finviz_number(data.get('Price', '0')), 'AvgVolume10Day': parse_finviz_number(data.get('Avg Volume', '0'))}
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
        return {'Ticker': ticker, 'ShortInterestPercent': round(short_percent * 100, 2), 'DaysToCover': info.get('shortRatio', 0), 'Float_Shares': float_shares, 'MarketCap': info.get('marketCap', 0), 'CurrentPrice': info.get('currentPrice', info.get('previousClose', 0)), 'AvgVolume10Day': info.get('averageDailyVolume10Day', 0)}
    except Exception:
        return None

def fetch_stock_data(ticker):
    """ Main fetch function that tries yfinance first, then falls back to Finviz. """
    data = fetch_data_with_yfinance(ticker)
    if data:
        return data
    return fetch_data_with_finviz(ticker)

# --- Squeeze Score Calculation ---

def calculate_squeeze_score(stock_data, peer_group_df):
    """ Calculates a Squeeze Score for a stock relative to its peer group. """
    if peer_group_df.empty:
        return 50.0 # Return a default score if there's no peer group

    stock_df_row = pd.DataFrame([stock_data])
    combined_group = pd.concat([peer_group_df, stock_df_row], ignore_index=True).drop_duplicates(subset=['Ticker'], keep='last')
    
    # Normalize metrics (0-1 scale, where 1 is better for a squeeze)
    # Handle cases where min == max to avoid division by zero
    max_si, min_si = combined_group['ShortInterestPercent'].max(), combined_group['ShortInterestPercent'].min()
    norm_si = (combined_group['ShortInterestPercent'] - min_si) / (max_si - min_si) if (max_si - min_si) > 0 else 0.5

    max_dtc, min_dtc = combined_group['DaysToCover'].max(), combined_group['DaysToCover'].min()
    norm_dtc = (combined_group['DaysToCover'] - min_dtc) / (max_dtc - min_dtc) if (max_dtc - min_dtc) > 0 else 0.5
    
    max_float, min_float = combined_group['Float_Shares'].max(), combined_group['Float_Shares'].min()
    # Invert for float: a lower float gets a higher score
    norm_float = 1 - ((combined_group['Float_Shares'] - min_float) / (max_float - min_float)) if (max_float - min_float) > 0 else 0.5
    
    # Weights from the MATLAB script
    weight_si = 0.50; weight_dtc = 0.30; weight_float = 0.20;
    
    combined_group['SqueezeScore'] = (norm_si * weight_si + norm_dtc * weight_dtc + norm_float * weight_float) * 100
    
    target_score = combined_group.loc[combined_group['Ticker'] == stock_data['Ticker'], 'SqueezeScore'].iloc[0]
    return target_score

def load_master_ticker_list():
    """ Loads and combines all tickers from the three provided CSV files. """
    print("Loading master ticker lists for validation...")
    try:
        df_nasdaq = pd.read_csv('nasdaq-listed.csv')
        df_nyse = pd.read_csv('nyse-listed.csv')
        df_other = pd.read_csv('other-listed.csv')

        nasdaq_tickers = set(df_nasdaq['Symbol'].dropna())
        nyse_tickers = set(df_nyse['ACT Symbol'].dropna())
        other_tickers = set(df_other['ACT Symbol'].dropna())
        
        master_list = nasdaq_tickers.union(nyse_tickers).union(other_tickers)
        print(f"Successfully loaded {len(master_list)} unique tickers for validation.\n")
        return master_list
    except FileNotFoundError:
        print("CRITICAL ERROR: Could not find one or more of the required ticker list CSVs (nasdaq-listed.csv, etc.).", file=sys.stderr)
        return None


# --- Main Program Logic ---

def main():
    """ Main function to run the interactive stock lookup tool. """
    master_ticker_set = load_master_ticker_list()
    if master_ticker_set is None:
        return # Exit if we can't load the validation lists

    try:
        list_of_files = glob.glob('full_market_data_*.csv')
        if not list_of_files:
            raise FileNotFoundError
        latest_file = max(list_of_files, key=os.path.getctime)
        print(f"Loading peer group data from: {latest_file}")
        all_financial_data = pd.read_csv(latest_file)
        peer_group = all_financial_data[(all_financial_data['CurrentPrice'] < 5) & (all_financial_data['CurrentPrice'] > 0)].copy()
        print(f"Successfully loaded {len(peer_group)} stocks into the peer group for scoring.\n")
    except (FileNotFoundError, ValueError):
        print("CRITICAL ERROR: No 'full_market_data_*.csv' file found.", file=sys.stderr)
        print("Please run 'get_all_financial_data.py' first to generate the necessary data file.", file=sys.stderr)
        return

    while True:
        ticker = input("Please enter a stock ticker (or type 'quit' to exit): ").strip().upper()
        if ticker in ['QUIT', 'EXIT']:
            break
        if not ticker:
            continue
            
        # --- NEW: VALIDATION STEP ---
        if ticker not in master_ticker_set:
            print(f"'{ticker}' is not a valid symbol in the provided ticker lists. Please check the spelling and try again.\n")
            continue

        print(f"\nPerforming live lookup for {ticker}...")
        live_data = fetch_stock_data(ticker)

        if not live_data:
            print(f"Could not retrieve live data for {ticker}. The stock may be delisted or data is unavailable.\n")
            continue

        live_data['SqueezeScore'] = calculate_squeeze_score(live_data, peer_group)

        def format_num(n):
            if n is None: return "N/A"
            if n >= 1e9: return f"{n / 1e9:.2f}B"
            if n >= 1e6: return f"{n / 1e6:.2f}M"
            if n >= 1e3: return f"{n / 1e3:.2f}K"
            return f"{n:.2f}"

        print("\n--- STOCK DATA LOOKUP ---")
        print(f"{'Ticker':<22}: {live_data['Ticker']}")
        print(f"{'Squeeze Score':<22}: {live_data['SqueezeScore']:.1f}")
        print(f"{'Short Interest (%)':<22}: {live_data['ShortInterestPercent']:.2f}")
        print(f"{'Days to Cover':<22}: {live_data['DaysToCover']:.2f}")
        print(f"{'Float':<22}: {format_num(live_data['Float_Shares'])}")
        print(f"{'Market Cap':<22}: {format_num(live_data['MarketCap'])}")
        print(f"{'Avg Volume':<22}: {format_num(live_data['AvgVolume10Day'])}")
        print(f"{'Current Price':<22}: {live_data['CurrentPrice']:.4f}")
        print("-------------------------\n")

if __name__ == '__main__':
    main()

