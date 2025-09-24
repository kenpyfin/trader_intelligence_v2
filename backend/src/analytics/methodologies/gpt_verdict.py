import os
import json
import requests
from datetime import date
from typing import Any, Dict

def _sanitize_for_json(obj: Any, max_list_len: int = 200) -> Any:
    """
    Recursively convert objects to JSON-safe types.
    - Truncates long lists to avoid overlong prompts.
    - Converts pandas/numpy types where possible.
    """
    try:
        import numpy as np  # local import to avoid hard dependency if not used
        import pandas as pd
    except Exception:
        np = None
        pd = None

    # Primitive types
    if obj is None or isinstance(obj, (str, int, float, bool)):
        # Replace NaN/Inf with None
        try:
            if isinstance(obj, float):
                if (obj != obj) or obj in (float("inf"), float("-inf")):
                    return None
        except Exception:
            pass
        return obj

    # Date and datetime
    if isinstance(obj, (date,)):
        return obj.isoformat()

    # Numpy types
    if np is not None:
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()

    # Pandas DataFrame / Series
    if 'pandas' in str(type(obj)).lower():
        try:
            import pandas as pd  # type: ignore
            if isinstance(obj, pd.DataFrame):
                # limit rows/cols to keep prompt manageable
                df = obj.copy()
                if len(df) > max_list_len:
                    df = df.head(max_list_len)
                return df.to_dict(orient="records")
            if isinstance(obj, pd.Series):
                return obj.to_dict()
        except Exception:
            return str(obj)

    # Dict
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v, max_list_len=max_list_len) for k, v in obj.items()}

    # List/Tuple/Set
    if isinstance(obj, (list, tuple, set)):
        seq = list(obj)
        if len(seq) > max_list_len:
            seq = seq[:max_list_len]
        return [_sanitize_for_json(x, max_list_len=max_list_len) for x in seq]

    # Fallback
    return str(obj)


def _build_messages(ticker: str, analysis_payload: Dict[str, Any], use_web_search: bool = False) -> Dict[str, Any]:
    """
    Build system/user messages for the chat completion API.
    We instruct the model to return strict JSON so we can parse it reliably.
    """
    system = (
        "You are a senior options strategist and equity analyst providing clear, structured investment analysis. "
        "You have access to comprehensive market analysis including: technical patterns, options flow, volatility analysis, "
        "fundamental metrics, put-call parity insights, and quantitative option valuations. "
        "Analyze the market_data, stock_fundamentals, volatility_structure, parity_analysis, and options_positioning "
        "along with traditional sub-analyses (trend, candlesticks, volume/oi, iv/hv, movement, undervalued opportunities) "
        "to produce a decisive trading verdict for options positioning. "
        
        "ANALYSIS FRAMEWORK - Structure your reasoning using these key areas: "
        "1. CURRENT MARKET STATE: What is the stock doing right now? (price, volume, volatility) "
        "2. TECHNICAL PICTURE: What do charts and indicators suggest? (trends, patterns, momentum) "
        "3. FUNDAMENTAL CONTEXT: How does the company look financially? (valuation, growth, health) "
        "4. OPTIONS LANDSCAPE: What opportunities exist in the options market? (IV levels, skew, undervalued strikes) "
        "5. RISK-REWARD ASSESSMENT: What are the key risks and potential rewards? "
        "6. STRATEGIC IMPLICATIONS: What does this mean for positioning? "
        
        "Pay special attention to: "
        "- CURRENT REAL-TIME PRICE from market_data.current_price - this is the most recent price, use this for all analysis "
        "- IV/HV ratio and volatility regime (market_data) "
        "- Key fundamental metrics like PE, growth rates, and financial health (stock_fundamentals) "
        "- Volatility term structure and skew dynamics (volatility_structure) "
        "- Put-call parity arbitrage opportunities (parity_analysis) "
        "- Undervalued options and strike positioning insights (options_positioning) "
        
        "CRITICAL: Always reference the current_price from market_data for price levels, support/resistance, and strike selection. "
        "Do not use outdated price information from other sources. "
        
        "REASONING CLARITY: In your rationale, walk through your thought process step-by-step. "
        "Connect each piece of evidence to your conclusion. Explain WHY each factor matters and HOW it influences your verdict. "
    )

    if use_web_search:
        system += (
            "You MUST perform a web search to find recent catalysts, earnings reports, regulatory news, and overall market sentiment for this stock. "
            "Incorporate these findings directly into your rationale and summary. "
        )
    else:
        system += (
            "When possible, perform a quick web search to enrich context (recent catalysts, earnings, regulatory news). "
            "If web search is not available in your current toolset, explicitly state that and proceed with your best judgment. "
        )

    system += (
        "\n\nIMPORTANT: You MUST return your response as valid JSON ONLY. Do not include any text before or after the JSON. "
        "Do not use markdown code blocks or any other formatting. Return raw JSON that can be parsed directly. "
        "\n\nFor the summary_html field, create a well-structured HTML with clear visual hierarchy using these guidelines:\n"
        "- Use <h4> for main sections (e.g., 'Market Analysis', 'Technical Overview', 'Fundamental Assessment')\n"
        "- Use <h5> for subsections (e.g., 'Price Action', 'Volume Profile', 'Volatility Environment')\n"
        "- Use bulleted lists (<ul><li>) for key points and findings\n"
        "- Use colored badges for important metrics: <span class='badge bg-success'>Bullish Signal</span>\n"
        "- Use alert boxes for critical insights: <div class='alert alert-info'><strong>Key Insight:</strong> Your insight here</div>\n"
        "- Organize information logically: Current State → Analysis → Implications → Recommendations\n"
        "- Keep each section concise but comprehensive\n"
        "\n\nRequired JSON structure:\n"
        "{\n"
        "  \"final_bias\": \"Bullish|Slightly Bullish|Neutral|Slightly Bearish|Bearish\",\n"
        "  \"summary_html\": \"string (well-structured HTML with clear hierarchy and visual organization)\",\n"
        "  \"rationale\": \"string (detailed reasoning with clear logical flow, 15-25 sentences)\",\n"
        "  \"key_reasoning_points\": [\"Main analytical point 1\", \"Main analytical point 2\", \"Main analytical point 3\"],\n"
        "  \"actionable_ideas\": [\"string1\", \"string2\", ...],\n"
        "  \"risk_factors\": [\"string1\", \"string2\", ...],\n"
        "  \"execution_recommendations\": {\n"
        "    \"primary_strategy\": {\"type\": \"string\", \"description\": \"string\", \"confidence\": \"High|Medium|Low\", \"time_horizon\": \"string\"},\n"
        "    \"alternative_strategies\": [{\"type\": \"string\", \"description\": \"string\", \"confidence\": \"High|Medium|Low\", \"time_horizon\": \"string\"}],\n"
        "    \"position_sizing\": {\"suggested_allocation\": \"string\", \"risk_level\": \"Conservative|Moderate|Aggressive\", \"justification\": \"string\"},\n"
        "    \"entry_conditions\": [\"string1\", \"string2\", ...],\n"
        "    \"exit_conditions\": [\"string1\", \"string2\", ...],\n"
        "    \"stop_loss_guidance\": \"string\",\n"
        "    \"profit_target_guidance\": \"string\"\n"
        "  },\n"
        "  \"search_performed\": true|false,\n"
        "  \"sources\": [\"string1\", \"string2\", ...]\n"
        "}\n\n"
        "Remember: Return ONLY the JSON object, no other text or formatting."
    )

    user = {
        "ticker": ticker,
        "sub_analyses": analysis_payload
    }

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user)}
    ]


def _openai_chat_completion(messages, model: str = "gpt-5", temperature: float = 0.2, timeout: int = None) -> Dict[str, Any]:
    """
    Minimal OpenAI-compatible completion using requests.
    Uses chat/completions for chat models, completions for non-chat models.
    Honors OPENAI_API_BASE and OPENAI_API_KEY from environment.
    """
    base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    
    print(f"DEBUG: Using API base: {base}")
    print(f"DEBUG: Using model: {model}")
    print(f"DEBUG: Message count: {len(messages)}")
    
    # Validate that we have a working API configuration
    if not key.startswith(('sk-', 'org-')):
        print(f"DEBUG: Using custom API key format: {key[:20]}...")
    
    # Use environment variable for timeout, default to 180 seconds (3 minutes)
    if timeout is None:
        timeout = int(os.getenv("GPT_VERDICT_TIMEOUT", "180"))

    # Determine endpoint based on model type
    # GPT realtime models and some others use completions endpoint
    is_realtime_model = "realtime" in model.lower() or model.startswith("gpt-4o-realtime")
    is_completions_model = is_realtime_model or model in ["text-davinci-003", "text-davinci-002", "davinci", "curie", "babbage", "ada"]
    
    if is_completions_model:
        url = f"{base}/completions"
        # Convert messages to single prompt for completions endpoint
        prompt = ""
        for msg in messages:
            if msg["role"] == "system":
                prompt += f"System: {msg['content']}\n\n"
            elif msg["role"] == "user":
                prompt += f"User: {msg['content']}\n\n"
        prompt += "Assistant:"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": 4000,
            "stream": False
        }
        
        # Add temperature only for models that support it
        if not model.startswith("gpt-5") and not model.startswith("o3"):
            payload["temperature"] = temperature
            
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        
        print(f"DEBUG: Making completions request to {url}")
        print(f"DEBUG: Payload keys: {list(payload.keys())}")
        print(f"DEBUG: Model in payload: {payload.get('model')}")
        
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
        print(f"DEBUG: Response status: {resp.status_code}")
        
        resp.raise_for_status()
        data = resp.json()
        print(f"DEBUG: Response keys: {list(data.keys())}")
        
        # Check for empty response or missing choices
        if "choices" not in data or not data["choices"]:
            print(f"ERROR: No choices in OpenAI response: {data}")
            raise RuntimeError(f"No choices in OpenAI response")
            
        # Prefer text, but some proxies may return message-style payloads even on /completions
        choice0 = data["choices"][0]
        content = (choice0.get("text") or "").strip()
        if not content and isinstance(choice0, dict) and "message" in choice0:
            msg = choice0.get("message") or {}
            content = (msg.get("content") or "").strip()
            # Some non-standard providers return content as a list of blocks
            if not content and isinstance(msg.get("content"), list):
                try:
                    blocks = msg.get("content")
                    parts = []
                    for b in blocks:
                        if isinstance(b, dict) and b.get("type") == "text":
                            parts.append(b.get("text") or "")
                        elif isinstance(b, str):
                            parts.append(b)
                    content = "\n".join([p for p in parts if p]).strip()
                except Exception:
                    content = ""
            # Function/tool-call fallbacks
            if not content:
                # tool_calls (OpenAI tool calling)
                tool_calls = msg.get("tool_calls")
                if isinstance(tool_calls, list) and tool_calls:
                    try:
                        fn = tool_calls[0].get("function", {})
                        args = fn.get("arguments")
                        if isinstance(args, (dict, list)):
                            content = json.dumps(args)
                        elif isinstance(args, str):
                            content = args
                    except Exception:
                        pass
                # legacy function_call
                if not content and isinstance(msg.get("function_call"), dict):
                    args = msg["function_call"].get("arguments")
                    if isinstance(args, (dict, list)):
                        content = json.dumps(args)
                    elif isinstance(args, str):
                        content = args
        
        # Check for empty content
        if not content:
            print(f"WARNING: Empty content in OpenAI response (completions). Full response: {data}")
            # Do not raise here; allow downstream fallback to handle gracefully
            content = ""
    else:
        url = f"{base}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 4000,
            "stream": False
        }
        
        # Add temperature only for models that support it
        if not model.startswith("gpt-5") and not model.startswith("o3"):
            payload["temperature"] = temperature
            
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        
        print(f"DEBUG: Making chat completions request to {url}")
        print(f"DEBUG: Payload keys: {list(payload.keys())}")
        print(f"DEBUG: Model in payload: {payload.get('model')}")
        print(f"DEBUG: Messages count: {len(messages)}")
        
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
        print(f"DEBUG: Response status: {resp.status_code}")
        
        resp.raise_for_status()
        data = resp.json()
        print(f"DEBUG: Response keys: {list(data.keys())}")
        
        # Check for empty response or missing choices
        if "choices" not in data or not data["choices"]:
            print(f"ERROR: No choices in OpenAI response: {data}")
            raise RuntimeError(f"No choices in OpenAI response")
            
        # Robustly extract content from the first choice
        choice = data["choices"][0]

        def _extract_choice_content(ch: dict) -> str:
            try:
                msg = ch.get("message", {}) if isinstance(ch, dict) else {}
                content_val = msg.get("content")
                # Some providers (or the Responses API) may return a list of blocks
                if isinstance(content_val, list):
                    parts = []
                    for item in content_val:
                        if isinstance(item, dict) and item.get("type") == "text":
                            parts.append(item.get("text") or "")
                        elif isinstance(item, str):
                            parts.append(item)
                    content_str = "\n".join([p for p in parts if p]).strip()
                    if content_str:
                        return content_str
                # Standard string content
                if isinstance(content_val, str) and content_val.strip():
                    return content_val.strip()
                # Tool/function call fallback
                tool_calls = msg.get("tool_calls")
                if isinstance(tool_calls, list) and tool_calls:
                    fn = tool_calls[0].get("function", {})
                    args = fn.get("arguments")
                    if isinstance(args, (dict, list)):
                        return json.dumps(args)
                    if isinstance(args, str) and args.strip():
                        return args.strip()
                if isinstance(msg.get("function_call"), dict):
                    args = msg["function_call"].get("arguments")
                    if isinstance(args, (dict, list)):
                        return json.dumps(args)
                    if isinstance(args, str) and args.strip():
                        return args.strip()
                # Some proxies may put text directly at choice["text"]
                if isinstance(ch.get("text"), str) and ch["text"].strip():
                    return ch["text"].strip()
                # Another non-standard field used by some bridges
                if isinstance(ch.get("response"), str) and ch["response"].strip():
                    return ch["response"].strip()
            except Exception as ex:
                print(f"WARNING: Exception while extracting content: {ex}")
            return ""

        content = _extract_choice_content(choice)

        # If still empty, do not raise; allow downstream fallback to handle gracefully
        if not content:
            print(f"WARNING: Empty content in OpenAI response (chat). Full response: {data}")
            content = ""
    
    def _extract_json_from_response(text: str) -> dict:
        """Extract JSON from potentially malformed response text."""
        # First try direct parsing
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON within the text (common with models that add explanations)
        import re
        
        # Look for JSON block between curly braces
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # Try to extract from markdown code blocks
        code_block_patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```'
        ]
        
        for pattern in code_block_patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    return json.loads(match.strip())
                except json.JSONDecodeError:
                    continue
        
        # If all extraction attempts fail, return None
        return None
    
    # Try to extract valid JSON from the response
    parsed_json = _extract_json_from_response(content)
    
    if parsed_json is not None:
        # Validate that essential fields are present and add defaults if missing
        if 'execution_recommendations' not in parsed_json:
            print("WARNING: execution_recommendations missing from GPT response, adding default structure")
            parsed_json['execution_recommendations'] = {
                "primary_strategy": {"type": "GPT Response Missing", "description": "GPT did not provide execution recommendations", "confidence": "Low", "time_horizon": "Unknown"},
                "alternative_strategies": [],
                "position_sizing": {"suggested_allocation": "Conservative allocation", "risk_level": "Conservative", "justification": "No GPT guidance provided"},
                "entry_conditions": [],
                "exit_conditions": [],
                "stop_loss_guidance": "Use standard risk management",
                "profit_target_guidance": "Use standard profit targets"
            }
        elif not isinstance(parsed_json['execution_recommendations'], dict):
            print(f"WARNING: execution_recommendations is not a dict: {type(parsed_json['execution_recommendations'])}")
            parsed_json['execution_recommendations'] = {
                "primary_strategy": {"type": "Invalid Format", "description": "GPT returned malformed execution recommendations", "confidence": "Low", "time_horizon": "Unknown"},
                "alternative_strategies": [],
                "position_sizing": {"suggested_allocation": "Conservative allocation", "risk_level": "Conservative", "justification": "Malformed GPT response"},
                "entry_conditions": [],
                "exit_conditions": [],
                "stop_loss_guidance": "Use standard risk management",
                "profit_target_guidance": "Use standard profit targets"
            }
        
        # Ensure required subfields exist
        exec_rec = parsed_json['execution_recommendations']
        if 'primary_strategy' not in exec_rec:
            exec_rec['primary_strategy'] = {"type": "Missing Primary", "description": "GPT did not provide primary strategy", "confidence": "Low", "time_horizon": "Unknown"}
        if 'position_sizing' not in exec_rec:
            exec_rec['position_sizing'] = {"suggested_allocation": "Conservative allocation", "risk_level": "Conservative", "justification": "No GPT guidance provided"}
        if 'entry_conditions' not in exec_rec:
            exec_rec['entry_conditions'] = []
        if 'exit_conditions' not in exec_rec:
            exec_rec['exit_conditions'] = []
        if 'alternative_strategies' not in exec_rec:
            exec_rec['alternative_strategies'] = []
        if 'stop_loss_guidance' not in exec_rec:
            exec_rec['stop_loss_guidance'] = "Use standard risk management"
        if 'profit_target_guidance' not in exec_rec:
            exec_rec['profit_target_guidance'] = "Use standard profit targets"
            
        # Ensure other required top-level fields exist
        if 'final_bias' not in parsed_json:
            parsed_json['final_bias'] = 'Neutral'
        if 'summary_html' not in parsed_json:
            parsed_json['summary_html'] = '<p>GPT did not provide summary</p>'
        if 'rationale' not in parsed_json:
            parsed_json['rationale'] = 'GPT did not provide rationale'
        if 'key_reasoning_points' not in parsed_json:
            parsed_json['key_reasoning_points'] = []
        if 'actionable_ideas' not in parsed_json:
            parsed_json['actionable_ideas'] = []
        if 'risk_factors' not in parsed_json:
            parsed_json['risk_factors'] = []
        if 'search_performed' not in parsed_json:
            parsed_json['search_performed'] = False
        if 'sources' not in parsed_json:
            parsed_json['sources'] = []
        
        # Attach model info so downstream save includes it
        if isinstance(parsed_json, dict):
            parsed_json.setdefault('model', model)
        print(f"DEBUG: Final GPT verdict contains execution_recommendations: {bool(parsed_json.get('execution_recommendations'))}")
        return parsed_json
    
    # Log the problematic response for debugging
    if content:
        print(f"WARNING: Failed to parse GPT verdict response as JSON. Raw response: {content[:500]}...")
        summary_html = f"<h5>AI Verdict (Unparsed)</h5><div style='background: #fff3cd; padding: 10px; border-radius: 4px; margin-bottom: 10px;'><strong>⚠️ Note:</strong> AI response could not be parsed as JSON</div><pre style='white-space: pre-wrap; background: #f8f9fa; padding: 10px; border-radius: 4px;'>{content[:1000]}</pre>"
        rationale = "Model response was not valid JSON; returning raw text."
    else:
        print("ERROR: GPT verdict response was completely empty!")
        summary_html = f"<h5>AI Verdict (Empty Response)</h5><div style='background: #f8d7da; padding: 10px; border-radius: 4px; margin-bottom: 10px;'><strong>⚠️ Error:</strong> AI service returned an empty response</div>"
        rationale = "AI service returned an empty response."
    
    # Fallback if model didn't return parseable JSON
    return {
        "final_bias": "Neutral",
        "summary_html": summary_html,
        "rationale": rationale,
        "key_reasoning_points": [],
        "actionable_ideas": [],
        "risk_factors": [],
        "execution_recommendations": {
            "primary_strategy": {"type": "Unknown", "description": "Unable to parse AI response", "confidence": "Low", "time_horizon": "Unknown"},
            "alternative_strategies": [],
            "position_sizing": {"suggested_allocation": "Unknown", "risk_level": "Conservative", "justification": "Unable to parse AI response"},
            "entry_conditions": [],
            "exit_conditions": [],
            "stop_loss_guidance": "Use standard risk management",
            "profit_target_guidance": "Use standard profit targets"
        },
        "search_performed": False,
        "sources": [],
        "model": model
    }


def generate_gpt_verdict(ticker: str, analysis_result: Dict[str, Any], model: str = "gpt-5", use_web_search: bool = False) -> Dict[str, Any]:
    """
    Compose a prompt from the existing sub-analyses and call the LLM to obtain a final verdict.
    Returns a dict with keys:
      - final_bias
      - summary_html (enhanced with structured HTML formatting)
      - rationale (detailed step-by-step reasoning)
      - key_reasoning_points (main analytical points in bullet format)
      - actionable_ideas
      - risk_factors
      - execution_recommendations (comprehensive trading strategy guidance)
      - search_performed
      - sources
    """
    # Select and sanitize relevant fields to control prompt size
    keys_of_interest = [
        "synthesis_data",
        "candlestick_analysis",
        "volume_oi_analysis",
        "movement_analysis_results",
        "results_df",
        "iv_high",
        "iv_low",
        # Enhanced context for better GPT verdict analysis
        "market_data",
        "parity_analysis", 
        "stock_fundamentals",
        "volatility_structure",
        "options_positioning",
        # The following keys are intentionally excluded to force the AI to generate its own
        # verdict from raw data instead of repeating a pre-computed conclusion.
        # "final_conclusion_html",
        # "final_bias",
        # "position_status",
        # "risk_exposure"
    ]
    payload = {k: _sanitize_for_json(analysis_result.get(k)) for k in keys_of_interest if k in analysis_result}
    messages = _build_messages(ticker, payload, use_web_search=use_web_search)

    try:
        ai = _openai_chat_completion(messages, model=model)
        return ai
    except requests.exceptions.Timeout as e:
        timeout_val = int(os.getenv("GPT_VERDICT_TIMEOUT", "180"))
        print(f"ERROR: GPT verdict timed out after {timeout_val} seconds: {e}")
        timeout_error = f"OpenWebUI request timed out after {timeout_val} seconds using model {model}"
    except requests.exceptions.ConnectionError as e:
        print(f"ERROR: GPT verdict connection failed: {e}")
        timeout_error = f"Cannot connect to OpenWebUI service: {str(e)}"
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: GPT verdict HTTP error: {e}")
        timeout_error = f"OpenWebUI returned error {e.response.status_code}: {e.response.text if hasattr(e.response, 'text') else str(e)}"
    except Exception as e:
        print(f"ERROR: GPT verdict failed: {e}")
        timeout_error = f"Unexpected error: {str(e)}"
        
    # Common fallback logic for all error types
    try:
        from ..analysis import generate_holistic_conclusion
        
        # Extract synthesis_data for model-based analysis
        synthesis_data = analysis_result.get("synthesis_data", {})
        if synthesis_data:
            model_html, model_bias = generate_holistic_conclusion(synthesis_data)
            
            # Return model-based verdict with clear indication
            return {
                "final_bias": model_bias,
                "summary_html": f"<h5>Model-Based Verdict (GPT Fallback)</h5><div style='background: #fff3cd; padding: 10px; border-radius: 4px; margin-bottom: 10px;'><strong>⚠️ Note:</strong> {timeout_error}. Showing model-based analysis instead.</div>{model_html}",
                "rationale": f"AI service issue: {timeout_error}. Displaying model-based analysis instead.",
                "key_reasoning_points": [],
                "actionable_ideas": [],
                "risk_factors": [],
                "execution_recommendations": {
                    "primary_strategy": {"type": "Model-Based", "description": "Use recommended strategy from analysis", "confidence": "Medium", "time_horizon": "Short to Medium"},
                    "alternative_strategies": [],
                    "position_sizing": {"suggested_allocation": "Conservative allocation recommended", "risk_level": "Conservative", "justification": "AI service unavailable, using conservative approach"},
                    "entry_conditions": ["Wait for confirmation signals"],
                    "exit_conditions": ["Monitor for reversal patterns"],
                    "stop_loss_guidance": "Use 2-3% stop loss below entry",
                    "profit_target_guidance": "Target 5-10% profit based on analysis"
                },
                "search_performed": False,
                "sources": ["Model-based holistic analysis"]
            }
        else:
            # If no synthesis data available, return basic fallback
            return {
                "final_bias": "Neutral",
                "summary_html": f"<h5>Analysis Unavailable</h5><div style='background: #f8d7da; padding: 10px; border-radius: 4px;'><strong>⚠️ Error:</strong> {timeout_error} and insufficient data for model-based analysis.</div>",
                "rationale": f"Both AI service and model-based analysis unavailable: {timeout_error}",
                "key_reasoning_points": [],
                "actionable_ideas": [],
                "risk_factors": [],
                "execution_recommendations": {
                    "primary_strategy": {"type": "Manual Review", "description": "Manual analysis required due to system issues", "confidence": "Low", "time_horizon": "Unknown"},
                    "alternative_strategies": [],
                    "position_sizing": {"suggested_allocation": "Minimal allocation until analysis available", "risk_level": "Conservative", "justification": "Both AI and model-based analysis unavailable"},
                    "entry_conditions": ["Wait for system recovery"],
                    "exit_conditions": ["Manual monitoring required"],
                    "stop_loss_guidance": "Use tight stop losses",
                    "profit_target_guidance": "Conservative profit targets"
                },
                "search_performed": False,
                "sources": []
            }
                
    except ImportError as import_error:
        print(f"ERROR: Cannot import generate_holistic_conclusion: {import_error}")
        # Ultimate fallback
        return {
            "final_bias": "Neutral",
            "summary_html": f"<h5>Analysis Unavailable</h5><div style='background: #f8d7da; padding: 10px; border-radius: 4px;'><strong>⚠️ Error:</strong> Both GPT service and fallback analysis unavailable.</div><p>GPT Error: {timeout_error}</p><p>Fallback Error: {str(import_error)}</p>",
            "rationale": f"Complete analysis failure - GPT: {timeout_error}, Fallback: {str(import_error)}",
            "key_reasoning_points": [],
            "actionable_ideas": [],
            "risk_factors": [],
            "execution_recommendations": {
                "primary_strategy": {"type": "System Error", "description": "Complete system failure - manual analysis required", "confidence": "Low", "time_horizon": "Unknown"},
                "alternative_strategies": [],
                "position_sizing": {"suggested_allocation": "No position recommended", "risk_level": "Conservative", "justification": "Complete analysis system failure"},
                "entry_conditions": ["System recovery required"],
                "exit_conditions": ["Manual intervention needed"],
                "stop_loss_guidance": "Do not enter positions",
                "profit_target_guidance": "System recovery required"
            },
            "search_performed": False,
            "sources": []
        }
