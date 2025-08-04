from pydantic import BaseModel
from datetime import date
from typing import List

class AnalysisRequest(BaseModel):
    ticker: str
    expiration_date: date
    risk_free_rate: float = 0.045 # Default value if not provided

class RiskFreeRateRequest(BaseModel):
    tickers: List[str]
    expiration_date: date
