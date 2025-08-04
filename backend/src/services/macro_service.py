import pandas as pd
import numpy as np
from datetime import date, timedelta
from finvizfinance.futures import Futures

from src.my_libs_py3.fmp import FMPClient
from src.my_libs_py3.my_data import PriceDataFetcher
from .analysis_service import _get_market_price_from_finviz_df

def get_macro_futures_data():
    """Fetches key macro futures data from Finviz."""
    try:
        futures = Futures()
        futures_data = futures.get_futures()
        # Select key indicators for a macro overview
        key_indices = ['ES', 'NQ', 'RTY', 'YM', 'GC', 'SI', 'CL', 'NG', 'ZB', 'ZN', 'BTC']
        filtered_data = {k: v for k, v in futures_data.items() if k in key_indices}
        return filtered_data
    except Exception as e:
        return {"error": f"Failed to fetch futures data from Finviz: {e}"}


def calculate_market_implied_risk_free_rate(tickers: list, expiration_date: date):
    """
    Calculates an aggregate market-implied risk-free rate from a basket of liquid ETFs.
    """
    fmp = FMPClient()
    price_fetcher = PriceDataFetcher()
    all_valid_rates = []
    log_messages = [f"Starting market-implied risk-free rate calculation for expiry {expiration_date.strftime('%Y-%m-%d')}..."]
    
    days_to_exp = (expiration_date - date.today()).days
    if days_to_exp <= 0:
        log_messages.append("Target expiration date is not in the future. Cannot calculate rate.")
        return None, log_messages
    T = days_to_exp / 365.0

    for ticker in tickers:
        log_messages.append(f"--- Processing {ticker} ---")
        rt_quote = fmp.realtimequote(ticker)
        if rt_quote is None or rt_quote.empty or 'price' not in rt_quote.columns:
            log_messages.append(f"Could not fetch current price for {ticker}. Skipping.")
            continue
        S_current = rt_quote.price.iloc[0]

        option_chain_df = price_fetcher.get_option_data_finviz(ticker, 'o', expiration_date.strftime('%Y-%m-%d'))
        if option_chain_df is None or option_chain_df.empty:
            log_messages.append(f"Could not fetch option chain for {ticker}. Skipping.")
            continue
        
        option_chain_df['Strike'] = pd.to_numeric(option_chain_df['Strike'], errors='coerce')
        option_chain_df.dropna(subset=['Strike'], inplace=True)
        
        strikes = option_chain_df['Strike'].unique()
        atm_strikes = strikes[np.abs(strikes - S_current) < (S_current * 0.05)]
        
        if len(atm_strikes) == 0:
            log_messages.append(f"Could not find any near-the-money strikes for {ticker}. Skipping.")
            continue

        ticker_rates = []
        for K in atm_strikes:
            call_price = _get_market_price_from_finviz_df(option_chain_df, K, 'C')
            put_price = _get_market_price_from_finviz_df(option_chain_df, K, 'P')

            if call_price is not None and put_price is not None and T > 0:
                synthetic_forward = S_current - call_price + put_price
                if synthetic_forward > 0 and K > 0:
                    implied_r = - (1 / T) * np.log(synthetic_forward / K)
                    if -0.05 < implied_r < 0.25:
                        ticker_rates.append(implied_r)
        
        if ticker_rates:
            avg_rate_for_ticker = np.mean(ticker_rates)
            log_messages.append(f"Found {len(ticker_rates)} valid rates. Average for {ticker}: {avg_rate_for_ticker:.3%}")
            all_valid_rates.append(avg_rate_for_ticker)
        else:
            log_messages.append(f"No valid implied rates found for {ticker}.")

    if all_valid_rates:
        market_rate = np.mean(all_valid_rates)
        log_messages.append(f"--- FINAL ---")
        log_messages.append(f"Overall market-implied risk-free rate: {market_rate:.3%}")
        return market_rate, log_messages
    else:
        log_messages.append("Could not determine market-implied rate from any ticker.")
        return None, log_messages
