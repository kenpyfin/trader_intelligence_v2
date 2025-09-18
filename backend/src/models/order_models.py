from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class OrderLeg(BaseModel):
    action: str  # 'BUY' or 'SELL'
    strike: float
    right: str   # 'C' or 'P'

class StrategyOrderRequest(BaseModel):
    ticker: str
    expiration_date: str # YYYY-MM-DD
    legs: List[OrderLeg]
    size: int = 1
    is_credit_spread: bool = False
    gpt_insights: Optional[Dict[str, Any]] = None  # GPT verdict insights for enhanced order context
