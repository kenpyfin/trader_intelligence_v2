import asyncio
from datetime import datetime
import numpy as np
from typing import List

from fastapi import APIRouter, HTTPException

from src.models.analysis_models import AnalysisRequest, RiskFreeRateRequest
from src.services import analysis_service, analysis_history_service

router = APIRouter()

@router.post("/stock")
async def analyze_stock(request: AnalysisRequest):
    """
    Runs a full, multi-faceted analysis on a stock option chain.
    """
    try:
        # Convert string date from request to date object for the service
        expiration_date = datetime.strptime(request.expiration_date, '%Y%m%d').date()
        
        print(
            f"INFO: Received analysis request for ticker={request.ticker}, "
            f"expiration={request.expiration_date}, method={request.analysis_method}"
        )

        analysis_result = await analysis_service.run_full_analysis(
            ticker=request.ticker,
            expiration_date=expiration_date,
            risk_free_rate=request.risk_free_rate,
            methodology=request.analysis_method,
            gpt_model=request.gpt_model,
            override_price=request.override_price
        )

        payload_to_persist = {
            'ticker': request.ticker,
            'expiration_date': request.expiration_date,
            'risk_free_rate': request.risk_free_rate,
            'analysis_method': request.analysis_method,
            'gpt_model': request.gpt_model,
            'override_price': request.override_price,
        }

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: analysis_history_service.save_analysis_record(payload_to_persist, analysis_result)
            )
        except Exception as history_err:
            print(f"WARN: Failed to persist analysis history: {history_err}")

        return analysis_result
    except ValueError as e:
        # Handle date parsing errors
        raise HTTPException(status_code=400, detail=f"Invalid date format for expiration_date. Expected YYYYMMDD. Error: {e}")
    except Exception as e:
        import traceback
        print(f"Error in analyze_stock endpoint: {e}")
        print(traceback.format_exc())
        # Generic error handler for other issues
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_analysis_history_all(ticker: str = "", page: int = 1, page_size: int = 20):
    """Fetch paginated analysis history, optionally filtered by ticker."""
    loop = asyncio.get_running_loop()
    try:
        history = await loop.run_in_executor(
            None,
            lambda: analysis_history_service.list_history(ticker, page=page, page_size=page_size)
        )
        return history
    except Exception as e:
        import traceback
        print(f"Error while fetching analysis history: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to fetch analysis history")


@router.get("/history/{ticker}")
async def get_analysis_history(ticker: str, page: int = 1, page_size: int = 20):
    """Fetch paginated analysis history for the specified ticker."""
    return await get_analysis_history_all(ticker=ticker, page=page, page_size=page_size)


@router.delete("/history/id/{entry_id}")
async def delete_analysis_history_entry(entry_id: str):
    """Remove a single analysis history entry."""
    loop = asyncio.get_running_loop()
    try:
        deleted = await loop.run_in_executor(
            None,
            lambda: analysis_history_service.delete_history_entry(entry_id)
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="History entry not found")
        return {'status': 'success'}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Error deleting analysis history entry {entry_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to delete history entry")


@router.delete("/history/{ticker}")
async def clear_analysis_history(ticker: str):
    """Remove all history entries for a ticker."""
    loop = asyncio.get_running_loop()
    try:
        deleted_count = await loop.run_in_executor(
            None,
            lambda: analysis_history_service.clear_history_for_ticker(ticker)
        )
        return {'status': 'success', 'deleted': deleted_count}
    except Exception as e:
        import traceback
        print(f"Error clearing analysis history for {ticker}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to clear history")


@router.post("/calculate-risk-free-rate")
async def calculate_market_rate(request: RiskFreeRateRequest):
    """
    Calculates a market-implied risk-free rate from liquid ETF option chains.
    """
    try:
        # Convert string date from request to date object for the service
        expiration_date = datetime.strptime(request.expiration_date, '%Y%m%d').date()
        
        market_rate, logs = await analysis_service.calculate_market_implied_risk_free_rate(
            expiration_date=expiration_date,
            tickers=request.tickers
        )
        
        return {"risk_free_rate": market_rate, "logs": logs}
    except ValueError as e:
        # Handle date parsing errors
        raise HTTPException(status_code=400, detail=f"Invalid date format for expiration_date. Expected YYYYMMDD. Error: {e}")
    except Exception as e:
        import traceback
        print(f"Error in calculate_market_rate endpoint: {e}")
        print(traceback.format_exc())
        # Generic error handler for other issues
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug-option-chain")
async def debug_option_chain(ticker: str, expiration_date: str):
    """
    Debug endpoint to fetch and return the raw option chain DataFrame from Alpaca.
    Expiration date should be in YYYYMMDD format.
    """
    try:
        df = await analysis_service.get_raw_option_chain(ticker, expiration_date)
        if df is None or df.empty:
            return {"message": "No option chain data returned from broker."}
        
        # Convert NaN to None for JSON compatibility and return as records
        df_serializable = df.replace({np.nan: None})
        return df_serializable.to_dict('records')
    except Exception as e:
        import traceback
        print(f"Error in debug_option_chain endpoint: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
