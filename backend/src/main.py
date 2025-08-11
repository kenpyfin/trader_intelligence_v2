from fastapi import FastAPI, HTTPException
import traceback
import asyncio
from datetime import date, timedelta

from .models.analysis_models import AnalysisRequest, RiskFreeRateRequest
from .models.order_models import StrategyOrderRequest
from .services.analysis_service import run_full_analysis, get_option_expirations
from .services.macro_service import get_macro_futures_data, calculate_market_implied_risk_free_rate
from .services import broker_service
from .routers import portfolio


app = FastAPI(
    title="Trader Intelligence API",
    description="API for stock and option analysis.",
    version="1.0.0",
)

app.include_router(portfolio.router)

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

@app.post("/orders/strategy")
async def create_strategy_order(request: StrategyOrderRequest):
    """
    Places a multi-leg strategy order via the connected broker.
    This corresponds to Key Feature 3 in the PDR.
    """
    try:
        result = await broker_service.place_strategy_order(request)
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")


@app.get("/analysis/expirations/{ticker}")
async def fetch_expirations(ticker: str):
    """Fetches available option expiration dates for a given ticker."""
    try:
        expirations = await get_option_expirations(ticker)
        # Frontend is designed to handle an empty list gracefully.
        return expirations
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")


@app.post("/analysis/stock")
async def analyze_stock(request: AnalysisRequest):
    """
    Runs a full stock and option analysis for a single, user-selected expiration date.
    This endpoint serves as the core of Key Feature 1.
    """
    from datetime import datetime
    try:
        # The frontend sends expiration_date as a 'YYYYMMDD' string.
        # We need to parse it into a date object for the analysis service.
        try:
            expiration_date = datetime.strptime(request.expiration_date, '%Y%m%d').date()
        except (ValueError, TypeError):
             raise HTTPException(status_code=400, detail="Invalid expiration_date format. Expected 'YYYYMMDD'.")

        analysis_result = await asyncio.to_thread(
            run_full_analysis,
            ticker=request.ticker.upper(),
            expiration_date=expiration_date,
            r_current=request.risk_free_rate
        )

        # Check if the single analysis was successful
        if analysis_result.get("status") != "success":
            error_message = analysis_result.get("message", "Analysis failed for the selected date.")
            raise HTTPException(status_code=400, detail=error_message)

        # The frontend expects an array of results, so we wrap the single result in a list.
        # We also calculate and add the DTE (days to expiration) for display purposes.
        analysis_result['dte'] = (expiration_date - date.today()).days
        return [analysis_result]

    except Exception as e:
        # Print the full error to the console for debugging
        print(traceback.format_exc())
        # Re-raise HTTP exceptions, otherwise wrap as a 500 error.
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")
