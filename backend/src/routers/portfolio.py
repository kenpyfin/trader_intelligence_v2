from fastapi import APIRouter, HTTPException
import traceback

from ..services import portfolio_service
from ..models.portfolio_models import CloseStrategyRequest

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

@router.get("/recent-orders")
async def get_recent_orders():
    """Endpoint to fetch the 10 most recent orders."""
    try:
        orders = await portfolio_service.get_recent_orders_service()
        return orders
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch recent orders: {e}")
