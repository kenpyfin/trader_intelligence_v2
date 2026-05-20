import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from analytics.methodologies.perplexity_research import (
    PerplexityConfigError,
    PerplexityAPIError,
    fetch_web_context,
    _require_api_key,
)
from analytics.methodologies.gpt_verdict import (
    generate_gpt_verdict,
    _build_analyst_messages,
    _openai_chat_completion,
)


class TestPerplexityResearch(unittest.TestCase):
    def test_missing_api_key_raises(self):
        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": ""}, clear=False):
            with self.assertRaises(PerplexityConfigError) as ctx:
                _require_api_key()
            self.assertIn("PERPLEXITY_API_KEY", str(ctx.exception))

    @patch("analytics.methodologies.perplexity_research.requests.post")
    def test_fetch_web_context_parses_citations(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Recent bullish news on AAPL."}}],
            "citations": [
                "https://example.com/news1",
                "https://example.com/news2",
            ],
            "search_results": [{"url": "https://example.com/news3", "title": "Extra"}],
        }
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "pplx-test"}, clear=False):
            result = fetch_web_context("AAPL", "2025-12-19", days_to_earnings=10)

        self.assertTrue(result["search_performed"])
        self.assertEqual(result["provider"], "perplexity")
        self.assertIn("bullish", result["summary"])
        self.assertEqual(len(result["sources"]), 3)
        self.assertIn("https://example.com/news1", result["sources"])

    @patch("analytics.methodologies.perplexity_research.requests.post")
    def test_fetch_web_context_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "pplx-test"}, clear=False):
            with self.assertRaises(PerplexityAPIError):
                fetch_web_context("AAPL", "2025-12-19")


class TestWebVerdictIntegration(unittest.TestCase):
    def test_analyst_messages_include_web_research(self):
        web_context = {
            "summary": "Earnings beat expected.",
            "sources": ["https://example.com/earnings"],
        }
        messages = _build_analyst_messages(
            "AAPL",
            "2025-12-19",
            {"market_data": {"current_price": 100}},
            use_web_search=True,
            web_context=web_context,
        )
        user_content = messages[1]["content"]
        self.assertIn("<web_research>", user_content)
        self.assertIn("Earnings beat expected", user_content)
        self.assertIn("Perplexity", messages[0]["content"])

    @patch("analytics.methodologies.gpt_verdict.requests.post")
    def test_gemini_payload_has_no_google_search(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {"parts": [{"text": '{"final_bias":"Neutral"}'}]},
                    "finishReason": "STOP",
                }
            ]
        }
        mock_post.return_value = mock_resp
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            _openai_chat_completion(
                [{"role": "user", "content": "hi"}],
                use_web_search=True,
            )
        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        self.assertNotIn("tools", payload)

    @patch("analytics.methodologies.gpt_verdict._validate_options_data")
    @patch("analytics.methodologies.gpt_verdict._openai_chat_completion_with_retry")
    @patch("analytics.methodologies.gpt_verdict.fetch_web_context")
    def test_generate_gpt_verdict_web_sets_sources(self, mock_fetch, mock_retry, mock_validate):
        validation = MagicMock()
        validation.data_completeness_score = 0.9
        validation.data_quality_score = 0.9
        validation.valid_strikes_count = 1
        validation.greeks_count = 1
        validation.complete_greeks_count = 1
        validation.invalid_greeks_count = 0
        validation.warnings = []
        validation.errors = []
        validation.quality_assessment_result = {"can_proceed": True, "overall_level": "good", "combined_score": 0.9}
        mock_validate.return_value = validation
        mock_fetch.return_value = {
            "provider": "perplexity",
            "model": "sonar",
            "summary": "Recent catalysts are positive.",
            "sources": ["https://example.com/a"],
            "search_performed": True,
            "fetched_at": "2025-01-01T00:00:00+00:00",
        }
        analyst = {
            "final_bias": "Bullish",
            "rationale": "Strong setup.",
            "summary_html": "<p>ok</p>",
            "key_reasoning_points": ["a"],
            "risk_factors": ["b"],
            "actionable_ideas": ["c"],
        }
        trader = {
            "execution_recommendations": {
                "primary_strategy": {"name": "Long Call"}
            }
        }
        mock_metrics = MagicMock(
            duration=1.0,
            response_size=100,
            failure_category=None,
            error_message=None,
        )
        mock_retry_metrics = MagicMock(
            total_attempts=1,
            successful_attempt=1,
            total_retry_time=0,
            circuit_breaker_triggered=False,
            delays_used=[],
            final_failure_category=None,
        )
        mock_retry.side_effect = [
            (analyst, mock_metrics, mock_retry_metrics),
            (trader, mock_metrics, mock_retry_metrics),
        ]

        analysis_result = {
            "market_data": {"days_to_earnings": 5},
            "options_positioning": {
                "greeks_by_strike": {"100": {"delta": 0.5}},
                "strike_distribution": {"valid_strikes": [100.0]},
            },
            "volatility_structure": {},
        }

        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "pplx-test"}, clear=False):
            result = generate_gpt_verdict(
                "AAPL",
                "2026-12-18",
                analysis_result,
                use_web_search=True,
            )

        self.assertTrue(result.get("search_performed"))
        self.assertEqual(result.get("sources"), ["https://example.com/a"])
        self.assertIn("web_research", result)
        mock_fetch.assert_called_once()

    @patch("analytics.methodologies.gpt_verdict.fetch_web_context")
    @patch("analytics.methodologies.gpt_verdict._openai_chat_completion_with_retry")
    def test_missing_key_before_gemini(self, mock_retry, mock_fetch):
        mock_fetch.side_effect = PerplexityConfigError("Web Verdict requires PERPLEXITY_API_KEY")
        with self.assertRaises(PerplexityConfigError):
            generate_gpt_verdict(
                "AAPL",
                "2025-12-19",
                {"market_data": {}},
                use_web_search=True,
            )
        mock_retry.assert_not_called()


if __name__ == "__main__":
    unittest.main()
