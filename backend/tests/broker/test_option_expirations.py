import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "backend"
SRC_PATH = BACKEND_ROOT / "src"

for candidate in (SRC_PATH, BACKEND_ROOT):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from my_libs_py3.TD_Order import _extract_expiration_list  # type: ignore


class FakeModel:
    def __init__(self, expiration_date):
        self.expiration_date = expiration_date

    def model_dump(self):
        return {"expiration_date": self.expiration_date}


def test_extract_expiration_list_handles_alpaca_chain():
    sample_chain = {
        "AAPL251017C00200000": {
            "symbol": "AAPL251017C00200000",
            "latest_quote": {
                "symbol": "AAPL251017C00200000",
                "timestamp": datetime(2025, 10, 3, 19, 59, 59, tzinfo=datetime.now().astimezone().tzinfo),
            },
            "latest_trade": {
                "symbol": "AAPL251017C00200000",
                "timestamp": datetime(2025, 10, 3, 19, 50, 9),
            },
        },
        "AAPL251017P00200000": {
            "symbol": "AAPL251017P00200000",
            "latest_quote": {
                "symbol": "AAPL251017P00200000",
                "timestamp": datetime(2025, 10, 3, 19, 59, 59),
            },
            "latest_trade": {
                "symbol": "AAPL251017P00200000",
                "timestamp": datetime(2025, 10, 3, 19, 50, 9),
            },
        },
        "meta": {
            "generated_at": datetime(2024, 10, 5),
            "expirations": ["2025-10-17", FakeModel(date(2026, 1, 17))],
        },
    }

    expirations = _extract_expiration_list(sample_chain)

    assert expirations == {"20251017", "20260117"}
