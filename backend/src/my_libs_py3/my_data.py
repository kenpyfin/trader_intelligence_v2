
from .TD_Order import *
from .my_lib import *
from .fmp import FMPClient
from ib_insync import util
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
    def __init__(self, trader=None, fmp_switch=False, fall_back=True):
        self.fmp_client = FMPClient()
        self.trader = trader
        self.fmp_switch = fmp_switch
        self.fall_back = fall_back
        self.finviz_key = self._read_finviz_key() # Initialize finviz key

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

    def get_price_data(self, tic_list, method, start_date=None, end_date=None, back_day=90, max_retries=2, last_record=False, fmp_switch=False, fall_back=True, frequency=None):
        valid_methods = ["minute", "day", "self_minute", "td_data", "intraday", "minute_to_day", "fmp","realtimedata", "finviz","ib"]
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
        elif method == "fmp":
            return self._query_fmp(tic_list, start_date, end_date, max_retries)
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
                self.ib.connect()
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
                self.ib_client.cancelHistoricalData(bars)
                attempt += 10000000
                return df
            except Exception as e:
                attempt += 1
                if attempt > max_retries:
                    self.ib.disconnect()
                    logging.info(f"Failed to fetch data for {ticker} after {max_retries} attempts. Error: {e}")
                    if self.fmp_switch:
                        logging.info("Switching to FMP")
                        df = self.fmp_client.historical_data(ticker, self.start_date.strftime('%Y-%m-%d'), self.end_date.strftime('%Y-%m-%d'))
                        df["Close"] = df["close"]
                        df["TimeStamp"] = df["date"]
                        df = df.drop(columns=['close', "date"])
                        return df
                else:
                    self.ib.disconnect()
                    if "timeout" in str(e).lower() or 'ConnectionRefused' in str(e) or "Connect call failed" in str(e):
                        logging.info(f"Error: {e}; API connection wait")
                        time.sleep(500)
                    print(f"Retry {attempt}/{max_retries} for {ticker} due to error: {e}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)

    def _query_fmp(self, tic_list, start_date, end_date, max_retries):
        if max_retries != 0:
            logging.info("mongo method doesn't have retry yet")
        result = pd.DataFrame()
        for tic in tic_list:
            data = self.fmp_client.historical_data(tic, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
            result = pd.concat([result, data], ignore_index=True)
        result["TimeStamp"] = result["date"]
        result["Close"] = result["adjClose"]
        result = result.drop(columns=['close', "date"])
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

                    df = self._calculate_returns(df)

                    new_data = df.iloc[-1:] if last_record else df
                    result = pd.concat([result, new_data], ignore_index=True)

                    print(f"Finished {tic} from Finviz")
                    attempt = max_retries + 1 # Success, exit retry loop
                    time.sleep(1) # Add a small delay between requests

                except requests.exceptions.RequestException as e:
                    attempt += 1
                    if response is not None and response.status_code == 429 and attempt <= max_retries:
                        logging.warning(f"Finviz API rate limit hit for {tic}. Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    elif attempt > max_retries:
                        logging.error(f"Failed to fetch data for {tic} from Finviz after {max_retries} attempts. Error: {e}")
                    elif response is not None and response.status_code == 400:
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
                if response is not None and response.status_code == 429 and attempt <= max_retries:
                    logging.warning(f"Finviz API rate limit hit for {tic} options. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                elif attempt > max_retries:
                    logging.error(f"Failed to fetch option data for {tic} from Finviz after {max_retries} attempts. Error: {e}")
                    return pd.DataFrame()
                elif response is not None and response.status_code == 400:
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

    def get_stock_details_finviz(self, tic, max_retries=2):
        """
        Fetches detailed stock data from Finviz Elite API, including dividend yield and earnings date.

        Args:
            tic (str): The ticker symbol (e.g., 'MSFT').
            max_retries (int): Maximum number of retries for the API request.

        Returns:
            dict: A dictionary with 'dividend_yield' (float) and 'earnings_date' (str), or an empty dict if error.
        """
        if not self.finviz_key:
            logging.error("Finviz authentication key is not set. Cannot fetch stock details.")
            return {}

        # v=161 is a common view for detailed stock data including fundamentals.
        base_url = "https://elite.finviz.com/export.ashx"
        url = f"{base_url}?v=161&t={tic.upper()}&auth={self.finviz_key}"
        
        retry_delay = 10
        attempt = 0
        
        while attempt <= max_retries:
            try:
                response = requests.get(url)
                response.raise_for_status()

                if "Invalid authentication" in response.text:
                    raise ValueError("Finviz API: Invalid authentication key.")
                if "No data" in response.text or response.text.strip() == "":
                    logging.warning(f"Finviz API: No stock details data found for ticker {tic}.")
                    return {}

                df = pd.read_csv(io.StringIO(response.text))
                
                if df.empty:
                    logging.warning(f"Finviz API: Empty DataFrame returned for stock details of {tic}.")
                    return {}

                # --- Extract Data ---
                results = {}
                stock_data = df.iloc[0] # Assuming first row has the data

                # 1. Dividend Yield
                dividend_yield_col_names = ["Dividend Yield", "Dividend"]
                actual_div_yield_col = next((col for col in dividend_yield_col_names if col in df.columns), None)
                
                div_yield_float = 0.0 # Default to 0.0
                if actual_div_yield_col:
                    dividend_yield_str = stock_data[actual_div_yield_col]
                    if pd.notna(dividend_yield_str) and isinstance(dividend_yield_str, str) and dividend_yield_str.strip() != '-':
                        if dividend_yield_str.endswith('%'):
                            try:
                                div_yield_float = float(dividend_yield_str.strip('%')) / 100.0
                            except ValueError:
                                logging.error(f"Finviz API: Could not parse dividend yield string '{dividend_yield_str}' for {tic}.")
                results['dividend_yield'] = div_yield_float

                # 2. Earnings Date
                earnings_date_col = "Earnings Date" # Based on typical Finviz CSV exports
                earnings_date_str = None
                if earnings_date_col in df.columns:
                    earnings_date_val = stock_data[earnings_date_col]
                    if pd.notna(earnings_date_val) and isinstance(earnings_date_val, str) and earnings_date_val.strip() != '-':
                        earnings_date_str = earnings_date_val.strip()
                results['earnings_date'] = earnings_date_str

                logging.info(f"Successfully fetched details for {tic}: Div Yield={results['dividend_yield']:.4f}, Earnings='{results['earnings_date']}'")
                return results

            except requests.exceptions.RequestException as e_req:
                attempt += 1
                current_response_text = response.text if 'response' in locals() and response is not None else "No response object"
                if response is not None and response.status_code == 429 and attempt <= max_retries:
                    logging.warning(f"Finviz API rate limit hit for {tic} stock details. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                elif attempt > max_retries:
                    logging.error(f"Failed to fetch stock details for {tic} from Finviz after {max_retries} attempts. Error: {e_req}. Last response: {current_response_text[:200]}")
                    return {}
                elif response is not None and response.status_code == 400:
                    logging.error(f"Finviz API 400 Error for {tic} stock details: Likely invalid ticker. URL: {url}. Response: {current_response_text[:200]}")
                    return {} # Do not retry on 400
                else:
                    logging.warning(f"Retry {attempt}/{max_retries} for {tic} stock details due to error: {e_req}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
            
            except ValueError as e_val: # Handles "Invalid authentication" or parsing errors
                logging.error(f"Data processing error for {tic} stock details: {e_val}")
                return {}
            except Exception as e_other:
                 logging.error(f"An unexpected error occurred while processing Finviz stock details for {tic}: {e_other}")
                 return {}
        
        return {} # Fallback if all retries fail
