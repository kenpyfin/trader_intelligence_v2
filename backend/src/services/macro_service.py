import asyncio
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


async def _get_rates_for_ticker(ticker, target_expiration_date, price_fetcher, fmp):
    """Helper to fetch and calculate implied rates for a single ticker at a single target expiry."""
    logs = []
    # --- Find nearest option chain for the target DTE ---
    option_chain_df = None
    actual_expiration_date = None
    # Search up to 20 days forward to have a higher chance of finding the monthly expiry,
    # which may be further away than the standard 7-day search window.
    for i in range(21): # Search up to 20 days forward
        search_date = target_expiration_date + timedelta(days=i)
        search_date_str = search_date.strftime('%Y-%m-%d')
        temp_df = price_fetcher.get_option_data_finviz(ticker, 'o', search_date_str)
        if temp_df is not None and not temp_df.empty:
            option_chain_df = temp_df
            actual_expiration_date = search_date
            if i > 0:
                logs.append(f"For {ticker}, using chain for {search_date_str} (closest to target DTE).")
            break
    
    if option_chain_df is None:
        logs.append(f"Could not find option chain for {ticker} near target. Skipping.")
        return None, logs

    days_to_exp = (actual_expiration_date - date.today()).days
    if days_to_exp <= 0: return None, logs
    T = days_to_exp / 365.0
    
    rt_quote = fmp.realtimequote(ticker)
    if rt_quote is None or rt_quote.empty: return None, logs
    S_current = rt_quote.price.iloc[0]

    stock_details = price_fetcher.get_stock_details_finviz(ticker)
    q = stock_details.get('dividend_yield', 0.0) if stock_details else 0.0
    
    option_chain_df['Strike'] = pd.to_numeric(option_chain_df['Strike'], errors='coerce')
    option_chain_df.dropna(subset=['Strike'], inplace=True)
    
    strikes = option_chain_df['Strike'].unique()
    atm_strikes = strikes[np.abs(strikes - S_current) < (S_current * 0.05)]
    if len(atm_strikes) == 0: return None, logs

    ticker_rates = []
    for K in atm_strikes:
        call_price = _get_market_price_from_finviz_df(option_chain_df, K, 'C')
        put_price = _get_market_price_from_finviz_df(option_chain_df, K, 'P')
        if call_price is not None and put_price is not None and K > 0:
            numerator = (S_current * np.exp(-q * T)) - (call_price - put_price)
            if numerator > 0:
                implied_r = - (1 / T) * np.log(numerator / K)
                if -0.05 < implied_r < 0.25: ticker_rates.append(implied_r)
    
    if len(ticker_rates) >= 5:
        ticker_rates.sort()
        trim_count = int(len(ticker_rates) * 0.2)
        return np.mean(ticker_rates[trim_count:-trim_count]), logs
    elif ticker_rates:
        return np.mean(ticker_rates), logs
    
    return None, logs


async def calculate_market_implied_risk_free_rate(tickers: list):
    """
    Calculates a robust, aggregate market-implied risk-free rate by running queries
    for multiple tickers and expiries concurrently.
    """
    fmp = FMPClient()
    price_fetcher = PriceDataFetcher()
    log_messages = [f"Starting multi-expiry risk-free rate calculation..."]
    
    standard_dtes = [30, 60, 90, 180]
    final_rates_from_curve = []

    for dte in standard_dtes:
        target_expiration_date = date.today() + timedelta(days=dte)
        log_messages.append(f"--- Processing Target DTE: ~{dte} days ---")
        
        rates_for_this_dte = []
        # Process tickers sequentially for the current DTE to avoid potential rate-limiting.
        for ticker in tickers:
            rate, logs = await _get_rates_for_ticker(ticker, target_expiration_date, price_fetcher, fmp)
            log_messages.extend(logs)
            if rate is not None:
                rates_for_this_dte.append(rate)

        if rates_for_this_dte:
            avg_rate_for_dte = np.mean(rates_for_this_dte)
            log_messages.append(f"Average implied rate for DTE ~{dte} is {avg_rate_for_dte:.3%}")
            final_rates_from_curve.append(avg_rate_for_dte)

    if final_rates_from_curve:
        market_rate = np.mean(final_rates_from_curve)
        log_messages.append(f"--- FINAL ---")
        log_messages.append(f"Overall market-implied risk-free rate (averaged across expiries): {market_rate:.3%}")
        return market_rate, log_messages
    else:
        log_messages.append("Could not determine market-implied rate from any ticker or DTE.")
        return None, log_messages
