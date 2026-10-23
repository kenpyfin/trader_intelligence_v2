"""Unit tests for pair_position_service (no live Mongo/broker)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "backend"
SRC_PATH = BACKEND_ROOT / "src"
for candidate in (str(SRC_PATH), str(BACKEND_ROOT), str(ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from src.services.pair_position_service import (  # noqa: E402
    group_stock_pairs,
    parse_pair_collection_name,
)


def _stock(symbol, position, unrealized=0.0, avg_cost=None):
    return {
        "symbol": symbol,
        "position": position,
        "avgCost": avg_cost if avg_cost is not None else abs(position) * 10,
        "marketValue": position * 12,
        "unrealizedPNL": unrealized,
        "contract_type": "Stock",
    }


def _log(ticker1, ticker2, size1, size2, last_trade_at="2026-09-01T14:32:00+00:00"):
    return {
        "pair_id": f"{ticker1}_{ticker2}",
        "ticker1": ticker1,
        "ticker2": ticker2,
        "size1": size1,
        "size2": size2,
        "last_trade_at": last_trade_at,
    }


class TestParsePairCollectionName(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_pair_collection_name("KO_PEP"), ("KO", "PEP"))
        self.assertEqual(parse_pair_collection_name("bj_su"), ("BJ", "SU"))

    def test_invalid(self):
        self.assertIsNone(parse_pair_collection_name("FOO_BAR_BAZ"))
        self.assertIsNone(parse_pair_collection_name("FOO"))
        self.assertIsNone(parse_pair_collection_name(""))
        self.assertIsNone(parse_pair_collection_name(None))


class TestGroupStockPairs(unittest.TestCase):
    def test_matched_both_legs(self):
        stocks = [_stock("KO", -100, 10.0), _stock("PEP", 50, -5.0)]
        logs = [_log("KO", "PEP", -100, 50)]
        result = group_stock_pairs(stocks, open_pair_logs=logs)
        self.assertEqual(len(result["pairs"]), 1)
        pair = result["pairs"][0]
        self.assertEqual(pair["status"], "matched")
        self.assertEqual(pair["combined_unrealized_pnl"], 5.0)
        self.assertEqual(result["dangling"], [])
        self.assertTrue(all(leg["qty_match"] for leg in pair["legs"]))

    def test_size_mismatch(self):
        stocks = [_stock("KO", -80), _stock("PEP", 50)]
        logs = [_log("KO", "PEP", -100, 50)]
        result = group_stock_pairs(stocks, open_pair_logs=logs)
        pair = result["pairs"][0]
        self.assertEqual(pair["status"], "size_mismatch")
        ko_leg = next(l for l in pair["legs"] if l["symbol"] == "KO")
        pep_leg = next(l for l in pair["legs"] if l["symbol"] == "PEP")
        self.assertFalse(ko_leg["qty_match"])
        self.assertTrue(pep_leg["qty_match"])
        self.assertEqual(result["dangling"], [])

    def test_missing_leg(self):
        stocks = [_stock("KO", -100)]
        logs = [_log("KO", "PEP", -100, 50)]
        result = group_stock_pairs(stocks, open_pair_logs=logs)
        pair = result["pairs"][0]
        self.assertEqual(pair["status"], "missing_leg")
        pep_leg = next(l for l in pair["legs"] if l["symbol"] == "PEP")
        self.assertFalse(pep_leg["present_at_broker"])
        self.assertIsNone(pep_leg["broker_qty"])
        self.assertIsNone(pep_leg["position"])
        self.assertEqual(result["dangling"], [])

    def test_dangling_stock(self):
        stocks = [_stock("AAPL", 10), _stock("KO", -100), _stock("PEP", 50)]
        logs = [_log("KO", "PEP", -100, 50)]
        result = group_stock_pairs(stocks, open_pair_logs=logs)
        self.assertEqual(len(result["pairs"]), 1)
        dangling_syms = [s["symbol"] for s in result["dangling"]]
        self.assertEqual(dangling_syms, ["AAPL"])

    def test_overlapping_pairs(self):
        stocks = [
            _stock("KO", -100),
            _stock("PEP", 50),
            _stock("MNST", 20),
        ]
        logs = [
            _log("KO", "PEP", -100, 50),
            _log("KO", "MNST", -100, 20),
        ]
        result = group_stock_pairs(stocks, open_pair_logs=logs)
        self.assertEqual(len(result["pairs"]), 2)
        by_id = {p["pair_id"]: p for p in result["pairs"]}
        self.assertIn("KO_MNST", by_id["KO_PEP"]["overlapping_pairs"])
        self.assertIn("KO_PEP", by_id["KO_MNST"]["overlapping_pairs"])
        self.assertEqual(result["dangling"], [])

    def test_size2_only_still_open_via_injected_log(self):
        """Open-pair detection with size1==0 size2!=0 (log already marked open)."""
        stocks = [_stock("A", 0), _stock("B", 30)]
        # Broker may still show A at 0; treat as present only if in stocks list.
        # Use B only at broker so pair is included via missing_leg path if A absent.
        stocks = [_stock("B", 30)]
        logs = [_log("A", "B", 0, 30)]
        result = group_stock_pairs(stocks, open_pair_logs=logs)
        self.assertEqual(len(result["pairs"]), 1)
        self.assertEqual(result["pairs"][0]["status"], "missing_leg")

    def test_omit_pair_with_neither_leg_at_broker(self):
        stocks = [_stock("AAPL", 5)]
        logs = [_log("KO", "PEP", -100, 50)]
        result = group_stock_pairs(stocks, open_pair_logs=logs)
        self.assertEqual(result["pairs"], [])
        self.assertEqual([s["symbol"] for s in result["dangling"]], ["AAPL"])

    def test_empty_stocks(self):
        result = group_stock_pairs([], open_pair_logs=[_log("KO", "PEP", -1, 1)])
        self.assertEqual(result, {"pairs": [], "dangling": []})

    def test_symbol_case_normalized(self):
        stocks = [_stock("ko", -100), _stock("pep", 50)]
        logs = [_log("KO", "PEP", -100, 50)]
        result = group_stock_pairs(stocks, open_pair_logs=logs)
        self.assertEqual(result["pairs"][0]["status"], "matched")
        self.assertEqual(result["dangling"], [])


if __name__ == "__main__":
    unittest.main()
