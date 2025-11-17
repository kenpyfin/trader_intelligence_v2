import asyncio
import uuid

# Ensure an event loop is set for the current context *before* importing ib_insync or its dependencies.
# This is crucial as some parts of ib_insync/eventkit might try to access the loop at import time.
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import ib_insync.util # ib_insync includes nest_asyncio as a dependency

# Apply ib_insync's patch. This function call includes nest_asyncio.apply()
# and is generally needed for ib_insync to work correctly in environments like Streamlit.
ib_insync.util.patchAsyncio()

# --- Display Helper Functions ---
def display_currency(value, default="N/A"):
    """Formats a number as currency (e.g., $123.45) or returns default if None or non-numeric."""
    if value is None:
        return default
    try:
        return f"\\${value:,.2f}" # Escaped $ for markdown, added comma for thousands
    except (ValueError, TypeError):
        return default

def display_percentage(value, precision=2, default="N/A"):
    """Formats a number as a percentage (e.g., 0.28 -> 28.00%) or returns default if None or non-numeric."""
    if value is None:
        return default
    try:
        return f"{value:.{precision}%}"
    except (ValueError, TypeError):
        return default

def display_percentage_point(value, precision=1, default="N/A", add_plus_sign=False):
    """Formats a number as percentage points (e.g., 50.0 -> 50.0%) or returns default if None or non-numeric."""
    if value is None:
        return default
    try:
        if add_plus_sign:
            return f"{value:+.{precision}f}%"
        return f"{value:.{precision}f}%"
    except (ValueError, TypeError):
        return default

def display_capitalized(value, default="N/A"):
    """Capitalizes a string or returns default if None."""
    if value is None:
        return default
    return str(value).capitalize()

def display_date(value, default="N/A"):
    """Formats a date object as string or returns default if None."""
    if value is None:
        return default
    return str(value) # Date objects have a good default string representation

def display_float(value, precision=2, default="N/A"):
    """Formats a float with specified precision or returns default if None or non-numeric."""
    if value is None:
        return default
    try:
        # Ensure the format specifier is correctly constructed for precision
        return f"{value:.{precision}f}"
    except (ValueError, TypeError):
        return default

import pandas as pd # Added for DataFrame operations in IV fetching
import streamlit as st
import numpy as np
import re # For advanced alert sorting
from datetime import date, timedelta
import json # For saving/loading state
import os   # For file path operations
import plotly.graph_objects as go
import my_libs_py3.my_lib # To access the directory path for saving state

from my_libs_py3.my_data import PriceDataFetcher
from my_libs_py3.fmp import FMPClient
from my_libs_py3.TD_Order import IBTrader
from option_leg_class import OptionLeg # Import the new class


# A custom JSON encoder to handle numpy types
class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)


@st.cache_resource
def get_ib_trader():
    """Returns a cached instance of the IBTrader."""
    return IBTrader()


# --- Session State Persistence Helper Functions ---
# Define the path for the session state file using the directory from my_libs_py3
# This ensures consistency if my_libs_py3.my_lib.directory is used elsewhere for file storage.
# Note: This assumes my_libs_py3.my_lib.directory is a valid, writable path.
_SESSION_STATE_FILE_PATH = os.path.join(my_libs_py3.my_lib.directory, "streamlit_session_state.json")

# Define keys that hold date objects within each position's dictionary
_POSITION_DATE_KEYS = ["expiration_date", "open_date"]
# Define date keys for legs in the strategy building form
_STRATEGY_LEG_BUILDING_DATE_KEYS = ["expiration_date"]

def _sanitize_for_json(item):
    """Recursively sanitizes an item for JSON serialization.
    Converts NaN/Infinity floats to None.
    """
    if isinstance(item, dict):
        return {k: _sanitize_for_json(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [_sanitize_for_json(elem) for elem in item]
    elif isinstance(item, float) and (np.isnan(item) or np.isinf(item)):
        # st.warning(f"Sanitizing NaN/Infinity float to None for JSON.") # Optional: for debugging
        return None  # Represent as null in JSON
    return item

def _save_app_session_state():
    """Saves serializable parts of st.session_state to a JSON file."""
    state_to_save = {}
    for k, v in st.session_state.items():
        if k == "ss_tracked_positions" and isinstance(v, list):
            # Handle the list of position dictionaries (which can include single options or strategies)
            serializable_positions = []
            for pos_dict in v: # pos_dict can be a single option or a strategy dict
                serializable_item = {}
                for pk, pv in pos_dict.items():
                    if pk == "legs" and isinstance(pv, list): # Handle legs within a strategy
                        serializable_legs_for_strategy = []
                        for leg_item in pv: # leg_item is expected to be an OptionLeg object or a dict
                            if isinstance(leg_item, OptionLeg):
                                serializable_legs_for_strategy.append(leg_item.to_dict())
                            elif isinstance(leg_item, dict): # Fallback for old format or other dicts
                                # This part handles dictionaries that might not be OptionLeg objects,
                                # applying the previous date serialization logic.
                                serializable_leg_dict = {}
                                for leg_k, leg_v in leg_item.items():
                                    if leg_k in _STRATEGY_LEG_BUILDING_DATE_KEYS and isinstance(leg_v, date):
                                        serializable_leg_dict[leg_k] = leg_v.isoformat()
                                    else:
                                        serializable_leg_dict[leg_k] = _sanitize_for_json(leg_v) # Sanitize value
                                serializable_legs_for_strategy.append(serializable_leg_dict)
                            else: # Should not happen - leg_item is not OptionLeg and not dict
                                # If leg_item is complex and not JSON serializable, json.dump will raise TypeError
                                serializable_legs_for_strategy.append(_sanitize_for_json(leg_item))
                        serializable_item[pk] = serializable_legs_for_strategy
                    elif pk in _POSITION_DATE_KEYS and isinstance(pv, date): # Handle top-level dates in position/strategy
                        serializable_item[pk] = pv.isoformat()
                    else:
                        serializable_item[pk] = _sanitize_for_json(pv) # Sanitize other values in position dict
                serializable_positions.append(serializable_item)
            state_to_save[k] = serializable_positions
        elif k == "ss_analysis_cache" and isinstance(v, dict):
            # Handle the analysis cache. The result objects can be complex.
            # We need to serialize dates within the cached results.
            def serialize_cache_item(item):
                if isinstance(item, dict):
                    return {k_item: serialize_cache_item(v_item) for k_item, v_item in item.items()}
                elif isinstance(item, list):
                    return [serialize_cache_item(elem) for elem in item]
                elif isinstance(item, date):
                    # Use a marker to identify date objects for deserialization
                    return {"_is_date_": True, "iso": item.isoformat()}
                elif isinstance(item, float) and (np.isnan(item) or np.isinf(item)):
                    return None # JSON doesn't support NaN/inf
                return item
            state_to_save[k] = serialize_cache_item(v)
        elif k == "ss_new_strategy_legs_building" and isinstance(v, list):
            # Handle the list of strategy leg OptionLeg objects being built (for the form)
            serializable_legs = []
            for leg_item in v: # leg_item is expected to be an OptionLeg object
                if isinstance(leg_item, OptionLeg):
                    # Assuming OptionLeg.to_dict() returns a dict that is either fully sanitized
                    # or will be caught by _sanitize_for_json if applied to its result.
                    # For now, trust to_dict() and sanitize its output.
                    serializable_legs.append(_sanitize_for_json(leg_item.to_dict()))
                elif isinstance(leg_item, dict): # Fallback for old format if any
                    serializable_leg_dict = {}
                    for leg_k, leg_v in leg_item.items():
                        if leg_k in _STRATEGY_LEG_BUILDING_DATE_KEYS and isinstance(leg_v, date):
                            serializable_leg_dict[leg_k] = leg_v.isoformat()
                        else:
                            serializable_leg_dict[leg_k] = _sanitize_for_json(leg_v) # Sanitize value
                    serializable_legs.append(serializable_leg_dict)
                else: # Should not happen - leg_item is not OptionLeg and not dict
                    serializable_legs.append(_sanitize_for_json(leg_item))
            state_to_save[k] = serializable_legs
        elif isinstance(v, date): # For other top-level date objects (e.g., form inputs)
            if k.startswith("ss_") or k.startswith("new_pos_"): # Save if ss_ or new_pos_ prefixed
                state_to_save[k] = v.isoformat()
        elif isinstance(v, (str, int, float, bool, list, dict)) or v is None:
            # Only include basic JSON-serializable types and None
            # Save if ss_ or new_pos_ prefixed (form inputs)
            if k.startswith("ss_") or k.startswith("new_pos_"): 
                state_to_save[k] = _sanitize_for_json(v) # Sanitize the value
        # Non-serializable items or items not matching prefixes (unless special cased) will be skipped

    temp_file_path = _SESSION_STATE_FILE_PATH + ".tmp"
    try:
        # Ensure directory exists
        state_dir = os.path.dirname(_SESSION_STATE_FILE_PATH)
        if not os.path.exists(state_dir):
            os.makedirs(state_dir, exist_ok=True)
            
        with open(temp_file_path, 'w') as f:
            json.dump(state_to_save, f, indent=4)
        
        # Atomically replace the old file with the new one
        os.replace(temp_file_path, _SESSION_STATE_FILE_PATH)

    except Exception as e:
        # Using st.warning to avoid blocking app flow for non-critical save errors
        st.warning(f"Could not save session state: {e}")
        # Clean up the temporary file if it exists
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

def _load_app_session_state():
    """Loads session state from a JSON file, adding unique IDs to positions if missing."""
    if not os.path.exists(_SESSION_STATE_FILE_PATH) or os.path.getsize(_SESSION_STATE_FILE_PATH) == 0:
        return {}
    try:
        with open(_SESSION_STATE_FILE_PATH, 'r') as f:
            loaded_data = json.load(f)

            # --- Deserialize cache with dates ---
            def deserialize_cache_item(item):
                if isinstance(item, dict):
                    if item.get("_is_date_"):
                        try:
                            return date.fromisoformat(item["iso"])
                        except (TypeError, ValueError):
                            return item # Return original dict if conversion fails
                    return {k_item: deserialize_cache_item(v_item) for k_item, v_item in item.items()}
                elif isinstance(item, list):
                    return [deserialize_cache_item(elem) for elem in item]
                return item

            if "ss_analysis_cache" in loaded_data:
                loaded_data["ss_analysis_cache"] = deserialize_cache_item(loaded_data["ss_analysis_cache"])

            # Convert date strings back to date objects
            for k, v in loaded_data.items():
                if k == "ss_tracked_positions" and isinstance(v, list):
                    deserialized_positions = [] # This will hold deserialized single options or strategies
                    for item_dict_str in v: # item_dict_str can be a single option or a strategy dict
                        # --- Upgrade: Add unique ID if missing ---
                        if 'id' not in item_dict_str:
                            item_dict_str['id'] = str(uuid.uuid4())
                        
                        deserialized_item = {}
                        for pk, pv_str in item_dict_str.items():
                            if pk == "legs" and isinstance(pv_str, list): # Handle legs within a strategy
                                deserialized_legs_for_strategy = []
                                for leg_item_dict_str in pv_str: # leg_item_dict_str is a dict from JSON
                                    if isinstance(leg_item_dict_str, dict) and leg_item_dict_str.get("_class_marker_") == "OptionLeg":
                                        try:
                                            deserialized_legs_for_strategy.append(OptionLeg.from_dict(leg_item_dict_str))
                                        except Exception as e_leg_load:
                                            st.warning(f"Failed to load OptionLeg from dict (with marker): {leg_item_dict_str}. Error: {e_leg_load}. Storing as dict.")
                                            deserialized_legs_for_strategy.append(leg_item_dict_str) # Fallback
                                    elif isinstance(leg_item_dict_str, dict): # Legacy dict (no marker) or other dict
                                        # Attempt to upgrade or process as legacy
                                        upgraded_or_legacy_leg = _try_upgrade_leg_dict_to_optionleg(leg_item_dict_str)
                                        deserialized_legs_for_strategy.append(upgraded_or_legacy_leg)
                                    else: # Not a dict, store as is (should ideally not happen for legs)
                                        deserialized_legs_for_strategy.append(leg_item_dict_str)
                                deserialized_item[pk] = deserialized_legs_for_strategy
                            elif pk in _POSITION_DATE_KEYS and isinstance(pv_str, str): # Handle top-level dates
                                try:
                                    deserialized_item[pk] = date.fromisoformat(pv_str)
                                except (TypeError, ValueError):
                                    st.warning(f"Could not convert date string '{pv_str}' for key '{pk}' in a tracked item. Using original value.")
                                    deserialized_item[pk] = pv_str
                            else:
                                deserialized_item[pk] = pv_str
                        deserialized_positions.append(deserialized_item)
                    loaded_data[k] = deserialized_positions
                elif k == "ss_new_strategy_legs_building" and isinstance(v, list):
                    # This is for the strategy building form (ss_new_strategy_legs_building)
                    deserialized_legs = []
                    for leg_item_dict_str in v: # leg_item_dict_str is a dict from JSON
                        if isinstance(leg_item_dict_str, dict) and leg_item_dict_str.get("_class_marker_") == "OptionLeg":
                            try:
                                deserialized_legs.append(OptionLeg.from_dict(leg_item_dict_str))
                            except Exception as e_leg_load:
                                st.warning(f"Failed to load OptionLeg for strategy building form (with marker): {leg_item_dict_str}. Error: {e_leg_load}. Storing as dict.")
                                deserialized_legs.append(leg_item_dict_str) # Fallback
                        elif isinstance(leg_item_dict_str, dict): # Legacy dict (no marker) or other dict
                            # Attempt to upgrade or process as legacy
                            upgraded_or_legacy_leg = _try_upgrade_leg_dict_to_optionleg(leg_item_dict_str)
                            deserialized_legs.append(upgraded_or_legacy_leg)
                        else: # Not a dict, store as is
                            deserialized_legs.append(leg_item_dict_str)
                    loaded_data[k] = deserialized_legs
                # Example for other top-level date keys if they existed and were ss_ prefixed
                # elif k == "ss_some_other_date_key" and isinstance(v, str):
                #     try:
                #         loaded_data[k] = date.fromisoformat(v)
                #     except (TypeError, ValueError):
                #         st.warning(f"Could not convert date string '{v}' for key '{k}'.")
                #         pass
            return loaded_data
    except json.JSONDecodeError as e_json:
        st.error(f"Error decoding session state JSON file ({_SESSION_STATE_FILE_PATH}): {e_json}. The file might be corrupted. Consider deleting it to reset state.")
        return {} # Return default state
    except Exception as e:
        st.warning(f"Could not load session state due to an unexpected error: {e}")
        return {}

def _try_upgrade_leg_dict_to_optionleg(leg_dict_str):
    """
    Attempts to convert a dictionary (potentially legacy format) to an OptionLeg object.
    If successful, returns the OptionLeg object.
    If unsuccessful, processes the expiration_date within the dictionary and returns the dictionary.
    """
    try:
        # OptionLeg.__init__ handles string dates and type conversions for other fields.
        # It expects keys: buy_sell, option_type, quantity, strike_price, expiration_date, open_price
        
        # Ensure all required keys are present for robust construction attempt.
        # This is a basic check; OptionLeg.__init__ will do more thorough validation.
        required_keys = ["buy_sell", "option_type", "quantity", "strike_price", "expiration_date", "open_price"]
        if not all(key in leg_dict_str for key in required_keys):
            # Let OptionLeg.__init__ handle missing keys if that's preferred,
            # or raise a more specific error here. For now, we proceed and let __init__ fail.
            pass # Proceed to attempt construction

        upgraded_leg = OptionLeg(
            buy_sell=leg_dict_str.get("buy_sell"),
            option_type=leg_dict_str.get("option_type"),
            quantity=leg_dict_str.get("quantity"),
            strike_price=leg_dict_str.get("strike_price"),
            expiration_date=leg_dict_str.get("expiration_date"), # Expected to be ISO string
            open_price=leg_dict_str.get("open_price")
        )
        st.info(f"Successfully upgraded a leg from legacy dictionary format to OptionLeg object: {upgraded_leg!r}")
        return upgraded_leg
    except Exception as e_upgrade:
        st.warning(f"Could not upgrade legacy leg dict to OptionLeg: {e_upgrade}. Keeping as dict. Details: {leg_dict_str}")
        # Fallback: parse date within the dict if it's a legacy dict and return the dict
        processed_legacy_dict = {}
        for leg_k, leg_v_str in leg_dict_str.items():
            # Only process expiration_date, as other fields are used as-is by fallback logic.
            if leg_k == "expiration_date" and isinstance(leg_v_str, str):
                try:
                    processed_legacy_dict[leg_k] = date.fromisoformat(leg_v_str)
                except (TypeError, ValueError):
                    # If date conversion fails, keep the original string value
                    processed_legacy_dict[leg_k] = leg_v_str 
            else:
                processed_legacy_dict[leg_k] = leg_v_str
        st.info("Processed a leg in legacy dictionary format (upgrade failed).")
        return processed_legacy_dict

# --- Helper Functions ---
def calculate_historical_volatility(prices, lookback_days=20):
    """Calculates annualized historical volatility from a list of closing prices."""
    if len(prices) < lookback_days + 1:
        # Not enough data points for the requested lookback period
        if len(prices) < 2: return 0.0 # Need at least two prices for one return
        lookback_days = len(prices) - 1 # Use available data

    # Use the last `lookback_days + 1` prices to get `lookback_days` returns
    relevant_prices = prices[-lookback_days-1:]
    returns = np.diff(np.log(relevant_prices))

    # Annualize the standard deviation of daily returns
    # Assuming 252 trading days in a year
    annualization_factor = np.sqrt(252)
    hv = np.std(returns) * annualization_factor
    return hv


def generate_forward_vol_structure(days_to_expiration, key_vol_points):
    """Generates a daily volatility term structure using forward volatility interpolation."""
    if days_to_expiration <= 0:
        return np.array([])
    
    if not key_vol_points:
        # Fallback to a default flat volatility if no key_vol_points are provided.
        # This should ideally be handled by the caller or configured.
        # print("Warning: No key volatility points provided. Using default flat vol of 0.20.")
        return np.full(days_to_expiration, 0.20)

    key_vol_points.sort() # Sort by day
    _days, _vols = zip(*key_vol_points)
    
    days = list(_days)
    vols = list(_vols)

    # Ensure vol structure starts from day 0
    if not days or days[0] != 0:
        first_vol = vols[0] if vols else 0.20 # Use first vol, or default if vols is empty
        days.insert(0, 0)
        vols.insert(0, first_vol)
    
    days_arr = np.array(days, dtype=float)
    vols_arr = np.array(vols, dtype=float) # Ensure float dtype for interpolation

    # We need spot vols for maturities 0, 1, ..., days_to_expiration for calculations.
    # target_days_for_spot will be [0, 1, ..., days_to_expiration].
    target_days_for_spot = np.arange(days_to_expiration + 1)
    
    # Interpolate spot volatilities for each day up to days_to_expiration.
    # spot_vols_daily[k] is the spot vol for a k-day maturity.
    spot_vols_daily = np.interp(target_days_for_spot, days_arr, vols_arr)

    forward_vols = np.zeros(days_to_expiration)

    # Calculate daily forward volatilities.
    # forward_vols[i] is the vol for the period [day i, day i+1].
    for i in range(days_to_expiration): # Loop from 0 to days_to_expiration-1
        # Time at end of day i (or start of day i) from today.
        t_i = i / 365.0
        # Time at end of day i+1 from today.
        t_i_plus_1 = (i + 1) / 365.0
        
        # Variance for maturity up to end of day i.
        # spot_vols_daily[i] is spot vol for i-day maturity.
        var_i = spot_vols_daily[i]**2 * t_i
        
        # Variance for maturity up to end of day i+1.
        # spot_vols_daily[i+1] is spot vol for (i+1)-day maturity.
        var_i_plus_1 = spot_vols_daily[i+1]**2 * t_i_plus_1
        
        numerator = var_i_plus_1 - var_i
        # Denominator is the length of the forward period in years (1 day = 1/365 years).
        denominator = t_i_plus_1 - t_i 
        
        if denominator <= 0: # Avoid division by zero or negative sqrt
            # This case should ideally not happen if t_i and t_i_plus_1 are correctly structured.
            # If it does, use the spot vol for the period.
            forward_vols[i] = spot_vols_daily[i+1] if i + 1 < len(spot_vols_daily) else spot_vols_daily[i]
        else:
            forward_vols[i] = np.sqrt(max(0, numerator) / denominator)
            
    return forward_vols

# --- Core Pricing Engine (from previous version) ---
def universal_binomial_pricer(S, K, expiration_date, r_input, sigma_input, model='jarrow_rudd', option_type='call', exercise_type='american', div=0.0, historical_vol=None):
    """Calculates option price using a choice of binomial models with advanced contextual alerts."""
    today = date.today()
    days_to_expiration = (expiration_date - today).days
    N = days_to_expiration
    T = days_to_expiration / 365.0
    
    if N <= 0:
        price = np.maximum(0, S - K if option_type == 'call' else K - S)
        delta = 1 if S > K else (0 if S == K else -1)
        # Return empty greeks dict for expired option, except for delta
        return price, {'delta': delta, 'gamma': 0, 'theta': 0, 'vega': 0}, ["Option has expired."]
    
    dt = T / N

    def process_param(param_input, t_values):
        if callable(param_input): return np.array([param_input(t) for t in t_values])
        if isinstance(param_input, (list, np.ndarray)): return np.array(param_input)
        return np.full(N, float(param_input))

    time_steps = np.linspace(0, T - dt, N)
    r_rates = process_param(r_input, time_steps)
    sigma_vols = process_param(sigma_input, time_steps)
    
    stock_price_tree = np.zeros((N + 1, N + 1))
    stock_price_tree[0, 0] = S # Initialize the root of the stock price tree
    p_steps = np.zeros(N)

    for i in range(N):
        r_step, sigma_step = r_rates[i], sigma_vols[i]
        if model.lower() == 'jarrow_rudd':
            p = 0.5
            drift = (r_step - div - 0.5 * sigma_step**2) * dt
            u, d = np.exp(drift + sigma_step * np.sqrt(dt)), np.exp(drift - sigma_step * np.sqrt(dt))
        else: # CRR
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
    # Greeks are typically calculated based on the initial state (node [0,0])
    # S_initial = stock_price_tree[0,0] # This is just S
    # C_initial = option_value_tree[0,0] # This is the option price

    if N >= 2:
        # Delta: (C_u - C_d) / (S_u - S_d) using nodes at t=1
        # S_u = stock_price_tree[0,1], S_d = stock_price_tree[1,1]
        # C_u = option_value_tree[0,1], C_d = option_value_tree[1,1]
        delta_numerator = option_value_tree[0, 1] - option_value_tree[1, 1]
        delta_denominator = stock_price_tree[0, 1] - stock_price_tree[1, 1]
        delta = delta_numerator / delta_denominator if delta_denominator != 0 else (1.0 if option_type == 'call' else -1.0) # Approximation for zero denominator

        # Gamma: (delta_u - delta_d) / (0.5 * (S_uu - S_dd)) using nodes at t=2
        # S_uu = stock_price_tree[0,2], S_ud = stock_price_tree[1,2], S_dd = stock_price_tree[2,2]
        # C_uu = option_value_tree[0,2], C_ud = option_value_tree[1,2], C_dd = option_value_tree[2,2]
        
        # Delta_u: (C_uu - C_ud) / (S_uu - S_ud)
        delta_u_num = option_value_tree[0, 2] - option_value_tree[1, 2]
        delta_u_den = stock_price_tree[0, 2] - stock_price_tree[1, 2]
        delta_up = delta_u_num / delta_u_den if delta_u_den != 0 else delta # Fallback

        # Delta_d: (C_ud - C_dd) / (S_ud - S_dd)
        delta_d_num = option_value_tree[1, 2] - option_value_tree[2, 2]
        delta_d_den = stock_price_tree[1, 2] - stock_price_tree[2, 2]
        delta_down = delta_d_num / delta_d_den if delta_d_den != 0 else delta # Fallback
        
        gamma_numerator = delta_up - delta_down
        # Average change in stock price from S_uu to S_dd path
        gamma_denominator = 0.5 * (stock_price_tree[0, 2] - stock_price_tree[2, 2])
        gamma = gamma_numerator / gamma_denominator if gamma_denominator != 0 else 0.0

        # Theta: (C_ud - C_initial) / (2 * dt)
        # C_ud is option_value_tree[1,2] - value after two steps, one up, one down.
        # C_initial is option_value_tree[0,0]
        theta = (option_value_tree[1, 2] - option_value_tree[0,0]) / (2 * dt)
        greeks = {'delta': delta, 'gamma': gamma, 'theta': theta}
    elif N == 1:
        # Simplified delta for the last day
        delta_numerator = option_value_tree[0, 1] - option_value_tree[1, 1]
        delta_denominator = stock_price_tree[0, 1] - stock_price_tree[1, 1]
        delta = delta_numerator / delta_denominator if delta_denominator != 0 else (1.0 if option_type == 'call' else -1.0)
        greeks = {'delta': delta, 'gamma': 0, 'theta': 0} # Theta is effectively the decay over the last period to expiry


    actionable_alerts = []
    if historical_vol and len(sigma_vols) > 0:
        iv, hv = sigma_vols[0], historical_vol # iv is the current spot implied volatility
        if iv / hv > 1.5: 
            actionable_alerts.append(f"CONTEXT: IV ({iv:.1%}) significantly above HV ({hv:.1%}). Suggests option premium is rich. Consider strategies that benefit from IV decline or be cautious with net long vega positions.")
        elif iv / hv < 0.7: 
            actionable_alerts.append(f"CONTEXT: IV ({iv:.1%}) significantly below HV ({hv:.1%}). Suggests option premium is cheap. Consider strategies that benefit from IV rise or look for net long vega opportunities.")
        # You could add a moderate case here too, e.g., 1.2 < iv/hv <= 1.5

    if exercise_type == 'american':
        for i in range(N):
            exercise_prices = [stock_price_tree[j, i] for j in range(i + 1) if exercise_decision_tree[j, i]]
            if exercise_prices:
                threshold = max(exercise_prices) if option_type == 'put' else min(exercise_prices)
                comp = "<=" if option_type == 'put' else ">="
                # *** ALERT FORMATTING CHANGE HERE ***
                alert_date = today + timedelta(days=i)
                alert_text = f"On {alert_date.strftime('%Y-%m-%d')}: EXERCISE ALERT: Optimal to exercise if price {comp} ${threshold:.2f}"
                actionable_alerts.append(alert_text)

    atm_threshold_pct, time_decay_warning_days = 0.05, 21
    if N <= time_decay_warning_days:
        is_atm = any(abs(stock_price_tree[j, i] - K) / K < atm_threshold_pct for i in range(N) for j in range(i+1) if stock_price_tree[j,i] > 0)
        if is_atm:
             # *** ALERT FORMATTING CHANGE HERE ***
            alert_date_str = f"in the next {N} days"
            alert_text = f"STRATEGY ALERT ({alert_date_str}): Nearing expiration while ATM. Theta decay will accelerate. "
            if historical_vol and sigma_vols[-1] > historical_vol:
                alert_text += "High IV suggests a large move is priced in; consider closing if you doubt it will occur."
            else:
                alert_text += "Consider closing to capture remaining time value."
            actionable_alerts.append(alert_text)

    def sort_key(alert_str): # Ensure consistent return type (string) for comparison
        if "EXERCISE ALERT" in alert_str:
            try:
                # Attempt to extract date for chronological sorting of exercise alerts
                date_part = alert_str.split("On ")[1].split(":")[0]
                return f"0 {date_part} {alert_str}" # Exercise alerts first, sorted by date
            except IndexError:
                return f"0 {alert_str}" # Fallback if date parsing fails
        if "STRATEGY ALERT" in alert_str: return f"1 {alert_str}"
        if "CONTEXT" in alert_str: return f"2 {alert_str}"
        return f"9 {alert_str}" # Default for any other alerts
            
    actionable_alerts.sort(key=sort_key)

    early_exercise_premium_at_t0 = 0.0
    if N > 0 and exercise_type == 'american': # Only for American options and if not expired
        # Calculate intrinsic and continuation value specifically for t=0 (node [0,0])
        intrinsic_value_t0 = np.maximum(0, stock_price_tree[0, 0] - K if option_type == 'call' else K - stock_price_tree[0, 0])
        
        # Continuation value at t=0 is based on values at t=1 (nodes [0,1] and [1,1])
        # Ensure N >= 1 for option_value_tree[0,1] and option_value_tree[1,1] to be valid
        if N >= 1:
            continuation_value_t0 = np.exp(-r_rates[0] * dt) * \
                                  (p_steps[0] * option_value_tree[0, 1] + 
                                   (1 - p_steps[0]) * option_value_tree[1, 1])
            
            if intrinsic_value_t0 > continuation_value_t0: # Optimal to exercise at t=0
                early_exercise_premium_at_t0 = intrinsic_value_t0 - continuation_value_t0
        # If N=0, early_exercise_premium_at_t0 remains 0 as option has expired or is at expiry.

    # Return the calculated option price, greeks, alerts, and early exercise premium at t=0
    return option_value_tree[0,0], greeks, actionable_alerts, early_exercise_premium_at_t0

# --- Main Position Tracking Class ---
class OptionPositionTracker:
    def __init__(self, ticker, K, expiration_date, option_type, open_date, open_price, 
                 profit_target_pct=50.0, stop_loss_pct=-25.0, open_iv=None,
                 exercise_type='american', model='jarrow_rudd'):
        self.ticker = ticker
        self.K = K
        self.expiration_date = expiration_date
        self.option_type = option_type
        self.open_date = open_date
        self.open_price = open_price
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self.open_iv = open_iv
        self.exercise_type = exercise_type
        self.model = model
        self.price_fetcher = PriceDataFetcher()
        # Streamlit will handle the display of this information when analysis is run.
        # If you need to see this at initialization for debugging, use st.sidebar.write or similar.


    def check_profit_targets(self, current_price, alerts_list):
        """Checks if pre-defined profit or loss targets have been hit."""
        pnl_pct = ((current_price - self.open_price) / self.open_price) * 100 if self.open_price > 0 else 0
        
        # *** P&L ALERT TEXT ENHANCED ***
        if pnl_pct >= self.profit_target_pct:
            alerts_list.append(f"P&L ALERT: Profit target of {self.profit_target_pct:.0f}% hit (P&L: {pnl_pct:+.2f}%). Consider using a trailing stop to protect gains while allowing for upside.")
        elif pnl_pct <= self.stop_loss_pct:
            alerts_list.append(f"P&L ALERT: Stop-loss of {self.stop_loss_pct:.0f}% hit. P&L is {pnl_pct:+.2f}%. Consider closing immediately.")
            
    def check_greeks_based_rules(self, greeks, current_option_price, days_to_expiration, alerts_list):
        """Adds alerts based on common trading heuristics related to Greeks."""
        delta = greeks.get('delta', 0)
        gamma = greeks.get('gamma', 0)
        theta = greeks.get('theta', 0) # This is annualized theta

        # *** DELTA ALERT TEXT ENHANCED ***
        if self.option_type == 'call' and delta >= 0.80:
             alerts_list.append(f"GREEKS ALERT: Delta is high ({delta:.2f}), implying an ~{abs(delta)*100:.0f}% chance of expiring ITM. Position will behave more like stock. Consider closing to realize profits.")
        elif self.option_type == 'put' and delta <= -0.80:
             alerts_list.append(f"GREEKS ALERT: Delta is high ({abs(delta):.2f}), implying an ~{abs(delta)*100:.0f}% chance of expiring ITM. Position will behave more like stock. Consider closing to realize profits.")

        # *** NEW GAMMA ALERT ***
        # High gamma is most impactful for ATM options near expiry, indicating instability.
        if gamma > 0.04 and days_to_expiration <= 45:
            alerts_list.append(f"GAMMA ALERT: Gamma is high ({gamma:.3f}). The option's Delta is sensitive and will change rapidly with stock price moves, increasing P&L volatility.")

        # Theta decay alert
        if current_option_price > 0 and days_to_expiration > 0:
            daily_theta = theta / 365.0
            theta_decay_pct_of_price = abs(daily_theta / current_option_price)
            
            # Alert if daily theta decay is more than 1% of option price, and DTE < 45 days
            THETA_DECAY_THRESHOLD_PCT = 0.01 
            THETA_ALERT_DTE_THRESHOLD = 45

            if theta_decay_pct_of_price > THETA_DECAY_THRESHOLD_PCT and days_to_expiration <= THETA_ALERT_DTE_THRESHOLD:
                alerts_list.append(f"THETA DECAY ALERT: Daily theta ({daily_theta:.3f}) is {theta_decay_pct_of_price:.2%} of option price. "
                                   f"Time decay is significant with {days_to_expiration} DTE.")
             
    def calculate_daily_check(self, r_current, key_vols_iv):
        """
        Performs daily analysis calculations and returns a dictionary of results.
        This function does NOT interact with Streamlit for display.
        """
        import traceback
        try:
            # --- 1. Fetch Data ---
            fmp = FMPClient()
            rt_quote = fmp.realtimequote(self.ticker)
            if rt_quote is None or rt_quote.empty or 'price' not in rt_quote.columns:
                raise ValueError(f"Could not fetch valid current price data for {self.ticker.upper()}.")
            S_current = rt_quote.price.iloc[0]
            if S_current is None:
                raise ValueError(f"Current price for {self.ticker.upper()} is None.")

            lookback_days_hv = 20
            historical_prices_df = self.price_fetcher.get_price_data([self.ticker], method="td_data", back_day=lookback_days_hv + 10)
            hv_current, hv_warning = None, None
            if historical_prices_df is not None and not historical_prices_df.empty and 'Close' in historical_prices_df.columns:
                closing_prices = historical_prices_df['Close'].tolist()
                if len(closing_prices) >= 2:
                    hv_current = calculate_historical_volatility(closing_prices, lookback_days=lookback_days_hv)
                else:
                    hv_warning = f"Not enough historical price data points ({len(closing_prices)}) for {self.ticker.upper()} to calculate HV."
            else:
                hv_warning = f"Could not fetch sufficient historical prices for {self.ticker.upper()} to calculate HV."

            stock_details = self.price_fetcher.get_stock_details_finviz(self.ticker)
            div_warning = None
            if not stock_details:
                div_warning = f"Could not fetch stock details for {self.ticker} from Finviz. Using default 0.00% for dividend yield."
            
            div_current_to_use = stock_details.get('dividend_yield', 0.0)

            # --- 2. Handle Expiration ---
            days_to_exp = (self.expiration_date - date.today()).days
            if days_to_exp < 0:
                intrinsic_value_at_expiry = max(0, S_current - self.K if self.option_type == 'call' else self.K - S_current)
                pnl_at_expiry = intrinsic_value_at_expiry - self.open_price if self.open_price is not None else None
                pnl_pct_at_expiry = None
                if pnl_at_expiry is not None and self.open_price is not None:
                    if self.open_price != 0: pnl_pct_at_expiry = (pnl_at_expiry / self.open_price) * 100
                    else: pnl_pct_at_expiry = float('inf') if pnl_at_expiry > 0 else (float('-inf') if pnl_at_expiry < 0 else 0.0)
                
                return {
                    "status": "expired", "ticker": self.ticker, "analysis_date": date.today(),
                    "expired_info": {
                        "pnl_at_expiry": pnl_at_expiry, "pnl_pct_at_expiry": pnl_pct_at_expiry
                    }
                }

            # --- 3. Price and Greeks Calculation ---
            vol_term_structure = generate_forward_vol_structure(days_to_exp, key_vols_iv)
            current_price, greeks, model_alerts, early_exercise_premium = universal_binomial_pricer(
                S=S_current, K=self.K, expiration_date=self.expiration_date, r_input=r_current,
                sigma_input=vol_term_structure, model=self.model, option_type=self.option_type,
                exercise_type=self.exercise_type, div=div_current_to_use, historical_vol=hv_current
            )

            vega_bump = 0.01
            bumped_key_vols_iv = [(d, v + vega_bump) for d, v in key_vols_iv]
            bumped_vol_term_structure = generate_forward_vol_structure(days_to_exp, bumped_key_vols_iv)
            price_after_vol_bump, _, _, _ = universal_binomial_pricer(
                S=S_current, K=self.K, expiration_date=self.expiration_date, r_input=r_current,
                sigma_input=bumped_vol_term_structure, model=self.model, option_type=self.option_type,
                exercise_type=self.exercise_type, div=div_current_to_use, historical_vol=None
            )
            greeks['vega'] = (price_after_vol_bump - current_price) if price_after_vol_bump is not None and current_price is not None else None

            # --- 4. Market Price and P&L ---
            option_chain_df_for_market_price = self.price_fetcher.get_option_data_finviz(self.ticker, 'o', self.expiration_date.strftime('%Y-%m-%d'))
            market_option_price = None
            if option_chain_df_for_market_price is not None and not option_chain_df_for_market_price.empty:
                market_option_price = _get_market_price_from_finviz_df(option_chain_df_for_market_price, self.K, self.option_type[0].upper())

            pnl_model, raw_pnl_pct_model = None, None
            if current_price is not None and self.open_price is not None:
                pnl_model = current_price - self.open_price
                if self.open_price != 0: raw_pnl_pct_model = (pnl_model / self.open_price) * 100
                else: raw_pnl_pct_model = float('inf') if pnl_model > 0 else (float('-inf') if pnl_model < 0 else 0.0)

            pnl_market, raw_pnl_pct_market = None, None
            if market_option_price is not None and self.open_price is not None:
                pnl_market = market_option_price - self.open_price
                if self.open_price != 0: raw_pnl_pct_market = (pnl_market / self.open_price) * 100
                else: raw_pnl_pct_market = float('inf') if pnl_market > 0 else (float('-inf') if pnl_market < 0 else 0.0)

            # --- 5. Generate Alerts ---
            all_alerts = list(model_alerts)
            self.check_profit_targets(current_price, all_alerts)
            self.check_greeks_based_rules(greeks, current_price, days_to_exp, all_alerts)
            if early_exercise_premium > 0:
                all_alerts.append(f"EARLY EXERCISE BENEFIT: Optimal to exercise now. Gain vs. holding: {display_currency(early_exercise_premium)} per share.")
            if self.open_iv is not None and len(vol_term_structure) > 0:
                current_spot_iv = vol_term_structure[0]
                if self.open_iv != 0:
                    iv_change_pct = ((current_spot_iv - self.open_iv) / self.open_iv) * 100
                    if abs(iv_change_pct) > 10.0:
                        direction = "increased" if iv_change_pct > 0 else "decreased"
                        all_alerts.append(f"IV CHANGE ALERT: Spot IV has {direction} by {iv_change_pct:+.1f}% (from {self.open_iv:.2%} to {current_spot_iv:.2%}). This impacts your option's value.")
            if 'vega' in greeks and greeks['vega'] is not None and greeks['vega'] != 0:
                all_alerts.append(f"VEGA ALERT: Position Vega is {greeks['vega']:.3f}. A 1% increase in IV would change the option's value by approx. ${greeks['vega']:.2f} per share.")
            if current_price is not None and market_option_price is not None:
                price_diff = abs(current_price - market_option_price)
                price_diff_pct = (price_diff / market_option_price) * 100 if market_option_price > 0.01 else 0
                if price_diff > 0.10 and price_diff_pct > 20.0:
                    comparison = "higher" if current_price > market_option_price else "lower"
                    all_alerts.append(f"MODEL VS MARKET PRICE: Model price ({display_currency(current_price)}) is {price_diff_pct:.1f}% {comparison} than Finviz market price ({display_currency(market_option_price)}). Discrepancy may indicate model calibration needs or market microstructure effects.")

            # --- 6. Assemble Results Dictionary ---
            return {
                "status": "success", "analysis_date": date.today(), "ticker": self.ticker,
                "warnings": [w for w in [hv_warning, div_warning] if w],
                "position_details": {
                    "type_display": f"{display_capitalized(self.exercise_type)} {display_capitalized(self.option_type)}",
                    "strike_display": display_currency(self.K), "open_date_display": display_date(self.open_date),
                    "expiration_date_display": display_date(self.expiration_date), "cost_display": display_currency(self.open_price),
                    "profit_target_display": display_percentage_point(self.profit_target_pct, precision=1),
                    "stop_loss_display": display_percentage_point(self.stop_loss_pct, precision=1),
                    "open_iv_display": display_percentage(self.open_iv, precision=2)
                },
                "market_data": {
                    "s_current_display": display_currency(S_current), "lookback_days_hv": lookback_days_hv,
                    "hv_current_display": display_percentage(hv_current, precision=2),
                    "div_current_display": display_percentage(div_current_to_use, precision=2)
                },
                "position_status": {
                    "pnl_model": pnl_model, "raw_pnl_pct_model": raw_pnl_pct_model,
                    "pnl_market": pnl_market, "raw_pnl_pct_market": raw_pnl_pct_market,
                    "current_model_price": current_price, "open_price": self.open_price,
                    "market_option_price": market_option_price
                },
                "risk_exposure": greeks,
                "actionable_alerts": all_alerts
            }
        except Exception as e:
            return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


def parse_key_iv_points(iv_str):
    """Parses a string like "0,0.28,30,0.29" into [(0, 0.28), (30, 0.29)]."""
    if not iv_str.strip():
        return []
    try:
        parts = [float(p.strip()) for p in iv_str.split(',')]
        if len(parts) % 2 != 0:
            st.error("Key IV Points string must have an even number of items (day,vol pairs).")
            return None # Indicate error
        return [(int(parts[i]), parts[i+1]) for i in range(0, len(parts), 2)]
    except ValueError:
        st.error("Invalid format for Key IV Points. Ensure all are numbers.")
        return None # Indicate error

# --- IV Term Structure Fetching Helper Functions ---
def _parse_finviz_iv_string(iv_input):
    """
    Converts Finviz IV string (e.g., "25.50%") or direct float/string float 
    (e.g., 0.2550 or "0.2550") to a float (e.g., 0.2550).
    """
    if pd.isna(iv_input):
        return None
    if isinstance(iv_input, float):
        return iv_input
    if isinstance(iv_input, str):
        if iv_input.endswith('%'):
            try:
                return float(iv_input.strip('%')) / 100.0
            except ValueError:
                return None
        else:
            # Try to convert directly if it's a string not ending in '%'
            try:
                return float(iv_input)
            except ValueError:
                return None
    return None

def _get_market_price_from_finviz_df(df, strike, option_type_char, current_stock_price_for_atm_fallback=None):
    """
    Extracts a market price for a specific option from Finviz DataFrame.
    Tries Bid/Ask midpoint, then Last Trade, then Last Close.
    option_type_char should be 'C' or 'P'.
    """
    if df is None or df.empty:
        return None

    # Ensure Strike and Type columns exist and are usable
    if 'Strike' not in df.columns or 'Type' not in df.columns:
        st.warning("Finviz DataFrame missing 'Strike' or 'Type' for market price extraction.")
        return None
    
    df['Strike'] = pd.to_numeric(df['Strike'], errors='coerce')
    # Finviz 'Type' is 'call' or 'put'. Convert option_type_char for matching.
    type_to_match = 'call' if option_type_char.upper() == 'C' else 'put'

    # Find the specific option row
    option_row_df = df[(df['Strike'] == strike) & (df['Type'].str.lower() == type_to_match)]

    if option_row_df.empty:
        # If exact match not found, maybe it's an ATM option for IV fetch, not direct price.
        # This part is more relevant if this function was also used for ATM IV's option.
        # For direct price, we expect an exact match.
        # If current_stock_price_for_atm_fallback is provided, we could try to find closest ATM as a last resort,
        # but for market price of a *specific* option, this is less ideal.
        st.warning(f"Specific option K={strike} {type_to_match} not found in Finviz data for market price.")
        return None

    option_row = option_row_df.iloc[0] # Get the Series for the row

    # Try Bid/Ask midpoint
    bid = pd.to_numeric(option_row.get('Bid'), errors='coerce')
    ask = pd.to_numeric(option_row.get('Ask'), errors='coerce')

    if pd.notna(bid) and pd.notna(ask) and ask > 0 and bid > 0 and (ask - bid) / ask < 0.5: # Basic liquidity/spread check
        return (bid + ask) / 2.0

    # Fallback to Last Trade
    last_trade = pd.to_numeric(option_row.get('Last Trade'), errors='coerce')
    if pd.notna(last_trade) and last_trade > 0:
        return last_trade
        
    # Fallback to Last Close
    last_close = pd.to_numeric(option_row.get('Last Close'), errors='coerce')
    if pd.notna(last_close) and last_close > 0:
        return last_close
        
    return None


def _get_atm_iv_from_finviz_df(df, current_stock_price):
    """Finds ATM IV from Finviz option chain DataFrame."""
    if df is None or df.empty or 'Strike' not in df.columns or 'IV' not in df.columns:
        return None

    # Ensure Strike is numeric
    df['Strike'] = pd.to_numeric(df['Strike'], errors='coerce')
    df = df.dropna(subset=['Strike'])
    if df.empty:
        return None

    # Find ATM strike
    try:
        diff_series = (df['Strike'] - current_stock_price).abs()
        sorted_indices = diff_series.argsort()
        atm_option_row = df.iloc[sorted_indices[:1]]
    except Exception: # Keep it broad in case of unexpected pandas issues
        return None # Error during ATM row selection

    if not atm_option_row.empty:
        iv_value = atm_option_row['IV'].iloc[0] # Changed variable name from iv_string
        parsed_iv = _parse_finviz_iv_string(iv_value)
        return parsed_iv
    else:
        return None

def fetch_iv_term_structure(ticker, price_fetcher, fmp_client, target_dtes=[7, 30, 90]):
    """
    Fetches IV term structure from Finviz for specified DTEs.
    Returns a list of (day, vol) tuples.
    """
    log_messages = []
    log_messages.append(f"Fetching IV term structure for {ticker} using Finviz...")
    key_iv_points = []
    MAX_DATE_SEARCH_ATTEMPTS = 7 # Max number of subsequent days to check if initial DTE yields no data
    
    # Get current stock price first
    rt_quote = fmp_client.realtimequote(ticker)
    if rt_quote is None or rt_quote.empty or 'price' not in rt_quote.columns:
        st.warning(f"Could not fetch current price for {ticker} to determine ATM IV. Skipping Finviz IV fetch.")
        return []
    current_stock_price = rt_quote.price.iloc[0]
    if current_stock_price is None:
        st.warning(f"Current price for {ticker} is None. Skipping Finviz IV fetch.")
        return [], log_messages # Return empty points and current logs

    for dte in target_dtes:
        expiration_date_dt = date.today() + timedelta(days=dte)
        expiration_date_str = expiration_date_dt.strftime('%Y-%m-%d')
        
        # Fetch both calls and puts to increase chance of finding liquid ATM IV
        # 'o' typically means both calls and puts in Finviz context if supported by export
        options_df = None
        found_data_for_dte = False

        for attempt in range(MAX_DATE_SEARCH_ATTEMPTS + 1): # +1 to include the initial attempt
            current_search_date_dt = expiration_date_dt + timedelta(days=attempt)
            current_search_date_str = current_search_date_dt.strftime('%Y-%m-%d')
            
            if attempt > 0: # Log if we are trying subsequent dates
                log_messages.append(f"  - DTE {dte}: No data for {expiration_date_dt.strftime('%Y-%m-%d')}. Trying next available date: {current_search_date_str} (Attempt {attempt}/{MAX_DATE_SEARCH_ATTEMPTS})")

            options_df = price_fetcher.get_option_data_finviz(ticker, 'o', current_search_date_str)
            
            if options_df is not None and not options_df.empty:
                atm_iv = _get_atm_iv_from_finviz_df(options_df, current_stock_price)
                if atm_iv is not None:
                    key_iv_points.append((dte, atm_iv)) # Use original DTE for the point
                    if attempt > 0:
                        log_messages.append(f"  - DTE {dte}: Found ATM IV {atm_iv:.2%} using data from {current_search_date_str} (after {attempt} day(s) search).")
                    else:
                        log_messages.append(f"  - DTE {dte}: Found ATM IV {atm_iv:.2%} for {current_search_date_str}.")
                    found_data_for_dte = True
                    break # Found data, exit search loop for this DTE
                else:
                    # Data was returned, but ATM IV could not be determined. Don't try next date for this DTE.
                    log_messages.append(f"  - DTE {dte}: Data found for {current_search_date_str}, but could not determine ATM IV.")
                    found_data_for_dte = True # Mark as found to prevent "no data" message below for this DTE
                    break 
            elif attempt == 0 : # Initial attempt failed, will loop if MAX_DATE_SEARCH_ATTEMPTS > 0
                log_messages.append(f"  - DTE {dte}: No option data returned from Finviz for initial target date {current_search_date_str}.")
            # If options_df is None or empty on subsequent attempts, the loop continues

        if not found_data_for_dte:
            log_messages.append(f"  - DTE {dte}: No option data found or ATM IV could not be determined after checking up to {MAX_DATE_SEARCH_ATTEMPTS} subsequent days from {expiration_date_str}.")
            
    if not key_iv_points:
        st.warning(f"Could not automatically fetch any IV points for {ticker} from Finviz after all attempts.") # Global warning
    else:
        # Ensure points are sorted by DTE, though target_dtes usually is.
        key_iv_points.sort()
        # Ensure 0-DTE point is present if others are, using closest available if 0-DTE itself failed
        if key_iv_points and key_iv_points[0][0] != 0:
            # If 0-DTE is missing but other points exist, add a 0-DTE point using the shortest-term available IV.
            # This is a simple heuristic.
            log_messages.append(f"  - Adding 0-DTE point using IV from DTE {key_iv_points[0][0]} as proxy.")
            key_iv_points.insert(0, (0, key_iv_points[0][1]))
        elif not key_iv_points: # Still no points
             pass # Already warned by the global st.warning above

    log_messages.append(f"Final Key IV points for {ticker}: {[(p[0], f'{p[1]:.2%}') for p in key_iv_points]}")
    return key_iv_points, log_messages


def calculate_market_implied_risk_free_rate(expiration_date, tickers=['SPY', 'QQQ', 'IWM']):
    """
    Calculates an aggregate market-implied risk-free rate from a basket of liquid ETFs for a given expiration date.
    """
    fmp = FMPClient()
    price_fetcher = PriceDataFetcher()
    all_valid_rates = []
    log_messages = [f"Starting market-implied risk-free rate calculation for expiry {expiration_date.strftime('%Y-%m-%d')}..."]
    
    days_to_exp = (expiration_date - date.today()).days
    T = days_to_exp / 365.0

    if T <= 0:
        log_messages.append("Target expiration date is not in the future. Cannot calculate rate.")
        return None, log_messages

    for ticker in tickers:
        log_messages.append(f"--- Processing {ticker} ---")
        # 1. Get current price
        rt_quote = fmp.realtimequote(ticker)
        if rt_quote is None or rt_quote.empty or 'price' not in rt_quote.columns:
            log_messages.append(f"Could not fetch current price for {ticker}. Skipping.")
            continue
        S_current = rt_quote.price.iloc[0]

        # 2. Get option chain
        option_chain_df = price_fetcher.get_option_data_finviz(ticker, 'o', expiration_date.strftime('%Y-%m-%d'))
        if option_chain_df is None or option_chain_df.empty:
            log_messages.append(f"Could not fetch option chain for {ticker}. Skipping.")
            continue
        
        option_chain_df['Strike'] = pd.to_numeric(option_chain_df['Strike'], errors='coerce')
        option_chain_df.dropna(subset=['Strike'], inplace=True)
        
        # 3. Select near-the-money strikes
        strikes = option_chain_df['Strike'].unique()
        atm_strikes = strikes[np.abs(strikes - S_current) < (S_current * 0.05)] # Within 5% of stock price
        
        if len(atm_strikes) == 0:
            log_messages.append("Could not find any near-the-money strikes. Skipping.")
            continue

        ticker_rates = []
        for K in atm_strikes:
            call_price = _get_market_price_from_finviz_df(option_chain_df, K, 'C')
            put_price = _get_market_price_from_finviz_df(option_chain_df, K, 'P')

            if call_price is not None and put_price is not None:
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

    if all_valid_rates:
        market_rate = np.mean(all_valid_rates)
        log_messages.append(f"--- FINAL ---")
        log_messages.append(f"Overall market-implied risk-free rate: {market_rate:.3%}")
        return market_rate, log_messages
    else:
        log_messages.append("Could not determine market-implied rate from any ticker.")
        return None, log_messages


def parse_earnings_date(earnings_str, today=date.today()):
    """
    Parses Finviz earnings date string. Handles multiple formats:
    - '7/31/2025 4:30:00 PM' (from v=161 export, with explicit year)
    - 'Aug 22/b' or 'Jul 15' (legacy format, infers year)
    """
    if not earnings_str or pd.isna(earnings_str) or earnings_str.strip() == '-':
        return None
        
    from datetime import datetime

    # --- Try parsing formats with an explicit year, like '7/31/2025 ...' or '2025-07-31' ---
    try:
        # We only need the date part, so we split by space and take the first part.
        date_part = earnings_str.split(' ')[0]
        # Common date formats to try
        for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(date_part, fmt).date()
            except ValueError:
                continue
    except (ValueError, IndexError):
        # This format failed, fall through to the next format attempt
        pass

    # --- If above fails, try parsing legacy format 'Aug 22/b' (year is inferred) ---
    try:
        # Clean string: remove '/b', '/a', etc.
        cleaned_str = earnings_str.split('/')[0].strip()
        
        # Parse Month Day
        dt_obj = datetime.strptime(cleaned_str, '%b %d').date()
        
        # Determine year
        if dt_obj.month < today.month or (dt_obj.month == today.month and dt_obj.day < today.day):
            # This earnings date has passed for this year, so it must be next year
            return dt_obj.replace(year=today.year + 1)
        else:
            # This earnings date is for the current year
            return dt_obj.replace(year=today.year)
    except (ValueError, AttributeError):
        # If all parsing attempts fail
        return None


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
            
            # Get ATM straddle price
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
        
        if len(closing_prices) >= 11: # Need 10 trading days for price change
            price_10d_ago = closing_prices[-11]
            price_change_10d_pct = ((S_current - price_10d_ago) / price_10d_ago) * 100
            analysis['price_change_10d_pct'] = price_change_10d_pct
        else:
            analysis['price_change_10d_pct'] = None
        
        # Volatility compression check
        if len(closing_prices) >= 51:
            hv_10d = calculate_historical_volatility(closing_prices, lookback_days=10)
            hv_50d = calculate_historical_volatility(closing_prices, lookback_days=50)
            analysis['hv_10d'] = hv_10d
            analysis['hv_50d'] = hv_50d
            if hv_10d < hv_50d * 0.8: # Threshold for compression
                # NEW: Check if coiling is happening close to an earnings date
                is_coiling_before_earnings = False
                if earnings_date:
                    days_to_earnings = (earnings_date - date.today()).days
                    if 0 < days_to_earnings <= 21: # Define "close" as within 21 days
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

    # 3. IV analysis text (to be displayed)
    analysis['iv_analysis_text'] = "To assess 'IV crush' risk, manually check the IV Rank/Percentile on your brokerage platform. IV Rank is not available here. A high rank (e.g., > 80) means options are expensive and vulnerable to a sharp drop in IV after an event, which can cause losses even if the stock moves as expected."

    # 4. Earnings date analysis (now separate from coiling text)
    if earnings_date and expiration_date:
        if date.today() < earnings_date <= expiration_date:
            analysis['earnings_within_expiry'] = True
            days_to_earnings = (earnings_date - date.today()).days
            analysis['earnings_note'] = f"Upcoming earnings on {earnings_date.strftime('%Y-%m-%d')} ({days_to_earnings} days), which is before expiration. This is a major catalyst."
            # The coiling text is now handled above and is more specific, so no need to append here.
        else:
            analysis['earnings_within_expiry'] = False
            if earnings_date > date.today():
                analysis['earnings_note'] = f"Next earnings date is {earnings_date.strftime('%Y-%m-%d')}, which is after the option's expiration date."

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
    # Heuristics: Volume > Open Interest, high absolute volume, and is OTM.
    otm_calls = calls[calls['Strike'] > S_current]
    otm_puts = puts[puts['Strike'] < S_current]
    
    # Scan OTM calls for UOA
    uoa_candidates_c = otm_calls[(otm_calls['Volume'] > otm_calls['Open Int.']) & (otm_calls['Volume'] > 500)]
    if not uoa_candidates_c.empty:
        # Prioritize where volume is much larger than OI
        uoa_candidates_c['vol_oi_ratio'] = uoa_candidates_c['Volume'] / (uoa_candidates_c['Open Int.'] + 1) # +1 to avoid div by zero
        analysis['uoa_calls'] = uoa_candidates_c.sort_values('vol_oi_ratio', ascending=False).head(3).to_dict('records')

    # Scan OTM puts for UOA
    uoa_candidates_p = otm_puts[(otm_puts['Volume'] > otm_puts['Open Int.']) & (otm_puts['Volume'] > 500)]
    if not uoa_candidates_p.empty:
        uoa_candidates_p['vol_oi_ratio'] = uoa_candidates_p['Volume'] / (uoa_candidates_p['Open Int.'] + 1)
        analysis['uoa_puts'] = uoa_candidates_p.sort_values('vol_oi_ratio', ascending=False).head(3).to_dict('records')

    # --- 3. Open Interest "Walls" ---
    # A wall is a strike with significantly higher OI than its neighbors, typically OTM.
    if not otm_puts.empty and len(otm_puts) > 2:
        put_wall_candidate = otm_puts.loc[otm_puts['Open Int.'].idxmax()]
        # Check if it's significantly larger than the average
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
    `df` should be a pandas DataFrame with 'Open', 'High', 'Low', 'Close', 'Volume' columns,
    sorted with the most recent date at the end.
    """
    # --- Contextual Analysis Setup ---
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    if df is None or not all(col in df.columns for col in required_cols):
        return {"error": f"DataFrame is missing one or more required columns for full analysis: {required_cols}", "context": {}}
    
    if len(df) < 51:
        return {"error": "Not enough historical data for contextual candlestick analysis (need at least 51 periods).", "context": {}}

    df = df.copy() # Avoid SettingWithCopyWarning
    
    # Convert to numeric, coercing errors
    for col in required_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.dropna(subset=required_cols, inplace=True)
    
    # Recalculate length check after cleaning
    if len(df) < 51:
        return {"error": "Not enough valid data points after cleaning.", "context": {}}

    # --- Calculate Indicators for Context ---
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    df['SMA100'] = df['Close'].rolling(window=100).mean()
    df['SMA200'] = df['Close'].rolling(window=200).mean()
        
    df['AvgVol10'] = df['Volume'].rolling(window=10).mean()
    
    if len(df) < 4:
        return {"error": "Not enough data after calculating indicators.", "context": {}}

    # --- Establish Market Context ---
    last_row = df.iloc[-1]
    C0 = last_row['Close']
    SMA50_val = last_row['SMA50']
    SMA200_val = last_row.get('SMA200')

    primary_trend = "Undetermined"
    if pd.notna(SMA200_val):
        primary_trend = "Uptrend" if C0 > SMA200_val else "Downtrend"

    secondary_trend = "Undetermined"
    if pd.notna(SMA50_val):
        secondary_trend = "Uptrend" if C0 > SMA50_val else "Downtrend"

    sma50_vs_200 = "N/A"
    if pd.notna(SMA50_val) and pd.notna(SMA200_val):
        sma50_vs_200 = "Golden Cross Active" if SMA50_val > SMA200_val else "Death Cross Active"

    market_context = {
        "primary_trend": primary_trend,
        "secondary_trend": secondary_trend,
        "price_vs_sma50": "Above" if secondary_trend == "Uptrend" else "Below",
        "price_vs_sma200": "Above" if primary_trend == "Uptrend" else ("Below" if primary_trend == "Downtrend" else "N/A"),
        "sma50_vs_sma200": sma50_vs_200
    }

    # --- Pattern Recognition Setup ---
    max_lookback = min(4, len(df))
    get_iloc = lambda col, i: df[col].iloc[-1-i]
    O, H, L, C, V, AvgVol10_series = ({i: get_iloc(col, i) for i in range(max_lookback)} for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'AvgVol10'])

    def Body(x): return abs(O[x] - C[x])
    def UpperShadow(x): return H[x] - max(O[x], C[x])
    def LowerShadow(x): return min(O[x], C[x]) - L[x]

    found_patterns = []

    # --- Define Contexts for Reversals ---
    is_downtrend_context = secondary_trend == "Downtrend" or (C[0] < C[1] and C[1] < C[2])
    is_uptrend_context = secondary_trend == "Uptrend" or (C[0] > C[1] and C[1] > C[2])

    # Helper to build interpretation string
    def build_interpretation(base_interp, vol_idx, name):
        is_high_vol = V[vol_idx] > AvgVol10_series[vol_idx] * 1.1
        vol_msg = "on high volume, strengthening the signal." if is_high_vol else "on average volume, so confirmation is crucial."
        strength = "Strong" if is_high_vol and "Engulfing" in name else ("Weak" if not is_high_vol else "Moderate")
        return f"{base_interp} It appeared {vol_msg}", strength

    # --- I. Bullish Reversal Patterns ---
    if is_downtrend_context:
        # 1. Hammer
        if 0 in O and LowerShadow(0) > (2 * Body(0)) and UpperShadow(0) < (0.1 * (H[0] - L[0])):
            interp, strength = build_interpretation("Sellers were rejected after a decline.", 0, "Hammer")
            found_patterns.append({"name": "Hammer (Bullish Reversal)", "interpretation": interp, "confirmation": f"A trade above the Hammer's high (${H[0]:.2f}).", "strength": strength})
        # 2. Bullish Engulfing
        if 1 in O and C[1] < O[1] and C[0] > O[0] and C[0] > O[1] and O[0] < C[1]:
            interp, strength = build_interpretation("A powerful momentum shift where buyers overwhelmed sellers.", 0, "Bullish Engulfing")
            found_patterns.append({"name": "Bullish Engulfing (Bullish Reversal)", "interpretation": interp, "confirmation": f"A trade above the engulfing candle's high (${H[0]:.2f}).", "strength": strength})
        # 3. Piercing Line
        if 1 in O and C[1] < O[1] and O[0] < L[1] and C[0] > ((O[1] + C[1]) / 2) and C[0] < O[1]:
            interp, strength = build_interpretation("A strong rejection of a gap down, showing buying interest.", 0, "Piercing Line")
            found_patterns.append({"name": "Piercing Line (Bullish Reversal)", "interpretation": interp, "confirmation": f"A trade above the piercing candle's high (${H[0]:.2f}).", "strength": strength})
        # 4. Morning Star
        if 2 in O and C[2] < O[2] and Body(2) > 0 and Body(1) < (0.2 * Body(2)) and O[1] < C[2] and C[0] > O[0] and C[0] > ((O[2] + C[2]) / 2):
            interp, strength = build_interpretation("Indecision (the 'star') after a decline was decisively reversed by buyers.", 0, "Morning Star")
            found_patterns.append({"name": "Morning Star (Bullish Reversal)", "interpretation": interp, "confirmation": f"A trade above the third candle's high (${H[0]:.2f}).", "strength": strength})

    # --- II. Bearish Reversal Patterns ---
    if is_uptrend_context:
        # 1. Shooting Star
        if 0 in O and UpperShadow(0) > (2 * Body(0)) and LowerShadow(0) < (0.1 * (H[0] - L[0])):
            interp, strength = build_interpretation("Buyers were rejected after a rally.", 0, "Shooting Star")
            found_patterns.append({"name": "Shooting Star (Bearish Reversal)", "interpretation": interp, "confirmation": f"A trade below the Shooting Star's low (${L[0]:.2f}).", "strength": strength})
        # 2. Bearish Engulfing
        if 1 in O and C[1] > O[1] and C[0] < O[0] and C[0] < O[1] and O[0] > C[1]:
            interp, strength = build_interpretation("A powerful momentum shift where sellers overwhelmed buyers.", 0, "Bearish Engulfing")
            found_patterns.append({"name": "Bearish Engulfing (Bearish Reversal)", "interpretation": interp, "confirmation": f"A trade below the engulfing candle's low (${L[0]:.2f}).", "strength": strength})
        # 3. Dark Cloud Cover
        if 1 in O and C[1] > O[1] and O[0] > H[1] and C[0] < ((O[1] + C[1]) / 2) and C[0] > O[1]:
            interp, strength = build_interpretation("Failure to hold a gap up shows buying exhaustion.", 0, "Dark Cloud Cover")
            found_patterns.append({"name": "Dark Cloud Cover (Bearish Reversal)", "interpretation": interp, "confirmation": f"A trade below the bearish candle's low (${L[0]:.2f}).", "strength": strength})
        # 4. Evening Star
        if 2 in O and C[2] > O[2] and Body(2) > 0 and Body(1) < (0.2 * Body(2)) and O[1] > C[2] and C[0] < O[0] and C[0] < ((O[2] + C[2]) / 2):
            interp, strength = build_interpretation("Indecision (the 'star') after a rally was decisively reversed by sellers.", 0, "Evening Star")
            found_patterns.append({"name": "Evening Star (Bearish Reversal)", "interpretation": interp, "confirmation": f"A trade below the third candle's low (${L[0]:.2f}).", "strength": strength})

    # --- III. Indecision Patterns (can appear in any context) ---
    if 0 in O and (H[0] - L[0] > 0):
        # 1. Doji
        if Body(0) < (0.05 * (H[0] - L[0])):
            context_msg = "after a strong trend, suggesting momentum may be fading." if is_uptrend_context or is_downtrend_context else "in a consolidating market."
            found_patterns.append({"name": "Doji (Indecision)", "interpretation": f"A candle of total indecision appeared {context_msg}", "confirmation": f"Wait for a breakout above the high (${H[0]:.2f}) or below the low (${L[0]:.2f}).", "strength": "Neutral"})
        # 2. Spinning Top
        elif Body(0) < (0.4 * (H[0] - L[0])):
            context_msg = "after a strong trend, suggesting a potential reversal." if is_uptrend_context or is_downtrend_context else "indicating continued uncertainty."
            found_patterns.append({"name": "Spinning Top (Indecision)", "interpretation": f"A battle between bulls and bears with no clear winner. Appeared {context_msg}", "confirmation": f"Wait for a breakout above the high (${H[0]:.2f}) or below the low (${L[0]:.2f}).", "strength": "Neutral"})
            
    return {"patterns": found_patterns, "context": market_context, "plot_df": df}


def generate_holistic_conclusion(synthesis_data):
    """
    Synthesizes all analysis sections into a holistic conclusion and a directional bias.
    """
    sentiments = {'bullish': 0, 'bearish': 0, 'neutral': 0}
    components = []
    bullish_drivers = []
    bearish_drivers = []

    def process_component(name, data):
        if not data: return
        
        # Add all components to the summary list for display
        components.append(f"<li><b>{name}:</b> {data['summary']}</li>")
        
        # Only factor in directional sentiments for the bias score
        sentiment = data.get('sentiment')
        if sentiment in ['bullish', 'bearish', 'neutral']:
            sentiments[sentiment] += data.get('weight', 1)
            if sentiment == 'bullish':
                bullish_drivers.append(name.lower())
            elif sentiment == 'bearish':
                bearish_drivers.append(name.lower())

    analysis_map = {
        'trend': "Trend", 'candlestick': "Candlesticks", 'parity': "Put-Call Parity",
        'volume_oi': "Volume/OI", 'undervalued': "Valuation Model",
        'earnings': "Upcoming Events", 'movement': "Price Action & Volatility"
    }
    for key, name in analysis_map.items():
        if key in synthesis_data:
            process_component(name, synthesis_data[key])

    # Determine overall bias
    bull_score = sentiments['bullish']
    bear_score = sentiments['bearish']

    final_bias = "Neutral"
    if bull_score > bear_score + 1: final_bias = "Bullish"
    elif bear_score > bull_score + 1: final_bias = "Bearish"
    elif bull_score > bear_score: final_bias = "Slightly Bullish"
    elif bear_score > bull_score: final_bias = "Slightly Bearish"
    
    # --- Generate Conclusion Text ---
    conclusion_html = "<h5>Summary of Findings:</h5><ul>" + "".join(components) + "</ul>"
    
    contradiction = (bull_score > 0 and bear_score > 0)
    
    conclusion_html += "<h5>Holistic Conclusion:</h5>"
    
    # 1. Main Bias Paragraph
    bias_paragraph = f"<p>The overall directional bias is <b>{final_bias}</b>. "
    if final_bias in ["Bullish", "Slightly Bullish"]:
        bias_paragraph += f"This is primarily supported by positive signals from the <b>{', '.join(bullish_drivers)}</b> analysis. "
        if contradiction:
            bias_paragraph += f"However, caution is warranted due to conflicting bearish indicators from <b>{', '.join(bearish_drivers)}</b>. A defined-risk bullish strategy is recommended. "
    elif final_bias in ["Bearish", "Slightly Bearish"]:
        bias_paragraph += f"This is driven by negative signals from the <b>{', '.join(bearish_drivers)}</b> analysis. "
        if contradiction:
            bias_paragraph += f"However, the presence of bullish signals from <b>{', '.join(bullish_drivers)}</b> suggests potential for a reversal, so a defined-risk bearish strategy is advised. "
    else: # Neutral
        if contradiction:
            bias_paragraph += "The analysis reveals a mix of bullish and bearish signals, leading to significant uncertainty. "
        else:
            bias_paragraph += "There are no strong directional signals from the core indicators. The stock appears to be in a consolidation phase. "
        bias_paragraph += "A range-bound or volatility-based strategy may be most appropriate. "
    
    conclusion_html += bias_paragraph + "</p>"

    # 2. Volatility and Event Context Paragraph
    context_paragraph = "<p><b>Context for Strategy Selection:</b><ul>"
    context_points = []
    
    if 'iv_hv' in synthesis_data and synthesis_data['iv_hv'].get('summary'):
        context_points.append(synthesis_data['iv_hv']['summary'])
    if 'movement' in synthesis_data and synthesis_data['movement'].get('summary'):
         context_points.append(synthesis_data['movement']['summary'])
    if 'earnings' in synthesis_data and "major catalyst" in synthesis_data['earnings'].get('summary', ''):
        context_points.append(synthesis_data['earnings']['summary'])

    if context_points:
        for point in context_points:
            context_paragraph += f"<li>{point}</li>"
        context_paragraph += "</ul></p>"
        conclusion_html += context_paragraph
    # If no context points, don't add the section.

    return conclusion_html, final_bias


def display_strategy_order_button(strategy_name, ticker, expiration_date, legs_data, key_suffix, is_credit_spread=False):
    trader = get_ib_trader()
    st.markdown("---") # Visual separator for each strategy suggestion
    
    # Display the legs of the strategy
    leg_descriptions = []
    for leg in legs_data:
        leg_descriptions.append(f"{leg['action']} 1x {leg['strike']:.2f} {leg['right']}")
    st.markdown(f"**Strategy Legs:** {', '.join(leg_descriptions)}")
    
    # Order placement UI
    cols = st.columns([2, 1])
    with cols[0]:
        trade_quantity_input = st.number_input("Number of Spreads", min_value=1, value=1, step=1, key=f"qty_strat_{key_suffix}")
    with cols[1]:
        st.write("") # Vertical alignment
        st.write("") # Vertical alignment
        if st.button("Place MKT Order", key=f"btn_strat_{key_suffix}"):
            with st.spinner(f"Sending {strategy_name} order to broker..."):
                try:
                    # Enrich legs_data with what the order function needs
                    enriched_legs = []
                    for leg in legs_data:
                        enriched_leg = leg.copy()
                        enriched_leg['expiry_date'] = expiration_date.strftime('%Y%m%d')
                        enriched_leg['quantity'] = 1 # The ratio of legs within the spread is 1
                        enriched_legs.append(enriched_leg)
                    
                    # For credit spreads, the order size must be negative (to SELL the spread)
                    order_size = -trade_quantity_input if is_credit_spread else trade_quantity_input

                    st.info(f"DEBUG: Calling trader.place_strategy_order for {trade_quantity_input} {strategy_name} on {ticker}.")
                    st.info(f"DEBUG: Legs data: {json.dumps(enriched_legs, indent=2, cls=NpEncoder)}")
                    st.info(f"DEBUG: is_credit_spread={is_credit_spread}, calculated order_size={order_size}")

                    # The `place_strategy_order` function will return quickly after submitting the order.
                    # It does not wait for the order to be filled.
                    trade = trader.place_strategy_order(
                        symbol=ticker,
                        legs_data=enriched_legs,
                        size=order_size,
                        order_type='MKT'
                    )

                    st.info(f"DEBUG: `place_strategy_order` returned. Trade object: {trade!r}")
                    st.info(f"DEBUG: Order details: {trade.order}")

                    st.success(f"Order for {trade_quantity_input} {strategy_name} sent to the broker.")
                    st.balloons()
                except Exception as e:
                    import traceback
                    st.error(f"Order placement failed: {e}")
                    st.error(f"DEBUG: Traceback:\n{traceback.format_exc()}")


def display_screener_results(screener_data):
    """Renders the results from the option screener using cached data."""
    if screener_data.get("status") == "error":
        st.error(screener_data.get("message", "An unknown error occurred in the screener."))
        return

    # Unpack data from the results dictionary
    ticker = screener_data['ticker']
    S_current = screener_data['S_current']
    expiration_date = screener_data['expiration_date']
    iv_logs = screener_data['iv_logs']
    iv_available = screener_data['iv_available']
    synthesis_data = screener_data['synthesis_data']
    final_conclusion_html = screener_data['final_conclusion_html']
    final_bias = screener_data['final_bias']
    iv_high = screener_data['iv_high']
    iv_low = screener_data['iv_low']
    strikes = screener_data['strikes']
    candlestick_analysis = screener_data['candlestick_analysis']
    volume_oi_analysis = screener_data['volume_oi_analysis']
    movement_analysis_results = screener_data['movement_analysis_results']
    results_df = screener_data.get('results_df') # Might not exist if no options are undervalued

    st.header("Option Screener Results")
    st.info(f"Current price for {ticker.upper()}: {display_currency(S_current)}")

    with st.expander("IV Fetch Log"):
        for msg in iv_logs:
            st.caption(msg)
    
    if not iv_available:
        st.warning("Could not fetch Implied Volatility. Using Historical Volatility for model pricing. IV-based strategy suggestions are disabled.")

    # --- Display Final Conclusive Summary ---
    st.header(f"Holistic Analysis for {ticker.upper()}")
    final_bias_color = "green" if "Bullish" in final_bias else ("red" if "Bearish" in final_bias else "orange")
    st.markdown(f"### Final Conclusion: <span style='color:{final_bias_color};'>{final_bias}</span>", unsafe_allow_html=True)
    st.markdown(final_conclusion_html, unsafe_allow_html=True)

    # --- Strategy Suggestions ---
    st.subheader("Strategy Suggestions")
    atm_strike = strikes[np.argmin(np.abs(strikes - S_current))]
    otm_calls = strikes[strikes > S_current]
    itm_calls = strikes[strikes < S_current]
    otm_puts = strikes[strikes < S_current]
    itm_puts = strikes[strikes > S_current]

    if final_bias == "Neutral":
        st.markdown("The overall bias is neutral. Consider range-bound or volatility-based strategies.")
        if iv_high:
            st.success("**Recommended Strategy Type: Sell Premium (High IV).**")
            st.markdown("- **Iron Condor:** A defined-risk strategy that profits if the stock stays between two strike prices. Best if you expect low volatility.")
            if len(otm_puts) >= 2 and len(otm_calls) >= 2:
                legs = [
                    {'action': 'SELL', 'strike': otm_puts[-1], 'right': 'P'},
                    {'action': 'BUY', 'strike': otm_puts[-2], 'right': 'P'},
                    {'action': 'SELL', 'strike': otm_calls[0], 'right': 'C'},
                    {'action': 'BUY', 'strike': otm_calls[1], 'right': 'C'}
                ]
                display_strategy_order_button("Iron Condor", ticker, expiration_date, legs, "iron_condor", is_credit_spread=True)
            else:
                st.warning("Not enough OTM strikes to construct an Iron Condor.")
        elif iv_low:
            st.warning("**Recommended Strategy Type: Buy Premium (Low IV).**")
            st.markdown("- **Long Straddle:** A strategy that profits from a large move in either direction. Best when you expect a sharp price move but are unsure of the direction.")
            legs = [
                {'action': 'BUY', 'strike': atm_strike, 'right': 'C'},
                {'action': 'BUY', 'strike': atm_strike, 'right': 'P'}
            ]
            display_strategy_order_button("Long Straddle", ticker, expiration_date, legs, "long_straddle", is_credit_spread=False)
        else:
            st.info("IV is neutral. No strong edge for buying or selling premium. Consider waiting for a clearer signal.")
    else: # Directional bias
        if "Bullish" in final_bias:
            if iv_high:
                st.success("**Recommended Strategy Type: Bullish Credit Spread (Sell Puts).**")
                st.markdown("This strategy benefits from a rising stock price, time decay, and a potential drop in IV. It has a high probability of profit but limited gain.")
                if len(otm_puts) >= 2:
                    legs = [
                        {'action': 'SELL', 'strike': otm_puts[-1], 'right': 'P'},
                        {'action': 'BUY', 'strike': otm_puts[-2], 'right': 'P'}
                    ]
                    display_strategy_order_button("Bull Put Spread", ticker, expiration_date, legs, "bull_put", is_credit_spread=True)
                else:
                    st.warning("Not enough OTM put strikes to construct a spread.")
            else: # iv_low or neutral
                st.warning("**Recommended Strategy Type: Bullish Debit Spread (Buy Calls).**")
                st.markdown("This strategy profits from a rising stock price and benefits from low IV. It has a lower cost basis than buying a call outright.")
                if len(itm_calls) >= 1 and len(otm_calls) >= 1:
                    legs = [
                        {'action': 'BUY', 'strike': itm_calls[-1], 'right': 'C'},
                        {'action': 'SELL', 'strike': otm_calls[0], 'right': 'C'}
                    ]
                    display_strategy_order_button("Bull Call Spread", ticker, expiration_date, legs, "bull_call", is_credit_spread=False)
                else:
                    st.warning("Not enough ITM/OTM call strikes to construct a spread.")
        elif "Bearish" in final_bias:
            if iv_high:
                st.success("**Recommended Strategy Type: Bearish Credit Spread (Sell Calls).**")
                st.markdown("This strategy benefits from a falling stock price, time decay, and a potential drop in IV.")
                if len(otm_calls) >= 2:
                    legs = [
                        {'action': 'SELL', 'strike': otm_calls[0], 'right': 'C'},
                        {'action': 'BUY', 'strike': otm_calls[1], 'right': 'C'}
                    ]
                    display_strategy_order_button("Bear Call Spread", ticker, expiration_date, legs, "bear_call", is_credit_spread=True)
                else:
                    st.warning("Not enough OTM call strikes to construct a spread.")
            else: # iv_low or neutral
                st.warning("**Recommended Strategy Type: Bearish Debit Spread (Buy Puts).**")
                st.markdown("This strategy profits from a falling stock price and benefits from low IV.")
                if len(itm_puts) >= 1 and len(otm_puts) >= 1:
                    legs = [
                        {'action': 'BUY', 'strike': itm_puts[0], 'right': 'P'},
                        {'action': 'SELL', 'strike': otm_puts[-1], 'right': 'P'}
                    ]
                    display_strategy_order_button("Bear Put Spread", ticker, expiration_date, legs, "bear_put", is_credit_spread=False)
                else:
                    st.warning("Not enough ITM/OTM put strikes to construct a spread.")
    
    # --- Display Detailed Analysis Sections ---
    with st.expander("Show Detailed Analysis Breakdown", expanded=False):
        # 1. Trend & Candlesticks
        st.subheader("1. Price Trend & Candlestick Analysis")
        if candlestick_analysis and "error" not in candlestick_analysis:
            plot_df = candlestick_analysis.get("plot_df")
            if plot_df is not None and not plot_df.empty:
                plot_df_recent = plot_df.tail(250)
                fig = go.Figure(data=[go.Candlestick(x=plot_df_recent.index, open=plot_df_recent['Open'], high=plot_df_recent['High'], low=plot_df_recent['Low'], close=plot_df_recent['Close'], name='Price')])
                if 'SMA20' in plot_df_recent.columns and not plot_df_recent['SMA20'].isnull().all(): fig.add_trace(go.Scatter(x=plot_df_recent.index, y=plot_df_recent['SMA20'], mode='lines', name='SMA 20', line=dict(color='blue', width=1)))
                if 'SMA50' in plot_df_recent.columns and not plot_df_recent['SMA50'].isnull().all(): fig.add_trace(go.Scatter(x=plot_df_recent.index, y=plot_df_recent['SMA50'], mode='lines', name='SMA 50', line=dict(color='orange', width=1.5)))
                if 'SMA100' in plot_df_recent.columns and not plot_df_recent['SMA100'].isnull().all(): fig.add_trace(go.Scatter(x=plot_df_recent.index, y=plot_df_recent['SMA100'], mode='lines', name='SMA 100', line=dict(color='red', width=1.5)))
                if 'SMA200' in plot_df_recent.columns and not plot_df_recent['SMA200'].isnull().all(): fig.add_trace(go.Scatter(x=plot_df_recent.index, y=plot_df_recent['SMA200'], mode='lines', name='SMA 200', line=dict(color='purple', width=2)))
                fig.update_layout(title=f'{ticker.upper()} Price Chart', yaxis_title='Price', xaxis_rangeslider_visible=False, height=400, margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig, use_container_width=True)
            if not candlestick_analysis.get("patterns"): st.markdown("No major candlestick patterns identified.")
            else:
                for pattern in candlestick_analysis["patterns"]: st.markdown(f"- **{pattern['name']}** (Strength: {pattern.get('strength', 'N/A')}): {pattern['interpretation']}")
            st.info(f"**Conclusion:** {synthesis_data.get('trend', {}).get('summary', 'Trend data unavailable.')} {synthesis_data.get('candlestick', {}).get('summary', '')}")
        else:
            st.warning(candlestick_analysis.get("error", "Could not perform candlestick analysis."))

        # 2. Sentiment Analysis
        st.subheader("2. Sentiment Analysis (Volume, OI & Parity)")
        if 'parity' in synthesis_data: st.markdown(synthesis_data['parity']['summary'])
        else: st.markdown("Put-Call Parity data not available.")
        if volume_oi_analysis and not volume_oi_analysis.get("error"):
            uoa_c = volume_oi_analysis.get('uoa_calls', [])
            uoa_p = volume_oi_analysis.get('uoa_puts', [])
            if uoa_c or uoa_p:
                st.markdown("**Unusual Option Activity:**")
                for item in uoa_c: st.markdown(f"- Bullish UOA: K ${item['Strike']:.2f} Call (Vol: {int(item['Volume'])}, OI: {int(item['Open Int.'])})")
                for item in uoa_p: st.markdown(f"- Bearish UOA: K ${item['Strike']:.2f} Put (Vol: {int(item['Volume'])}, OI: {int(item['Open Int.'])})")
            
            put_wall_disp = volume_oi_analysis.get('oi_put_wall')
            call_wall_disp = volume_oi_analysis.get('oi_call_wall')
            if put_wall_disp or call_wall_disp:
                st.markdown("**Open Interest Walls:**")
                if put_wall_disp: st.markdown(f"- Put Wall (Support): K ${put_wall_disp['Strike']:.2f} (OI: {int(put_wall_disp['Open Int.'])})")
                if call_wall_disp: st.markdown(f"- Call Wall (Resistance): K ${call_wall_disp['Strike']:.2f} (OI: {int(call_wall_disp['Open Int.'])})")
        st.info(f"**Conclusion:** {synthesis_data.get('volume_oi', {}).get('summary', 'Volume/OI data not conclusive.')}")
        
        # 3. Volatility Analysis
        st.subheader("3. Volatility Analysis (IV vs HV)")
        if movement_analysis_results:
            exp_move_pct = movement_analysis_results.get('expected_move_pct')
            if exp_move_pct is not None: st.markdown(f"**Market-Implied Move:** The options market is pricing in a **{exp_move_pct:.2f}%** move by expiration.")
            vol_comp = movement_analysis_results.get('vol_compression_text')
            if vol_comp: st.markdown(f"**Price Action:** {vol_comp}")
        st.info(f"**Conclusion:** {synthesis_data.get('iv_hv', {}).get('summary', 'IV/HV comparison not available.')}")
        
        # 4. Quantitative Analysis
        st.subheader("4. Quantitative Analysis (Undervalued Options)")
        if results_df is not None and not results_df.empty:
            st.info(f"**Conclusion:** {synthesis_data.get('undervalued', {}).get('summary', 'Valuation model did not provide a signal.')}")
            st.dataframe(results_df.style.format({"Strike": "{:.2f}", "Market Price": "${:.2f}", "Model Price": "${:.2f}", "Undervalued By ($)": "${:.2f}", "Undervalued By (%)": "{:.2f}%"}))
        else:
            st.markdown("No options met the undervaluation criteria.")
            st.info(f"**Conclusion:** {synthesis_data.get('undervalued', {}).get('summary', 'Valuation model did not provide a signal.')}")


def run_option_screener():
    """
    Performs all calculations for the option screener and returns a dictionary of results for display.
    This function should not contain any Streamlit display calls (e.g., st.write).
    """
    ticker = st.session_state.ss_screener_ticker
    expiration_date = st.session_state.ss_screener_exp_date

    if not ticker:
        return {"status": "error", "message": "Please provide a ticker for the screener."}

    fmp = FMPClient()
    price_fetcher = PriceDataFetcher()

    # 1. Fetch current stock price
    rt_quote = fmp.realtimequote(ticker)
    if rt_quote is None or rt_quote.empty or 'price' not in rt_quote.columns:
        return {"status": "error", "message": f"Could not fetch current price for {ticker}."}
    S_current = rt_quote.price.iloc[0]
    if S_current is None:
        return {"status": "error", "message": f"Current price for {ticker} is None."}

    # 2. Fetch option chain
    expiration_date_str = expiration_date.strftime('%Y-%m-%d')
    option_chain_df = price_fetcher.get_option_data_finviz(ticker, 'o', expiration_date_str)
    if option_chain_df is None or option_chain_df.empty:
        return {"status": "error", "message": f"Could not fetch option chain for {ticker} on {expiration_date_str}."}
    
    option_chain_df['Strike'] = pd.to_numeric(option_chain_df['Strike'], errors='coerce')
    option_chain_df.dropna(subset=['Strike'], inplace=True)
    option_chain_df.sort_values('Strike', inplace=True)
    
    if option_chain_df.empty:
        return {"status": "error", "message": f"No options found for {ticker} on {expiration_date_str}."}

    # 3. Select strikes
    strikes = option_chain_df['Strike'].unique()
    otm_strikes_for_call = strikes[strikes > S_current][:6]
    itm_strikes_for_call = strikes[strikes < S_current][-6:]
    selected_strikes = np.concatenate([itm_strikes_for_call, otm_strikes_for_call])
    
    if len(selected_strikes) == 0:
        return {"status": "error", "message": "Could not find any ITM/OTM strikes to analyze."}

    # 4. Prepare for pricing
    r_current = st.session_state.ss_current_risk_free_rate
    lookback_days_hv = 20
    historical_prices_df = price_fetcher.get_price_data([ticker], method="td_data", back_day=350) 
    hv_current = None
    if historical_prices_df is not None and not historical_prices_df.empty and 'Close' in historical_prices_df.columns:
        closing_prices = historical_prices_df['Close'].tolist()
        if len(closing_prices) >= 2:
            hv_current = calculate_historical_volatility(closing_prices, lookback_days=lookback_days_hv)
    
    key_vols_iv, iv_logs = fetch_iv_term_structure(ticker, price_fetcher, fmp)
    iv_available = bool(key_vols_iv)
    
    if not iv_available:
        if hv_current:
            key_vols_iv = [(0, hv_current)]
        # else, generate_forward_vol_structure will use its default.
    
    stock_details = price_fetcher.get_stock_details_finviz(ticker)
    div_current = stock_details.get('dividend_yield', 0.0)
    earnings_date_str = stock_details.get('earnings_date')
    earnings_date = parse_earnings_date(earnings_date_str)

    movement_analysis_results = analyze_high_movement_expectation(S_current, option_chain_df, historical_prices_df, earnings_date=earnings_date, expiration_date=expiration_date)
    volume_oi_analysis = analyze_volume_and_oi_signals(option_chain_df, S_current)
    candlestick_analysis = analyze_candlestick_patterns(historical_prices_df)

    days_to_exp = (expiration_date - date.today()).days
    if days_to_exp < 0:
        return {"status": "error", "message": "Expiration date is in the past."}
    
    vol_term_structure = generate_forward_vol_structure(days_to_exp, key_vols_iv)

    # 5. Loop and price
    results = []
    parity_data = []
    progress_bar = st.progress(0)
    for i, K in enumerate(selected_strikes):
        call_market_price = _get_market_price_from_finviz_df(option_chain_df, K, 'C')
        put_market_price = _get_market_price_from_finviz_df(option_chain_df, K, 'P')
        if call_market_price is not None and put_market_price is not None:
            T = days_to_exp / 365.0
            parity_diff = (call_market_price - put_market_price) - (S_current - K * np.exp(-r_current * T))
            parity_data.append({"Strike": K, "Parity Difference": parity_diff})

        for option_type_to_check in ['call', 'put']:
            market_price = call_market_price if option_type_to_check == 'call' else put_market_price
            if market_price is None: continue
            model_price, _, _, _ = universal_binomial_pricer(
                S=S_current, K=K, expiration_date=expiration_date, r_input=r_current,
                sigma_input=vol_term_structure, model='jarrow_rudd', option_type=option_type_to_check,
                exercise_type='american', div=div_current, historical_vol=hv_current
            )
            if model_price > market_price:
                diff = model_price - market_price
                diff_pct = (diff / market_price) * 100 if market_price > 0 else float('inf')
                results.append({
                    "Strike": K, "Type": option_type_to_check.capitalize(), "Market Price": market_price,
                    "Model Price": model_price, "Undervalued By ($)": diff, "Undervalued By (%)": diff_pct,
                    "Moneyness": "ITM" if (option_type_to_check == 'call' and K < S_current) or (option_type_to_check == 'put' and K > S_current) else "OTM"
                })
        progress_bar.progress((i + 1) / len(selected_strikes))
    progress_bar.empty()

    # 6. Synthesize results
    synthesis_data = {}
    spot_iv = key_vols_iv[0][1] if key_vols_iv and key_vols_iv[0][0] == 0 else (key_vols_iv[0][1] if key_vols_iv else None)
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
        synthesis_data['trend'] = {'sentiment': trend_sentiment, 'weight': 1.5, 'summary': f"The primary trend is **{primary_trend}** (vs 200d MA) and the secondary trend is **{secondary_trend}** (vs 50d MA)."}
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
    results_df = None
    if results:
        results_df = pd.DataFrame(results).sort_values("Undervalued By (%)", ascending=False)
        top_result = results_df.iloc[0]
        undervalued_sentiment = 'bullish' if top_result['Type'] == 'Call' else 'bearish'
        undervalued_summary = f"The quantitative model's top pick is an undervalued **{top_result['Type']}** at K ${top_result['Strike']:.2f}, suggesting a **{undervalued_sentiment}** bias."
        synthesis_data['undervalued'] = {'sentiment': undervalued_sentiment, 'summary': undervalued_summary}
    else:
        synthesis_data['undervalued'] = {'sentiment': 'neutral', 'summary': 'The model found no clearly undervalued options.'}

    final_conclusion_html, final_bias = generate_holistic_conclusion(synthesis_data)

    return {
        "status": "success", "ticker": ticker, "S_current": S_current, "expiration_date": expiration_date,
        "iv_logs": iv_logs, "iv_available": iv_available, "synthesis_data": synthesis_data,
        "final_conclusion_html": final_conclusion_html, "final_bias": final_bias, "iv_high": iv_high,
        "iv_low": iv_low, "strikes": strikes, "candlestick_analysis": candlestick_analysis,
        "volume_oi_analysis": volume_oi_analysis, "movement_analysis_results": movement_analysis_results,
        "results_df": results_df,
    }


def calculate_strategy_analysis(strategy_data, r_current, key_vols_iv, fmp_client, price_fetcher):
    """
    Performs analysis calculations for a multi-leg strategy and returns a dictionary of results.
    """
    import traceback
    strategy_ticker = strategy_data.get("ticker", "N/A")
    legs = strategy_data.get("legs", [])
    
    try:
        # --- 1. Fetch Common Market Data ---
        rt_quote_strat = fmp_client.realtimequote(strategy_ticker)
        if rt_quote_strat is None or rt_quote_strat.empty or 'price' not in rt_quote_strat.columns:
            raise ValueError(f"Could not fetch valid current price data for underlying {strategy_ticker.upper()}.")
        S_current_strat = rt_quote_strat.price.iloc[0]
        if S_current_strat is None:
            raise ValueError(f"Current price for underlying {strategy_ticker.upper()} is None.")

        lookback_days_hv_strat = 20
        historical_prices_df_strat = price_fetcher.get_price_data([strategy_ticker], method="td_data", back_day=lookback_days_hv_strat + 10)
        hv_current_strat, hv_warning = None, None
        if historical_prices_df_strat is not None and not historical_prices_df_strat.empty and 'Close' in historical_prices_df_strat.columns:
            closing_prices_strat = historical_prices_df_strat['Close'].tolist()
            if len(closing_prices_strat) >= 2:
                hv_current_strat = calculate_historical_volatility(closing_prices_strat, lookback_days=lookback_days_hv_strat)
            else:
                hv_warning = f"Not enough historical price data points ({len(closing_prices_strat)}) for {strategy_ticker.upper()} to calculate HV."
        else:
            hv_warning = f"Could not fetch sufficient historical prices for {strategy_ticker.upper()} to calculate HV."

        fetched_div_yield_strat = price_fetcher.get_stock_details_finviz(strategy_ticker)
        div_warning = None
        if not fetched_div_yield_strat:
            div_warning = f"Could not fetch stock details for {strategy_ticker} from Finviz. Using default 0.00% for dividend yield."
        
        div_current_strat_to_use = fetched_div_yield_strat.get('dividend_yield', 0.0)

        # --- 2. Analyze Each Leg and Aggregate ---
        total_strategy_open_cost = strategy_data.get("strategy_open_price", 0.0)
        total_strategy_current_model_value = 0.0
        total_strategy_current_market_value = 0.0
        total_strategy_delta, total_strategy_gamma, total_strategy_vega, total_strategy_theta_annual = 0.0, 0.0, 0.0, 0.0
        total_net_benefit_from_early_exercise = 0.0
        individual_leg_analysis_results = []
        any_leg_market_price_missing = False
        has_any_leg_specific_alerts = False

        for leg_idx, leg_obj in enumerate(legs):
            if not isinstance(leg_obj, OptionLeg):
                individual_leg_analysis_results.append({"description": f"Leg {leg_idx+1}: Invalid data format (not an OptionLeg object)", "status": "error"})
                continue

            direction_multiplier = -1 if leg_obj.buy_sell == 'sell' else 1
            days_to_exp_leg = (leg_obj.expiration_date - date.today()).days

            current_leg_price_val, leg_greeks_val, leg_model_alerts_val, leg_early_exercise_premium = 0.0, {}, [], 0.0
            
            if days_to_exp_leg < 0:
                current_leg_price_val = max(0, S_current_strat - leg_obj.strike_price if leg_obj.option_type == 'call' else leg_obj.strike_price - S_current_strat)
                leg_greeks_val = {'delta': 1.0 if S_current_strat > leg_obj.strike_price else -1.0, 'gamma': 0, 'theta': 0, 'vega': 0} # Simplified
                leg_model_alerts_val.append("Leg has expired.")
            else:
                vol_term_structure_leg = generate_forward_vol_structure(days_to_exp_leg, key_vols_iv)
                current_leg_price_val, leg_greeks_val, leg_model_alerts_val, leg_early_exercise_premium = universal_binomial_pricer(
                    S=S_current_strat, K=leg_obj.strike_price, expiration_date=leg_obj.expiration_date, r_input=r_current,
                    sigma_input=vol_term_structure_leg, model=strategy_data.get('model', 'jarrow_rudd'),
                    option_type=leg_obj.option_type, exercise_type=strategy_data.get('exercise_type', 'american'),
                    div=div_current_strat_to_use, historical_vol=hv_current_strat
                )
                # Vega for leg
                vega_bump = 0.01
                bumped_key_vols_iv_leg = [(d, v + vega_bump) for d, v in key_vols_iv]
                bumped_vol_term_structure_leg = generate_forward_vol_structure(days_to_exp_leg, bumped_key_vols_iv_leg)
                price_after_vol_bump_leg, _, _, _ = universal_binomial_pricer(
                    S=S_current_strat, K=leg_obj.strike_price, expiration_date=leg_obj.expiration_date, r_input=r_current,
                    sigma_input=bumped_vol_term_structure_leg, model=strategy_data.get('model', 'jarrow_rudd'),
                    option_type=leg_obj.option_type, exercise_type=strategy_data.get('exercise_type', 'american'),
                    div=div_current_strat_to_use, historical_vol=None
                )
                leg_greeks_val['vega'] = (price_after_vol_bump_leg - current_leg_price_val) if price_after_vol_bump_leg is not None and current_leg_price_val is not None else None

            # Market price for leg
            leg_option_chain_df = price_fetcher.get_option_data_finviz(strategy_ticker, 'o', leg_obj.expiration_date.strftime('%Y-%m-%d'))
            leg_market_price_val = _get_market_price_from_finviz_df(leg_option_chain_df, leg_obj.strike_price, leg_obj.option_type[0].upper())

            # Aggregation
            total_strategy_current_model_value += current_leg_price_val * leg_obj.quantity * direction_multiplier
            if leg_market_price_val is not None:
                total_strategy_current_market_value += leg_market_price_val * leg_obj.quantity * direction_multiplier
            else:
                any_leg_market_price_missing = True

            total_strategy_delta += leg_greeks_val.get('delta', 0.0) * leg_obj.quantity * direction_multiplier
            total_strategy_gamma += leg_greeks_val.get('gamma', 0.0) * leg_obj.quantity * direction_multiplier
            total_strategy_vega += leg_greeks_val.get('vega', 0.0) * leg_obj.quantity * direction_multiplier
            total_strategy_theta_annual += leg_greeks_val.get('theta', 0.0) * leg_obj.quantity * direction_multiplier
            if leg_obj.buy_sell == 'buy' and strategy_data.get('exercise_type') == 'american' and leg_early_exercise_premium > 0:
                total_net_benefit_from_early_exercise += leg_early_exercise_premium * leg_obj.quantity
            
            if leg_model_alerts_val:
                for alert_text_leg in leg_model_alerts_val:
                    if "EXERCISE ALERT" not in alert_text_leg:
                        has_any_leg_specific_alerts = True
                        break

            individual_leg_analysis_results.append({
                "description": leg_obj.get_description(display_currency, display_date),
                "current_model_price_per_option": current_leg_price_val,
                "current_market_price_per_option": leg_market_price_val,
                "greeks": leg_greeks_val, "alerts": leg_model_alerts_val,
                "early_exercise_premium_per_option": leg_early_exercise_premium
            })

        if any_leg_market_price_missing:
            total_strategy_current_market_value = None # Mark as indeterminate

        # --- 3. Calculate Strategy-level P&L and Alerts ---
        strategy_pnl_model = total_strategy_current_model_value - total_strategy_open_cost
        raw_strategy_pnl_pct_model = (strategy_pnl_model / abs(total_strategy_open_cost)) * 100 if total_strategy_open_cost != 0 else float('inf') if strategy_pnl_model > 0 else (float('-inf') if strategy_pnl_model < 0 else 0.0)

        strategy_pnl_market, raw_strategy_pnl_pct_market = None, None
        if total_strategy_current_market_value is not None:
            strategy_pnl_market = total_strategy_current_market_value - total_strategy_open_cost
            raw_strategy_pnl_pct_market = (strategy_pnl_market / abs(total_strategy_open_cost)) * 100 if total_strategy_open_cost != 0 else float('inf') if strategy_pnl_market > 0 else (float('-inf') if strategy_pnl_market < 0 else 0.0)

        strategy_level_alerts = []
        profit_target_strat_val = strategy_data.get("profit_target_pct")
        stop_loss_strat_val = strategy_data.get("stop_loss_pct")

        if profit_target_strat_val is not None and raw_strategy_pnl_pct_market is not None and not np.isinf(raw_strategy_pnl_pct_market) and not np.isnan(raw_strategy_pnl_pct_market):
            if raw_strategy_pnl_pct_market >= profit_target_strat_val:
                strategy_level_alerts.append(f"STRATEGY P&L ALERT (Market): Profit target of {profit_target_strat_val:.1f}% hit (Market P&L: {raw_strategy_pnl_pct_market:+.2f}%). Consider taking profit.")
        if stop_loss_strat_val is not None and raw_strategy_pnl_pct_market is not None and not np.isinf(raw_strategy_pnl_pct_market) and not np.isnan(raw_strategy_pnl_pct_market):
            if raw_strategy_pnl_pct_market <= stop_loss_strat_val:
                strategy_level_alerts.append(f"STRATEGY P&L ALERT (Market): Stop-loss of {stop_loss_strat_val:.1f}% hit (Market P&L: {raw_strategy_pnl_pct_market:+.2f}%). Consider closing.")

        min_dte_strategy = float('inf')
        if legs:
            min_dte_strategy = min((leg.expiration_date - date.today()).days for leg in legs if isinstance(leg, OptionLeg))

        if min_dte_strategy <= 7:
            pnl_threshold_for_closing_alert = abs(total_strategy_open_cost) * 0.05 if total_strategy_open_cost != 0 else 0
            if strategy_pnl_market is not None and strategy_pnl_market < pnl_threshold_for_closing_alert:
                strategy_level_alerts.append(f"STRATEGY CLOSE RECOMMENDATION: Shortest leg expires in {min_dte_strategy} day(s). Overall Market P&L is {display_currency(strategy_pnl_market)} ({raw_strategy_pnl_pct_market:+.2f}%). Consider closing.")
            elif strategy_pnl_market is None:
                strategy_level_alerts.append(f"STRATEGY CLOSE INFO: Shortest leg expires in {min_dte_strategy} day(s). Market P&L could not be determined. Review manually.")

        sum_of_buy_quantities = sum(leg.quantity for leg in legs if isinstance(leg, OptionLeg) and leg.buy_sell == 'buy')
        if total_strategy_delta is not None and sum_of_buy_quantities > 0 and abs(total_strategy_delta) > 0.7 * sum_of_buy_quantities:
             strategy_level_alerts.append(f"STRATEGY GREEK INFO: Overall Delta is {total_strategy_delta:.2f}, indicating a strong directional bias.")
        
        daily_strategy_theta = total_strategy_theta_annual / 365.0 if total_strategy_theta_annual is not None else None
        if daily_strategy_theta is not None and daily_strategy_theta < 0:
             strategy_level_alerts.append(f"STRATEGY GREEK INFO: Overall daily Theta is {daily_strategy_theta:.2f}. Strategy is subject to time decay.")

        if total_strategy_vega is not None and total_strategy_open_cost != 0 and abs(total_strategy_vega) > 0.05 * abs(total_strategy_open_cost):
            strategy_level_alerts.append(f"STRATEGY VEGA ALERT: Overall Vega is {total_strategy_vega:.2f}. Strategy value is sensitive to IV changes. A 1% point increase in IV would change value by approx. {display_currency(total_strategy_vega)}.")
        elif total_strategy_vega is not None:
            strategy_level_alerts.append(f"STRATEGY GREEK INFO: Overall Vega is {total_strategy_vega:.2f}. A 1% point increase in IV would change value by approx. {display_currency(total_strategy_vega)}.")

        if total_net_benefit_from_early_exercise > 0:
            strategy_level_alerts.append(f"STRATEGY EARLY EXERCISE BENEFIT: Potential net gain of {display_currency(total_net_benefit_from_early_exercise)} by exercising specific long American legs now.")

        if has_any_leg_specific_alerts:
            strategy_level_alerts.append("CRITICAL LEG ALERTS: Some legs have other specific alerts. Review individual leg breakdowns.")

        # --- 4. Assemble Final Results Dictionary ---
        return {
            "status": "success", "analysis_date": date.today(), "ticker": strategy_ticker,
            "warnings": [w for w in [hv_warning, div_warning] if w],
            "strategy_details": {
                "name": strategy_data.get("name", "Unnamed Strategy"),
                "open_date": strategy_data.get("open_date"),
                "profit_target_pct": strategy_data.get("profit_target_pct"),
                "stop_loss_pct": strategy_data.get("stop_loss_pct"),
                "model": strategy_data.get("model"),
                "exercise_type": strategy_data.get("exercise_type")
            },
            "market_data": {
                "s_current_strat": S_current_strat, "lookback_days_hv_strat": lookback_days_hv_strat,
                "hv_current_strat": hv_current_strat, "div_current_strat_to_use": div_current_strat_to_use
            },
            "strategy_status": {
                "pnl_model": strategy_pnl_model, "raw_pnl_pct_model": raw_strategy_pnl_pct_model,
                "pnl_market": strategy_pnl_market, "raw_pnl_pct_market": raw_strategy_pnl_pct_market,
                "total_model_value": total_strategy_current_model_value,
                "total_market_value": total_strategy_current_market_value,
                "open_cost": total_strategy_open_cost
            },
            "strategy_risk_exposure": {
                "delta": total_strategy_delta, "gamma": total_strategy_gamma,
                "vega": total_strategy_vega, "theta_annual": total_strategy_theta_annual
            },
            "strategy_alerts": strategy_level_alerts,
            "leg_results": individual_leg_analysis_results
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}

def display_strategy_analysis_results(results):
    """Displays the results from calculate_strategy_analysis using Streamlit components."""
    if results['status'] == 'error':
        st.error(f"An error occurred during strategy analysis: {results['message']}")
        st.error(results['traceback'])
        return

    # --- Display successful analysis ---
    st.header(f"Strategy Analysis: {results['strategy_details']['name']}")
    st.subheader(f"Underlying: {results['ticker'].upper()}")

    for warning_msg in results.get('warnings', []):
        st.warning(f"WARNING: {warning_msg}")

    # --- Strategy Details ---
    sd_res = results['strategy_details']
    st.markdown(f"""
    - **Open Date:** {display_date(sd_res['open_date'])}
    - **Profit Target:** {display_percentage_point(sd_res['profit_target_pct'], precision=1)} | **Stop Loss:** {display_percentage_point(sd_res['stop_loss_pct'], precision=1)}
    - **Model:** {display_capitalized(sd_res['model'])} | **Exercise Type:** {display_capitalized(sd_res['exercise_type'])}
    """)

    # --- Market Data ---
    md_res = results['market_data']
    st.subheader("Market Data for Underlying")
    st.markdown(f"""
    - **Current Stock Price ({results['ticker'].upper()}):** {display_currency(md_res['s_current_strat'])}
    - **{md_res['lookback_days_hv_strat']}-Day Historical Volatility:** {display_percentage(md_res['hv_current_strat'], precision=2)}
    - **Annual Dividend Yield (Finviz):** {display_percentage(md_res['div_current_strat_to_use'], precision=2)}
    """)

    # --- Overall Strategy Status ---
    st.subheader("1. Overall Strategy Status")
    ss_res = results['strategy_status']
    
    # Model P&L
    pnl_model_display = display_currency(ss_res['pnl_model'])
    raw_pnl_pct_model = ss_res['raw_pnl_pct_model']
    pnl_model_pct_display_val = "N/A"
    if raw_pnl_pct_model is not None:
        if np.isinf(raw_pnl_pct_model): pnl_model_pct_display_val = f"{'+' if raw_pnl_pct_model > 0 else ''}{str(raw_pnl_pct_model).lower()}"
        else: pnl_model_pct_display_val = f"{raw_pnl_pct_model:+.2f}%"
    
    # Market P&L
    pnl_market_display = display_currency(ss_res['pnl_market'])
    raw_pnl_pct_market = ss_res['raw_pnl_pct_market']
    pnl_market_pct_display_val = "N/A"
    if raw_pnl_pct_market is not None:
        if np.isinf(raw_pnl_pct_market): pnl_market_pct_display_val = f"{'+' if raw_pnl_pct_market > 0 else ''}{str(raw_pnl_pct_market).lower()}"
        else: pnl_market_pct_display_val = f"{raw_pnl_pct_market:+.2f}%"

    st.markdown(f"""
    - **Strategy Model P&L:** {pnl_model_display} ({pnl_model_pct_display_val})
    - **Strategy Market P&L (Finviz):** {pnl_market_display} ({pnl_market_pct_display_val})
    - **Current Strategy Model Value:** {display_currency(ss_res['total_model_value'])}
    - **Current Strategy Market Value (Finviz):** {display_currency(ss_res['total_market_value'])}
    - **Strategy Open Cost/Credit:** {display_currency(ss_res['open_cost'])}
    """)

    # --- Overall Strategy Risk ---
    st.subheader("2. Overall Strategy Risk Exposure (Greeks)")
    greeks = results['strategy_risk_exposure']
    daily_theta_val = greeks.get('theta_annual', 0.0) / 365.0 if greeks.get('theta_annual') is not None else None
    st.markdown(f"""
    - **Delta:** {display_float(greeks.get('delta'), precision=3)}
    - **Gamma:** {display_float(greeks.get('gamma'), precision=3)}
    - **Vega:** {display_float(greeks.get('vega'), precision=3)}
    - **Theta (daily):** {display_float(daily_theta_val, precision=3)}
    """)

    # --- Alerts ---
    st.subheader("3. Actionable Alerts Summary (Strategy Level)")
    all_alerts = results['strategy_alerts']
    if not all_alerts:
        st.info("  - No specific strategy-level alerts triggered.")
    else:
        # Sorting logic can be added here if needed
        for alert in all_alerts:
            if "Stop-loss" in alert: st.error(f"- {alert}")
            elif "Profit target" in alert: st.success(f"- {alert}")
            elif "BENEFIT" in alert or "RECOMMENDATION" in alert or "VEGA ALERT" in alert or "CRITICAL" in alert: st.warning(f"- {alert}")
            else: st.info(f"- {alert}")

    # --- Leg Breakdown ---
    st.subheader("4. Individual Leg Breakdown")
    leg_results = results.get('leg_results', [])
    if not leg_results:
        st.info("No legs to display analysis for.")
    else:
        for leg_res in leg_results:
            with st.expander(leg_res["description"], expanded=False):
                if leg_res.get("status") == "error":
                    st.error(leg_res.get("description"))
                    continue
                
                st.markdown(f"  - **Model Price:** {display_currency(leg_res['current_model_price_per_option'])} | **Market Price:** {display_currency(leg_res['current_market_price_per_option'])}")
                
                leg_greeks = leg_res['greeks']
                leg_daily_theta = leg_greeks.get('theta', 0.0) / 365.0
                st.markdown(f"  - **Greeks:** Delta: {display_float(leg_greeks.get('delta'), 3)}, Gamma: {display_float(leg_greeks.get('gamma'), 3)}, Vega: {display_float(leg_greeks.get('vega'), 3)}, Theta: {display_float(leg_daily_theta, 3)}")
                
                if leg_res.get('early_exercise_premium_per_option', 0.0) > 0:
                    st.markdown(f"  - **Early Exercise Premium:** {display_currency(leg_res['early_exercise_premium_per_option'])} per option.")
                
                if leg_res['alerts']:
                    st.markdown(f"  - **Model Alerts for this leg:**")
                    for alert_item in leg_res['alerts']:
                        st.markdown(f"    - {alert_item}")

# --- Analysis Calculation and Display Functions ---

def display_daily_check_results(results):
    """Displays the results from calculate_daily_check using Streamlit components."""
    if results['status'] == 'error':
        st.error(f"An error occurred during analysis: {results['message']}")
        import traceback
        st.error(results['traceback'])
        return
    
    if results['status'] == 'expired':
        st.error("POSITION EXPIRED.")
        pnl_at_expiry_display = display_currency(results['expired_info']['pnl_at_expiry'])
        pnl_pct_at_expiry_display = display_percentage_point(results['expired_info']['pnl_pct_at_expiry'], precision=2, add_plus_sign=True)
        st.markdown(f"  - **Final P&L at Expiry:** {pnl_at_expiry_display} per share ({pnl_pct_at_expiry_display})")
        return

    # --- Display successful analysis ---
    st.header(f"Daily Strategy Briefing for {results['ticker'].upper()}")
    
    for warning_msg in results.get('warnings', []):
        st.warning(f"WARNING: {warning_msg}")

    st.subheader("Position Details")
    pd_res = results['position_details']
    st.markdown(f"""
    - **Type:** {pd_res['type_display']}
    - **Strike:** {pd_res['strike_display']}
    - **Opened:** {pd_res['open_date_display']} | **Expires:** {pd_res['expiration_date_display']}
    - **Cost:** {pd_res['cost_display']}
    - **Profit Target:** {pd_res['profit_target_display']} | **Stop Loss:** {pd_res['stop_loss_display']}
    - **Open IV:** {pd_res['open_iv_display']}
    """)

    st.subheader("Market Data")
    md_res = results['market_data']
    st.markdown(f"""
    - **Current Stock Price ({results['ticker'].upper()}):** {md_res['s_current_display']}
    - **{md_res['lookback_days_hv']}-Day Historical Volatility:** {md_res['hv_current_display']}
    - **Annual Dividend Yield (Finviz):** {md_res['div_current_display']}
    """)

    st.subheader("1. Position Status")
    ps_res = results['position_status']
    pnl_model_display = display_currency(ps_res['pnl_model'])
    raw_pnl_pct_model = ps_res['raw_pnl_pct_model']
    pnl_model_pct_display_val = "N/A"
    if raw_pnl_pct_model is None: pnl_model_pct_display_val = "N/A"
    elif np.isinf(raw_pnl_pct_model): pnl_model_pct_display_val = f"{'+' if raw_pnl_pct_model > 0 else ''}{str(raw_pnl_pct_model).lower()}"
    else: pnl_model_pct_display_val = f"{raw_pnl_pct_model:+.2f}"
    
    pnl_market_display = display_currency(ps_res['pnl_market'])
    raw_pnl_pct_market = ps_res['raw_pnl_pct_market']
    pnl_market_pct_display_val = "N/A"
    if raw_pnl_pct_market is None: pnl_market_pct_display_val = "N/A"
    elif np.isinf(raw_pnl_pct_market): pnl_market_pct_display_val = f"{'+' if raw_pnl_pct_market > 0 else ''}{str(raw_pnl_pct_market).lower()}"
    else: pnl_market_pct_display_val = f"{raw_pnl_pct_market:+.2f}"

    st.markdown(f"""
    - **Model P&L:** {pnl_model_display} per share ({pnl_model_pct_display_val}%)
    - **Market P&L (Finviz):** {pnl_market_display} per share ({pnl_market_pct_display_val}%)
    - **Current Model Price:** {display_currency(ps_res['current_model_price'])} (vs. Open Price: {display_currency(ps_res['open_price'])})
    - **Current Market Price (Finviz):** {display_currency(ps_res['market_option_price'])}
    """)

    st.subheader("2. Risk Exposure (Greeks)")
    greeks = results['risk_exposure']
    daily_theta_val = greeks.get('theta', 0.0) / 365.0 if greeks.get('theta') is not None else None
    st.markdown(f"""
    - **Delta:** {display_float(greeks.get('delta'), precision=3)}
    - **Gamma:** {display_float(greeks.get('gamma'), precision=3)}
    - **Vega:** {display_float(greeks.get('vega'), precision=3)}
    - **Theta (daily):** {display_float(daily_theta_val, precision=3)}
    """)

    st.subheader("3. Actionable Alerts Summary")
    all_alerts = results['actionable_alerts']
    if not all_alerts:
        st.info("  - No strategic alerts triggered.")
    else:
        def sort_key(alert_str):
            if "P&L ALERT: Stop-loss" in alert_str: return f"00 {alert_str}"
            if "P&L ALERT: Profit target" in alert_str: return f"01 {alert_str}"
            if "EARLY EXERCISE BENEFIT:" in alert_str: return f"02 {alert_str}"
            if "EXERCISE ALERT" in alert_str:
                try:
                    date_part = alert_str.split("On ")[1].split(":")[0]
                    return f"03 {date_part} {alert_str}"
                except IndexError: return f"03 {alert_str}"
            if "GREEKS ALERT: Delta" in alert_str: return f"04 {alert_str}"
            if "GAMMA ALERT" in alert_str: return f"05 {alert_str}"
            if "THETA DECAY ALERT" in alert_str: return f"06 {alert_str}"
            if "VEGA ALERT" in alert_str: return f"07 {alert_str}"
            if "IV CHANGE ALERT" in alert_str: return f"08 {alert_str}"
            if "STRATEGY ALERT" in alert_str: return f"09 {alert_str}"
            if "CONTEXT: IV" in alert_str: return f"10 {alert_str}"
            if "MODEL VS MARKET PRICE:" in alert_str: return f"11 {alert_str}"
            return f"99 {alert_str}"
        
        all_alerts.sort(key=sort_key)
        exercise_alerts_list = [a for a in all_alerts if "EXERCISE ALERT" in a]
        other_alerts_list = [a for a in all_alerts if "EXERCISE ALERT" not in a]

        if exercise_alerts_list:
            with st.expander(f"Exercise Alerts ({len(exercise_alerts_list)} found)", expanded=True):
                for ex_alert in exercise_alerts_list:
                    st.warning(f"- {ex_alert.replace('EXERCISE ALERT: ', '')}")
        
        for alert in other_alerts_list:
            if "P&L ALERT: Stop-loss" in alert: st.error(f"- {alert}")
            elif "P&L ALERT: Profit target" in alert: st.success(f"- {alert}")
            elif "EARLY EXERCISE BENEFIT:" in alert: st.warning(f"- {alert}")
            elif "GAMMA ALERT" in alert or "THETA DECAY ALERT" in alert: st.warning(f"- {alert}")
            else: st.info(f"- {alert}")

# --- Streamlit App ---
def main_streamlit_app():
    st.title("Option Position Tracker & Strategy Advisor")

    # Load persisted state from file at the beginning of the app run
    loaded_state_from_file = _load_app_session_state()

    # Define default values for session state
    defaults = {
        "ss_current_risk_free_rate": 0.045,
        "ss_tracked_positions": [],
        "ss_analysis_cache": {}, # Cache for analysis results
        "new_pos_ticker_symbol": 'SPY',
        "new_pos_strike_price": 500.0,
        "new_pos_expiration_date": date.today() + timedelta(days=45),
        "new_pos_option_type": 'call',
        "new_pos_open_date": date.today(),
        "new_pos_open_price": 5.50,
        "new_pos_open_iv": 0.20,
        "new_pos_profit_target": 50.0,
        "new_pos_stop_loss": -25.0,
        "new_pos_exercise_type": 'american',
        "new_pos_model": 'jarrow_rudd',
        "ss_new_strategy_name": "My Strategy",
        "ss_new_strategy_ticker_symbol": "SPY",
        "ss_new_strategy_open_date": date.today(),
        "ss_new_strategy_profit_target_pct": 50.0,
        "ss_new_strategy_stop_loss_pct": -25.0,
        "ss_new_strategy_legs_building": [],
        "ss_current_leg_buy_sell": "buy",
        "ss_current_leg_option_type": "call",
        "ss_current_leg_quantity": 1,
        "ss_current_leg_strike_price": 500.0,
        "ss_current_leg_expiration_date": date.today() + timedelta(days=45),
        "ss_new_strategy_open_price": 1.00,
        "ss_market_rate_tickers": "SPY, QQQ, IWM",
        "ss_market_rate_exp_date": date.today() + timedelta(days=30),
        "ss_screener_ticker": "SPY",
        "ss_screener_exp_date": date.today() + timedelta(days=30),
        "run_screener_flag": False,
    }

    # Initialize session state
    for key, default_value in defaults.items():
        if key not in st.session_state:
            loaded_value = loaded_state_from_file.get(key)
            if loaded_value is not None:
                if key in ["ss_tracked_positions", "ss_new_strategy_legs_building", "ss_analysis_cache"]:
                    st.session_state[key] = loaded_value
                elif isinstance(default_value, date) and isinstance(loaded_value, str):
                    try:
                        st.session_state[key] = date.fromisoformat(loaded_value)
                    except (TypeError, ValueError):
                        st.session_state[key] = default_value
                else:
                    st.session_state[key] = loaded_value
            else:
                st.session_state[key] = default_value
    
    if "ss_new_strategy_legs_building" not in st.session_state or not isinstance(st.session_state.ss_new_strategy_legs_building, list):
        st.session_state.ss_new_strategy_legs_building = []

    # If a new rate was calculated in the last run, update the main state variable now,
    # before any widgets are created. This avoids the "cannot be modified after instantiation" error.
    if 'temp_new_risk_free_rate' in st.session_state:
        st.session_state.ss_current_risk_free_rate = st.session_state.temp_new_risk_free_rate
        del st.session_state['temp_new_risk_free_rate']
        _save_app_session_state()

    # --- Sidebar UI ---
    st.sidebar.header("Global Market Parameters")
    st.sidebar.number_input("Current Risk-Free Rate (e.g., 0.045 for 4.5%)", key="ss_current_risk_free_rate", format="%.3f", on_change=_save_app_session_state)

    st.sidebar.text_input("Tickers for Implied Rate", key="ss_market_rate_tickers", help="Comma-separated list of tickers (e.g., SPY, QQQ, IWM)", on_change=_save_app_session_state)
    st.sidebar.date_input("Expiration for Implied Rate", key="ss_market_rate_exp_date", on_change=_save_app_session_state)

    if st.sidebar.button("Calculate Market-Implied Rate"):
        with st.sidebar:
            ticker_list_str = st.session_state.get("ss_market_rate_tickers", "SPY, QQQ, IWM")
            tickers_to_use = [t.strip().upper() for t in ticker_list_str.split(',') if t.strip()]

            with st.spinner(f"Calculating from {', '.join(tickers_to_use)}..."):
                market_rate, logs = calculate_market_implied_risk_free_rate(
                    expiration_date=st.session_state.ss_market_rate_exp_date,
                    tickers=tickers_to_use
                )
                st.session_state['ss_market_rate_logs'] = logs
                if market_rate is not None:
                    st.session_state.temp_new_risk_free_rate = market_rate
                    _save_app_session_state()
                    st.rerun()

    # Display logs if they exist
    if 'ss_market_rate_logs' in st.session_state:
        with st.sidebar.expander("Implied Rate Calculation Log", expanded=False):
            for log_msg in st.session_state['ss_market_rate_logs']:
                st.caption(log_msg)

    st.sidebar.info("IV and Dividend Yield are fetched automatically during analysis.")

    with st.sidebar.expander("Option Screener", expanded=False):
        st.text_input("Ticker Symbol", key="ss_screener_ticker", on_change=_save_app_session_state)
        st.date_input("Expiration Date", key="ss_screener_exp_date", on_change=_save_app_session_state)
        if st.button("Find Undervalued Options"):
            st.session_state['run_screener_flag'] = True
            _save_app_session_state()
            st.rerun()

    with st.sidebar.expander("Add New Option Position", expanded=False):
        st.text_input("Ticker Symbol", key="new_pos_ticker_symbol", on_change=_save_app_session_state)
        st.number_input("Strike Price", key="new_pos_strike_price", format="%.2f", on_change=_save_app_session_state)
        st.date_input("Expiration Date", key="new_pos_expiration_date", on_change=_save_app_session_state)
        st.selectbox("Option Type", ['call', 'put'], key="new_pos_option_type", on_change=_save_app_session_state)
        st.date_input("Open Date", key="new_pos_open_date", on_change=_save_app_session_state)
        st.number_input("Open Price ($ per option)", key="new_pos_open_price", format="%.2f", min_value=0.0, on_change=_save_app_session_state)
        st.number_input("Open IV at Purchase (e.g., 0.28 for 28%)", key="new_pos_open_iv", format="%.3f", min_value=0.0, on_change=_save_app_session_state)
        st.number_input("Profit Target %", key="new_pos_profit_target", format="%.1f", on_change=_save_app_session_state)
        st.number_input("Stop Loss % (negative for loss)", key="new_pos_stop_loss", format="%.1f", on_change=_save_app_session_state)
        st.selectbox("Exercise Type", ['american', 'european'], key="new_pos_exercise_type", on_change=_save_app_session_state)
        st.selectbox("Binomial Model", ['jarrow_rudd', 'crr'], key="new_pos_model", on_change=_save_app_session_state)

        if st.button("Add Position to Tracking"):
            new_position_data = {
                "id": str(uuid.uuid4()), "ticker": st.session_state.new_pos_ticker_symbol,
                "K": st.session_state.new_pos_strike_price, "expiration_date": st.session_state.new_pos_expiration_date,
                "option_type": st.session_state.new_pos_option_type, "open_date": st.session_state.new_pos_open_date,
                "open_price": st.session_state.new_pos_open_price, "open_iv": st.session_state.new_pos_open_iv,
                "profit_target_pct": st.session_state.new_pos_profit_target, "stop_loss_pct": st.session_state.new_pos_stop_loss,
                "exercise_type": st.session_state.new_pos_exercise_type, "model": st.session_state.new_pos_model,
            }
            if not new_position_data["ticker"]:
                st.sidebar.error("Ticker Symbol cannot be empty.")
            else:
                st.session_state.ss_tracked_positions.append(new_position_data)
                _save_app_session_state()
                st.sidebar.success(f"Added {new_position_data['ticker']} to tracking.")
                st.rerun()

    def _on_add_leg_clicked():
        try:
            new_leg = OptionLeg(
                buy_sell=st.session_state.ss_current_leg_buy_sell, option_type=st.session_state.ss_current_leg_option_type,
                quantity=st.session_state.ss_current_leg_quantity, strike_price=st.session_state.ss_current_leg_strike_price,
                expiration_date=st.session_state.ss_current_leg_expiration_date, open_price=0.0,
            )
            st.session_state.ss_new_strategy_legs_building.append(new_leg)
            _save_app_session_state()
        except Exception as e:
            st.sidebar.error(f"Error adding leg: {e}")

    def _on_add_strategy_to_tracking_clicked():
        if not st.session_state.ss_new_strategy_name.strip() or not st.session_state.ss_new_strategy_ticker_symbol.strip() or not st.session_state.ss_new_strategy_legs_building:
            st.sidebar.error("Strategy Name, Ticker, and at least one leg are required.")
            return

        strategy_data_to_save = {
            "id": str(uuid.uuid4()), "type": "strategy", "name": st.session_state.ss_new_strategy_name,
            "ticker": st.session_state.ss_new_strategy_ticker_symbol, "open_date": st.session_state.ss_new_strategy_open_date,
            "strategy_open_price": st.session_state.ss_new_strategy_open_price,
            "profit_target_pct": st.session_state.ss_new_strategy_profit_target_pct,
            "stop_loss_pct": st.session_state.ss_new_strategy_stop_loss_pct,
            "legs": st.session_state.ss_new_strategy_legs_building,
            "model": st.session_state.new_pos_model, "exercise_type": st.session_state.new_pos_exercise_type
        }
        st.session_state.ss_tracked_positions.append(strategy_data_to_save)
        st.sidebar.success(f"Strategy '{strategy_data_to_save['name']}' added.")
        
        # Clear form
        st.session_state.ss_new_strategy_name = defaults["ss_new_strategy_name"]
        st.session_state.ss_new_strategy_ticker_symbol = defaults["ss_new_strategy_ticker_symbol"]
        st.session_state.ss_new_strategy_open_date = defaults["ss_new_strategy_open_date"]
        st.session_state.ss_new_strategy_open_price = defaults["ss_new_strategy_open_price"]
        st.session_state.ss_new_strategy_profit_target_pct = defaults["ss_new_strategy_profit_target_pct"]
        st.session_state.ss_new_strategy_stop_loss_pct = defaults["ss_new_strategy_stop_loss_pct"]
        st.session_state.ss_new_strategy_legs_building = []
        _save_app_session_state()

    with st.sidebar.expander("Add New Option Strategy", expanded=False):
        st.text_input("Strategy Name", key="ss_new_strategy_name", on_change=_save_app_session_state)
        st.text_input("Underlying Ticker", key="ss_new_strategy_ticker_symbol", on_change=_save_app_session_state)
        st.date_input("Strategy Open Date", key="ss_new_strategy_open_date", on_change=_save_app_session_state)
        st.number_input("Strategy Open Price (Debit + / Credit -)", key="ss_new_strategy_open_price", format="%.2f", on_change=_save_app_session_state)
        st.number_input("Strategy Profit Target %", key="ss_new_strategy_profit_target_pct", format="%.1f", on_change=_save_app_session_state)
        st.number_input("Strategy Stop Loss % (negative)", key="ss_new_strategy_stop_loss_pct", format="%.1f", on_change=_save_app_session_state)
        st.button("Add Strategy to Tracking", on_click=_on_add_strategy_to_tracking_clicked)

    with st.sidebar.expander("Define Legs for New Strategy", expanded=True):
        st.markdown("**Define New Leg:**")
        leg_cols = st.columns(2)
        leg_cols[0].selectbox("Buy/Sell", ["buy", "sell"], key="ss_current_leg_buy_sell", on_change=_save_app_session_state)
        leg_cols[0].number_input("Quantity", key="ss_current_leg_quantity", min_value=1, step=1, on_change=_save_app_session_state)
        leg_cols[0].selectbox("Option Type", ["call", "put"], key="ss_current_leg_option_type", on_change=_save_app_session_state)
        leg_cols[1].number_input("Strike Price", key="ss_current_leg_strike_price", format="%.2f", on_change=_save_app_session_state)
        leg_cols[1].date_input("Leg Expiration Date", key="ss_current_leg_expiration_date", on_change=_save_app_session_state)
        st.button("Add This Leg to Strategy", on_click=_on_add_leg_clicked)

        if st.session_state.ss_new_strategy_legs_building:
            st.markdown("**Legs for Current Strategy:**")
            for i, leg_obj in enumerate(st.session_state.ss_new_strategy_legs_building):
                leg_desc = leg_obj.get_description(display_currency, display_date) if isinstance(leg_obj, OptionLeg) else "Invalid leg data"
                leg_disp_cols = st.columns([0.85, 0.15])
                leg_disp_cols[0].markdown(f"<small>{i+1}. {leg_desc}</small>", unsafe_allow_html=True)
                if leg_disp_cols[1].button(f"🗑️", key=f"remove_strategy_leg_{i}", help="Remove this leg"):
                    st.session_state.ss_new_strategy_legs_building.pop(i)
                    _save_app_session_state()
                    st.rerun()

    st.sidebar.header("Tracked Positions")
    if not st.session_state.ss_tracked_positions:
        st.sidebar.info("No positions are currently being tracked.")
    else:
        for i, pos_data in enumerate(st.session_state.ss_tracked_positions):
            pos_id = pos_data.get('id', f"no_id_{i}")
            if pos_data.get("type") == "strategy":
                pos_summary = f"STRATEGY: {pos_data.get('name', 'Unnamed')} ({len(pos_data.get('legs', []))} legs)"
            else:
                exp_date_str = pos_data['expiration_date'].strftime('%y-%m-%d') if isinstance(pos_data.get('expiration_date'), date) else "N/A"
                pos_summary = f"OPTION: {pos_data.get('ticker','N/A')} {display_currency(pos_data.get('K','N/A'),'')} {pos_data.get('option_type','N/A').capitalize()[0]} Exp: {exp_date_str}"
            
            col1, col2 = st.sidebar.columns([0.85, 0.15])
            col1.markdown(f"<small>{i+1}. {pos_summary}</small>", unsafe_allow_html=True)
            if col2.button(f"🗑️", key=f"remove_tracked_item_{pos_id}", help="Remove this item"):
                st.session_state.ss_tracked_positions.pop(i)
                if pos_id in st.session_state.ss_analysis_cache:
                    del st.session_state.ss_analysis_cache[pos_id]
                _save_app_session_state()
                st.rerun()

    # --- Main Page Content ---
    st.markdown("---")
    if st.button("Clear All Tracked Positions & Cache"):
        st.session_state.ss_tracked_positions = []
        st.session_state.ss_analysis_cache = {}
        if 'ss_screener_results_data' in st.session_state:
            del st.session_state['ss_screener_results_data']
        _save_app_session_state()
        st.rerun()

    if st.session_state.get('run_screener_flag', False):
        with st.spinner("Running full analysis... This may take a moment."):
            screener_results = run_option_screener()
            st.session_state.ss_screener_results_data = screener_results
        st.session_state['run_screener_flag'] = False
        _save_app_session_state()
        st.rerun() # Rerun to ensure the results are displayed immediately

    if 'ss_screener_results_data' in st.session_state and st.session_state.ss_screener_results_data:
        display_screener_results(st.session_state.ss_screener_results_data)
    elif st.session_state.ss_tracked_positions:
        analysis_section()
    else:
        st.info("Add positions or strategies using the sidebar to begin analysis, or use the Option Screener.")

def analysis_section():
    """Main section for displaying analysis of tracked positions with caching."""
    if not st.session_state.ss_tracked_positions:
        return

    # --- Create Tabs ---
    tab_titles = []
    for pos_data in st.session_state.ss_tracked_positions:
        if pos_data.get("type") == "strategy":
            title = f"Strat: {pos_data.get('name', 'Unnamed')} ({pos_data.get('ticker', '?').upper()})"
        else:
            exp_date_str = pos_data.get('expiration_date').strftime('%y-%m-%d') if isinstance(pos_data.get('expiration_date'), date) else "N/A"
            title = f"{pos_data.get('ticker','?').upper()} {pos_data.get('K','?')}{pos_data.get('option_type','?')[0].upper()} ({exp_date_str})"
        tab_titles.append(title)
    
    tabs = st.tabs(tab_titles)

    # --- Loop through positions and display analysis ---
    for i, (tab, position_data) in enumerate(zip(tabs, st.session_state.ss_tracked_positions)):
        with tab:
            pos_id = position_data.get("id")
            if not pos_id: # Should not happen with the upgrade logic
                st.error("Position is missing a unique ID. Please remove and re-add.")
                continue

            # --- Refresh Button and Cache Info ---
            if st.button("Refresh Analysis", key=f"refresh_{pos_id}"):
                with st.spinner(f"Analyzing {position_data.get('ticker', 'position')}..."):
                    # --- Fetch data ON-DEMAND inside the refresh button logic ---
                    fmp = FMPClient()
                    price_fetcher = PriceDataFetcher()
                    ticker_for_iv = position_data.get("ticker")
                    if ticker_for_iv:
                        key_vols_iv, iv_logs = fetch_iv_term_structure(ticker_for_iv, price_fetcher, fmp)
                        # Store iv_logs in session state to display them after rerun
                        st.session_state[f"iv_logs_{pos_id}"] = iv_logs
                    else:
                        key_vols_iv, iv_logs = [], ["No ticker found for this position to fetch IV."]
                        st.session_state[f"iv_logs_{pos_id}"] = iv_logs

                    if position_data.get("type") == "strategy":
                        analysis_result = calculate_strategy_analysis(position_data, st.session_state.ss_current_risk_free_rate, key_vols_iv, fmp, price_fetcher)
                        st.session_state.ss_analysis_cache[pos_id] = analysis_result
                    else:
                        tracker = OptionPositionTracker(
                            ticker=position_data.get("ticker"), K=position_data.get("K"),
                            expiration_date=position_data.get("expiration_date"), option_type=position_data.get("option_type"),
                            open_date=position_data.get("open_date"), open_price=position_data.get("open_price"),
                            profit_target_pct=position_data.get("profit_target_pct", 50.0),
                            stop_loss_pct=position_data.get("stop_loss_pct", -25.0), open_iv=position_data.get("open_iv"),
                            exercise_type=position_data.get("exercise_type", 'american'), model=position_data.get("model", 'jarrow_rudd')
                        )
                        analysis_result = tracker.calculate_daily_check(st.session_state.ss_current_risk_free_rate, key_vols_iv)
                        st.session_state.ss_analysis_cache[pos_id] = analysis_result
                _save_app_session_state()
                st.rerun()

            cached_result = st.session_state.ss_analysis_cache.get(pos_id)

            if cached_result:
                analysis_date = cached_result.get('analysis_date')
                if isinstance(analysis_date, date):
                    st.caption(f"Analysis as of: {analysis_date.strftime('%Y-%m-%d')}")
                
                if position_data.get("type") == "strategy":
                    display_strategy_analysis_results(cached_result)
                else:
                    display_daily_check_results(cached_result)
            else:
                st.info("This position has not been analyzed yet. Click 'Refresh Analysis' to begin.")
            
            # Display IV fetch log if it exists in session state
            iv_logs_to_display = st.session_state.get(f"iv_logs_{pos_id}")
            if iv_logs_to_display:
                with st.expander("IV Fetch Log", expanded=False):
                    for msg in iv_logs_to_display:
                        st.caption(msg)

if __name__ == '__main__':
    main_streamlit_app()
