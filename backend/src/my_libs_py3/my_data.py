
from .TD_Order import IBTrader
from .db import mongo
from .fmp import FMPClient
from ib_insync import util, Stock
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
import os
import io
import requests
import asyncio
import numpy as np
from datetime import datetime, timedelta
import logging
import os
import io
import requests
try:
    from airflow.models import Variable
except Exception:  # Catch broader exceptions if Airflow is present but fails to init
    Variable = None  # Airflow is not available or failed to initialize
from dotenv import load_dotenv, find_dotenv
#********************************************************

#   Price Data Pipeline

#********************************************************


####  SORT THE PRICE SERIES ASCENDING
class PriceDataFetcher:
    def __init__(self, trader=None, fmp_switch=False, fall_back=True, enable_intelligent_fallback=True):
        self.fmp_client = FMPClient()
        self.trader = trader
        self.fmp_switch = fmp_switch
        self.fall_back = fall_back
        self.finviz_key = self._read_finviz_key() # Initialize finviz key

        # [NEW] Intelligent Fallback Configuration
        self.enable_intelligent_fallback = enable_intelligent_fallback
        self._fallback_manager = None  # Lazy initialization to avoid circular imports

    def _parse_finviz_value(self, value_str):
        if value_str is None:
            return np.nan
        if isinstance(value_str, (int, float)):
            if isinstance(value_str, float) and np.isnan(value_str):
                return np.nan
            return float(value_str)
        if not isinstance(value_str, str) or value_str == '-':
            return np.nan
        value_str = value_str.strip()
        try:
            if value_str.endswith('%'):
                return float(value_str.rstrip('%')) / 100.0
            elif value_str.endswith('B'):
                return float(value_str.rstrip('B')) * 1e9
            elif value_str.endswith('M'):
                return float(value_str.rstrip('M')) * 1e6
            elif value_str.endswith('K'):
                return float(value_str.rstrip('K')) * 1e3
            return float(value_str)
        except (ValueError, TypeError):
            return np.nan

    def _read_finviz_key(self):
        """Reads the Finviz authentication key first from Airflow Variables,
        then from a .env file or environment variables."""
        key = None
        # Try reading from Airflow Variable first
        if Variable:
            airflow_var_logger = logging.getLogger("airflow.models.variable")
            original_level = airflow_var_logger.getEffectiveLevel()
            try:
                # Temporarily set logging level to CRITICAL to suppress ERROR messages from Variable.get
                airflow_var_logger.setLevel(logging.CRITICAL)
                key = Variable.get("finviz_api_key")
            except Exception as e: # Catches KeyNotFound or other Airflow-specific errors
                logging.info(f"Could not retrieve 'finviz_api_key' from Airflow Variables: {e}. Trying .env file.")
            finally:
                # Restore original logging level
                if 'original_level' in locals(): # Ensure original_level was set
                    airflow_var_logger.setLevel(original_level)

        # If not found in Airflow Variables, try .env file and os.environ
        if not key:
            load_dotenv(find_dotenv()) # Load .env file if present
            key = os.getenv("finviz_api_key")

        if not key:
            # Use the specific name from the .env example if it's different
            if os.getenv("FINVIZ_API_KEY"): # Checking the .env example key name
                 key = os.getenv("FINVIZ_API_KEY")
            else:
                 logging.warning("finviz_api_key not found in Airflow Variables or .env file. Finviz queries may fail.")
        return key

    def adjust_with_corporate_actions(self, ticker: str, df: pd.DataFrame, persist: bool = True) -> pd.DataFrame:
        """
        Adjusts the Close (and OHL if present) series for splits and dividends using FMP endpoints.
        - Splits: apply split ratio backwards (pre-split prices adjusted by 1/ratio).
        - Dividends: adjust pre-dividend prices by (P_prev - D) / P_prev on ex-date.
        Persists adjusted series to Mongo 'adjusted_prices' collection when persist=True.
        """
        try:
            if df is None or df.empty or 'TimeStamp' not in df.columns or 'Close' not in df.columns:
                return df
            df = df.copy()
            # Ensure datetime and ascending order
            df['TimeStamp'] = pd.to_datetime(df['TimeStamp'])
            df.sort_values('TimeStamp', inplace=True)
            df.reset_index(drop=True, inplace=True)

            start_str = (self.start_date if hasattr(self, 'start_date') and self.start_date else df['TimeStamp'].min()).strftime('%Y-%m-%d')
            end_str = (self.end_date if hasattr(self, 'end_date') and self.end_date else df['TimeStamp'].max()).strftime('%Y-%m-%d')

            # Fetch splits and dividends
            splits_df = self.fmp_client.get_symbol_splits(ticker, start_str, end_str)
            dividends_df = self.fmp_client.get_symbol_dividends(ticker, start_str, end_str)

            # Prepare adjustment factor series (initialize to 1.0)
            adj_factor = pd.Series(1.0, index=df.index)

            # Apply splits
            if not splits_df.empty:
                # Normalize fields
                if 'date' in splits_df.columns:
                    splits_df['date'] = pd.to_datetime(splits_df['date'])
                if 'numerator' in splits_df.columns and 'denominator' in splits_df.columns:
                    splits_df['ratio'] = splits_df['numerator'].astype(float) / splits_df['denominator'].astype(float)
                elif 'splitRatio' in splits_df.columns:
                    # format like "2:1"
                    def parse_ratio(s):
                        try:
                            a, b = str(s).split(':')
                            return float(a) / float(b)
                        except Exception:
                            return 1.0
                    splits_df['ratio'] = splits_df['splitRatio'].apply(parse_ratio)
                else:
                    splits_df['ratio'] = 1.0
                # For each split, multiply all prior dates by 1/ratio
                for _, row in splits_df.sort_values('date', ascending=True).iterrows():
                    ratio = row.get('ratio', 1.0)
                    event_date = row.get('date')
                    if pd.isna(ratio) or ratio <= 0 or pd.isna(event_date):
                        continue
                    # prior dates strictly before event_date
                    prior_mask = df['TimeStamp'] < event_date
                    adj_factor.loc[prior_mask] = adj_factor.loc[prior_mask] / float(ratio)

            # Apply dividends
            if not dividends_df.empty:
                if 'date' in dividends_df.columns:
                    dividends_df['date'] = pd.to_datetime(dividends_df['date'])
                # Dividend field can be 'dividend' or 'adjDividend'
                div_col = 'dividend' if 'dividend' in dividends_df.columns else ('adjDividend' if 'adjDividend' in dividends_df.columns else None)
                if div_col:
                    # For each dividend, apply factor to all prior dates: (P_prev - D)/P_prev
                    for _, row in dividends_df.sort_values('date', ascending=True).iterrows():
                        event_date = row.get('date')
                        D = row.get(div_col, 0.0)
                        if pd.isna(event_date) or pd.isna(D) or float(D) <= 0:
                            continue
                        # find previous available close before event_date
                        prev_idx = df.index[df['TimeStamp'] < event_date]
                        if len(prev_idx) == 0:
                            continue
                        prev_close = df.loc[prev_idx.max(), 'Close']
                        if prev_close and prev_close > 0:
                            f = (float(prev_close) - float(D)) / float(prev_close)
                            # multiply all dates strictly before event_date
                            adj_factor.loc[df['TimeStamp'] < event_date] = adj_factor.loc[df['TimeStamp'] < event_date] * f

            # Apply factor
            df['RawClose'] = df['Close']
            df['Close'] = df['Close'] * adj_factor
            # Adjust O/H/L if present
            for col in ['Open', 'High', 'Low']:
                if col in df.columns:
                    df[col] = df[col] * adj_factor

            # Add Ticker column for persistence
            if 'Ticker' not in df.columns:
                df['Ticker'] = ticker

            if persist:
                try:
                    db = mongo(coll_name="adjusted_prices")
                    # Persist only necessary columns
                    cols = [c for c in ['Ticker', 'TimeStamp', 'Close', 'RawClose', 'Open', 'High', 'Low'] if c in df.columns]
                    db.frame_to_mongo(df[cols])
                except Exception as e:
                    logging.info(f"Persist adjusted series skipped due to: {e}")

            return df
        except Exception as e:
            logging.info(f"adjust_with_corporate_actions failed for {ticker}: {e}")
            return df

    def get_price_data(self, tic_list, method, start_date=None, end_date=None, back_day=90, max_retries=2, last_record=False, fmp_switch=False, fall_back=True, frequency=None):
        valid_methods = ["minute", "day", "self_minute", "td_data", "intraday", "minute_to_day", "alpaca","realtimedata", "finviz","ib"]
        if method not in valid_methods:
            raise ValueError(f"Method '{method}' not correct. Supported methods: {', '.join(valid_methods)}")

        # Use constructor values as defaults if not provided in method call
        self.fmp_switch = fmp_switch if fmp_switch is not None else self.fmp_switch
        self.fall_back = fall_back if fall_back is not None else self.fall_back

        start_date, end_date = self._set_date_range(start_date, end_date, back_day)
        self.start_date = start_date
        self.end_date = end_date
        print("Note: Price data 'Close' column might represent different values depending on the source (e.g., Adj Close for FMP/IB, Close for Finviz).")

        if method == "day":
            return self._query_mongo(None, tic_list, start_date, end_date, last_record, back_day, max_retries)
        elif method == "self_minute":
            return self._query_mongo("stocks_10minute", tic_list, start_date, end_date, last_record, back_day, max_retries)
        elif method in ["td_data", "intraday", "realtimedata"]:
            frequency = 'd' if method in ["td_data","realtimedata"] else '10m'
            return self._query_finviz(tic_list, frequency, self.start_date, self.end_date, last_record, max_retries)
        elif method == "alpaca":
            return self._query_alpaca(tic_list, start_date, end_date, max_retries)
        elif method == "finviz":
             valid_finviz_frequencies = ["1m", "3m", "5m", "10m" ,"15m", "30m", "1h", "d", "w", "m"]
             if frequency is None or frequency not in valid_finviz_frequencies:
                 raise ValueError(f"Frequency must be provided and be one of {', '.join(valid_finviz_frequencies)} for 'finviz' method.")
             # timerange is derived from start_date and end_date
             return self._query_finviz(tic_list, frequency, self.start_date, self.end_date, last_record, max_retries)
        elif method == "ib":
            bar_size = '1 day' if method in ["td_data","realtimedata"] else '10 mins'
            return self._query_ib(tic_list, last_record, back_day, bar_size, 'ADJUSTED_LAST', max_retries)

    def _set_date_range(self, start_date, end_date, back_day):
        if start_date is None:
            start_date = datetime.now() - timedelta(days=back_day)
        if end_date is None:
            end_date = datetime.now() + timedelta(days=1)
        return start_date, end_date

    def _query_mongo(self, db_name, tic_list, start_date, end_date, last_record, back_day, max_retries):
        if max_retries != 0:
            logging.info("mongo method doesn't have retry yet")
        db = mongo(db_name) if db_name is not None else mongo()
        result = pd.DataFrame()
        for tic in tic_list:
            try:
                temp = self._fetch_from_mongo(db, tic, start_date, end_date)
                temp = self._calculate_returns(temp)
                result = pd.concat([result, temp.iloc[-1:] if last_record else temp], ignore_index=True)

                total_days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days
                # Ensure the data covers at least one-third of the requested period
                if len(temp) < total_days / 3:
                    raise Exception("Data rows not enough for the requested period")
                print(f"Finished {tic}, Timestamp is in UTC")
            except Exception as e:
                print(e)
                if self.fall_back:
                    print("Switching to IB method")
                    
                    temp = self._query_ib([tic], last_record, back_day, '10 mins', 'ADJUSTED_LAST', max_retries)
                    result = result.append(temp)
        return result

    def _fetch_from_mongo(self, mongodb, ticker, start_date, end_date):
        temp = mongodb.query_database(ticker.upper(), start_date=start_date, end_date=end_date)
        temp["TimeStamp"] = pd.to_datetime(temp['TimeStamp'],utc=True)
        return temp

    def _calculate_returns(self, df):
        df["Return"] = (df.Close.diff(1) / df.Close)
        df["Fwd_Return"] = np.log(df.Close.shift(-1) / df.Close)
        return df

    def _query_ib(self, tic_list, last_record, back_day, bar_size, what_to_show, max_retries):
        self.ib = IBTrader() if self.trader is None else self.trader
        self.ib_client = self.ib.client
        result = pd.DataFrame()
        for tic in tic_list:
            try:
                temp = self._fetch_from_ib(tic, back_day, bar_size, what_to_show, max_retries)
                temp = self.adjust_with_corporate_actions(tic, temp)
                temp = self._calculate_returns(temp)
                temp["Ticker"] = tic
                new_data = temp.iloc[-1:] if last_record else temp
                result = pd.concat([result, new_data], ignore_index=True)
                print(f"Finished {tic}")
            except Exception as e:
                print(e)
        return result

    def _fetch_from_ib(self, ticker, back_day, bar_size, what_to_show, max_retries):
        retry_delay = 10
        attempt = 0
        while attempt <= max_retries:
            try:
                self.ib_client.connect(self.ib.ip_add, self.ib.port)
                contract = Stock(ticker, 'SMART', "USD")
                if back_day > 365:
                    years = back_day // 365 + 1
                    durationStr = f"{years} Y"
                else:
                    durationStr = f'{back_day} D'  # Ensure more than back_day days are covered

                bars = self.ib_client.reqHistoricalData(
                    contract,
                    endDateTime='',
                    durationStr=durationStr,
                    barSizeSetting=bar_size,
                    whatToShow=what_to_show,
                    useRTH=True,
                    formatDate=2
                )
                df = util.df(bars)
                df["Close"] = df["close"]
                df["TimeStamp"] = df["date"]
                df = df.drop(columns=['close', "date"])
                attempt += 10000000
                return df
            except Exception as e:
                attempt += 1
                if attempt > max_retries:
                    self.ib_client.disconnect()
                    logging.info(f"Failed to fetch data for {ticker} after {max_retries} attempts. Error: {e}")
                    if self.fmp_switch:
                        logging.info("Switching to FMP")
                        df = self.fmp_client.historical_data(ticker, self.start_date.strftime('%Y-%m-%d'), self.end_date.strftime('%Y-%m-%d'))
                        df["Close"] = df["close"]
                        df["TimeStamp"] = df["date"]
                        df = df.drop(columns=['close', "date"])
                        return df
                else:
                    self.ib_client.disconnect()
                    if "timeout" in str(e).lower() or 'ConnectionRefused' in str(e) or "Connect call failed" in str(e):
                        logging.info(f"Error: {e}; API connection wait")
                        time.sleep(500)
                    print(f"Retry {attempt}/{max_retries} for {ticker} due to error: {e}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)

    def _query_alpaca(self, tic_list, start_date, end_date, max_retries):
        if max_retries > 0:
            logging.info("Alpaca query retry logic not implemented yet.")

        # IBTrader is an alias for AlpacaTrader
        trader = IBTrader() if self.trader is None else self.trader
        
        all_data = []
        for tic in tic_list:
            try:
                # Use asyncio.run() to call the async method from this sync function.
                # Alpaca expects ISO 8601 format for start/end.
                df = asyncio.run(trader.get_historical_data_df(
                    symbol=tic,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                    timeframe='1Day' # Assuming daily data for now
                ))
                
                if not df.empty:
                    df["Ticker"] = tic
                    all_data.append(df)
            except Exception as e:
                logging.error(f"Failed to fetch data for {tic} from Alpaca: {e}")

        if not all_data:
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        # The DataFrame from get_historical_data_df should already have the correct column names
        result = self._calculate_returns(result)
        return result

    def _query_finviz(self, tic_list, frequency, start_date, end_date, last_record, max_retries):
        if not self.finviz_key:
            logging.error("Finviz authentication key is not set.")
            return pd.DataFrame() # Return empty DataFrame if key is missing

        result = pd.DataFrame()
        base_url = "https://elite.finviz.com/quote_export.ashx"
        retry_delay = 10

        # Format the date range for the Finviz API
        finviz_timerange = f"range_{start_date.strftime('%m-%d-%Y')}x{end_date.strftime('%m-%d-%Y')}"

        for tic in tic_list:
            attempt = 0
            while attempt <= max_retries:
                try:
                    # Use the provided frequency and the formatted timerange
                    url = f"{base_url}?t={tic}&p={frequency}&r={finviz_timerange}&auth={self.finviz_key}"
                    response = requests.get(url)
                    response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)

                    # Check if the response content indicates an error (e.g., "Invalid authentication")
                    if "Invalid authentication" in response.text:
                         raise ValueError("Finviz API: Invalid authentication key.")
                    if "No data" in response.text:
                         logging.warning(f"Finviz API: No data found for ticker {tic} with frequency {frequency} and timerange {finviz_timerange}.")
                         break # No data, no need to retry
                    
                    df = pd.read_csv(io.StringIO(response.text))

                    # Basic validation of expected columns
                    if 'Date' not in df.columns or 'Close' not in df.columns:
                         raise ValueError(f"Finviz API: Unexpected columns in response for {tic}. Columns found: {df.columns.tolist()}")

                    df["TimeStamp"] = pd.to_datetime(df['Date'])
                    # Keep original 'Close' column as Finviz export might not be adjusted
                    df["Ticker"] = tic

                    # Drop original date column if needed, keep others like Open, High, Low, Volume
                    df = df.drop(columns=['Date'])

                    df = self.adjust_with_corporate_actions(tic, df)
                    df = self._calculate_returns(df)

                    new_data = df.iloc[-1:] if last_record else df
                    result = pd.concat([result, new_data], ignore_index=True)

                    print(f"Finished {tic} from Finviz")
                    attempt = max_retries + 1 # Success, exit retry loop
                    time.sleep(1) # Add a small delay between requests

                except requests.exceptions.RequestException as e:
                    attempt += 1
                    if 'response' in locals() and response is not None and response.status_code == 429 and attempt <= max_retries:
                        logging.warning(f"Finviz API rate limit hit for {tic}. Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    elif attempt > max_retries:
                        logging.error(f"Failed to fetch data for {tic} from Finviz after {max_retries} attempts. Error: {e}")
                    elif 'response' in locals() and response is not None and response.status_code == 400:
                        logging.error(f"400 Error: Probably not supported ticker {tic}")

                        attempt = max_retries + 1
                    else:
                        print(f"Retry {attempt}/{max_retries} for {tic} due to error: {e}. Retrying in {retry_delay} seconds...")

                except ValueError as e:
                    # Handle specific ValueErrors like "Invalid authentication" or "Unexpected columns"
                    logging.error(f"Data processing error for {tic}: {e}")
                    break # Do not retry on data processing errors

                except Exception as e:
                     # Catch any other unexpected errors
                     logging.error(f"An unexpected error occurred while processing Finviz data for {tic}: {e}")
                     break # Don't retry on unexpected errors

        return result

    def get_option_data_finviz(self, tic, option_type, expiration_date, max_retries=2):
        """
        Fetches option chain data from Finviz Elite API for a specific expiration date.

        This function queries the Finviz Elite API to retrieve the full option chain
        (calls, puts, or both) for a given ticker and expiration date. It handles
        retries, rate limiting, and common API errors.

        The returned DataFrame contains detailed information for each option contract,
        including greeks, volume, and open interest.

        Args:
            tic (str): The ticker symbol (e.g., 'MSFT', 'GOOGL').
            option_type (str): Type of options to fetch.
                - 'oc' for Calls
                - 'op' for Puts
                - 'o' for both Calls and Puts
            expiration_date (str): The option expiration date in 'YYYY-MM-DD' format.
            max_retries (int): Maximum number of retries for the API request. Defaults to 2.

        Returns:
            pandas.DataFrame: A DataFrame containing the option chain data. The columns include:
                - 'Contract Name': The option symbol.
                - 'Last Trade': The timestamp of the last trade.
                - 'Strike': The strike price.
                - 'Last Close': The last closing price of the contract.
                - 'Bid': The current bid price.
                - 'Ask': The current ask price.
                - 'Change $': The dollar change from the previous close.
                - 'Change %': The percentage change from the previous close.
                - 'Volume': The trading volume for the day.
                - 'Open Int.': The open interest.
                - 'Type': 'call' or 'put'.
                - 'IV': Implied Volatility.
                - 'Delta', 'Gamma', 'Theta', 'Vega', 'Rho': The option greeks.
                - 'Ticker': The ticker symbol for the underlying stock.
            Returns an empty DataFrame if the API key is not set, no data is found, or an
            unrecoverable error occurs.
        """
        if not self.finviz_key:
            logging.error("Finviz authentication key is not set. Cannot fetch option data.")
            return pd.DataFrame()

        base_url = "https://elite.finviz.com/export/options"
        # Finviz API expects expiration date in YYYY-MM-DD format, which is already the input format.
        # Example: https://elite.finviz.com/export/options?t=MSFT&ty=oc&e=2023-10-20&auth=YOUR_KEY
        url = f"{base_url}?t={tic.upper()}&ty={option_type.lower()}&e={expiration_date}&auth={self.finviz_key}"
        
        retry_delay = 10
        attempt = 0
        
        while attempt <= max_retries:
            try:
                response = requests.get(url)
                response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)

                if "Invalid authentication" in response.text:
                    raise ValueError("Finviz API: Invalid authentication key.")
                if "No data" in response.text or response.text.strip() == "": # Check for "No data" or empty response
                    logging.warning(f"Finviz API: No option data found for ticker {tic}, type {option_type}, expiration {expiration_date}.")
                    return pd.DataFrame() # Return empty DataFrame if no data

                df = pd.read_csv(io.StringIO(response.text))
                
                # Validate expected columns - adjust if necessary based on actual CSV headers
                expected_cols = [
                    'Contract Name', 'Last Trade', 'Strike', 'Last Close', 'Bid', 'Ask',
                    'Change $', 'Change %', 'Volume', 'Open Int.', 'Type', 'IV', 'Delta',
                    'Gamma', 'Theta', 'Vega', 'Rho'
                ]
                if not all(col in df.columns for col in expected_cols):
                    logging.warning(f"Finviz API: Unexpected columns in option response for {tic}. Found: {df.columns.tolist()}")
                    # Depending on strictness, you might return empty df or try to proceed
                    # For now, we'll proceed if some key columns are missing but log a warning.

                df["Ticker"] = tic.upper()
                logging.info(f"Successfully fetched option data for {tic} (exp: {expiration_date}, type: {option_type}) from Finviz.")
                return df

            except requests.exceptions.RequestException as e:
                attempt += 1
                if 'response' in locals() and response is not None and response.status_code == 429 and attempt <= max_retries:
                    logging.warning(f"Finviz API rate limit hit for {tic} options. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                elif attempt > max_retries:
                    logging.error(f"Failed to fetch option data for {tic} from Finviz after {max_retries} attempts. Error: {e}")
                    return pd.DataFrame()
                elif 'response' in locals() and response is not None and response.status_code == 400:
                    logging.error(f"Finviz API 400 Error for {tic} options: Likely invalid parameters (e.g., ticker, date format, option type). URL: {url}")
                    return pd.DataFrame() # Do not retry on 400
                else:
                    logging.warning(f"Retry {attempt}/{max_retries} for {tic} options due to error: {e}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
            
            except ValueError as e:
                # Handle specific ValueErrors like "Invalid authentication"
                logging.error(f"Data processing error for {tic} options: {e}")
                return pd.DataFrame() # Do not retry on data processing errors

            except Exception as e:
                 # Catch any other unexpected errors
                 logging.error(f"An unexpected error occurred while processing Finviz option data for {tic}: {e}")
                 return pd.DataFrame() # Don't retry on unexpected errors
        
        return pd.DataFrame() # Should be unreachable if loop finishes, but as a fallback

    def _fetch_finviz_export_csv(self, tic: str, view: int, max_retries: int = 2) -> pd.DataFrame:
        """Fetch a Finviz Elite CSV export for a single ticker."""
        if not self.finviz_key:
            logging.error("Finviz authentication key is not set.")
            return pd.DataFrame()

        base_url = "https://elite.finviz.com/export.ashx"
        url = f"{base_url}?v={view}&t={tic.upper()}&auth={self.finviz_key}"
        retry_delay = 10
        attempt = 0

        while attempt <= max_retries:
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                if "Invalid authentication" in response.text:
                    raise ValueError("Finviz API: Invalid authentication key.")
                if "No data" in response.text or not response.text.strip():
                    logging.warning("Finviz API: No export data for %s (v=%s).", tic, view)
                    return pd.DataFrame()
                df = pd.read_csv(io.StringIO(response.text))
                if df.empty:
                    return pd.DataFrame()
                return df
            except requests.exceptions.RequestException as exc:
                attempt += 1
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status == 429 and attempt <= max_retries:
                    logging.warning("Finviz rate limit for %s v=%s; retrying.", tic, view)
                    time.sleep(retry_delay)
                    continue
                if status == 400:
                    logging.error("Finviz 400 for %s v=%s", tic, view)
                    return pd.DataFrame()
                if attempt > max_retries:
                    logging.error("Finviz export failed for %s v=%s: %s", tic, view, exc)
                    return pd.DataFrame()
                time.sleep(retry_delay)
            except ValueError as exc:
                logging.error("Finviz export error for %s v=%s: %s", tic, view, exc)
                return pd.DataFrame()
            except Exception as exc:
                logging.error("Unexpected Finviz export error for %s v=%s: %s", tic, view, exc)
                return pd.DataFrame()
        return pd.DataFrame()

    def get_company_finviz_profile(self, tic, max_retries=2):
        """
        Fetch a broad company profile from Finviz Elite (v=152 overview + v=161 financials).
        Returns a normalized dict of fundamental fields.
        """
        overview = self._fetch_finviz_export_csv(tic, 152, max_retries=max_retries)
        financials = self._fetch_finviz_export_csv(tic, 161, max_retries=max_retries)
        if overview.empty and financials.empty:
            return {}

        row = {}
        if not overview.empty:
            row.update(overview.iloc[0].to_dict())
        if not financials.empty:
            for key, value in financials.iloc[0].to_dict().items():
                row.setdefault(key, value)

        def _val(col):
            if col not in row:
                return np.nan
            raw = row[col]
            if col in ("Earnings Date", "Company", "Sector", "Industry", "Country"):
                if raw is None or (isinstance(raw, float) and np.isnan(raw)):
                    return np.nan
                text = str(raw).strip()
                return text if text and text != "-" else np.nan
            return self._parse_finviz_value(raw)

        market_cap = _val("Market Cap")
        if isinstance(market_cap, (int, float)) and not np.isnan(market_cap) and market_cap > 0:
            # Finviz exports market cap in millions USD.
            market_cap = float(market_cap) * 1_000_000

        return {
            "company": _val("Company"),
            "sector": _val("Sector"),
            "industry": _val("Industry"),
            "country": _val("Country"),
            "price": _val("Price"),
            "market_cap": market_cap,
            "pe": _val("P/E"),
            "forward_pe": _val("Forward P/E"),
            "peg": _val("PEG"),
            "ps": _val("P/S"),
            "pb": _val("P/B"),
            "pcash": _val("P/Cash"),
            "pfcf": _val("P/Free Cash Flow"),
            "dividend_yield": _val("Dividend Yield"),
            "payout_ratio": _val("Payout Ratio"),
            "eps_ttm": _val("EPS (ttm)"),
            "eps_growth_this_year": _val("EPS Growth This Year"),
            "eps_growth_past_5y": _val("EPS Growth Past 5 Years"),
            "sales_growth_past_5y": _val("Sales Growth Past 5 Years"),
            "eps_growth_qoq": _val("EPS Growth Quarter Over Quarter"),
            "sales_growth_qoq": _val("Sales Growth Quarter Over Quarter"),
            "insider_own": _val("Insider Ownership"),
            "inst_own": _val("Institutional Ownership"),
            "roa": _val("Return on Assets"),
            "roe": _val("Return on Equity"),
            "roic": _val("Return on Invested Capital"),
            "current_ratio": _val("Current Ratio"),
            "quick_ratio": _val("Quick Ratio"),
            "lt_debt_equity": _val("LT Debt/Equity"),
            "debt_equity": _val("Total Debt/Equity"),
            "gross_margin": _val("Gross Margin"),
            "operating_margin": _val("Operating Margin"),
            "profit_margin": _val("Profit Margin"),
            "beta": _val("Beta"),
            "avg_volume": _val("Average Volume"),
            "rel_volume": _val("Relative Volume"),
            "earnings_date": _val("Earnings Date"),
            "analyst_recom": _val("Analyst Recom"),
            "target_price": _val("Target Price"),
            "perf_week": _val("Performance (Week)"),
            "perf_month": _val("Performance (Month)"),
            "perf_quarter": _val("Performance (Quarter)"),
            "rsi_14": _val("Relative Strength Index (14)"),
            "sma_20": _val("20-Day Simple Moving Average"),
            "sma_50": _val("50-Day Simple Moving Average"),
            "sma_200": _val("200-Day Simple Moving Average"),
            "high_52w": _val("52-Week High"),
            "low_52w": _val("52-Week Low"),
        }

    def get_stock_details_finviz(self, tic, max_retries=2):
        """
        Fetches detailed stock data from Finviz Elite API, including dividend yield and earnings date.

        Args:
            tic (str): The ticker symbol (e.g., 'MSFT').
            max_retries (int): Maximum number of retries for the API request.

        Returns:
            dict: A dictionary with fundamental stock data, or an empty dict if error.
        """
        profile = self.get_company_finviz_profile(tic, max_retries=max_retries)
        if not profile:
            return {}

        return {
            "Industry": profile.get("industry"),
            "Sector": profile.get("sector"),
            "Market_cap": profile.get("market_cap"),
            "Earnings_date": profile.get("earnings_date"),
            "PEG": profile.get("peg"),
            "Profit_Margin": profile.get("profit_margin"),
            "Avg_Volume": profile.get("avg_volume"),
            "Inst_Own": profile.get("inst_own"),
            "Beta": profile.get("beta"),
            "Current_Ratio": profile.get("current_ratio"),
            "PB": profile.get("pb"),
            "Debt_to_Equity": profile.get("debt_equity"),
            "LDebt_to_Equity": profile.get("lt_debt_equity"),
            "ROE": profile.get("roe"),
            "ROA": profile.get("roa"),
            "dividend_yield": profile.get("dividend_yield"),
            "price": profile.get("price"),
            "pe_ratio": profile.get("pe"),
            "eps_growth_this_year": profile.get("eps_growth_this_year"),
            "sales_growth_quarterly": profile.get("sales_growth_qoq"),
            "debt_equity": profile.get("debt_equity"),
            "roa": profile.get("roa"),
            "roe": profile.get("roe"),
            "profit_margin": profile.get("profit_margin"),
            "beta": profile.get("beta"),
            "average_volume": profile.get("avg_volume"),
            "relative_volume": profile.get("rel_volume"),
            "market_cap": profile.get("market_cap"),
            "earnings_date": profile.get("earnings_date"),
        }

    async def get_current_price_from_broker_async(self, ticker: str) -> float | None:
        """
        Asynchronously fetches the current market price for a ticker from the broker (Alpaca).
        """
        trader = IBTrader() if self.trader is None else self.trader
        price = None
        try:
            # AlpacaTrader's methods are async.
            price = await trader.get_current_price(symbol=ticker)
            if price is not None and isinstance(price, (int, float)) and price > 0:
                logging.info(f"Fetched current price for {ticker} from broker: {price}")
                return float(price)
            else:
                logging.warning(f"Broker returned invalid price for {ticker}: {price}")
                return None
        except Exception as e:
            logging.info(f"Could not fetch current price for {ticker} from broker: {e}")
        return None

    def get_futures_data_finviz(self, max_retries=2):
        """
        Fetches futures market data from Finviz Elite API.

        Args:
            max_retries (int): Maximum number of retries for the API request.

        Returns:
            pandas.DataFrame: A DataFrame with futures data, or an empty DataFrame on error.
        """
        if not self.finviz_key:
            logging.error("Finviz authentication key is not set. Cannot fetch futures data.")
            return pd.DataFrame()

        # v=210 is the view for futures data
        base_url = "https://elite.finviz.com/export.ashx"
        url = f"{base_url}?v=210&auth={self.finviz_key}"
        
        retry_delay = 10
        attempt = 0
        
        while attempt <= max_retries:
            try:
                response = requests.get(url)
                response.raise_for_status()

                if "Invalid authentication" in response.text:
                    raise ValueError("Finviz API: Invalid authentication key.")
                if "No data" in response.text or response.text.strip() == "":
                    logging.warning("Finviz API: No futures data found.")
                    return pd.DataFrame()

                df = pd.read_csv(io.StringIO(response.text))
                logging.info("Successfully fetched futures data from Finviz.")
                return df

            except requests.exceptions.RequestException as e:
                attempt += 1
                current_response_text = response.text if 'response' in locals() and response is not None else "No response object"
                if 'response' in locals() and response is not None and response.status_code == 429 and attempt <= max_retries:
                    logging.warning(f"Finviz API rate limit hit for futures. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                elif attempt > max_retries:
                    logging.error(f"Failed to fetch futures data from Finviz after {max_retries} attempts. Error: {e}. Last response: {current_response_text[:200]}")
                    return pd.DataFrame()
                else:
                    logging.warning(f"Retry {attempt}/{max_retries} for futures due to error: {e}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
            
            except ValueError as e:
                logging.error(f"Data processing error for futures: {e}")
                return pd.DataFrame()
            except Exception as e:
                 logging.error(f"An unexpected error occurred while processing Finviz futures data: {e}")
                 return pd.DataFrame()

        return pd.DataFrame()

    # ********************************************************
    #   INTELLIGENT FALLBACK METHODS
    # ********************************************************

    def _get_fallback_manager(self):
        """Lazy initialization of fallback manager to avoid circular imports."""
        if self._fallback_manager is None:
            try:
                from src.analytics.data_quality_fallback_manager import DataQualityFallbackManager
                from src.analytics.expiration_fallback_config import create_default_fallback_config
                config = create_default_fallback_config()
                self._fallback_manager = DataQualityFallbackManager(config)
            except ImportError as e:
                logging.warning(f"Failed to initialize fallback manager: {e}")
                self._fallback_manager = None
        return self._fallback_manager

    async def get_option_data_with_intelligent_fallback(self, ticker: str, option_type: str,
                                                       expiration_date: str, max_retries: int = 2,
                                                       enable_fallback: bool = None) -> pd.DataFrame:
        """
        Enhanced version of get_option_data_finviz with intelligent fallback strategy.

        This method implements the 'more active options' recommendation by:
        1. Attempting the initial request
        2. Assessing data quality using existing quality assessment system
        3. If quality is insufficient, trying alternative expiration dates with better liquidity
        4. Attempting different data sources if available

        Args:
            ticker (str): Stock ticker symbol
            option_type (str): 'oc' for calls, 'op' for puts, 'o' for both
            expiration_date (str): Target expiration date (YYYY-MM-DD format)
            max_retries (int): Maximum retries for initial request
            enable_fallback (bool): Override for enabling fallback (uses instance default if None)

        Returns:
            pandas.DataFrame: Option chain data with enhanced fallback strategy applied
        """
        # Use instance setting if not overridden
        if enable_fallback is None:
            enable_fallback = self.enable_intelligent_fallback

        # First, try the original method
        initial_data = self.get_option_data_finviz(ticker, option_type, expiration_date, max_retries)

        # If fallback is disabled or manager unavailable, return initial result
        if not enable_fallback:
            return initial_data

        fallback_manager = self._get_fallback_manager()
        if fallback_manager is None:
            logging.warning("Fallback manager not available, returning initial data")
            return initial_data

        # If initial data is good enough, return it
        if initial_data is not None and not initial_data.empty:
            quality_assessment = fallback_manager._assess_data_quality(initial_data, ticker)
            should_fallback, triggers = fallback_manager.decision_engine.should_trigger_fallback(quality_assessment)

            if not should_fallback:
                logging.info(f"Initial data quality acceptable for {ticker}/{expiration_date}")
                return initial_data

            logging.info(f"Triggering intelligent fallback for {ticker}: {[t.value for t in triggers]}")

        # Convert string date to date object
        try:
            from datetime import datetime
            target_date = datetime.strptime(expiration_date, '%Y-%m-%d').date()
        except ValueError:
            logging.error(f"Invalid date format: {expiration_date}")
            return initial_data

        # Execute intelligent fallback
        try:
            from src.analytics.expiration_fallback_config import DataSource
            fallback_result = await fallback_manager.execute_with_fallback(
                ticker=ticker,
                expiration_date=target_date,
                data_fetcher=self,
                initial_source=DataSource.FINVIZ_ELITE,
                option_type=option_type
            )

            if fallback_result.final_success and fallback_result.final_data is not None:
                logging.info(f"Intelligent fallback succeeded for {ticker}: "
                           f"{fallback_result.final_expiration} via {fallback_result.final_source.value}")

                # Log fallback execution summary for monitoring
                summary = fallback_result.get_summary()
                logging.info(f"Fallback execution summary: {summary['execution_stats']}")

                return fallback_result.final_data
            else:
                logging.warning(f"Intelligent fallback failed for {ticker}, returning initial data")
                return initial_data

        except Exception as e:
            logging.error(f"Intelligent fallback execution failed for {ticker}: {e}")
            return initial_data

    def get_recommended_expiration_dates(self, ticker: str, target_dte_list: List[int] = None) -> List[str]:
        """
        Get recommended expiration dates based on liquidity and activity patterns.

        This method implements the 'more active options' recommendation by identifying
        expiration dates that typically have higher liquidity and better data quality.

        Args:
            ticker (str): Stock ticker symbol
            target_dte_list (List[int]): Target days to expiration. Defaults to [7, 30, 90]

        Returns:
            List[str]: List of recommended expiration dates in YYYY-MM-DD format
        """
        from datetime import date, timedelta

        if target_dte_list is None:
            target_dte_list = [7, 14, 21, 30, 60, 90]

        recommended_dates = []
        today = date.today()

        for dte in target_dte_list:
            target_date = today + timedelta(days=dte)

            # Adjust to nearest Friday (weekly options) or third Friday (monthly)
            if dte <= 30:  # Weekly options preference for shorter term
                days_until_friday = (4 - target_date.weekday()) % 7
                if days_until_friday == 0:
                    days_until_friday = 7
                adjusted_date = target_date + timedelta(days=days_until_friday)
            else:  # Monthly options for longer term
                # Find third Friday of the month
                first_day = target_date.replace(day=1)
                third_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7 + 14)

                # If we've passed the third Friday, go to next month
                if target_date > third_friday:
                    next_month = (first_day + timedelta(days=32)).replace(day=1)
                    adjusted_date = next_month + timedelta(days=(4 - next_month.weekday()) % 7 + 14)
                else:
                    adjusted_date = third_friday

            recommended_dates.append(adjusted_date.strftime('%Y-%m-%d'))

        return recommended_dates

    def assess_data_quality_simple(self, option_data: pd.DataFrame, ticker: str) -> dict:
        """
        Simple data quality assessment for option chain data.

        This provides a lightweight quality check that can be used independently
        of the full fallback system.

        Args:
            option_data (pd.DataFrame): Option chain data to assess
            ticker (str): Stock ticker symbol

        Returns:
            dict: Quality assessment with score and recommendations
        """
        if option_data is None or option_data.empty:
            return {
                "quality_score": 0.0,
                "quality_level": "failed",
                "recommendations": ["No data available - try different expiration date"],
                "valid_strikes": 0,
                "total_rows": 0
            }

        assessment = {
            "total_rows": len(option_data),
            "valid_strikes": 0,
            "complete_greeks": 0,
            "quality_score": 0.0,
            "recommendations": []
        }

        # Count valid strikes
        if 'Strike' in option_data.columns:
            valid_strikes = option_data[option_data['Strike'].notna() & (option_data['Strike'] > 0)]
            assessment["valid_strikes"] = len(valid_strikes)

        # Check Greeks completeness
        greek_columns = ['Delta', 'Gamma', 'Theta', 'Vega']
        available_greeks = [col for col in greek_columns if col in option_data.columns]

        if available_greeks:
            complete_rows = option_data.dropna(subset=available_greeks)
            assessment["complete_greeks"] = len(complete_rows)

        # Calculate quality score
        if assessment["total_rows"] > 0:
            completeness_ratio = assessment["valid_strikes"] / assessment["total_rows"]
            greeks_ratio = assessment["complete_greeks"] / assessment["total_rows"]
            assessment["quality_score"] = (completeness_ratio * 0.6 + greeks_ratio * 0.4)

        # Determine quality level and recommendations
        if assessment["quality_score"] >= 0.8:
            assessment["quality_level"] = "excellent"
        elif assessment["quality_score"] >= 0.6:
            assessment["quality_level"] = "good"
        elif assessment["quality_score"] >= 0.4:
            assessment["quality_level"] = "acceptable"
        elif assessment["quality_score"] >= 0.2:
            assessment["quality_level"] = "poor"
            assessment["recommendations"].append("Consider trying shorter-term expiration for better liquidity")
        else:
            assessment["quality_level"] = "failed"
            assessment["recommendations"].extend([
                "Try different expiration date with more active options",
                "Consider weekly expiration dates for higher liquidity",
                "Check if ticker supports options trading"
            ])

        # Add specific recommendations based on data characteristics
        if assessment["valid_strikes"] < 5:
            assessment["recommendations"].append("Low number of strikes - try more liquid expiration date")

        if 'Volume' in option_data.columns:
            avg_volume = pd.to_numeric(option_data['Volume'], errors='coerce').mean()
            if pd.notna(avg_volume) and avg_volume < 10:
                assessment["recommendations"].append("Low trading volume - consider more active expiration dates")

        return assessment
