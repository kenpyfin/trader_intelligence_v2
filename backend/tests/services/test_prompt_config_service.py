"""Tests for editable GPT prompt catalog and persistence."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
SRC_PATH = BACKEND_ROOT / "src"
for candidate in (str(SRC_PATH), str(BACKEND_ROOT), str(ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from src.services import prompt_config_service  # noqa: E402
from src.services.prompt_defaults import PROMPT_BY_ID, PROMPT_DEFINITIONS  # noqa: E402


class TestPromptConfigService(unittest.TestCase):
    def setUp(self):
        self.mongo_patcher = patch.object(prompt_config_service, "_get_collection")
        mock_get = self.mongo_patcher.start()
        mock_get.return_value.find.return_value = []
        self.mock_collection = mock_get.return_value
        self.addCleanup(self.mongo_patcher.stop)
        prompt_config_service.reset_prompt_cache()
        self.addCleanup(prompt_config_service.reset_prompt_cache)

    def test_catalog_covers_all_runtime_prompt_ids(self):
        expected = {
            "gpt_verdict.analyst.system",
            "gpt_verdict.analyst.web_research_addendum",
            "gpt_verdict.analyst.user_header",
            "gpt_verdict.trader.system",
            "gpt_verdict.trader.user_header",
            "perplexity.research.system",
            "perplexity.research.user",
            "exit_signal.system",
            "exit_signal.user",
            "exit_signal.completion",
            "company_intel.system",
            "company_intel.user",
            "conflict_resolution.system",
            "conflict_resolution.user",
        }
        self.assertEqual({item.id for item in PROMPT_DEFINITIONS}, expected)
        self.assertGreater(len(PROMPT_BY_ID["gpt_verdict.analyst.system"].default_text), 1000)

    def test_render_prompt_replaces_only_documented_placeholders(self):
        with patch.object(prompt_config_service, "_get_collection") as mock_col:
            mock_col.return_value.find.return_value = []
            prompt_config_service.reset_prompt_cache()
            rendered = prompt_config_service.render_prompt(
                "gpt_verdict.analyst.system",
                ticker="AAPL",
            )
        self.assertIn("cite AAPL data ONLY", rendered)
        self.assertIn('"final_bias": "Bullish"', rendered)
        self.assertNotIn("{ticker}", rendered)

    def test_get_prompt_text_uses_override(self):
        with patch.object(prompt_config_service, "_get_collection") as mock_col:
            mock_col.return_value.find.return_value = [
                {
                    "_id": "perplexity.research.system",
                    "text": "Custom research system",
                    "updated_at": datetime(2026, 9, 3, tzinfo=timezone.utc),
                }
            ]
            prompt_config_service.reset_prompt_cache()
            text = prompt_config_service.get_prompt_text("perplexity.research.system")
        self.assertEqual(text, "Custom research system")

    def test_update_prompt_writes_mongo_and_cache(self):
        mock_col = MagicMock()
        mock_col.find.return_value = []
        with patch.object(prompt_config_service, "_get_collection", return_value=mock_col):
            prompt_config_service.reset_prompt_cache()
            payload = prompt_config_service.update_prompt(
                "exit_signal.system",
                "Evaluate exits using tools only.",
            )
            self.assertTrue(payload["is_customized"])
            self.assertEqual(payload["text"], "Evaluate exits using tools only.")
            self.assertTrue(payload["persisted"])
            mock_col.update_one.assert_called_once()
            self.assertEqual(
                prompt_config_service.get_prompt_text("exit_signal.system"),
                "Evaluate exits using tools only.",
            )

    def test_update_prompt_rejects_empty_text(self):
        with self.assertRaises(prompt_config_service.PromptValidationError):
            prompt_config_service.update_prompt("exit_signal.system", "   ")

    def test_unknown_prompt_id_raises(self):
        with self.assertRaises(prompt_config_service.UnknownPromptError):
            prompt_config_service.get_prompt_text("does.not.exist")

    def test_reset_prompt_restores_default(self):
        mock_col = MagicMock()
        mock_col.find.return_value = []
        default = PROMPT_BY_ID["company_intel.system"].default_text
        with patch.object(prompt_config_service, "_get_collection", return_value=mock_col):
            prompt_config_service.reset_prompt_cache()
            prompt_config_service.update_prompt("company_intel.system", "Temporary override")
            payload = prompt_config_service.reset_prompt("company_intel.system")
            self.assertFalse(payload["is_customized"])
            self.assertEqual(payload["text"], default)
            mock_col.delete_one.assert_called_once()


class TestPromptConsumersUseCatalog(unittest.TestCase):
    def setUp(self):
        prompt_config_service.reset_prompt_cache()
        self.addCleanup(prompt_config_service.reset_prompt_cache)
        self.mongo_patch = patch.object(prompt_config_service, "_get_collection")
        mock_col = self.mongo_patch.start()
        mock_col.return_value.find.return_value = []
        self.addCleanup(self.mongo_patch.stop)

    def test_analyst_messages_use_configured_prompt(self):
        from src.analytics.methodologies.gpt_verdict import _build_analyst_messages

        prompt_config_service.update_prompt(
            "gpt_verdict.analyst.system",
            "Configured analyst for {ticker}. Return JSON.",
        )
        messages = _build_analyst_messages(
            "MSFT",
            "2026-12-19",
            {"market_data": {"current_price": 100}},
        )
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Configured analyst for MSFT", messages[0]["content"])
        self.assertIn("Analyze MSFT for expiration 2026-12-19", messages[1]["content"])

    def test_conflict_messages_use_configured_prompt(self):
        from src.services.conflict_resolution_service import _build_messages

        prompt_config_service.update_prompt(
            "conflict_resolution.system",
            "Configured conflict resolver.",
        )
        messages = _build_messages(
            "spy",
            [
                {
                    "id": "1",
                    "final_bias": "Bullish",
                    "rationale": "up",
                    "summary": "summary a",
                },
                {
                    "id": "2",
                    "final_bias": "Bearish",
                    "rationale": "down",
                    "summary": "summary b",
                },
            ],
        )
        self.assertEqual(messages[0]["content"], "Configured conflict resolver.")
        self.assertIn("SPY", messages[1]["content"])
