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


def test_extract_strategy_markdown_returns_strategy_section():
    markdown = """
# Stock Selection Strategies

## Active Built-In Strategy: `peer_v1`
Line A
Line B

## Strategy Selection Contract
Line C
""".strip()
    section = stock_selection_service._extract_strategy_markdown(markdown, "peer_v1")
    assert "Line A" in section
    assert "Line C" not in section


def test_latest_snapshot_query_supports_legacy_default_strategy():
    query = stock_selection_service._latest_snapshot_query("peer_v1")
    assert query["status"] == "success"
    assert "$or" in query


def test_strategy_doc_path_respects_explicit_file_env(monkeypatch, tmp_path):
    doc = tmp_path / "STOCK_SELECTION_STRATEGIES.md"
    doc.write_text("# test", encoding="utf-8")
    monkeypatch.setenv("STOCK_SELECTION_STRATEGIES_PATH", str(doc))
    resolved = stock_selection_service._strategy_doc_path("peer_v1")
    assert resolved == doc


def test_get_strategy_document_peer_v1_loads_markdown():
    result = stock_selection_service.get_strategy_document("peer_v1")
    assert result["status"] == "success"
    assert "peer_v1" in result["markdown"]
    assert "sell_premium" in result["markdown"]

