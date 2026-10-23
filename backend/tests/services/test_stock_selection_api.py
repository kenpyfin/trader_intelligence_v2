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
    get_stock_selection_strategy_doc,
    list_stock_selection_strategies,
    get_stock_selection_health,
    run_stock_selection_snapshot,
)
from src.models.stock_selection_models import StockSelectionRunRequest
from src.services import stock_selection_service


def test_latest_stock_selection_endpoint(monkeypatch):
    def fake_latest(view="all", mode="sell_premium", strategy_id="peer_v1"):
        return {
            "status": "success",
            "view": view,
            "mode": mode,
            "strategy_id": strategy_id,
            "payload": {"metadata": {"as_of": "2026-05-01"}, "clusters": []},
        }

    monkeypatch.setattr(stock_selection_service, "get_latest_snapshot", fake_latest)
    data = asyncio.run(get_latest_stock_selection(view="clusters", mode="buy_premium", strategy_id="peer_v1"))
    assert data["status"] == "success"
    assert data["view"] == "clusters"
    assert data["mode"] == "buy_premium"
    assert data["strategy_id"] == "peer_v1"


def test_stock_selection_health_endpoint(monkeypatch):
    monkeypatch.setattr(
        stock_selection_service,
        "get_health",
        lambda strategy_id="peer_v1": {"status": "healthy", "latest_as_of": "2026-05-01", "strategy_id": strategy_id},
    )
    response = asyncio.run(get_stock_selection_health(strategy_id="peer_v1"))
    assert response["status"] == "healthy"
    assert response["strategy_id"] == "peer_v1"


def test_stock_selection_run_endpoint(monkeypatch):
    monkeypatch.setattr(
        stock_selection_service,
        "run_selection_snapshot_if_stale",
        lambda max_tickers=800, top_n_per_group=10, strategy_id="peer_v1": {
            "status": "success",
            "snapshot_id": "abc123",
            "tickers_ranked": 100,
            "strategy_id": strategy_id,
        },
    )
    data = asyncio.run(
        run_stock_selection_snapshot(
            StockSelectionRunRequest(force=False, max_tickers=500, top_n_per_group=8, strategy_id="peer_v1")
        )
    )
    assert data["status"] == "success"
    assert data["snapshot_id"] == "abc123"
    assert data["strategy_id"] == "peer_v1"


def test_stock_selection_strategy_doc_endpoint(monkeypatch):
    monkeypatch.setattr(
        stock_selection_service,
        "get_strategy_document",
        lambda strategy_id="peer_v1": {
            "status": "success",
            "strategy_id": strategy_id,
            "title": "Strategy peer_v1",
            "markdown": "## Active Built-In Strategy: `peer_v1`",
        },
    )
    response = asyncio.run(get_stock_selection_strategy_doc(strategy_id="peer_v1"))
    assert response["status"] == "success"
    assert response["strategy_id"] == "peer_v1"


def test_stock_selection_strategies_endpoint(monkeypatch):
    monkeypatch.setattr(
        stock_selection_service,
        "list_available_strategies",
        lambda: {
            "status": "success",
            "strategies": [{"strategy_id": "peer_v1", "label": "Peer Classification v1"}],
        },
    )
    response = asyncio.run(list_stock_selection_strategies())
    assert response["status"] == "success"
    assert response["strategies"][0]["strategy_id"] == "peer_v1"

