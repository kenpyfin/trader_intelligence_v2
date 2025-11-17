"""Utility script to fetch and display option chain snapshots from Alpaca."""

import asyncio
from typing import Dict, List, Sequence

from backend.src.my_libs_py3.TD_Order import (
    AlpacaTrader,
    _extract_expiration_list,
    _looks_like_occ,
    _parse_occ_symbol,
)


def _coerce_mapping(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump") and callable(value.model_dump):
        try:
            return value.model_dump()
        except Exception:
            pass
    if hasattr(value, "dict") and callable(value.dict):
        try:
            return value.dict()
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return {k: getattr(value, k) for k in dir(value) if not k.startswith("_") and not callable(getattr(value, k))}
        except Exception:
            pass
    return None


def _snapshot_rows(chain: Dict[str, Dict[str, object]]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for key, raw_payload in (chain or {}).items():
        payload = _coerce_mapping(raw_payload)
        if payload is None:
            continue
        occ_symbol = payload.get("symbol") if isinstance(payload.get("symbol"), str) else key
        if not isinstance(occ_symbol, str) or not _looks_like_occ(occ_symbol):
            continue
        details = _parse_occ_symbol(occ_symbol)
        latest_quote = _coerce_mapping(payload.get("latest_quote")) or {}
        latest_trade = _coerce_mapping(payload.get("latest_trade")) or {}
        rows.append(
            {
                "symbol": occ_symbol,
                "expiry": details.get("expiry"),
                "right": details.get("right"),
                "strike": details.get("strike"),
                "bid": latest_quote.get("bid_price"),
                "ask": latest_quote.get("ask_price"),
                "bid_size": latest_quote.get("bid_size"),
                "ask_size": latest_quote.get("ask_size"),
                "last": latest_trade.get("price"),
                "timestamp": latest_quote.get("timestamp") or latest_trade.get("timestamp"),
            }
        )
    rows.sort(key=lambda row: (row.get("expiry"), row.get("strike"), row.get("right")))
    return rows


async def fetch_option_chain(symbol: str) -> Dict[str, Sequence[Dict[str, object]]]:
    """Fetch the Alpaca option chain snapshots and return expirations plus quotes."""
    trader = AlpacaTrader()
    await trader.connect()
    chain = await trader.client.get_option_chain(symbol)
    expirations = sorted(_extract_expiration_list(chain))
    rows = _snapshot_rows(chain if isinstance(chain, dict) else {})
    return {"expirations": expirations, "snapshots": rows}


def _format_row(row: Dict[str, object]) -> str:
    bid = row.get("bid")
    ask = row.get("ask")
    last = row.get("last")
    bid_ask = "-"
    if bid is not None or ask is not None:
        bid_fmt = f"{bid:.2f}" if isinstance(bid, (int, float)) else "-"
        ask_fmt = f"{ask:.2f}" if isinstance(ask, (int, float)) else "-"
        bid_ask = f"{bid_fmt}/{ask_fmt}"
    last_fmt = f"{last:.2f}" if isinstance(last, (int, float)) else "-"
    return (
        f"{row.get('expiry')} {row.get('right')} {row.get('strike'):<8}"
        f" | bid/ask {bid_ask:<11} | last {last_fmt:<6} | {row.get('symbol')}"
    )


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch option chain snapshots from Alpaca")
    parser.add_argument("symbol", help="Underlying ticker symbol, e.g. AAPL")
    parser.add_argument("--limit", type=int, default=15, help="Number of rows to display (default: 15)")
    args = parser.parse_args()

    data = await fetch_option_chain(args.symbol)
    expirations: Sequence[str] = data["expirations"]
    snapshots: Sequence[Dict[str, object]] = data["snapshots"]

    if not expirations:
        print(f"No option expirations found for {args.symbol.upper()}.")
    else:
        print(f"Option expirations for {args.symbol.upper()}: {', '.join(expirations)}")

    if not snapshots:
        print("No option quotes returned for this symbol.")
        return

    print("\nSample quotes:")
    for row in snapshots[: max(args.limit, 0) or len(snapshots)]:
        print("  " + _format_row(row))


if __name__ == "__main__":
    asyncio.run(main())
