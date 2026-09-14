"""
Company fundamentals (Mongo screener + Finviz) and AI deep dive with MongoDB caching.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from ..my_libs_py3.db import connect_mongo
from ..my_libs_py3.my_data import PriceDataFetcher
from .prompt_config_service import get_prompt_text, render_prompt

logger = logging.getLogger(__name__)

COLLECTION = "company_deep_dive"
TTL_DAYS = int(os.getenv("COMPANY_DEEP_DIVE_TTL_DAYS", "30"))
DEEP_DIVE_VERSION = "v2"
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-2.5-flash")

SCREENER_RANK_FIELDS = [
    "P/E",
    "P/S",
    "P/Cash",
    "P/Free Cash Flow",
    "Gross Margin",
    "Operating Margin",
    "Profit Margin",
    "EPS (ttm)",
    "Current Ratio",
    "Quick Ratio",
    "Total Debt/Equity",
    "Institutional Ownership",
    "Insider Ownership",
    "Analyst Recom",
    "Performance (Week)",
    "Sales Growth Quarter Over Quarter",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _collection():
    conn = connect_mongo("trader_intelligence", COLLECTION)
    return conn.table


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _load_mongo_screener(ticker: str) -> Dict[str, Any]:
    """Load latest screener snapshot for a ticker from all_symbol.screenerModel."""
    sym = (ticker or "").upper().strip()
    if not sym:
        return {}
    try:
        conn = connect_mongo("all_symbol", "screenerModel")
        latest = conn.table.find_one(
            {"Refresh_Date": {"$exists": True}},
            {"Refresh_Date": 1},
            sort=[("Refresh_Date", -1)],
        )
        if not latest:
            return {}
        refresh_date = latest.get("Refresh_Date")
        doc = conn.table.find_one({"Ticker": sym, "Refresh_Date": refresh_date})
        if not doc:
            return {}
        ranks = {
            field: _clean(doc.get(field))
            for field in SCREENER_RANK_FIELDS
            if doc.get(field) is not None
        }
        refresh_iso = None
        if isinstance(refresh_date, datetime):
            refresh_iso = refresh_date.isoformat()
        return {
            "sector": _clean(doc.get("Sector")),
            "industry": _clean(doc.get("Industry")),
            "refresh_date": refresh_iso,
            "ranks": ranks,
        }
    except Exception as exc:
        logger.warning("Mongo screener load failed for %s: %s", sym, exc)
        return {}


def _load_finviz_profile(ticker: str) -> Dict[str, Any]:
    sym = (ticker or "").upper().strip()
    try:
        fetcher = PriceDataFetcher()
        profile = fetcher.get_company_finviz_profile(sym)
        return profile if isinstance(profile, dict) else {}
    except Exception as exc:
        logger.warning("Finviz profile load failed for %s: %s", sym, exc)
        return {}


def get_fundamentals(ticker: str) -> Dict[str, Any]:
    """
    Merge Mongo screener context with live Finviz fundamentals.

    Note: screenerModel numeric fields are cross-sectional ranks for stock selection,
    not literal ratios. Actual P/E, margins, etc. come from Finviz.
    """
    sym = (ticker or "").upper().strip()
    mongo = _load_mongo_screener(sym)
    finviz = _load_finviz_profile(sym)

    sector = mongo.get("sector") or _clean(finviz.get("sector"))
    industry = mongo.get("industry") or _clean(finviz.get("industry"))
    company_name = _clean(finviz.get("company")) or sym

    description_parts = [p for p in [company_name, sector, industry] if p]
    description = " · ".join(description_parts) if description_parts else ""

    return {
        "ticker": sym,
        "sources": {
            "mongo": bool(mongo),
            "finviz": bool(finviz),
        },
        "profile": {
            "companyName": company_name,
            "sector": sector,
            "industry": industry,
            "country": _clean(finviz.get("country")),
            "description": description,
        },
        "metrics": {
            "price": _clean(finviz.get("price")),
            "marketCap": _clean(finviz.get("market_cap")),
            "pe": _clean(finviz.get("pe")),
            "forwardPe": _clean(finviz.get("forward_pe")),
            "peg": _clean(finviz.get("peg")),
            "ps": _clean(finviz.get("ps")),
            "pb": _clean(finviz.get("pb")),
            "beta": _clean(finviz.get("beta")),
            "roe": _clean(finviz.get("roe")),
            "roa": _clean(finviz.get("roa")),
            "roic": _clean(finviz.get("roic")),
            "debtToEquity": _clean(finviz.get("debt_equity")),
            "currentRatio": _clean(finviz.get("current_ratio")),
            "quickRatio": _clean(finviz.get("quick_ratio")),
            "grossProfitMargin": _clean(finviz.get("gross_margin")),
            "operatingMargin": _clean(finviz.get("operating_margin")),
            "netProfitMargin": _clean(finviz.get("profit_margin")),
            "dividendYield": _clean(finviz.get("dividend_yield")),
            "epsTtm": _clean(finviz.get("eps_ttm")),
            "earningsDate": _clean(finviz.get("earnings_date")),
            "targetPrice": _clean(finviz.get("target_price")),
            "instOwn": _clean(finviz.get("inst_own")),
            "insiderOwn": _clean(finviz.get("insider_own")),
            "perfWeek": _clean(finviz.get("perf_week")),
            "perfMonth": _clean(finviz.get("perf_month")),
            "perfQuarter": _clean(finviz.get("perf_quarter")),
        },
        "screener": {
            "refresh_date": mongo.get("refresh_date"),
            "ranks": mongo.get("ranks") or {},
        },
        "finviz_url": f"https://finviz.com/quote.ashx?t={sym}",
    }


def get_cached_deep_dive(ticker: str) -> Optional[Dict[str, Any]]:
    sym = (ticker or "").upper().strip()
    if not sym:
        return None
    try:
        doc = _collection().find_one({"cache_key": sym})
    except Exception as exc:
        logger.warning("company deep dive cache read failed for %s: %s", sym, exc)
        return None
    if not doc:
        return None

    stale = False
    if doc.get("version") != DEEP_DIVE_VERSION:
        stale = True
    else:
        generated_at = doc.get("generated_at")
        if generated_at:
            try:
                if isinstance(generated_at, str):
                    ts = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                else:
                    ts = generated_at
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_days = (_utc_now() - ts).total_seconds() / 86400.0
                stale = age_days > TTL_DAYS
            except Exception:
                stale = True
        else:
            stale = True

    doc["_stale"] = stale
    if doc.get("_id") is not None:
        doc["id"] = str(doc.pop("_id"))
    return doc


def upsert_deep_dive(
    *,
    ticker: str,
    markdown: str,
    sources: List[str],
    data_sources: List[str],
    model: str,
) -> None:
    sym = (ticker or "").upper().strip()
    doc = {
        "cache_key": sym,
        "ticker": sym,
        "markdown": markdown,
        "sources": sources or [],
        "data_sources": data_sources or [],
        "web_search_performed": False,
        "model": model,
        "version": DEEP_DIVE_VERSION,
        "generated_at": _utc_now().isoformat(),
    }
    try:
        _collection().update_one({"cache_key": sym}, {"$set": doc}, upsert=True)
    except Exception as exc:
        logger.warning("company deep dive cache write failed for %s: %s", sym, exc)


def _synthesize_deep_dive_markdown(ticker: str, fundamentals: Dict[str, Any]) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")

    profile = fundamentals.get("profile") or {}
    metrics = fundamentals.get("metrics") or {}
    screener = fundamentals.get("screener") or {}
    company_name = profile.get("companyName") or ticker

    system_instruction = get_prompt_text("company_intel.system")
    user_prompt = render_prompt(
        "company_intel.user",
        ticker=ticker,
        company_name=company_name,
        profile_json=json.dumps(profile, default=str),
        metrics_json=json.dumps(metrics, default=str),
        screener_json=json.dumps(screener, default=str),
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096},
    }
    resp = requests.post(url, params={"key": key}, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
    text_parts = [str(p.get("text", "")).strip() for p in parts if p.get("text")]
    markdown = "\n".join(t for t in text_parts if t).strip()
    if not markdown:
        raise RuntimeError("Gemini returned empty content")
    return markdown


def generate_deep_dive(ticker: str, fundamentals: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Generate company deep dive from Finviz + Mongo context (Gemini synthesis)."""
    sym = (ticker or "").upper().strip()
    fundamentals = fundamentals or get_fundamentals(sym)
    if not fundamentals.get("sources", {}).get("finviz") and not fundamentals.get("sources", {}).get("mongo"):
        raise RuntimeError(f"No Finviz or Mongo data available for {sym}")

    markdown = _synthesize_deep_dive_markdown(sym, fundamentals)
    sources = [fundamentals.get("finviz_url") or f"https://finviz.com/quote.ashx?t={sym}"]
    data_sources = []
    if fundamentals.get("sources", {}).get("finviz"):
        data_sources.append("finviz")
    if fundamentals.get("sources", {}).get("mongo"):
        data_sources.append("mongo")

    return {
        "markdown": markdown,
        "sources": sources,
        "data_sources": data_sources,
        "web_search_performed": False,
        "model": DEFAULT_GEMINI_MODEL,
    }


def get_or_create_deep_dive(ticker: str, force: bool = False) -> Dict[str, Any]:
    sym = (ticker or "").upper().strip()
    if not sym:
        return {"ticker": "", "markdown": "", "error": "Ticker is required", "from_cache": False}

    cached = get_cached_deep_dive(sym)
    if cached and not force and not cached.get("_stale"):
        out = dict(cached)
        out["from_cache"] = True
        out.pop("_stale", None)
        return out

    try:
        fundamentals = get_fundamentals(sym)
        generated = generate_deep_dive(sym, fundamentals)
        upsert_deep_dive(
            ticker=sym,
            markdown=generated["markdown"],
            sources=generated.get("sources") or [],
            data_sources=generated.get("data_sources") or [],
            model=generated.get("model") or DEFAULT_GEMINI_MODEL,
        )
        fresh = get_cached_deep_dive(sym) or {}
        out = dict(fresh)
        out["from_cache"] = False
        out.pop("_stale", None)
        return out
    except Exception as exc:
        logger.exception("deep dive generation failed for %s: %s", sym, exc)
        if cached:
            stale_doc = dict(cached)
            stale_doc["from_cache"] = True
            stale_doc["stale"] = True
            stale_doc["error"] = str(exc)
            stale_doc.pop("_stale", None)
            return stale_doc
        return {
            "ticker": sym,
            "markdown": "",
            "sources": [f"https://finviz.com/quote.ashx?t={sym}"],
            "data_sources": [],
            "web_search_performed": False,
            "from_cache": False,
            "error": str(exc),
        }
