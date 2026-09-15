"""Tests for analysis follow-up chat (no live Gemini calls)."""
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

from src.services.analysis_chat_service import (  # noqa: E402
    compact_analysis_context,
    generate_analysis_chat_reply,
    validate_chat_history,
)


def _sample_analysis():
    return {
        "ticker": "AAPL",
        "S_current": 190.5,
        "expiration_date": "2026-10-16",
        "dte": 32,
        "analysis_method": "gpt-verdict",
        "final_bias": "Bullish",
        "final_conclusion_html": "<p>Trend is <b>up</b> with support at 185.</p>",
        "recommended_strategy": {"type": "Bull Call Spread"},
        "recommended_strategies": [{"type": "Bull Call Spread"}],
        "gpt_verdict": {
            "final_bias": "Bullish",
            "rationale": "SMA stack is aligned.",
            "plot_data": {"x": [1, 2, 3]},
        },
        "candlestick_analysis": {
            "plot_data": {"candles": [1, 2, 3]},
            "patterns": [{"name": "hammer"}],
        },
        "results_df": [{"Strike": 185, "Type": "Call"}] * 20,
        "parity_analysis": {
            "parity_data": [{"Parity Difference": 0.1}] * 8,
            "arbitrage_opportunities": 1,
        },
        "market_data": {"current_price": 190.5},
    }


class TestAnalysisChatService(unittest.TestCase):
    def test_compact_analysis_context_drops_plot_data_and_keeps_bias(self):
        compacted = compact_analysis_context(_sample_analysis())
        self.assertEqual(compacted["ticker"], "AAPL")
        self.assertEqual(compacted["final_bias"], "Bullish")
        self.assertIn("Trend is up", compacted["final_conclusion"])
        self.assertNotIn("<b>", compacted["final_conclusion"])
        self.assertEqual(compacted["recommended_strategy"]["type"], "Bull Call Spread")
        self.assertNotIn("plot_data", compacted.get("gpt_verdict") or {})
        self.assertNotIn("candlestick_analysis", compacted)
        self.assertEqual(compacted["results_df"]["count"], 20)
        self.assertEqual(len(compacted["results_df"]["sample"]), 15)
        self.assertEqual(compacted["parity_analysis"]["parity_row_count"], 8)
        self.assertNotIn("parity_data", compacted["parity_analysis"])

    def test_validate_chat_history_rejects_empty_and_non_user_last(self):
        with self.assertRaises(ValueError) as empty_ctx:
            validate_chat_history([])
        self.assertIn("empty", str(empty_ctx.exception).lower())

        with self.assertRaises(ValueError) as last_ctx:
            validate_chat_history([{"role": "assistant", "content": "hello"}])
        self.assertIn("last message", str(last_ctx.exception).lower())

        with self.assertRaises(ValueError):
            validate_chat_history([{"role": "system", "content": "nope"}])

    @patch("src.services.analysis_chat_service.render_prompt", return_value="CONTEXT JSON")
    @patch("src.services.analysis_chat_service.get_prompt_text", return_value="SYSTEM PROMPT")
    @patch("src.services.analysis_chat_service.requests.post")
    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    def test_generate_analysis_chat_reply_returns_gemini_text(
        self, mock_post, _mock_prompt, _mock_render
    ):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [
                {"content": {"parts": [{"text": "Bias is Bullish because SMA aligned."}]}}
            ]
        }
        mock_post.return_value = mock_response

        result = generate_analysis_chat_reply(
            _sample_analysis(),
            [
                {"role": "assistant", "content": "I've loaded the AAPL analysis."},
                {"role": "user", "content": "Why this bias?"},
            ],
            model="gemini-2.5-flash",
        )

        self.assertEqual(result["status"], "success")
        self.assertIn("Bullish", result["reply"])
        self.assertEqual(result["model"], "gemini-2.5-flash")
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["contents"][0]["role"], "user")
        self.assertNotIn("application/json", str(payload.get("generationConfig")))

    @patch("src.services.analysis_chat_service.render_prompt", return_value="CONTEXT JSON")
    @patch("src.services.analysis_chat_service.get_prompt_text", return_value="SYSTEM PROMPT")
    @patch("src.services.analysis_chat_service.requests.post")
    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GEMINI_DEFAULT_MODEL": "gemini-2.5-flash"})
    def test_non_gemini_model_falls_back_to_default(self, mock_post, _mock_prompt, _mock_render):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        }
        mock_post.return_value = mock_response
        result = generate_analysis_chat_reply(
            _sample_analysis(),
            [{"role": "user", "content": "Explain the bias."}],
            model="sonar-pro",
        )
        self.assertEqual(result["model"], "gemini-2.5-flash")
        url = mock_post.call_args.args[0]
        self.assertIn("gemini-2.5-flash", url)

    @patch.dict(os.environ, {"GEMINI_API_KEY": ""})
    def test_missing_gemini_api_key_raises(self):
        with self.assertRaises(RuntimeError) as ctx:
            generate_analysis_chat_reply(
                _sample_analysis(),
                [{"role": "user", "content": "Why this bias?"}],
            )
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
