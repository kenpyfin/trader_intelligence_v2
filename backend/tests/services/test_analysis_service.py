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

from src.services import analysis_service


class DummyTrader:
    async def get_option_expirations(self, symbol: str):
        assert symbol.upper() == "AAPL"
        return [
            "20240419",
            "20240426",
            "20240315",
            "20240405",
            "20240412",
            "20240419",
            "20240517",
            "20240621",
            "20240719",
            "20240816",
            "20240920",
            "20241018",
        ]


def test_get_option_expirations_sorts_all_unique(monkeypatch):
    dummy_trader = DummyTrader()

    async def fake_get_trader():
        return dummy_trader

    monkeypatch.setattr(analysis_service.connection_manager, "get_trader", fake_get_trader)

    expirations = asyncio.run(analysis_service.get_option_expirations("aapl"))

    assert expirations == [
        "20240315",
        "20240405",
        "20240412",
        "20240419",
        "20240426",
        "20240517",
        "20240621",
        "20240719",
        "20240816",
        "20240920",
        "20241018",
    ]
