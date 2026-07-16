"""Time-series of risk-free rates used in past analyses."""
import datetime
import math
from typing import Any, Dict, List, Optional, Tuple

import pymongo

from ..my_libs_py3.db import connect_mongo
from .risk_free_rate_scheduler_service import (
    MACRO_METRICS_COLLECTION,
    is_us_market_hours_for_timestamp,
)


def _to_float(value: Any) -> Optional[float]:
    try:
        numeric = float(value)
        if not math.isfinite(numeric):
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _extract_rate_from_verdict_data(data: Dict[str, Any]) -> Optional[float]:
    if not isinstance(data, dict):
        return None
    market = data.get('market_data') or {}
    return _to_float(data.get('risk_free_rate')) or _to_float(market.get('risk_free_rate'))


def _day_key(created_at: Any) -> Optional[str]:
    if isinstance(created_at, datetime.datetime):
        return created_at.date().isoformat()
    if isinstance(created_at, str) and created_at:
        return created_at[:10]
    return None


def _parse_created_at(value: Any) -> Optional[datetime.datetime]:
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    return None


def _filter_market_hours_points(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop observations recorded outside US regular market hours."""
    filtered: List[Dict[str, Any]] = []
    for row in points:
        created = _parse_created_at(row.get('created_at'))
        if created is None:
            continue
        if is_us_market_hours_for_timestamp(created):
            filtered.append(row)
    return filtered


def _dedupe_latest_per_day(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only the latest observation for each calendar day."""
    by_day: Dict[str, Dict[str, Any]] = {}
    for row in points:
        day = _day_key(row.get('created_at'))
        if not day:
            continue
        existing = by_day.get(day)
        if existing is None or (row.get('created_at') or '') > (existing.get('created_at') or ''):
            by_day[day] = row
    return sorted(by_day.values(), key=lambda item: item.get('created_at') or '')


def list_risk_free_rate_history(
    ticker: str = '',
    limit: int = 200,
    days: int = 365,
) -> Dict[str, Any]:
    """
    Return ascending time-series points of risk-free rates used in analyses.

    Primary source: analysis_history (one row per completed run).
    Supplement: verdicts with explicit risk_free_rate (manual saves).
    """
    conn = connect_mongo('trader_intelligence')
    history_col = conn.db['analysis_history']
    verdict_col = conn.db['verdicts']
    metrics_col = conn.db[MACRO_METRICS_COLLECTION]

    try:
        limit = max(1, min(int(limit), 1000))
    except (TypeError, ValueError):
        limit = 200
    try:
        days = max(1, min(int(days), 3650))
    except (TypeError, ValueError):
        days = 365

    since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    normalized_ticker = (ticker or '').strip().upper()

    history_query: Dict[str, Any] = {
        'created_at': {'$gte': since},
        'risk_free_rate': {'$ne': None},
    }
    if normalized_ticker:
        history_query['ticker'] = normalized_ticker

    points: List[Dict[str, Any]] = []
    seen_keys = set()

    cursor = (
        history_col.find(history_query, {
            'created_at': 1,
            'risk_free_rate': 1,
            'ticker': 1,
            'analysis_method': 1,
        })
        .sort('created_at', pymongo.ASCENDING)
        .limit(limit)
    )
    for doc in cursor:
        rate = _to_float(doc.get('risk_free_rate'))
        created = doc.get('created_at')
        if rate is None or not isinstance(created, datetime.datetime):
            continue
        key = (created.replace(microsecond=0).isoformat(), doc.get('ticker'), rate)
        seen_keys.add(key)
        points.append({
            'created_at': created.isoformat(),
            'risk_free_rate': rate,
            'ticker': doc.get('ticker'),
            'analysis_method': doc.get('analysis_method'),
            'source': 'analysis_run',
        })

    verdict_query: Dict[str, Any] = {
        'created_at': {'$gte': since},
    }
    if normalized_ticker:
        verdict_query['ticker'] = normalized_ticker

    verdict_cursor = (
        verdict_col.find(verdict_query, {
            'created_at': 1,
            'risk_free_rate': 1,
            'ticker': 1,
            'analysis_method': 1,
            'data': 1,
        })
        .sort('created_at', pymongo.ASCENDING)
        .limit(limit)
    )
    for doc in verdict_cursor:
        rate = _to_float(doc.get('risk_free_rate')) or _extract_rate_from_verdict_data(doc.get('data') or {})
        created = doc.get('created_at')
        if rate is None or not isinstance(created, datetime.datetime):
            continue
        key = (created.replace(microsecond=0).isoformat(), doc.get('ticker'), rate)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        points.append({
            'created_at': created.isoformat(),
            'risk_free_rate': rate,
            'ticker': doc.get('ticker'),
            'analysis_method': doc.get('analysis_method'),
            'source': 'verdict_save',
        })

    if not normalized_ticker:
        metrics_query: Dict[str, Any] = {'created_at': {'$gte': since}}
        metrics_cursor = (
            metrics_col.find(metrics_query, {
                'created_at': 1,
                'risk_free_rate': 1,
                'as_of': 1,
                'tickers': 1,
                'source': 1,
            })
            .sort('created_at', pymongo.ASCENDING)
            .limit(limit)
        )
        for doc in metrics_cursor:
            rate = _to_float(doc.get('risk_free_rate'))
            created = doc.get('created_at')
            if rate is None or not isinstance(created, datetime.datetime):
                continue
            key: Tuple[str, Any, float] = (created.replace(microsecond=0).isoformat(), None, rate)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            points.append({
                'created_at': created.isoformat(),
                'risk_free_rate': rate,
                'ticker': None,
                'analysis_method': 'daily_calculation',
                'source': doc.get('source') or 'daily_calculation',
                'as_of': doc.get('as_of'),
            })

    points = _filter_market_hours_points(points)
    points = _dedupe_latest_per_day(points)
    if len(points) > limit:
        points = points[-limit:]

    return {
        'status': 'success',
        'items': points,
        'total': len(points),
        'ticker_filter': normalized_ticker or None,
        'days': days,
    }
