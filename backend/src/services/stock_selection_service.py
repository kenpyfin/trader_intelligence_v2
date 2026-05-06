from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from ..analytics.peer_classification import (
    ClusterResult,
    build_feature_frame,
    cluster_peers,
    preprocess_feature_frame,
)
from ..analytics.strategy_registry import (
    DEFAULT_STRATEGY_ID,
    get_strategy,
    list_strategies as list_registered_strategies,
)
from ..my_libs_py3.db import connect_mongo


MODEL_VERSION = "peer-v1.0"
SNAPSHOT_COLLECTION = "stock_selection_snapshots"
FRESHNESS_TARGET_MINUTES = 24 * 60


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float, np.number)):
        if np.isnan(value) or np.isinf(value):
            return None
        return float(value)
    text = str(value).strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
    suffix_mult = 1.0
    up = text.upper()
    if up.endswith("T"):
        suffix_mult = 1e12
        text = text[:-1]
    elif up.endswith("B"):
        suffix_mult = 1e9
        text = text[:-1]
    elif up.endswith("M"):
        suffix_mult = 1e6
        text = text[:-1]
    elif up.endswith("K"):
        suffix_mult = 1e3
        text = text[:-1]
    try:
        return float(text) * suffix_mult
    except Exception:
        return None


def _sanitize_for_json(item: Any) -> Any:
    if isinstance(item, dict):
        return {str(k): _sanitize_for_json(v) for k, v in item.items()}
    if isinstance(item, list):
        return [_sanitize_for_json(v) for v in item]
    if isinstance(item, tuple):
        return [_sanitize_for_json(v) for v in item]
    if isinstance(item, pd.Timestamp):
        return item.isoformat()
    if isinstance(item, datetime):
        return item.isoformat()
    if isinstance(item, np.generic):
        return item.item()
    if isinstance(item, float) and (np.isnan(item) or np.isinf(item)):
        return None
    return item


def _latest_refresh_date() -> Optional[datetime]:
    conn = connect_mongo("all_symbol", "screenerModel")
    doc = conn.table.find_one({"Refresh_Date": {"$exists": True}}, sort=[("Refresh_Date", -1)])
    if not doc:
        return None
    return doc.get("Refresh_Date")


def _load_fundamentals(max_tickers: int) -> pd.DataFrame:
    refresh_date = _latest_refresh_date()
    if refresh_date is None:
        return pd.DataFrame()

    fields = {
        "_id": 0,
        "Ticker": 1,
        "Sector": 1,
        "Industry": 1,
        "Refresh_Date": 1,
        "P/E": 1,
        "P/S": 1,
        "P/Cash": 1,
        "P/Free Cash Flow": 1,
        "Gross Margin": 1,
        "Operating Margin": 1,
        "Profit Margin": 1,
        "EPS (ttm)": 1,
        "Current Ratio": 1,
        "Quick Ratio": 1,
        "Total Debt/Equity": 1,
        "Institutional Ownership": 1,
        "Insider Ownership": 1,
        "Analyst Recom": 1,
        # Keep multiple possible market cap field variants to handle schema drift.
        "Market_cap": 1,
        "Market Cap": 1,
        "market_cap": 1,
        "marketCap": 1,
    }
    conn = connect_mongo("all_symbol", "screenerModel")
    docs = list(conn.table.find({"Refresh_Date": refresh_date}, fields))
    if not docs:
        return pd.DataFrame()
    df = pd.DataFrame(docs)
    if "Ticker" not in df.columns:
        return pd.DataFrame()
    df["ticker"] = df["Ticker"].astype(str).str.upper()
    df = df.drop_duplicates(subset=["ticker"], keep="last")

    # Normalize market cap source field into canonical `Market_cap`.
    market_cap_source = next(
        (c for c in ["Market_cap", "Market Cap", "market_cap", "marketCap"] if c in df.columns),
        None,
    )
    if market_cap_source is not None:
        df["Market_cap"] = df[market_cap_source]
    else:
        df["Market_cap"] = np.nan

    numeric_map = {
        "P/E": "pe",
        "P/S": "ps",
        "P/Cash": "pcash",
        "P/Free Cash Flow": "pfcf",
        "Gross Margin": "gross_margin",
        "Operating Margin": "operating_margin",
        "Profit Margin": "profit_margin",
        "EPS (ttm)": "eps_ttm",
        "Current Ratio": "current_ratio",
        "Quick Ratio": "quick_ratio",
        "Total Debt/Equity": "debt_equity",
        "Institutional Ownership": "inst_own",
        "Insider Ownership": "insider_own",
        "Analyst Recom": "analyst_recom",
    }
    for src, dst in numeric_map.items():
        df[dst] = df[src].apply(_safe_float) if src in df.columns else np.nan

    df["value_score"] = (
        pd.Series(df["pe"]).rank(pct=True, ascending=False).fillna(0.5)
        + pd.Series(df["ps"]).rank(pct=True, ascending=False).fillna(0.5)
        + pd.Series(df["pcash"]).rank(pct=True, ascending=False).fillna(0.5)
        + pd.Series(df["pfcf"]).rank(pct=True, ascending=False).fillna(0.5)
    ) / 4.0
    df["quality_score"] = (
        pd.Series(df["gross_margin"]).rank(pct=True, ascending=True).fillna(0.5)
        + pd.Series(df["operating_margin"]).rank(pct=True, ascending=True).fillna(0.5)
        + pd.Series(df["profit_margin"]).rank(pct=True, ascending=True).fillna(0.5)
        + pd.Series(df["eps_ttm"]).rank(pct=True, ascending=True).fillna(0.5)
    ) / 4.0
    df["resilience_score"] = (
        pd.Series(df["current_ratio"]).rank(pct=True, ascending=True).fillna(0.5)
        + pd.Series(df["quick_ratio"]).rank(pct=True, ascending=True).fillna(0.5)
        + pd.Series(df["debt_equity"]).rank(pct=True, ascending=False).fillna(0.5)
    ) / 3.0
    df["positioning_score"] = (
        pd.Series(df["inst_own"]).rank(pct=True, ascending=True).fillna(0.5)
        + pd.Series(df["insider_own"]).rank(pct=True, ascending=True).fillna(0.5)
        + pd.Series(df["analyst_recom"]).rank(pct=True, ascending=False).fillna(0.5)
    ) / 3.0

    # Down-select for runtime practicality by available market cap
    df["market_cap_num"] = df["Market_cap"].apply(_safe_float).fillna(0.0)
    df = df.sort_values("market_cap_num", ascending=False).head(max_tickers)
    return df


def _price_metrics_for_ticker(ticker: str, lookback: int = 90) -> Optional[Dict[str, Any]]:
    conn = connect_mongo("stocks_daily")
    coll = conn.db[ticker]
    docs = list(coll.find({}, {"_id": 0, "Close": 1, "Volume": 1, "TimeStamp": 1}).sort("TimeStamp", -1).limit(lookback))
    if len(docs) < 30:
        return None
    df = pd.DataFrame(docs).sort_values("TimeStamp")
    if "Close" not in df.columns or "Volume" not in df.columns:
        return None
    close = pd.to_numeric(df["Close"], errors="coerce")
    volume = pd.to_numeric(df["Volume"], errors="coerce")
    returns = np.log(close / close.shift(1)).dropna()
    if len(returns) < 20:
        return None

    ret_10d = _safe_float((close.iloc[-1] / close.iloc[-10]) - 1) if len(close) >= 10 else None
    ret_20d = _safe_float((close.iloc[-1] / close.iloc[-20]) - 1) if len(close) >= 20 else None
    sma20 = close.tail(20).mean()
    sma60 = close.tail(60).mean() if len(close) >= 60 else close.mean()
    trend_20_60 = _safe_float((sma20 / sma60) - 1) if sma60 else None
    rolling_max = close.tail(20).max()
    drawdown_20d = _safe_float((close.iloc[-1] / rolling_max) - 1) if rolling_max else None
    vol_20d = _safe_float(returns.tail(20).std() * np.sqrt(252))
    adv20_shares = _safe_float(volume.tail(20).mean())
    adv20_dollar = _safe_float((close.tail(20) * volume.tail(20)).mean())
    volume_stability = _safe_float(1.0 / (volume.tail(20).std() / (volume.tail(20).mean() + 1e-9)))

    return {
        "ticker": ticker,
        "ret_10d": ret_10d,
        "ret_20d": ret_20d,
        "vol_20d": vol_20d,
        "trend_20_60": trend_20_60,
        "drawdown_20d": drawdown_20d,
        "adv20_shares": adv20_shares,
        "adv20_dollar": adv20_dollar,
        "volume_stability": volume_stability,
    }


def _load_daily_metrics(tickers: pd.Series) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        metric = _price_metrics_for_ticker(ticker)
        if metric is not None:
            rows.append(metric)
    return pd.DataFrame(rows)


def _load_intraday_metrics(tickers: pd.Series) -> pd.DataFrame:
    rows = []
    conn = connect_mongo("stocks_10minute")
    for ticker in tickers:
        coll = conn.db[ticker]
        docs = list(coll.find({}, {"_id": 0, "Close": 1, "TimeStamp": 1}).sort("TimeStamp", -1).limit(240))
        if len(docs) < 40:
            continue
        df = pd.DataFrame(docs).sort_values("TimeStamp")
        close = pd.to_numeric(df["Close"], errors="coerce")
        returns = np.log(close / close.shift(1)).dropna()
        if len(returns) < 20:
            continue
        rows.append(
            {
                "ticker": ticker,
                "intraday_vol_5d": _safe_float(returns.tail(5 * 24).std() * np.sqrt(252)),
                "intraday_trend_5d": _safe_float((close.iloc[-1] / close.iloc[-(5 * 24)]) - 1) if len(close) >= 5 * 24 else None,
            }
        )
    return pd.DataFrame(rows)


def _load_iv_metrics(tickers: pd.Series) -> pd.DataFrame:
    rows = []
    iv_conn = connect_mongo("iv_history")
    for ticker in tickers:
        coll = iv_conn.db[ticker]
        docs = list(coll.find({}, {"_id": 0, "spot_iv": 1, "iv_7d": 1, "iv_30d": 1, "TimeStamp": 1}).sort("TimeStamp", -1).limit(320))
        if not docs:
            continue
        docs = list(reversed(docs))
        spot = [d.get("spot_iv") for d in docs if d.get("spot_iv") is not None]
        if len(spot) < 30:
            continue
        current = float(spot[-1])
        min_iv = float(min(spot))
        max_iv = float(max(spot))
        iv_rank = 0.5 if max_iv == min_iv else (current - min_iv) / (max_iv - min_iv)
        latest = docs[-1]
        iv_30d = _safe_float(latest.get("iv_30d"))
        iv_7d = _safe_float(latest.get("iv_7d"))
        rows.append(
            {
                "ticker": ticker,
                "iv_rank": _safe_float(iv_rank),
                "spot_iv": _safe_float(latest.get("spot_iv")),
                "iv_term_slope": None if iv_30d is None or iv_7d is None else _safe_float(iv_30d - iv_7d),
            }
        )
    return pd.DataFrame(rows)


def _snapshot_collection():
    conn = connect_mongo("trader_intelligence", SNAPSHOT_COLLECTION)
    return conn.table


def _shape_payload(
    grouped: Dict[str, Dict[str, Any]],
    metadata: Dict[str, Any],
    mode: str,
) -> Dict[str, Any]:
    return {
        "metadata": metadata,
        "clusters": grouped[mode]["clusters"],
        "sectors": grouped[mode]["sectors"],
        "regimes": grouped[mode]["regimes"],
    }


def _latest_snapshot_query(strategy_id: str) -> Dict[str, Any]:
    if strategy_id == DEFAULT_STRATEGY_ID:
        return {
            "status": "success",
            "$or": [
                {"strategy_id": strategy_id},
                {"strategy_id": {"$exists": False}},
            ],
        }
    return {"status": "success", "strategy_id": strategy_id}


def _strategy_doc_candidates(strategy_id: str) -> list[Path]:
    """Ordered search paths for strategy markdown (first existing wins)."""
    strategy = get_strategy(strategy_id)
    doc_ref = strategy.documentation_file.strip()
    service_file = Path(__file__).resolve()
    # .../backend/src/services/stock_selection_service.py -> backend root
    backend_root = service_file.parents[2]

    candidates: list[Path] = []

    explicit = os.getenv("STOCK_SELECTION_STRATEGIES_PATH", "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser().resolve())

    env_root = os.getenv("TRADER_INTELLIGENCE_PROJECT_ROOT", "").strip()
    if env_root:
        root = Path(env_root).expanduser().resolve()
        candidates.append(root / doc_ref if "/" not in doc_ref else root / Path(doc_ref))

    if "/" in doc_ref or doc_ref.startswith("docs" + os.sep):
        candidates.append((backend_root / doc_ref).resolve())
    else:
        candidates.append((backend_root / "docs" / doc_ref).resolve())
        for parent in service_file.parents:
            candidates.append((parent / doc_ref).resolve())
            candidates.append((parent / "docs" / doc_ref).resolve())

    candidates.append((Path.cwd() / doc_ref).resolve())
    candidates.append((Path.cwd() / "docs" / doc_ref).resolve())

    seen: set[str] = set()
    ordered: list[Path] = []
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            ordered.append(path)
    return ordered


def _strategy_doc_path(strategy_id: str) -> Path:
    ordered = _strategy_doc_candidates(strategy_id)
    for path in ordered:
        if path.exists():
            return path
    return ordered[0] if ordered else Path(get_strategy(strategy_id).documentation_file)



def _extract_strategy_markdown(markdown: str, strategy_id: str) -> str:
    lines = markdown.splitlines()
    header = f"## Active Built-In Strategy: `{strategy_id}`"
    start_idx = -1
    for idx, line in enumerate(lines):
        if line.strip() == header:
            start_idx = idx
            break
    if start_idx < 0:
        return markdown.strip()

    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        if lines[idx].startswith("## ") and lines[idx].strip() != header:
            end_idx = idx
            break
    return "\n".join(lines[start_idx:end_idx]).strip()


def list_available_strategies() -> Dict[str, Any]:
    return {"status": "success", "strategies": list_registered_strategies()}


def get_strategy_document(strategy_id: str = DEFAULT_STRATEGY_ID) -> Dict[str, Any]:
    candidates = _strategy_doc_candidates(strategy_id)
    doc_path = next((p for p in candidates if p.exists()), None)
    if doc_path is None:
        preview = ", ".join(str(p) for p in candidates[:5])
        return {
            "status": "error",
            "strategy_id": strategy_id,
            "title": "Strategy Documentation Missing",
            "markdown": "",
            "message": (
                "Strategy documentation not found. "
                f"Tried (first of {len(candidates)}): {preview}. "
                "Set STOCK_SELECTION_STRATEGIES_PATH to the markdown file, "
                "or TRADER_INTELLIGENCE_PROJECT_ROOT to the repo root, "
                "or include backend/docs/STOCK_SELECTION_STRATEGIES.md in the image."
            ),
        }
    full_text = doc_path.read_text(encoding="utf-8")
    return {
        "status": "success",
        "strategy_id": strategy_id,
        "title": f"Strategy {strategy_id}",
        "markdown": _extract_strategy_markdown(full_text, strategy_id),
        "source_path": str(doc_path),
    }


def run_selection_snapshot(
    max_tickers: int = 800,
    top_n_per_group: int = 10,
    strategy_id: str = DEFAULT_STRATEGY_ID,
) -> Dict[str, Any]:
    strategy = get_strategy(strategy_id)
    generated_at = datetime.utcnow()
    fundamentals = _load_fundamentals(max_tickers=max_tickers)
    if fundamentals.empty:
        return {"status": "error", "message": "No fundamentals available for snapshot generation."}

    tickers = fundamentals["ticker"].dropna().astype(str).str.upper()
    daily = _load_daily_metrics(tickers)
    intraday = _load_intraday_metrics(tickers)
    iv = _load_iv_metrics(tickers)

    feature_frame = build_feature_frame(fundamentals, daily, intraday, iv)
    preprocessed, exclusions = preprocess_feature_frame(feature_frame)
    clustered: ClusterResult = cluster_peers(preprocessed)
    all_exclusions = dict(exclusions)
    for key, value in clustered.exclusions_by_reason.items():
        all_exclusions[key] = all_exclusions.get(key, 0) + value

    if clustered.clustered_frame.empty:
        return {"status": "error", "message": "No eligible stocks after filtering and clustering."}

    grouped = strategy.runner(clustered.clustered_frame, top_n_per_group=top_n_per_group)
    as_of = generated_at.date().isoformat()
    metadata = {
        "as_of": as_of,
        "generated_at": generated_at,
        "model_version": MODEL_VERSION,
        "strategy_id": strategy_id,
        "freshness_minutes": FRESHNESS_TARGET_MINUTES,
        "tickers_considered": int(len(feature_frame)),
        "tickers_ranked": int(len(clustered.clustered_frame)),
        "tickers_excluded": int(len(feature_frame) - len(clustered.clustered_frame)),
        "exclusions_by_reason": all_exclusions,
    }

    snapshot_doc = {
        "as_of": as_of,
        "generated_at": generated_at,
        "model_version": MODEL_VERSION,
        "strategy_id": strategy_id,
        "status": "success",
        "metadata": _sanitize_for_json(metadata),
        "payload_by_mode": _sanitize_for_json(
            {
                "sell_premium": _shape_payload(grouped, metadata, "sell_premium"),
                "buy_premium": _shape_payload(grouped, metadata, "buy_premium"),
            }
        ),
    }
    insert_res = _snapshot_collection().insert_one(snapshot_doc)
    return {
        "status": "success",
        "snapshot_id": str(insert_res.inserted_id),
        "as_of": as_of,
        "strategy_id": strategy_id,
        "tickers_considered": metadata["tickers_considered"],
        "tickers_ranked": metadata["tickers_ranked"],
        "tickers_excluded": metadata["tickers_excluded"],
    }


def get_latest_snapshot(
    view: str = "all",
    mode: str = "sell_premium",
    strategy_id: str = DEFAULT_STRATEGY_ID,
) -> Dict[str, Any]:
    get_strategy(strategy_id)
    doc = _snapshot_collection().find_one(_latest_snapshot_query(strategy_id), sort=[("generated_at", -1)])
    if not doc:
        return {"status": "error", "message": "No cached stock selection snapshot available."}
    payload = (doc.get("payload_by_mode") or {}).get(mode, {})
    if view != "all":
        payload = {
            "metadata": payload.get("metadata"),
            view: payload.get(view, []),
        }
    return {
        "status": "success",
        "view": view,
        "mode": mode,
        "strategy_id": doc.get("strategy_id", DEFAULT_STRATEGY_ID),
        "payload": payload,
    }


def get_snapshot_by_date(
    as_of: str,
    view: str = "all",
    mode: str = "sell_premium",
    strategy_id: str = DEFAULT_STRATEGY_ID,
) -> Dict[str, Any]:
    get_strategy(strategy_id)
    query = {"as_of": as_of}
    query.update(_latest_snapshot_query(strategy_id))
    doc = _snapshot_collection().find_one(query, sort=[("generated_at", -1)])
    if not doc:
        return {"status": "error", "message": f"No snapshot found for as_of={as_of}"}
    payload = (doc.get("payload_by_mode") or {}).get(mode, {})
    if view != "all":
        payload = {
            "metadata": payload.get("metadata"),
            view: payload.get(view, []),
        }
    return {
        "status": "success",
        "view": view,
        "mode": mode,
        "strategy_id": doc.get("strategy_id", DEFAULT_STRATEGY_ID),
        "payload": payload,
    }


def get_health(strategy_id: str = DEFAULT_STRATEGY_ID) -> Dict[str, Any]:
    get_strategy(strategy_id)
    doc = _snapshot_collection().find_one(_latest_snapshot_query(strategy_id), sort=[("generated_at", -1)])
    if not doc:
        return {
            "status": "empty",
            "strategy_id": strategy_id,
            "freshness_target_minutes": FRESHNESS_TARGET_MINUTES,
            "details": {},
        }
    generated_at = doc.get("generated_at")
    if not isinstance(generated_at, datetime):
        return {
            "status": "stale",
            "strategy_id": strategy_id,
            "freshness_target_minutes": FRESHNESS_TARGET_MINUTES,
            "details": {"reason": "invalid_generated_at"},
        }
    age_minutes = int((datetime.utcnow() - generated_at).total_seconds() // 60)
    status = "healthy" if age_minutes <= FRESHNESS_TARGET_MINUTES else "stale"
    return {
        "status": status,
        "strategy_id": doc.get("strategy_id", DEFAULT_STRATEGY_ID),
        "latest_as_of": doc.get("as_of"),
        "generated_at": generated_at,
        "age_minutes": age_minutes,
        "freshness_target_minutes": FRESHNESS_TARGET_MINUTES,
        "details": {"model_version": doc.get("model_version")},
    }


def run_selection_snapshot_if_stale(
    max_age_minutes: int = FRESHNESS_TARGET_MINUTES,
    max_tickers: int = 800,
    top_n_per_group: int = 10,
    strategy_id: str = DEFAULT_STRATEGY_ID,
) -> Dict[str, Any]:
    health = get_health(strategy_id=strategy_id)
    if health.get("status") == "healthy":
        return {"status": "success", "message": "Snapshot is already fresh; no run needed."}
    return run_selection_snapshot(
        max_tickers=max_tickers,
        top_n_per_group=top_n_per_group,
        strategy_id=strategy_id,
    )


def get_ticker_rankings(ticker: str) -> Dict[str, Any]:
    ticker = ticker.strip().upper()
    strategies = list_registered_strategies()
    results = []

    for strategy in strategies:
        strategy_id = strategy.get("strategy_id")
        if not strategy_id:
            continue
            
        doc = _snapshot_collection().find_one(_latest_snapshot_query(strategy_id), sort=[("generated_at", -1)])
        if not doc:
            continue

        payload_by_mode = doc.get("payload_by_mode", {})
        for mode, payload in payload_by_mode.items():
            clusters = payload.get("clusters", [])
            found_in_mode = False
            for cluster in clusters:
                if found_in_mode:
                    break
                stocks = cluster.get("stocks", [])
                for stock in stocks:
                    if stock.get("ticker", "").upper() == ticker:
                        results.append({
                            "strategy_id": strategy_id,
                            "strategy_label": strategy.get("label", strategy_id),
                            "mode": mode,
                            "global_rank": stock.get("global_rank"),
                            "cluster_rank": stock.get("cluster_rank"),
                            "selection_score": stock.get("selection_score"),
                            "confidence_score": stock.get("confidence_score"),
                            "regime_bucket": stock.get("regime_bucket"),
                            "group_label": cluster.get("group_label"),
                        })
                        found_in_mode = True
                        break

    return {
        "status": "success",
        "ticker": ticker,
        "rankings": results
    }

