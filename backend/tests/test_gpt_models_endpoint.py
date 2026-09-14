"""Regression tests for GPT / Gemini model listing and /api/gpt-models."""
import asyncio
import os
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

from src.services.gpt_models_service import (  # noqa: E402
    classify_gemini_models_error,
    fallback_gpt_models,
    list_gpt_models,
    parse_gemini_models_payload,
)


class TestGptModelsService(unittest.TestCase):
    def test_parse_gemini_models_payload_filters_generate_content(self):
        payload = {
            "models": [
                {
                    "name": "models/gemini-2.5-flash",
                    "displayName": "Gemini 2.5 Flash",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/embedding-001",
                    "displayName": "Embedding",
                    "supportedGenerationMethods": ["embedContent"],
                },
                {
                    "name": "bad-name",
                    "supportedGenerationMethods": ["generateContent"],
                },
            ]
        }
        models = parse_gemini_models_payload(payload)
        self.assertEqual(models, [{"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash"}])

    def test_classify_leaked_key(self):
        code, message = classify_gemini_models_error(
            403,
            '{"error":{"message":"Your API key was reported as leaked."}}',
        )
        self.assertEqual(code, "api_key_leaked")
        self.assertIn("leaked", message.lower())
        self.assertIn("GEMINI_API_KEY", message)

    def test_list_gpt_models_missing_api_key_returns_fallback(self):
        result = list_gpt_models(api_key="")
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["error_code"], "missing_api_key")
        self.assertEqual(result["source"], "fallback")
        self.assertGreaterEqual(len(result["models"]), 1)
        self.assertEqual(result["models"][0]["id"], fallback_gpt_models()[0]["id"])

    def test_list_gpt_models_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [
                {
                    "name": "models/gemini-2.5-pro",
                    "displayName": "Gemini 2.5 Pro",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/gemini-2.5-flash",
                    "displayName": "Gemini 2.5 Flash",
                    "supportedGenerationMethods": ["generateContent"],
                },
            ]
        }
        mock_get = MagicMock(return_value=mock_resp)

        result = list_gpt_models(api_key="test-key", http_get=mock_get)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["source"], "gemini")
        self.assertNotIn("warning", result)
        ids = [m["id"] for m in result["models"]]
        self.assertEqual(ids, ["gemini-2.5-flash", "gemini-2.5-pro"])
        mock_get.assert_called_once()

    def test_list_gpt_models_upstream_403_leaked_key_falls_back(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = (
            '{"error":{"code":403,"message":"Your API key was reported as leaked.",'
            '"status":"PERMISSION_DENIED"}}'
        )
        mock_get = MagicMock(return_value=mock_resp)

        result = list_gpt_models(api_key="leaked-key", http_get=mock_get)
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["error_code"], "api_key_leaked")
        self.assertEqual(result["upstream_status"], 403)
        self.assertGreaterEqual(len(result["models"]), 1)
        self.assertIn("leaked", result["warning"].lower())

    def test_list_gpt_models_upstream_5xx_falls_back(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "internal"
        mock_get = MagicMock(return_value=mock_resp)

        result = list_gpt_models(api_key="test-key", http_get=mock_get)
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["error_code"], "upstream_error")
        self.assertEqual(result["source"], "fallback")

    def test_list_gpt_models_connection_error_falls_back(self):
        import requests as requests_lib

        mock_get = MagicMock(side_effect=requests_lib.ConnectionError("dns failed"))
        result = list_gpt_models(api_key="test-key", http_get=mock_get)
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["error_code"], "connection_error")
        self.assertGreaterEqual(len(result["models"]), 1)


class TestGptModelsEndpoint(unittest.TestCase):
    def test_import_main_registers_gpt_models_and_conflict_routes(self):
        from src.main import app

        paths = {getattr(route, "path", None) for route in app.routes}
        self.assertIn("/api/gpt-models", paths)
        self.assertIn("/gpt-models", paths)
        self.assertIn("/api/analysis/conflict-resolve", paths)

    def test_conflict_resolution_service_import_does_not_break_gpt_models(self):
        import src.services.conflict_resolution_service  # noqa: F401

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [
                {
                    "name": "models/gemini-2.5-flash",
                    "displayName": "Gemini 2.5 Flash",
                    "supportedGenerationMethods": ["generateContent"],
                }
            ]
        }
        result = list_gpt_models(api_key="k", http_get=MagicMock(return_value=mock_resp))
        self.assertEqual(result["status"], "success")

    def test_get_available_gpt_models_endpoint_uses_service(self):
        from src.main import get_available_gpt_models

        fake_payload = {
            "status": "degraded",
            "models": fallback_gpt_models(),
            "default": "gemini-2.5-flash",
            "warning": "Gemini API key was reported as leaked.",
            "error_code": "api_key_leaked",
            "source": "fallback",
        }

        with patch("src.main.list_gpt_models", return_value=fake_payload):
            result = asyncio.run(get_available_gpt_models())

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["error_code"], "api_key_leaked")
        self.assertTrue(result["models"])


if __name__ == "__main__":
    unittest.main()
