from fastapi import APIRouter, HTTPException
from src.models.analysis_models import AnalysisRequest
from src.services import analysis_service
from datetime import datetime

router = APIRouter()

@router.post("/stock")
async def analyze_stock(request: AnalysisRequest):
    """
    Runs a full, multi-faceted analysis on a stock option chain.
    """
    try:
        # Convert string date from request to date object for the service
        expiration_date = datetime.strptime(request.expiration_date, '%Y%m%d').date()
        
        analysis_result = await analysis_service.run_full_analysis(
            ticker=request.ticker,
            expiration_date=expiration_date,
            risk_free_rate=request.risk_free_rate,
            methodology=request.analysis_method
        )
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
