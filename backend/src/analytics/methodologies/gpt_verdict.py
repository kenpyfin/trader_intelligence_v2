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


def _build_messages(ticker: str, analysis_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build system/user messages for the chat completion API.
    We instruct the model to return strict JSON so we can parse it reliably.
    """
    system = (
        "You are a senior options strategist and equity analyst. "
        "Given structured sub-analyses (trend, candlesticks, parity, volume/oi, iv/hv, movement, undervalued table), "
        "produce a decisive trading verdict for the underlying stock's option positioning. "
        "When possible, perform a quick web search to enrich context (recent catalysts, earnings, regulatory news). "
        "If web search is not available in your current toolset, explicitly state that and proceed with your best judgment. "
        "Return STRICT JSON with keys: "
        "{"
        "\"final_bias\": one of [\"Bullish\",\"Slightly Bullish\",\"Neutral\",\"Slightly Bearish\",\"Bearish\"], "
        "\"summary_html\": string (concise HTML with headings and bullet points), "
        "\"rationale\": string (plain text, 2-5 sentences), "
        "\"actionable_ideas\": [string, ...], "
        "\"risk_factors\": [string, ...], "
        "\"search_performed\": boolean, "
        "\"sources\": [string, ...] "
        "}"
    )

    user = {
        "ticker": ticker,
        "sub_analyses": analysis_payload
    }

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user)}
    ]


def _openai_chat_completion(messages, model: str = "gpt-5", temperature: float = 0.2, timeout: int = 30) -> Dict[str, Any]:
    """
    Minimal OpenAI-compatible chat completion using requests.
    Honors OPENAI_API_BASE and OPENAI_API_KEY from environment.
    """
    base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")

    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except Exception:
        # Fallback if model didn't return strict JSON
        return {
            "final_bias": "Neutral",
            "summary_html": f"<h5>AI Verdict (Unparsed)</h5><p>{content}</p>",
            "rationale": "Model response was not valid JSON; returning raw text.",
            "actionable_ideas": [],
            "risk_factors": [],
            "search_performed": False,
            "sources": []
        }


def generate_gpt_verdict(ticker: str, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compose a prompt from the existing sub-analyses and call the LLM to obtain a final verdict.
    Returns a dict with keys:
      - final_bias
      - summary_html
      - rationale
      - actionable_ideas
      - risk_factors
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
        "market_data",
        "position_status",
        "risk_exposure",
        "iv_high",
        "iv_low",
        "final_conclusion_html",
        "final_bias"
    ]
    payload = {k: _sanitize_for_json(analysis_result.get(k)) for k in keys_of_interest if k in analysis_result}
    messages = _build_messages(ticker, payload)

    try:
        ai = _openai_chat_completion(messages)
        return ai
    except Exception as e:
        # Graceful fallback: return neutral verdict with error note
        return {
            "final_bias": analysis_result.get("final_bias", "Neutral"),
            "summary_html": "<h5>AI Verdict</h5><p>AI call failed; falling back to model-based summary.</p>",
            "rationale": f"AI error: {e}",
            "actionable_ideas": [],
            "risk_factors": [],
            "search_performed": False,
            "sources": []
        }
