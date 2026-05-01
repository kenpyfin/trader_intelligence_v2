"""Alpaca implementation of the AsyncBrokerClient abstraction."""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from alpaca.data.enums import OptionsFeed
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import (
    OptionBarsRequest,
    OptionChainRequest,
    OptionLatestQuoteRequest,
    StockBarsRequest,
    StockLatestQuoteRequest,
)
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, OrderClass, OrderSide, PositionIntent, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, LimitOrderRequest, MarketOrderRequest, OptionLegRequest

from .base import AsyncBrokerClient


@dataclass
class AccountValue:
    account: str
    tag: str
    value: Any
    currency: str


_OPTION_ASSET_CLASS_SENTINEL = object()
_OPTION_ASSET_CLASS_CACHE: Any = _OPTION_ASSET_CLASS_SENTINEL


class AlpacaAsyncClient(AsyncBrokerClient):
    """Thin asynchronous wrapper around alpaca-py trading and data clients."""

    backend = "alpaca"

    def __init__(self) -> None:
        self._key_id = os.getenv("APCA_API_KEY_ID")
        self._secret_key = os.getenv("APCA_API_SECRET_KEY")
        self._base_url = os.getenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
        # If not set, use sandbox data URL when trading base is paper (match paper keys)
        _base = (self._base_url or "").lower()
        if os.getenv("APCA_DATA_BASE_URL"):
            self._data_url = os.getenv("APCA_DATA_BASE_URL")
        elif "paper" in _base or "sandbox" in _base:
            self._data_url = "https://data.sandbox.alpaca.markets"
        else:
            self._data_url = "https://data.alpaca.markets"
        self._trading: Optional[TradingClient] = None
        self._stock_data: Optional[StockHistoricalDataClient] = None
        self._option_data: Optional[OptionHistoricalDataClient] = None
        self._connect_lock = asyncio.Lock()

    async def connect(self, host: str, port: int, clientId: int, timeout: int, account: str = None, readonly: bool = False) -> None:
        del host, port, clientId, timeout, account, readonly  # Unused, kept for interface compatibility
        if self._trading is not None:
            return
        async with self._connect_lock:
            if self._trading is not None:
                return
            if not self._key_id or not self._secret_key:
                raise RuntimeError("Alpaca credentials are not set in environment variables.")
            # Alpaca uses separate trading and market data domains; store both client handles.
            self._trading = _create_trading_client(self._key_id, self._secret_key, self._is_paper(), self._base_url)
            self._stock_data = _create_stock_data_client(self._key_id, self._secret_key, self._data_url)
            self._option_data = _create_option_data_client(self._key_id, self._secret_key, self._data_url)

    def disconnect(self) -> None:
        self._trading = None
        self._stock_data = None
        self._option_data = None

    def is_connected(self) -> bool:
        return self._trading is not None

    async def account_summary(self) -> List[AccountValue]:
        self._ensure_connected()
        account = await asyncio.to_thread(self._trading.get_account)  # type: ignore[arg-type]
        currency = getattr(account, "currency", "USD")
        portfolio_value = _as_float(getattr(account, "portfolio_value", None) or getattr(account, "equity", 0))
        unrealized = _as_float(getattr(account, "unrealized_pl", 0))
        buying_power = _as_float(getattr(account, "buying_power", getattr(account, "cash", 0)))
        return [
            AccountValue(account="All", tag="NetLiquidationByCurrency", value=str(portfolio_value), currency=currency),
            AccountValue(account="All", tag="UnrealizedPnL", value=str(unrealized), currency=currency),
            AccountValue(account="All", tag="AvailableFunds", value=str(buying_power), currency=currency),
        ]

    async def req_positions(self) -> List[Dict[str, Any]]:
        self._ensure_connected()
        positions = await asyncio.to_thread(self._trading.get_all_positions)  # type: ignore[arg-type]
        return [_model_to_dict(pos) for pos in positions]

    async def qualify_contracts(self, contract: Any):
        # Alpaca does not require explicit qualification; pass through the contract metadata.
        return contract

    async def place_order(self, contract: Any, order: Any):
        self._ensure_connected()
        payload = _merge_contract_order(contract, order)
        asset_type = payload.get("asset_type")
        if asset_type == "stock":
            order_request = _build_stock_order(payload)
            return await asyncio.to_thread(self._trading.submit_order, order_data=order_request)  # type: ignore[arg-type]
        if asset_type == "option":
            order_request = _build_option_order(payload)
            return await asyncio.to_thread(self._trading.submit_order, order_data=order_request)  # type: ignore[arg-type]
        raise ValueError(f"Unsupported asset_type '{asset_type}' for Alpaca order placement.")

    async def cancel_order(self, order: Any):
        self._ensure_connected()
        order_id = getattr(order, "id", None) or getattr(order, "order_id", None) or order
        if not order_id:
            raise ValueError("cancel_order requires an order identifier.")
        await asyncio.to_thread(self._trading.cancel_order_by_id, str(order_id))

    async def req_mkt_data(self, contract: Any, genericTickList: str, snapshot: bool, regulatorySnapshot: bool):
        del genericTickList, snapshot, regulatorySnapshot
        asset_type = getattr(contract, "asset_type", None) or contract.get("asset_type")
        symbol = getattr(contract, "symbol", None) or contract.get("symbol")
        if not asset_type or not symbol:
            raise ValueError("Market data requests require contract asset_type and symbol.")
        if asset_type == "stock":
            if self._stock_data is None:
                raise RuntimeError("Stock data client is not initialized.")
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            result = await asyncio.to_thread(self._stock_data.get_stock_latest_quote, request)
            return result.get(symbol)
        if asset_type == "option":
            if self._option_data is None:
                raise RuntimeError("Option data client is not initialized.")
            option_symbol = contract.get("option_symbol") or build_occ_symbol(
                symbol,
                contract["expiry"],
                Decimal(str(contract["strike"])) if "strike" in contract else Decimal("0"),
                contract["right"],
            )
            request = OptionLatestQuoteRequest(symbol_or_symbols=option_symbol)
            result = await asyncio.to_thread(self._option_data.get_option_latest_quote, request)
            return result.get(option_symbol)
        raise ValueError(f"Unsupported asset_type '{asset_type}' for market data request.")

    async def cancel_mkt_data(self, contract: Any):
        del contract  # No streaming subscriptions to cancel in the HTTP API.
        return None

    async def req_historical_data(self, contract: Any, **kwargs):
        self._ensure_connected()
        asset_type = getattr(contract, "asset_type", None) or contract.get("asset_type")
        symbol = getattr(contract, "symbol", None) or contract.get("symbol")
        timeframe = kwargs.get("timeframe") or kwargs.get("barSizeSetting", "1 day")
        limit = kwargs.get("limit") or kwargs.get("barLimit", 100)
        if asset_type == "stock":
            if self._stock_data is None:
                raise RuntimeError("Stock data client is not initialized.")
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=_to_timeframe(timeframe),
                limit=limit,
            )
            bars = await asyncio.to_thread(self._stock_data.get_stock_bars, request)
            return bars.get(symbol, [])
        if asset_type == "option":
            if self._option_data is None:
                raise RuntimeError("Option data client is not initialized.")
            option_symbol = contract.get("option_symbol") or build_occ_symbol(
                symbol,
                contract["expiry"],
                Decimal(str(contract["strike"])) if "strike" in contract else Decimal("0"),
                contract["right"],
            )
            request = OptionBarsRequest(
                symbol_or_symbols=option_symbol,
                timeframe=_to_timeframe(timeframe),
                limit=limit,
            )
            bars = await asyncio.to_thread(self._option_data.get_option_bars, request)
            return bars.get(option_symbol, [])
        raise ValueError(f"Unsupported asset_type '{asset_type}' for historical data request.")

    async def get_order_by_id(self, order_id: str):
        self._ensure_connected()
        return await asyncio.to_thread(self._trading.get_order_by_id, str(order_id))

    async def list_orders(self, status: Optional[str] = None, limit: Optional[int] = None):
        self._ensure_connected()
        request_obj = None
        request_kwargs: Dict[str, Any] = {}
        if status:
            status_normalized = str(status).upper()
            status_enum = QueryOrderStatus.__members__.get(status_normalized)
            if status_enum is None:
                try:
                    status_enum = QueryOrderStatus(str(status).lower())
                except Exception:
                    status_enum = None
            if status_enum is not None:
                request_kwargs["status"] = status_enum
        if limit is not None:
            try:
                request_kwargs["limit"] = int(limit)
            except (TypeError, ValueError):
                pass
        if request_kwargs:
            request_obj = GetOrdersRequest(**request_kwargs)
        if request_obj is not None:
            return await asyncio.to_thread(self._trading.get_orders, request_obj)
        return await asyncio.to_thread(self._trading.get_orders)

    async def get_option_chain(
        self,
        symbol: str,
        expiration_date_gte: Optional[str] = None,
        expiration_date_lte: Optional[str] = None,
    ):
        """Fetch option chain snapshots, optionally filtered by expiration date range."""
        if self._option_data is None:
            raise RuntimeError("Option data client is not initialized.")
        request = _build_option_chain_request(
            symbol,
            expiration_date_gte=expiration_date_gte,
            expiration_date_lte=expiration_date_lte,
        )
        return await asyncio.to_thread(self._option_data.get_option_chain, request)

    def _is_paper(self) -> bool:
        return "paper" in self._base_url

    def _ensure_connected(self) -> None:
        if self._trading is None:
            raise RuntimeError("Alpaca client is not connected. Call connect() first.")


def _model_to_dict(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()  # type: ignore[return-value]
    if hasattr(model, "_raw"):
        raw = getattr(model, "_raw")
        if isinstance(raw, dict):
            return raw
    return {k: getattr(model, k) for k in dir(model) if not k.startswith("_") and not callable(getattr(model, k))}


def _create_trading_client(api_key: str, secret_key: str, paper: bool, base_url: str) -> TradingClient:
    attempts = []
    if base_url:
        attempts.append({"args": (api_key, secret_key), "kwargs": {"paper": paper, "base_url": base_url}})
        attempts.append({"args": (), "kwargs": {"api_key": api_key, "secret_key": secret_key, "paper": paper, "base_url": base_url}})
    attempts.append({"args": (api_key, secret_key), "kwargs": {"paper": paper}})
    attempts.append({"args": (), "kwargs": {"api_key": api_key, "secret_key": secret_key, "paper": paper}})
    attempts.append({"args": (api_key, secret_key), "kwargs": {}})
    attempts.append({"args": (), "kwargs": {"api_key": api_key, "secret_key": secret_key}})

    last_error: Optional[Exception] = None
    for attempt in attempts:
        try:
            return TradingClient(*attempt["args"], **attempt["kwargs"])
        except TypeError as err:
            last_error = err
            continue
    raise RuntimeError(f"Unable to instantiate TradingClient with the provided parameters: {last_error}")


def _create_stock_data_client(api_key: str, secret_key: str, base_url: str) -> StockHistoricalDataClient:
    attempts = []
    if base_url:
        attempts.append({"args": (api_key, secret_key), "kwargs": {"base_url": base_url}})
        attempts.append({"args": (), "kwargs": {"api_key": api_key, "secret_key": secret_key, "base_url": base_url}})
    attempts.append({"args": (api_key, secret_key), "kwargs": {}})
    attempts.append({"args": (), "kwargs": {"api_key": api_key, "secret_key": secret_key}})
    attempts.append({"args": (), "kwargs": {}})

    last_error: Optional[Exception] = None
    for attempt in attempts:
        try:
            return StockHistoricalDataClient(*attempt["args"], **attempt["kwargs"])
        except TypeError as err:
            last_error = err
            continue
    raise RuntimeError(f"Unable to instantiate StockHistoricalDataClient with the provided parameters: {last_error}")


def _create_option_data_client(api_key: str, secret_key: str, base_url: str) -> OptionHistoricalDataClient:
    attempts = []
    if base_url:
        attempts.append({"args": (api_key, secret_key), "kwargs": {"base_url": base_url}})
        attempts.append({"args": (), "kwargs": {"api_key": api_key, "secret_key": secret_key, "base_url": base_url}})
    attempts.append({"args": (api_key, secret_key), "kwargs": {}})
    attempts.append({"args": (), "kwargs": {"api_key": api_key, "secret_key": secret_key}})
    attempts.append({"args": (), "kwargs": {}})

    last_error: Optional[Exception] = None
    for attempt in attempts:
        try:
            return OptionHistoricalDataClient(*attempt["args"], **attempt["kwargs"])
        except TypeError as err:
            last_error = err
            continue
    raise RuntimeError(f"Unable to instantiate OptionHistoricalDataClient with the provided parameters: {last_error}")


def _merge_contract_order(contract: Any, order: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if isinstance(contract, dict):
        payload.update(contract)
    elif hasattr(contract, "__dict__"):
        payload.update({k: v for k, v in vars(contract).items() if not k.startswith("_")})
    if isinstance(order, dict):
        payload.update(order)
    elif hasattr(order, "__dict__"):
        payload.update({k: v for k, v in vars(order).items() if not k.startswith("_")})
    return payload


def _resolve_option_chain_feed():
    env_value = (os.getenv("APCA_OPTION_FEED") or "").strip().lower()
    feed_map = {
        "indicative": getattr(OptionsFeed, "INDICATIVE", None),
        "opra": getattr(OptionsFeed, "OPRA", None),
    }
    if env_value:
        feed = feed_map.get(env_value)
        if feed is not None:
            return feed
    default_feed = feed_map.get("indicative")
    if default_feed is not None:
        return default_feed
    if env_value:
        return env_value
    for value in feed_map.values():
        if value is not None:
            return value
    return None


def _normalize_expiry_for_api(expiry: str) -> str:
    """Convert expiry to YYYY-MM-DD for Alpaca API."""
    expiry = expiry.strip().replace("-", "")
    if len(expiry) == 8 and expiry.isdigit():
        return f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:8]}"
    if len(expiry) == 6 and expiry.isdigit():
        return f"20{expiry[:2]}-{expiry[2:4]}-{expiry[4:6]}"
    return expiry


def _build_option_chain_request(
    symbol: str,
    expiration_date_gte: Optional[str] = None,
    expiration_date_lte: Optional[str] = None,
) -> OptionChainRequest:
    symbol_upper = symbol.upper()
    feed = _resolve_option_chain_feed()
    kwargs: Dict[str, Any] = {"underlying_symbol": symbol_upper}
    if feed is not None:
        kwargs["feed"] = feed
    if expiration_date_gte:
        kwargs["expiration_date_gte"] = _normalize_expiry_for_api(expiration_date_gte)
    if expiration_date_lte:
        kwargs["expiration_date_lte"] = _normalize_expiry_for_api(expiration_date_lte)

    try:
        request = OptionChainRequest(**kwargs)
        if feed is not None and getattr(request, "feed", None) in (None, ""):
            try:
                request.feed = feed
            except Exception:
                pass
        return request
    except Exception as err:
        raise RuntimeError(
            f"Unable to construct OptionChainRequest for symbol {symbol_upper}: {err}"
        )


def _build_stock_order(payload: Dict[str, Any]) -> Any:
    side = _to_order_side(payload.get("side") or payload.get("action"))
    qty = payload.get("qty") or payload.get("quantity") or payload.get("size")
    if qty is None:
        raise ValueError("Stock order payload requires quantity/qty/size field.")
    qty_value = float(qty)
    symbol = payload.get("symbol")
    if not symbol:
        raise ValueError("Stock order payload requires symbol field.")
    tif = _to_time_in_force(payload.get("time_in_force") or payload.get("tif") or "day")
    order_type = (payload.get("order_type") or payload.get("type") or "market").lower()
    if order_type == "market":
        return MarketOrderRequest(symbol=symbol, qty=qty_value, side=side, time_in_force=tif)
    if order_type == "limit":
        limit_price = payload.get("limit_price") or payload.get("price")
        if limit_price is None:
            raise ValueError("Limit order payload requires limit_price.")
        return LimitOrderRequest(symbol=symbol, qty=qty_value, side=side, time_in_force=tif, limit_price=float(limit_price))
    raise ValueError(f"Unsupported stock order type '{order_type}'.")


def _build_option_order(payload: Dict[str, Any]) -> Any:
    if payload.get("legs"):
        return _build_multi_option_order(payload)
    return _build_single_option_order(payload)


def _build_multi_option_order(payload: Dict[str, Any]) -> Any:
    legs_payload = payload.get("legs")
    if not legs_payload:
        raise ValueError("Multi-leg option orders require a non-empty legs list.")

    symbol = payload.get("symbol")
    if not symbol:
        raise ValueError("Option order payload requires symbol field.")
    qty_value = payload.get("qty") or payload.get("quantity") or payload.get("size")
    if qty_value is None:
        raise ValueError("Option order payload requires qty for multi-leg orders.")
    qty_float = float(qty_value)
    if qty_float <= 0:
        raise ValueError("Strategy quantity must be positive.")

    tif = _to_time_in_force(payload.get("time_in_force") or payload.get("tif") or "day")
    side_value = payload.get("side") or payload.get("action")
    if not side_value:
        raise ValueError("Multi-leg option orders require a side (BUY/SELL).")

    legs = _build_option_legs(legs_payload)

    asset_class_value = _resolve_option_asset_class()
    order_type = (payload.get("order_type") or payload.get("type") or "market").lower()

    # Alpaca rejects mleg submissions when a root symbol is provided; omit it here.
    base_kwargs: Dict[str, Any] = {
        "qty": qty_float,
        "side": _to_order_side(side_value),
        "time_in_force": tif,
        "legs": legs,
        "order_class": OrderClass.MLEG,
    }

    if order_type == "market":
        return _build_option_request(MarketOrderRequest, base_kwargs, asset_class_value)
    if order_type == "limit":
        limit_price = payload.get("limit_price") or payload.get("price")
        if limit_price is None:
            raise ValueError("Limit option order payload requires limit_price.")
        base_kwargs["limit_price"] = float(limit_price)
        return _build_option_request(LimitOrderRequest, base_kwargs, asset_class_value)
    raise ValueError(f"Unsupported option order type '{order_type}'.")


def _build_option_legs(legs_payload: Sequence[Dict[str, Any]]) -> List[OptionLegRequest]:
    legs: List[OptionLegRequest] = []
    for leg in legs_payload:
        option_symbol = leg.get("option_symbol")
        if not option_symbol:
            expiry = leg.get("expiry") or leg.get("expiry_date")
            strike = leg.get("strike")
            right = leg.get("right")
            underlying = leg.get("symbol")
            if not all([underlying, expiry, strike, right]):
                raise ValueError("Each multi-leg entry requires option_symbol or (symbol, expiry, strike, right).")
            option_symbol = build_occ_symbol(underlying, expiry, Decimal(str(strike)), right)

        ratio_qty = leg.get("ratio_qty")
        if ratio_qty is None:
            raise ValueError("Each leg requires ratio_qty field.")
        ratio_value = float(ratio_qty)
        if ratio_value == 0:
            continue
        ratio_float = abs(ratio_value)
        # Alpaca requires ratio_qty > 0; encode direction via leg side.

        side_value = leg.get("side")
        if not side_value:
            side_value = "SELL" if ratio_value < 0 else "BUY"
        side_enum = _to_order_side(side_value) if side_value else None

        position_intent_value = leg.get("position_intent")
        position_intent_enum = _to_position_intent(position_intent_value) if position_intent_value else None

        legs.append(
            OptionLegRequest(
                symbol=option_symbol,
                ratio_qty=ratio_float,
                side=side_enum,
                position_intent=position_intent_enum,
            )
        )

    if not legs:
        raise ValueError("Multi-leg order requires at least one non-zero ratio leg.")
    return legs


def _build_single_option_order(payload: Dict[str, Any]) -> Any:
    side = _to_order_side(payload.get("side") or payload.get("action"))
    qty = payload.get("qty") or payload.get("quantity") or payload.get("size")
    if qty is None:
        raise ValueError("Option order payload requires quantity/qty/size field.")
    qty_value = int(round(float(qty)))
    symbol = payload.get("symbol")
    expiry = payload.get("expiry") or payload.get("expiration")
    strike = payload.get("strike")
    right = payload.get("right") or payload.get("option_type")
    if not all([symbol, expiry, strike, right]):
        raise ValueError("Option order payload requires symbol, expiry, strike, and right fields.")
    occ_symbol = payload.get("option_symbol") or build_occ_symbol(symbol, expiry, Decimal(str(strike)), right)
    tif = _to_time_in_force(payload.get("time_in_force") or payload.get("tif") or "day")
    order_type = (payload.get("order_type") or payload.get("type") or "market").lower()
    asset_class_value = _resolve_option_asset_class()
    if order_type == "market":
        base_kwargs = {"symbol": occ_symbol, "qty": qty_value, "side": side, "time_in_force": tif}
        return _build_option_request(MarketOrderRequest, base_kwargs, asset_class_value)
    if order_type == "limit":
        limit_price = payload.get("limit_price") or payload.get("price")
        if limit_price is None:
            raise ValueError("Limit option order payload requires limit_price.")
        base_kwargs = {
            "symbol": occ_symbol,
            "qty": qty_value,
            "side": side,
            "time_in_force": tif,
            "limit_price": float(limit_price),
        }
        return _build_option_request(LimitOrderRequest, base_kwargs, asset_class_value)
    raise ValueError(f"Unsupported option order type '{order_type}'.")


def _build_option_request(factory, base_kwargs: Dict[str, Any], asset_class_value: Any):
    kwargs_with_asset = dict(base_kwargs)
    if asset_class_value is not None:
        kwargs_with_asset["asset_class"] = asset_class_value
    try:
        return factory(**kwargs_with_asset)
    except (TypeError, ValueError):
        request = factory(**base_kwargs)
        _attach_option_asset_class(request, asset_class_value)
        return request


def _resolve_option_asset_class() -> Any:
    global _OPTION_ASSET_CLASS_CACHE
    if _OPTION_ASSET_CLASS_CACHE is not _OPTION_ASSET_CLASS_SENTINEL:
        return _OPTION_ASSET_CLASS_CACHE
    for attr in ("OPTION", "OPTIONS", "US_OPTION"):
        value = getattr(AssetClass, attr, None)
        if value is not None:
            _OPTION_ASSET_CLASS_CACHE = value
            return value
    for fallback in ("option", "us_option"):
        _OPTION_ASSET_CLASS_CACHE = fallback
        return fallback
    _OPTION_ASSET_CLASS_CACHE = None
    return None


def _attach_option_asset_class(order_request: Any, asset_class_value: Any) -> None:
    if asset_class_value is None:
        return
    for attr in ("asset_class", "assetClass"):
        try:
            setattr(order_request, attr, asset_class_value)
            return
        except Exception:
            continue


def build_occ_symbol(symbol: str, expiry: str, strike: Decimal, right: str) -> str:
    right_char = right.upper()[0]
    if right_char not in {"C", "P"}:
        raise ValueError("Option right must be 'C' or 'P'.")
    expiry_clean = _normalize_expiry(expiry)
    strike_int = int(strike * 1000)
    strike_field = f"{strike_int:08d}"
    root = _normalize_underlying_root(symbol)
    return f"{root}{expiry_clean}{right_char}{strike_field}"


def _normalize_underlying_root(symbol: str) -> str:
    cleaned = "".join(ch for ch in symbol.upper() if ch.isalpha())
    if not cleaned:
        raise ValueError("Underlying symbol must include at least one letter.")
    return cleaned[:5]


def _normalize_expiry(expiry: str) -> str:
    expiry = expiry.strip()
    if len(expiry) == 8 and expiry.isdigit():  # YYYYMMDD
        return expiry[2:]
    if len(expiry) == 6 and expiry.isdigit():  # YYMMDD
        return expiry
    raise ValueError("Expiry must be in YYYYMMDD or YYMMDD format.")


def _to_order_side(value: Any) -> OrderSide:
    if isinstance(value, OrderSide):
        return value
    normalized = str(value).upper()
    if normalized == "BUY":
        return OrderSide.BUY
    if normalized == "SELL":
        return OrderSide.SELL
    raise ValueError(f"Unsupported order side '{value}'.")


def _to_time_in_force(value: Any) -> TimeInForce:
    if isinstance(value, TimeInForce):
        return value
    normalized = str(value).upper()
    if normalized in {"DAY", "DAYTIME"}:
        return TimeInForce.DAY
    if normalized == "GTC":
        return TimeInForce.GTC
    if normalized == "IOC":
        return TimeInForce.IOC
    if normalized == "FOK":
        return TimeInForce.FOK
    # Alpaca defaults to DAY when unspecified.
    return TimeInForce.DAY


def _to_timeframe(value: Any) -> TimeFrame:
    if isinstance(value, TimeFrame):
        return value
    normalized = str(value).lower()
    mapping = {
        "1 min": TimeFrame.Minute,
        "1min": TimeFrame.Minute,
        "minute": TimeFrame.Minute,
        "5 min": TimeFrame.FiveMinutes,
        "15 min": TimeFrame.FifteenMinutes,
        "30 min": TimeFrame.ThirtyMinutes,
        "1 hour": TimeFrame.Hour,
        "hour": TimeFrame.Hour,
        "day": TimeFrame.Day,
        "1 day": TimeFrame.Day,
        "daily": TimeFrame.Day,
    }
    return mapping.get(normalized, TimeFrame.Day)


def _to_position_intent(value: Any) -> PositionIntent:
    if isinstance(value, PositionIntent):
        return value
    normalized = str(value).upper()
    mapping = {
        "BUY_TO_OPEN": PositionIntent.BUY_TO_OPEN,
        "BUY-TO-OPEN": PositionIntent.BUY_TO_OPEN,
        "BUY_TO_CLOSE": PositionIntent.BUY_TO_CLOSE,
        "BUY-TO-CLOSE": PositionIntent.BUY_TO_CLOSE,
        "SELL_TO_OPEN": PositionIntent.SELL_TO_OPEN,
        "SELL-TO-OPEN": PositionIntent.SELL_TO_OPEN,
        "SELL_TO_CLOSE": PositionIntent.SELL_TO_CLOSE,
        "SELL-TO-CLOSE": PositionIntent.SELL_TO_CLOSE,
    }
    intent = mapping.get(normalized)
    if intent is None:
        raise ValueError(f"Unsupported position_intent '{value}'.")
    return intent


def _as_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
