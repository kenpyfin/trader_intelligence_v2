import asyncio
import traceback
from typing import List, Optional
from src.models.order_models import StrategyOrderRequest
from . import verdict_service
from .order_tracking_service import record_strategy_execution
from .connection_manager import connection_manager

async def get_current_price(symbol: str) -> Optional[float]:
    """Get the current price of a symbol from the broker."""
    try:
        trader = await connection_manager.get_trader()
        price = await trader.realtimequote(symbol)
        return price
    except Exception as e:
        print(f"ERROR: Failed to get current price for {symbol}: {e}")
        return None

async def get_available_strikes(symbol: str, expiration_date: str) -> List[float]:
    """Get available option strikes for a symbol and expiration date."""
    try:
        trader = await connection_manager.get_trader()
        # Get the option chain for this symbol and expiration
        option_chain_df = await trader.get_option_chain_df(symbol, expiration_date)
        if option_chain_df.empty:
            print(f"WARNING: No option chain data found for {symbol} at {expiration_date}")
            return []
            
        # Extract unique strikes
        if 'Strike' in option_chain_df.columns:
            strikes = option_chain_df['Strike'].dropna().unique().tolist()
            return [float(strike) for strike in strikes]
        else:
            print(f"ERROR: Option chain does not contain Strike column. Columns: {option_chain_df.columns.tolist()}")
            return []
    except Exception as e:
        print(f"ERROR: Failed to get available strikes for {symbol} at {expiration_date}: {e}")
        return []

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
        
        # Alpaca expects expiry in YYYYMMDD format for internal processing
        # The _normalize_expiry function in TD_Order.py will convert it to the required format
        expiry_date_broker_format = order_request.expiration_date
        
        # Debug log the incoming legs
        print(f"DEBUG: Incoming legs from order request:")
        for i, leg in enumerate(order_request.legs):
            print(f"  Leg {i+1}: action={leg.action}, strike={leg.strike}, right={leg.right}, expiry={leg.expiry}, secType={leg.secType}")
            if leg.strike is None and leg.strike_offset is not None:
                print(f"  Leg {i+1} has strike_offset={leg.strike_offset} but no strike value")
        
        # Enrich leg data for IBTrader
        enriched_legs = []
        for leg in order_request.legs:
            # Handle strike_offset if strike is None
            leg_strike = leg.strike
            if leg_strike is None and hasattr(leg, 'strike_offset') and leg.strike_offset is not None:
                # Calculate the actual strike price from the offset
                try:
                    # First, get the current price of the underlying
                    current_price = await get_current_price(order_request.ticker)
                    if current_price is None:
                        raise ValueError(f"Could not determine current price for {order_request.ticker}")
                    
                    print(f"DEBUG: Current price for {order_request.ticker}: ${current_price}")
                    
                    # Parse the offset format (e.g., ATM, ITM1, OTM2)
                    offset_type = ''.join([c for c in leg.strike_offset if not c.isdigit()])
                    offset_value = ''.join([c for c in leg.strike_offset if c.isdigit()])
                    offset_value = int(offset_value) if offset_value else 0
                    
                    # Get the available strikes for this expiration
                    strikes = await get_available_strikes(order_request.ticker, order_request.expiration_date)
                    if not strikes:
                        print(f"WARNING: No option chain data available for {order_request.ticker} at {order_request.expiration_date}")
                        print("Using fallback strike calculation based on current price...")
                        # Fallback: Generate synthetic strikes based on current price
                        # This is less accurate but allows us to proceed when option chain data is unavailable
                        strike_increment = max(1.0, round(current_price * 0.01))  # Default 1% increment
                        base_strike = round(current_price / strike_increment) * strike_increment  # Round to nearest increment
                        
                        # Generate strikes around the current price
                        num_strikes = 10  # Generate 10 strikes above and below
                        strikes = [base_strike + (i - num_strikes) * strike_increment for i in range(num_strikes * 2 + 1)]
                        print(f"Generated synthetic strikes: {strikes}")
                        
                        if not strikes:
                            raise ValueError(f"Could not generate strikes for {order_request.ticker} at {order_request.expiration_date}")
                    
                    # Sort strikes in ascending order
                    strikes.sort()
                    
                    # Find the ATM strike (closest to current price)
                    atm_index = min(range(len(strikes)), key=lambda i: abs(strikes[i] - current_price))
                    atm_strike = strikes[atm_index]
                    
                    print(f"DEBUG: ATM strike for {order_request.ticker}: ${atm_strike}")
                    
                    # Calculate the target strike based on offset
                    if offset_type == 'ATM':
                        leg_strike = atm_strike
                    elif offset_type == 'ITM':
                        # For calls, ITM means lower strikes; for puts, ITM means higher strikes
                        direction = -1 if leg.right == 'C' else 1
                        target_index = atm_index + (direction * offset_value)
                        target_index = max(0, min(target_index, len(strikes) - 1))  # Ensure within bounds
                        leg_strike = strikes[target_index]
                    elif offset_type == 'OTM':
                        # For calls, OTM means higher strikes; for puts, OTM means lower strikes
                        direction = 1 if leg.right == 'C' else -1
                        target_index = atm_index + (direction * offset_value)
                        target_index = max(0, min(target_index, len(strikes) - 1))  # Ensure within bounds
                        leg_strike = strikes[target_index]
                    else:
                        raise ValueError(f"Unknown strike offset format: {leg.strike_offset}")
                    
                    print(f"DEBUG: Calculated strike for {leg.strike_offset} {leg.right}: ${leg_strike}")
                except Exception as e:
                    print(f"ERROR: Failed to calculate strike from offset {leg.strike_offset}: {str(e)}")
                    raise ValueError(f"Failed to calculate strike from offset {leg.strike_offset}: {str(e)}")
            
            if leg_strike is None:
                print(f"WARNING: Leg has no strike value: {leg}")
            
            enriched_legs.append({
                'action': leg.action,
                'strike': leg_strike,  # Use the potentially calculated strike value
                'right': leg.right,
                'expiry': expiry_date_broker_format,
                'quantity': 1 # Ratio within the spread is 1:1
            })

        # If no AI guidance provided, pull the latest saved verdict for this ticker/expiration
        insights_to_store = order_request.gpt_insights
        if not insights_to_store:
            latest_verdict = verdict_service.get_latest_verdict_for(
                order_request.ticker, order_request.expiration_date
            )
            if latest_verdict and isinstance(latest_verdict.get('data'), dict):
                data = latest_verdict['data']
                # If a full gpt_verdict object exists in the saved analysis, use it directly.
                # This ensures all guidance (entry/exit signals, etc.) is preserved.
                if data.get('gpt_verdict') and isinstance(data['gpt_verdict'], dict):
                    insights_to_store = data['gpt_verdict']
                else:
                    # Fallback to creating a minimal guidance object if there's no full gpt_verdict
                    insights_to_store = {
                        'final_bias': data.get('final_bias'),
                        'actionable_ideas': data.get('actionable_ideas'),
                        'risk_factors': data.get('risk_factors'),
                    }
                    if not any(v is not None for v in insights_to_store.values()):
                        insights_to_store = None

        # For credit spreads, the order size must be negative (to SELL the spread)
        order_size = -order_request.size if order_request.is_credit_spread else order_request.size

        # Log the enriched legs data for debugging
        print(f"DEBUG: Placing strategy order for {order_request.ticker} with legs:")
        for i, leg in enumerate(enriched_legs):
            print(f"  Leg {i+1}: {leg}")
            
        # Validate that each leg has the required fields and they are not None
        for i, leg in enumerate(enriched_legs):
            missing = []
            if leg.get('expiry') is None: missing.append('expiry')
            if leg.get('strike') is None: missing.append('strike')
            if leg.get('right') is None: missing.append('right')
            
            if missing:
                print(f"ERROR: Leg {i+1} validation failed with data: {leg}")
                raise ValueError(f"Leg {i+1} is missing required fields: {', '.join(missing)}")
        
        try:
            trade = await trader.place_strategy_order(
                symbol=order_request.ticker,
                legs_data=enriched_legs,
                size=order_size,
                order_type='MKT',
                open_position=True,
            )
        except Exception as e:
            print(f"ERROR: Failed to place strategy order: {e}")
            print(f"DEBUG: Order details - Symbol: {order_request.ticker}, Size: {order_size}, Legs: {enriched_legs}")
            raise

        if trade and hasattr(trade, 'orderStatus') and trade.orderStatus:
            # Include GPT context in success message
            gpt_context = ""
            if order_request.gpt_insights:
                bias = order_request.gpt_insights.get('final_bias', 'Unknown')
                gpt_context = f" (AI Bias: {bias})"
                
            # Try to extract identifiers from the IB trade object
            broker_order_id = None
            broker_perm_id = None
            try:
                broker_order_id = getattr(getattr(trade, 'order', None), 'orderId', None)
                broker_perm_id = getattr(getattr(trade, 'order', None), 'permId', None)
            except Exception:
                pass

            # Persist a tracked-order record linking execution to guidance snapshot
            try:
                # Ensure guidance snapshot is carried into the tracked record
                enriched_request = order_request.copy(update={'gpt_insights': insights_to_store})
                tracking = record_strategy_execution(
                    order_request=enriched_request,
                    trade_info={
                        'order_status': trade.orderStatus.status,
                        'filled': trade.orderStatus.filled,
                        'remaining': trade.orderStatus.remaining,
                        'message': f"Order for {order_request.size} {order_request.ticker} strategy sent{gpt_context}.",
                    },
                    broker_order_id=broker_order_id,
                    broker_perm_id=broker_perm_id,
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
                "gpt_insights_included": bool(insights_to_store),
                "tracking_id": tracking_id,
                "broker_order_id": broker_order_id,
                "broker_perm_id": broker_perm_id,
            }
        else:
            return {"status": "error", "message": "Failed to place order or get status from broker."}

    except Exception as e:
        print(traceback.format_exc())
        return {"status": "error", "message": str(e)}
