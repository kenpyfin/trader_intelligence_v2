"""
Group broker stock positions into pair-trade cards using Mongo `pair_trade_log`.

Validation is read-only: compare log outstanding sizes to broker quantities.
Does not mutate pair logs or call Habitica.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from ..my_libs_py3.db import connect_mongo

QTY_MATCH_TOLERANCE = 1e-4
OPEN_SIZE_EPS = 1e-6


def parse_pair_collection_name(name: str) -> Optional[Tuple[str, str]]:
    """Require exactly one underscore: TICKER1_TICKER2."""
    if not name or not isinstance(name, str):
        return None
    parts = name.split("_")
    if len(parts) != 2:
        return None
    t1, t2 = parts[0].strip().upper(), parts[1].strip().upper()
    if not t1 or not t2:
        return None
    return t1, t2


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _serialize_timestamp(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _is_open_pair(size1: float, size2: float) -> bool:
    return abs(size1) > OPEN_SIZE_EPS or abs(size2) > OPEN_SIZE_EPS


def _qty_match(log_qty: float, broker_qty: float) -> bool:
    return abs(log_qty - broker_qty) <= QTY_MATCH_TOLERANCE


def load_open_pair_logs_for_symbols(symbols: Set[str]) -> List[Dict[str, Any]]:
    """
    Load open pair logs whose tickers intersect `symbols`.

    Open = abs(sum(size1)) > eps OR abs(sum(size2)) > eps.
    """
    symbols_upper = {str(s).strip().upper() for s in (symbols or set()) if s}
    if not symbols_upper:
        return []

    conn = connect_mongo("pair_trade_log")
    collection_names = list(conn.db.list_collection_names())
    results: List[Dict[str, Any]] = []

    for name in collection_names:
        parsed = parse_pair_collection_name(name)
        if not parsed:
            continue
        ticker1, ticker2 = parsed
        if ticker1 not in symbols_upper and ticker2 not in symbols_upper:
            continue

        coll = conn.db[name]
        agg = list(
            coll.aggregate(
                [
                    {
                        "$group": {
                            "_id": None,
                            "size1": {"$sum": "$size1"},
                            "size2": {"$sum": "$size2"},
                            "last_trade_at": {"$max": "$TimeStamp"},
                        }
                    }
                ]
            )
        )
        if not agg:
            continue

        row = agg[0]
        size1 = _to_float(row.get("size1"))
        size2 = _to_float(row.get("size2"))
        if not _is_open_pair(size1, size2):
            continue

        results.append(
            {
                "pair_id": f"{ticker1}_{ticker2}",
                "ticker1": ticker1,
                "ticker2": ticker2,
                "size1": size1,
                "size2": size2,
                "last_trade_at": _serialize_timestamp(row.get("last_trade_at")),
            }
        )

    return results


def _build_leg(
    symbol: str,
    role: str,
    log_outstanding: float,
    stock_by_symbol: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    position = stock_by_symbol.get(symbol)
    present = position is not None
    broker_qty = _to_float(position.get("position")) if present else 0.0
    match = present and _qty_match(log_outstanding, broker_qty)
    return {
        "symbol": symbol,
        "role": role,
        "log_outstanding": log_outstanding,
        "broker_qty": broker_qty if present else None,
        "qty_match": match,
        "present_at_broker": present,
        "position": position,
    }


def _pair_status(legs: List[Dict[str, Any]]) -> str:
    present_count = sum(1 for leg in legs if leg.get("present_at_broker"))
    if present_count == 1:
        return "missing_leg"
    if present_count == 2 and all(leg.get("qty_match") for leg in legs):
        return "matched"
    return "size_mismatch"


def _combined_unrealized_pnl(legs: List[Dict[str, Any]]) -> Optional[float]:
    total = 0.0
    found = False
    for leg in legs:
        pos = leg.get("position") or {}
        for key in ("unrealizedPNL", "unrealizedPnl", "unrealized_pnl", "unrealizedPnL"):
            if key in pos and pos[key] is not None:
                try:
                    total += float(pos[key])
                    found = True
                    break
                except (TypeError, ValueError):
                    continue
    return total if found else None


def group_stock_pairs(
    stocks: List[Dict[str, Any]],
    open_pair_logs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Group broker stocks into pair cards + dangling leftovers.

    If `open_pair_logs` is None, loads from Mongo for symbols present in `stocks`.
    """
    stocks = list(stocks or [])
    stock_by_symbol: Dict[str, Dict[str, Any]] = {}
    for stock in stocks:
        sym = str(stock.get("symbol") or "").strip().upper()
        if not sym:
            continue
        # Keep first occurrence if duplicates appear
        if sym not in stock_by_symbol:
            normalized = dict(stock)
            normalized["symbol"] = sym
            stock_by_symbol[sym] = normalized

    if open_pair_logs is None:
        open_pair_logs = load_open_pair_logs_for_symbols(set(stock_by_symbol.keys()))

    # Overlap index: symbol -> list of pair_ids that include it
    symbol_to_pairs: Dict[str, List[str]] = {}
    for log in open_pair_logs or []:
        pair_id = log.get("pair_id") or f"{log.get('ticker1')}_{log.get('ticker2')}"
        for key in ("ticker1", "ticker2"):
            sym = str(log.get(key) or "").strip().upper()
            if not sym:
                continue
            symbol_to_pairs.setdefault(sym, []).append(pair_id)

    pairs: List[Dict[str, Any]] = []
    paired_symbols: Set[str] = set()

    for log in open_pair_logs or []:
        ticker1 = str(log.get("ticker1") or "").strip().upper()
        ticker2 = str(log.get("ticker2") or "").strip().upper()
        if not ticker1 or not ticker2:
            continue

        size1 = _to_float(log.get("size1"))
        size2 = _to_float(log.get("size2"))
        legs = [
            _build_leg(ticker1, "ticker1", size1, stock_by_symbol),
            _build_leg(ticker2, "ticker2", size2, stock_by_symbol),
        ]

        # Omit pairs with neither leg at the broker
        if not any(leg.get("present_at_broker") for leg in legs):
            continue

        pair_id = log.get("pair_id") or f"{ticker1}_{ticker2}"
        overlapping: Set[str] = set()
        for sym in (ticker1, ticker2):
            for other_id in symbol_to_pairs.get(sym, []):
                if other_id != pair_id:
                    overlapping.add(other_id)

        for leg in legs:
            if leg.get("present_at_broker"):
                paired_symbols.add(leg["symbol"])

        pairs.append(
            {
                "pair_id": pair_id,
                "ticker1": ticker1,
                "ticker2": ticker2,
                "status": _pair_status(legs),
                "last_trade_at": log.get("last_trade_at"),
                "combined_unrealized_pnl": _combined_unrealized_pnl(legs),
                "overlapping_pairs": sorted(overlapping),
                "legs": legs,
            }
        )

    dangling = [
        stock_by_symbol[sym]
        for sym in stock_by_symbol
        if sym not in paired_symbols
    ]

    return {"pairs": pairs, "dangling": dangling}
