"""
Deterministic market-data tools for the exit-signal Gemini agent.
Returns JSON facts only; the LLM interprets fuzzy language (e.g. "approaches", "near").
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

AGENT_VERSION = "2.0.0"


def extract_dollar_levels_from_text(text: str) -> List[float]:
    """Pull explicit $ prices from condition wording (e.g. 'near $351.85')."""
    levels: List[float] = []
    for m in re.finditer(r"\$\s*(\d+(?:\.\d+)?)", text or ""):
        try:
            levels.append(float(m.group(1)))
        except ValueError:
            continue
    return levels


def compare_price_to_level(
    current_price: float,
    level: float,
    *,
    near_pct: float = 3.0,
) -> Dict[str, Any]:
    """Pure helper: distance from current price to a reference level."""
    if level == 0:
        return {"error": "level must be non-zero"}
    pct_diff = ((current_price - level) / level) * 100.0
    abs_pct = abs(pct_diff)
    return {
        "current_price": round(current_price, 4),
        "level": round(level, 4),
        "pct_diff_from_level": round(pct_diff, 4),
        "abs_pct_diff": round(abs_pct, 4),
        "is_above": current_price > level,
        "is_below": current_price < level,
        "is_near_default_3pct": abs_pct <= near_pct,
        "near_threshold_pct": near_pct,
    }


@dataclass
class ExitSignalToolDeps:
    """Injectable dependencies for tool execution (testing + production)."""

    price_fetcher: Any = None
    fmp_client: Any = None
    spot_overrides: Dict[str, float] = field(default_factory=dict)

    def _fetcher(self):
        if self.price_fetcher is None:
            from src.my_libs_py3.my_data import PriceDataFetcher

            self.price_fetcher = PriceDataFetcher()
        return self.price_fetcher

    def _fmp(self):
        if self.fmp_client is None:
            from src.my_libs_py3.fmp import FMPClient

            self.fmp_client = FMPClient()
        return self.fmp_client


def _load_daily_closes(ticker: str, lookback: int = 400) -> Optional[pd.Series]:
    try:
        from src.my_libs_py3.db import connect_mongo

        conn = connect_mongo("stocks_daily")
        coll = conn.db[ticker]
        docs = list(
            coll.find({}, {"_id": 0, "Close": 1, "TimeStamp": 1})
            .sort("TimeStamp", -1)
            .limit(lookback)
        )
        if len(docs) < 20:
            fetcher = ExitSignalToolDeps()._fetcher()
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=lookback)
            df = fetcher.get_price_data([ticker], method="td_data", start_date=start_dt, end_date=end_dt)
            if df is None or df.empty or "Close" not in df.columns:
                return None
            return pd.to_numeric(df["Close"], errors="coerce").dropna()

        df = pd.DataFrame(docs).sort_values("TimeStamp")
        return pd.to_numeric(df["Close"], errors="coerce").dropna()
    except Exception as exc:
        logger.warning("daily closes fetch failed for %s: %s", ticker, exc)
        return None


def get_spot_price(ticker: str, deps: Optional[ExitSignalToolDeps] = None) -> Dict[str, Any]:
    sym = (ticker or "").strip().upper()
    if not sym:
        return {"error": "ticker required"}

    deps = deps or ExitSignalToolDeps()
    if sym in deps.spot_overrides:
        return {"ticker": sym, "spot_price": deps.spot_overrides[sym], "source": "override"}

    price = None
    source = None
    try:
        rt = deps._fmp().realtimequote(sym)
        if rt is not None and not rt.empty and "price" in rt.columns:
            val = rt.price.iloc[0]
            if val and float(val) > 0:
                price = float(val)
                source = "FMP"
    except Exception as exc:
        logger.debug("FMP spot failed %s: %s", sym, exc)

    if price is None:
        try:
            details = deps._fetcher().get_stock_details_finviz(sym)
            p = details.get("price") if details else None
            if p is not None and not (isinstance(p, float) and np.isnan(p)):
                price = float(p)
                source = "Finviz"
        except Exception as exc:
            logger.debug("Finviz spot failed %s: %s", sym, exc)

    if price is None:
        return {"ticker": sym, "error": "could not fetch spot price"}

    return {"ticker": sym, "spot_price": round(price, 4), "source": source}


def get_sma(ticker: str, window: int = 200, deps: Optional[ExitSignalToolDeps] = None) -> Dict[str, Any]:
    sym = (ticker or "").strip().upper()
    w = int(window)
    if w not in (20, 50, 200):
        return {"error": "window must be 20, 50, or 200"}

    closes = _load_daily_closes(sym, lookback=max(400, w + 50))
    if closes is None or len(closes) < w:
        return {"ticker": sym, "window": w, "error": "insufficient price history"}

    sma = float(closes.tail(w).mean())
    spot = get_spot_price(sym, deps)
    current = spot.get("spot_price")
    result: Dict[str, Any] = {
        "ticker": sym,
        "window": w,
        "sma": round(sma, 4),
        "bars_used": int(min(len(closes), w)),
    }
    if current is not None:
        result["spot_price"] = current
        result["spot_vs_sma_pct"] = round(((current - sma) / sma) * 100.0, 4) if sma else None
        result["price_above_sma"] = current > sma
        result["price_below_sma"] = current < sma
    return result


def compare_spot_to_stated_levels(
    ticker: str,
    condition_text: str,
    near_pct: float = 3.0,
    deps: Optional[ExitSignalToolDeps] = None,
) -> Dict[str, Any]:
    """
    Compare live spot to every $ level written in the condition text.
    Use this when the condition cites a specific price (e.g. 'near $351.85').
    Rolling recent-high from get_recent_high_low does NOT override these levels.
    """
    sym = (ticker or "").strip().upper()
    levels = extract_dollar_levels_from_text(condition_text)
    if not levels:
        return {
            "ticker": sym,
            "error": "no dollar levels found in condition text",
            "levels": [],
        }

    spot_payload = get_spot_price(sym, deps)
    spot = spot_payload.get("spot_price")
    if spot is None:
        return {"ticker": sym, "error": spot_payload.get("error", "no spot price"), "levels": levels}

    comparisons = []
    for level in levels:
        row = compare_price_to_level(float(spot), float(level), near_pct=near_pct)
        row["stated_level"] = level
        comparisons.append(row)

    any_near = any(c.get("is_near_default_3pct") for c in comparisons)
    all_below = all(c.get("is_below") for c in comparisons if c.get("is_below") is not None)

    return {
        "ticker": sym,
        "spot_price": spot,
        "near_threshold_pct": near_pct,
        "stated_level_comparisons": comparisons,
        "any_stated_level_near_spot": any_near,
        "spot_below_all_stated_levels": all_below and len(comparisons) > 0,
        "interpretation_hint": (
            "For 'approaches/near $X', use any_stated_level_near_spot. "
            "Do not treat rolling 20d high as a substitute for a cited $X."
        ),
    }


def get_recent_high_low(
    ticker: str,
    window_days: int = 20,
    deps: Optional[ExitSignalToolDeps] = None,
) -> Dict[str, Any]:
    sym = (ticker or "").strip().upper()
    w = int(window_days)
    if w < 5 or w > 252:
        return {"error": "window_days must be between 5 and 252"}

    closes = _load_daily_closes(sym, lookback=max(400, w + 10))
    if closes is None or len(closes) < w:
        return {"ticker": sym, "window_days": w, "error": "insufficient price history"}

    window = closes.tail(w)
    high = float(window.max())
    low = float(window.min())
    spot = get_spot_price(sym, deps)
    current = spot.get("spot_price")

    result: Dict[str, Any] = {
        "ticker": sym,
        "window_days": w,
        "recent_high": round(high, 4),
        "recent_low": round(low, 4),
        "bars_used": len(window),
    }
    if current is not None:
        result["spot_price"] = current
        result["pct_below_recent_high"] = round(((current - high) / high) * 100.0, 4) if high else None
        result["pct_above_recent_low"] = round(((current - low) / low) * 100.0, 4) if low else None
        if high:
            result["distance_to_high"] = compare_price_to_level(current, high)
        result["spot_at_rolling_high"] = (
            result.get("distance_to_high", {}).get("is_near_default_3pct") is True
        )
    return result


def get_iv_context(ticker: str, deps: Optional[ExitSignalToolDeps] = None) -> Dict[str, Any]:
    sym = (ticker or "").strip().upper()
    deps = deps or ExitSignalToolDeps()

    iv_rank = None
    spot_iv = None
    iv_30d = None
    iv_7d = None
    try:
        from src.analytics.analysis import calculate_iv_rank

        iv_rank = calculate_iv_rank(sym)
    except Exception as exc:
        logger.debug("iv rank failed %s: %s", sym, exc)

    try:
        from src.my_libs_py3.db import connect_mongo

        db = connect_mongo("iv_history", sym)
        latest = db.table.find_one({"Ticker": sym}, sort=[("TimeStamp", -1)])
        if latest:
            spot_iv = latest.get("spot_iv")
            iv_30d = latest.get("iv_30d")
            iv_7d = latest.get("iv_7d")
    except Exception:
        pass

    hv = None
    hv_rank = None
    iv_hv_ratio = None
    try:
        closes = _load_daily_closes(sym, 300)
        if closes is not None and len(closes) >= 30:
            from src.analytics.analysis import calculate_hv_rank

            hv, hv_rank = calculate_hv_rank(closes)
            if spot_iv is not None and hv and hv > 0:
                iv_hv_ratio = float(spot_iv) / float(hv)
    except Exception as exc:
        logger.debug("hv context failed %s: %s", sym, exc)

    iv_term_slope = None
    if iv_30d is not None and iv_7d is not None:
        iv_term_slope = float(iv_30d) - float(iv_7d)

    return {
        "ticker": sym,
        "spot_iv": _round_optional(spot_iv),
        "iv_rank": _round_optional(iv_rank),
        "hv_rank": _round_optional(hv_rank),
        "historical_volatility": _round_optional(hv),
        "iv_hv_ratio": _round_optional(iv_hv_ratio),
        "iv_30d": _round_optional(iv_30d),
        "iv_7d": _round_optional(iv_7d),
        "iv_term_slope": _round_optional(iv_term_slope),
    }


def get_earnings_context(ticker: str, deps: Optional[ExitSignalToolDeps] = None) -> Dict[str, Any]:
    sym = (ticker or "").strip().upper()
    deps = deps or ExitSignalToolDeps()

    earnings_str = None
    try:
        details = deps._fetcher().get_stock_details_finviz(sym)
        if details:
            earnings_str = details.get("Earnings_date")
    except Exception as exc:
        logger.debug("earnings fetch failed %s: %s", sym, exc)

    from src.analytics.analysis import parse_earnings_date

    earnings_date = parse_earnings_date(str(earnings_str) if earnings_str is not None else None)
    today = date.today()
    days_until = None
    if earnings_date:
        days_until = (earnings_date - today).days

    return {
        "ticker": sym,
        "earnings_date_raw": str(earnings_str) if earnings_str is not None else None,
        "earnings_date": earnings_date.isoformat() if earnings_date else None,
        "days_until_earnings": days_until,
        "is_before_earnings": days_until > 0 if days_until is not None else None,
    }


def _round_optional(val: Any, places: int = 4) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return round(f, places)
    except (TypeError, ValueError):
        return None


# Gemini functionDeclarations + local registry
GEMINI_FUNCTION_DECLARATIONS: List[Dict[str, Any]] = [
    {
        "name": "get_spot_price",
        "description": "Current underlying stock price for a ticker.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "ticker": {"type": "STRING", "description": "Stock symbol, e.g. AAPL"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_sma",
        "description": "Simple moving average (20, 50, or 200-day) and spot vs SMA.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "ticker": {"type": "STRING"},
                "window": {"type": "INTEGER", "description": "20, 50, or 200"},
            },
            "required": ["ticker", "window"],
        },
    },
    {
        "name": "get_recent_high_low",
        "description": "Recent high/low over N trading days and distance from spot.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "ticker": {"type": "STRING"},
                "window_days": {"type": "INTEGER", "description": "Lookback days, e.g. 20 or 252"},
            },
            "required": ["ticker", "window_days"],
        },
    },
    {
        "name": "get_iv_context",
        "description": "Implied volatility, IV rank, HV, and IV/HV ratio.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"ticker": {"type": "STRING"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_earnings_context",
        "description": "Next earnings date and days until earnings.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"ticker": {"type": "STRING"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "compare_spot_to_stated_levels",
        "description": (
            "Extracts $ prices from condition text and compares live spot to each cited level."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "ticker": {"type": "STRING"},
                "condition_text": {
                    "type": "STRING",
                    "description": "Full exit condition sentence containing $ levels",
                },
                "near_pct": {"type": "NUMBER", "description": "Optional; default 3"},
            },
            "required": ["ticker", "condition_text"],
        },
    },
    {
        "name": "compare_price_to_level",
        "description": "Percent distance from current price to a numeric level; default near = 3%.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "current_price": {"type": "NUMBER"},
                "level": {"type": "NUMBER"},
                "near_pct": {"type": "NUMBER", "description": "Optional; default 3"},
            },
            "required": ["current_price", "level"],
        },
    },
]

_TOOL_HANDLERS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "get_spot_price": lambda args, deps: get_spot_price(args.get("ticker", ""), deps),
    "get_sma": lambda args, deps: get_sma(
        args.get("ticker", ""),
        int(args.get("window", 200)),
        deps,
    ),
    "get_recent_high_low": lambda args, deps: get_recent_high_low(
        args.get("ticker", ""),
        int(args.get("window_days", 20)),
        deps,
    ),
    "get_iv_context": lambda args, deps: get_iv_context(args.get("ticker", ""), deps),
    "get_earnings_context": lambda args, deps: get_earnings_context(args.get("ticker", ""), deps),
    "compare_spot_to_stated_levels": lambda args, deps: compare_spot_to_stated_levels(
        args.get("ticker", ""),
        args.get("condition_text", ""),
        near_pct=float(args.get("near_pct", 3.0)),
        deps=deps,
    ),
    "compare_price_to_level": lambda args, deps: compare_price_to_level(
        float(args["current_price"]),
        float(args["level"]),
        near_pct=float(args.get("near_pct", 3.0)),
    ),
}


def execute_tool(
    name: str,
    args: Dict[str, Any],
    deps: Optional[ExitSignalToolDeps] = None,
) -> Dict[str, Any]:
    """Run a registered tool by name; used by the Gemini agent loop."""
    handler = _TOOL_HANDLERS.get(name)
    if not handler:
        return {"error": f"unknown tool: {name}"}
    deps = deps or ExitSignalToolDeps()
    try:
        return handler(args or {}, deps)
    except Exception as exc:
        logger.exception("tool %s failed: %s", name, exc)
        return {"error": str(exc), "tool": name}
