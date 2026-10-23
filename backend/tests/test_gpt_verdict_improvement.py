import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from analytics.methodologies.gpt_verdict import generate_gpt_verdict

class TestGPTVerdictImprovement(unittest.TestCase):
    
    @patch('analytics.methodologies.gpt_verdict._openai_chat_completion_with_retry')
    @patch('analytics.methodologies.gpt_verdict._validate_options_data')
    def test_two_stage_process(self, mock_validate, mock_completion):
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
        # Setup mocks
        mock_analyst_response = {
            "final_bias": "Bullish",
            "rationale": "Markets are good.",
            "risk_factors": ["None"]
        }
        mock_trader_response = {
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
        mock_completion.side_effect = [
            (mock_analyst_response, mock_metrics, mock_retry_metrics),
            (mock_trader_response, mock_metrics, mock_retry_metrics),
        ]
        
        # Input data
        analysis_result = {
            "market_data": {"current_price": 100},
            "macro_context": {"spy_trend": "Uptrend", "vix_regime": "Low"},
            "volatility_structure": {"hv_rank": 0.5},
            "options_positioning": {"valid_strikes": [100, 105]}
        }
        
        # Run
        print("Testing generate_gpt_verdict...")
        result = generate_gpt_verdict("AAPL", "2026-12-18", analysis_result)
        
        # Verify
        self.assertEqual(mock_completion.call_count, 2, "Should call OpenAI twice (Analyst + Trader)")
        self.assertEqual(result['final_bias'], "Bullish")
        self.assertEqual(result['execution_recommendations']['primary_strategy']['name'], "Long Call")
        
        # Verify Analyst call args
        args1, kwargs1 = mock_completion.call_args_list[0]
        messages1 = kwargs1.get("messages") or args1[0]
        print("Verifying Analyst Prompt...")
        self.assertIn("Senior Quantitative Analyst", messages1[0]['content'])
        self.assertIn("macro_context", messages1[1]['content'])
        
        # Verify Trader call args
        args2, kwargs2 = mock_completion.call_args_list[1]
        messages2 = kwargs2.get("messages") or args2[0]
        print("Verifying Trader Prompt...")
        self.assertIn("Senior Options Execution Trader", messages2[0]['content'])
        self.assertIn("Analyst's thesis", messages2[0]['content'])
        
        print("Test Passed!")

if __name__ == '__main__':
    unittest.main()
