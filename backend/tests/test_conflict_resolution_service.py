"""Regression tests for conflict resolution service (no live Gemini calls)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
SRC_PATH = BACKEND_ROOT / "src"
for candidate in (str(SRC_PATH), str(BACKEND_ROOT), str(ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from src.services.conflict_resolution_service import (  # noqa: E402
    _build_messages,
    _strip_html,
    resolve_conflicts,
)


class TestConflictResolutionService(unittest.TestCase):
    def test_strip_html_truncates(self):
        text = _strip_html("<p>Hello <b>world</b></p>")
        self.assertEqual(text, "Hello world")
        long_html = "<p>" + ("x" * 2000) + "</p>"
        truncated = _strip_html(long_html, max_len=50)
        self.assertTrue(truncated.endswith("..."))
        self.assertLessEqual(len(truncated), 53)

    def test_build_messages_includes_biases(self):
        summaries = [
            {
                "id": "1",
                "label": "A",
                "created_at": "t1",
                "final_bias": "Bullish",
                "analysis_method": "gpt-verdict",
                "gpt_model": "gemini-2.5-flash",
                "expiration_date": "2026-01-01",
                "S_current": 100,
                "rationale": "up",
                "summary": "summary a",
                "key_reasoning_points": ["point a"],
                "risk_factors": ["risk a"],
            },
            {
                "id": "2",
                "label": "B",
                "created_at": "t2",
                "final_bias": "Bearish",
                "analysis_method": "holistic-market-edge",
                "gpt_model": None,
                "expiration_date": "2026-01-01",
                "S_current": 101,
                "rationale": "",
                "summary": "summary b",
                "key_reasoning_points": [],
                "risk_factors": [],
            },
        ]
        messages = _build_messages("spy", summaries)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn("Bullish", messages[1]["content"])
        self.assertIn("Bearish", messages[1]["content"])
        self.assertIn("SPY", messages[1]["content"])

    def test_resolve_conflicts_requires_two_verdicts(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_conflicts("SPY", ["only-one"])
        self.assertIn("at least 2", str(ctx.exception).lower())

    @patch("src.services.conflict_resolution_service._get_collection")
    @patch("src.services.conflict_resolution_service._openai_chat_completion")
    @patch("src.services.conflict_resolution_service.get_verdict_by_id")
    def test_resolve_conflicts_persists_llm_result(self, mock_get, mock_llm, mock_col):
        mock_get.side_effect = [
            {
                "id": "id1",
                "ticker": "SPY",
                "label": "One",
                "created_at": "2026-01-01T00:00:00",
                "final_bias": "Bullish",
                "analysis_method": "gpt-verdict",
                "gpt_model": "gemini-2.5-flash",
                "expiration_date": "2026-02-01",
                "data": {
                    "final_bias": "Bullish",
                    "final_conclusion_html": "<p>bull</p>",
                    "gpt_verdict": {
                        "rationale": "strong trend",
                        "key_reasoning_points": ["a"],
                        "risk_factors": [],
                    },
                    "S_current": 500,
                },
            },
            {
                "id": "id2",
                "ticker": "SPY",
                "label": "Two",
                "created_at": "2026-01-02T00:00:00",
                "final_bias": "Bearish",
                "analysis_method": "gpt-verdict",
                "gpt_model": "gemini-2.5-flash",
                "expiration_date": "2026-02-01",
                "data": {
                    "final_bias": "Bearish",
                    "final_conclusion_html": "<p>bear</p>",
                    "gpt_verdict": {
                        "rationale": "weak tape",
                        "key_reasoning_points": ["b"],
                        "risk_factors": ["r"],
                    },
                    "S_current": 499,
                },
            },
        ]
        metrics = MagicMock()
        metrics.model = "gemini-2.5-flash"
        mock_llm.return_value = (
            {
                "final_bias": "Neutral",
                "confidence_level": "Medium",
                "conflict_summary": "Mixed signals",
                "agreement_points": ["Same expiration"],
                "disagreement_points": ["Opposite bias"],
                "rationale": "Blend both views",
                "summary_html": "<p>Neutral</p>",
                "actionable_ideas": ["Wait"],
                "risk_factors": ["Volatility"],
            },
            metrics,
        )
        collection = MagicMock()
        collection.insert_one.return_value = MagicMock(inserted_id="abc123")
        mock_col.return_value = collection

        result = resolve_conflicts("spy", ["id1", "id2"], model="gemini-2.5-flash")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["final_bias"], "Neutral")
        self.assertEqual(result["conflict_summary"], "Mixed signals")
        self.assertEqual(result["id"], "abc123")
        self.assertEqual(len(result["sources"]), 2)
        self.assertEqual(result["sources"][0]["final_bias"], "Bullish")
        self.assertEqual(result["sources"][1]["final_bias"], "Bearish")
        self.assertEqual(result["sources"][0]["label"], "One")
        collection.insert_one.assert_called_once()
        persisted = collection.insert_one.call_args[0][0]
        self.assertEqual(len(persisted["sources"]), 2)
        mock_llm.assert_called_once()
        self.assertEqual(mock_llm.call_args.kwargs.get("stage"), "ConflictResolver")

    @patch("src.services.conflict_resolution_service._get_collection")
    def test_list_resolutions_includes_source_history(self, mock_col):
        collection = MagicMock()
        collection.count_documents.return_value = 1
        collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = [
            {
                "_id": "res1",
                "ticker": "SPY",
                "model": "gemini-2.5-flash",
                "final_bias": "Neutral",
                "confidence_level": "Medium",
                "conflict_summary": "Mixed",
                "verdict_ids": ["id1", "id2"],
                "sources": [
                    {
                        "id": "id1",
                        "label": "Before",
                        "final_bias": "Bullish",
                        "created_at": "2026-01-01T00:00:00",
                        "analysis_method": "gpt-verdict",
                        "expiration_date": "2026-02-01",
                    },
                    {
                        "id": "id2",
                        "label": "After",
                        "final_bias": "Bearish",
                        "created_at": "2026-01-02T00:00:00",
                        "analysis_method": "gpt-verdict",
                        "expiration_date": "2026-02-01",
                    },
                ],
                "created_at": __import__("datetime").datetime(2026, 1, 3, 12, 0, 0),
            }
        ]
        mock_col.return_value = collection

        from src.services.conflict_resolution_service import list_resolutions

        data = list_resolutions("SPY", page=1, page_size=10)
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["items"]), 1)
        item = data["items"][0]
        self.assertEqual(item["source_count"], 2)
        self.assertEqual(len(item["sources"]), 2)
        self.assertEqual(item["sources"][0]["label"], "Before")
        self.assertEqual(item["sources"][1]["final_bias"], "Bearish")


if __name__ == "__main__":
    unittest.main()
