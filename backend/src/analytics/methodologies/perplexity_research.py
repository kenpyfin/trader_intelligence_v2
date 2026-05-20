"""
Perplexity Sonar web research for Web Verdict analysis.
Fetches recent news, catalysts, and citations to inject into the Gemini Analyst stage.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("perplexity_research")

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
DEFAULT_MODEL = os.getenv("PERPLEXITY_MODEL", "sonar")
DEFAULT_TIMEOUT = int(os.getenv("PERPLEXITY_TIMEOUT", "45"))


class PerplexityConfigError(RuntimeError):
    """Raised when Web Verdict is requested but Perplexity is not configured."""


class PerplexityAPIError(RuntimeError):
    """Raised when the Perplexity API returns an error or unusable response."""


def _require_api_key() -> str:
    key = os.getenv("PERPLEXITY_API_KEY", "").strip()
    if not key:
        raise PerplexityConfigError(
            "Web Verdict requires PERPLEXITY_API_KEY. "
            "Set it in your environment or .env file to enable web research."
        )
    return key


def _build_research_prompt(
    ticker: str,
    expiration_date: str,
    days_to_earnings: Optional[int] = None,
) -> str:
    earnings_note = ""
    if days_to_earnings is not None:
        earnings_note = f" Days to next earnings: {days_to_earnings}."

    return (
        f"Research {ticker} stock for an options trade expiring on {expiration_date}.{earnings_note}\n\n"
        "Find and summarize the most relevant recent information (last 2-4 weeks), including:\n"
        "- Breaking news and headlines\n"
        "- Upcoming or recent earnings and other catalysts\n"
        "- Analyst rating changes and price target updates\n"
        "- Regulatory, legal, or M&A developments\n"
        "- Sector and macro headlines that materially affect this stock\n\n"
        "Provide a concise bullet-style summary focused on what matters for a directional "
        "options thesis through the expiration date. Cite specific facts; avoid generic filler."
    )


def _extract_sources(data: Dict[str, Any]) -> List[str]:
    sources: List[str] = []
    citations = data.get("citations")
    if isinstance(citations, list):
        for item in citations:
            if isinstance(item, str) and item.strip():
                sources.append(item.strip())

    search_results = data.get("search_results")
    if isinstance(search_results, list):
        for result in search_results:
            if not isinstance(result, dict):
                continue
            url = result.get("url") or result.get("link")
            if isinstance(url, str) and url.strip() and url.strip() not in sources:
                sources.append(url.strip())

    return sources


def fetch_web_context(
    ticker: str,
    expiration_date: str,
    *,
    days_to_earnings: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetch web-grounded research from Perplexity Sonar for the given ticker and expiration.

    Raises:
        PerplexityConfigError: If PERPLEXITY_API_KEY is not set.
        PerplexityAPIError: On HTTP errors, timeouts, or empty responses.
    """
    api_key = _require_api_key()
    model = DEFAULT_MODEL
    timeout = DEFAULT_TIMEOUT
    prompt = _build_research_prompt(ticker, expiration_date, days_to_earnings)

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a financial research assistant. Provide factual, recent market "
                    "intelligence with clear sourcing. Be concise and trading-focused."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    logger.info(
        "Fetching Perplexity web context",
        extra={"ticker": ticker, "expiration_date": expiration_date, "model": model},
    )

    try:
        resp = requests.post(
            PERPLEXITY_API_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except requests.exceptions.Timeout as exc:
        raise PerplexityAPIError(
            f"Perplexity request timed out after {timeout}s"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise PerplexityAPIError(f"Perplexity request failed: {exc}") from exc

    if resp.status_code != 200:
        snippet = resp.text[:500] if resp.text else ""
        raise PerplexityAPIError(
            f"Perplexity API error (HTTP {resp.status_code}): {snippet}"
        )

    try:
        data = resp.json()
    except ValueError as exc:
        raise PerplexityAPIError("Perplexity returned invalid JSON") from exc

    choices = data.get("choices") or []
    if not choices:
        raise PerplexityAPIError("Perplexity returned no choices")

    message = (choices[0] or {}).get("message") or {}
    summary = (message.get("content") or "").strip()
    if not summary:
        raise PerplexityAPIError("Perplexity returned empty content")

    sources = _extract_sources(data)
    search_results = data.get("search_results")
    if not isinstance(search_results, list):
        search_results = []

    return {
        "provider": "perplexity",
        "model": model,
        "summary": summary,
        "sources": sources,
        "search_results": search_results,
        "search_performed": True,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
