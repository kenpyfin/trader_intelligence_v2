import pandas as pd
import numpy as np
from datetime import date, timedelta
from src.my_libs_py3.my_data import PriceDataFetcher
from src.my_libs_py3.fmp import FMPClient
from src.analytics.treasury_curve import build_treasury_curve
from .methodologies.gpt_verdict import generate_gpt_verdict

# This file is a migration of the analysis logic from option_trade.py.
# All Streamlit-specific code (st.*) has been removed.

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
    for col in required_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.dropna(subset=required_cols, inplace=True)
    if len(df) < 51: return {"error": "Not enough valid data points after cleaning.", "context": {}}

    df['SMA50'] = df['Close'].rolling(window=50).mean()
    df['SMA200'] = df['Close'].rolling(window=200).mean()
    df['AvgVol10'] = df['Volume'].rolling(window=10).mean()
    
    if len(df) < 4: return {"error": "Not enough data after calculating indicators.", "context": {}}

    last_row = df.iloc[-1]
    C0, SMA50_val, SMA200_val = last_row['Close'], last_row['SMA50'], last_row.get('SMA200')
    primary_trend = "Uptrend" if pd.notna(SMA200_val) and C0 > SMA200_val else "Downtrend" if pd.notna(SMA200_val) else "Undetermined"
    secondary_trend = "Uptrend" if C0 > SMA50_val else "Downtrend"

    market_context = {
        "primary_trend": primary_trend,
        "secondary_trend": secondary_trend
    }
    
    # Simplified pattern logic for brevity. Full logic can be migrated if needed.
    found_patterns = []
    # In a real implementation, the detailed pattern recognition logic from option_trade.py would go here.
    # For now, this is a placeholder.

    return {"patterns": found_patterns, "context": market_context, "plot_df": df}


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


def run_analysis(ticker: str, expiration_date: date, r_current: float = 0.05, rate_source: str = 'etf', analysis_method: str = 'holistic-market-edge'):
    fmp = FMPClient()
    price_fetcher = PriceDataFetcher()

    rt_quote = fmp.realtimequote(ticker)
    if rt_quote is None or rt_quote.empty or 'price' not in rt_quote.columns:
        return {"status": "error", "message": f"Could not fetch current price for {ticker}."}
    S_current = rt_quote.price.iloc[0]

    option_chain_df = price_fetcher.get_option_data_finviz(ticker, 'o', expiration_date.strftime('%Y-%m-%d'))
    if option_chain_df is None or option_chain_df.empty:
        return {"status": "error", "message": f"Could not fetch option chain for {ticker} on {expiration_date}."}
    
    option_chain_df['Strike'] = pd.to_numeric(option_chain_df['Strike'], errors='coerce')
    option_chain_df.dropna(subset=['Strike'], inplace=True)
    option_chain_df.sort_values('Strike', inplace=True)
    strikes = option_chain_df['Strike'].unique()
    
    historical_prices_df = price_fetcher.get_price_data([ticker], method="td_data", back_day=350)
    hv_current = calculate_historical_volatility(historical_prices_df['Close'].tolist()) if historical_prices_df is not None and not historical_prices_df.empty else None

    key_vols_iv, _ = fetch_iv_term_structure(ticker, price_fetcher, fmp)
    if not key_vols_iv and hv_current: key_vols_iv = [(0, hv_current)]

    stock_details = price_fetcher.get_stock_details_finviz(ticker)
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
                results.append({"Strike": K, "Type": option_type.capitalize(), "Market Price": market_price, "Model Price": model_price})

    synthesis_data = {}
    spot_iv = key_vols_iv[0][1] if key_vols_iv else None
    iv_high, iv_low = False, False
    if key_vols_iv and hv_current:
        if spot_iv > hv_current * 1.2: iv_high = True
        elif spot_iv < hv_current * 0.8: iv_low = True
    
    # This section is a simplified port from option_trade.py's synthesis logic
    if candlestick_analysis and "context" in candlestick_analysis:
        synthesis_data['trend'] = {'sentiment': 'bullish' if candlestick_analysis['context']['primary_trend'] == 'Uptrend' else 'bearish', 'summary': f"Primary trend is {candlestick_analysis['context']['primary_trend']}"}

    final_conclusion_html, final_bias = generate_holistic_conclusion(synthesis_data)

    analysis_result_package = {
        "status": "success", "ticker": ticker, "S_current": S_current, "expiration_date": expiration_date.isoformat(), "dte": days_to_exp,
        "synthesis_data": synthesis_data,
        "final_conclusion_html": final_conclusion_html, "final_bias": final_bias, "iv_high": iv_high,
        "iv_low": iv_low, "candlestick_analysis": candlestick_analysis, "volume_oi_analysis": volume_oi_analysis,
        "movement_analysis_results": movement_analysis_results, "results_df": results
    }

    if 'gpt-verdict' in analysis_method:
        use_web = 'web' in analysis_method
        gpt_verdict = generate_gpt_verdict(ticker, analysis_result_package, model="gpt-5", use_web_search=use_web)
        analysis_result_package['final_bias'] = gpt_verdict.get('final_bias', 'Neutral')
        analysis_result_package['final_conclusion_html'] = gpt_verdict.get('summary_html', 'Failed to get AI summary.')
        analysis_result_package['gpt_verdict'] = gpt_verdict

    return analysis_result_package
