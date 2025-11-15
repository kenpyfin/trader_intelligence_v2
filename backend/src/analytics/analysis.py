import pandas as pd
import numpy as np
from datetime import date, timedelta, datetime
from src.my_libs_py3.my_data import PriceDataFetcher
from src.my_libs_py3.fmp import FMPClient
from src.analytics.treasury_curve import build_treasury_curve
from .methodologies.gpt_verdict import generate_gpt_verdict

# This file is a migration of the analysis logic from option_trade.py.
# All Streamlit-specific code (st.*) has been removed.

def _sanitize_for_json_serialization(obj):
    """
    Recursively sanitize objects to be JSON-serializable, handling pandas/numpy types.
    """
    if obj is None:
        return None
    elif isinstance(obj, (str, int, float, bool)):
        # Handle NaN and infinity for floats
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        return obj
    elif isinstance(obj, (date, datetime, pd.Timestamp)):
        # Convert dates and timestamps to ISO format strings
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        elif hasattr(obj, 'strftime'):
            return obj.strftime('%Y-%m-%d %H:%M:%S') if hasattr(obj, 'hour') else obj.strftime('%Y-%m-%d')
        else:
            return str(obj)
    elif isinstance(obj, np.generic):
        # Handle numpy scalars
        return obj.item()
    elif isinstance(obj, np.ndarray):
        # Handle numpy arrays
        return obj.tolist()
    elif hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):
        # Handle pandas DataFrames/Series
        return _sanitize_for_json_serialization(obj.to_dict())
    elif isinstance(obj, dict):
        # Recursively handle dictionaries
        return {str(k): _sanitize_for_json_serialization(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        # Recursively handle sequences
        return [_sanitize_for_json_serialization(item) for item in obj]
    else:
        # Fallback to string representation
        return str(obj)

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
    if days_to_expiration <= 0: return np.maximum(0, S - K if option_type == 'call' else K - S), {}, [], 0
    N, T, dt = days_to_expiration, days_to_expiration / 365.0, (days_to_expiration / 365.0) / days_to_expiration
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
            p = 0.5; drift = (r_step - div - 0.5 * sigma_step**2) * dt
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
    option_value_tree[:, N] = np.maximum(0, stock_price_tree[:, N] - K if option_type == 'call' else K - stock_price_tree[:, N])
    for i in range(N - 1, -1, -1):
        r_step, p_step = r_rates[i], p_steps[i]
        for j in range(i + 1):
            expected_value = (p_step * option_value_tree[j, i + 1] + (1 - p_step) * option_value_tree[j + 1, i + 1])
            continuation_value = np.exp(-r_step * dt) * expected_value
            if exercise_type == 'european': option_value_tree[j, i] = continuation_value
            else:
                intrinsic_value = np.maximum(0, stock_price_tree[j, i] - K if option_type == 'call' else K - stock_price_tree[j, i])
                option_value_tree[j, i] = np.maximum(continuation_value, intrinsic_value)
    # Greeks, alerts, and early exercise premium logic omitted for this phase for brevity.
    # The full logic from option_trade.py can be migrated here in subsequent steps.
    return option_value_tree[0,0], {}, [], 0

def _parse_finviz_iv_string(iv_input):
    if pd.isna(iv_input): return None
    if isinstance(iv_input, float): return iv_input
    if isinstance(iv_input, str):
        if iv_input.endswith('%'):
            try: return float(iv_input.strip('%')) / 100.0
            except ValueError: return None
        else:
            try: return float(iv_input)
            except ValueError: return None
    return None

def _get_market_price_from_finviz_df(df, strike, option_type_char):
    if df is None or df.empty: return None
    if 'Strike' not in df.columns or 'Type' not in df.columns: return None
    df['Strike'] = pd.to_numeric(df['Strike'], errors='coerce')
    type_to_match = 'call' if option_type_char.upper() == 'C' else 'put'
    option_row_df = df[(df['Strike'] == strike) & (df['Type'].str.lower() == type_to_match)]
    if option_row_df.empty: return None
    option_row = option_row_df.iloc[0]
    bid, ask = pd.to_numeric(option_row.get('Bid'), errors='coerce'), pd.to_numeric(option_row.get('Ask'), errors='coerce')
    if pd.notna(bid) and pd.notna(ask) and ask > 0 and bid > 0 and (ask - bid) / ask < 0.5: return (bid + ask) / 2.0
    last_trade = pd.to_numeric(option_row.get('Last Trade'), errors='coerce')
    if pd.notna(last_trade) and last_trade > 0: return last_trade
    last_close = pd.to_numeric(option_row.get('Last Close'), errors='coerce')
    if pd.notna(last_close) and last_close > 0: return last_close
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
    if not atm_option_row.empty: return _parse_finviz_iv_string(atm_option_row['IV'].iloc[0])
    return None

def fetch_iv_term_structure(ticker, price_fetcher, fmp_client, target_dtes=[7, 30, 90]):
    rt_quote = fmp_client.realtimequote(ticker)
    if rt_quote is None or rt_quote.empty or 'price' not in rt_quote.columns: return [], []
    current_stock_price = rt_quote.price.iloc[0]
    if current_stock_price is None: return [], []
    key_iv_points, log_messages = [], []
    for dte in target_dtes:
        expiration_date_dt = date.today() + timedelta(days=dte)
        for attempt in range(8):
            current_search_date_dt = expiration_date_dt + timedelta(days=attempt)
            current_search_date_str = current_search_date_dt.strftime('%Y-%m-%d')
            options_df = price_fetcher.get_option_data_finviz(ticker, 'o', current_search_date_str)
            if options_df is not None and not options_df.empty:
                atm_iv = _get_atm_iv_from_finviz_df(options_df, current_stock_price)
                if atm_iv is not None:
                    key_iv_points.append((dte, atm_iv))
                    break
    if key_iv_points and key_iv_points[0][0] != 0:
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
        else: return dt_obj.replace(year=today.year)
    except (ValueError, AttributeError): return None

def analyze_high_movement_expectation(S_current, option_chain_df, historical_prices_df, earnings_date=None, expiration_date=None):
    """Analyzes factors suggesting high movement expectation."""
    analysis = {}

    # 1. Calculate Expected Move from ATM straddle
    if option_chain_df is None or option_chain_df.empty:
        analysis['expected_move_note'] = "Option chain data not available to calculate expected move."
    else:
        strikes = option_chain_df['Strike'].unique()
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
                analysis['expected_move_note'] = f"Could not calculate expected move from ATM straddle (market prices unavailable for strike ${atm_strike:.2f})."
        else:
            analysis['expected_move_note'] = "No strikes found in option chain data."


    # 2. Look at the Chart (Price Action Analysis)
    if historical_prices_df is not None and not historical_prices_df.empty and 'Close' in historical_prices_df.columns:
        closing_prices = historical_prices_df['Close'].tolist()
        
        if len(closing_prices) >= 11:
            price_10d_ago = closing_prices[-11]
            price_change_10d_pct = ((S_current - price_10d_ago) / price_10d_ago) * 100
            analysis['price_change_10d_pct'] = price_change_10d_pct
        else:
            analysis['price_change_10d_pct'] = None
        
        if len(closing_prices) >= 51:
            hv_10d = calculate_historical_volatility(closing_prices, lookback_days=10)
            hv_50d = calculate_historical_volatility(closing_prices, lookback_days=50)
            analysis['hv_10d'] = hv_10d
            analysis['hv_50d'] = hv_50d
            if hv_10d < hv_50d * 0.8:
                is_coiling_before_earnings = False
                if earnings_date:
                    days_to_earnings = (earnings_date - date.today()).days
                    if 0 < days_to_earnings <= 21:
                        is_coiling_before_earnings = True
                        analysis['vol_compression_text'] = f"Volatility compression detected ahead of earnings in {days_to_earnings} days. This 'coiling' often precedes a significant price move."
                
                if not is_coiling_before_earnings:
                    analysis['vol_compression_text'] = "Possible volatility compression detected: 10-day HV is significantly lower than 50-day HV, suggesting a 'coiling' pattern."
            else:
                 analysis['vol_compression_text'] = "No significant volatility compression detected (10-day HV is not significantly lower than 50-day HV)."
        else:
            analysis['vol_compression_text'] = "Not enough data for volatility compression analysis (need 50+ trading days)."

    else:
        analysis['price_change_10d_pct'] = None
        analysis['vol_compression_text'] = "Historical price data not available for analysis."

    analysis['iv_analysis_text'] = "To assess 'IV crush' risk, manually check the IV Rank/Percentile on your brokerage platform. IV Rank is not available here. A high rank (e.g., > 80) means options are expensive and vulnerable to a sharp drop in IV after an event, which can cause losses even if the stock moves as expected."

    if earnings_date and expiration_date:
        if date.today() < earnings_date <= expiration_date:
            analysis['earnings_within_expiry'] = True
            days_to_earnings = (earnings_date - date.today()).days
            analysis['earnings_note'] = f"Upcoming earnings on {earnings_date.strftime('%Y-%m-%d')} ({days_to_earnings} days), which is before expiration. This is a major catalyst."
        else:
            analysis['earnings_within_expiry'] = False
            if earnings_date > date.today():
                analysis['earnings_note'] = f"Next earnings date is {earnings_date.strftime('%Y-%m-%d')}, which is after the option's expiration date."

    return analysis


def analyze_volume_and_oi_signals(df, S_current):
    if df is None or df.empty:
        return {"error": "Option chain data is not available."}

    analysis = {
        "pc_ratio": None, "uoa_calls": [], "uoa_puts": [],
        "oi_put_wall": None, "oi_call_wall": None, "notes": []
    }

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

    total_call_volume = calls['Volume'].sum()
    total_put_volume = puts['Volume'].sum()
    if total_call_volume > 0:
        analysis['pc_ratio'] = total_put_volume / total_call_volume
    
    otm_calls = calls[calls['Strike'] > S_current]
    otm_puts = puts[puts['Strike'] < S_current]
    
    uoa_candidates_c = otm_calls[(otm_calls['Volume'] > otm_calls['Open Int.']) & (otm_calls['Volume'] > 500)]
    if not uoa_candidates_c.empty:
        uoa_candidates_c['vol_oi_ratio'] = uoa_candidates_c['Volume'] / (uoa_candidates_c['Open Int.'] + 1)
        analysis['uoa_calls'] = uoa_candidates_c.sort_values('vol_oi_ratio', ascending=False).head(3).to_dict('records')

    uoa_candidates_p = otm_puts[(otm_puts['Volume'] > otm_puts['Open Int.']) & (otm_puts['Volume'] > 500)]
    if not uoa_candidates_p.empty:
        uoa_candidates_p['vol_oi_ratio'] = uoa_candidates_p['Volume'] / (uoa_candidates_p['Open Int.'] + 1)
        analysis['uoa_puts'] = uoa_candidates_p.sort_values('vol_oi_ratio', ascending=False).head(3).to_dict('records')

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
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    if df is None or not all(col in df.columns for col in required_cols):
        return {"error": f"DataFrame is missing one or more required columns: {required_cols}", "context": {}}

    if len(df) < 51:
        return {"error": "Not enough historical data for analysis (need at least 51 periods).", "context": {}}

    df = df.copy()
    # Ensure we have a datetime index for proper date handling on the frontend
    if 'TimeStamp' in df.columns:
        try:
            df['TimeStamp'] = pd.to_datetime(df['TimeStamp'], errors='coerce')
            df.sort_values('TimeStamp', inplace=True)
            df.set_index('TimeStamp', inplace=True)
        except Exception:
            # If any issue occurs, proceed without changing index
            pass
    for col in required_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.dropna(subset=required_cols, inplace=True)
    if len(df) < 51:
        return {"error": "Not enough valid data points after cleaning.", "context": {}}

    # Core indicators for MA context
    # Add more SMAs for richer context
    df['SMA10'] = df['Close'].rolling(window=10).mean()
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    df['SMA100'] = df['Close'].rolling(window=100).mean()
    df['SMA200'] = df['Close'].rolling(window=200).mean()
    # Shift AvgVol10 by 1 to compare today's volume vs prior average
    df['AvgVol10'] = df['Volume'].rolling(window=10).mean().shift(1)

    if len(df) < 4:
        return {"error": "Not enough data after calculating indicators.", "context": {}}

    last_row = df.iloc[-1]
    C0, SMA50_val, SMA200_val = last_row['Close'], last_row['SMA50'], last_row.get('SMA200')
    primary_trend = (
        "Uptrend" if pd.notna(SMA200_val) and C0 > SMA200_val
        else "Downtrend" if pd.notna(SMA200_val)
        else "Undetermined"
    )
    secondary_trend = "Uptrend" if C0 > SMA50_val else "Downtrend"

    market_context = {
        "primary_trend": primary_trend,
        "secondary_trend": secondary_trend
    }

    # Basic pattern recognition with volume-aware strength
    found_patterns = []
    max_lookback = min(4, len(df))
    get_iloc = lambda col, i: df[col].iloc[-1 - i]
    O = {i: get_iloc('Open', i) for i in range(max_lookback)}
    H = {i: get_iloc('High', i) for i in range(max_lookback)}
    L = {i: get_iloc('Low', i) for i in range(max_lookback)}
    C = {i: get_iloc('Close', i) for i in range(max_lookback)}
    V = {i: get_iloc('Volume', i) for i in range(max_lookback)}
    AV10 = {i: get_iloc('AvgVol10', i) for i in range(max_lookback)}

    def Body(x): return abs(O.get(x, 0) - C.get(x, 0))
    def UpperShadow(x): return H.get(x, 0) - max(O.get(x, 0), C.get(x, 0))
    def LowerShadow(x): return min(O.get(x, 0), C.get(x, 0)) - L.get(x, 0)

    is_downtrend = secondary_trend == "Downtrend" or (C.get(0, 0) < C.get(1, 0) < C.get(2, 0))
    is_uptrend = secondary_trend == "Uptrend" or (C.get(0, 0) > C.get(1, 0) > C.get(2, 0))

    def build_interpretation(base_interp, vol_idx, name):
        is_high_vol = V.get(vol_idx, 0) > (AV10.get(vol_idx, 0) or 0) * 1.2 if AV10.get(vol_idx, None) is not None else False
        vol_msg = "on high volume, strengthening the signal." if is_high_vol else "on average volume."
        strength = "Strong" if is_high_vol and "Engulfing" in name else ("Moderate" if is_high_vol else "Weak")
        return f"{base_interp} It appeared {vol_msg}", strength

    # Bullish reversal
    if is_downtrend:
        if LowerShadow(0) > (2 * Body(0)) and UpperShadow(0) < (0.1 * (H.get(0, 0) - L.get(0, 0))):
            interp, strength = build_interpretation("Sellers were rejected after a decline.", 0, "Hammer")
            found_patterns.append({"name": "Hammer (Bullish Reversal)", "interpretation": interp, "strength": strength})
        if Body(0) > 0 and C.get(1, C.get(0, 0)) < O.get(1, C.get(0, 0)) and C.get(0, 0) > O.get(1, C.get(0, 0)) and O.get(0, 0) < C.get(1, C.get(0, 0)):
            interp, strength = build_interpretation("A powerful momentum shift where buyers overwhelmed sellers.", 0, "Bullish Engulfing")
            found_patterns.append({"name": "Bullish Engulfing", "interpretation": interp, "strength": strength})

    # Bearish reversal
    if is_uptrend:
        if UpperShadow(0) > (2 * Body(0)) and LowerShadow(0) < (0.1 * (H.get(0, 0) - L.get(0, 0))):
            interp, strength = build_interpretation("Buyers were rejected after a rally.", 0, "Shooting Star")
            found_patterns.append({"name": "Shooting Star (Bearish Reversal)", "interpretation": interp, "strength": strength})
        if Body(0) > 0 and C.get(1, C.get(0, 0)) > O.get(1, C.get(0, 0)) and C.get(0, 0) < O.get(1, C.get(0, 0)) and O.get(0, 0) > C.get(1, C.get(0, 0)):
            interp, strength = build_interpretation("A powerful momentum shift where sellers overwhelmed buyers.", 0, "Bearish Engulfing")
            found_patterns.append({"name": "Bearish Engulfing", "interpretation": interp, "strength": strength})

    # Prepare plotly-friendly data in 'split' orientation
    # Show data from the beginning of last year until now
    try:
        start_of_last_year = date(date.today().year - 1, 1, 1)
        end_dt = pd.Timestamp(datetime.now())
        start_dt = pd.Timestamp(start_of_last_year)
        if isinstance(df.index, pd.DatetimeIndex):
            plot_df = df.loc[(df.index >= start_dt) & (df.index <= end_dt)]
        else:
            plot_df = df
    except Exception:
        plot_df = df
    plot_data = plot_df.to_dict('split')
    # Ensure index (dates) are stringified for the frontend
    if 'index' in plot_data and len(plot_data['index']) > 0 and hasattr(plot_data['index'][0], 'strftime'):
        plot_data['index'] = [ts.strftime('%Y-%m-%d') for ts in plot_data['index']]

    return {"patterns": found_patterns, "context": market_context, "plot_data": plot_data}


def generate_holistic_conclusion(synthesis_data):
    sentiments = {'bullish': 0, 'bearish': 0, 'neutral': 0}
    components, bullish_drivers, bearish_drivers = [], [], []

    def process_component(name, data):
        if not data: return
        components.append(f"<li><b>{name}:</b> {data['summary']}</li>")
        sentiment = data.get('sentiment')
        if sentiment in sentiments:
            sentiments[sentiment] += data.get('weight', 1)
            if sentiment == 'bullish': bullish_drivers.append(name.lower())
            elif sentiment == 'bearish': bearish_drivers.append(name.lower())

    analysis_map = { 'trend': "Trend", 'candlestick': "Candlesticks", 'parity': "Put-Call Parity", 'volume_oi': "Volume/OI", 'undervalued': "Valuation Model", 'earnings': "Upcoming Events", 'movement': "Price Action & Volatility" }
    for key, name in analysis_map.items():
        if key in synthesis_data:
            process_component(name, synthesis_data[key])

    bull_score, bear_score = sentiments['bullish'], sentiments['bearish']
    if bull_score > bear_score + 1: final_bias = "Bullish"
    elif bear_score > bull_score + 1: final_bias = "Bearish"
    elif bull_score > bear_score: final_bias = "Slightly Bullish"
    elif bear_score > bull_score: final_bias = "Slightly Bearish"
    else: final_bias = "Neutral"
    
    conclusion_html = "<h5>Summary of Findings:</h5><ul>" + "".join(components) + "</ul>"
    # Detailed text generation omitted for brevity but would follow logic from option_trade.py
    conclusion_html += f"<h5>Holistic Conclusion:</h5><p>The overall directional bias is <b>{final_bias}</b>.</p>"

    return conclusion_html, final_bias


def run_analysis(ticker: str, expiration_date: date, r_current: float = 0.05, rate_source: str = 'etf', analysis_method: str = 'holistic-market-edge', override_price: float = None, gpt_model: str = 'gpt-5'):
    fmp = FMPClient()
    price_fetcher = PriceDataFetcher()

    # Multi-source price fetching with validation
    S_current = None
    price_sources = []
    price_validation_note = "Price source validation"
    
    # Check for manual price override first (for testing/debugging)
    if override_price and override_price > 0:
        S_current = override_price
        price_sources.append(("Manual Override", override_price))
        price_validation_note = f"Using manual price override: ${override_price:.2f}"
        print(f"Using manual price override for {ticker}: ${override_price:.2f}")
    else:
        # Try FMP real-time quote first
        try:
            rt_quote = fmp.realtimequote(ticker)
            if rt_quote is not None and not rt_quote.empty and 'price' in rt_quote.columns:
                fmp_price = rt_quote.price.iloc[0]
                if fmp_price and fmp_price > 0:
                    price_sources.append(("FMP", fmp_price))
                    S_current = fmp_price
        except Exception as e:
            print(f"FMP price fetch failed for {ticker}: {e}")
        
        # Get finviz stock details (includes current price)
        stock_details = price_fetcher.get_stock_details_finviz(ticker)
        finviz_price = stock_details.get('price')
        if finviz_price:
            try:
                finviz_price_float = float(finviz_price)
                if finviz_price_float > 0:
                    price_sources.append(("Finviz", finviz_price_float))
                    # Use finviz price if no FMP price or if FMP seems stale
                    if S_current is None:
                        S_current = finviz_price_float
            except (ValueError, TypeError):
                pass
        
        # Try finviz real-time data as backup
        if S_current is None:
            try:
                finviz_rt = price_fetcher.get_price_data([ticker], method="realtimedata", back_day=1, last_record=True)
                if finviz_rt is not None and not finviz_rt.empty and 'Close' in finviz_rt.columns:
                    finviz_rt_price = finviz_rt['Close'].iloc[-1]
                    if finviz_rt_price and finviz_rt_price > 0:
                        price_sources.append(("Finviz-RT", finviz_rt_price))
                        S_current = finviz_rt_price
            except Exception as e:
                print(f"Finviz real-time fetch failed for {ticker}: {e}")
    
    # Get stock_details if not already fetched  
    if 'stock_details' not in locals():
        stock_details = price_fetcher.get_stock_details_finviz(ticker)
    
    if S_current is None or S_current <= 0:
        return {"status": "error", "message": f"Could not fetch valid current price for {ticker} from any source. Sources tried: FMP, Finviz"}
    
    # Validate price consistency across sources
    if len(price_sources) > 1:
        prices = [p[1] for p in price_sources]
        max_price, min_price = max(prices), min(prices)
        price_spread_pct = (max_price - min_price) / min_price * 100 if min_price > 0 else 0
        
        if price_spread_pct > 5:  # More than 5% spread suggests stale data
            # Use the most recent/reliable source (prefer Finviz over FMP for current prices)
            for source_name, source_price in reversed(price_sources):  # reversed to prefer later sources
                if source_name.startswith("Finviz") and source_price > 0:
                    S_current = source_price
                    break
            price_validation_note = f"Price discrepancy detected: {[f'{s}=${p:.2f}' for s,p in price_sources]}. Using {S_current:.2f}"
        else:
            price_validation_note = f"Price validated across sources: {[f'{s}=${p:.2f}' for s,p in price_sources]}"
    else:
        source_name = price_sources[0][0] if price_sources else "Unknown"
        price_validation_note = f"Single source price: {source_name}=${S_current:.2f}"

    option_chain_df = price_fetcher.get_option_data_finviz(ticker, 'o', expiration_date.strftime('%Y-%m-%d'))
    if option_chain_df is None or option_chain_df.empty:
        return {"status": "error", "message": f"Could not fetch option chain for {ticker} on {expiration_date}."}
    
    option_chain_df['Strike'] = pd.to_numeric(option_chain_df['Strike'], errors='coerce')
    option_chain_df.dropna(subset=['Strike'], inplace=True)
    option_chain_df.sort_values('Strike', inplace=True)
    strikes = option_chain_df['Strike'].unique()
    
    # Fetch enough historical data: from the start of last year to today
    start_dt = datetime(date.today().year - 1, 1, 1)
    end_dt = datetime.now()
    historical_prices_df = price_fetcher.get_price_data([ticker], method="td_data", start_date=start_dt, end_date=end_dt)
    hv_current = calculate_historical_volatility(historical_prices_df['Close'].tolist()) if historical_prices_df is not None and not historical_prices_df.empty else None

    key_vols_iv, _ = fetch_iv_term_structure(ticker, price_fetcher, fmp)
    if not key_vols_iv and hv_current: key_vols_iv = [(0, hv_current)]

    div_current = stock_details.get('dividend_yield', 0.0)
    earnings_date = parse_earnings_date(stock_details.get('earnings_date'))

    movement_analysis_results = analyze_high_movement_expectation(S_current, option_chain_df, historical_prices_df, earnings_date=earnings_date, expiration_date=expiration_date)
    volume_oi_analysis = analyze_volume_and_oi_signals(option_chain_df, S_current)
    candlestick_analysis = analyze_candlestick_patterns(historical_prices_df)

    days_to_exp = (expiration_date - date.today()).days
    if days_to_exp < 0: return {"status": "error", "message": "Expiration date is in the past."}
    
    vol_term_structure = generate_forward_vol_structure(days_to_exp, key_vols_iv)
    if rate_source == 'treasury':
        r_input = build_treasury_curve(fmp)['rate_fn']
    else: r_input = r_current

    results, parity_data = [], []
    selected_strikes = strikes[(strikes > S_current * 0.8) & (strikes < S_current * 1.2)]
    for K in selected_strikes:
        call_market_price = _get_market_price_from_finviz_df(option_chain_df, K, 'C')
        put_market_price = _get_market_price_from_finviz_df(option_chain_df, K, 'P')
        if call_market_price is not None and put_market_price is not None:
            T = days_to_exp / 365.0
            parity_diff = (call_market_price - put_market_price) - (S_current - K * np.exp(-r_current * T))
            parity_data.append({"Strike": K, "Parity Difference": parity_diff})

        for option_type, market_price in [('call', call_market_price), ('put', put_market_price)]:
            if market_price is None: continue
            model_price, _, _, _ = universal_binomial_pricer(S=S_current, K=K, expiration_date=expiration_date, r_input=r_input, sigma_input=vol_term_structure, option_type=option_type, div=div_current)
            if model_price > market_price:
                diff = model_price - market_price
                diff_pct = (diff / market_price) * 100 if market_price > 0 else float('inf')
                results.append({
                    "Strike": K, "Type": option_type.capitalize(), "Market Price": market_price,
                    "Model Price": model_price, "Undervalued By ($)": diff, "Undervalued By (%)": diff_pct
                })

    synthesis_data = {}
    iv_available = bool(key_vols_iv)
    spot_iv = key_vols_iv[0][1] if iv_available and key_vols_iv[0][0] == 0 else (key_vols_iv[0][1] if iv_available else None)
    iv_high, iv_low = False, False
    if iv_available and spot_iv and hv_current:
        if spot_iv > hv_current * 1.2: iv_high = True
        elif spot_iv < hv_current * 0.8: iv_low = True
    
    if candlestick_analysis and "context" in candlestick_analysis and "error" not in candlestick_analysis:
        context = candlestick_analysis["context"]
        primary_trend = context.get('primary_trend', 'Undetermined')
        secondary_trend = context.get('secondary_trend', 'Undetermined')
        trend_sentiment = 'neutral'
        if primary_trend == "Uptrend":
            if secondary_trend == "Uptrend": trend_sentiment = 'bullish'
            else: trend_sentiment = 'neutral'
        elif primary_trend == "Downtrend":
            if secondary_trend == "Downtrend": trend_sentiment = 'bearish'
            else: trend_sentiment = 'neutral'
        synthesis_data['trend'] = {'sentiment': trend_sentiment, 'weight': 1.5, 'summary': f"The primary trend is **{primary_trend}** and the secondary trend is **{secondary_trend}**."}
        patterns = candlestick_analysis.get("patterns", [])
        if patterns:
            bullish_patterns = [p for p in patterns if "Bullish" in p['name']]
            bearish_patterns = [p for p in patterns if "Bearish" in p['name']]
            candlestick_sentiment = 'neutral'
            if bullish_patterns and not bearish_patterns: candlestick_sentiment = 'bullish'
            elif bearish_patterns and not bullish_patterns: candlestick_sentiment = 'bearish'
            strongest_pattern = sorted(patterns, key=lambda p: {"Strong": 0, "Moderate": 1, "Weak": 2, "Neutral": 3}.get(p.get('strength', 'Neutral'), 99))[0]
            synthesis_data['candlestick'] = {'sentiment': candlestick_sentiment, 'summary': f"A **'{strongest_pattern['name']}'** pattern was identified with **{strongest_pattern['strength']}** strength."}
        else:
            synthesis_data['candlestick'] = { 'sentiment': 'neutral', 'summary': "No significant candlestick patterns were found." }
    if parity_data:
        parity_df = pd.DataFrame(parity_data)
        parity_df['Parity Diff (%)'] = (parity_df['Parity Difference'] / S_current) * 100
        avg_parity_diff_pct = parity_df['Parity Diff (%)'].mean()
        parity_sentiment, parity_summary = 'neutral', "Put and call prices appear fairly valued against each other."
        if avg_parity_diff_pct > 0.15:
            parity_sentiment, parity_summary = 'bullish', f"Calls are relatively expensive to puts (avg dev: {avg_parity_diff_pct:+.2f}%), implying **bullish** market sentiment."
        elif avg_parity_diff_pct < -0.15:
            parity_sentiment, parity_summary = 'bearish', f"Puts are relatively expensive to calls (avg dev: {avg_parity_diff_pct:+.2f}%), implying **bearish** market sentiment."
        synthesis_data['parity'] = {'sentiment': parity_sentiment, 'summary': parity_summary, 'weight': 0.5}
    if volume_oi_analysis and not volume_oi_analysis.get("error"):
        pc_ratio, uoa_calls, uoa_puts = volume_oi_analysis.get('pc_ratio'), volume_oi_analysis.get('uoa_calls', []), volume_oi_analysis.get('uoa_puts', [])
        bull_signals, bear_signals, summary_parts = 0, 0, []
        if pc_ratio is not None:
            if pc_ratio < 0.7: bull_signals += 1; summary_parts.append(f"a low P/C ratio of {pc_ratio:.2f} (bullish)")
            elif pc_ratio > 1.0: bear_signals += 1; summary_parts.append(f"a high P/C ratio of {pc_ratio:.2f} (bearish)")
            else: summary_parts.append(f"a neutral P/C ratio of {pc_ratio:.2f}")
        if uoa_calls: bull_signals += 1.5; summary_parts.append("unusual buying in OTM calls")
        if uoa_puts: bear_signals += 1.5; summary_parts.append("unusual buying in OTM puts")
        put_wall, call_wall = volume_oi_analysis.get('oi_put_wall'), volume_oi_analysis.get('oi_call_wall')
        if put_wall: summary_parts.append(f"a significant Put Wall at K ${put_wall['Strike']:.2f} (potential support)")
        if call_wall: summary_parts.append(f"a significant Call Wall at K ${call_wall['Strike']:.2f} (potential resistance)")
        vol_sentiment = 'neutral'
        if bull_signals > bear_signals: vol_sentiment = 'bullish'
        elif bear_signals > bull_signals: vol_sentiment = 'bearish'
        vol_summary = "Volume and OI signals are neutral." if not summary_parts else "Key signals include: " + ", ".join(summary_parts) + "."
        synthesis_data['volume_oi'] = {'sentiment': vol_sentiment, 'summary': vol_summary}
    iv_summary = "IV is in line with HV."
    if iv_high: iv_summary = "IV is **high** relative to HV, suggesting option premiums are expensive. This favors premium-selling (credit) strategies."
    elif iv_low: iv_summary = "IV is **low** relative to HV, suggesting option premiums are cheap. This favors premium-buying (debit) strategies."
    synthesis_data['iv_hv'] = {'sentiment': 'high_vol' if iv_high else ('low_vol' if iv_low else 'neutral_vol'), 'summary': iv_summary}
    if movement_analysis_results:
        movement_summary_parts = []
        if 'expected_move_pct' in movement_analysis_results: movement_summary_parts.append(f"The market implies a **{movement_analysis_results['expected_move_pct']:.2f}%** move by expiration.")
        vol_comp_text = movement_analysis_results.get('vol_compression_text')
        if vol_comp_text and "compression detected" in vol_comp_text: movement_summary_parts.append(vol_comp_text)
        if movement_summary_parts: synthesis_data['movement'] = {'sentiment': 'event', 'summary': ' '.join(movement_summary_parts)}
    if movement_analysis_results.get('earnings_note'): synthesis_data['earnings'] = {'sentiment': 'earnings_event', 'summary': movement_analysis_results['earnings_note']}
    
    results_df = pd.DataFrame(results).sort_values("Undervalued By (%)", ascending=False) if results else None
    if results_df is not None and not results_df.empty:
        top_result = results_df.iloc[0]
        undervalued_sentiment = 'bullish' if top_result['Type'] == 'Call' else 'bearish'
        undervalued_summary = f"The quantitative model's top pick is an undervalued **{top_result['Type']}** at K ${top_result['Strike']:.2f}, suggesting a **{undervalued_sentiment}** bias."
        synthesis_data['undervalued'] = {'sentiment': undervalued_sentiment, 'summary': undervalued_summary}
    else:
        synthesis_data['undervalued'] = {'sentiment': 'neutral', 'summary': 'The model found no clearly undervalued options.'}

    # This is the base package of sub-analyses
    analysis_result_package = {
        "status": "success", "ticker": ticker, "S_current": S_current, "expiration_date": expiration_date.isoformat(), "dte": days_to_exp,
        "analysis_method": analysis_method,
        "gpt_model": gpt_model if 'gpt' in analysis_method else None,
        "synthesis_data": synthesis_data,
        "iv_high": iv_high,
        "iv_low": iv_low, 
        "candlestick_analysis": _sanitize_for_json_serialization(candlestick_analysis), 
        "volume_oi_analysis": _sanitize_for_json_serialization(volume_oi_analysis),
        "movement_analysis_results": _sanitize_for_json_serialization(movement_analysis_results), 
        "results_df": results_df,
        
        # Enhanced market context for GPT verdict
        "market_data": _sanitize_for_json_serialization({
            "current_price": S_current,
            "price_sources_checked": price_sources,
            "data_timestamp": date.today().isoformat(),
            "ticker": ticker,
            "price_validation": price_validation_note,
            "historical_volatility": hv_current,
            "implied_volatility": spot_iv,
            "iv_hv_ratio": (spot_iv / hv_current) if (spot_iv and hv_current and hv_current > 0) else None,
            "dividend_yield": div_current,
            "risk_free_rate": r_current,
            "earnings_date": earnings_date.isoformat() if earnings_date else None,
            "days_to_earnings": (earnings_date - date.today()).days if earnings_date else None,
            "price_context": f"CRITICAL: The current real-time price for {ticker} is ${S_current:.2f} as of {date.today().isoformat()}. This price was validated across multiple sources. ALWAYS use this price ${S_current:.2f} for all analysis, strike selection, and recommendations. Do not reference any other price levels. {price_validation_note}"
        }),
        
        # Put-call parity analysis for options positioning insights
        "parity_analysis": _sanitize_for_json_serialization({
            "parity_data": parity_data,
            "arbitrage_opportunities": len([p for p in parity_data if abs(p.get("Parity Difference", 0)) > 0.5]) if parity_data else 0
        }),
        
        # Enhanced stock fundamentals from finviz
        "stock_fundamentals": _sanitize_for_json_serialization({
            "details": stock_details,
            "key_metrics": {
                "pe_ratio": stock_details.get('pe_ratio'),
                "eps_growth": stock_details.get('eps_growth_this_year'),
                "revenue_growth": stock_details.get('sales_growth_quarterly'),
                "debt_to_equity": stock_details.get('debt_equity'),
                "roa": stock_details.get('roa'),
                "roe": stock_details.get('roe'),
                "profit_margin": stock_details.get('profit_margin'),
                "beta": stock_details.get('beta'),
                "average_volume": stock_details.get('average_volume'),
                "relative_volume": stock_details.get('relative_volume'),
                "market_cap": stock_details.get('market_cap')
            }
        }),
        
        # Volatility term structure for IV analysis
        "volatility_structure": _sanitize_for_json_serialization({
            "iv_term_points": key_vols_iv,
            "forward_vol_structure": vol_term_structure.tolist() if isinstance(vol_term_structure, np.ndarray) else vol_term_structure,
            "vol_skew_analysis": {
                "iv_rank_proxy": "high" if iv_high else ("low" if iv_low else "normal"),
                "hv_comparison": {
                    "iv_above_hv": spot_iv > hv_current if (spot_iv and hv_current) else None,
                    "iv_hv_spread": (spot_iv - hv_current) if (spot_iv and hv_current) else None
                }
            }
        }),
        
        # Options flow and positioning insights
        "options_positioning": _sanitize_for_json_serialization({
            "total_undervalued_options": len(results) if results else 0,
            "top_opportunity": results_df.iloc[0].to_dict() if (results_df is not None and not results_df.empty) else None,
            "strike_distribution": {
                "analyzed_strikes": selected_strikes.tolist() if hasattr(selected_strikes, 'tolist') else list(selected_strikes),
                "atm_strike": float(strikes[np.argmin(np.abs(strikes - S_current))]) if len(strikes) > 0 else None
            }
        })
    }

    # Import the generate_holistic_conclusion function  
    from ..services.analysis_service import generate_holistic_conclusion
    
    if (('gpt' in analysis_method) and ('verdict' in analysis_method)) or ('gpt-verdict' in analysis_method):
        print(f"DEBUG: Running GPT Verdict analysis for {ticker} (method: {analysis_method})")
        use_web = 'web' in analysis_method
        # Pass the sub-analyses to the AI
        gpt_verdict = generate_gpt_verdict(ticker, analysis_result_package, model=gpt_model or 'gpt-5', use_web_search=use_web)
        print(f"DEBUG: GPT Verdict response received: {gpt_verdict}")

        # Populate the package with AI results
        analysis_result_package['final_bias'] = gpt_verdict.get('final_bias', 'Neutral')
        analysis_result_package['final_conclusion_html'] = gpt_verdict.get('summary_html', '<p>Failed to retrieve AI summary.</p>')
        analysis_result_package['gpt_verdict'] = gpt_verdict
        
        # Generate recommended strategy based on the GPT bias and guidance hints
        primary_hint = (gpt_verdict.get('execution_recommendations') or {}).get('primary_strategy')
        _, _, primary_strategy, recommended_strategies = generate_holistic_conclusion(
            synthesis_data,
            strikes,
            S_current,
            bias_override=gpt_verdict.get('final_bias'),
            strategy_hint=primary_hint,
        )
        # Store both the primary strategy and all recommended strategies
        analysis_result_package['recommended_strategy'] = _sanitize_for_json_serialization(primary_strategy)
        analysis_result_package['recommended_strategies'] = _sanitize_for_json_serialization(recommended_strategies)
        print(f"DEBUG: Generated {len(recommended_strategies)} recommended strategies for GPT analysis")
    else:
        print(f"DEBUG: Running Holistic Market Edge analysis for {ticker}")
        # Generate the rule-based conclusion - handle 4 return values
        final_conclusion_html, final_bias, primary_strategy, recommended_strategies = generate_holistic_conclusion(synthesis_data, strikes, S_current)
        analysis_result_package['final_conclusion_html'] = final_conclusion_html
        analysis_result_package['final_bias'] = final_bias
        # Store both the primary strategy and all recommended strategies
        analysis_result_package['recommended_strategy'] = _sanitize_for_json_serialization(primary_strategy)
        analysis_result_package['recommended_strategies'] = _sanitize_for_json_serialization(recommended_strategies)
        analysis_result_package['gpt_verdict'] = None # Ensure it's not present for rule-based analysis
        print(f"DEBUG: Generated {len(recommended_strategies)} recommended strategies for Holistic analysis")

    # Serialize DataFrame for API response after all internal processing is done
    results_df_value = analysis_result_package.get('results_df')
    if results_df_value is not None and hasattr(results_df_value, 'to_dict'):
        # It's still a DataFrame, convert it
        analysis_result_package['results_df'] = results_df_value.to_dict('records')
    elif results_df_value is not None:
        # It's already been converted or is another type, sanitize it
        analysis_result_package['results_df'] = _sanitize_for_json_serialization(results_df_value)
    else:
        # It's None, set to empty list
        analysis_result_package['results_df'] = []
    
    print(f"DEBUG: Final analysis package for {ticker}: bias={analysis_result_package.get('final_bias')}")
    
    # Final sanitization pass to ensure all data is JSON serializable
    analysis_result_package = _sanitize_for_json_serialization(analysis_result_package)
    
    return analysis_result_package
