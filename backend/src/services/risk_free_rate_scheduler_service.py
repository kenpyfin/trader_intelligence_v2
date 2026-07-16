"""Daily risk-free rate calculation scheduling and persistence."""
from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional, Tuple

import pytz

from ..my_libs_py3.db import connect_mongo
from .macro_service import calculate_market_implied_risk_free_rate

MACRO_METRICS_COLLECTION = "macro_metrics"
DEFAULT_RF_TICKERS = ["SPY", "QQQ", "IWM"]
US_EASTERN = pytz.timezone("US/Eastern")
DEFAULT_MARKET_OPEN = datetime.time(9, 30)
DEFAULT_MARKET_CLOSE = datetime.time(16, 0)


def _utc_now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _today_iso() -> str:
    return datetime.date.today().isoformat()


def _metrics_collection():
    conn = connect_mongo("trader_intelligence")
    return conn.db[MACRO_METRICS_COLLECTION]


def is_us_trading_day(check_date: Optional[datetime.date] = None) -> bool:
    """Return True when the US equity market has a scheduled session on check_date."""
    check_date = check_date or datetime.date.today()
    if check_date.weekday() >= 5:
        return False
    return _alpaca_calendar_has_session(check_date)


def _default_session_bounds(check_date: datetime.date) -> Tuple[datetime.datetime, datetime.datetime]:
    open_dt = US_EASTERN.localize(datetime.datetime.combine(check_date, DEFAULT_MARKET_OPEN))
    close_dt = US_EASTERN.localize(datetime.datetime.combine(check_date, DEFAULT_MARKET_CLOSE))
    return open_dt, close_dt


def _normalize_to_eastern(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return US_EASTERN.localize(value)
    return value.astimezone(US_EASTERN)


def _get_trading_session_bounds(
    check_date: datetime.date,
) -> Optional[Tuple[datetime.datetime, datetime.datetime]]:
    """Return (open, close) in US/Eastern for check_date, or None when there is no session."""
    if check_date.weekday() >= 5:
        return None

    key = os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("APCA_API_SECRET_KEY")
    if not key or not secret:
        return _default_session_bounds(check_date)

    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetCalendarRequest

        base_url = (os.getenv("APCA_API_BASE_URL") or "https://api.alpaca.markets").lower()
        paper = "paper" in base_url or "sandbox" in base_url
        client = TradingClient(key, secret, paper=paper)
        events = client.get_calendar(GetCalendarRequest(start=check_date, end=check_date))
        if not events:
            return None
        event = events[0]
        return _normalize_to_eastern(event.open), _normalize_to_eastern(event.close)
    except Exception as exc:
        print(f"WARN(RiskFreeRateScheduler): Alpaca session bounds lookup failed: {exc}")
        return _default_session_bounds(check_date)


def is_us_market_hours(now: Optional[datetime.datetime] = None) -> bool:
    """Return True when US equity markets are currently in regular session."""
    if now is None:
        eastern_now = datetime.datetime.now(US_EASTERN)
    else:
        eastern_now = _normalize_to_eastern(now)

    check_date = eastern_now.date()
    if not is_us_trading_day(check_date):
        return False

    bounds = _get_trading_session_bounds(check_date)
    if not bounds:
        return False

    open_dt, close_dt = bounds
    return open_dt <= eastern_now < close_dt


def is_us_market_hours_for_timestamp(timestamp: datetime.datetime) -> bool:
    """Return True when timestamp falls within US regular session (UTC-aware safe)."""
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
    return is_us_market_hours(timestamp.astimezone(US_EASTERN))


def _alpaca_calendar_has_session(check_date: datetime.date) -> bool:
    key = os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("APCA_API_SECRET_KEY")
    if not key or not secret:
        return True

    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetCalendarRequest

        base_url = (os.getenv("APCA_API_BASE_URL") or "https://api.alpaca.markets").lower()
        paper = "paper" in base_url or "sandbox" in base_url
        client = TradingClient(key, secret, paper=paper)
        events = client.get_calendar(GetCalendarRequest(start=check_date, end=check_date))
        return bool(events)
    except Exception as exc:
        print(f"WARN(RiskFreeRateScheduler): Alpaca calendar check failed: {exc}")
        return check_date.weekday() < 5


def _latest_metric_doc() -> Optional[Dict[str, Any]]:
    return _metrics_collection().find_one({}, sort=[("created_at", -1)])


def _has_rate_for_today() -> bool:
    return _metrics_collection().find_one({"as_of": _today_iso()}) is not None


def get_health() -> Dict[str, Any]:
    today = _today_iso()
    latest = _latest_metric_doc()
    latest_rate = latest.get("risk_free_rate") if latest else None
    latest_as_of = latest.get("as_of") if latest else None

    if not is_us_trading_day():
        return {
            "status": "healthy",
            "reason": "non_trading_day",
            "as_of": today,
            "latest_rate": latest_rate,
            "latest_as_of": latest_as_of,
            "tickers": DEFAULT_RF_TICKERS,
        }

    if not is_us_market_hours() and not _has_rate_for_today():
        return {
            "status": "healthy",
            "reason": "outside_market_hours",
            "as_of": today,
            "latest_rate": latest_rate,
            "latest_as_of": latest_as_of,
            "tickers": DEFAULT_RF_TICKERS,
        }

    if _has_rate_for_today():
        today_doc = _metrics_collection().find_one({"as_of": today}, sort=[("created_at", -1)])
        return {
            "status": "healthy",
            "reason": "calculated_today",
            "as_of": today,
            "latest_rate": today_doc.get("risk_free_rate") if today_doc else latest_rate,
            "latest_as_of": today,
            "tickers": (today_doc or {}).get("tickers") or DEFAULT_RF_TICKERS,
        }

    return {
        "status": "stale",
        "reason": "missing_today",
        "as_of": today,
        "latest_rate": latest_rate,
        "latest_as_of": latest_as_of,
        "tickers": DEFAULT_RF_TICKERS,
    }


def get_latest_daily_rate() -> Dict[str, Any]:
    latest = _latest_metric_doc()
    if not latest:
        return {"status": "empty", "risk_free_rate": None}
    created = latest.get("created_at")
    return {
        "status": "success",
        "risk_free_rate": latest.get("risk_free_rate"),
        "as_of": latest.get("as_of"),
        "created_at": created.isoformat() if isinstance(created, datetime.datetime) else created,
        "tickers": latest.get("tickers") or DEFAULT_RF_TICKERS,
        "source": latest.get("source") or "daily_calculation",
    }


async def calculate_and_store_daily_risk_free_rate(
    tickers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not is_us_market_hours():
        return {
            "status": "skipped",
            "reason": "outside_market_hours",
            "message": "Skipped: US equity market is closed.",
        }

    normalized_tickers = [t.strip().upper() for t in (tickers or DEFAULT_RF_TICKERS) if t and t.strip()]
    if not normalized_tickers:
        normalized_tickers = list(DEFAULT_RF_TICKERS)

    rate, logs = await calculate_market_implied_risk_free_rate(normalized_tickers)
    if rate is None:
        return {
            "status": "error",
            "message": "Could not compute market-implied risk-free rate.",
            "logs": logs,
        }

    now = _utc_now()
    today = now.date().isoformat()
    doc = {
        "as_of": today,
        "created_at": now,
        "risk_free_rate": float(rate),
        "tickers": normalized_tickers,
        "source": "daily_calculation",
    }
    insert_res = _metrics_collection().insert_one(doc)
    return {
        "status": "success",
        "snapshot_id": str(insert_res.inserted_id),
        "as_of": today,
        "risk_free_rate": float(rate),
        "tickers": normalized_tickers,
        "logs": logs,
    }


async def run_daily_risk_free_rate_if_stale(
    tickers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not is_us_trading_day():
        return {
            "status": "skipped",
            "reason": "non_trading_day",
            "message": "Skipped: not a US trading day.",
        }
    if _has_rate_for_today():
        latest = get_latest_daily_rate()
        return {
            "status": "success",
            "message": "Risk-free rate already calculated today.",
            "as_of": latest.get("as_of"),
            "risk_free_rate": latest.get("risk_free_rate"),
        }
    if not is_us_market_hours():
        return {
            "status": "skipped",
            "reason": "outside_market_hours",
            "message": "Skipped: US equity market is closed.",
        }
    return await calculate_and_store_daily_risk_free_rate(tickers=tickers)
