import traceback

from fastapi import APIRouter, HTTPException, Query

from ..models.stock_selection_models import (
    SelectionMode,
    SelectionStrategy,
    SelectionView,
    StockSelectionRunRequest,
)
from ..services import stock_selection_service


router = APIRouter(tags=["Stock Selection"])


@router.get("/stock-selection/latest")
@router.get("/api/stock-selection/latest")
async def get_latest_stock_selection(
    view: SelectionView = Query("all"),
    mode: SelectionMode = Query("sell_premium"),
    strategy_id: SelectionStrategy = Query("peer_v1"),
):
    try:
        return stock_selection_service.get_latest_snapshot(view=view, mode=mode, strategy_id=strategy_id)
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch latest stock selection snapshot: {e}")


@router.get("/stock-selection/health")
@router.get("/api/stock-selection/health")
async def get_stock_selection_health(strategy_id: SelectionStrategy = Query("peer_v1")):
    try:
        return stock_selection_service.get_health(strategy_id=strategy_id)
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
                strategy_id=request.strategy_id,
            )
        return stock_selection_service.run_selection_snapshot_if_stale(
            max_tickers=request.max_tickers,
            top_n_per_group=request.top_n_per_group,
            strategy_id=request.strategy_id,
        )
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to run stock selection snapshot: {e}")


@router.get("/stock-selection/strategies")
@router.get("/api/stock-selection/strategies")
async def list_stock_selection_strategies():
    try:
        return stock_selection_service.list_available_strategies()
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to list stock selection strategies: {e}")


@router.get("/stock-selection/strategy-doc")
@router.get("/api/stock-selection/strategy-doc")
async def get_stock_selection_strategy_doc(strategy_id: SelectionStrategy = Query("peer_v1")):
    try:
        return stock_selection_service.get_strategy_document(strategy_id=strategy_id)
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch stock selection strategy documentation: {e}")

