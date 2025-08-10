from collections import defaultdict
import asyncio
import pandas as pd

from ..my_libs_py3.TD_Order import IBTrader
from ..models.portfolio_models import CloseStrategyRequest

async def get_grouped_open_positions():
    """
    Fetches all open positions from the broker and groups them by contract type.
    Options are further grouped by underlying symbol.
    """
    trader = IBTrader()
    positions_df = await trader.open_positions()

    if positions_df.empty:
        return {"options": {}, "stocks": [], "others": []}

    grouped_positions = {
        "options": defaultdict(list),
        "stocks": [],
        "others": []
    }

    all_positions = positions_df.to_dict('records')

    for pos in all_positions:
        contract_type = pos.get('contract_type')
        if contract_type == 'Option':
            grouped_positions['options'][pos['symbol']].append(pos)
        elif contract_type == 'Stock':
            grouped_positions['stocks'].append(pos)
        else:
            # For futures, forex, etc.
            grouped_positions['others'].append(pos)

    # Convert defaultdict to regular dict for JSON serialization
    grouped_positions['options'] = dict(grouped_positions['options'])
    
    return grouped_positions

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
            
    return {"status": "submitted", "trades": closing_trades}
