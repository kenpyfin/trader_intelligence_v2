"""Gemini / GPT model listing helpers for the Analysis UI."""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-2.5-flash")

# Curated fallbacks so the UI can still offer model choices when the live
# Gemini list endpoint is unavailable (auth failure, rate limit, network).
DEFAULT_GPT_MODELS: List[Dict[str, str]] = [
    {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
    {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
    {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash"},
    {"id": "gemini-flash-latest", "name": "Gemini Flash Latest"},
]


def _default_model_id() -> str:
    return os.getenv("GEMINI_DEFAULT_MODEL", "gemini-2.5-flash")


def fallback_gpt_models() -> List[Dict[str, str]]:
    """Return a copy of the curated fallback model list."""
    return [dict(item) for item in DEFAULT_GPT_MODELS]


def parse_gemini_models_payload(models_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Map Gemini listModels JSON into [{id, name}, ...] for generateContent models."""
    models: List[Dict[str, str]] = []
    for model in models_data.get("models", []) if isinstance(models_data, dict) else []:
        name = model.get("name", "")
        if not isinstance(name, str) or not name.startswith("models/"):
            continue
        generation_methods = model.get("supportedGenerationMethods", []) or []
        if "generateContent" not in generation_methods:
            continue
        model_id = name.split("/", 1)[1]
        models.append(
            {
                "id": model_id,
                "name": model.get("displayName", model_id) or model_id,
            }
        )
    models.sort(key=lambda x: x["name"])
    return models


def classify_gemini_models_error(status_code: int, body_text: str) -> Tuple[str, str]:
    """
    Return (error_code, human_message) for a failed Gemini models list call.
    """
    text = body_text or ""
    lowered = text.lower()
    if status_code in (401, 403) and "leaked" in lowered:
        return (
            "api_key_leaked",
            "Gemini API key was reported as leaked. Create a new key in Google AI Studio "
            "and update GEMINI_API_KEY in .env, then restart the backend.",
        )
    if status_code in (401, 403):
        return (
            "api_key_invalid",
            f"Gemini rejected the API key (HTTP {status_code}). Check GEMINI_API_KEY.",
        )
    if status_code == 429:
        return (
            "rate_limited",
            "Gemini model listing is rate-limited. Showing fallback models temporarily.",
        )
    return (
        "upstream_error",
        f"Failed to fetch Gemini models (HTTP {status_code}). Showing fallback models.",
    )


def list_gpt_models(
    api_key: Optional[str] = None,
    http_get: Optional[Callable[..., Any]] = None,
    timeout: int = 10,
) -> Dict[str, Any]:
    """
    List GPT/Gemini models for the Analysis UI.

    Always returns a usable models list. When the live Gemini call fails,
    returns curated fallbacks with status='degraded' and a warning so the
    frontend can keep the selector working and show a clear connection message.
    """
    key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY")
    default_model = _default_model_id()
    getter = http_get or requests.get

    if not key:
        return {
            "status": "degraded",
            "models": fallback_gpt_models(),
            "default": default_model,
            "warning": "Gemini API key not configured. Set GEMINI_API_KEY in .env.",
            "error_code": "missing_api_key",
            "source": "fallback",
        }

    try:
        response = getter(
            GEMINI_MODELS_URL,
            params={"key": key},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return {
            "status": "degraded",
            "models": fallback_gpt_models(),
            "default": default_model,
            "warning": f"Failed to connect to Gemini model service: {exc}",
            "error_code": "connection_error",
            "source": "fallback",
        }

    status_code = getattr(response, "status_code", 0)
    body_text = ""
    try:
        body_text = response.text[:500] if getattr(response, "text", None) else ""
    except Exception:
        body_text = ""

    if status_code != 200:
        error_code, warning = classify_gemini_models_error(status_code, body_text)
        return {
            "status": "degraded",
            "models": fallback_gpt_models(),
            "default": default_model,
            "warning": warning,
            "error_code": error_code,
            "source": "fallback",
            "upstream_status": status_code,
        }

    try:
        models_data = response.json()
    except ValueError:
        return {
            "status": "degraded",
            "models": fallback_gpt_models(),
            "default": default_model,
            "warning": "Gemini returned invalid JSON for model listing. Showing fallback models.",
            "error_code": "invalid_response",
            "source": "fallback",
        }

    models = parse_gemini_models_payload(models_data)
    if not models:
        return {
            "status": "degraded",
            "models": fallback_gpt_models(),
            "default": default_model,
            "warning": "Gemini returned no generateContent models. Showing fallback models.",
            "error_code": "empty_models",
            "source": "fallback",
        }

    return {
        "status": "success",
        "models": models,
        "default": default_model,
        "source": "gemini",
    }
