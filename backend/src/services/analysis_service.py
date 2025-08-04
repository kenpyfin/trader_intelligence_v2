import asyncio
import pandas as pd
import numpy as np
from datetime import date, timedelta
import json
import re

# IB-insync asyncio patching is not required in a FastAPI/uvicorn environment
# and is incompatible with the 'uvloop' used by uvicorn.


from src.my_libs_py3.my_data import PriceDataFetcher
from src.my_libs_py3.fmp import FMPClient
import plotly.graph_objects as go


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

def _get_market_price_from_finviz_df(df, strike, option_type_char, current_stock_price_for_atm_fallback=None):
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
    analysis = {}
    if option_chain_df is None or option_chain_df.empty:
        analysis['expected_move_note'] = "Option chain data not available."
    else:
        strikes = option_chain_df['Strike'].unique()
        if len(strikes) > 0:
            atm_strike = strikes[np.argmin(np.abs(strikes - S_current))]
            atm_call_price = _get_market_price_from_finviz_df(option_chain_df, atm_strike, 'C')
            atm_put_price = _get_market_price_from_finviz_df(option_chain_df, atm_strike, 'P')
            if atm_call_price is not None and atm_put_price is not None:
                atm_straddle_price = atm_call_price + atm_put_price
                analysis['expected_move_pct'] = (atm_straddle_price / S_current) * 100 if S_current > 0 else 0
    # ... more analysis logic would go here ...
    return analysis

def analyze_volume_and_oi_signals(df, S_current):
    if df is None or df.empty: return {"error": "Option chain data is not available."}
    analysis = {"pc_ratio": None, "uoa_calls": [], "uoa_puts": [], "notes": []}
    required_cols = ['Volume', 'Open Int.', 'Type', 'Strike']
    if not all(col in df.columns for col in required_cols): return analysis
    df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce').fillna(0)
    df['Open Int.'] = pd.to_numeric(df['Open Int.'], errors='coerce').fillna(0)
    df['Strike'] = pd.to_numeric(df['Strike'], errors='coerce')
    df.dropna(subset=['Strike', 'Type'], inplace=True)
    calls = df[df['Type'].str.lower() == 'call']
    puts = df[df['Type'].str.lower() == 'put']
    if calls.empty and puts.empty: return analysis
    total_call_volume = calls['Volume'].sum()
    if total_call_volume > 0: analysis['pc_ratio'] = puts['Volume'].sum() / total_call_volume
    # ... more analysis logic would go here ...
    return analysis

def analyze_candlestick_patterns(df):
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    if df is None or not all(col in df.columns for col in required_cols) or len(df) < 51:
        return {"error": "Not enough data for candlestick analysis."}
    # ... candlestick analysis logic would go here ...
    
    # Convert the DataFrame to a JSON-serializable format for the API response.
    # The 'split' orientation is clean and easy for a frontend to parse.
    plot_data_dict = df.tail(250).to_dict('split')

    # Timestamps in the index are not serializable, so convert them to strings.
    if 'index' in plot_data_dict:
        try:
            plot_data_dict['index'] = [ts.strftime('%Y-%m-%d') for ts in plot_data_dict['index']]
        except (AttributeError, TypeError):
             # Fallback for non-datetime indexes
            plot_data_dict['index'] = [str(i) for i in plot_data_dict['index']]

    return {"patterns": [], "context": {}, "plot_data": plot_data_dict}

def generate_holistic_conclusion(synthesis_data):
    sentiments = {'bullish': 0, 'bearish': 0, 'neutral': 0}
    # ... conclusion generation logic would go here ...
    return "Conclusion text.", "Neutral"

def _sanitize_for_json(item):
    """
    Recursively walk a data structure and convert non-JSON-compliant floats
    (NaN, Infinity, -Infinity) to None.
    """
    if isinstance(item, dict):
        return {k: _sanitize_for_json(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [_sanitize_for_json(elem) for elem in item]
    elif isinstance(item, (float, np.floating)) and (np.isnan(item) or np.isinf(item)):
        return None  # Convert to null, which is valid in JSON
    return item

def run_full_analysis(ticker: str, expiration_date: date, r_current: float = 0.045):
    """
    Performs all calculations for the option screener.
    This is a migration of run_option_screener from option_trade.py, adapted for backend use.
    """
    if not ticker: return {"status": "error", "message": "Please provide a ticker."}

    fmp = FMPClient()
    price_fetcher = PriceDataFetcher()

    rt_quote = fmp.realtimequote(ticker)
    if rt_quote is None or rt_quote.empty or 'price' not in rt_quote.columns:
        return {"status": "error", "message": f"Could not fetch current price for {ticker}."}
    S_current = rt_quote.price.iloc[0]
    if S_current is None: return {"status": "error", "message": f"Current price for {ticker} is None."}

    expiration_date_str = expiration_date.strftime('%Y-%m-%d')
    option_chain_df = price_fetcher.get_option_data_finviz(ticker, 'o', expiration_date_str)
    if option_chain_df is None or option_chain_df.empty:
        return {"status": "error", "message": f"Could not fetch option chain for {ticker} on {expiration_date_str}."}
    option_chain_df['Strike'] = pd.to_numeric(option_chain_df['Strike'], errors='coerce')
    option_chain_df.dropna(subset=['Strike'], inplace=True)
    option_chain_df.sort_values('Strike', inplace=True)
    if option_chain_df.empty: return {"status": "error", "message": f"No options found for {ticker} on {expiration_date_str}."}

    strikes = option_chain_df['Strike'].unique()
    otm_strikes_for_call, itm_strikes_for_call = strikes[strikes > S_current][:6], strikes[strikes < S_current][-6:]
    selected_strikes = np.concatenate([itm_strikes_for_call, otm_strikes_for_call])
    if len(selected_strikes) == 0: return {"status": "error", "message": "Could not find ITM/OTM strikes."}

    historical_prices_df = price_fetcher.get_price_data([ticker], method="td_data", back_day=350)
    hv_current = None
    if historical_prices_df is not None and not historical_prices_df.empty:
        closing_prices = historical_prices_df['Close'].tolist()
        if len(closing_prices) >= 2: hv_current = calculate_historical_volatility(closing_prices, lookback_days=20)
    
    key_vols_iv, iv_logs = fetch_iv_term_structure(ticker, price_fetcher, fmp)
    iv_available = bool(key_vols_iv)
    if not iv_available and hv_current: key_vols_iv = [(0, hv_current)]
    
    stock_details = price_fetcher.get_stock_details_finviz(ticker)
    div_current = stock_details.get('dividend_yield', 0.0)
    earnings_date = parse_earnings_date(stock_details.get('earnings_date'))

    movement_analysis_results = analyze_high_movement_expectation(S_current, option_chain_df, historical_prices_df, earnings_date=earnings_date, expiration_date=expiration_date)
    volume_oi_analysis = analyze_volume_and_oi_signals(option_chain_df, S_current)
    candlestick_analysis = analyze_candlestick_patterns(historical_prices_df)

    days_to_exp = (expiration_date - date.today()).days
    if days_to_exp < 0: return {"status": "error", "message": "Expiration date is in the past."}
    
    vol_term_structure = generate_forward_vol_structure(days_to_exp, key_vols_iv)
    results = []
    for K in selected_strikes:
        for option_type in ['call', 'put']:
            market_price = _get_market_price_from_finviz_df(option_chain_df, K, option_type[0].upper())
            if market_price is None: continue
            model_price, _, _, _ = universal_binomial_pricer(
                S=S_current, K=K, expiration_date=expiration_date, r_input=r_current,
                sigma_input=vol_term_structure, option_type=option_type, div=div_current, historical_vol=hv_current
            )
            if model_price > market_price:
                diff = model_price - market_price
                diff_pct = (diff / market_price) * 100 if market_price > 0 else float('inf')
                results.append({"Strike": K, "Type": option_type.capitalize(), "Market Price": market_price, "Model Price": model_price, "Undervalued By ($)": diff, "Undervalued By (%)": diff_pct})
    
    synthesis_data = {} # Synthesis logic would be here...
    final_conclusion_html, final_bias = generate_holistic_conclusion(synthesis_data)

    results_df = pd.DataFrame(results).sort_values("Undervalued By (%)", ascending=False) if results else pd.DataFrame()

    response_data = {
        "status": "success", "ticker": ticker, "S_current": S_current, "expiration_date": expiration_date.isoformat(),
        "iv_logs": iv_logs, "iv_available": iv_available, "synthesis_data": synthesis_data,
        "final_conclusion_html": final_conclusion_html, "final_bias": final_bias, "iv_high": False, "iv_low": False, # Simplified
        "strikes": strikes.tolist(), "candlestick_analysis": candlestick_analysis, "volume_oi_analysis": volume_oi_analysis,
        "movement_analysis_results": movement_analysis_results, "results_df": results_df.to_dict('records'),
    }

    return _sanitize_for_json(response_data)
