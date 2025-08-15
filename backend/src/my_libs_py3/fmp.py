from urllib.request import urlopen
import requests
import pandas as pd
import requests as r
from datetime import datetime, timedelta
import time
import os
from dotenv import load_dotenv

load_dotenv()


class FMPClient:
    def __init__(self):
        self.api_key = os.getenv("FMP_API_KEY")
        if not self.api_key:
            raise ValueError("FMP_API_KEY environment variable not set. Please add it to your .env file.")
        self.url_root_v3 = 'https://financialmodelingprep.com/api/v3/'
        self.url_root_v4 = 'https://financialmodelingprep.com/api/v4/'

    def fetch_url_with_rate_limit(self, url):
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception(f"Request failed with status {response.status_code}")

        remaining = response.headers.get('X-RateLimit-Remaining')
        reset_time = response.headers.get('X-RateLimit-Reset')
        if remaining:
            remaining = int(remaining)
            if remaining == 0:
                if reset_time:
                    time_to_sleep = int(reset_time) - time.time()
                    if time_to_sleep > 0:
                        print(f"Rate limit exceeded. Sleeping for {time_to_sleep} seconds.")
                        time.sleep(time_to_sleep)
                else:
                    raise Exception(
                        "Rate limit exceeded, and no reset time provided. Please wait before making more requests.")

        return response.json()

    def realtimequote(self, ticker):
        url = f"{self.url_root_v3}quote/{ticker.upper()}?apikey={self.api_key}"
        return pd.DataFrame(requests.get(url).json())

    def get_delisted_companies(self):
        url = f"{self.url_root_v3}delisted-companies?apikey={self.api_key}"
        return self.fetch_url_with_rate_limit(url)

    def all_stock_list(self):
        url = f"{self.url_root_v3}available-traded/list?apikey={self.api_key}"
        data = self.fetch_url_with_rate_limit(url)
        cantrade = pd.DataFrame(data).dropna(subset=["exchange"])
        us_exchanges = ['AMEX', 'NASDAQ', 'NYSE', 'OTC', 'CBOE']
        return cantrade[cantrade.exchangeShortName.isin(us_exchanges)]

    def dcf(self, ticker, history='today'):
        if history == 'today':
            url = f"{self.url_root_v3}discounted-cash-flow/{ticker.upper()}?apikey={self.api_key}"
        elif history == 'advanced':
            url = f"{self.url_root_v4}advanced_discounted_cash_flow/?symbol={ticker.upper()}&apikey={self.api_key}"
        elif history == 'daily':
            url = f"{self.url_root_v3}historical-daily-discounted-cash-flow/{ticker.upper()}?apikey={self.api_key}"
        elif history in ['annual', 'quarter']:
            url = f"{self.url_root_v3}historical-discounted-cash-flow-statement/{ticker.upper()}?period={history}&apikey={self.api_key}"
        else:
            raise KeyError(f"Invalid history key: '{history}'")
        data = self.fetch_url_with_rate_limit(url)
        return pd.DataFrame(data)

    def sector_pe(self, date, exchange):
        if exchange not in ['AMEX', 'NASDAQ', 'NYSE']:
            raise Exception("Select from 'AMEX', 'NASDAQ', 'NYSE'")
        url = f"{self.url_root_v4}sector_price_earning_ratio?date={date.strftime('%Y-%m-%d')}&exchange={exchange}&apikey={self.api_key}"
        return pd.DataFrame(self.fetch_url_with_rate_limit(url))

    def industry_pe(self, date, exchange):
        if exchange not in ['AMEX', 'NASDAQ', 'NYSE']:
            raise Exception("Select from 'AMEX', 'NASDAQ', 'NYSE'")
        url = f"{self.url_root_v4}industry_price_earning_ratio?date={date.strftime('%Y-%m-%d')}&exchange={exchange}&apikey={self.api_key}"
        return pd.DataFrame(self.fetch_url_with_rate_limit(url))

    def stock_peer(self, ticker):
        url = f"{self.url_root_v4}stock_peers?symbol={ticker}&apikey={self.api_key}"
        data = self.fetch_url_with_rate_limit(url)
        if "peersList" in data and len(data["peersList"]) > 0:
            return pd.DataFrame(data["peersList"])
        else:
            return pd.DataFrame()

    def historical_data(self, ticker, start_date, end_date, data_type='stock'):
        """
        Fetch historical data for a specified ticker within a date range.

        Args:
            ticker (str): The ticker symbol for the stock.
            start_date (str): The start date in the format 'YYYY-MM-DD'.
            end_date (str): The end date in the format 'YYYY-MM-DD'.
            data_type (str): The type of data to fetch (default is 'stock').

        Returns:
            pd.DataFrame: DataFrame containing historical data.
        """
        if data_type == 'stock':
            url = f"{self.url_root_v3}historical-price-full/{ticker}?from={start_date}&to={end_date}&apikey={self.api_key}"
        elif data_type == 'forex':
            url = f"{self.url_root_v3}historical-price-full/forex/{ticker}?from={start_date}&to={end_date}&apikey={self.api_key}"
        else:
            raise ValueError("Invalid data_type. Accepted values are 'stock' or 'forex'.")

        data = self.fetch_url_with_rate_limit(url)
        return pd.DataFrame(data['historical'])

    def stock_split_calendar(self, from_date, to_date):
        """
        Fetch the stock split calendar within a specified date range.

        Args:
            from_date (str): The start date in the format 'YYYY-MM-DD'.
            to_date (str): The end date in the format 'YYYY-MM-DD'.

        Returns:
            pd.DataFrame: DataFrame containing stock split calendar data.
        """
        url = f"{self.url_root_v3}stock_split_calendar?from={from_date}&to={to_date}&apikey={self.api_key}"
        data = self.fetch_url_with_rate_limit(url)
        return pd.DataFrame(data)

    def get_symbol_splits(self, ticker: str, from_date: str, to_date: str) -> pd.DataFrame:
        """
        Fetch historical stock split events for a symbol between two dates (inclusive).
        """
        url = f"{self.url_root_v3}historical-price-full/stock_split/{ticker.upper()}?from={from_date}&to={to_date}&apikey={self.api_key}"
        data = self.fetch_url_with_rate_limit(url)
        # FMP returns {"symbol": "...", "historical": [...]}
        hist = data.get('historical', data if isinstance(data, list) else [])
        return pd.DataFrame(hist)

    def get_symbol_dividends(self, ticker: str, from_date: str, to_date: str) -> pd.DataFrame:
        """
        Fetch historical stock dividend events for a symbol between two dates (inclusive).
        """
        url = f"{self.url_root_v3}historical-price-full/stock_dividend/{ticker.upper()}?from={from_date}&to={to_date}&apikey={self.api_key}"
        data = self.fetch_url_with_rate_limit(url)
        hist = data.get('historical', data if isinstance(data, list) else [])
        return pd.DataFrame(hist)

    def get_treasury_yields(self, date: str = None, from_date: str = None, to_date: str = None) -> pd.DataFrame:
        """
        Fetch U.S. Treasury yield curve data from FMP.
        - If 'date' is provided, fetch that day's yields.
        - Else, use from/to range (defaults to recent window if not provided).
        Returns a DataFrame with columns including: date, month1, month3, month6, year1, year2, year3,
        year5, year7, year10, year20, year30 (as available).
        """
        if date:
            url = f"{self.url_root_v4}treasury?date={date}&apikey={self.api_key}"
        else:
            if not from_date or not to_date:
                # default to last 10 days if range not provided
                to_date = (datetime.utcnow().date()).strftime('%Y-%m-%d')
                from_date = (datetime.utcnow().date() - timedelta(days=10)).strftime('%Y-%m-%d')
            url = f"{self.url_root_v4}treasury?from={from_date}&to={to_date}&apikey={self.api_key}"
        data = self.fetch_url_with_rate_limit(url)
        return pd.DataFrame(data)

