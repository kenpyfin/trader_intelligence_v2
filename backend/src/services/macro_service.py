import asyncio
import pandas as pd
import numpy as np
from datetime import date, timedelta
from src.my_libs_py3.fmp import FMPClient
from src.my_libs_py3.my_data import PriceDataFetcher
# from .analysis_service import _get_market_price_from_finviz_df # No longer used
from .connection_manager import connection_manager
from datetime import datetime

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


def _get_market_price_from_alpaca_df(df, strike, option_type_char):
    """
    Extracts a market price for a specific option from an Alpaca DataFrame.
    Tries Bid/Ask midpoint, then Last Trade. Uses spread for liquidity check.
    """
    if df is None or df.empty:
        return None

    type_to_match = 'call' if option_type_char.upper() == 'C' else 'put'
    option_row_df = df[(df['Strike'] == strike) & (df['Type'].str.lower() == type_to_match)]

    if option_row_df.empty:
        return None

    option_row = option_row_df.iloc[0]

    bid = pd.to_numeric(option_row.get('Bid'), errors='coerce')
    ask = pd.to_numeric(option_row.get('Ask'), errors='coerce')

    # Liquidity check based on bid/ask spread
    if pd.notna(bid) and pd.notna(ask) and ask > 0 and bid > 0 and (ask - bid) / ask < 0.5:
        return (bid + ask) / 2.0

    # Fallback to Last Trade if midpoint is not liquid enough
    last_trade = pd.to_numeric(option_row.get('Last Trade'), errors='coerce')
    if pd.notna(last_trade) and last_trade > 0:
        return last_trade
        
    return None

async def calculate_market_implied_risk_free_rate(tickers: list):
    """
    Calculates a robust, aggregate market-implied risk-free rate by running queries
    for multiple tickers and expiries concurrently using Alpaca data.
    """
    trader = await connection_manager.get_trader()
    log_messages = [f"Starting multi-expiry risk-free rate calculation..."]
    
    standard_dtes = [30, 60, 90]
    final_rates_from_curve = []

    for dte in standard_dtes:
        target_expiration_date = date.today() + timedelta(days=dte)
        log_messages.append(f"--- Processing Target DTE: ~{dte} days ---")
        
        rates_for_this_dte = []
        for ticker in tickers:
            try:
                # 1. Get current price
                S_current = await trader.get_current_price(ticker, "STK")
                if S_current is None:
                    log_messages.append(f"ERROR: Could not fetch current price for {ticker}. Skipping.")
                    continue
                log_messages.append(f"INFO: For {ticker}, current price: ${S_current:.2f}")

                # 2. Find closest available expiration
                available_expirations = await trader.get_option_expirations(ticker)
                if not available_expirations:
                    log_messages.append(f"WARN: No option expirations found for {ticker}. Skipping.")
                    continue
                
                available_dates_dt = [datetime.strptime(exp, '%Y%m%d').date() for exp in available_expirations]
                time_diffs = [abs(target_expiration_date - d) for d in available_dates_dt]
                closest_date_idx = np.argmin(time_diffs)
                closest_expiration_date = available_dates_dt[closest_date_idx]
                expiration_date_to_use_str = closest_expiration_date.strftime('%Y%m%d')

                log_messages.append(f"For {ticker}, using chain for {closest_expiration_date.strftime('%Y-%m-%d')} (closest to target DTE).")

                # 3. Calculate time to expiration (T) based on the ACTUAL expiry date
                days_to_exp = (closest_expiration_date - date.today()).days
                if days_to_exp <= 0: continue
                T = days_to_exp / 365.0
                
                # 4. Get option chain
                option_chain_df = await trader.get_option_chain_df(ticker, expiration_date_to_use_str)
                if option_chain_df is None or option_chain_df.empty: continue

                # 5. Calculate rates
                strikes = option_chain_df['Strike'].unique()
                atm_strikes = strikes[np.abs(strikes - S_current) < (S_current * 0.05)]
                if len(atm_strikes) == 0: continue

                ticker_rates = []
                for K in atm_strikes:
                    call_price = _get_market_price_from_alpaca_df(option_chain_df, K, 'C')
                    put_price = _get_market_price_from_alpaca_df(option_chain_df, K, 'P')

                    if call_price is not None and put_price is not None:
                        synthetic_forward = S_current - call_price + put_price
                        if synthetic_forward > 0 and K > 0:
                            implied_r = - (1 / T) * np.log(synthetic_forward / K)
                            if -0.05 < implied_r < 0.25:
                                ticker_rates.append(implied_r)
                
                if ticker_rates:
                    rates_for_this_dte.append(np.mean(ticker_rates))

            except Exception as e:
                import traceback
                log_messages.append(f"CRITICAL error processing {ticker} for DTE {dte}: {e}")
                log_messages.append(traceback.format_exc())

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
