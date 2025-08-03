from pydantic import BaseModel
from datetime import date

class AnalysisRequest(BaseModel):
    ticker: str
    expiration_date: date
    # The risk free rate is now hardcoded in the service layer, but can be added back here if needed.
    # risk_free_rate: float = 0.05
