import requests
import os
import sys
import asyncio
from requests_html import AsyncHTMLSession

def get_marketaux_news_sync(ticker, api_token):
    """
    Synchronous function to fetch news from MarketAux. 
    This is run in a separate thread to avoid blocking async operations.
    """
    url = f"https://api.marketaux.com/v1/news/all?symbols={ticker}&filter_entities=true&limit=10&api_token={api_token}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        articles = response.json().get('data', [])
        return [article['title'] for article in articles]
    except Exception:
        return [] # Fail silently if the API call doesn't work

async def get_google_news(session, ticker):
    """
    Asynchronously scrapes Google News for headlines.
    """
    search_query = f'"{ticker} stock news"'
    url = f"https://news.google.com/search?q={search_query}&hl=en-US&gl=US&ceid=US%3Aen"
    try:
        r = await session.get(url, timeout=30)
        await r.html.arender(sleep=2, timeout=30)
        
        headlines = []
        articles = r.html.find('h4 > a')
        for link in articles:
            title = link.text.strip()
            if title:
                headlines.append(title)
        return headlines[:15]
    except Exception:
        return [] # Fail silently if scraping doesn't work

async def get_all_news(ticker, api_token):
    """
    Orchestrates fetching news from all sources in parallel.
    """
    browser_args = ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--no-zygote']
    session = AsyncHTMLSession(browser_args=browser_args)
    
    try:
        print(f"Fetching news for {ticker.upper()} from all sources (this may take a moment)...")

        # Get the current asyncio event loop
        loop = asyncio.get_running_loop()

        # Create tasks: one for the async Google News scrape, and one for the sync API call
        google_task = get_google_news(session, ticker)
        marketaux_task = loop.run_in_executor(None, get_marketaux_news_sync, ticker, api_token)

        # Wait for both tasks to complete
        results = await asyncio.gather(google_task, marketaux_task)
        
        google_headlines, marketaux_headlines = results
        
        # Combine and de-duplicate the headlines
        all_headlines = marketaux_headlines + google_headlines
        if not all_headlines:
            print("No news found for this ticker from any source.")
            return []
        
        unique_headlines = list(dict.fromkeys(all_headlines))
        return unique_headlines

    finally:
        await session.close()

# --- Main execution block ---
if __name__ == '__main__':
    marketaux_api_token = os.getenv("MARKETAUX_API_TOKEN")

    if not marketaux_api_token:
        print("--- ERROR ---")
        print("MarketAux API token not found. Please set the 'MARKETAUX_API_TOKEN' environment variable.")
        sys.exit(1)

    if len(sys.argv) > 1:
        ticker_symbol = sys.argv[1]
        news_list = asyncio.run(get_all_news(ticker_symbol, marketaux_api_token))
        if news_list:
            print(f"\n--- Aggregated News for ${ticker_symbol.upper()} ---")
            for i, headline in enumerate(news_list, 1):
                print(f"{i}. {headline}")
    else:
        while True:
            ticker_symbol = input("Please enter a stock ticker (or type 'quit' to exit): ")
            if ticker_symbol.lower() in ['quit', 'exit']:
                break
            if not ticker_symbol:
                continue

            news_list = asyncio.run(get_all_news(ticker_symbol.strip(), marketaux_api_token))
            if news_list:
                print(f"\n--- Aggregated News for ${ticker_symbol.upper().strip()} ---")
                for i, headline in enumerate(news_list, 1):
                    print(f"{i}. {headline}")
            print("\n" + "="*50 + "\n")

