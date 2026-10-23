"""Load, persist, and render editable GPT / LLM prompts."""
from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pymongo

from .prompt_defaults import PROMPT_BY_ID, PROMPT_DEFINITIONS, PromptDefinition

logger = logging.getLogger(__name__)

DB_NAME = "trader_intelligence"
COLLECTION = "gpt_prompt_overrides"
MAX_PROMPT_CHARS = 100_000
MONGO_URI = "mongodb://10.0.1.22:27017"

_cache_lock = threading.Lock()
_overrides: Optional[Dict[str, Dict[str, Any]]] = None
_mongo_client: Optional[pymongo.MongoClient] = None


class UnknownPromptError(KeyError):
    """Raised when a prompt id is not in the catalog."""


class PromptValidationError(ValueError):
    """Raised when prompt text fails validation."""


def _get_collection():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = pymongo.MongoClient(
            MONGO_URI,
            tz_aware=True,
            serverSelectionTimeoutMS=3000,
        )
    return _mongo_client[DB_NAME][COLLECTION]


def _ensure_cache() -> Dict[str, Dict[str, Any]]:
    global _overrides
    with _cache_lock:
        if _overrides is not None:
            return _overrides
        loaded: Dict[str, Dict[str, Any]] = {}
        try:
            for doc in _get_collection().find({}):
                prompt_id = doc.get("_id")
                text = doc.get("text")
                if prompt_id not in PROMPT_BY_ID or not isinstance(text, str):
                    continue
                loaded[str(prompt_id)] = {
                    "text": text,
                    "updated_at": doc.get("updated_at"),
                }
        except Exception as exc:
            logger.warning("Could not load GPT prompt overrides from Mongo: %s", exc)
        _overrides = loaded
        return _overrides


def reset_prompt_cache() -> None:
    """Clear the in-memory override cache (tests and after bulk reset)."""
    global _overrides
    with _cache_lock:
        _overrides = None


def get_definition(prompt_id: str) -> PromptDefinition:
    definition = PROMPT_BY_ID.get(prompt_id)
    if definition is None:
        raise UnknownPromptError(prompt_id)
    return definition


def get_prompt_text(prompt_id: str) -> str:
    """Return the active prompt text (override if present, else built-in default)."""
    definition = get_definition(prompt_id)
    cache = _ensure_cache()
    override = cache.get(prompt_id)
    if override and isinstance(override.get("text"), str):
        return override["text"]
    return definition.default_text


def render_prompt(prompt_id: str, **kwargs: Any) -> str:
    """Replace documented {placeholders} only; other braces are left intact."""
    text = get_prompt_text(prompt_id)
    definition = get_definition(prompt_id)
    for key in definition.placeholders:
        if key not in kwargs:
            continue
        text = text.replace("{" + key + "}", str(kwargs[key]))
    return text


def _isoformat(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return str(value)


def serialize_prompt(prompt_id: str) -> Dict[str, Any]:
    definition = get_definition(prompt_id)
    cache = _ensure_cache()
    override = cache.get(prompt_id)
    text = override["text"] if override and isinstance(override.get("text"), str) else definition.default_text
    return {
        "id": definition.id,
        "name": definition.name,
        "category": definition.category,
        "description": definition.description,
        "role": definition.role,
        "placeholders": list(definition.placeholders),
        "text": text,
        "default_text": definition.default_text,
        "is_customized": prompt_id in cache,
        "updated_at": _isoformat(override.get("updated_at") if override else None),
    }


def list_prompts() -> List[Dict[str, Any]]:
    _ensure_cache()
    return [serialize_prompt(item.id) for item in PROMPT_DEFINITIONS]


def list_categories() -> List[str]:
    seen = []
    for item in PROMPT_DEFINITIONS:
        if item.category not in seen:
            seen.append(item.category)
    return seen


def _validate_text(text: Any) -> str:
    if not isinstance(text, str):
        raise PromptValidationError("Prompt text must be a string")
    if not text.strip():
        raise PromptValidationError("Prompt text cannot be empty")
    if len(text) > MAX_PROMPT_CHARS:
        raise PromptValidationError(f"Prompt text exceeds {MAX_PROMPT_CHARS} characters")
    return text


def update_prompt(prompt_id: str, text: str) -> Dict[str, Any]:
    get_definition(prompt_id)
    validated = _validate_text(text)
    now = datetime.now(timezone.utc)
    cache = _ensure_cache()
    with _cache_lock:
        cache[prompt_id] = {"text": validated, "updated_at": now}
    persisted = True
    try:
        _get_collection().update_one(
            {"_id": prompt_id},
            {"$set": {"text": validated, "updated_at": now}},
            upsert=True,
        )
    except Exception as exc:
        persisted = False
        logger.warning("Could not persist GPT prompt override for %s: %s", prompt_id, exc)
    payload = serialize_prompt(prompt_id)
    payload["persisted"] = persisted
    return payload


def reset_prompt(prompt_id: str) -> Dict[str, Any]:
    get_definition(prompt_id)
    cache = _ensure_cache()
    with _cache_lock:
        cache.pop(prompt_id, None)
    persisted = True
    try:
        _get_collection().delete_one({"_id": prompt_id})
    except Exception as exc:
        persisted = False
        logger.warning("Could not delete GPT prompt override for %s: %s", prompt_id, exc)
    payload = serialize_prompt(prompt_id)
    payload["persisted"] = persisted
    return payload


def reset_all_prompts() -> Dict[str, Any]:
    cache = _ensure_cache()
    with _cache_lock:
        cache.clear()
    persisted = True
    try:
        _get_collection().delete_many({})
    except Exception as exc:
        persisted = False
        logger.warning("Could not delete GPT prompt overrides: %s", exc)
    return {
        "prompts": list_prompts(),
        "persisted": persisted,
    }


# Same file can be imported as src.services... or services... depending on sys.path.
# Keep a single module instance so overrides and test patches apply everywhere.
for _alias in ("src.services.prompt_config_service", "services.prompt_config_service"):
    if _alias != __name__:
        sys.modules[_alias] = sys.modules[__name__]
