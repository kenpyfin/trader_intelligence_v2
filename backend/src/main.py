from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import date
from .analytics.analysis import run_analysis
import traceback

app = FastAPI(
    title="Trader Intelligence API",
    description="API for stock and option analysis.",
    version="1.0.0",
)

class AnalysisRequest(BaseModel):
    ticker: str
    expiration_date: date
    # Optional risk-free rate, defaults to 5%
    risk_free_rate: float = 0.05

@app.get("/")
def read_root():
    """A simple endpoint to check if the API is running."""
    return {"message": "Welcome to the Trader Intelligence API"}

@app.post("/api/analyze/stock")
async def analyze_stock(request: AnalysisRequest):
    """
    Runs a comprehensive analysis for a given stock and option expiration date.
    """
    try:
        # FastAPI will run this synchronous function in a thread pool
        results = run_analysis(
            ticker=request.ticker.upper(),
            expiration_date=request.expiration_date,
            r_current=request.risk_free_rate
        )
        return results
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
