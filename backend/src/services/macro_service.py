import pandas as pd
import numpy as np
from datetime import date, timedelta
from src.my_libs_py3.fmp import FMPClient
from src.my_libs_py3.my_data import PriceDataFetcher
from .analysis_service import _get_market_price_from_finviz_df

def get_macro_futures_data():
    """Fetches key macro futures data from Finviz."""
    try:
        price_fetcher = PriceDataFetcher()
        futures_df = price_fetcher.get_futures_data_finviz()
        
        if futures_df.empty:
            return {"error": "Failed to fetch futures data from Finviz or no data returned."}
        
        # Set 'Ticker' as index and convert to dictionary of records
        futures_df.set_index('Ticker', inplace=True)
        futures_data = futures_df.to_dict('index')

        # Select key indicators for a macro overview
        key_indices = ['ES', 'NQ', 'RTY', 'YM', 'GC', 'SI', 'CL', 'NG', 'ZB', 'ZN', 'BTC']
        filtered_data = {k: v for k, v in futures_data.items() if k in key_indices}
        return filtered_data
    except Exception as e:
        return {"error": f"Failed to fetch futures data from Finviz: {e}"}


def calculate_market_implied_risk_free_rate(tickers: list, expiration_date: date):
    """
    Calculates a robust, aggregate market-implied risk-free rate from a basket of liquid ETFs.
    This improved method accounts for dividends, filters for option liquidity, and uses a
    trimmed mean to reduce the impact of outliers.
    """
    fmp = FMPClient()
    price_fetcher = PriceDataFetcher()
    all_valid_rates = []
    log_messages = [f"Starting robust market-implied risk-free rate calculation for expiry {expiration_date.strftime('%Y-%m-%d')}..."]
    
    days_to_exp = (expiration_date - date.today()).days
    if days_to_exp <= 0:
        log_messages.append("Target expiration date is not in the future. Cannot calculate rate.")
        return None, log_messages
    T = days_to_exp / 365.0

    for ticker in tickers:
        log_messages.append(f"--- Processing {ticker} ---")
        # 1. Fetch current price and dividend yield
        rt_quote = fmp.realtimequote(ticker)
        if rt_quote is None or rt_quote.empty or 'price' not in rt_quote.columns:
            log_messages.append(f"Could not fetch current price for {ticker}. Skipping.")
            continue
        S_current = rt_quote.price.iloc[0]

        stock_details = price_fetcher.get_stock_details_finviz(ticker)
        q = stock_details.get('dividend_yield', 0.0) if stock_details else 0.0
        log_messages.append(f"Using dividend yield (q) of {q:.2%}")

        # 2. Get option chain
        option_chain_df = price_fetcher.get_option_data_finviz(ticker, 'o', expiration_date.strftime('%Y-%m-%d'))
        if option_chain_df is None or option_chain_df.empty:
            log_messages.append(f"Could not fetch option chain for {ticker}. Skipping.")
            continue
        
        option_chain_df['Strike'] = pd.to_numeric(option_chain_df['Strike'], errors='coerce')
        option_chain_df.dropna(subset=['Strike'], inplace=True)
        
        # 3. Select near-the-money strikes
        strikes = option_chain_df['Strike'].unique()
        atm_strikes = strikes[np.abs(strikes - S_current) < (S_current * 0.05)]
        
        if len(atm_strikes) == 0:
            log_messages.append(f"Could not find any near-the-money strikes for {ticker}. Skipping.")
            continue

        # 4. Calculate implied rate for each strike using dividend-adjusted formula
        ticker_rates = []
        for K in atm_strikes:
            call_price = _get_market_price_from_finviz_df(option_chain_df, K, 'C')
            put_price = _get_market_price_from_finviz_df(option_chain_df, K, 'P')

            if call_price is not None and put_price is not None and T > 0 and K > 0:
                # Dividend-adjusted put-call parity: C - P = S*e^(-qT) - K*e^(-rT)
                # Solved for r: r = - (1/T) * ln( (S*e^(-qT) - (C - P)) / K )
                dividend_discount_factor = np.exp(-q * T)
                price_difference = call_price - put_price
                
                numerator = (S_current * dividend_discount_factor) - price_difference
                
                if numerator > 0:
                    implied_r = - (1 / T) * np.log(numerator / K)
                    # Filter for reasonable rates to exclude calculation errors/anomalies
                    if -0.05 < implied_r < 0.25:
                        ticker_rates.append(implied_r)
        
        # 5. Use a trimmed mean for robustness against outliers
        if len(ticker_rates) >= 5: # Only trim if we have enough data points
            ticker_rates.sort()
            trim_count = int(len(ticker_rates) * 0.2) # Trim 20% from each end
            trimmed_rates = ticker_rates[trim_count:-trim_count]
            avg_rate_for_ticker = np.mean(trimmed_rates)
            log_messages.append(f"Found {len(ticker_rates)} valid rates. Trimmed mean for {ticker}: {avg_rate_for_ticker:.3%}")
            all_valid_rates.append(avg_rate_for_ticker)
        elif ticker_rates:
            avg_rate_for_ticker = np.mean(ticker_rates)
            log_messages.append(f"Found {len(ticker_rates)} valid rates (not enough to trim). Average for {ticker}: {avg_rate_for_ticker:.3%}")
            all_valid_rates.append(avg_rate_for_ticker)
        else:
            log_messages.append(f"No valid liquid option pairs found for {ticker} to calculate rate.")

    if all_valid_rates:
        # Also use a trimmed mean (or median for small N) for the final aggregate rate
        if len(all_valid_rates) >= 3:
             all_valid_rates.sort()
             # Using median for small sample of tickers is robust
             market_rate = np.median(all_valid_rates)
        elif all_valid_rates:
             market_rate = np.mean(all_valid_rates)
        else: # No rates found at all
            log_messages.append("Could not determine market-implied rate from any ticker.")
            return None, log_messages

        log_messages.append(f"--- FINAL ---")
        log_messages.append(f"Overall market-implied risk-free rate: {market_rate:.3%}")
        return market_rate, log_messages
    else:
        log_messages.append("Could not determine market-implied rate from any ticker.")
        return None, log_messages
