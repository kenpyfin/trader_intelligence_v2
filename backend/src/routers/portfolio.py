from fastapi import APIRouter, HTTPException
import traceback

from ..services import portfolio_service
from ..models.portfolio_models import CloseStrategyRequest

router = APIRouter(
    prefix="/portfolio",
    tags=["Portfolio"],
)

@router.get("/open-strategies")
async def get_open_strategies():
    """Endpoint to fetch and list all open option strategies from the broker."""
    try:
        strategies = await portfolio_service.get_open_strategies()
        return strategies
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch open strategies: {e}")

@router.post("/close-strategy")
async def close_open_strategy(request: CloseStrategyRequest):
    """Endpoint to close an entire strategy by submitting opposing orders for all its legs."""
    try:
        result = await portfolio_service.close_strategy(request)
        return result
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to close strategy: {e}")
