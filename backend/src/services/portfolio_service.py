from collections import defaultdict
import asyncio
import pandas as pd
import numpy as np

from ..my_libs_py3.TD_Order import IBTrader
from ..models.portfolio_models import CloseStrategyRequest

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

async def get_grouped_open_positions():
    """
    Fetches all open positions from the broker, calculates portfolio summary metrics,
    and groups positions by contract type. Options are further grouped by underlying symbol.
    """
    trader = IBTrader()
    positions_df = await trader.open_positions()

    if positions_df.empty:
        return {
            "summary": {"market_value": 0, "unrealized_pnl": 0},
            "positions": {"options": {}, "stocks": [], "others": []}
        }

    # Ensure required columns exist before trying to sum them.
    if 'marketValue' not in positions_df.columns:
        positions_df['marketValue'] = 0
    if 'unrealizedPNL' not in positions_df.columns:
        positions_df['unrealizedPNL'] = 0
        
    # Calculate portfolio-wide summary
    total_market_value = positions_df['marketValue'].sum()
    total_unrealized_pnl = positions_df['unrealizedPNL'].sum()

    portfolio_summary = {
        "market_value": total_market_value,
        "unrealized_pnl": total_unrealized_pnl
    }
    
    # Group individual positions
    grouped_positions_data = {
        "options": defaultdict(list),
        "stocks": [],
        "others": []
    }

    all_positions = positions_df.to_dict('records')

    for pos in all_positions:
        contract_type = pos.get('contract_type')
        if contract_type == 'Option':
            grouped_positions_data['options'][pos['symbol']].append(pos)
        elif contract_type == 'Stock':
            grouped_positions_data['stocks'].append(pos)
        else:
            # For futures, forex, etc.
            grouped_positions_data['others'].append(pos)

    # Convert defaultdict to regular dict for JSON serialization
    grouped_positions_data['options'] = dict(grouped_positions_data['options'])
    
    response_data = {
        "summary": portfolio_summary,
        "positions": grouped_positions_data
    }
    return _sanitize_for_json(response_data)

async def get_recent_orders_service():
    """
    Fetches the 10 most recent orders from the broker.
    """
    trader = IBTrader()
    recent_orders = await trader.get_recent_orders(count=10)
    # The data is already sanitized in the trader method by creating dicts,
    # but an extra _sanitize_for_json call ensures full compliance.
    return _sanitize_for_json(recent_orders)

async def close_strategy(request: CloseStrategyRequest):
    """
    Closes a strategy by placing opposing market orders for each of its legs concurrently.
    """
    trader = IBTrader()
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
    
    # Execute all closing orders concurrently.
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results.
    for i, result in enumerate(results):
        leg = request.legs[i]
        if isinstance(result, Exception):
            closing_trades.append({
                "leg": f"{leg.symbol} {leg.expiry} {leg.strike} {leg.right}",
                "status": "error",
                "message": str(result)
            })
        else:
            # Wait for the trade to get a status update, but with a short timeout.
            await trader.wait_for_order_fill(result, timeout=5)
            closing_trades.append({
                "leg": f"{leg.symbol} {leg.expiry} {leg.strike} {leg.right}",
                "status": "success",
                "order_status": result.orderStatus.status,
                "filled": result.orderStatus.filled,
                "remaining": result.orderStatus.remaining,
            })
            
    return _sanitize_for_json({"status": "submitted", "trades": closing_trades})
