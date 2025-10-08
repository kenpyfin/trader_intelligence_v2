import asyncio
import pandas as pd
import numpy as np
from datetime import date, timedelta
import json
import re
import os
from typing import Any, Dict, Optional

# IB-insync asyncio patching is not required in a FastAPI/uvicorn environment
# and is incompatible with the 'uvloop' used by uvicorn.


from src.my_libs_py3.my_data import PriceDataFetcher
from src.my_libs_py3.fmp import FMPClient
from .connection_manager import connection_manager
import plotly.graph_objects as go
from src.analytics.sabr import calibrate_sabr, sabr_iv
from src.analytics.analysis import _parse_finviz_iv_string
from src.analytics.treasury_curve import build_treasury_curve
from src.analytics.methodologies.gpt_verdict import generate_gpt_verdict
from src.my_libs_py3.db import mongo


async def get_option_expirations(ticker: str):
    """
    Fetches the next 10 available option expiration dates for a given ticker.
    """
    trader = await connection_manager.get_trader()
    # This will require a new method in IBTrader
    expirations = await trader.get_option_expirations(ticker)
    
    # The dates from IB are strings 'YYYYMMDD'. Sorting them is correct.
    sorted_expirations = sorted(expirations)
    
    # Return up to the next 10 dates
    return sorted_expirations[:10]


# A custom JSON encoder to handle numpy types, useful for FastAPI's response model
class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)

# --- Helper Functions from option_trade.py ---
def calculate_historical_volatility(prices, lookback_days=20):
    if len(prices) < lookback_days + 1:
        if len(prices) < 2: return 0.0
        lookback_days = len(prices) - 1
    relevant_prices = prices[-lookback_days-1:]
    returns = np.diff(np.log(relevant_prices))
    annualization_factor = np.sqrt(252)
    hv = np.std(returns) * annualization_factor
    return hv

def generate_forward_vol_structure(days_to_expiration, key_vol_points):
    if days_to_expiration <= 0: return np.array([])
    if not key_vol_points: return np.full(days_to_expiration, 0.20)
    key_vol_points.sort()
    _days, _vols = zip(*key_vol_points)
    days, vols = list(_days), list(_vols)
    if not days or days[0] != 0:
        first_vol = vols[0] if vols else 0.20
        days.insert(0, 0)
        vols.insert(0, first_vol)
    days_arr, vols_arr = np.array(days, dtype=float), np.array(vols, dtype=float)
    target_days_for_spot = np.arange(days_to_expiration + 1)
    spot_vols_daily = np.interp(target_days_for_spot, days_arr, vols_arr)
    forward_vols = np.zeros(days_to_expiration)
    for i in range(days_to_expiration):
        t_i, t_i_plus_1 = i / 365.0, (i + 1) / 365.0
        var_i, var_i_plus_1 = spot_vols_daily[i]**2 * t_i, spot_vols_daily[i+1]**2 * t_i_plus_1
        numerator, denominator = var_i_plus_1 - var_i, t_i_plus_1 - t_i
        if denominator <= 0:
            forward_vols[i] = spot_vols_daily[i+1] if i + 1 < len(spot_vols_daily) else spot_vols_daily[i]
        else:
            forward_vols[i] = np.sqrt(max(0, numerator) / denominator)
    return forward_vols

def universal_binomial_pricer(S, K, expiration_date, r_input, sigma_input, model='jarrow_rudd', option_type='call', exercise_type='american', div=0.0, historical_vol=None):
    today = date.today()
    days_to_expiration = (expiration_date - today).days
    if days_to_expiration <= 0:
        price = np.maximum(0, S - K if option_type == 'call' else K - S)
        return price, {'delta': 1 if S > K else -1, 'gamma': 0, 'theta': 0, 'vega': 0}, ["Option has expired."], 0.0
    N, T = days_to_expiration, days_to_expiration / 365.0
    dt = T / N
    def process_param(param_input, t_values):
        if callable(param_input): return np.array([param_input(t) for t in t_values])
        if isinstance(param_input, (list, np.ndarray)): return np.array(param_input)
        return np.full(N, float(param_input))
    time_steps = np.linspace(0, T - dt, N)
    r_rates, sigma_vols = process_param(r_input, time_steps), process_param(sigma_input, time_steps)
    stock_price_tree = np.zeros((N + 1, N + 1)); stock_price_tree[0, 0] = S
    p_steps = np.zeros(N)
    for i in range(N):
        r_step, sigma_step = r_rates[i], sigma_vols[i]
        if model.lower() == 'jarrow_rudd':
            p = 0.5
            drift = (r_step - div - 0.5 * sigma_step**2) * dt
            u, d = np.exp(drift + sigma_step * np.sqrt(dt)), np.exp(drift - sigma_step * np.sqrt(dt))
        else:
            u, d = np.exp(sigma_step * np.sqrt(dt)), 1 / np.exp(sigma_step * np.sqrt(dt))
            p = (np.exp((r_step - div) * dt) - d) / (u - d)
        p_steps[i] = p
        for j in range(i + 1):
            if stock_price_tree[j, i] > 0:
                stock_price_tree[j, i + 1] = stock_price_tree[j, i] * u
                stock_price_tree[j + 1, i + 1] = stock_price_tree[j, i] * d
    option_value_tree = np.zeros((N + 1, N + 1))
    exercise_decision_tree = np.full((N + 1, N + 1), False)
    option_value_tree[:, N] = np.maximum(0, stock_price_tree[:, N] - K if option_type == 'call' else K - stock_price_tree[:, N])
    for i in range(N - 1, -1, -1):
        r_step, p_step = r_rates[i], p_steps[i]
        for j in range(i + 1):
            expected_value = (p_step * option_value_tree[j, i + 1] + (1 - p_step) * option_value_tree[j + 1, i + 1])
            continuation_value = np.exp(-r_step * dt) * expected_value
            if exercise_type == 'european':
                option_value_tree[j, i] = continuation_value
            else:
                intrinsic_value = np.maximum(0, stock_price_tree[j, i] - K if option_type == 'call' else K - stock_price_tree[j, i])
                option_value_tree[j, i] = np.maximum(continuation_value, intrinsic_value)
                if intrinsic_value > continuation_value: exercise_decision_tree[j, i] = True
    greeks = {}
    if N >= 2:
        delta_num = option_value_tree[0, 1] - option_value_tree[1, 1]
        delta_den = stock_price_tree[0, 1] - stock_price_tree[1, 1]
        delta = delta_num / delta_den if delta_den != 0 else (1.0 if option_type == 'call' else -1.0)
        delta_u_num = option_value_tree[0, 2] - option_value_tree[1, 2]
        delta_u_den = stock_price_tree[0, 2] - stock_price_tree[1, 2]
        delta_up = delta_u_num / delta_u_den if delta_u_den != 0 else delta
        delta_d_num = option_value_tree[1, 2] - option_value_tree[2, 2]
        delta_d_den = stock_price_tree[1, 2] - stock_price_tree[2, 2]
        delta_down = delta_d_num / delta_d_den if delta_d_den != 0 else delta
        gamma_num = delta_up - delta_down
        gamma_den = 0.5 * (stock_price_tree[0, 2] - stock_price_tree[2, 2])
        gamma = gamma_num / gamma_den if gamma_den != 0 else 0.0
        theta = (option_value_tree[1, 2] - option_value_tree[0,0]) / (2 * dt)
        greeks = {'delta': delta, 'gamma': gamma, 'theta': theta}
    elif N == 1:
        delta_num = option_value_tree[0, 1] - option_value_tree[1, 1]
        delta_den = stock_price_tree[0, 1] - stock_price_tree[1, 1]
        delta = delta_num / delta_den if delta_den != 0 else (1.0 if option_type == 'call' else -1.0)
        greeks = {'delta': delta, 'gamma': 0, 'theta': 0}
    actionable_alerts = []
    # ... (Alert generation logic omitted for brevity, but would be included here)
    early_exercise_premium_at_t0 = 0.0
    if N > 0 and exercise_type == 'american':
        intrinsic_value_t0 = np.maximum(0, stock_price_tree[0, 0] - K if option_type == 'call' else K - stock_price_tree[0, 0])
        if N >= 1:
            continuation_value_t0 = np.exp(-r_rates[0] * dt) * (p_steps[0] * option_value_tree[0, 1] + (1 - p_steps[0]) * option_value_tree[1, 1])
            if intrinsic_value_t0 > continuation_value_t0:
                early_exercise_premium_at_t0 = intrinsic_value_t0 - continuation_value_t0
    return option_value_tree[0,0], greeks, actionable_alerts, early_exercise_premium_at_t0


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


async def calculate_market_implied_risk_free_rate(expiration_date, tickers=['SPY', 'QQQ', 'IWM']):
    """
    Calculates an aggregate market-implied risk-free rate from a basket of liquid ETFs
    for a given expiration date using Alpaca data.
    """
    trader = await connection_manager.get_trader()
    all_valid_rates = []
    log_messages = [f"Starting market-implied risk-free rate calculation for expiry {expiration_date.strftime('%Y-%m-%d')}..."]
    
    days_to_exp = (expiration_date - date.today()).days
    T = days_to_exp / 365.0

    if T <= 0:
        log_messages.append("Target expiration date is not in the future. Cannot calculate rate.")
        return None, log_messages

    for ticker in tickers:
        log_messages.append(f"--- Processing {ticker} ---")
        try:
            # 1. Get current price
            S_current = await trader.get_current_price(ticker, "STK")
            if S_current is None:
                log_messages.append(f"Could not fetch current price for {ticker}. Skipping.")
                continue

            # 2. Find closest available expiration and get option chain from Alpaca
            target_expiration_str = expiration_date.strftime('%Y%m%d')
            available_expirations = await trader.get_option_expirations(ticker)
            if not available_expirations:
                log_messages.append(f"No option expirations found for {ticker}. Skipping.")
                continue

            target_date_dt = datetime.strptime(target_expiration_str, '%Y%m%d')
            available_dates_dt = [datetime.strptime(exp, '%Y%m%d') for exp in available_expirations]
            
            time_diffs = [abs(target_date_dt - d) for d in available_dates_dt]
            closest_date_idx = np.argmin(time_diffs)
            closest_expiration_dt = available_dates_dt[closest_date_idx]
            expiration_date_to_use = closest_expiration_dt.strftime('%Y%m%d')

            if expiration_date_to_use != target_expiration_str:
                log_messages.append(f"Target date {expiration_date.strftime('%Y-%m-%d')} not available. Using closest expiration: {closest_expiration_dt.strftime('%Y-%m-%d')}.")

            option_chain_df = await trader.get_option_chain_df(ticker, expiration_date_to_use)
            if option_chain_df is None or option_chain_df.empty:
                log_messages.append(f"Could not fetch option chain for {ticker} on {expiration_date_to_use}. Skipping.")
                continue
            
            # 3. Select near-the-money strikes
            strikes = option_chain_df['Strike'].unique()
            atm_strikes = strikes[np.abs(strikes - S_current) < (S_current * 0.05)] # Within 5% of stock price
            
            if len(atm_strikes) == 0:
                log_messages.append("Could not find any near-the-money strikes. Skipping.")
                continue

            ticker_rates = []
            for K in atm_strikes:
                call_price = _get_market_price_from_alpaca_df(option_chain_df, K, 'C')
                put_price = _get_market_price_from_alpaca_df(option_chain_df, K, 'P')

                if call_price is not None and put_price is not None:
                    # Put-Call Parity: C - P = S - K*exp(-rT)
                    synthetic_forward = S_current - call_price + put_price
                    if synthetic_forward > 0 and K > 0:
                        implied_r = - (1 / T) * np.log(synthetic_forward / K)
                        if -0.05 < implied_r < 0.25: # Filter for reasonable rates
                            ticker_rates.append(implied_r)
            
            if ticker_rates:
                avg_rate_for_ticker = np.mean(ticker_rates)
                log_messages.append(f"Found {len(ticker_rates)} valid rates. Average for {ticker}: {avg_rate_for_ticker:.3%}")
                all_valid_rates.append(avg_rate_for_ticker)
            else:
                log_messages.append(f"No valid implied rates found for {ticker}.")
        except Exception as e:
            import traceback
            log_messages.append(f"An error occurred while processing {ticker}: {e}")
            log_messages.append(traceback.format_exc())

    if all_valid_rates:
        market_rate = np.mean(all_valid_rates)
        log_messages.append(f"--- FINAL ---")
        log_messages.append(f"Overall market-implied risk-free rate: {market_rate:.3%}")
        return market_rate, log_messages
    else:
        log_messages.append("Could not determine market-implied rate from any ticker.")
        return None, log_messages


def _get_market_price_from_finviz_df(df, strike, option_type_char, current_stock_price_for_atm_fallback=None):
    if df is None or df.empty: return None
    if 'Strike' not in df.columns or 'Type' not in df.columns: return None
    df['Strike'] = pd.to_numeric(df['Strike'], errors='coerce')
    type_to_match = 'call' if option_type_char.upper() == 'C' else 'put'
    option_row_df = df[(df['Strike'] == strike) & (df['Type'].str.lower() == type_to_match)]
    if option_row_df.empty: return None
    option_row = option_row_df.iloc[0]
    
    # --- Robust Liquidity Check ---
    # To get a reliable price, we need to ensure the option is liquid.
    # We check for a valid bid/ask, minimum volume, minimum open interest, and a tight spread.
    bid = pd.to_numeric(option_row.get('Bid'), errors='coerce')
    ask = pd.to_numeric(option_row.get('Ask'), errors='coerce')
    volume = pd.to_numeric(option_row.get('Volume'), errors='coerce')
    open_int = pd.to_numeric(option_row.get('Open Int.'), errors='coerce')

    is_liquid = (
        pd.notna(bid) and pd.notna(ask) and
        bid > 0.01 and ask > 0.01 and  # Price must be meaningful.
        pd.notna(volume) and volume >= 10 and # Minimum volume to be considered active.
        pd.notna(open_int) and open_int >= 100 and # Minimum open interest for established market.
        (ask - bid) / ask < 0.25  # Bid-ask spread must be less than 25% of ask price.
    )

    if is_liquid:
        # Use the midpoint of the bid-ask spread for the most current, reliable price.
        return (bid + ask) / 2.0
    
    # If the option is not liquid, we return None as fallbacks like 'Last Trade' or 'Last Close'
    # can be stale and misleading for an implied rate calculation.
    return None

def _get_atm_iv_from_finviz_df(df, current_stock_price):
    if df is None or df.empty or 'Strike' not in df.columns or 'IV' not in df.columns: return None
    df['Strike'] = pd.to_numeric(df['Strike'], errors='coerce')
    df = df.dropna(subset=['Strike'])
    if df.empty: return None
    try:
        diff_series = (df['Strike'] - current_stock_price).abs()
        atm_option_row = df.iloc[diff_series.argsort()[:1]]
    except Exception: return None
    if not atm_option_row.empty:
        return _parse_finviz_iv_string(atm_option_row['IV'].iloc[0])
    return None

def fetch_iv_term_structure(ticker, price_fetcher, fmp_client, target_dtes=[7, 30, 90]):
    log_messages = []
    key_iv_points = []
    MAX_DATE_SEARCH_ATTEMPTS = 7
    rt_quote = fmp_client.realtimequote(ticker)
    if rt_quote is None or rt_quote.empty or 'price' not in rt_quote.columns: return [], log_messages
    current_stock_price = rt_quote.price.iloc[0]
    if current_stock_price is None: return [], log_messages
    for dte in target_dtes:
        expiration_date_dt = date.today() + timedelta(days=dte)
        found_data_for_dte = False
        for attempt in range(MAX_DATE_SEARCH_ATTEMPTS + 1):
            current_search_date_dt = expiration_date_dt + timedelta(days=attempt)
            current_search_date_str = current_search_date_dt.strftime('%Y-%m-%d')
            options_df = price_fetcher.get_option_data_finviz(ticker, 'o', current_search_date_str)
            if options_df is not None and not options_df.empty:
                atm_iv = _get_atm_iv_from_finviz_df(options_df, current_stock_price)
                if atm_iv is not None:
                    key_iv_points.append((dte, atm_iv))
                    found_data_for_dte = True
                    break
                else:
                    found_data_for_dte = True
                    break
        if not found_data_for_dte: log_messages.append(f"DTE {dte}: No data found.")
    if key_iv_points:
        key_iv_points.sort()
        if key_iv_points[0][0] != 0:
            key_iv_points.insert(0, (0, key_iv_points[0][1]))
    return key_iv_points, log_messages

def parse_earnings_date(earnings_str, today=date.today()):
    if not earnings_str or pd.isna(earnings_str) or earnings_str.strip() == '-': return None
    from datetime import datetime
    try:
        date_part = earnings_str.split(' ')[0]
        for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
            try: return datetime.strptime(date_part, fmt).date()
            except ValueError: continue
    except (ValueError, IndexError): pass
    try:
        cleaned_str = earnings_str.split('/')[0].strip()
        dt_obj = datetime.strptime(cleaned_str, '%b %d').date()
        if dt_obj.month < today.month or (dt_obj.month == today.month and dt_obj.day < today.day):
            return dt_obj.replace(year=today.year + 1)
        return dt_obj.replace(year=today.year)
    except (ValueError, AttributeError): return None

def analyze_high_movement_expectation(S_current, option_chain_df, historical_prices_df, earnings_date=None, expiration_date=None):
    """Analyzes factors suggesting high movement expectation."""
    analysis = {}

    # 1. Calculate Expected Move from ATM straddle
    if option_chain_df is None or option_chain_df.empty:
        analysis['expected_move_note'] = "Option chain data not available to calculate expected move."
    else:
        # Ensure Strike is numeric before processing
        if 'Strike' in option_chain_df.columns:
            option_chain_df['Strike'] = pd.to_numeric(option_chain_df['Strike'], errors='coerce')
            strikes = option_chain_df['Strike'].dropna().unique()
            if len(strikes) > 0:
                atm_strike_idx = np.argmin(np.abs(strikes - S_current))
                atm_strike = strikes[atm_strike_idx]
                
                atm_call_price = _get_market_price_from_finviz_df(option_chain_df, atm_strike, 'C')
                atm_put_price = _get_market_price_from_finviz_df(option_chain_df, atm_strike, 'P')
                
                if atm_call_price is not None and atm_put_price is not None:
                    atm_straddle_price = atm_call_price + atm_put_price
                    expected_move_pct = (atm_straddle_price / S_current) * 100 if S_current > 0 else 0
                    analysis['expected_move_pct'] = expected_move_pct
                    analysis['atm_straddle_price'] = atm_straddle_price
                    analysis['atm_strike'] = atm_strike
                else:
                    analysis['expected_move_note'] = f"Could not calculate expected move (market prices unavailable for ATM strike ${atm_strike:.2f})."
            else:
                analysis['expected_move_note'] = "No valid strikes found in option chain data."
        else:
            analysis['expected_move_note'] = "Strike column missing from option data."


    # 2. Volatility compression check (coiling spring)
    if historical_prices_df is not None and not historical_prices_df.empty and 'Close' in historical_prices_df.columns:
        closing_prices = historical_prices_df['Close'].tolist()
        if len(closing_prices) >= 51:
            hv_10d = calculate_historical_volatility(closing_prices, lookback_days=10)
            hv_50d = calculate_historical_volatility(closing_prices, lookback_days=50)
            analysis['hv_10d'] = hv_10d
            analysis['hv_50d'] = hv_50d
            if hv_10d < hv_50d * 0.8: # Threshold for compression
                is_coiling_before_earnings = False
                if earnings_date:
                    days_to_earnings = (earnings_date - date.today()).days
                    if 0 < days_to_earnings <= 21:
                        is_coiling_before_earnings = True
                        analysis['vol_compression_text'] = f"Volatility compression detected ahead of earnings in {days_to_earnings} days. This 'coiling' often precedes a significant price move."
                
                if not is_coiling_before_earnings:
                    analysis['vol_compression_text'] = "Possible volatility compression detected: 10-day HV is significantly lower than 50-day HV, suggesting a 'coiling' pattern."
            else:
                 analysis['vol_compression_text'] = "No significant volatility compression detected."
        else:
            analysis['vol_compression_text'] = "Not enough data for volatility compression analysis (need 51+ days)."
    else:
        analysis['vol_compression_text'] = "Historical price data not available for volatility compression analysis."

    # 3. Earnings date analysis
    if earnings_date and expiration_date:
        if date.today() < earnings_date <= expiration_date:
            analysis['earnings_within_expiry'] = True
            days_to_earnings = (earnings_date - date.today()).days
            analysis['earnings_note'] = f"Major Catalyst Event: Upcoming earnings on {earnings_date.strftime('%Y-%m-%d')} ({days_to_earnings} days), which is before expiration."
        else:
            analysis['earnings_within_expiry'] = False
            if earnings_date > date.today():
                analysis['earnings_note'] = f"Next earnings date ({earnings_date.strftime('%Y-%m-%d')}) is after the option's expiration."

    return analysis


def analyze_volume_and_oi_signals(df, S_current):
    """
    Analyzes volume and open interest from an option chain DataFrame to find market signals.
    """
    if df is None or df.empty:
        return {"error": "Option chain data is not available."}

    analysis = {
        "pc_ratio": None, "uoa_calls": [], "uoa_puts": [],
        "oi_put_wall": None, "oi_call_wall": None, "notes": []
    }

    # --- Data Preparation ---
    required_cols = ['Volume', 'Open Int.', 'Type', 'Strike']
    for col in required_cols:
        if col not in df.columns:
            analysis['notes'].append(f"Missing required column: {col}")
            return analysis
    
    df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce').fillna(0)
    df['Open Int.'] = pd.to_numeric(df['Open Int.'], errors='coerce').fillna(0)
    df['Strike'] = pd.to_numeric(df['Strike'], errors='coerce')
    df.dropna(subset=['Strike', 'Type'], inplace=True)

    calls = df[df['Type'].str.lower() == 'call']
    puts = df[df['Type'].str.lower() == 'put']

    if calls.empty and puts.empty:
        analysis['notes'].append("No valid call or put data found after cleaning.")
        return analysis

    # --- 1. Put/Call Ratio (Volume) ---
    total_call_volume = calls['Volume'].sum()
    total_put_volume = puts['Volume'].sum()
    if total_call_volume > 0:
        analysis['pc_ratio'] = total_put_volume / total_call_volume
    
    # --- 2. Unusual Option Activity (UOA) ---
    otm_calls = calls[calls['Strike'] > S_current]
    otm_puts = puts[puts['Strike'] < S_current]
    
    # Use .copy() to avoid SettingWithCopyWarning when adding a new column
    uoa_candidates_c = otm_calls[(otm_calls['Volume'] > otm_calls['Open Int.']) & (otm_calls['Volume'] > 500)].copy()
    if not uoa_candidates_c.empty:
        uoa_candidates_c['vol_oi_ratio'] = uoa_candidates_c['Volume'] / (uoa_candidates_c['Open Int.'] + 1)
        analysis['uoa_calls'] = uoa_candidates_c.sort_values('vol_oi_ratio', ascending=False).head(3).to_dict('records')

    # Use .copy() to avoid SettingWithCopyWarning
    uoa_candidates_p = otm_puts[(otm_puts['Volume'] > otm_puts['Open Int.']) & (otm_puts['Volume'] > 500)].copy()
    if not uoa_candidates_p.empty:
        uoa_candidates_p['vol_oi_ratio'] = uoa_candidates_p['Volume'] / (uoa_candidates_p['Open Int.'] + 1)
        analysis['uoa_puts'] = uoa_candidates_p.sort_values('vol_oi_ratio', ascending=False).head(3).to_dict('records')

    # --- 3. Open Interest "Walls" ---
    if not otm_puts.empty and len(otm_puts) > 2:
        put_wall_candidate = otm_puts.loc[otm_puts['Open Int.'].idxmax()]
        if put_wall_candidate['Open Int.'] > otm_puts['Open Int.'].mean() * 3 and put_wall_candidate['Open Int.'] > 1000:
            analysis['oi_put_wall'] = put_wall_candidate.to_dict()

    if not otm_calls.empty and len(otm_calls) > 2:
        call_wall_candidate = otm_calls.loc[otm_calls['Open Int.'].idxmax()]
        if call_wall_candidate['Open Int.'] > otm_calls['Open Int.'].mean() * 3 and call_wall_candidate['Open Int.'] > 1000:
            analysis['oi_call_wall'] = call_wall_candidate.to_dict()

    return analysis


def analyze_candlestick_patterns(df):
    """
    Analyzes recent candlestick data for key patterns within the broader market context.
    """
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    if df is None or not all(col in df.columns for col in required_cols) or len(df) < 51:
        return {"error": "Not enough historical data for contextual candlestick analysis (need at least 51 periods).", "context": {}}

    df = df.copy()
    # Ensure datetime index for date-aware plotting
    if 'TimeStamp' in df.columns:
        try:
            df['TimeStamp'] = pd.to_datetime(df['TimeStamp'], errors='coerce')
            df.sort_values('TimeStamp', inplace=True)
            df.set_index('TimeStamp', inplace=True)
        except Exception:
            pass
    for col in required_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.dropna(subset=required_cols, inplace=True)
    if len(df) < 51:
        return {"error": "Not enough valid data points after cleaning.", "context": {}}

    # --- Calculate Indicators for Context ---
    df['SMA10'] = df['Close'].rolling(window=10).mean()
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    df['SMA100'] = df['Close'].rolling(window=100).mean()
    df['SMA200'] = df['Close'].rolling(window=200).mean()
    df['AvgVol10'] = df['Volume'].rolling(window=10).mean().shift(1) # Shift to get prior 10 day avg vol

    # --- Establish Market Context ---
    last_row = df.iloc[-1]
    secondary_trend = "Uptrend" if last_row['Close'] > last_row['SMA50'] else "Downtrend"
    primary_trend = "Uptrend" if last_row['Close'] > last_row['SMA200'] else "Downtrend"
    market_context = {"primary_trend": primary_trend, "secondary_trend": secondary_trend}

    # --- Pattern Recognition Setup ---
    max_lookback = min(4, len(df))
    get_iloc = lambda col, i: df[col].iloc[-1-i]
    O, H, L, C, V, AvgVol10 = ({i: get_iloc(col, i) for i in range(max_lookback)} for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'AvgVol10'])

    def Body(x): return abs(O.get(x, 0) - C.get(x, 0))
    def UpperShadow(x): return H.get(x, 0) - max(O.get(x, 0), C.get(x, 0))
    def LowerShadow(x): return min(O.get(x, 0), C.get(x, 0)) - L.get(x, 0)
    
    found_patterns = []
    is_downtrend = secondary_trend == "Downtrend" or (C.get(0, 0) < C.get(1, 0) and C.get(1, 0) < C.get(2, 0))
    is_uptrend = secondary_trend == "Uptrend" or (C.get(0, 0) > C.get(1, 0) and C.get(1, 0) > C.get(2, 0))

    def build_interpretation(base_interp, vol_idx, name):
        is_high_vol = V.get(vol_idx, 0) > AvgVol10.get(vol_idx, 0) * 1.2
        vol_msg = "on high volume, strengthening the signal." if is_high_vol else "on average volume."
        strength = "Strong" if is_high_vol and "Engulfing" in name else ("Moderate" if is_high_vol else "Weak")
        return f"{base_interp} It appeared {vol_msg}", strength

    # --- Bullish Reversal Patterns ---
    if is_downtrend:
        if LowerShadow(0) > (2 * Body(0)) and UpperShadow(0) < (0.1 * (H[0] - L[0])):
            interp, strength = build_interpretation("Sellers were rejected after a decline.", 0, "Hammer")
            found_patterns.append({"name": "Hammer (Bullish Reversal)", "interpretation": interp, "strength": strength})
        if Body(0) > 0 and C.get(1, C[0]) < O.get(1, C[0]) and C[0] > O[1] and O[0] < C[1]:
            interp, strength = build_interpretation("A powerful momentum shift where buyers overwhelmed sellers.", 0, "Bullish Engulfing")
            found_patterns.append({"name": "Bullish Engulfing", "interpretation": interp, "strength": strength})

    # --- Bearish Reversal Patterns ---
    if is_uptrend:
        if UpperShadow(0) > (2 * Body(0)) and LowerShadow(0) < (0.1 * (H[0] - L[0])):
            interp, strength = build_interpretation("Buyers were rejected after a rally.", 0, "Shooting Star")
            found_patterns.append({"name": "Shooting Star (Bearish Reversal)", "interpretation": interp, "strength": strength})
        if Body(0) > 0 and C.get(1, C[0]) > O.get(1, C[0]) and C[0] < O[1] and O[0] > C[1]:
            interp, strength = build_interpretation("A powerful momentum shift where sellers overwhelmed buyers.", 0, "Bearish Engulfing")
            found_patterns.append({"name": "Bearish Engulfing", "interpretation": interp, "strength": strength})

    # Use last-year-to-date range when possible
    try:
        from datetime import date as _date, datetime as _datetime
        start_of_last_year = _date(_date.today().year - 1, 1, 1)
        end_dt = pd.Timestamp(_datetime.now())
        start_dt = pd.Timestamp(start_of_last_year)
        plot_df = df.loc[(df.index >= start_dt) & (df.index <= end_dt)] if isinstance(df.index, pd.DatetimeIndex) else df
    except Exception:
        plot_df = df
    plot_data_dict = plot_df.to_dict('split')
    if 'index' in plot_data_dict and hasattr(plot_data_dict['index'][0], 'strftime'):
        plot_data_dict['index'] = [ts.strftime('%Y-%m-%d') for ts in plot_data_dict['index']]

    return {"patterns": found_patterns, "context": market_context, "plot_data": plot_data_dict}

def generate_holistic_conclusion(
    synthesis_data,
    strikes,
    S_current,
    bias_override: Optional[str] = None,
    strategy_hint: Optional[Any] = None,
):
    """
    Synthesizes all analysis sections into a holistic conclusion, a directional bias,
    and a professional strategy recommendation.
    """
    sentiments = {'bullish': 0, 'bearish': 0, 'neutral': 0}
    components, bullish_drivers, bearish_drivers = [], [], []

    def process_component(name, data):
        if not data or not data.get('summary'): return
        components.append(f"<li><b>{name}:</b> {data['summary']}</li>")
        sentiment = data.get('sentiment')
        if sentiment in ['bullish', 'bearish', 'neutral']:
            sentiments[sentiment] += data.get('weight', 1)
            if sentiment == 'bullish': bullish_drivers.append(name.lower().replace('_', ' '))
            elif sentiment == 'bearish': bearish_drivers.append(name.lower().replace('_', ' '))

    analysis_map = {
        'trend': "Trend", 'candlestick': "Candlesticks", 'parity': "Put-Call Parity",
        'volume_oi': "Volume/OI", 'undervalued': "Valuation", 'iv_hv': "Volatility",
        'earnings': "Catalysts", 'movement': "Price Action"
    }
    for key, name in analysis_map.items():
        if key in synthesis_data:
            process_component(name, synthesis_data[key])

    bull_score, bear_score = sentiments['bullish'], sentiments['bearish']
    final_bias = "Neutral"
    if bull_score > bear_score + 1.5: final_bias = "Bullish"
    elif bear_score > bull_score + 1.5: final_bias = "Bearish"
    elif bull_score > bear_score: final_bias = "Slightly Bullish"
    elif bear_score > bull_score: final_bias = "Slightly Bearish"

    def _normalize_bias_label(label: Optional[str]) -> Optional[str]:
        if not label:
            return None
        norm = str(label).strip().lower()
        if "slight" in norm and "bull" in norm:
            return "Slightly Bullish"
        if "slight" in norm and "bear" in norm:
            return "Slightly Bearish"
        if "moderat" in norm and "bull" in norm:
            return "Slightly Bullish"
        if "moderat" in norm and "bear" in norm:
            return "Slightly Bearish"
        if "strong" in norm and "bull" in norm:
            return "Bullish"
        if "strong" in norm and "bear" in norm:
            return "Bearish"
        if "bull" in norm:
            return "Bullish"
        if "bear" in norm:
            return "Bearish"
        if "neutral" in norm:
            return "Neutral"
        return None

    bias_overridden = False
    normalized_override = _normalize_bias_label(bias_override)
    if normalized_override:
        final_bias = normalized_override
        bias_overridden = True
    
    conclusion_html = "<h5>Summary of Findings:</h5><ul>" + "".join(components) + "</ul>"
    
    # --- Holistic Conclusion Paragraph ---
    conclusion_html += "<h5>Holistic Conclusion:</h5>"
    contradiction = (bull_score > 0 and bear_score > 0)
    bias_paragraph = f"<p>The overall directional bias is <b>{final_bias}</b>. "
    if "Bullish" in final_bias:
        drivers = f"<b>{', '.join(bullish_drivers)}</b>"
        bias_paragraph += f"This is primarily supported by positive signals from the {drivers} analysis. "
        if contradiction:
            bias_paragraph += f"However, caution is warranted due to conflicting bearish indicators from <b>{', '.join(bearish_drivers)}</b>."
    elif "Bearish" in final_bias:
        drivers = f"<b>{', '.join(bearish_drivers)}</b>"
        bias_paragraph += f"This is driven by negative signals from the {drivers} analysis. "
        if contradiction:
            bias_paragraph += f"However, the presence of bullish signals from <b>{', '.join(bullish_drivers)}</b> suggests potential for a reversal."
    else:
        bias_paragraph += "The analysis reveals a mix of bullish and bearish signals, leading to significant uncertainty. " if contradiction else "There are no strong directional signals from the core indicators. "
    if bias_overridden:
        bias_paragraph += " This directional view has been aligned with the AI verdict guidance."
    conclusion_html += bias_paragraph + "</p>"

    # --- Professional Strategy Recommendation ---
    iv_sentiment = synthesis_data.get('iv_hv', {}).get('sentiment')
    strategy_rec = "<h5>Recommended Strategy:</h5>"

    # This will hold the structured data for the recommended strategy for API consumers.
    recommended_strategy = {"name": "None", "legs": [], "is_credit_spread": False}

    # Determine ATM and OTM strikes for constructing strategy legs
    atm_strike = strikes[np.argmin(np.abs(strikes - S_current))] if len(strikes) > 0 else S_current
    otm_calls = strikes[strikes > S_current]
    itm_calls = strikes[strikes < S_current]
    otm_puts = strikes[strikes < S_current]
    itm_puts = strikes[strikes > S_current]

    def _normalize_strategy_hint_label(label: Optional[str]) -> Optional[str]:
        if not label:
            return None
        norm = str(label).strip().lower()
        mapping = [
            ("iron condor", "Iron Condor"),
            ("condor", "Iron Condor"),
            ("short straddle", "Short Straddle"),
            ("long straddle", "Long Straddle"),
            ("straddle", "Long Straddle"),
            ("bull call spread", "Bull Call Spread"),
            ("call debit spread", "Bull Call Spread"),
            ("bear call spread", "Bear Call Spread"),
            ("call credit spread", "Bear Call Spread"),
            ("bear put spread", "Bear Put Spread"),
            ("put debit spread", "Bear Put Spread"),
            ("bull put spread", "Bull Put Spread"),
            ("put credit spread", "Bull Put Spread"),
            ("cash secured put", "Cash Secured Put"),
            ("cash-secured put", "Cash Secured Put"),
            ("short put", "Cash Secured Put"),
            ("long call", "Long Call"),
            ("long put", "Long Put"),
            ("short call", "Short Call"),
            ("covered call", "Short Call"),
            ("watch and wait", "Watch and Wait"),
        ]
        for key, canonical in mapping:
            if key in norm:
                return canonical
        return None

    def _build_strategy_from_name(name: str):
        if name == "Iron Condor":
            if len(otm_puts) >= 2 and len(otm_calls) >= 2:
                return {
                    "name": "Iron Condor",
                    "is_credit_spread": True,
                    "legs": [
                        {'action': 'SELL', 'strike': float(otm_puts[-1]), 'right': 'P'},
                        {'action': 'BUY', 'strike': float(otm_puts[-2]), 'right': 'P'},
                        {'action': 'SELL', 'strike': float(otm_calls[0]), 'right': 'C'},
                        {'action': 'BUY', 'strike': float(otm_calls[1]), 'right': 'C'}
                    ]
                }
        elif name == "Short Straddle":
            return {
                "name": "Short Straddle",
                "is_credit_spread": False,
                "legs": [
                    {'action': 'SELL', 'strike': float(atm_strike), 'right': 'C'},
                    {'action': 'SELL', 'strike': float(atm_strike), 'right': 'P'}
                ]
            }
        elif name == "Long Straddle":
            return {
                "name": "Long Straddle",
                "is_credit_spread": False,
                "legs": [
                    {'action': 'BUY', 'strike': float(atm_strike), 'right': 'C'},
                    {'action': 'BUY', 'strike': float(atm_strike), 'right': 'P'}
                ]
            }
        elif name == "Bull Put Spread":
            if len(otm_puts) >= 2:
                return {
                    "name": "Bull Put Spread",
                    "is_credit_spread": True,
                    "legs": [
                        {'action': 'SELL', 'strike': float(otm_puts[-1]), 'right': 'P'},
                        {'action': 'BUY', 'strike': float(otm_puts[-2]), 'right': 'P'}
                    ]
                }
        elif name == "Bull Call Spread":
            if len(itm_calls) >= 1 and len(otm_calls) >= 1:
                return {
                    "name": "Bull Call Spread",
                    "is_credit_spread": False,
                    "legs": [
                        {'action': 'BUY', 'strike': float(itm_calls[-1]), 'right': 'C'},
                        {'action': 'SELL', 'strike': float(otm_calls[0]), 'right': 'C'}
                    ]
                }
        elif name == "Cash Secured Put":
            strike_value = float(otm_puts[-1]) if len(otm_puts) >= 1 else float(atm_strike * 0.95)
            return {
                "name": "Cash Secured Put",
                "is_credit_spread": False,
                "legs": [
                    {'action': 'SELL', 'strike': strike_value, 'right': 'P'}
                ]
            }
        elif name == "Long Call":
            return {
                "name": "Long Call",
                "is_credit_spread": False,
                "legs": [
                    {'action': 'BUY', 'strike': float(atm_strike), 'right': 'C'}
                ]
            }
        elif name == "Long Put":
            return {
                "name": "Long Put",
                "is_credit_spread": False,
                "legs": [
                    {'action': 'BUY', 'strike': float(atm_strike), 'right': 'P'}
                ]
            }
        elif name == "Bear Call Spread":
            if len(otm_calls) >= 2:
                return {
                    "name": "Bear Call Spread",
                    "is_credit_spread": True,
                    "legs": [
                        {'action': 'SELL', 'strike': float(otm_calls[0]), 'right': 'C'},
                        {'action': 'BUY', 'strike': float(otm_calls[1]), 'right': 'C'}
                    ]
                }
        elif name == "Bear Put Spread":
            if len(itm_puts) >= 1 and len(otm_puts) >= 1:
                return {
                    "name": "Bear Put Spread",
                    "is_credit_spread": False,
                    "legs": [
                        {'action': 'BUY', 'strike': float(itm_puts[0]), 'right': 'P'},
                        {'action': 'SELL', 'strike': float(otm_puts[-1]), 'right': 'P'}
                    ]
                }
        elif name == "Short Call":
            strike_value = float(otm_calls[0]) if len(otm_calls) >= 1 else float(atm_strike * 1.05)
            return {
                "name": "Short Call",
                "is_credit_spread": False,
                "legs": [
                    {'action': 'SELL', 'strike': strike_value, 'right': 'C'}
                ]
            }
        elif name == "Watch and Wait":
            return {
                "name": "Watch and Wait",
                "is_credit_spread": False,
                "legs": [
                    {'action': 'WATCH', 'strike': float(atm_strike), 'right': 'SIGNAL'}
                ]
            }
        return None

    hint_type = None
    hint_description = ""
    hint_confidence = None
    hint_horizon = None
    if isinstance(strategy_hint, dict):
        hint_type = strategy_hint.get('type')
        hint_description = strategy_hint.get('description') or ''
        hint_confidence = strategy_hint.get('confidence')
        hint_horizon = strategy_hint.get('time_horizon')
    elif isinstance(strategy_hint, str):
        hint_type = strategy_hint

    normalized_hint_name = _normalize_strategy_hint_label(hint_type)
    hint_applied = False
    if normalized_hint_name:
        hinted_strategy = _build_strategy_from_name(normalized_hint_name)
        if hinted_strategy:
            recommended_strategy = hinted_strategy
            hint_applied = True
            desc_segments = []
            if hint_description:
                desc_segments.append(hint_description)
            if hint_confidence:
                desc_segments.append(f"Confidence: {hint_confidence}.")
            if hint_horizon:
                desc_segments.append(f"Time horizon: {hint_horizon}.")
            desc_text = " ".join(desc_segments) or "Align execution with the AI recommended approach."
            strategy_rec += f"<p><b>AI Suggested Strategy - {normalized_hint_name}.</b> {desc_text}</p>"
        else:
            # We understood the hint but cannot build it with available strikes
            strategy_rec += f"<p><b>AI Suggested Strategy - {hint_type}.</b> Unable to automatically construct matching legs with available strikes; defaulting to model-derived guidance.</p>"
    elif hint_type:
        strategy_rec += f"<p><b>AI Suggested Strategy - {hint_type}.</b> This configuration is not yet supported for one-click execution; falling back to model-derived guidance.</p>"

    if not hint_applied:
        if final_bias == "Neutral":
            if iv_sentiment == 'high_vol':
                strategy_rec += "<p><b>Sell Premium (High IV) - Iron Condor.</b> The analysis is neutral and implied volatility is high. An Iron Condor profits if the stock price remains within a defined range, benefiting from time decay and a potential decrease in IV. This is a defined-risk, high-probability trade.</p>"
                if len(otm_puts) >= 2 and len(otm_calls) >= 2:
                    recommended_strategy = {
                        "name": "Iron Condor",
                        "is_credit_spread": True,
                        "legs": [
                            {'action': 'SELL', 'strike': otm_puts[-1], 'right': 'P'},
                            {'action': 'BUY', 'strike': otm_puts[-2], 'right': 'P'},
                            {'action': 'SELL', 'strike': otm_calls[0], 'right': 'C'},
                            {'action': 'BUY', 'strike': otm_calls[1], 'right': 'C'}
                        ]
                    }
                else:
                    # Fallback when insufficient strikes for Iron Condor
                    recommended_strategy = {
                        "name": "Short Straddle",
                        "is_credit_spread": False,
                        "legs": [
                            {'action': 'SELL', 'strike': atm_strike, 'right': 'C'},
                            {'action': 'SELL', 'strike': atm_strike, 'right': 'P'}
                        ]
                    }
            elif iv_sentiment == 'low_vol':
                strategy_rec += "<p><b>Buy Premium (Low IV) - Long Straddle.</b> The analysis is neutral but a large move is possible, especially if a catalyst is near. A Long Straddle profits from a significant price move in either direction and benefits from the currently cheap option premiums.</p>"
                recommended_strategy = {
                    "name": "Long Straddle",
                    "is_credit_spread": False,
                    "legs": [
                        {'action': 'BUY', 'strike': atm_strike, 'right': 'C'},
                        {'action': 'BUY', 'strike': atm_strike, 'right': 'P'}
                    ]
                }
            else:
                strategy_rec += "<p><b>Wait for a clearer signal.</b> The directional bias is neutral and IV is not at an extreme. It may be prudent to wait for a better entry point or a clearer market sentiment before committing capital.</p>"
                # Provide a basic watch strategy so execution section appears
                recommended_strategy = {
                    "name": "Watch and Wait",
                    "is_credit_spread": False,
                    "legs": [
                        {'action': 'WATCH', 'strike': atm_strike, 'right': 'SIGNAL'}
                    ]
                }
        elif "Bullish" in final_bias:
            if iv_sentiment == 'high_vol':
                strategy_rec += "<p><b>Defined-Risk Bullish (High IV) - Bull Put Spread.</b> With a bullish bias and high IV, selling a credit spread is advantageous. A Bull Put Spread profits if the stock moves up, sideways, or even slightly down. It benefits from time decay and high premiums, while defining your maximum risk.</p>"
                if len(otm_puts) >= 2:
                    recommended_strategy = {
                        "name": "Bull Put Spread",
                        "is_credit_spread": True,
                        "legs": [
                            {'action': 'SELL', 'strike': otm_puts[-1], 'right': 'P'},
                            {'action': 'BUY', 'strike': otm_puts[-2], 'right': 'P'}
                        ]
                    }
                else:
                    # Fallback when insufficient strikes for spread
                    recommended_strategy = {
                        "name": "Cash Secured Put",
                        "is_credit_spread": False,
                        "legs": [
                            {'action': 'SELL', 'strike': atm_strike * 0.95, 'right': 'P'}
                        ]
                    }
            else:
                strategy_rec += "<p><b>Defined-Risk Bullish (Low/Mid IV) - Bull Call Spread.</b> With a bullish bias and cheaper premiums, a debit spread is attractive. A Bull Call Spread profits from a rise in the stock price with a lower cost and less time decay sensitivity than buying a call outright. Your risk and reward are both capped.</p>"
                if len(itm_calls) >= 1 and len(otm_calls) >= 1:
                    recommended_strategy = {
                        "name": "Bull Call Spread",
                        "is_credit_spread": False,
                        "legs": [
                            {'action': 'BUY', 'strike': itm_calls[-1], 'right': 'C'},
                            {'action': 'SELL', 'strike': otm_calls[0], 'right': 'C'}
                        ]
                    }
                else:
                    # Fallback when insufficient strikes for spread
                    recommended_strategy = {
                        "name": "Long Call",
                        "is_credit_spread": False,
                        "legs": [
                            {'action': 'BUY', 'strike': atm_strike, 'right': 'C'}
                        ]
                    }
        elif "Bearish" in final_bias:
            if iv_sentiment == 'high_vol':
                strategy_rec += "<p><b>Defined-Risk Bearish (High IV) - Bear Call Spread.</b> With a bearish bias and high IV, a credit spread is a strong choice. A Bear Call Spread profits if the stock moves down, sideways, or slightly up. It benefits from rich option premiums and time decay.</p>"
                if len(otm_calls) >= 2:
                    recommended_strategy = {
                        "name": "Bear Call Spread",
                        "is_credit_spread": True,
                        "legs": [
                            {'action': 'SELL', 'strike': otm_calls[0], 'right': 'C'},
                            {'action': 'BUY', 'strike': otm_calls[1], 'right': 'C'}
                        ]
                    }
                else:
                    # Fallback when insufficient strikes for spread
                    recommended_strategy = {
                        "name": "Short Call",
                        "is_credit_spread": False,
                        "legs": [
                            {'action': 'SELL', 'strike': atm_strike * 1.05, 'right': 'C'}
                        ]
                    }
            else:
                strategy_rec += "<p><b>Defined-Risk Bearish (Low/Mid IV) - Bear Put Spread.</b> With a bearish bias and low IV, a debit spread is a good way to express a directional view. A Bear Put Spread profits from a fall in the stock price while having a lower cost and defined risk compared to buying a put.</p>"
                if len(itm_puts) >= 1 and len(otm_puts) >= 1:
                    recommended_strategy = {
                        "name": "Bear Put Spread",
                        "is_credit_spread": False,
                        "legs": [
                            {'action': 'BUY', 'strike': itm_puts[0], 'right': 'P'},
                            {'action': 'SELL', 'strike': otm_puts[-1], 'right': 'P'}
                        ]
                    }
                else:
                    # Fallback when insufficient strikes for spread
                    recommended_strategy = {
                        "name": "Long Put",
                        "is_credit_spread": False,
                        "legs": [
                            {'action': 'BUY', 'strike': atm_strike, 'right': 'P'}
                        ]
                    }
    
    # Final safety check - ensure we always have a valid strategy for execution section
    if recommended_strategy["name"] == "None" or len(recommended_strategy["legs"]) == 0:
        # Provide a basic directional strategy as ultimate fallback
        if "Bullish" in final_bias:
            recommended_strategy = {
                "name": "Long Call (Basic)",
                "is_credit_spread": False,
                "legs": [
                    {'action': 'BUY', 'strike': atm_strike, 'right': 'C'}
                ]
            }
        elif "Bearish" in final_bias:
            recommended_strategy = {
                "name": "Long Put (Basic)",
                "is_credit_spread": False,
                "legs": [
                    {'action': 'BUY', 'strike': atm_strike, 'right': 'P'}
                ]
            }
        else:
            # Neutral fallback
            recommended_strategy = {
                "name": "Long Straddle (Basic)",
                "is_credit_spread": False,
                "legs": [
                    {'action': 'BUY', 'strike': atm_strike, 'right': 'C'},
                    {'action': 'BUY', 'strike': atm_strike, 'right': 'P'}
                ]
            }
    
    conclusion_html += strategy_rec
    return conclusion_html, final_bias, recommended_strategy

def _sanitize_for_json(item):
    """
    Recursively walk a data structure and convert non-JSON-compliant types
    (NaN, Infinity, numpy integers/floats) to standard Python types.
    """
    if isinstance(item, dict):
        return {k: _sanitize_for_json(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [_sanitize_for_json(elem) for elem in item]
    # This must come before float check
    elif isinstance(item, np.integer):
        return int(item)
    elif isinstance(item, np.floating):
        if np.isnan(item) or np.isinf(item):
            return None
        return float(item)
    elif isinstance(item, np.ndarray):
        return item.tolist()
    # Standard float check for NaN/inf
    elif isinstance(item, float) and (np.isnan(item) or np.isinf(item)):
        return None
    return item

async def run_full_analysis(ticker: str, expiration_date: date, r_current: float = 0.045, rate_source: str = 'etf', methodology: str = 'holistic-market-edge', gpt_model: str = 'gpt-5', override_price: float = None):
    """
    Performs all calculations for the option screener, fully implementing Key Feature 1.
    Now uses the improved run_analysis function with multi-source price validation.
    """
    from src.analytics.analysis import run_analysis
    
    # Use the improved analysis function with multi-source price validation
    analysis_result = run_analysis(
        ticker=ticker,
        expiration_date=expiration_date, 
        r_current=r_current,
        rate_source=rate_source,
        analysis_method=methodology,
        override_price=override_price,
        gpt_model=gpt_model
    )
    
    return analysis_result
