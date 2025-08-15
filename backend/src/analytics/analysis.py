import pandas as pd
import numpy as np
from datetime import date, timedelta
from src.my_libs_py3.my_data import PriceDataFetcher
from src.my_libs_py3.fmp import FMPClient
from src.analytics.treasury_curve import build_treasury_curve

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

def run_analysis(ticker: str, expiration_date: date, r_current: float = 0.05, rate_source: str = 'etf'):
    """
    This is the core analysis function, refactored from run_option_screener in option_trade.py.
    It returns a JSON-serializable dictionary with the analysis results.
    """
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
    selected_strikes = strikes[(strikes > S_current * 0.8) & (strikes < S_current * 1.2)] # Analyze strikes within 20% of current price

    historical_prices_df = price_fetcher.get_price_data([ticker], method="td_data", back_day=350)
    hv_current = calculate_historical_volatility(historical_prices_df['Close'].tolist()) if historical_prices_df is not None and not historical_prices_df.empty else None

    key_vols_iv, _ = fetch_iv_term_structure(ticker, price_fetcher, fmp)
    if not key_vols_iv and hv_current: key_vols_iv = [(0, hv_current)]

    stock_details = price_fetcher.get_stock_details_finviz(ticker)
    div_current = stock_details.get('dividend_yield', 0.0)

    days_to_exp = (expiration_date - date.today()).days
    if days_to_exp < 0: return {"status": "error", "message": "Expiration date is in the past."}
    
    vol_term_structure = generate_forward_vol_structure(days_to_exp, key_vols_iv)
    
    # Determine risk-free rate input for pricer
    if rate_source == 'treasury':
        curve = build_treasury_curve(fmp)
        r_input = curve['rate_fn']
    else:
        r_input = r_current

    results = []
    for K in selected_strikes:
        for option_type in ['call', 'put']:
            market_price = _get_market_price_from_finviz_df(option_chain_df, K, option_type[0].upper())
            if market_price is None: continue
            
            model_price, _, _, _ = universal_binomial_pricer(
                S=S_current, K=K, expiration_date=expiration_date, r_input=r_input,
                sigma_input=vol_term_structure, option_type=option_type, div=div_current
            )
            
            if model_price > market_price:
                results.append({
                    "Strike": K, "Type": option_type.capitalize(), "Market Price": market_price,
                    "Model Price": model_price, "Undervalued By ($)": model_price - market_price,
                    "Undervalued By (%)": (model_price - market_price) / market_price * 100 if market_price > 0 else 0
                })

    # For Phase 1, we return the raw list of undervalued options.
    # The full holistic analysis can be added back later.
    return {
        "status": "success",
        "ticker": ticker,
        "current_price": S_current,
        "analysis_time": date.today().isoformat(),
        "undervalued_options": results,
        "rate_source": rate_source
    }
