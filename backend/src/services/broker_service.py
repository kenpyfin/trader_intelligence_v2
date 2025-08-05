import asyncio
import traceback
from src.my_libs_py3.TD_Order import IBTrader
from src.models.order_models import StrategyOrderRequest

async def place_strategy_order(order_request: StrategyOrderRequest):
    """
    Connects to IB and places a complex strategy order.
    """
    trader = None
    try:
        trader = IBTrader() # This connects on init
        
        # IBTrader's place_strategy_order expects YYYYMMDD format
        expiry_date_ib_format = order_request.expiration_date.replace('-', '')
        
        # Enrich leg data for IBTrader
        enriched_legs = []
        for leg in order_request.legs:
            enriched_legs.append({
                'action': leg.action,
                'strike': leg.strike,
                'right': leg.right,
                'expiry_date': expiry_date_ib_format,
                'quantity': 1 # Ratio within the spread is 1:1
            })

        # For credit spreads, the order size must be negative (to SELL the spread)
        order_size = -order_request.size if order_request.is_credit_spread else order_request.size

        trade = await trader.place_strategy_order(
            symbol=order_request.ticker,
            legs_data=enriched_legs,
            size=order_size,
            order_type='MKT'
        )

        if trade and hasattr(trade, 'orderStatus') and trade.orderStatus:
             return {
                "status": "success",
                "message": f"Order for {order_request.size} {order_request.ticker} strategy sent.",
                "order_status": trade.orderStatus.status,
                "filled": trade.orderStatus.filled,
                "remaining": trade.orderStatus.remaining,
            }
        else:
            return {"status": "error", "message": "Failed to place order or get status from broker."}

    except Exception as e:
        print(traceback.format_exc())
        return {"status": "error", "message": str(e)}
    finally:
        if trader:
            trader.disconnect()
