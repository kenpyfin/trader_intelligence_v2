from pydantic import BaseModel
from datetime import date
from typing import List

class AnalysisRequest(BaseModel):
    ticker: str
    risk_free_rate: float = 0.045 # Default value if not provided

class RiskFreeRateRequest(BaseModel):
    tickers: List[str]
