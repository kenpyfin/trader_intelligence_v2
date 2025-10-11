from collections import defaultdict
import asyncio
import pandas as pd
import numpy as np

from ..models.portfolio_models import CloseStrategyRequest, CloseStockPositionRequest
from .connection_manager import connection_manager

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
        "available_cash": account_details.get('buying_power'),
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
    
    # Step 5: Combine and return.
    response_data = {
        "summary": portfolio_summary,
        "positions": grouped_positions_data
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
