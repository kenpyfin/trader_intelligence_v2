import traceback

from fastapi import APIRouter, HTTPException, Query

from ..models.stock_selection_models import SelectionMode, SelectionView, StockSelectionRunRequest
from ..services import stock_selection_service


router = APIRouter(tags=["Stock Selection"])


@router.get("/stock-selection/latest")
@router.get("/api/stock-selection/latest")
async def get_latest_stock_selection(
    view: SelectionView = Query("all"),
    mode: SelectionMode = Query("sell_premium"),
):
    try:
        return stock_selection_service.get_latest_snapshot(view=view, mode=mode)
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch latest stock selection snapshot: {e}")


@router.get("/stock-selection/health")
@router.get("/api/stock-selection/health")
async def get_stock_selection_health():
    try:
        return stock_selection_service.get_health()
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch stock selection health: {e}")


@router.post("/stock-selection/run")
@router.post("/api/stock-selection/run")
async def run_stock_selection_snapshot(request: StockSelectionRunRequest):
    try:
        if request.force:
            return stock_selection_service.run_selection_snapshot(
                max_tickers=request.max_tickers,
                top_n_per_group=request.top_n_per_group,
            )
        return stock_selection_service.run_selection_snapshot_if_stale(
            max_tickers=request.max_tickers,
            top_n_per_group=request.top_n_per_group,
        )
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to run stock selection snapshot: {e}")

