import sys
import os
from datetime import date, timedelta

# Add backend to path (parent of src)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import src.analytics.analysis as analysis_module
from src.analytics.analysis import run_analysis

print(f"DEBUG: analysis module file: {analysis_module.__file__}")

def verify_data_injection():
    ticker = "AAPL"
    # Use a known valid monthly expiration date (3rd Friday of Dec 2025)
    exp_date = date(2025, 12, 19)
    
    print(f"Running analysis for {ticker}...")
    try:
        # Use GPT method to verify the full payload structure
        result = run_analysis(ticker, exp_date, analysis_method='gpt-verdict')
        
        print(f"DEBUG: Result keys: {list(result.keys())}")
        if 'status' in result and result['status'] == 'error':
            print(f"DEBUG: Error message: {result.get('message')}")
        
        print("\nVerifying Macro Context:")
        if 'macro_context' in result:
            print("PASS: macro_context found")
            print(result['macro_context'])
        else:
            print("FAIL: macro_context missing")

        if 'gpt_verdict' in result:
            print("\nVerifying GPT Verdict:")
            # print(result['gpt_verdict']) # Too large for console
            import json
            with open('verdict_debug.json', 'w') as f:
                json.dump(result['gpt_verdict'], f, indent=2)
            print("Saved gpt_verdict to verdict_debug.json")
        else:
            print("\nGPT Verdict NOT found (expected for holistic method, but checking structure if present)")
            
        print("\nVerifying HV Rank:")
        found_hv = False
        if 'market_data' in result and 'hv_rank' in result['market_data']:
            print(f"PASS: hv_rank found in market_data: {result['market_data']['hv_rank']}")
            found_hv = True
            
        if 'volatility_structure' in result and 'hv_rank' in result['volatility_structure']:
            print(f"PASS: hv_rank found in volatility_structure: {result['volatility_structure']['hv_rank']}")
            found_hv = True
            
        if not found_hv:
            print("FAIL: hv_rank missing")
            
    except Exception as e:
        print(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_data_injection()
