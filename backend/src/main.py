from fastapi import FastAPI, HTTPException
import traceback
from datetime import date, timedelta

from .models.analysis_models import AnalysisRequest, RiskFreeRateRequest
from .services.analysis_service import run_full_analysis
from .services.macro_service import get_macro_futures_data, calculate_market_implied_risk_free_rate

app = FastAPI(
    title="Trader Intelligence API",
    description="API for stock and option analysis.",
    version="1.0.0",
)

@app.get("/")
def read_root():
    """A simple endpoint to check if the API is running."""
    return {"message": "Welcome to the Trader Intelligence API"}

@app.get("/macro-data")
def get_macro_data():
    """Endpoint to fetch macro economic data (futures)."""
    try:
        data = get_macro_futures_data()
        if "error" in data:
            raise HTTPException(status_code=500, detail=data["error"])
        return data
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@app.post("/calculate-risk-free-rate")
async def get_risk_free_rate(request: RiskFreeRateRequest):
    """Calculates the market-implied risk-free rate from a basket of ETFs."""
    try:
        # The service now calculates the rate across multiple standard expiries automatically.
        rate, logs = await calculate_market_implied_risk_free_rate(
            tickers=request.tickers
        )
        return {"risk_free_rate": rate, "logs": logs}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@app.post("/analyze/stock")
async def analyze_stock(request: AnalysisRequest):
    """
    Runs a full stock and option analysis for multiple, standard expiration dates (DTEs).
    This endpoint serves as the core of Key Feature 1.
    """
    try:
        all_results = []
        # Define a standard set of DTEs to analyze for a comprehensive view.
        # This covers short-term, medium-term, and quarterly cycles.
        standard_dtes_to_analyze = [30, 45, 60, 90]
        # Loop through each standard Day to Expiration (DTE)
        for dte in standard_dtes_to_analyze:
            expiration_date = date.today() + timedelta(days=dte)
            
            # FastAPI runs synchronous functions in a thread pool, preventing blocking.
            analysis_result = run_full_analysis(
                ticker=request.ticker.upper(),
                expiration_date=expiration_date,
                r_current=request.risk_free_rate
            )
            
            # We only add successful analyses to the final result list.
            # Errors for a single DTE (e.g., no options available) are logged by the service
            # but don't stop the entire request.
            if analysis_result.get("status") == "success":
                # Add the DTE to the result for easy reference on the frontend
                analysis_result['dte'] = dte
                all_results.append(analysis_result)

        if not all_results:
             raise HTTPException(status_code=400, detail="Analysis failed for all requested expiration dates. This could be due to no options being available for those dates.")

        # The frontend will now receive an array of analysis results.
        return all_results

    except Exception as e:
        # Print the full error to the console for debugging
        print(traceback.format_exc())
        # Return a 500 Internal Server Error for unexpected issues
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")
