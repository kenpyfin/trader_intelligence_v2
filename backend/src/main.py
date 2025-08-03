from fastapi import FastAPI, HTTPException
import traceback
from datetime import date

from .models.analysis_models import AnalysisRequest
from .services.analysis_service import run_full_analysis

app = FastAPI(
    title="Trader Intelligence API",
    description="API for stock and option analysis.",
    version="1.0.0",
)

@app.get("/")
def read_root():
    """A simple endpoint to check if the API is running."""
    return {"message": "Welcome to the Trader Intelligence API"}

@app.post("/api/analyze/stock")
async def analyze_stock(request: AnalysisRequest):
    """
    Runs a full stock and option analysis based on the provided ticker and expiration date.
    This endpoint serves as the core of Key Feature 1.
    """
    try:
        # FastAPI runs synchronous functions in a thread pool, preventing blocking.
        analysis_result = run_full_analysis(
            ticker=request.ticker.upper(),
            expiration_date=request.expiration_date
        )
        
        if analysis_result.get("status") == "error":
            # Return a 400 Bad Request for user-side errors (e.g., bad ticker)
            raise HTTPException(status_code=400, detail=analysis_result.get("message", "Analysis failed due to invalid input."))
        
        return analysis_result

    except Exception as e:
        # Print the full error to the console for debugging
        print(traceback.format_exc())
        # Return a 500 Internal Server Error for unexpected issues
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")
