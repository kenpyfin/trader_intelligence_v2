#!/usr/bin/env python3
"""Repair stocks_daily OHLCV using Alpaca split+dividend-adjusted daily bars.

Normalizes each ticker collection to a single canonical schema per trading day:
  Ticker, TimeStamp, Open, High, Low, Close, adjClose, Volume, Return, Fwd_Return

Close and adjClose are set to the same adjusted close from Alpaca (adjustment=all).

Usage:
  # Dry-run one ticker
  python scripts/repair_stocks_daily_from_alpaca.py --ticker AAPL --dry-run

  # Repair priority tickers from 2024-01-01
  python scripts/repair_stocks_daily_from_alpaca.py --tickers AAPL,MSFT,SPY --start 2024-01-01

  # Repair top market-cap names from screenerModel
  python scripts/repair_stocks_daily_from_alpaca.py --top-n 100 --start 2024-01-01

  # Repair all collections in stocks_daily (Phase 1 full universe)
  python scripts/repair_stocks_daily_from_alpaca.py --all-collections --start 2017-01-01 \
    --checkpoint /tmp/alpaca_repair_full.ckpt.json

  # Dedupe only (no Alpaca fetch): collapse duplicate same-day bars, coalesce fields
  python scripts/repair_stocks_daily_from_alpaca.py --ticker AAPL --dedupe-only --dry-run

Env (from .env or shell):
  APCA_API_KEY_ID, APCA_API_SECRET_KEY
  APCA_DATA_BASE_URL (default https://data.alpaca.markets)
  APCA_STOCK_FEED (iex|sip, default iex)
  APCA_BARS_BATCH_SIZE (default 50)
  APCA_BARS_MAX_RETRIES (default 5)
  MONGO_URI (default mongodb://10.0.1.22:27017)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import numpy as np
import pandas as pd
import pymongo
from dotenv import load_dotenv

try:
    from alpaca.common.exceptions import APIError as AlpacaAPIError
except ImportError:  # pragma: no cover
    AlpacaAPIError = Exception  # type: ignore[misc, assignment]

try:
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "alpaca-py is required. Install with: pip install alpaca-py"
    ) from exc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Lowercase + vendor junk fields to strip on repair
UNSET_FIELDS = [
    "open", "high", "low", "close", "volume", "datetime",
    "Adj Close", "change", "changePercent", "changeOverTime", "label",
    "vwap", "unadjustedVolume", "unadjustedvolume",
    "average", "barCount", "ask", "askSize", "bid", "bidSize",
]

CANONICAL_FIELDS = (
    "Ticker", "TimeStamp", "Open", "High", "Low", "Close", "adjClose", "Volume",
    "Return", "Fwd_Return",
)

DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_RETRIES = 5

# Mongo collection name -> Alpaca symbol (hyphen class shares use dot on Alpaca)
ALPACA_SYMBOL_MAP: Dict[str, str] = {
    "BRK-A": "BRK.A",
    "BRK-B": "BRK.B",
    "BF-A": "BF.A",
    "BF-B": "BF.B",
    "AKO-A": "AKO.A",
    "AKO-B": "AKO.B",
    "HEI-A": "HEI.A",
    "HEI-B": "HEI.B",
    "CWEN-A": "CWEN.A",
    "CWEN": "CWEN",
    "GEF-B": "GEF.B",
    "GEF": "GEF",
    "LEN-B": "LEN.B",
    "MOG-A": "MOG.A",
    "MOG-B": "MOG.B",
}
ALPACA_TO_MONGO: Dict[str, str] = {v.upper(): k for k, v in ALPACA_SYMBOL_MAP.items()}


def _utc_day_start(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    return datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)


def _mongo_client() -> pymongo.MongoClient:
    uri = os.getenv("MONGO_URI", "mongodb://10.0.1.22:27017")
    return pymongo.MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=8000)


def _alpaca_client() -> StockHistoricalDataClient:
    key = os.getenv("APCA_API_KEY_ID", "").strip()
    secret = os.getenv("APCA_API_SECRET_KEY", "").strip()
    if not key or not secret:
        raise ValueError("Set APCA_API_KEY_ID and APCA_API_SECRET_KEY")
    return StockHistoricalDataClient(key, secret)


def _stock_feed() -> DataFeed:
    raw = (os.getenv("APCA_STOCK_FEED") or "iex").strip().lower()
    if raw == "sip":
        return DataFeed.SIP
    return DataFeed.IEX


def _batch_size() -> int:
    raw = (os.getenv("APCA_BARS_BATCH_SIZE") or str(DEFAULT_BATCH_SIZE)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_BATCH_SIZE


def _max_retries() -> int:
    raw = (os.getenv("APCA_BARS_MAX_RETRIES") or str(DEFAULT_MAX_RETRIES)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_RETRIES


def _chunked(items: Sequence[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield list(items[i : i + size])


def to_alpaca_symbol(ticker: str) -> str:
    t = ticker.upper().strip()
    return ALPACA_SYMBOL_MAP.get(t, t)


def from_alpaca_symbol(symbol: str) -> str:
    s = symbol.upper().strip()
    return ALPACA_TO_MONGO.get(s, s)


def load_all_tickers(db: pymongo.database.Database) -> List[str]:
    return sorted(db.list_collection_names())


def load_mismatch_tickers(db: pymongo.database.Database) -> List[str]:
    """Tickers where Close and adjClose differ (legacy partial repair)."""
    out: List[str] = []
    for name in db.list_collection_names():
        coll = db[name]
        if coll.estimated_document_count() == 0:
            continue
        if coll.count_documents(
            {
                "$expr": {
                    "$gt": [
                        {"$abs": {"$subtract": ["$Close", "$adjClose"]}},
                        {"$multiply": [{"$abs": "$Close"}, 0.0001]},
                    ]
                }
            },
            limit=1,
        ):
            out.append(name)
    return sorted(out)


def _delete_timestamp_range(
    coll: pymongo.collection.Collection,
    start: date,
    end: date,
) -> int:
    """Delete bars in [start, end]; match naive and tz-aware TimeStamp values."""
    range_start_naive = datetime.combine(start, datetime.min.time())
    range_end_naive = datetime.combine(end, datetime.min.time()) + timedelta(days=1)
    range_start_utc = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    range_end_utc = datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
    del_res = coll.delete_many(
        {
            "$or": [
                {"TimeStamp": {"$gte": range_start_naive, "$lt": range_end_naive}},
                {"TimeStamp": {"$gte": range_start_utc, "$lt": range_end_utc}},
            ]
        }
    )
    return int(del_res.deleted_count)


def load_checkpoint(path: str) -> Set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        completed = data.get("completed") or []
        return {str(t).upper() for t in completed}
    except Exception as exc:
        logger.warning("Could not read checkpoint %s: %s", path, exc)
        return set()


def save_checkpoint(path: str, completed: Set[str], skipped: Set[str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "completed": sorted(completed),
        "skipped": sorted(skipped),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def is_collection_complete(db: pymongo.database.Database, ticker: str) -> bool:
    """True when collection looks fully Alpaca-repaired recently."""
    coll = db[ticker]
    if coll.estimated_document_count() == 0:
        return False
    miss_ohlc = coll.count_documents(
        {"$or": [{"Open": None}, {"High": None}, {"Low": None}]}
    )
    if miss_ohlc > 0:
        return False
    if coll.count_documents({"open": {"$exists": True}}) > 0:
        return False
    last = coll.find_one(sort=[("TimeStamp", -1)])
    if not last:
        return False
    last_ts = last.get("TimeStamp")
    if not isinstance(last_ts, datetime):
        return False
    if last.get("adjClose") is None:
        return False
    fresh_cutoff = datetime.now(timezone.utc).date() - timedelta(days=4)
    return last_ts.date() >= fresh_cutoff


def _is_retryable_alpaca_error(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True
    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) == 429:
        return True
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "too many requests" in text


def _retry_delay_seconds(exc: BaseException, attempt: int) -> float:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    if headers:
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after is not None:
            try:
                return max(float(retry_after), 1.0)
            except (TypeError, ValueError):
                pass
    return min(2.0 ** attempt, 60.0)


def _coalesce_ohlcv(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Merge capitalized and lowercase OHLCV into canonical capitalized fields."""
    def pick(upper: str, lower: str):
        v = doc.get(upper)
        if v is None:
            v = doc.get(lower)
        return v

    close = pick("Close", "close")
    out = {
        "Ticker": doc.get("Ticker"),
        "TimeStamp": doc.get("TimeStamp"),
        "Open": pick("Open", "open"),
        "High": pick("High", "high"),
        "Low": pick("Low", "low"),
        "Close": close,
        "adjClose": close if doc.get("adjClose") is None else doc.get("adjClose"),
        "Volume": pick("Volume", "volume"),
    }
    if out["adjClose"] is None:
        out["adjClose"] = out["Close"]
    return out


def _sortable_timestamp(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return _utc_day_start(ts)
    return _utc_day_start(pd.to_datetime(ts, utc=True).to_pydatetime())


def _add_returns(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not rows:
        return rows
    for row in rows:
        if row.get("TimeStamp") is not None:
            row["TimeStamp"] = _sortable_timestamp(row["TimeStamp"])
    rows = sorted(rows, key=lambda r: r["TimeStamp"])
    closes = [r.get("Close") for r in rows]
    for i, row in enumerate(rows):
        if i > 0 and closes[i - 1] not in (None, 0) and closes[i] is not None:
            row["Return"] = float((closes[i] - closes[i - 1]) / closes[i - 1])
        else:
            row["Return"] = row.get("Return")
        if i < len(rows) - 1 and closes[i] not in (None, 0) and closes[i + 1] is not None:
            row["Fwd_Return"] = float(np.log(closes[i + 1] / closes[i]))
        else:
            row["Fwd_Return"] = row.get("Fwd_Return")
    return rows


def _normalize_bars_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()

    if isinstance(frame.index, pd.MultiIndex):
        frame = frame.reset_index()
    else:
        frame = frame.reset_index()

    rename = {
        "symbol": "Ticker",
        "timestamp": "TimeStamp",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    frame.rename(columns={k: v for k, v in rename.items() if k in frame.columns}, inplace=True)
    if "TimeStamp" not in frame.columns and "timestamp" in frame.columns:
        frame["TimeStamp"] = frame["timestamp"]
    if "Ticker" not in frame.columns and "symbol" in frame.columns:
        frame["Ticker"] = frame["symbol"]

    frame["TimeStamp"] = pd.to_datetime(frame["TimeStamp"], utc=True).map(_utc_day_start)
    frame["Ticker"] = frame["Ticker"].astype(str).str.upper().map(from_alpaca_symbol)
    frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
    frame["adjClose"] = frame["Close"]
    for col in ("Open", "High", "Low", "Volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["Close", "Ticker"])
    keep = ["Ticker", "TimeStamp", "Open", "High", "Low", "Close", "adjClose", "Volume"]
    return frame[[c for c in keep if c in frame.columns]]


def _build_bars_request(
    tickers: Sequence[str],
    start: date,
    end: date,
) -> StockBarsRequest:
    # tickers are Mongo collection names; Alpaca API uses mapped symbols
    symbols = [to_alpaca_symbol(t) for t in tickers]
    symbol_arg: Any = symbols[0] if len(symbols) == 1 else symbols
    return StockBarsRequest(
        symbol_or_symbols=symbol_arg,
        timeframe=TimeFrame.Day,
        start=datetime.combine(start, datetime.min.time()).replace(tzinfo=timezone.utc),
        end=datetime.combine(end, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(days=1),
        adjustment=Adjustment.ALL,
        feed=_stock_feed(),
    )


def _is_invalid_symbol_error(exc: BaseException) -> bool:
    return "invalid symbol" in str(exc).lower()


def _extract_invalid_symbol(exc: BaseException) -> Optional[str]:
    match = re.search(r"invalid symbol:\s*([A-Za-z0-9.\-]+)", str(exc), re.IGNORECASE)
    if not match:
        return None
    return from_alpaca_symbol(match.group(1).upper())


def fetch_alpaca_daily_bars_batch(
    client: StockHistoricalDataClient,
    tickers: Sequence[str],
    start: date,
    end: date,
    max_retries: Optional[int] = None,
) -> pd.DataFrame:
    """Fetch split+dividend adjusted daily bars for one or more tickers with 429 retry."""
    if not tickers:
        return pd.DataFrame()

    retries = max_retries if max_retries is not None else _max_retries()
    request = _build_bars_request(tickers, start, end)
    last_exc: Optional[BaseException] = None

    for attempt in range(retries):
        try:
            bars = client.get_stock_bars(request)
            return _normalize_bars_frame(bars.df)
        except Exception as exc:
            last_exc = exc
            if _is_invalid_symbol_error(exc):
                raise
            if attempt + 1 >= retries or not _is_retryable_alpaca_error(exc):
                raise
            delay = _retry_delay_seconds(exc, attempt)
            logger.warning(
                "Alpaca rate limit for %s (attempt %d/%d); sleeping %.1fs",
                ",".join(tickers[:3]) + ("..." if len(tickers) > 3 else ""),
                attempt + 1,
                retries,
                delay,
            )
            time.sleep(delay)

    if last_exc is not None:
        raise last_exc
    return pd.DataFrame()


def _fetch_single_ticker_bars(
    client: StockHistoricalDataClient,
    ticker: str,
    start: date,
    end: date,
    max_retries: Optional[int],
) -> pd.DataFrame:
    try:
        return fetch_alpaca_daily_bars_batch(client, [ticker], start, end, max_retries)
    except Exception as exc:
        if _is_invalid_symbol_error(exc):
            logger.warning("Skipping invalid Alpaca symbol %s: %s", ticker, exc)
            return pd.DataFrame()
        raise


def fetch_alpaca_daily_bars_resilient(
    client: StockHistoricalDataClient,
    tickers: Sequence[str],
    start: date,
    end: date,
    max_retries: Optional[int] = None,
) -> pd.DataFrame:
    """Batch fetch; drop invalid symbols and continue with the rest of the batch."""
    pending = [t.upper().strip() for t in tickers if t]
    if not pending:
        return pd.DataFrame()
    if len(pending) == 1:
        return _fetch_single_ticker_bars(client, pending[0], start, end, max_retries)

    frames: List[pd.DataFrame] = []
    skipped: List[str] = []

    while pending:
        try:
            frame = fetch_alpaca_daily_bars_batch(client, pending, start, end, max_retries)
            if not frame.empty:
                frames.append(frame)
            break
        except Exception as exc:
            if not _is_invalid_symbol_error(exc):
                raise
            bad = _extract_invalid_symbol(exc)
            if bad and bad in pending:
                pending = [t for t in pending if t != bad]
                skipped.append(bad)
                logger.warning("Skipping invalid Alpaca symbol %s; retrying batch (%d left)", bad, len(pending))
                continue

            logger.warning(
                "Could not isolate invalid symbol in batch; falling back to per-ticker fetch (%d symbols)",
                len(pending),
            )
            for ticker in pending:
                single = _fetch_single_ticker_bars(client, ticker, start, end, max_retries)
                if not single.empty:
                    frames.append(single)
            break

    if skipped:
        logger.info("Skipped invalid symbols: %s", ", ".join(skipped))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def fetch_alpaca_daily_bars(
    client: StockHistoricalDataClient,
    ticker: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Fetch split+dividend adjusted daily bars for a single ticker."""
    frame = fetch_alpaca_daily_bars_batch(client, [ticker], start, end)
    if frame.empty:
        return frame
    return frame[frame["Ticker"] == ticker.upper()].copy()


def bars_to_docs(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    rows = frame.to_dict(orient="records")
    for row in rows:
        row["TimeStamp"] = _utc_day_start(row["TimeStamp"])
        for k in ("Open", "High", "Low", "Close", "adjClose", "Volume"):
            if row.get(k) is not None and not (isinstance(row[k], float) and np.isnan(row[k])):
                row[k] = float(row[k])
    return _add_returns(rows)


def load_top_tickers(client: pymongo.MongoClient, top_n: int) -> List[str]:
    coll = client["all_symbol"]["screenerModel"]
    latest = coll.find_one({"Refresh_Date": {"$exists": True}}, sort=[("Refresh_Date", -1)])
    if not latest:
        raise RuntimeError("No screenerModel Refresh_Date found")
    refresh = latest["Refresh_Date"]
    fields = {"Ticker": 1, "Market_cap": 1, "Market Cap": 1, "market_cap": 1, "marketCap": 1}
    docs = list(coll.find({"Refresh_Date": refresh}, fields))
    if not docs:
        raise RuntimeError(f"No screener rows for Refresh_Date={refresh}")

    def cap_val(doc: Dict[str, Any]) -> float:
        for key in ("Market_cap", "Market Cap", "market_cap", "marketCap"):
            v = doc.get(key)
            if v is None:
                continue
            try:
                return float(str(v).replace(",", "").replace("$", ""))
            except ValueError:
                continue
        return 0.0

    docs.sort(key=cap_val, reverse=True)
    tickers = []
    seen = set()
    for doc in docs:
        t = str(doc.get("Ticker", "")).upper().strip()
        if not t or t in seen:
            continue
        seen.add(t)
        tickers.append(t)
        if len(tickers) >= top_n:
            break
    return tickers


def dedupe_collection(
    coll: pymongo.collection.Collection,
    ticker: str,
    start: Optional[date],
    dry_run: bool,
) -> Dict[str, int]:
    """Collapse duplicate same-day docs by coalescing OHLCV; keep one per date."""
    query: Dict[str, Any] = {}
    if start:
        query["TimeStamp"] = {"$gte": datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)}
    docs = list(coll.find(query).sort("TimeStamp", 1))
    by_day: Dict[date, List[Dict[str, Any]]] = {}
    for doc in docs:
        ts = doc.get("TimeStamp")
        if not isinstance(ts, datetime):
            continue
        by_day.setdefault(ts.date(), []).append(doc)

    deleted = 0
    upserted = 0
    for day, day_docs in sorted(by_day.items()):
        if len(day_docs) == 1:
            merged = _coalesce_ohlcv(day_docs[0])
            merged["Ticker"] = ticker.upper()
            merged["TimeStamp"] = _utc_day_start(day_docs[0]["TimeStamp"])
            if merged.get("adjClose") is None:
                merged["adjClose"] = merged.get("Close")
            # Skip if still incomplete
            if any(merged.get(k) is None for k in ("Open", "High", "Low", "Close", "Volume")):
                continue
            if not dry_run:
                coll.replace_one({"_id": day_docs[0]["_id"]}, merged, upsert=False)
                unset = {f: "" for f in UNSET_FIELDS}
                coll.update_one({"_id": day_docs[0]["_id"]}, {"$unset": unset})
            upserted += 1
            continue

        # Multiple docs same day: merge fields, prefer capitalized non-null
        merged = {"Ticker": ticker.upper(), "TimeStamp": _utc_day_start(day_docs[0]["TimeStamp"])}
        for doc in day_docs:
            coalesced = _coalesce_ohlcv(doc)
            for k in ("Open", "High", "Low", "Close", "adjClose", "Volume"):
                if merged.get(k) is None and coalesced.get(k) is not None:
                    merged[k] = coalesced[k]
        if merged.get("adjClose") is None:
            merged["adjClose"] = merged.get("Close")
        if any(merged.get(k) is None for k in ("Open", "High", "Low", "Close", "Volume")):
            continue
        if dry_run:
            deleted += len(day_docs) - 1
            upserted += 1
            continue
        day_start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        coll.delete_many({"TimeStamp": {"$gte": day_start, "$lt": day_end}})
        deleted += len(day_docs)
        coll.insert_one(merged)
        upserted += 1

    if upserted and not dry_run:
        # Recompute returns on full series
        all_docs = list(coll.find({}, CANONICAL_FIELDS).sort("TimeStamp", 1))
        repaired = _add_returns(all_docs)
        for doc in repaired:
            coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {"Return": doc.get("Return"), "Fwd_Return": doc.get("Fwd_Return")}},
            )

    return {"days_processed": len(by_day), "days_written": upserted, "docs_deleted": deleted}


def repair_ticker_from_frame(
    db: pymongo.database.Database,
    ticker: str,
    frame: pd.DataFrame,
    dry_run: bool,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> Dict[str, Any]:
    ticker = ticker.upper()
    coll = db[ticker]
    stats: Dict[str, Any] = {"ticker": ticker, "fetched": 0, "written": 0, "deleted": 0}

    ticker_frame = frame[frame["Ticker"] == ticker] if not frame.empty else frame
    stats["fetched"] = len(ticker_frame)
    if ticker_frame.empty:
        logger.warning("%s: no Alpaca bars returned", ticker)
        return stats

    docs = bars_to_docs(ticker_frame)
    for doc in docs:
        doc["Ticker"] = ticker

    if dry_run:
        stats["written"] = len(docs)
        stats["deleted"] = len(docs)
        return stats

    if start is not None and end is not None:
        stats["deleted"] = _delete_timestamp_range(coll, start, end)
    else:
        stats["deleted"] = 0

    if docs:
        coll.insert_many(docs)
        stats["written"] = len(docs)

    if stats["written"]:
        all_docs = list(coll.find({}, list(CANONICAL_FIELDS)).sort("TimeStamp", 1))
        for d in all_docs:
            d.pop("_id", None)
        repaired = _add_returns(all_docs)
        for doc in repaired:
            ts = doc["TimeStamp"]
            coll.update_one(
                {"TimeStamp": ts},
                {
                    "$set": {
                        "Return": doc.get("Return"),
                        "Fwd_Return": doc.get("Fwd_Return"),
                    },
                    "$unset": {f: "" for f in UNSET_FIELDS},
                },
            )

    return stats


def repair_ticker(
    db: pymongo.database.Database,
    alpaca: StockHistoricalDataClient,
    ticker: str,
    start: date,
    end: date,
    dry_run: bool,
    dedupe_only: bool,
) -> Dict[str, Any]:
    ticker = ticker.upper()
    coll = db[ticker]
    stats: Dict[str, Any] = {"ticker": ticker, "fetched": 0, "written": 0, "deleted": 0}

    if dedupe_only:
        stats.update(dedupe_collection(coll, ticker, start, dry_run))
        return stats

    frame = fetch_alpaca_daily_bars(alpaca, ticker, start, end)
    return repair_ticker_from_frame(db, ticker, frame, dry_run, start=start, end=end)


def parse_tickers(args: argparse.Namespace, mongo: pymongo.MongoClient, db) -> List[str]:
    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.top_n:
        tickers = load_top_tickers(mongo, args.top_n)
    elif args.all_collections:
        tickers = load_all_tickers(db)
    elif args.mismatch_only:
        tickers = load_mismatch_tickers(db)
    else:
        raise ValueError(
            "Provide --ticker, --tickers, --top-n, --all-collections, or --mismatch-only"
        )

    if args.limit is not None:
        tickers = tickers[: args.limit]
    return tickers


def main(argv: Optional[Sequence[str]] = None) -> int:
    script_path = Path(__file__).resolve()
    for env_path in (
        script_path.parents[1] / ".env",
        script_path.parents[2] / ".env",
        Path.cwd() / ".env",
    ):
        load_dotenv(env_path)
    parser = argparse.ArgumentParser(description="Repair stocks_daily from Alpaca adjusted OHLCV")
    parser.add_argument("--ticker", help="Single ticker symbol")
    parser.add_argument("--tickers", help="Comma-separated tickers")
    parser.add_argument("--top-n", type=int, help="Top N tickers by market cap from screenerModel")
    parser.add_argument("--all-collections", action="store_true",
                        help="Repair all collection names in stocks_daily")
    parser.add_argument("--mismatch-only", action="store_true",
                        help="Repair only tickers where Close != adjClose")
    parser.add_argument("--start", default="2017-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD (default today UTC)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to MongoDB")
    parser.add_argument("--dedupe-only", action="store_true", help="Only dedupe/coalesce existing docs")
    parser.add_argument("--batch-size", type=int, default=None, help="Symbols per Alpaca request (default 50)")
    parser.add_argument("--sleep", type=float, default=0.5, help="Seconds between Alpaca batches")
    parser.add_argument("--checkpoint", default=None,
                        help="JSON checkpoint path for resume (e.g. /tmp/alpaca_repair_full.ckpt.json)")
    parser.add_argument("--skip-complete", action="store_true",
                        help="Skip collections that already look fully repaired")
    parser.add_argument("--limit", type=int, default=None, help="Process only first N tickers (testing)")
    args = parser.parse_args(argv)

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else datetime.now(timezone.utc).date()
    batch_size = args.batch_size if args.batch_size is not None else _batch_size()

    mongo = _mongo_client()
    mongo.admin.command("ping")
    db = mongo["stocks_daily"]
    tickers = parse_tickers(args, mongo, db)
    alpaca = None if args.dedupe_only else _alpaca_client()

    completed: Set[str] = load_checkpoint(args.checkpoint) if args.checkpoint else set()
    skipped: Set[str] = set()
    if args.checkpoint and Path(args.checkpoint).exists():
        try:
            skipped = {str(t).upper() for t in json.loads(Path(args.checkpoint).read_text()).get("skipped", [])}
        except Exception:
            skipped = set()

    pending_tickers: List[str] = []
    for t in tickers:
        if t in completed:
            continue
        if args.skip_complete and is_collection_complete(db, t):
            completed.add(t)
            continue
        pending_tickers.append(t)

    logger.info(
        "Repairing %d tickers (%d pending, %d already done) from %s to %s "
        "(dry_run=%s dedupe_only=%s feed=%s batch_size=%d)",
        len(tickers), len(pending_tickers), len(completed),
        start, end, args.dry_run, args.dedupe_only, os.getenv("APCA_STOCK_FEED", "iex"), batch_size,
    )

    summary = []
    if args.dedupe_only:
        for i, ticker in enumerate(pending_tickers, 1):
            try:
                stats = repair_ticker(db, alpaca, ticker, start, end, args.dry_run, args.dedupe_only)
                summary.append(stats)
                completed.add(ticker)
                if args.checkpoint:
                    save_checkpoint(args.checkpoint, completed, skipped)
                logger.info("[%d/%d] %s: %s", i, len(pending_tickers), ticker, stats)
            except Exception as exc:
                logger.exception("[%d/%d] %s failed: %s", i, len(pending_tickers), ticker, exc)
    else:
        batches = list(_chunked(pending_tickers, batch_size))
        for batch_idx, batch in enumerate(batches, 1):
            try:
                frame = fetch_alpaca_daily_bars_resilient(alpaca, batch, start, end)
            except Exception as exc:
                logger.exception(
                    "Batch %d/%d failed (%s): %s",
                    batch_idx,
                    len(batches),
                    ",".join(batch[:5]) + ("..." if len(batch) > 5 else ""),
                    exc,
                )
                if batch_idx < len(batches):
                    time.sleep(args.sleep)
                continue

            if frame.empty:
                logger.warning("Batch %d/%d returned no bars", batch_idx, len(batches))
                for ticker in batch:
                    skipped.add(ticker)
                if args.checkpoint:
                    save_checkpoint(args.checkpoint, completed, skipped)
                if batch_idx < len(batches):
                    time.sleep(args.sleep)
                continue

            for ticker in batch:
                try:
                    stats = repair_ticker_from_frame(
                        db, ticker, frame, args.dry_run, start=start, end=end,
                    )
                    summary.append(stats)
                    if stats.get("written", 0) > 0 or stats.get("fetched", 0) > 0:
                        completed.add(ticker)
                    else:
                        skipped.add(ticker)
                    logger.info("[%s] %s", ticker, stats)
                except Exception as exc:
                    logger.exception("Ticker %s failed after batch fetch: %s", ticker, exc)
                    skipped.add(ticker)

            if args.checkpoint:
                save_checkpoint(args.checkpoint, completed, skipped)

            if batch_idx < len(batches):
                time.sleep(args.sleep)

    written = sum(s.get("written", 0) for s in summary)
    logger.info(
        "Done. processed=%d written=%d completed=%d skipped=%d",
        len(summary), written, len(completed), len(skipped),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
