from collections import defaultdict
import asyncio
import pandas as pd

from ..my_libs_py3.TD_Order import IBTrader
from ..models.portfolio_models import CloseStrategyRequest

async def get_open_strategies():
    """
    Fetches all open positions, filters for options, and groups them by underlying
    symbol to represent them as strategies.
    """
    trader = IBTrader()
    positions_df = await trader.open_positions()
    
    # Filter for options only. If no options, return empty dict.
    if positions_df.empty or 'contract_type' not in positions_df.columns or not (positions_df['contract_type'] == 'Option').any():
        return {}
        
    option_positions = positions_df[positions_df['contract_type'] == 'Option'].to_dict('records')
    
    # Group by underlying symbol
    strategies = defaultdict(list)
    for pos in option_positions:
        strategies[pos['symbol']].append(pos)
        
    return dict(strategies)

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
