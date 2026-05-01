import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "backend"
SRC_PATH = BACKEND_ROOT / "src"

for candidate in (SRC_PATH, BACKEND_ROOT):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from src.services import stock_selection_service


class _FakeTable:
    def __init__(self, docs):
        self._docs = docs

    def find(self, *_args, **_kwargs):
        return self._docs


class _FakeConn:
    def __init__(self, docs):
        self.table = _FakeTable(docs)


def test_load_fundamentals_accepts_market_cap_with_space(monkeypatch):
    docs = [
        {
            "Ticker": "AAPL",
            "Sector": "Technology",
            "Industry": "Consumer Electronics",
            "Refresh_Date": "2026-05-01",
            "P/E": "25",
            "P/S": "7",
            "P/Cash": "18",
            "P/Free Cash Flow": "22",
            "Gross Margin": "45%",
            "Operating Margin": "29%",
            "Profit Margin": "24%",
            "EPS (ttm)": "6.2",
            "Current Ratio": "1.1",
            "Quick Ratio": "0.9",
            "Total Debt/Equity": "120",
            "Institutional Ownership": "65%",
            "Insider Ownership": "0.4%",
            "Analyst Recom": "2.1",
            "Market Cap": "3.0T",
        }
    ]

    monkeypatch.setattr(stock_selection_service, "_latest_refresh_date", lambda: "2026-05-01")
    monkeypatch.setattr(stock_selection_service, "connect_mongo", lambda *_args, **_kwargs: _FakeConn(docs))

    frame = stock_selection_service._load_fundamentals(max_tickers=10)
    assert not frame.empty
    assert "market_cap_num" in frame.columns
    assert frame["market_cap_num"].iloc[0] > 0

