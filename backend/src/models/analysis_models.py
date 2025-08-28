from pydantic import BaseModel
from datetime import date
from typing import List

class AnalysisRequest(BaseModel):
    ticker: str
    expiration_date: str # Expects YYYYMMDD format
    risk_free_rate: float = 0.045 # Default value if not provided
    analysis_method: str = 'holistic-market-edge'

class RiskFreeRateRequest(BaseModel):
    tickers: List[str]
