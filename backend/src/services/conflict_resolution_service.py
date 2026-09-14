"""Persist and generate conflict resolutions across saved verdicts."""
import datetime
import re
from typing import Any, Dict, List, Optional

import pymongo
from bson import ObjectId

from ..analytics.methodologies.gpt_verdict import _openai_chat_completion
from ..my_libs_py3.db import connect_mongo
from .analysis_service import _sanitize_for_json
from .prompt_config_service import get_prompt_text, render_prompt
from .verdict_service import get_verdict_by_id


def _get_collection():
    """Return the Mongo collection for conflict resolutions."""
    conn = connect_mongo('trader_intelligence')
    return conn.db['conflict_resolutions']


def _strip_html(html: Optional[str], max_len: int = 1500) -> str:
    """Convert HTML summary to plain text and truncate."""
    if not html or not isinstance(html, str):
        return ''
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_len:
        return text[:max_len].rstrip() + '...'
    return text


def _summarize_verdict(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact summary of a saved verdict for the LLM prompt."""
    data = doc.get('data') or {}
    gpt_verdict = data.get('gpt_verdict') if isinstance(data.get('gpt_verdict'), dict) else {}

    return {
        'id': doc.get('id'),
        'label': doc.get('label') or '',
        'created_at': doc.get('created_at'),
        'final_bias': doc.get('final_bias') or data.get('final_bias'),
        'analysis_method': doc.get('analysis_method') or data.get('analysis_method'),
        'gpt_model': doc.get('gpt_model') or gpt_verdict.get('model'),
        'expiration_date': doc.get('expiration_date') or data.get('expiration_date'),
        'S_current': data.get('S_current'),
        'rationale': gpt_verdict.get('rationale') or '',
        'summary': _strip_html(data.get('final_conclusion_html')),
        'key_reasoning_points': gpt_verdict.get('key_reasoning_points') or [],
        'risk_factors': gpt_verdict.get('risk_factors') or [],
    }


def _build_messages(ticker: str, summaries: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Build system + user messages for conflict resolution."""
    system = get_prompt_text("conflict_resolution.system")

    blocks = []
    for i, s in enumerate(summaries, start=1):
        key_points = s.get('key_reasoning_points') or []
        risks = s.get('risk_factors') or []
        key_points_text = '\n'.join(f'  - {p}' for p in key_points) or '  (none)'
        risks_text = '\n'.join(f'  - {r}' for r in risks) or '  (none)'
        blocks.append(
            f"### Verdict {i}\n"
            f"- id: {s.get('id')}\n"
            f"- label: {s.get('label') or '(none)'}\n"
            f"- saved_at: {s.get('created_at')}\n"
            f"- bias: {s.get('final_bias')}\n"
            f"- method: {s.get('analysis_method')}\n"
            f"- model: {s.get('gpt_model')}\n"
            f"- expiration: {s.get('expiration_date')}\n"
            f"- spot: {s.get('S_current')}\n"
            f"- rationale:\n{s.get('rationale') or '(none)'}\n"
            f"- summary:\n{s.get('summary') or '(none)'}\n"
            f"- key_reasoning_points:\n{key_points_text}\n"
            f"- risk_factors:\n{risks_text}\n"
        )

    user = render_prompt(
        "conflict_resolution.user",
        ticker=ticker.upper(),
        verdict_blocks="\n".join(blocks),
    )

    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ]


def resolve_conflicts(
    ticker: str,
    verdict_ids: List[str],
    model: str = 'gemini-2.5-flash',
) -> Dict[str, Any]:
    """
    Load saved verdicts, call Gemini to reconcile conflicts, and persist the result.
    """
    normalized_ticker = (ticker or '').upper().strip()
    if not normalized_ticker:
        raise ValueError('ticker is required')

    ids = [str(v).strip() for v in (verdict_ids or []) if str(v).strip()]
    if len(ids) < 2:
        raise ValueError('Need at least 2 saved verdicts to resolve.')

    docs: List[Dict[str, Any]] = []
    for oid in ids:
        doc = get_verdict_by_id(oid)
        if not doc:
            continue
        doc_ticker = (doc.get('ticker') or '').upper()
        if doc_ticker and doc_ticker != normalized_ticker:
            continue
        docs.append(doc)

    if len(docs) < 2:
        raise ValueError('Need at least 2 saved verdicts to resolve.')

    summaries = [_summarize_verdict(d) for d in docs]
    messages = _build_messages(normalized_ticker, summaries)

    parsed, metrics = _openai_chat_completion(
        messages,
        model=model,
        temperature=0.3,
        stage='ConflictResolver',
        llm_provider='gemini',
    )

    if parsed is None:
        raise RuntimeError(
            metrics.error_message or 'Conflict resolver LLM call failed'
        )

    if not isinstance(parsed, dict):
        raise RuntimeError('Conflict resolver returned a non-object response')

    sources = [
        {
            'id': s.get('id'),
            'label': s.get('label') or '',
            'final_bias': s.get('final_bias'),
            'created_at': s.get('created_at'),
            'analysis_method': s.get('analysis_method'),
            'expiration_date': s.get('expiration_date'),
        }
        for s in summaries
    ]

    resolved_model = getattr(metrics, 'model', None) or model
    created_at = datetime.datetime.utcnow()
    doc: Dict[str, Any] = {
        'ticker': normalized_ticker,
        'model': resolved_model,
        'verdict_ids': [s.get('id') for s in summaries],
        'sources': sources,
        'final_bias': parsed.get('final_bias'),
        'confidence_level': parsed.get('confidence_level'),
        'conflict_summary': parsed.get('conflict_summary'),
        'agreement_points': parsed.get('agreement_points') or [],
        'disagreement_points': parsed.get('disagreement_points') or [],
        'summary_html': parsed.get('summary_html'),
        'rationale': parsed.get('rationale'),
        'actionable_ideas': parsed.get('actionable_ideas') or [],
        'risk_factors': parsed.get('risk_factors') or [],
        'resolution': _sanitize_for_json(parsed),
        'created_at': created_at,
    }

    collection = _get_collection()
    result = collection.insert_one(doc)
    doc_id = str(result.inserted_id)

    return {
        'status': 'success',
        'id': doc_id,
        'ticker': normalized_ticker,
        'model': resolved_model,
        'verdict_ids': doc['verdict_ids'],
        'sources': sources,
        'final_bias': doc['final_bias'],
        'confidence_level': doc['confidence_level'],
        'conflict_summary': doc['conflict_summary'],
        'agreement_points': doc['agreement_points'],
        'disagreement_points': doc['disagreement_points'],
        'summary_html': doc['summary_html'],
        'rationale': doc['rationale'],
        'actionable_ideas': doc['actionable_ideas'],
        'risk_factors': doc['risk_factors'],
        'created_at': created_at.isoformat(),
    }


def list_resolutions(ticker: str, page: int = 1, page_size: int = 25) -> Dict[str, Any]:
    """Return a paginated list of conflict resolutions for a ticker."""
    col = _get_collection()
    normalized_ticker = (ticker or '').upper()
    filt = {'ticker': normalized_ticker}

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
        created_at = d.get('created_at')
        sources = d.get('sources') or []
        items.append({
            'id': str(d.get('_id')),
            'ticker': d.get('ticker'),
            'model': d.get('model'),
            'final_bias': d.get('final_bias'),
            'confidence_level': d.get('confidence_level'),
            'conflict_summary': d.get('conflict_summary'),
            'source_count': len(sources),
            'verdict_ids': d.get('verdict_ids') or [],
            'sources': sources,
            'created_at': created_at.isoformat() if isinstance(created_at, datetime.datetime) else created_at,
        })

    return {
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'has_more': (skip + len(items)) < total,
    }


def get_resolution_by_id(oid: str) -> Optional[Dict[str, Any]]:
    """Fetch a full conflict resolution document by ID."""
    col = _get_collection()
    try:
        doc = col.find_one({'_id': ObjectId(oid)})
        if not doc:
            return None
        doc['id'] = str(doc.pop('_id'))
        if isinstance(doc.get('created_at'), datetime.datetime):
            doc['created_at'] = doc['created_at'].isoformat()
        return doc
    except Exception:
        return None
