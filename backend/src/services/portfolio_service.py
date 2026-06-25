from collections import defaultdict
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, date

from ..models.portfolio_models import CloseStrategyRequest, CloseStockPositionRequest
from .connection_manager import connection_manager
from .order_tracking_service import list_tracked_orders
from ..analytics.execution_signal_evaluator import (
    aggregate_exit_timing,
    build_exit_context_from_portfolio,
)
from ..analytics.exit_signal_agent import pending_agent_evaluations
from .exit_signal_eval_service import (
    get_cached_evaluation,
    timing_from_cached_evaluations,
)
from .strategy_signature import strategy_signature

def _sanitize_for_json(item):
    """
    Recursively walk a data structure and convert non-JSON-compliant types
    (NaN, Infinity, numpy integers/floats) to standard Python types.
    """
    if isinstance(item, dict):
        return {k: _sanitize_for_json(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [_sanitize_for_json(elem) for elem in item]
    elif isinstance(item, np.integer):
        return int(item)
    elif isinstance(item, np.floating):
        if np.isnan(item) or np.isinf(item):
            return None
        return float(item)
    elif isinstance(item, np.ndarray):
        return item.tolist()
    elif isinstance(item, float) and (np.isnan(item) or np.isinf(item)):
        return None
    return item

def _coalesce_column(df, target_name, candidates, default=0):
    """
    Ensures a numeric column named `target_name` exists by taking the first present candidate column,
    converting it to numeric, and filling missing values. If none of the candidates exist, creates
    the column with the provided default.
    """
    for name in candidates:
        if name in df.columns:
            df[target_name] = pd.to_numeric(df[name], errors='coerce')
            break
    if target_name not in df.columns:
        df[target_name] = default
    df[target_name] = df[target_name].fillna(default)
    return df

async def get_grouped_open_positions():
    """
    Fetches all open positions and account summary from the broker. It fetches them
    independently so that a failure in one does not prevent the other from being returned.
    """
    trader = await connection_manager.get_trader()
    account_details = {}
    positions_df = pd.DataFrame()

    # Step 1: Fetch account summary.
    try:
        account_details = await asyncio.wait_for(trader.get_account_details(), timeout=30.0)
        print(f"DEBUG(PortfolioSvc): Fetched account details: {account_details}")
    except Exception as e:
        print(f"WARN: Could not fetch account details, will use empty summary. Error: {e}")
        account_details = {}

    # Step 2: Fetch open positions, with retry logic.
    try:
        positions_df = await asyncio.wait_for(trader.open_positions(), timeout=45.0)
    except asyncio.TimeoutError:
        print("WARN: Positions request timed out, resetting connection and retrying...")
        await connection_manager.reset_connection()
        trader = await connection_manager.get_trader()
        try:
            positions_df = await asyncio.wait_for(trader.open_positions(), timeout=30.0)
        except Exception as e_retry:
            print(f"ERROR: Failed to fetch positions on retry: {e_retry}")
            positions_df = pd.DataFrame()
    except Exception as e:
        print(f"ERROR: Failed to fetch positions: {e}")
        positions_df = pd.DataFrame()

    # Step 3: Always build the portfolio summary from whatever account details we have.
    portfolio_summary = {
        "market_value": account_details.get('total_account_value'),
        "unrealized_pnl": account_details.get('unrealized_pnl'),
        "realized_pnl_today": account_details.get('realized_pnl_today'),
        "available_cash": account_details.get('available_cash') if account_details.get('available_cash') is not None else account_details.get('buying_power'),
        "pnl_today": account_details.get('pnl_today'),
    }
    print(f"DEBUG(PortfolioSvc): Constructed portfolio summary: {portfolio_summary}")

    # Step 4: Process positions if any were fetched.
    grouped_positions_data = {
        "options": defaultdict(list),
        "stocks": [],
        "others": []
    }

    if not positions_df.empty:
        positions_df = positions_df.copy()
        _coalesce_column(positions_df, 'marketValue', ['marketValue', 'market_value', 'marketvalue'], default=0)
        _coalesce_column(positions_df, 'unrealizedPNL', ['unrealizedPNL', 'unrealizedPnl', 'unrealizedPnL', 'unrealized_pnl', 'unrealized'], default=0)
        
        all_positions = positions_df.to_dict('records')
        for pos in all_positions:
            contract_type = pos.get('contract_type')
            if contract_type == 'Option':
                grouped_positions_data['options'][pos['symbol']].append(pos)
            elif contract_type == 'Stock':
                grouped_positions_data['stocks'].append(pos)
            else:
                grouped_positions_data['others'].append(pos)
    
    # Convert defaultdict to regular dict for JSON serialization
    grouped_positions_data['options'] = dict(grouped_positions_data['options'])

    # Step 4b: Live underlying stock prices from Alpaca (same path as analysis / IV pipeline).
    underlying_spot_prices: dict = {}
    option_underlyings = list(grouped_positions_data["options"].keys())
    if option_underlyings:
        try:
            canon_prices = await asyncio.wait_for(
                trader.get_stock_market_prices(option_underlyings),
                timeout=45.0,
            )
            underlying_spot_prices = {
                sym: canon_prices.get(str(sym).strip().upper()) for sym in option_underlyings
            }
        except Exception as exc:
            print(f"WARN: Could not fetch Alpaca market prices for option underlyings: {exc}")
            underlying_spot_prices = {sym: None for sym in option_underlyings}

    # Step 5: Combine and return.
    # --- Step 5b: Evaluate close-now action hints for open option strategies ---
    action_hints = {
        "close_now": [],
        "exit_eval_source": "agent",
        "agent_cache_evaluated_at": None,
        "exit_eval_refresh_pending": False,
        "strategy_exit_evals": {},
    }
    pending_exit_refresh_jobs = []

    try:
        tracked_orders = list_tracked_orders(limit=120)

        def _gcd_many(nums):
            import math
            cleaned = [abs(int(n)) for n in (nums or []) if n is not None]
            cleaned = [n for n in cleaned if n > 0]
            if not cleaned:
                return 1
            g = cleaned[0]
            for n in cleaned[1:]:
                g = math.gcd(g, n)
                if g == 1:
                    break
            return g or 1

        def _dte_from_expiry(expiry: str) -> int:
            if not expiry:
                return 0
            s = str(expiry).replace("-", "")
            if len(s) != 8 or not s.isdigit():
                return 0
            try:
                exp_date = datetime.strptime(s, "%Y%m%d").date()
                return max(0, (exp_date - date.today()).days)
            except Exception:
                return 0

        def _estimate_initial_credit_received(legs):
            # Approximate net premium received for the whole open position.
            # Uses broker avgCost and the sign of `position`:
            #   - long leg (position > 0) is debit: subtract its avgCost
            #   - short leg (position < 0) is credit: add its avgCost
            credit = 0.0
            for l in legs or []:
                qty = l.get("position")
                avg = l.get("avgCost")
                try:
                    qty_f = float(qty)
                    avg_f = float(avg)
                except Exception:
                    continue
                if qty_f == 0 or avg_f is None:
                    continue
                if qty_f < 0:
                    credit += abs(qty_f) * avg_f
                else:
                    credit -= abs(qty_f) * avg_f
            # Options multiplier approximation: 100x
            return credit * 100.0

        def _build_open_signature_symbol_legs(legs):
            active_legs = [l for l in (legs or []) if l.get("position") is not None and float(l.get("position")) != 0.0]
            if not active_legs:
                return None

            qtys = [abs(int(float(l.get("position")))) for l in active_legs]
            g = _gcd_many(qtys)

            expiries = [l.get("expiry") for l in active_legs if l.get("expiry")]
            if not expiries:
                return None
            counts = defaultdict(int)
            for e in expiries:
                counts[str(e)] += 1
            chosen_exp = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[0][0]

            norm_legs = []
            for l in active_legs:
                pos = float(l.get("position"))
                action = "BUY" if pos > 0 else "SELL"
                qty_ratio = abs(int(pos)) // g
                try:
                    strike = float(l.get("strike"))
                except Exception:
                    strike = None
                right = str(l.get("right", "")).upper()[:1]
                if strike is None:
                    continue
                norm_legs.append(
                    {
                        "action": action,
                        "quantity": int(qty_ratio),
                        "strike": strike,
                        "right": right,
                    }
                )
            if not norm_legs:
                return None
            # Pass chosen expiry exactly as stored in signature (YYYYMMDD)
            exp_flat = str(chosen_exp).replace("-", "")
            return {
                "expiration_date": exp_flat,
                "legs": norm_legs,
            }

        option_positions = grouped_positions_data.get("options") or {}
        for sym, legs in option_positions.items():
            sig_parts = _build_open_signature_symbol_legs(legs)
            if not sig_parts:
                continue

            sig = strategy_signature(sym, sig_parts["expiration_date"], sig_parts["legs"])
            matches = [o for o in tracked_orders if o.get("signature") == sig]
            if not matches:
                continue

            # Earliest tracked guidance snapshot
            matches_sorted = sorted(matches, key=lambda o: (o.get("placed_at") or ""))
            matched = matches_sorted[0]

            gpt_guidance = matched.get("gpt_guidance") or {}
            recs = gpt_guidance.get("execution_recommendations") or {}
            exit_conditions = recs.get("exit_conditions") or []
            conditions_for_eval = list(exit_conditions) if isinstance(exit_conditions, list) else []

            # If exit_conditions are missing, fold in the guidance strings.
            if not conditions_for_eval:
                if isinstance(recs.get("stop_loss_guidance"), str):
                    conditions_for_eval.append(recs.get("stop_loss_guidance"))
                if isinstance(recs.get("profit_target_guidance"), str):
                    conditions_for_eval.append(recs.get("profit_target_guidance"))

            legs_list = legs or []
            aggregate_unrealized_pnl = sum(float(l.get("unrealizedPNL") or 0) for l in legs_list)
            aggregate_market_value = sum(float(l.get("marketValue") or 0) for l in legs_list)

            # DTE is derived from the options expiry in open positions.
            dte = _dte_from_expiry(sig_parts["expiration_date"])
            underlying_price = None
            if sym and sym in underlying_spot_prices:
                underlying_price = underlying_spot_prices.get(sym)

            strategy_is_credit = matched.get("is_credit_spread")
            initial_credit_received = None
            if isinstance(strategy_is_credit, bool) and strategy_is_credit:
                initial_credit_received = _estimate_initial_credit_received(legs_list)
                if initial_credit_received <= 0:
                    initial_credit_received = None

            ctx = build_exit_context_from_portfolio(
                symbol=sym,
                legs=legs_list,
                underlying_price=underlying_price,
                aggregate_unrealized_pnl=aggregate_unrealized_pnl,
                aggregate_market_value=aggregate_market_value,
                dte=dte,
                days_to_earnings=None,
                strategy_is_credit_spread=strategy_is_credit,
                initial_credit_received=initial_credit_received,
            )

            cached = get_cached_evaluation(sig, conditions_for_eval)
            cache_fresh = bool(cached and not cached.get("_stale"))
            cache_evaluated_at = cached.get("evaluated_at") if cached else None
            cached_evaluations = (cached.get("evaluations") if cached else None) or []

            refresh_job = {
                "signature": sig,
                "symbol": sym,
                "conditions": conditions_for_eval,
                "underlying_price": underlying_price,
                "aggregate_unrealized_pnl": aggregate_unrealized_pnl,
                "aggregate_market_value": aggregate_market_value,
                "dte": dte,
                "strategy_is_credit_spread": strategy_is_credit,
                "initial_credit_received": initial_credit_received,
                "legs": legs_list,
            }

            if cached_evaluations and cache_fresh:
                exit_timing = timing_from_cached_evaluations(
                    conditions_for_eval,
                    cached_evaluations,
                )
                action_hints["exit_eval_source"] = "agent_cache"
                action_hints["agent_cache_evaluated_at"] = cache_evaluated_at
            elif cached_evaluations:
                exit_timing = timing_from_cached_evaluations(
                    conditions_for_eval,
                    cached_evaluations,
                )
                action_hints["exit_eval_source"] = "cache_stale"
                if not action_hints.get("agent_cache_evaluated_at"):
                    action_hints["agent_cache_evaluated_at"] = cache_evaluated_at
                pending_exit_refresh_jobs.append(refresh_job)
            else:
                exit_timing = aggregate_exit_timing(
                    pending_agent_evaluations(conditions_for_eval)
                )
                action_hints["exit_eval_source"] = "agent_pending"
                pending_exit_refresh_jobs.append(refresh_job)

            action_hints["strategy_exit_evals"][sym] = {
                "label": exit_timing.get("label"),
                "summary": exit_timing.get("summary"),
                "conditions": exit_timing.get("conditions") or [],
                "evaluated_at": cache_evaluated_at,
                "aggregate_status": exit_timing.get("status"),
            }

            if exit_timing.get("status") == "close_now":
                action_hints["close_now"].append(
                    {
                        "symbol": sym,
                        "label": exit_timing.get("label"),
                        "summary": exit_timing.get("summary"),
                        "conditions": exit_timing.get("conditions") or [],
                        "evaluated_at": cache_evaluated_at,
                    }
                )

    except Exception as e:
        # Best-effort hints; never break portfolio page.
        print(f"WARN(PortfolioSvc): action hints evaluation failed: {e}")

    if pending_exit_refresh_jobs:
        action_hints["exit_eval_refresh_pending"] = True
        try:
            from .exit_signal_eval_service import refresh_jobs_sync

            asyncio.create_task(asyncio.to_thread(refresh_jobs_sync, pending_exit_refresh_jobs))
        except Exception as refresh_exc:
            print(f"WARN(PortfolioSvc): could not schedule exit eval refresh: {refresh_exc}")

    response_data = {
        "summary": portfolio_summary,
        "positions": grouped_positions_data,
        "underlying_spot_prices": underlying_spot_prices,
        "action_hints": action_hints,
    }
    return _sanitize_for_json(response_data)

async def get_recent_orders_service():
    """
    Fetches the 10 most recent orders from the broker.
    """
    try:
        trader = await connection_manager.get_trader()
        
        # Add timeout wrapper for the recent orders call
        try:
            recent_orders = await asyncio.wait_for(trader.get_recent_orders(count=10), timeout=30.0)
        except asyncio.TimeoutError:
            print("WARN: Recent orders request timed out, returning empty list")
            recent_orders = []
        except Exception as e:
            # Handle broker internal timeouts like "completed orders request timed out"
            if "completed orders" in str(e).lower() or "timeout" in str(e).lower():
                print(f"WARN: Broker recent-orders request timed out ({e}), returning empty list")
                recent_orders = []
            else:
                raise
        
        # The data is already sanitized in the trader method by creating dicts,
        # but an extra _sanitize_for_json call ensures full compliance.
        return _sanitize_for_json(recent_orders)
        
    except Exception as e:
        print(f"ERROR: Failed to fetch recent orders: {e}")
        return _sanitize_for_json([])

async def close_strategy(request: CloseStrategyRequest):
    """
    Closes a strategy by placing a single combo order to close all legs atomically.
    This ensures all legs are filled together, preventing partial hedged positions.
    """
    trader = await connection_manager.get_trader()
    
    if not request.legs:
        return _sanitize_for_json({"status": "error", "message": "No legs provided for strategy closure"})
    
    try:
        # Get the underlying symbol from the first leg (all legs should have same symbol)
        underlying_symbol = request.legs[0].symbol
        
        # Prepare legs data for the strategy order
        # Each leg action should be OPPOSITE of current position to close it
        legs_data = []
        for leg in request.legs:
            # Determine the closing action - opposite of current position
            closing_action = "SELL" if leg.quantity > 0 else "BUY"
            
            legs_data.append({
                'action': closing_action,
                'quantity': 1,  # Ratio within the strategy (always 1:1 for basic strategies)
                'expiry_date': leg.expiry.replace('-', ''),  # Convert YYYY-MM-DD to YYYYMMDD
                'strike': leg.strike,
                'right': leg.right
            })
        
        # The size is the absolute quantity of the strategy to close
        # Use the minimum absolute position as the strategy size
        strategy_size = min(abs(leg.quantity) for leg in request.legs)
        
        print(f"DEBUG: Closing strategy {underlying_symbol} with size {strategy_size}")
        print(f"DEBUG: Strategy legs: {legs_data}")
        
        # Place the strategy order to close the entire position atomically
        result = await trader.place_strategy_order(
            symbol=underlying_symbol,
            legs_data=legs_data,
            size=strategy_size,  # Positive size since action is already set in legs
            order_type='MKT',
            open_position=False,
        )
        
        # Briefly poll for a status update without cancelling on timeout
        await trader.wait_for_order_fill(result, timeout=5)
        
        # Create response with strategy-level information
        strategy_summary = {
            "strategy": f"{underlying_symbol} {len(request.legs)}-leg strategy",
            "status": "success",
            "order_status": result.orderStatus.status,
            "filled": result.orderStatus.filled,
            "remaining": result.orderStatus.remaining,
            "strategy_size": strategy_size,
            "legs_closed": len(request.legs),
            "order_id": getattr(getattr(result, 'order', None), 'orderId', None),
            "perm_id": getattr(getattr(result, 'order', None), 'permId', None)
        }
        
        return _sanitize_for_json({"status": "submitted", "trade": strategy_summary})
        
    except Exception as e:
        print(f"ERROR: Failed to close strategy for {underlying_symbol}: {e}")
        # Fallback: If combo order fails, fall back to individual leg orders
        print("INFO: Falling back to individual leg closure...")
        
        closing_trades = []
        tasks = []
        for leg in request.legs:
            # The size to close is the negative of the current position quantity.
            closing_size = -leg.quantity
            
            task = trader.place_option_order(
                symbol=leg.symbol,
                size=closing_size,
                expiry_date=leg.expiry,
                strike=leg.strike,
                right=leg.right,
                order_type='MKT'
            )
            tasks.append(task)
        
        # Execute all closing orders concurrently as fallback
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(results):
            leg = request.legs[i]
            if isinstance(result, Exception):
                closing_trades.append({
                    "leg": f"{leg.symbol} {leg.expiry} {leg.strike} {leg.right}",
                    "status": "error",
                    "message": str(result)
                })
            else:
                # Briefly poll for a status update without cancelling on timeout
                await trader.wait_for_order_fill(result, timeout=5)
                closing_trades.append({
                    "leg": f"{leg.symbol} {leg.expiry} {leg.strike} {leg.right}",
                    "status": "success",
                    "order_status": result.orderStatus.status,
                    "filled": result.orderStatus.filled,
                    "remaining": result.orderStatus.remaining,
                    "order_id": getattr(getattr(result, 'order', None), 'orderId', None),
                    "perm_id": getattr(getattr(result, 'order', None), 'permId', None),
                })
                
        return _sanitize_for_json({
            "status": "submitted", 
            "trades": closing_trades,
            "note": "Strategy closed using individual leg orders as fallback"
        })

async def close_stock_position(request: CloseStockPositionRequest):
    """
    Closes a stock position by placing a market order for the opposing quantity.
    """
    trader = await connection_manager.get_trader()
    
    try:
        # The size to close is the negative of the current position quantity
        closing_size = -request.quantity
        
        # Place the stock market order
        result = await trader.place_stock_market_order(request.symbol, closing_size)
        
        # Briefly poll for a status update without cancelling on timeout
        await trader.wait_for_order_fill(result, timeout=5)
        
        response_data = {
            "status": "submitted",
            "symbol": request.symbol,
            "quantity_closed": abs(closing_size),
            "order_status": result.orderStatus.status,
            "filled": result.orderStatus.filled,
            "remaining": result.orderStatus.remaining,
            "order_id": getattr(getattr(result, 'order', None), 'orderId', None),
            "perm_id": getattr(getattr(result, 'order', None), 'permId', None),
        }
        
        return _sanitize_for_json(response_data)
        
    except Exception as e:
        return _sanitize_for_json({
            "status": "error",
            "symbol": request.symbol,
            "message": str(e)
        })
