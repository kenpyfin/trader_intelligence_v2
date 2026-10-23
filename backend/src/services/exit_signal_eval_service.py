"""
Mongo cache and refresh orchestration for agentic exit-signal evaluations.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from src.analytics.exit_signal_agent import (
    DEFAULT_GEMINI_MODEL,
    evaluate_exit_conditions_with_agent,
)
from src.analytics.exit_signal_tools import AGENT_VERSION, ExitSignalToolDeps
from src.analytics.execution_signal_evaluator import (
    _evaluate_single_condition,
    aggregate_exit_timing,
)
from src.my_libs_py3.db import connect_mongo

logger = logging.getLogger(__name__)

COLLECTION = "exit_signal_evaluations"
TTL_MINUTES = int(os.getenv("EXIT_SIGNAL_EVAL_TTL_MINUTES", "20"))
_refresh_lock = threading.Lock()
_refresh_in_flight: Set[str] = set()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _conditions_hash(conditions: List[str]) -> str:
    normalized = "\n".join(sorted((c or "").strip().lower() for c in conditions if (c or "").strip()))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _cache_key(signature: str, conditions: List[str]) -> str:
    return f"{signature}:{_conditions_hash(conditions)}"


def _collection():
    conn = connect_mongo("trader_intelligence", COLLECTION)
    return conn.table


def get_cached_evaluation(
    signature: str,
    conditions: List[str],
) -> Optional[Dict[str, Any]]:
    """Return cached document if present and within TTL."""
    if not signature or not conditions:
        return None
    key = _cache_key(signature, conditions)
    try:
        doc = _collection().find_one({"cache_key": key})
    except Exception as exc:
        logger.warning("exit eval cache read failed: %s", exc)
        return None
    if not doc:
        return None

    evaluated_at = doc.get("evaluated_at")
    if not evaluated_at:
        return None

    try:
        if isinstance(evaluated_at, str):
            ts = datetime.fromisoformat(evaluated_at.replace("Z", "+00:00"))
        else:
            ts = evaluated_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_min = (_utc_now() - ts).total_seconds() / 60.0
        if age_min > TTL_MINUTES:
            doc["_stale"] = True
        else:
            doc["_stale"] = False
    except Exception:
        doc["_stale"] = True

    return doc


def upsert_evaluation(
    *,
    signature: str,
    symbol: str,
    conditions: List[str],
    evaluations: List[Dict[str, Any]],
    aggregate_status: str,
    model: str = DEFAULT_GEMINI_MODEL,
) -> None:
    key = _cache_key(signature, conditions)
    now = _utc_now().isoformat()
    doc = {
        "cache_key": key,
        "strategy_signature": signature,
        "symbol": symbol,
        "conditions": conditions,
        "evaluations": evaluations,
        "aggregate_status": aggregate_status,
        "evaluated_at": now,
        "model": model,
        "agent_version": AGENT_VERSION,
    }
    try:
        _collection().update_one({"cache_key": key}, {"$set": doc}, upsert=True)
    except Exception as exc:
        logger.warning("exit eval cache write failed: %s", exc)


def merge_regex_and_agent_evaluations(
    conditions: List[str],
    context: Dict[str, Any],
    agent_evaluations: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """
    Hybrid: use regex when it returns met/unmet; otherwise use agent cache row by text match.
    """
    agent_by_text = {}
    for ev in agent_evaluations or []:
        key = (ev.get("text") or "").strip().lower()
        if key:
            agent_by_text[key] = ev

    merged: List[Dict[str, Any]] = []
    for text in conditions:
        if not isinstance(text, str) or not text.strip():
            continue
        regex_ev = _evaluate_single_condition(text, context, mode="exit")
        if regex_ev.get("status") in ("met", "unmet"):
            regex_ev["evaluator"] = "regex"
            merged.append(regex_ev)
            continue

        agent_ev = agent_by_text.get(text.strip().lower())
        if agent_ev:
            merged.append(dict(agent_ev))
        else:
            merged.append(regex_ev)
    return merged


def evaluations_for_conditions(
    conditions: List[str],
    cached_evaluations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Map cached per-condition evals onto the current condition list (no regex re-run)."""
    by_text = {
        (e.get("text") or "").strip().lower(): e
        for e in (cached_evaluations or [])
        if (e.get("text") or "").strip()
    }
    aligned: List[Dict[str, Any]] = []
    for text in conditions:
        if not isinstance(text, str) or not text.strip():
            continue
        key = text.strip().lower()
        if key in by_text:
            aligned.append(dict(by_text[key]))
        else:
            aligned.append(
                {
                    "text": text,
                    "status": "unknown",
                    "reason": "No cached evaluation for this condition.",
                    "evaluator": "cache",
                }
            )
    return aligned


def timing_from_cached_evaluations(
    conditions: List[str],
    cached_evaluations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggregate exit timing directly from cached evaluations."""
    evals = evaluations_for_conditions(conditions, cached_evaluations)
    return aggregate_exit_timing(evals)


def evaluate_and_cache_strategy(
    *,
    signature: str,
    symbol: str,
    conditions: List[str],
    context: Optional[Dict[str, Any]] = None,
    model: str = DEFAULT_GEMINI_MODEL,
    deps: Optional[ExitSignalToolDeps] = None,
) -> Dict[str, Any]:
    """Run agent-only evaluation for all conditions, aggregate, persist cache."""
    from src.analytics.exit_signal_agent import pending_agent_evaluations

    texts = [c for c in (conditions or []) if isinstance(c, str) and c.strip()]
    ctx = dict(context or {})

    if symbol and deps and symbol in deps.spot_overrides:
        ctx["underlying_price"] = deps.spot_overrides[symbol]
        ctx["current_price"] = deps.spot_overrides[symbol]

    agent_evals = evaluate_exit_conditions_with_agent(
        ticker=symbol,
        conditions=texts,
        model=model,
        deps=deps,
        portfolio_context=ctx,
    )
    if not agent_evals and texts:
        agent_evals = pending_agent_evaluations(texts)

    timing = aggregate_exit_timing(agent_evals)

    upsert_evaluation(
        signature=signature,
        symbol=symbol,
        conditions=texts,
        evaluations=agent_evals,
        aggregate_status=timing.get("status", "review"),
        model=model,
    )
    timing["evaluated_at"] = _utc_now().isoformat()
    timing["evaluation_source"] = "agent_cache"
    return timing


def collect_open_strategy_jobs(
    grouped_positions: Dict[str, Any],
    tracked_orders: List[Dict[str, Any]],
    underlying_spot_prices: Dict[str, Optional[float]],
) -> List[Dict[str, Any]]:
    """
    Build refresh jobs from open option positions + tracked order guidance.
    Mirrors portfolio_service matching logic (simplified).
    """
    from collections import defaultdict
    from datetime import date, datetime

    from .strategy_signature import strategy_signature

    def _gcd_many(nums):
        import math

        cleaned = [abs(int(n)) for n in (nums or []) if n is not None]
        cleaned = [n for n in cleaned if n > 0]
        if not cleaned:
            return 1
        g = cleaned[0]
        for n in cleaned[1:]:
            g = math.gcd(g, n)
            if g == 1:
                break
        return g or 1

    def _build_open_signature_symbol_legs(legs):
        active_legs = [l for l in (legs or []) if l.get("position") is not None and float(l.get("position")) != 0.0]
        if not active_legs:
            return None
        qtys = [abs(int(float(l.get("position")))) for l in active_legs]
        g = _gcd_many(qtys)
        expiries = [l.get("expiry") for l in active_legs if l.get("expiry")]
        if not expiries:
            return None
        counts = defaultdict(int)
        for e in expiries:
            counts[str(e)] += 1
        chosen_exp = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[0][0]
        norm_legs = []
        for l in active_legs:
            pos = float(l.get("position"))
            action = "BUY" if pos > 0 else "SELL"
            qty_ratio = abs(int(pos)) // g
            try:
                strike = float(l.get("strike"))
            except Exception:
                strike = None
            right = str(l.get("right", "")).upper()[:1]
            if strike is None:
                continue
            norm_legs.append(
                {
                    "action": action,
                    "quantity": int(qty_ratio),
                    "strike": strike,
                    "right": right,
                }
            )
        if not norm_legs:
            return None
        exp_flat = str(chosen_exp).replace("-", "")
        return {"expiration_date": exp_flat, "legs": norm_legs}

    jobs: List[Dict[str, Any]] = []
    option_positions = grouped_positions.get("options") or {}
    for sym, legs in option_positions.items():
        sig_parts = _build_open_signature_symbol_legs(legs)
        if not sig_parts:
            continue
        sig = strategy_signature(sym, sig_parts["expiration_date"], sig_parts["legs"])
        matches = [o for o in tracked_orders if o.get("signature") == sig]
        if not matches:
            continue
        matches_sorted = sorted(matches, key=lambda o: (o.get("placed_at") or ""))
        matched = matches_sorted[0]
        gpt_guidance = matched.get("gpt_guidance") or {}
        recs = gpt_guidance.get("execution_recommendations") or {}
        exit_conditions = recs.get("exit_conditions") or []
        conditions_for_eval = list(exit_conditions) if isinstance(exit_conditions, list) else []
        if not conditions_for_eval:
            if isinstance(recs.get("stop_loss_guidance"), str):
                conditions_for_eval.append(recs.get("stop_loss_guidance"))
            if isinstance(recs.get("profit_target_guidance"), str):
                conditions_for_eval.append(recs.get("profit_target_guidance"))
        if not conditions_for_eval:
            continue

        underlying_price = underlying_spot_prices.get(sym) if underlying_spot_prices else None
        jobs.append(
            {
                "signature": sig,
                "symbol": sym,
                "conditions": conditions_for_eval,
                "underlying_price": underlying_price,
            }
        )
    return jobs


def refresh_jobs_sync(jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run agent evaluation + cache upsert for a list of strategy jobs (sync)."""
    from src.analytics.execution_signal_evaluator import build_exit_context_from_portfolio

    with _refresh_lock:
        to_run = []
        for job in jobs:
            sig = job.get("signature")
            if not sig or sig in _refresh_in_flight:
                continue
            _refresh_in_flight.add(sig)
            to_run.append(job)

    if not to_run:
        logger.debug("exit eval refresh skipped; all signatures already in flight")
        return {
            "refreshed": 0,
            "errors": [],
            "results": [],
            "skipped_in_flight": len(jobs or []),
            "evaluated_at": _utc_now().isoformat(),
        }

    deps = ExitSignalToolDeps()
    for job in to_run:
        sym = job.get("symbol")
        if sym and job.get("underlying_price") is not None:
            deps.spot_overrides[str(sym)] = float(job["underlying_price"])

    results = []
    errors = []
    try:
        for job in to_run:
            try:
                ctx = build_exit_context_from_portfolio(
                    symbol=job["symbol"],
                    legs=job.get("legs") or [],
                    underlying_price=job.get("underlying_price"),
                    aggregate_unrealized_pnl=job.get("aggregate_unrealized_pnl"),
                    aggregate_market_value=job.get("aggregate_market_value"),
                    dte=job.get("dte"),
                    days_to_earnings=None,
                    strategy_is_credit_spread=job.get("strategy_is_credit_spread"),
                    initial_credit_received=job.get("initial_credit_received"),
                )
                timing = evaluate_and_cache_strategy(
                    signature=job["signature"],
                    symbol=job["symbol"],
                    conditions=job["conditions"],
                    context=ctx,
                    deps=deps,
                )
                agent_count = sum(
                    1
                    for e in (timing.get("conditions") or [])
                    if e.get("evaluator") == "agent"
                )
                results.append(
                    {
                        "symbol": job["symbol"],
                        "signature": job["signature"],
                        "status": timing.get("status"),
                        "agent_conditions": agent_count,
                    }
                )
            except Exception as exc:
                logger.exception("refresh failed for %s: %s", job.get("symbol"), exc)
                errors.append({"symbol": job.get("symbol"), "error": str(exc)})
    finally:
        with _refresh_lock:
            for job in to_run:
                sig = job.get("signature")
                if sig:
                    _refresh_in_flight.discard(sig)

    return {
        "refreshed": len(results),
        "errors": errors,
        "results": results,
        "evaluated_at": _utc_now().isoformat(),
    }


async def refresh_all_open_exit_evaluations() -> Dict[str, Any]:
    """Refresh agent cache for all open tracked strategies."""
    from . import portfolio_service

    grouped = await portfolio_service.get_grouped_open_positions()
    positions = grouped.get("positions") or {}
    underlying_spot = grouped.get("underlying_spot_prices") or {}
    from .order_tracking_service import list_tracked_orders

    tracked = list_tracked_orders(limit=120)
    jobs = collect_open_strategy_jobs(positions, tracked, underlying_spot)
    import asyncio

    return await asyncio.to_thread(refresh_jobs_sync, jobs)
