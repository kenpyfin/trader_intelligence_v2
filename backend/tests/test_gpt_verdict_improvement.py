import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from analytics.methodologies.gpt_verdict import generate_gpt_verdict

class TestGPTVerdictImprovement(unittest.TestCase):
    
    @patch('analytics.methodologies.gpt_verdict._openai_chat_completion')
    def test_two_stage_process(self, mock_completion):
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
        
        # Configure side_effect to return analyst response first, then trader response
        mock_completion.side_effect = [mock_analyst_response, mock_trader_response]
        
        # Input data
        analysis_result = {
            "market_data": {"current_price": 100},
            "macro_context": {"spy_trend": "Uptrend", "vix_regime": "Low"},
            "volatility_structure": {"hv_rank": 0.5},
            "options_positioning": {"valid_strikes": [100, 105]}
        }
        
        # Run
        print("Testing generate_gpt_verdict...")
        result = generate_gpt_verdict("AAPL", "2023-12-20", analysis_result)
        
        # Verify
        self.assertEqual(mock_completion.call_count, 2, "Should call OpenAI twice (Analyst + Trader)")
        self.assertEqual(result['final_bias'], "Bullish")
        self.assertEqual(result['execution_recommendations']['primary_strategy']['name'], "Long Call")
        
        # Verify Analyst call args
        args1, _ = mock_completion.call_args_list[0]
        messages1 = args1[0]
        print("Verifying Analyst Prompt...")
        self.assertIn("Senior Quantitative Analyst", messages1[0]['content'])
        self.assertIn("macro_context", messages1[1]['content'])
        
        # Verify Trader call args
        args2, _ = mock_completion.call_args_list[1]
        messages2 = args2[0]
        print("Verifying Trader Prompt...")
        self.assertIn("Senior Options Execution Trader", messages2[0]['content'])
        self.assertIn("Analyst's thesis", messages2[0]['content'])
        
        print("Test Passed!")

if __name__ == '__main__':
    unittest.main()
