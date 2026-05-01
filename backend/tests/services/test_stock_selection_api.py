import sys
from pathlib import Path

import asyncio

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "backend"
SRC_PATH = BACKEND_ROOT / "src"

for candidate in (SRC_PATH, BACKEND_ROOT):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from src.routers.stock_selection import (
    get_latest_stock_selection,
    get_stock_selection_health,
    run_stock_selection_snapshot,
)
from src.models.stock_selection_models import StockSelectionRunRequest
from src.services import stock_selection_service


def test_latest_stock_selection_endpoint(monkeypatch):
    def fake_latest(view="all", mode="sell_premium"):
        return {
            "status": "success",
            "view": view,
            "mode": mode,
            "payload": {"metadata": {"as_of": "2026-05-01"}, "clusters": []},
        }

    monkeypatch.setattr(stock_selection_service, "get_latest_snapshot", fake_latest)
    data = asyncio.run(get_latest_stock_selection(view="clusters", mode="buy_premium"))
    assert data["status"] == "success"
    assert data["view"] == "clusters"
    assert data["mode"] == "buy_premium"


def test_stock_selection_health_endpoint(monkeypatch):
    monkeypatch.setattr(
        stock_selection_service,
        "get_health",
        lambda: {"status": "healthy", "latest_as_of": "2026-05-01"},
    )
    response = asyncio.run(get_stock_selection_health())
    assert response["status"] == "healthy"


def test_stock_selection_run_endpoint(monkeypatch):
    monkeypatch.setattr(
        stock_selection_service,
        "run_selection_snapshot_if_stale",
        lambda max_tickers=800, top_n_per_group=10: {
            "status": "success",
            "snapshot_id": "abc123",
            "tickers_ranked": 100,
        },
    )
    data = asyncio.run(
        run_stock_selection_snapshot(
            StockSelectionRunRequest(force=False, max_tickers=500, top_n_per_group=8)
        )
    )
    assert data["status"] == "success"
    assert data["snapshot_id"] == "abc123"

