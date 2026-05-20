import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
import pymongo

from ..my_libs_py3.db import connect_mongo
from .analysis_service import _sanitize_for_json


def _get_collection():
    """
    Returns the Mongo collection for saved verdicts.
    Uses database 'trader_intelligence' and collection 'verdicts'.
    """
    conn = connect_mongo('trader_intelligence')
    return conn.db['verdicts']


def save_verdict_document(verdict: Dict[str, Any], label: Optional[str] = None) -> Dict[str, Any]:
    """
    Persist a verdict snapshot for later retrieval/compare.

    Expects a single analysis result object (the item inside the list returned by /analysis/stock).
    """
    col = _get_collection()

    # Sanitize nested data to be JSON-safe
    clean = _sanitize_for_json(verdict)

    # Build a compact overview for list displays (verdict history)
    analysis_method = clean.get('analysis_method')
    gpt_model = clean.get('gpt_verdict', {}).get('model') if isinstance(clean.get('gpt_verdict'), dict) else None
    iv_state = 'high' if clean.get('iv_high') else ('low' if clean.get('iv_low') else 'normal')
    if isinstance(analysis_method, str):
        if ('gpt' in analysis_method) and ('web' in analysis_method):
            method_label = 'Web Verdict'
        elif 'gpt' in analysis_method:
            method_label = 'GPT Verdict'
        else:
            method_label = 'Model Verdict'
    else:
        method_label = 'Model Verdict'

    overview: Dict[str, Any] = {
        'ticker': clean.get('ticker'),
        'expiration_date': clean.get('expiration_date'),
        'dte': clean.get('dte'),
        'final_bias': clean.get('final_bias'),
        'analysis_method': analysis_method,
        'gpt_model': gpt_model,
        'S_current': clean.get('S_current'),
        'iv_state': iv_state,
        'method_label': method_label,
    }

    doc: Dict[str, Any] = {
        'ticker': clean.get('ticker'),
        'expiration_date': clean.get('expiration_date'),
        'analysis_method': analysis_method,
        'gpt_model': gpt_model,
        'final_bias': clean.get('final_bias'),
        'created_at': datetime.datetime.utcnow(),
        'label': label or '',
        'overview': overview,
        'data': clean,
    }

    result = col.insert_one(doc)
    return {
        'status': 'success',
        'id': str(result.inserted_id),
    }


def list_verdicts(ticker: str, page: int = 1, page_size: int = 25) -> Dict[str, Any]:
    """Return a paginated list of saved verdicts for a ticker with compact overview."""
    col = _get_collection()
    filt = {'ticker': ticker}

    # Sanitize pagination inputs
    try:
        page = int(page)
    except Exception:
        page = 1
    try:
        page_size = int(page_size)
    except Exception:
        page_size = 25
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    skip = (page - 1) * page_size

    total = col.count_documents(filt)
    cursor = (
        col.find(filt)
        .sort('created_at', pymongo.DESCENDING)
        .skip(skip)
        .limit(page_size)
    )
    items: List[Dict[str, Any]] = []
    for d in cursor:
        # Ensure we have an overview for each row (fallback to infer from data if needed)
        data = d.get('data') or {}
        analysis_method = d.get('analysis_method') or data.get('analysis_method')
        if isinstance(analysis_method, str):
            if ('gpt' in analysis_method) and ('web' in analysis_method):
                method_label = 'Web Verdict'
            elif 'gpt' in analysis_method:
                method_label = 'GPT Verdict'
            else:
                method_label = 'Model Verdict'
        else:
            method_label = 'Model Verdict'
        iv_state = 'high' if (data.get('iv_high')) else ('low' if (data.get('iv_low')) else 'normal')
        overview = d.get('overview') or {
            'ticker': d.get('ticker'),
            'expiration_date': d.get('expiration_date'),
            'dte': data.get('dte'),
            'final_bias': d.get('final_bias'),
            'analysis_method': analysis_method,
            'gpt_model': d.get('gpt_model') or (data.get('gpt_verdict', {}) or {}).get('model'),
            'S_current': data.get('S_current'),
            'iv_state': iv_state,
            'method_label': method_label,
        }
        items.append({
            'id': str(d.get('_id')),
            'ticker': d.get('ticker'),
            'expiration_date': d.get('expiration_date'),
            'final_bias': d.get('final_bias'),
            'label': d.get('label', ''),
            'analysis_method': d.get('analysis_method'),
            'gpt_model': d.get('gpt_model'),
            'created_at': d.get('created_at').isoformat() if d.get('created_at') else None,
            'overview': overview,
        })

    return {
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'has_more': (skip + len(items)) < total,
    }


def get_verdict_by_id(oid: str) -> Optional[Dict[str, Any]]:
    """Fetch a full saved verdict document by its ID."""
    col = _get_collection()
    try:
        doc = col.find_one({'_id': ObjectId(oid)})
        if not doc:
            return None
        # Convert _id and datetime
        doc['id'] = str(doc.pop('_id'))
        if isinstance(doc.get('created_at'), datetime.datetime):
            doc['created_at'] = doc['created_at'].isoformat()
        return doc
    except Exception:
        return None


def get_latest_verdict_for(ticker: str, expiration_date: str) -> Optional[Dict[str, Any]]:
    """
    Fetch the most recent saved verdict for a given ticker and expiration date (YYYY-MM-DD).
    Returns the full document including the 'data' payload if found, else None.
    """
    col = _get_collection()
    try:
        doc = (
            col.find({'ticker': ticker.upper(), 'expiration_date': expiration_date})
            .sort('created_at', pymongo.DESCENDING)
            .limit(1)
        )
        docs = list(doc)
        if not docs:
            return None
        d = docs[0]
        d['id'] = str(d.pop('_id'))
        if isinstance(d.get('created_at'), datetime.datetime):
            d['created_at'] = d['created_at'].isoformat()
        return d
    except Exception:
        return None
