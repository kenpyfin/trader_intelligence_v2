from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


SelectionView = Literal["all", "clusters", "sectors", "regimes"]
SelectionMode = Literal["sell_premium", "buy_premium"]


class StockSelectionRunRequest(BaseModel):
    max_tickers: int = Field(800, ge=50, le=5000, description="Max universe size to evaluate")
    top_n_per_group: int = Field(10, ge=1, le=50, description="Top stocks to keep per grouping")
    force: bool = Field(False, description="Force recompute even if a fresh cache exists")


class StockSelectionRunResponse(BaseModel):
    status: Literal["success", "error"]
    snapshot_id: Optional[str] = None
    as_of: Optional[str] = None
    tickers_considered: int = 0
    tickers_ranked: int = 0
    tickers_excluded: int = 0
    message: Optional[str] = None


class RankedStock(BaseModel):
    ticker: str
    mode: SelectionMode
    selection_score: float
    cluster_rank: int
    global_rank: int
    confidence_score: float
    cluster_id: str
    cluster_size: int
    cluster_coherence: float
    regime_bucket: str
    iv_rank: Optional[float] = None
    fundamental_composite: float
    trend_composite: float
    liquidity_composite: float
    reasons: List[str] = Field(default_factory=list)


class RankedGroup(BaseModel):
    group_key: str
    group_label: str
    stocks: List[RankedStock] = Field(default_factory=list)


class StockSelectionSnapshotMetadata(BaseModel):
    as_of: str
    generated_at: datetime
    model_version: str
    freshness_minutes: int
    tickers_considered: int
    tickers_ranked: int
    tickers_excluded: int
    exclusions_by_reason: Dict[str, int] = Field(default_factory=dict)


class StockSelectionSnapshotPayload(BaseModel):
    metadata: StockSelectionSnapshotMetadata
    clusters: List[RankedGroup] = Field(default_factory=list)
    sectors: List[RankedGroup] = Field(default_factory=list)
    regimes: List[RankedGroup] = Field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None


class StockSelectionLatestResponse(BaseModel):
    status: Literal["success", "error"]
    view: SelectionView = "all"
    mode: SelectionMode = "sell_premium"
    payload: Optional[StockSelectionSnapshotPayload] = None
    message: Optional[str] = None


class StockSelectionHealthResponse(BaseModel):
    status: Literal["healthy", "stale", "empty"]
    latest_as_of: Optional[str] = None
    generated_at: Optional[datetime] = None
    age_minutes: Optional[int] = None
    freshness_target_minutes: int = 24 * 60
    details: Dict[str, Any] = Field(default_factory=dict)

