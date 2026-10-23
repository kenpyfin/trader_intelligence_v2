"""Stateless Gemini chat grounded in a single analysis result."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence

import requests

from ..analytics.methodologies.gpt_verdict import _resolve_gemini_model
from .prompt_config_service import get_prompt_text, render_prompt

logger = logging.getLogger(__name__)

NESTED_DROP = {"plot_data"}
KEEP_TOP_LEVEL = (
    "ticker",
    "S_current",
    "expiration_date",
    "dte",
    "analysis_method",
    "gpt_model",
    "final_bias",
    "final_conclusion_html",
    "recommended_strategy",
    "recommended_strategies",
    "gpt_verdict",
    "synthesis_data",
    "macro_context",
    "technical_analysis",
    "volume_oi_analysis",
    "movement_analysis_results",
    "market_data",
    "stock_fundamentals",
    "volatility_structure",
    "options_positioning",
    "parity_analysis",
    "iv_high",
    "iv_low",
    "results_df",
)
MAX_CONTEXT_CHARS = 80_000
MAX_MESSAGES = 20
MAX_MESSAGE_CHARS = 4000
RESULTS_DF_SAMPLE = 15
ALLOWED_ROLES = {"user", "assistant"}
DEFAULT_MODEL = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-2.5-flash")
GEMINI_TIMEOUT_SECONDS = 90


def _strip_html(html: Optional[str], max_len: int = 4000) -> str:
    if not html or not isinstance(html, str):
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        return text[:max_len].rstrip() + "..."
    return text


def _drop_nested(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _drop_nested(item)
            for key, item in value.items()
            if key not in NESTED_DROP
        }
    if isinstance(value, list):
        return [_drop_nested(item) for item in value]
    return value


def _summarize_results_df(rows: Any) -> Dict[str, Any]:
    if not isinstance(rows, list):
        return {"count": 0, "sample": []}
    sample = rows[:RESULTS_DF_SAMPLE]
    return {"count": len(rows), "sample": _drop_nested(sample)}


def _summarize_parity(parity: Any) -> Dict[str, Any]:
    if not isinstance(parity, dict):
        return {}
    raw = parity.get("parity_data")
    row_count = len(raw) if isinstance(raw, list) else 0
    return {
        "arbitrage_opportunities": parity.get("arbitrage_opportunities"),
        "parity_row_count": row_count,
    }


def compact_analysis_context(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Keep conclusion and trading fields; drop bulky chart/table blobs."""
    source = analysis if isinstance(analysis, dict) else {}
    compacted: Dict[str, Any] = {}
    for key in KEEP_TOP_LEVEL:
        if key not in source:
            continue
        value = source.get(key)
        if key == "final_conclusion_html":
            compacted["final_conclusion"] = _strip_html(value)
            continue
        if key == "results_df":
            compacted["results_df"] = _summarize_results_df(value)
            continue
        if key == "parity_analysis":
            compacted["parity_analysis"] = _summarize_parity(value)
            continue
        compacted[key] = _drop_nested(value)
    return compacted


def serialize_analysis_json(compacted: Dict[str, Any]) -> str:
    text = json.dumps(compacted, default=str)
    if len(text) > MAX_CONTEXT_CHARS:
        return text[:MAX_CONTEXT_CHARS].rstrip() + "...[truncated]"
    return text


def _as_message_dicts(history: Sequence[Any]) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    for item in history or []:
        if hasattr(item, "role") and hasattr(item, "content"):
            role = str(getattr(item, "role", "") or "").strip().lower()
            content = str(getattr(item, "content", "") or "")
        elif isinstance(item, dict):
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "")
        else:
            raise ValueError("Each chat message must be an object with role and content")
        messages.append({"role": role, "content": content})
    return messages


def validate_chat_history(history: Sequence[Any]) -> List[Dict[str, str]]:
    messages = _as_message_dicts(history)
    if not messages:
        raise ValueError("messages cannot be empty")
    if len(messages) > MAX_MESSAGES:
        raise ValueError(f"messages cannot exceed {MAX_MESSAGES} items")
    for message in messages:
        if message["role"] not in ALLOWED_ROLES:
            raise ValueError("message role must be 'user' or 'assistant'")
        content = message["content"].strip()
        if not content:
            raise ValueError("message content cannot be empty")
        if len(content) > MAX_MESSAGE_CHARS:
            raise ValueError(f"message content cannot exceed {MAX_MESSAGE_CHARS} characters")
        message["content"] = content
    if messages[-1]["role"] != "user":
        raise ValueError("last message must be from the user")
    return messages


def build_chat_messages(analysis: Dict[str, Any], history: Sequence[Any]) -> List[Dict[str, str]]:
    """System + analysis context, followed by the user/assistant thread."""
    compacted = compact_analysis_context(analysis)
    ticker = str(compacted.get("ticker") or analysis.get("ticker") or "").strip().upper()
    expiration = str(compacted.get("expiration_date") or analysis.get("expiration_date") or "")
    analysis_json = serialize_analysis_json(compacted)
    system = get_prompt_text("analysis_chat.system")
    context = render_prompt(
        "analysis_chat.context",
        ticker=ticker or "UNKNOWN",
        expiration_date=expiration or "unknown",
        analysis_json=analysis_json,
    )
    validated = validate_chat_history(history)
    return [
        {"role": "system", "content": f"{system}\n\n{context}"},
        *validated,
    ]


def _to_gemini_contents(history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    contents: List[Dict[str, Any]] = []
    for message in history:
        gemini_role = "model" if message["role"] == "assistant" else "user"
        text = message["content"]
        if contents and contents[-1]["role"] == gemini_role:
            contents[-1]["parts"][0]["text"] += "\n\n" + text
            continue
        contents.append({"role": gemini_role, "parts": [{"text": text}]})
    while contents and contents[0]["role"] == "model":
        contents.pop(0)
    if not contents:
        raise ValueError("chat history must include a user message")
    return contents


def _extract_gemini_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
    text_parts = [str(part.get("text") or "").strip() for part in parts if part.get("text")]
    return "\n".join(part for part in text_parts if part).strip()


def generate_analysis_chat_reply(
    analysis: Dict[str, Any],
    messages: Sequence[Any],
    model: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    """Call Gemini in text mode with compact analysis context."""
    if not isinstance(analysis, dict):
        raise ValueError("analysis is required")
    ticker = str(analysis.get("ticker") or "").strip()
    if not ticker:
        raise ValueError("analysis.ticker is required")

    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    chat_messages = build_chat_messages(analysis, messages)
    system_instruction = chat_messages[0]["content"]
    contents = _to_gemini_contents(chat_messages[1:])
    resolved_model = _resolve_gemini_model(model or DEFAULT_MODEL)
    if not str(resolved_model).lower().startswith("gemini"):
        resolved_model = DEFAULT_MODEL

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{resolved_model}:generateContent"
    payload = {
        "contents": contents,
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2048,
        },
    }

    logger.info(
        "Analysis chat Gemini request",
        extra={
            "ticker": ticker.upper(),
            "model": resolved_model,
            "message_count": len(contents),
        },
    )

    try:
        response = requests.post(url, params={"key": api_key}, json=payload, timeout=GEMINI_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(f"Gemini chat timed out after {GEMINI_TIMEOUT_SECONDS}s") from exc
    except requests.exceptions.HTTPError as exc:
        status = getattr(exc.response, "status_code", None)
        snippet = ""
        if exc.response is not None:
            snippet = (exc.response.text or "")[:400]
        raise RuntimeError(f"Gemini chat HTTP {status}: {snippet}") from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Gemini chat request failed: {exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("Gemini chat returned invalid JSON") from exc

    reply = _extract_gemini_text(data)
    if not reply:
        raise RuntimeError("Gemini returned empty content")

    return {
        "status": "success",
        "reply": reply,
        "model": resolved_model,
    }
