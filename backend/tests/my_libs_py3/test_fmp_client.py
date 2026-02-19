import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC_PATH = ROOT / "backend" / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from my_libs_py3.fmp import FMPClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "dummy-key")
    return FMPClient()


def test_realtimequote_handles_list_payload(monkeypatch, client):
    sample = [{"symbol": "AAPL", "price": 123.45}]
    monkeypatch.setattr(FMPClient, "fetch_url_with_rate_limit", lambda self, url: sample)
    df = client.realtimequote("AAPL")
    assert not df.empty
    assert df.iloc[0]["symbol"] == "AAPL"
    assert df.iloc[0]["price"] == pytest.approx(123.45)


def test_realtimequote_normalizes_single_dict(monkeypatch, client):
    sample = {"symbol": "MSFT", "price": 405.12}
    monkeypatch.setattr(FMPClient, "fetch_url_with_rate_limit", lambda self, url: sample)
    df = client.realtimequote("MSFT")
    assert list(df.columns) == ["symbol", "price"]
    assert df.iloc[0]["symbol"] == "MSFT"


def test_realtimequote_returns_empty_on_error_dict(monkeypatch, client):
    monkeypatch.setattr(FMPClient, "fetch_url_with_rate_limit", lambda self, url: {"Error Message": "oops"})
    df = client.realtimequote("TSLA")
    assert df.empty


def test_realtimequote_returns_empty_on_exception(monkeypatch, client):
    def boom(self, url):
        raise RuntimeError("network down")

    monkeypatch.setattr(FMPClient, "fetch_url_with_rate_limit", boom)
    df = client.realtimequote("GOOG")
    assert isinstance(df, pd.DataFrame)
    assert df.empty
