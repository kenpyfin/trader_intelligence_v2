import asyncio
import traceback
from src.models.order_models import StrategyOrderRequest
from .order_tracking_service import record_strategy_execution
from .connection_manager import connection_manager

async def place_strategy_order(order_request: StrategyOrderRequest):
    """
    Connects to IB and places a complex strategy order.
    Enhanced with GPT verdict insights for better trade context.
    """
    try:
        # Log GPT insights if available
        if order_request.gpt_insights:
            print(f"DEBUG: Executing strategy with GPT insights:")
            print(f"  - AI Bias: {order_request.gpt_insights.get('final_bias', 'Unknown')}")
            print(f"  - Actionable Ideas: {len(order_request.gpt_insights.get('actionable_ideas', []))} items")
            print(f"  - Risk Factors: {len(order_request.gpt_insights.get('risk_factors', []))} items")
            print(f"  - Rationale: {order_request.gpt_insights.get('rationale', '')[:100]}...")
        else:
            print(f"DEBUG: Executing strategy without GPT insights (model-based analysis)")
            
        trader = await connection_manager.get_trader()
        
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
            # Include GPT context in success message
            gpt_context = ""
            if order_request.gpt_insights:
                bias = order_request.gpt_insights.get('final_bias', 'Unknown')
                gpt_context = f" (AI Bias: {bias})"
                
            # Try to extract identifiers from the IB trade object
            ib_order_id = None
            ib_perm_id = None
            try:
                ib_order_id = getattr(getattr(trade, 'order', None), 'orderId', None)
                ib_perm_id = getattr(getattr(trade, 'order', None), 'permId', None)
            except Exception:
                pass

            # Persist a tracked-order record linking execution to guidance snapshot
            try:
                tracking = record_strategy_execution(
                    order_request=order_request,
                    trade_info={
                        'order_status': trade.orderStatus.status,
                        'filled': trade.orderStatus.filled,
                        'remaining': trade.orderStatus.remaining,
                        'message': f"Order for {order_request.size} {order_request.ticker} strategy sent{gpt_context}.",
                    },
                    ib_order_id=ib_order_id,
                    ib_perm_id=ib_perm_id,
                )
                tracking_id = tracking.get('id')
            except Exception as _e:
                print(f"WARN: Failed to record tracked order: {_e}")
                tracking_id = None

            return {
                "status": "success",
                "message": f"Order for {order_request.size} {order_request.ticker} strategy sent{gpt_context}.",
                "order_status": trade.orderStatus.status,
                "filled": trade.orderStatus.filled,
                "remaining": trade.orderStatus.remaining,
                "gpt_insights_included": bool(order_request.gpt_insights),
                "tracking_id": tracking_id,
                "ib_order_id": ib_order_id,
                "ib_perm_id": ib_perm_id,
            }
        else:
            return {"status": "error", "message": "Failed to place order or get status from broker."}

    except Exception as e:
        print(traceback.format_exc())
        return {"status": "error", "message": str(e)}
