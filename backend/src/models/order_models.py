from pydantic import BaseModel
from typing import List

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
