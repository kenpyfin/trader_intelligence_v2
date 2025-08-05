from pydantic import BaseModel, Field
from datetime import date
from typing import List

class AnalysisRequest(BaseModel):
    ticker: str
    dtes: List[int] = Field(default_factory=lambda: [30, 45, 60], description="A list of 'days to expiration' to analyze.")
    risk_free_rate: float = 0.045 # Default value if not provided

class RiskFreeRateRequest(BaseModel):
    tickers: List[str]
    expiration_date: date
