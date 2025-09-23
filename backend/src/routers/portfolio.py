from fastapi import APIRouter, HTTPException
import traceback

from ..services import portfolio_service
from ..services.order_tracking_service import list_tracked_orders, get_tracked_order, estimate_current_mtm
from ..services.connection_manager import connection_manager
from ..models.portfolio_models import CloseStrategyRequest, CloseStockPositionRequest

router = APIRouter(
    prefix="/portfolio",
    tags=["Portfolio"],
)

@router.get("/open-positions")
async def get_open_positions():
    """Endpoint to fetch and list all open positions from the broker, grouped by type."""
    try:
        positions = await portfolio_service.get_grouped_open_positions()
        return positions
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch open positions: {e}")

@router.post("/close-strategy")
async def close_open_strategy(request: CloseStrategyRequest):
    """Endpoint to close an entire strategy by submitting opposing orders for all its legs."""
    try:
        result = await portfolio_service.close_strategy(request)
        return result
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to close strategy: {e}")

@router.post("/close-stock-position")
async def close_stock_position(request: CloseStockPositionRequest):
    """Endpoint to close a stock position by placing an opposing market order."""
    try:
        result = await portfolio_service.close_stock_position(request)
        return result
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to close stock position: {e}")

@router.get("/recent-orders")
async def get_recent_orders():
    """Endpoint to fetch the 10 most recent orders."""
    try:
        orders = await portfolio_service.get_recent_orders_service()
        return orders
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch recent orders: {e}")


@router.post("/reset-connection")
async def reset_broker_connection():
    """Force resets the broker connection to recover from timeouts or loop mismatches."""
    try:
        await connection_manager.reset_connection()
        return {"status": "success", "message": "Connection reset"}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to reset connection: {e}")


@router.get("/tracked-orders")
async def get_tracked_orders(limit: int = 25, include_mtm: bool = False):
    """
    List recently tracked one-button strategy executions. Optionally include a current MTM estimate.
    """
    try:
        items = list_tracked_orders(limit)
        if include_mtm:
            # Enrich each item with an approximate MTM value
            enriched = []
            for item in items:
                doc = get_tracked_order(item['id'])
                if not doc:
                    enriched.append({**item, 'mtm': None})
                    continue
                try:
                    mtm = await estimate_current_mtm(doc)
                except Exception as _e:
                    mtm = {'unit_mtm': None, 'total_mtm': None, 'error': str(_e)}
                enriched.append({**item, 'mtm': mtm})
            return enriched
        return items
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch tracked orders: {e}")


@router.get("/tracked-orders/{order_id}")
async def get_tracked_order_detail(order_id: str, include_mtm: bool = True):
    """Fetch a single tracked order including the saved guidance snapshot and optional MTM estimate."""
    try:
        doc = get_tracked_order(order_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Tracked order not found")
        if include_mtm:
            try:
                doc['mtm'] = await estimate_current_mtm(doc)
            except Exception as _e:
                doc['mtm'] = {'unit_mtm': None, 'total_mtm': None, 'error': str(_e)}
        return doc
    except HTTPException:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch tracked order: {e}")
