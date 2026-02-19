from urllib.request import urlopen
import requests
import pandas as pd
import requests as r
from datetime import datetime, timedelta
import json
import os


if os.getcwd() == "/opt/airflow":
    home_dir="/opt/airflow/"
else:
    home_dir = "/home/ken/big_storage/airflowProd/"
    
def readgateway(line):
    with open(home_dir + "notebook/My_Trader/record-Copy1.txt") as file:
        for i in range(line):
            abc = file.readline() 
    return abc

api_key = readgateway(9).rstrip()
# url_root = 'https://fmpcloud.io/api/v3/'
url_root = 'https://financialmodelingprep.com/api/v3/'
url_root_v4 = 'https://financialmodelingprep.com/api/v4/'
  
    
def fetch_url_with_rate_limit(url):
    """Fetch the URL content and check for rate limits in the response headers.
    
    Args:
        url (str): The URL to fetch.

    Returns:
        dict: Parsed JSON data from the response.
    """
    
    response = requests.get(url)
    
    # Check if the request was successful
    if response.status_code != 200:
        raise Exception(f"Request failed with status {response.status_code}")

    # Check rate limiting headers (these headers might differ based on the API)
    remaining = response.headers.get('X-RateLimit-Remaining')
    reset_time = response.headers.get('X-RateLimit-Reset')
    
    if remaining:
        remaining = int(remaining)
        if remaining == 0:
            if reset_time:
                # Sleep if there's a reset time provided until the rate limit is reset
                time_to_sleep = int(reset_time) - time.time()
                if time_to_sleep > 0:
                    print(f"Rate limit exceeded. Sleeping for {time_to_sleep} seconds.")
                    time.sleep(time_to_sleep)
            else:
                raise Exception("Rate limit exceeded, and no reset time provided. Please wait before making more requests.")
    
    return response.json()
    
## PROD Heavy
def realtimequote(ticker):
    url = url_root + "quote/{}".format(ticker.upper())
#     url = "https://financialmodelingprep.com/api/v3/quote/{}".format(ticker.upper())
    payload = {
        "apikey" :api_key    
    }
    return pd.DataFrame( r.get(url, params = payload).json())
#     return pd.DataFrame( r.get(url).json())
    
def get_urlroot():

    return url_root

# def get_urlrootfmp():

#     return url_root_fmp

def get_apikey():

    return api_key

def latest_trading_date(today = datetime.now()):
    while len(industry_pe(today,"NYSE"))==0:
        today -= timedelta(days=1)
        latest_trading_date(today)
    return today


def get_delisted_companies():
    """Fetch a list of companies that have been delisted.
    
    Returns:
        A list containing information about companies that have been delisted.
    """
    url = f"{url_root}delisted-companies?apikey={get_apikey()}"
    return fetch_url_with_rate_limit(url)

def all_stock_list():
    """Fetch a list of all stocks.
    
    Returns:
        pd.DataFrame: DataFrame containing information about stocks.
    """
    
    url = f"{url_root}stock/list?apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)

    cantrade = pd.DataFrame(data)
    cantrade = cantrade.dropna(subset=["exchange"])
    
    return cantrade

def dcf(ticker, history='today'):
    """Discounted Cash Flow Valuation API from https://fmpcloud.io/documentation#dcf
    
    Args:
        ticker (str): Ticker for which we need the DCF.
        history (str, optional): 'today','daily', 'quarter', 'annual'. Periodicity of requested DCF valuations. Defaults to 'today'.

    Returns:
        dict: Discounted Cash Flow Valuation info for the selected ticker.
    """
    
    apikey = get_apikey()

    if history == 'today':
        url = f"{url_root}discounted-cash-flow/{ticker.upper()}?apikey={apikey}"
    elif history == 'advanced':
        url = f"{url_root_v4}advanced_discounted_cash_flow/?symbol={ticker.upper()}&apikey={apikey}"
    elif history == 'daily':
        url = f"{url_root}historical-daily-discounted-cash-flow/{ticker.upper()}?apikey={apikey}"
    elif history in ['annual', 'quarter']:
        url = f"{url_root}historical-discounted-cash-flow-statement/{ticker.upper()}?period={history}&apikey={apikey}"
    else:
        raise KeyError(f"Discounted Cash Flow history requested not correct. '{history}' is not an accepted key")

    data = fetch_url_with_rate_limit(url)
    return pd.DataFrame(data)

def sector_pe(date: datetime, exchange):
    """Fetch the sector price-earning ratio.
    
    Args:
        date (datetime): Date for which the data is needed.
        exchange (str): Exchange to fetch the data from.

    Returns:
        pd.DataFrame: DataFrame containing sector price-earning ratio data.
    """
    
    if exchange not in ['AMEX', 'NASDAQ', 'NYSE']:
        raise Exception("select from 'AMEX', 'NASDAQ', 'NYSE'")
    
    url = f"{url_root_v4}sector_price_earning_ratio?date={date.strftime('%Y-%m-%d')}&exchange={exchange}&apikey={get_apikey()}"
    
    data = fetch_url_with_rate_limit(url)
    return pd.DataFrame(data)

def industry_pe(date: datetime, exchange):
    """Fetch the industry price-earning ratio.
    
    Args:
        date (datetime): Date for which the data is needed.
        exchange (str): Exchange to fetch the data from.

    Returns:
        pd.DataFrame: DataFrame containing industry price-earning ratio data.
    """
    
    if exchange not in ['AMEX', 'NASDAQ', 'NYSE']:
        raise Exception("select from 'AMEX', 'NASDAQ', 'NYSE'")
    
    url = f"{url_root_v4}industry_price_earning_ratio?date={date.strftime('%Y-%m-%d')}&exchange={exchange}&apikey={get_apikey()}"
    
    data = fetch_url_with_rate_limit(url)
    return pd.DataFrame(data)

def stock_peer(ticker) -> list:
    """Fetch the stock peers for a given ticker.
    
    Args:
        ticker (str): Ticker for which the peers are needed.

    Returns:
        pd.DataFrame: DataFrame containing stock peer data.
    """
    
    url = f"{url_root_v4}stock_peers?symbol={ticker}&apikey={get_apikey()}"
    
    data = fetch_url_with_rate_limit(url)
    
    if len(data) > 0 and "peersList" in data[0]:
        return data[0]["peersList"]
    else:
        return []



def tradable_tickers(exchange=['New York Stock Exchange Arca', 'NASDAQ Global Select', 'New York Stock Exchange', 'NASDAQ Capital Market', 'American Stock Exchange', 'Nasdaq Capital Market', 'Nasdaq']):
    """Get list of tradable tickers for given exchanges.

    Args:
        exchange (list): List of exchanges.

    Returns:
        pd.DataFrame: DataFrame containing tradable tickers.
    """
    
    url = f"{get_urlroot()}available-traded/list?apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)
    
    df = pd.DataFrame(data)
    df = df[df['exchange'].isin(exchange)]
    
    return df.reset_index(drop=True)

def earning_calendar(ticker):
    """Get the earning calendar for a given ticker.

    Args:
        ticker (str): Ticker for which earning calendar is needed.

    Returns:
        pd.DataFrame: DataFrame containing earning calendar.
    """
    
    url = f"{get_urlroot()}historical/earning_calendar/{ticker.upper()}?datatype=json&apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)
    
    return pd.DataFrame(data)

def rss_feed():
    """Get RSS Feed data from the API.

    Returns:
        pd.DataFrame: DataFrame containing RSS feed data.
    """
    
    url = f"{get_urlroot()}rss_feed?apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)
    
    return pd.DataFrame(data)

def balance_sheet(ticker, period='annual', ftype='full'):
    """Retrieve balance sheet data from the API for a given ticker.

    Args:
        ticker (str): Ticker for which balance sheet is required.
        period (str, optional): Periodicity of the request ('annual' or 'quarter'). Defaults to 'annual'.
        ftype (str, optional): Defines the type of sheet ('full' or 'growth'). Defaults to 'full'.

    Returns:
        pd.DataFrame: DataFrame containing balance sheet data.
    """
    
    typeurl_map = {
        'full': 'balance-sheet-statement/',
        'growth': 'balance-sheet-statement-growth/'
    }
    typeurl = typeurl_map.get(ftype)
    
    if not typeurl:
        raise ValueError('Invalid ftype provided.')

    url = f"{get_urlroot()}{typeurl}{ticker.upper()}?period={period}&apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)
    
    return pd.DataFrame(data)

def income_statement(ticker, period='annual', ftype='full'):
    """Retrieve income statement data from the API for a given ticker.

    Args:
        ticker (str): Ticker for which income statement is required.
        period (str, optional): Periodicity of the request ('annual' or 'quarter'). Defaults to 'annual'.
        ftype (str, optional): Defines the type of statement ('full' or 'growth'). Defaults to 'full'.

    Returns:
        pd.DataFrame: DataFrame containing income statement data.
    """
    
    typeurl_map = {
        'full': 'income-statement/',
        'growth': 'income-statement-growth/'
    }
    typeurl = typeurl_map.get(ftype)
    
    if not typeurl:
        raise ValueError('Invalid ftype provided.')

    url = f"{get_urlroot()}{typeurl}{ticker.upper()}?period={period}&apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)
    
    return pd.DataFrame(data)

def cash_flow_statement(ticker, period='annual', ftype='full', limit=20):
    """Retrieve cash flow statement data from the API for a given ticker.

    Args:
        ticker (str): Ticker for which cash flow statement is required.
        period (str, optional): Periodicity of the request ('annual' or 'quarter'). Defaults to 'annual'.
        ftype (str, optional): Defines the type of statement ('full' or 'growth'). Defaults to 'full'.
        limit (int, optional): Number of records to retrieve. Defaults to 20.

    Returns:
        pd.DataFrame: DataFrame containing cash flow statement data.
    """
    
    typeurl_map = {
        'full': 'cash-flow-statement/',
        'growth': 'cash-flow-statement-growth/'
    }
    typeurl = typeurl_map.get(ftype)
    
    if not typeurl:
        raise ValueError('Invalid ftype provided.')

    url = f"{get_urlroot()}{typeurl}{ticker.upper()}?period={period}&limit={limit}&apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)
    
    return pd.DataFrame(data)

def financial_ratios(ticker, period='annual', ttm=False):
    """Retrieve financial ratios data for a given ticker.

    Args:
        ticker (str): Ticker for which financial ratios are required.
        period (str, optional): Periodicity ('annual' or 'quarter'). Defaults to 'annual'.
        ttm (bool, optional): Retrieve trailing twelve months data. Defaults to False.

    Returns:
        dict: Financial ratios data for the ticker.
    """
    typeurl = "ratios-ttm/" if ttm else "ratios/"
    url = f"{get_urlroot()}{typeurl}{ticker.upper()}?period={period}&apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)
    return pd.DataFrame(data)

def key_metrics(ticker, period='annual'):
    """Retrieve key metrics data for a given ticker.

    Args:
        ticker (str): Ticker for which key metrics are required.
        period (str, optional): Periodicity ('annual' or 'quarter'). Defaults to 'annual'.

    Returns:
        dict: Key metrics data for the ticker.
    """
    url = f"{get_urlroot()}key-metrics/{ticker.upper()}?period={period}&apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)
    return pd.DataFrame(data)

def enterprise_value(ticker, period='annual'):
    """Retrieve enterprise value data for a given ticker.

    Args:
        ticker (str): Ticker for which enterprise value is required.
        period (str, optional): Periodicity ('annual' or 'quarter'). Defaults to 'annual'.

    Returns:
        dict: Enterprise value data for the ticker.
    """
    url = f"{get_urlroot()}enterprise-values/{ticker.upper()}?period={period}&apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)
    return pd.DataFrame(data)
    
def financial_statements_growth(ticker, period = 'annual'):
    """Financial Statements Growth API from https://fmpcloud.io/documentation#financialStatementGrowth
    
    Input:
        ticker : ticker for which we need the financial growth
        period : 'annual', 'quarter'. Periodicity of requested balance sheet. Defaults to annual
    Returns:
        Financial Statements Growth info for selected ticker 
    """
    urlroot = get_urlroot()
    apikey = get_apikey()
    typeurl = "financial-growth/"
    
    url = urlroot + typeurl + ticker.upper() + "?" + "period=" + period + "&apikey=" + apikey
    response = urlopen(url)
    data = response.read().decode("utf-8")
    return safe_read_json(data)



def market_capitalization(ticker, history='today'):
    """Retrieve market capitalization data for a given ticker.

    Args:
        ticker (str): Ticker for which market capitalization is required.
        history (str, optional): 'today' or 'daily'. Defaults to 'today'.

    Returns:
        dict: Market capitalization data for the ticker.
    
    Raises:
        ValueError: If the specified history is not 'today' or 'daily'.
    """
    typeurl = 'market-capitalization/' if history == 'today' else 'historical-market-capitalization/' if history == 'daily' else None
    if typeurl is None:
        raise ValueError('Invalid market cap history requested.')

    url = f"{get_urlroot()}{typeurl}{ticker.upper()}?apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)
    return pd.DataFrame(data)

def rating(ticker, history='today'):
    """Retrieve rating data for a given ticker.

    Args:
        ticker (str): Ticker for which rating information is required.
        history (str, optional): 'today' or 'daily'. Defaults to 'today'.

    Returns:
        dict: Rating data for the ticker.
    
    Raises:
        ValueError: If the specified history is not 'today' or 'daily'.
    """
    typeurl = 'rating/' if history == 'today' else 'historical-rating/' if history == 'daily' else None
    if typeurl is None:
        raise ValueError('Invalid rating history requested.')

    url = f"{get_urlroot()}{typeurl}{ticker.upper()}?apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)
    return pd.DataFrame(data)


def stock_screener(mcgt=None, mclt=None, bgt=None, blt=None, divgt=None, divlt=None, volgt=None, vollt=None, sector=None, limit=100):
    """Fetch stocks based on screening criteria from the FMP Cloud API."""
    params = {
        "marketCapMoreThan": mcgt,
        "marketCapLowerThan": mclt,
        "betaMoreThan": bgt,
        "betaLowerThan": blt,
        "dividendMoreThan": divgt,
        "dividendLowerThan": divlt,
        "volumeMoreThan": volgt,
        "volumeLowerThan": vollt,
        "sector": sector,
        "limit": limit,
        "apikey": get_apikey()
    }
    url = get_urlroot() + 'stock-screener?'
    query_string = "&".join([f"{key}={value}" for key, value in params.items() if value is not None])
    final_url = url + query_string
    data = fetch_url_with_rate_limit(final_url)
    return pd.DataFrame(json.loads(data))

def top_active():
    """Fetch top active stocks from the FMP Cloud API."""
    url = f"https://fmpcloud.io/api/v3/actives?apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)
    return safe_read_json(data)


def company_profile(ticker):
    """Fetch company profile information from the FMP Cloud API.

    Args:
        ticker (str): Stock ticker symbol.

    Returns:
        dict: Company profile information.
    """
    base_url = "https://financialmodelingprep.com/api/v3/profile/"
    api_key = get_apikey()  # Assuming you have a function to get the API key
    final_url = f"{base_url}{ticker}?apikey={api_key}"
    
    response = urlopen(final_url)
    data = fetch_url_with_rate_limit(final_url)
    return pd.DataFrame(data)


def company_outlook(symbol):
    """Fetch the company outlook for a given stock symbol.
    
    Args:
        symbol (str): The stock symbol for which the outlook is to be fetched.
    
    Returns:
        dict: A dictionary containing information about the company's outlook.
    """
    url = f"{url_root_v4}company-outlook?symbol={symbol.upper()}&apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)

    return data


def is_market_open():
    """Check if the market is open or not.
    
    Returns:
        A dictionary containing information about the market's status, next open/close time, etc.
    """
    url = f"{url_root}is-the-market-open?apikey={get_apikey()}"
    data = fetch_url_with_rate_limit(url)
    return safe_read_json(data)

def safe_read_json(data):

    try:    
        data.date = result.date.apply(lambda x: x[:10])
    except:
        # print ("Cannot convert datetime to date")
        pass
    result = pd.DataFrame([data])

    return result