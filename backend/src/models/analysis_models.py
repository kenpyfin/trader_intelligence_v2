from pydantic import BaseModel
from datetime import date
from typing import List, Optional, Dict, Any

class AnalysisRequest(BaseModel):
    ticker: str
    expiration_date: str # Expects YYYYMMDD format
    risk_free_rate: float = 0.045 # Default value if not provided
    analysis_method: str = 'holistic-market-edge'
    gpt_model: str = 'gpt-5' # GPT model to use for verdict analysis
    override_price: Optional[float] = None # Manual price override for testing/debugging

class RiskFreeRateRequest(BaseModel):
    tickers: List[str]


class SaveVerdictRequest(BaseModel):
    """Payload to save an analysis verdict snapshot for later comparison."""
    verdict: Dict[str, Any]
    label: Optional[str] = None
