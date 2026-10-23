import datetime
from typing import Any, Dict, List, Optional

from ..models.order_models import StrategyOrderRequest
from ..my_libs_py3.db import connect_mongo
from .analysis_service import _sanitize_for_json
from .connection_manager import connection_manager
from .strategy_signature import strategy_signature


def _get_collection():
    """Returns the Mongo collection for tracked orders."""
    conn = connect_mongo('trader_intelligence')
    return conn.db['tracked_orders']


def _strategy_signature(ticker: str, expiration_date: str, legs: List[Dict[str, Any]]) -> str:
    # Legacy wrapper kept for backwards compatibility with any older callers.
    return strategy_signature(ticker, expiration_date, legs)


def record_strategy_execution(
    order_request: StrategyOrderRequest,
    trade_info: Dict[str, Any],
    broker_order_id: Optional[Any] = None,
    broker_perm_id: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Persist a record of a one-button executed strategy with attached guidance snapshot.

    - Stores a compact snapshot of GPT insights (if provided) for later lookup.
    - Stores a normalized representation of legs for signature/matching purposes.
    - Returns {'status': 'success', 'id': '<mongo_id>'}
    """
    col = _get_collection()

    # Normalize legs with explicit quantity=1 within strategy ratio
    legs_for_store: List[Dict[str, Any]] = []
    for l in order_request.legs:
        legs_for_store.append({
            'action': l.action.upper(),
            'quantity': 1,
            'strike': float(l.strike),
            'right': l.right.upper(),
        })

    signature = strategy_signature(order_request.ticker, order_request.expiration_date.replace('-', ''), legs_for_store)

    # Keep only essential GPT fields to keep document small
    gpt_snapshot: Optional[Dict[str, Any]] = None
    if order_request.gpt_insights and isinstance(order_request.gpt_insights, dict):
        gi = order_request.gpt_insights
        gpt_snapshot = {
            'final_bias': gi.get('final_bias'),
            'summary_html': gi.get('summary_html'),
            'execution_recommendations': gi.get('execution_recommendations'),
            'rationale': gi.get('rationale'),
            'sources': gi.get('sources'),
            'actionable_ideas': gi.get('actionable_ideas'),
            'risk_factors': gi.get('risk_factors'),
        }

    doc: Dict[str, Any] = {
        'ticker': order_request.ticker.upper(),
        'expiration_date': order_request.expiration_date,  # stored as YYYY-MM-DD (frontend format)
        'size': int(order_request.size),
        'is_credit_spread': bool(order_request.is_credit_spread),
        'legs': legs_for_store,
        'signature': signature,
        'gpt_snapshot': gpt_snapshot,
        'broker_order_id': broker_order_id,
        'broker_perm_id': broker_perm_id,
        'broker_trade': trade_info,
        'placed_at': datetime.datetime.utcnow(),
        'status': trade_info.get('order_status') or trade_info.get('status') or 'submitted',
    }
    if broker_order_id is not None:
        doc['ib_order_id'] = broker_order_id  # legacy field for existing consumers
    if broker_perm_id is not None:
        doc['ib_perm_id'] = broker_perm_id

    clean_doc = _sanitize_for_json(doc)
    result = _get_collection().insert_one(clean_doc)
    return {'status': 'success', 'id': str(result.inserted_id)}


def list_tracked_orders(limit: int = 50) -> List[Dict[str, Any]]:
    """Return compact list of recently tracked one-button strategy executions."""
    col = _get_collection()
    cursor = (
        col.find({}, {
            'ticker': 1,
            'expiration_date': 1,
            'size': 1,
            'is_credit_spread': 1,
            'legs': 1,
            'signature': 1,
            'gpt_snapshot.final_bias': 1,
            'gpt_snapshot.execution_recommendations': 1,
            'gpt_snapshot.actionable_ideas': 1,
            'gpt_snapshot.risk_factors': 1,
            'gpt_snapshot.rationale': 1,
            'placed_at': 1,
            'status': 1
        })
        .sort('placed_at', -1)
        .limit(max(1, min(limit, 200)))
    )
    out: List[Dict[str, Any]] = []
    for d in cursor:
        out.append({
            'id': str(d.get('_id')),
            'ticker': d.get('ticker'),
            'expiration_date': d.get('expiration_date'),
            'size': d.get('size'),
            'is_credit_spread': d.get('is_credit_spread'),
            'legs': d.get('legs', []),
            'signature': d.get('signature'),
            'gpt_guidance': {
                'final_bias': (d.get('gpt_snapshot') or {}).get('final_bias'),
                'execution_recommendations': (d.get('gpt_snapshot') or {}).get('execution_recommendations'),
                'actionable_ideas': (d.get('gpt_snapshot') or {}).get('actionable_ideas'),
                'risk_factors': (d.get('gpt_snapshot') or {}).get('risk_factors'),
                'rationale': (d.get('gpt_snapshot') or {}).get('rationale'),
            },
            'placed_at': d.get('placed_at').isoformat() if d.get('placed_at') else None,
            'status': d.get('status')
        })
    return out


def get_tracked_order(order_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a full tracked order document by its ID."""
    from bson import ObjectId
    col = _get_collection()
    try:
        doc = col.find_one({'_id': ObjectId(order_id)})
        if not doc:
            return None
        doc['id'] = str(doc.pop('_id'))
        if isinstance(doc.get('placed_at'), datetime.datetime):
            doc['placed_at'] = doc['placed_at'].isoformat()
        return doc
    except Exception:
        return None


async def estimate_current_mtm(order_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute an approximate current mark-to-market value for one strategy unit and for the full size.
    Uses current option mid/last price per leg from the broker. This is an approximation and not a P&L.
    Returns {'unit_mtm': float, 'total_mtm': float, 'legs': [{...price...}]}
    """
    try:
        trader = await connection_manager.get_trader()
    except Exception as e:
        return {'unit_mtm': None, 'total_mtm': None, 'legs': [], 'error': f'Broker unavailable: {e}'}

    ticker = order_doc.get('ticker')
    expiry = order_doc.get('expiration_date', '').replace('-', '')
    legs = order_doc.get('legs', [])
    size = int(order_doc.get('size', 1))

    legs_out: List[Dict[str, Any]] = []
    unit_value = 0.0
    for l in legs:
        right = l.get('right')
        strike = float(l.get('strike'))
        qty = int(l.get('quantity', 1))
        action = l.get('action', 'BUY')
        price = await trader.get_current_price(ticker, 'OPT', expiry, strike, right)
        legs_out.append({
            'action': action,
            'quantity': qty,
            'strike': strike,
            'right': right,
            'price': price
        })
        if price is not None:
            contrib = price * qty
            unit_value += contrib if action == 'BUY' else -contrib

    # Assume 100x multiplier for equity options
    unit_mtm = round(unit_value * 100.0, 2) if legs_out else None
    total_mtm = round(unit_mtm * size, 2) if unit_mtm is not None else None
    return {'unit_mtm': unit_mtm, 'total_mtm': total_mtm, 'legs': legs_out}
