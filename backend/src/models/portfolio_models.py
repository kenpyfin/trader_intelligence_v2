from pydantic import BaseModel
from typing import List

class PositionLeg(BaseModel):
    """Defines the structure for a single leg of an open position to be closed."""
    symbol: str
    secType: str
    expiry: str
    strike: float
    right: str
    exchange: str
    currency: str
    quantity: int # The number of contracts for this leg in the position

class CloseStrategyRequest(BaseModel):
    """The request model for the close-strategy endpoint."""
    legs: List[PositionLeg]

class CloseStockPositionRequest(BaseModel):
    """The request model for closing a stock position."""
    symbol: str
    quantity: int  # The quantity to close (should be negative of current position)
