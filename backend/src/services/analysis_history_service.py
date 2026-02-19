"""Persistence helpers for analysis run history."""
import datetime
from typing import Any, Dict, List, Optional

import pymongo
from bson import ObjectId

from ..my_libs_py3.db import connect_mongo
from .analysis_service import _sanitize_for_json


def _get_collection():
    """Return the Mongo collection used for persisting analysis history."""
    conn = connect_mongo('trader_intelligence')
    return conn.db['analysis_history']


def _normalize_expiration(expiration_value: Optional[Any]) -> Dict[str, Optional[str]]:
    """Return raw and ISO formatted expiration representations when possible."""
    if expiration_value is None:
        return {'raw': None, 'iso': None}

    raw = str(expiration_value)
    # Remove non-digit separators for parsing while keeping the original representation
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if len(digits) != 8:
        return {'raw': raw, 'iso': None}

    try:
        dt = datetime.datetime.strptime(digits, '%Y%m%d').date()
        return {'raw': raw, 'iso': dt.isoformat()}
    except ValueError:
        return {'raw': raw, 'iso': None}


def save_analysis_record(request_payload: Dict[str, Any], analysis_result: Any) -> Dict[str, Any]:
    """Persist a completed analysis run along with its full verdict content."""
    collection = _get_collection()

    sanitized_request = _sanitize_for_json(request_payload) if request_payload else {}
    sanitized_result = _sanitize_for_json(analysis_result) if analysis_result is not None else None

    primary_verdict = None
    if isinstance(sanitized_result, list):
        primary_verdict = sanitized_result[0] if sanitized_result else None
    else:
        primary_verdict = sanitized_result

    expiration_info = _normalize_expiration(sanitized_request.get('expiration_date'))

    doc: Dict[str, Any] = {
        'ticker': (sanitized_request.get('ticker') or '').upper() if sanitized_request else None,
        'analysis_method': sanitized_request.get('analysis_method'),
        'gpt_model': sanitized_request.get('gpt_model'),
        'risk_free_rate': sanitized_request.get('risk_free_rate'),
        'override_price': sanitized_request.get('override_price'),
        'expiration_date': expiration_info['iso'] or sanitized_request.get('expiration_date'),
        'expiration_date_raw': expiration_info['raw'],
        'request_payload': sanitized_request,
        'analysis_result': sanitized_result,
        'primary_verdict': primary_verdict,
        'final_bias': primary_verdict.get('final_bias') if isinstance(primary_verdict, dict) else None,
        'created_at': datetime.datetime.utcnow(),
    }

    result = collection.insert_one(doc)
    return {'status': 'success', 'id': str(result.inserted_id)}


def list_history(ticker: str, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
    """Return paginated history entries for a ticker."""
    collection = _get_collection()
    normalized_ticker = (ticker or '').upper()

    try:
        page = int(page)
    except Exception:
        page = 1
    try:
        page_size = int(page_size)
    except Exception:
        page_size = 20

    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    skip = (page - 1) * page_size

    query = {'ticker': normalized_ticker} if normalized_ticker else {}

    total = collection.count_documents(query)
    cursor = (
        collection.find(query)
        .sort('created_at', pymongo.DESCENDING)
        .skip(skip)
        .limit(page_size)
    )

    items: List[Dict[str, Any]] = []
    for doc in cursor:
        created_at = doc.get('created_at')
        items.append({
            'id': str(doc.get('_id')),
            'ticker': doc.get('ticker'),
            'analysis_method': doc.get('analysis_method'),
            'gpt_model': doc.get('gpt_model'),
            'risk_free_rate': doc.get('risk_free_rate'),
            'override_price': doc.get('override_price'),
            'expiration_date': doc.get('expiration_date'),
            'expiration_date_raw': doc.get('expiration_date_raw'),
            'final_bias': doc.get('final_bias'),
            'created_at': created_at.isoformat() if isinstance(created_at, datetime.datetime) else None,
            'request_payload': doc.get('request_payload'),
            'analysis_result': doc.get('analysis_result'),
            'primary_verdict': doc.get('primary_verdict'),
        })

    return {
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'has_more': (skip + len(items)) < total,
    }


def delete_history_entry(entry_id: str) -> bool:
    """Delete a single history entry by ObjectId."""
    collection = _get_collection()
    try:
        result = collection.delete_one({'_id': ObjectId(entry_id)})
        return result.deleted_count > 0
    except Exception:
        return False


def clear_history_for_ticker(ticker: str) -> int:
    """Remove all history entries for a ticker. Returns the number of deleted docs."""
    collection = _get_collection()
    normalized_ticker = (ticker or '').upper()
    result = collection.delete_many({'ticker': normalized_ticker})
    return result.deleted_count
