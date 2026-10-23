from __future__ import annotations

import asyncio
import atexit
import os
import time
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import pandas as pd

from .broker.alpaca_client import AlpacaAsyncClient, build_occ_symbol
from .iv_from_alpaca import calculate_iv_points_from_alpaca_chain

TIMEOUT = int(os.getenv("ALPACA_ORDER_TIMEOUT", "60"))
DEFAULT_TIF = os.getenv("ALPACA_DEFAULT_TIME_IN_FORCE", "day")


@dataclass
class OrderDetails:
    orderId: str
    symbol: str
    action: str
    orderType: str
    totalQuantity: float
    limitPrice: Optional[float] = None
    clientOrderId: Optional[str] = None


@dataclass
class OrderStatusDetails:
    status: str
    filled: float = 0.0
    remaining: float = 0.0
    avgFillPrice: Optional[float] = None
    submittedAt: Optional[str] = None
    updatedAt: Optional[str] = None


class TradeEnvelope:
    def __init__(self, order: OrderDetails, status: OrderStatusDetails, raw: Any = None) -> None:
        self.order = order
        self.orderStatus = status
        self.raw = raw
        self.order_ids = [order.orderId]


class StrategyEnvelope:
    def __init__(self, trades: List[TradeEnvelope]) -> None:
        self.trades = trades
        self.order = trades[0].order if trades else None
        self.raw = [t.raw for t in trades]
        self.order_ids = [t.order.orderId for t in trades]
        self.orderStatus = _aggregate_status([t.orderStatus for t in trades])


class AlpacaTrader:
    def __init__(self) -> None:
        self.client = AlpacaAsyncClient()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._connect_lock = asyncio.Lock()
        atexit.register(self.disconnect)

    async def connect(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            self._loop = loop
        if self.client.is_connected():
            return
        async with self._connect_lock:
            if self.client.is_connected():
                return
            await self.client.connect(host="", port=0, clientId=0, timeout=0)

    def disconnect(self) -> None:
        self.client.disconnect()

    async def get_available_fund(self) -> float:
        summary = await self.get_account_summary()
        for item in summary:
            if item.tag == "AvailableFunds":
                try:
                    return float(item.value)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    async def get_account_summary(self):
        await self.connect()
        return await self.client.account_summary()

    async def get_account_details(self) -> Dict[str, Optional[float]]:
        """
        Fetches key financial metrics from the account summary.
        """
        await self.connect()
        summary_obj = await self.get_account_summary()
        print(f"DEBUG(TD_Order): Received account summary from broker: {summary_obj}")

        if not isinstance(summary_obj, list):
            # Fallback for Alpaca's direct object response
            equity = _maybe_float(getattr(summary_obj, "equity", None))
            last_equity = _maybe_float(getattr(summary_obj, "last_equity", None))
            pnl_today = None
            if equity is not None and last_equity is not None:
                pnl_today = equity - last_equity
            return {
                "total_account_value": equity,
                "pnl_today": pnl_today,
                "unrealized_pnl": _maybe_float(getattr(summary_obj, "unrealized_pl", None)),
                "realized_pnl_today": _maybe_float(getattr(summary_obj, "realized_pl", None)),
                "available_cash": _maybe_float(getattr(summary_obj, "cash", None)),
                "buying_power": _maybe_float(getattr(summary_obj, "buying_power", None)),
            }

        # Handle IBKR-style list of AccountValue objects
        summary_map = {
            item.tag: _maybe_float(item.value)
            for item in summary_obj
            if hasattr(item, "tag") and hasattr(item, "value")
        }

        equity = summary_map.get("Equity")
        last_equity = summary_map.get("PreviousEquity")
        pnl_today = None
        if equity is not None and last_equity is not None:
            pnl_today = equity - last_equity

        # Map known tags to our expected dictionary keys
        return {
            "total_account_value": summary_map.get("NetLiquidationByCurrency") or summary_map.get("NetLiquidation"),
            "pnl_today": pnl_today,
            "unrealized_pnl": summary_map.get("UnrealizedPnL"),
            "realized_pnl_today": summary_map.get("RealizedPnL"),
            "available_cash": summary_map.get("AvailableFunds"),
            "buying_power": summary_map.get("BuyingPower"),
        }

    async def get_position_by_symbol(self, symbol) -> float:
        await self.connect()
        positions = await self.client.req_positions()
        symbol_upper = symbol.upper()
        for pos in positions:
            asset_class = pos.get("asset_class") or pos.get("assetClass")
            pos_symbol = pos.get("symbol") or ""
            if asset_class in ("us_option", "option"):
                parsed = _parse_occ_symbol(pos_symbol)
                base_symbol = parsed.get("underlying", "")
            else:
                base_symbol = pos_symbol
            if base_symbol.upper() == symbol_upper:
                return _to_float(pos.get("qty") or pos.get("quantity") or pos.get("position"))
        return 0.0

    async def place_forex_market_order(self, symbol, size):
        raise NotImplementedError("Alpaca does not support spot forex trading via the trading API.")

    async def place_stock_market_order(self, symbol, size):
        await self.connect()
        action = "BUY" if size >= 0 else "SELL"
        quantity = abs(float(size))
        contract = _stock_contract(symbol)
        order_payload = {
            "asset_type": "stock",
            "order_type": "market",
            "side": action,
            "qty": quantity,
            "time_in_force": DEFAULT_TIF,
        }
        order_obj = await self.client.place_order(contract, order_payload)
        return _alpaca_order_to_trade(order_obj)

    async def place_stock_limit_order(self, symbol, size, limit_price):
        await self.connect()
        if limit_price is None:
            raise ValueError("Limit price is required for stock limit orders.")
        action = "BUY" if size > 0 else "SELL"
        quantity = abs(float(size))
        contract = _stock_contract(symbol)
        order_payload = {
            "asset_type": "stock",
            "order_type": "limit",
            "side": action,
            "qty": quantity,
            "limit_price": float(limit_price),
            "time_in_force": DEFAULT_TIF,
        }
        order_obj = await self.client.place_order(contract, order_payload)
        return _alpaca_order_to_trade(order_obj)

    async def place_option_order(
        self,
        symbol: str,
        size: int,
        expiry_date: str,
        strike: float,
        right: str,
        order_type: str = "MKT",
        limit_price: float = None,
        exchange: str = "SMART",
    ):
        del exchange
        await self.connect()
        action = "BUY" if size > 0 else "SELL"
        quantity = abs(int(size))
        order_kind = order_type.upper()
        final_limit = limit_price
        if order_kind == "MKT" and final_limit is None:
            market_price = await self.get_current_price(symbol, "OPT", expiry_date, strike, right)
            if market_price:
                final_limit = round(market_price, 2)
                order_kind = "LMT"
        contract = _option_contract(symbol, expiry_date, strike, right)
        order_payload = {
            "asset_type": "option",
            "order_type": "market" if order_kind == "MKT" else "limit",
            "side": action,
            "qty": quantity,
            "limit_price": float(final_limit) if final_limit is not None else None,
            "time_in_force": DEFAULT_TIF,
        }
        if order_payload["order_type"] == "limit" and order_payload["limit_price"] is None:
            raise ValueError("Limit price is required for limit option orders.")
        order_obj = await self.client.place_order(contract, order_payload)
        return _alpaca_order_to_trade(order_obj)

    async def place_strategy_order(
        self,
        symbol: str,
        legs_data: list,
        size: int,
        order_type: str = "MKT",
        limit_price: float = None,
        exchange: str = "SMART",
        open_position: bool = True,
    ):
        del exchange
        if not legs_data:
            raise ValueError("Strategy legs cannot be empty.")
        contracts: List[TradeEnvelope] = []
        order_kind = order_type.upper()
        final_limit = limit_price
        absolute_size = abs(int(size))
        if absolute_size == 0:
            raise ValueError("Strategy size must be non-zero.")

        sell_tokens: Set[str] = {"SELL", "SHORT", "WRITE"}
        buy_tokens: Set[str] = {"BUY", "LONG"}

        option_leg_specs: List[Dict[str, Any]] = []
        stock_leg_specs: List[Dict[str, Any]] = []

        for leg in legs_data:
            base_qty = int(leg.get("quantity", 1))
            if base_qty == 0:
                continue
            leg_action = str(leg.get("action", "BUY")).upper()
            if leg_action not in sell_tokens and leg_action not in buy_tokens:
                raise ValueError(f"Unsupported leg action '{leg_action}'.")
            leg_sign = -1 if leg_action in sell_tokens else 1
            per_leg_qty = int(base_qty * absolute_size * leg_sign)
            if per_leg_qty == 0:
                continue

            sec_type = leg.get("secType", "OPT")
            if sec_type == "STK":
                stock_leg_specs.append(
                    {
                        "per_leg_qty": per_leg_qty,
                        "action": leg_action,
                    }
                )
                continue

            expiry = leg.get("expiry_date") or leg.get("expiry")
            strike = leg.get("strike")
            right = leg.get("right")

            if not all([expiry, strike, right]):
                raise ValueError("Each option leg requires expiry, strike, and right fields.")
            occ_symbol = leg.get("option_symbol") or build_occ_symbol(symbol, expiry, _to_decimal(strike), right)
            ratio_qty = float(base_qty * leg_sign)
            position_intent = _leg_position_intent(open_position=open_position, leg_sign=leg_sign)
            option_leg_specs.append(
                {
                    "occ_symbol": occ_symbol,
                    "ratio_qty": ratio_qty,
                    "per_leg_qty": per_leg_qty,
                    "expiry": expiry,
                    "strike": strike,
                    "right": right,
                    "action": leg_action,
                    "position_intent": position_intent,
                }
            )

        if not option_leg_specs and not stock_leg_specs:
            raise ValueError("No executable legs were produced for strategy order.")

        # Alpaca multi-leg orders only support options. If stock is involved, submit individually.
        use_multi_leg_order = len(option_leg_specs) > 1 and not stock_leg_specs
        if use_multi_leg_order:
            order_side = _strategy_side_from_legs(option_leg_specs, size)
            multi_contract = {"asset_type": "option", "symbol": symbol.upper()}
            multi_payload: Dict[str, Any] = {
                "asset_type": "option",
                "order_type": "limit",
                "side": order_side,
                "qty": absolute_size,
                "time_in_force": DEFAULT_TIF,
                "order_class": "mleg",
                "legs": [
                    {
                        "option_symbol": spec["occ_symbol"],
                        "ratio_qty": spec["ratio_qty"],
                        "side": spec["action"],
                        "position_intent": spec["position_intent"],
                    }
                    for spec in option_leg_specs
                ],
            }
            if final_limit is None:
                final_limit = await self._derive_strategy_limit_price(symbol, option_leg_specs)
            if final_limit is None:
                raise RuntimeError("Unable to determine limit price for multi-leg strategy order.")
            multi_payload["limit_price"] = float(final_limit)

            try:
                order_obj = await self.client.place_order(multi_contract, multi_payload)
                return _alpaca_order_to_trade(order_obj)
            except Exception as exc:
                raise RuntimeError(f"Multi-leg order submission failed: {exc}") from exc

        # Fallback to individual orders if not a pure multi-leg option strategy
        for spec in stock_leg_specs:
            trade = await self.place_stock_market_order(symbol=symbol, size=spec["per_leg_qty"])
            contracts.append(trade)

        for spec in option_leg_specs:
            trade = await self.place_option_order(
                symbol=symbol,
                size=spec["per_leg_qty"],
                expiry_date=spec["expiry"],
                strike=spec["strike"],
                right=spec["right"],
                order_type=order_type,
                limit_price=limit_price,
            )
            contracts.append(trade)

        if len(contracts) == 1:
            return contracts[0]
        return StrategyEnvelope(contracts)

    async def _derive_strategy_limit_price(self, symbol: str, leg_specs: Sequence[Dict[str, Any]]) -> Optional[float]:
        total_value = 0.0
        observed = False
        for spec in leg_specs:
            ratio = float(spec.get("ratio_qty", 0.0))
            if ratio == 0:
                continue
            observed = True
            market_data = await self.get_option_market_data(symbol, spec["expiry"], spec["strike"], spec["right"])
            if not market_data:
                return None
            bid = _maybe_float(market_data.get("bid"))
            ask = _maybe_float(market_data.get("ask"))
            midpoint = _maybe_float(market_data.get("midpoint"))
            leg_price = _select_leg_price(midpoint, bid, ask, ratio)
            if leg_price is None:
                return None
            total_value += leg_price * ratio
        if not observed:
            return None
        return round(abs(total_value), 2)

    async def wait_for_order_fill(self, trade, timeout=TIMEOUT, cancel_on_timeout: bool = False):
        await self.connect()
        order_ids = getattr(trade, "order_ids", None)
        if not order_ids:
            order_ids = [trade.order.orderId]
        start = time.time()
        while True:
            refreshed = []
            for oid in order_ids:
                refreshed.append(await self.client.get_order_by_id(oid))
            _update_trade_structure(trade, refreshed)
            if _all_terminal(refreshed):
                return trade.orderStatus.status
            if (time.time() - start) > timeout:
                if cancel_on_timeout:
                    for oid in order_ids:
                        try:
                            await self.client.cancel_order(oid)
                        except Exception:
                            pass
                return trade.orderStatus.status
            await asyncio.sleep(1)

    async def open_positions_symbol(self):
        positions_df = await self.open_positions()
        if positions_df.empty:
            return []
        return positions_df["symbol"].dropna().unique().tolist()

    async def open_positions(self):
        await self.connect()
        positions = await self.client.req_positions()
        normalized = [_normalize_position(p) for p in positions]
        if not normalized:
            return pd.DataFrame()
        return pd.DataFrame(normalized)

    async def get_stock_market_prices(self, symbols: Sequence[str]) -> Dict[str, Optional[float]]:
        """Batch last-sale / snapshot market prices (Alpaca `get_stock_snapshot`)."""
        await self.connect()
        if not symbols:
            return {}
        return await self.client.get_stock_market_prices(symbols)

    async def get_option_expirations(self, symbol: str):
        await self.connect()
        chain = await self.client.get_option_chain(symbol)
        print(f"DEBUG(TD_Order): get_option_chain for expirations returned object of type {type(chain)}")
        expirations = _extract_expiration_list(chain)
        print(f"DEBUG(TD_Order): Extracted {len(expirations)} unique expirations for {symbol}.")
        return sorted(expirations)

    async def realtimequote(self, ticker):
        return await self.get_current_price(ticker, "STK")

    async def get_current_price(
        self,
        symbol: str,
        contract_type: str = "STK",
        expiry_date: str = None,
        strike: float = None,
        right: str = None,
        exchange: str = "SMART",
    ):
        del exchange
        await self.connect()
        if contract_type.upper() == "STK":
            contract = _stock_contract(symbol)
        elif contract_type.upper() == "OPT":
            if not all([expiry_date, strike, right]):
                raise ValueError("Options require expiry_date, strike, and right.")
            contract = _option_contract(symbol, expiry_date, strike, right)
        else:
            raise ValueError(f"Unsupported contract type {contract_type}.")
        quote = await self.client.req_mkt_data(contract, "", True, False)
        price = _quote_to_price(quote)
        if price is not None:
            return price
        bars = await self.client.req_historical_data(contract, timeframe="1 day", limit=5)
        if bars:
            last_bar = bars[-1]
            close = getattr(last_bar, "close", None)
            if close is not None:
                try:
                    return float(close)
                except (TypeError, ValueError):
                    pass
        return None

    async def get_option_market_data(self, symbol: str, expiry_date: str, strike: float, right: str, exchange: str = "SMART"):
        del exchange
        await self.connect()
        contract = _option_contract(symbol, expiry_date, strike, right)
        quote = await self.client.req_mkt_data(contract, "", True, False)
        fallback_quote: Dict[str, Any] = {}
        fallback_trade: Dict[str, Any] = {}
        occ_symbol = contract["option_symbol"]
        if quote is None:
            chain = await self.client.get_option_chain(symbol)
            if isinstance(chain, dict):
                normalized_occ = occ_symbol.replace(" ", "")
                snapshot = chain.get(occ_symbol) or chain.get(normalized_occ)
                if snapshot is None:
                    snapshot = next(
                        (
                            payload
                            for payload in chain.values()
                            if isinstance(payload, dict)
                            and (payload.get("symbol") in {occ_symbol, normalized_occ})
                        ),
                        None,
                    )
                if snapshot:
                    latest_quote = getattr(snapshot, 'latest_quote', None)
                    latest_trade = getattr(snapshot, 'latest_trade', None)
                    if latest_quote:
                        fallback_quote = {
                            "bid_price": getattr(latest_quote, 'bid_price', None),
                            "ask_price": getattr(latest_quote, 'ask_price', None),
                            "midpoint": getattr(latest_quote, 'midpoint', None),
                            "timestamp": getattr(latest_quote, 'timestamp', None),
                        }
                    if latest_trade:
                        fallback_trade = {
                            "price": getattr(latest_trade, 'price', None),
                            "timestamp": getattr(latest_trade, 'timestamp', None),
                        }

        bid = getattr(quote, "bid_price", None) if quote is not None else None
        ask = getattr(quote, "ask_price", None) if quote is not None else None
        midpoint = getattr(quote, "midpoint", None) if quote is not None else None
        timestamp = getattr(quote, "timestamp", None) if quote is not None else None

        if bid is None:
            bid = fallback_quote.get("bid_price")
        if ask is None:
            ask = fallback_quote.get("ask_price")
        if midpoint is None and bid is not None and ask is not None:
            midpoint = (float(bid) + float(ask)) / 2
        if midpoint is None:
            midpoint = fallback_quote.get("midpoint") or fallback_trade.get("price")
        if timestamp is None:
            timestamp = fallback_quote.get("timestamp") or fallback_trade.get("timestamp")

        if bid is None and ask is None and midpoint is None:
            return None

        return {
            "bid": bid,
            "ask": ask,
            "midpoint": midpoint,
            "timestamp": _to_iso(timestamp),
        }

    async def cancel_order(self, trade):
        await self.connect()
        if trade is None:
            return
        order_ids = getattr(trade, "order_ids", None)
        if not order_ids and getattr(trade, "order", None):
            order_ids = [trade.order.orderId]
        if not order_ids:
            raise ValueError("Trade does not include order identifiers.")
        for oid in order_ids:
            try:
                await self.client.cancel_order(oid)
            except Exception:
                pass

    async def get_recent_orders(self, count=10):
        await self.connect()
        orders = await self.client.list_orders(status="all", limit=count)
        envelopes = [_alpaca_order_to_trade(order) for order in orders]
        return [_trade_to_summary_dict(env) for env in envelopes]

    async def get_historical_data_df(self, symbol: str, start: str, end: str, timeframe: str = "1Day") -> pd.DataFrame:
        """
        Fetches historical data from Alpaca and returns a pandas DataFrame.
        """
        await self.connect()
        contract = _stock_contract(symbol)
        
        # This assumes the underlying client supports start/end, which is standard.
        bars = await self.client.req_historical_data(
            contract, start=start, end=end, timeframe=timeframe
        )

        if not bars:
            return pd.DataFrame()

        # Convert bars to DataFrame, assuming standard bar attributes (t, o, h, l, c, v)
        # The Alpaca V2 API returns t, o, h, l, c, v, n, vw.
        df = pd.DataFrame([
            {
                "TimeStamp": getattr(bar, 't', None),
                "Open": getattr(bar, 'o', None),
                "High": getattr(bar, 'h', None),
                "Low": getattr(bar, 'l', None),
                "Close": getattr(bar, 'c', None),
                "Volume": getattr(bar, 'v', None),
            } for bar in bars
        ])
        
        if not df.empty and 'TimeStamp' in df.columns:
            # The timestamp is typically timezone-aware (UTC) from Alpaca
            df['TimeStamp'] = pd.to_datetime(df['TimeStamp'])
        
        return df

    async def get_option_chain_df(self, symbol: str, expiration_date: str) -> pd.DataFrame:
        """
        Fetches the option chain for a specific expiration date from Alpaca
        and returns it as a pandas DataFrame.
        Uses server-side expiration filter to ensure the requested expiry is in the first page.
        """
        await self.connect()
        norm_expiration = _normalize_expiry(expiration_date).replace("-", "")
        chain = await self.client.get_option_chain(
            symbol,
            expiration_date_gte=norm_expiration,
            expiration_date_lte=norm_expiration,
        )
        if not isinstance(chain, dict):
            print(f"DEBUG(TD_Order): get_option_chain for {symbol} returned non-dict: {type(chain)}")
            return pd.DataFrame()

        print(f"DEBUG(TD_Order): Received raw chain for {symbol} with {len(chain)} contracts.")
        rows = []
        print(f"DEBUG(TD_Order): Filtering for expiration date {norm_expiration}...")

        match_count = 0
        for occ_symbol, snapshot in chain.items():
            parsed = _parse_occ_symbol(occ_symbol)
            if parsed.get("expiry") != norm_expiration:
                continue

            match_count += 1
            quote = getattr(snapshot, "latest_quote", None)
            trade = getattr(snapshot, "latest_trade", None)

            row = {
                "Strike": parsed.get("strike"),
                "Type": "call" if parsed.get("right") == "C" else "put",
                "Bid": _maybe_float(getattr(quote, "bid_price", None)),
                "Ask": _maybe_float(getattr(quote, "ask_price", None)),
                "Last Trade": _maybe_float(getattr(trade, "price", None)),
                "option_symbol": occ_symbol,
            }
            rows.append(row)

        print(f"DEBUG(TD_Order): Found {match_count} contracts for {symbol} matching expiration {norm_expiration}.")
        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows)

    def _run_sync(self, coro):
        """Run async coroutine from sync context (works in Jupyter or script)."""
        try:
            asyncio.get_running_loop()
            # Already in async context: run in a new thread to avoid blocking
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        except RuntimeError:
            return asyncio.run(coro)

    def get_spot_price_from_data_api(self, symbol: str) -> Optional[float]:
        """
        Sync wrapper: fetch spot price from Alpaca Data API (stock latest quote).
        Used by the IV pipeline; same data source as option chain for calculating IV.
        """
        try:
            return self._run_sync(self.get_current_price(symbol, "STK"))
        except Exception:
            return None

    def calculate_iv_points_from_data_api(
        self,
        symbol: str,
        risk_free_rate: float = 0.05,
    ) -> Optional[Dict[str, float]]:
        """
        Compute IV points (spot, 7d, 30d, 90d) from Alpaca option chain + spot.
        Alpaca does not provide IV; we back it out from option prices via binomial pricer.
        Same mechanism can be saved to MongoDB for IV rank in trader intelligence.
        """
        async def _get_spot_and_chain():
            await self.connect()
            spot = await self.get_current_price(symbol, "STK")
            if spot is None or spot <= 0:
                return None, None
            chain = await self.client.get_option_chain(symbol)
            return spot, chain

        try:
            spot, chain = self._run_sync(_get_spot_and_chain())
        except Exception:
            return None
        if spot is None or not isinstance(chain, dict):
            return None
        return calculate_iv_points_from_alpaca_chain(
            chain, float(spot), risk_free_rate=risk_free_rate
        )


IBTrader = AlpacaTrader


def _stock_contract(symbol: str) -> Dict[str, Any]:
    return {"asset_type": "stock", "symbol": symbol.upper()}


def _option_contract(symbol: str, expiry: str, strike: float, right: str) -> Dict[str, Any]:
    occ = build_occ_symbol(symbol, expiry, _to_decimal(strike), right)
    return {
        "asset_type": "option",
        "symbol": symbol.upper(),
        "expiry": _normalize_expiry(expiry),
        "strike": float(strike),
        "right": right.upper()[0],
        "option_symbol": occ,
    }


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _parse_occ_symbol(symbol: str) -> Dict[str, Any]:
    if not symbol:
        return {"underlying": "", "expiry": "", "right": "", "strike": 0.0}
    cleaned = symbol.replace(" ", "")
    if len(cleaned) < 15:
        return {"underlying": symbol.strip(), "expiry": "", "right": "", "strike": 0.0}
    first_digit = next((idx for idx, ch in enumerate(cleaned) if ch.isdigit()), None)
    if first_digit is None or len(cleaned) < first_digit + 15:
        return {"underlying": symbol.strip(), "expiry": "", "right": "", "strike": 0.0}
    root = symbol[:first_digit].strip()
    expiry_segment = cleaned[first_digit : first_digit + 6]
    right = cleaned[first_digit + 6].upper()
    strike_segment = cleaned[first_digit + 7 : first_digit + 15]
    try:
        strike = int(strike_segment) / 1000.0
    except ValueError:
        strike = 0.0
    if expiry_segment.isdigit():
        year, month, day = expiry_segment[:2], expiry_segment[2:4], expiry_segment[4:6]
        expiry_fmt = f"20{year}{month}{day}"
    else:
        expiry_fmt = ""
    return {"underlying": root, "expiry": expiry_fmt, "right": right, "strike": strike}


def _normalize_position(raw: Dict[str, Any]) -> Dict[str, Any]:
    asset_class = raw.get("asset_class") or raw.get("assetClass")
    unrealized_pnl = _maybe_float(
        raw.get("unrealized_pl")
        or raw.get("unrealizedPnl")
        or raw.get("unrealized_pnl")
        or raw.get("unrealizedPNL")
    )
    base = {
        "account": raw.get("account_id") or raw.get("account"),
        "exchange": raw.get("exchange") or "ALPACA",
        "currency": raw.get("currency") or "USD",
        "localSymbol": raw.get("symbol"),
        "position": _to_float(raw.get("qty") or raw.get("quantity") or raw.get("position")),
        "avgCost": _maybe_float(raw.get("avg_entry_price") or raw.get("avgPrice")),
        "marketValue": _maybe_float(raw.get("market_value")),
        "unrealizedPNL": unrealized_pnl,
    }
    if asset_class in ("us_option", "option"):
        parsed = _parse_occ_symbol(raw.get("symbol", ""))
        base.update(
            {
                "contract_type": "Option",
                "symbol": parsed["underlying"],
                "tradingClass": parsed["underlying"],
                "strike": parsed["strike"],
                "right": parsed["right"],
                "expiry": parsed["expiry"],
            }
        )
    else:
        base.update(
            {
                "contract_type": "Stock",
                "symbol": (raw.get("symbol") or "").upper(),
                "tradingClass": (raw.get("symbol") or "").upper(),
            }
        )
    return base


def _strategy_side_from_legs(leg_specs: Sequence[Dict[str, Any]], size: int) -> str:
    net = sum(float(spec.get("ratio_qty", 0.0)) for spec in leg_specs)
    if net > 1e-9:
        return "BUY"
    if net < -1e-9:
        return "SELL"
    return "BUY" if size >= 0 else "SELL"


def _select_leg_price(midpoint: Optional[float], bid: Optional[float], ask: Optional[float], ratio: float) -> Optional[float]:
    if midpoint is not None:
        return midpoint
    direction = 1 if ratio > 0 else -1
    if direction > 0:
        for candidate in (ask, bid):
            if candidate is not None:
                return float(candidate)
    else:
        for candidate in (bid, ask):
            if candidate is not None:
                return float(candidate)
    return None


def _leg_position_intent(open_position: bool, leg_sign: int) -> str:
    if open_position:
        return "buy_to_open" if leg_sign > 0 else "sell_to_open"
    return "buy_to_close" if leg_sign > 0 else "sell_to_close"


def _aggregate_status(statuses: Sequence[OrderStatusDetails]) -> OrderStatusDetails:
    if not statuses:
        return OrderStatusDetails(status="Unknown")
    normalized = [s.status.lower() for s in statuses]
    if all(s in ("filled", "complete") for s in normalized):
        combined = "Filled"
    elif any(s in ("cancelled", "canceled", "expired", "rejected") for s in normalized):
        combined = "Cancelled"
    elif any(s in ("partiallyfilled", "partially_filled", "partial") for s in normalized):
        combined = "PartiallyFilled"
    else:
        combined = "Submitted"
    filled = sum(s.filled for s in statuses)
    remaining = sum(max(s.remaining, 0.0) for s in statuses)
    avg = _weighted_average([s.avgFillPrice for s in statuses], [s.filled for s in statuses])
    submitted = next((s.submittedAt for s in statuses if s.submittedAt), None)
    updated = next((s.updatedAt for s in statuses if s.updatedAt), None)
    return OrderStatusDetails(
        status=combined,
        filled=filled,
        remaining=remaining,
        avgFillPrice=avg,
        submittedAt=submitted,
        updatedAt=updated,
    )


def _weighted_average(values: Sequence[Optional[float]], weights: Sequence[float]) -> Optional[float]:
    numerator = 0.0
    denominator = 0.0
    for value, weight in zip(values, weights):
        if value is None or weight is None:
            continue
        numerator += value * weight
        denominator += weight
    if denominator == 0:
        return None
    return numerator / denominator


def _alpaca_order_to_trade(order_obj: Any) -> TradeEnvelope:
    order_id = str(getattr(order_obj, "id", getattr(order_obj, "order_id", "")))
    symbol = getattr(order_obj, "symbol", "")
    side = str(getattr(order_obj, "side", "")).upper()
    order_type = str(getattr(order_obj, "type", "")).upper()
    qty = _to_float(getattr(order_obj, "qty", getattr(order_obj, "quantity", 0)))
    limit_price = _maybe_float(getattr(order_obj, "limit_price", None) or getattr(order_obj, "limit", None))
    filled_qty = _to_float(getattr(order_obj, "filled_qty", 0))
    avg_price = _maybe_float(getattr(order_obj, "filled_avg_price", None))
    status_value = _normalize_status(str(getattr(order_obj, "status", "")))
    submitted_at = _to_iso(getattr(order_obj, "submitted_at", None))
    updated_at = _to_iso(getattr(order_obj, "updated_at", None))
    details = OrderDetails(
        orderId=order_id,
        symbol=symbol,
        action=side or "BUY",
        orderType=order_type or "MARKET",
        totalQuantity=qty,
        limitPrice=limit_price,
        clientOrderId=getattr(order_obj, "client_order_id", None),
    )
    status = OrderStatusDetails(
        status=status_value,
        filled=filled_qty,
        remaining=max(qty - filled_qty, 0.0),
        avgFillPrice=avg_price,
        submittedAt=submitted_at,
        updatedAt=updated_at,
    )
    return TradeEnvelope(details, status, raw=order_obj)


def _normalize_status(status: str) -> str:
    normalized = status.lower()
    mapping = {
        "new": "Submitted",
        "pending_new": "Submitted",
        "accepted": "Submitted",
        "partially_filled": "PartiallyFilled",
        "partiallyfilled": "PartiallyFilled",
        "filled": "Filled",
        "done_for_day": "Filled",
        "canceled": "Cancelled",
        "cancelled": "Cancelled",
        "expired": "Cancelled",
        "rejected": "Rejected",
    }
    return mapping.get(normalized, status.capitalize() if status else "Unknown")


def _quote_to_price(quote: Any) -> Optional[float]:
    if quote is None:
        return None
    for attr in ("last_price", "last", "close", "midpoint", "price"):
        value = getattr(quote, attr, None)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    bid = getattr(quote, "bid_price", None)
    ask = getattr(quote, "ask_price", None)
    try:
        if bid is not None and ask is not None:
            return (float(bid) + float(ask)) / 2.0
    except (TypeError, ValueError):
        pass
    return None


def _update_trade_structure(trade: Any, refreshed_orders: Sequence[Any]) -> None:
    if isinstance(trade, StrategyEnvelope):
        existing = {t.order.orderId: t for t in trade.trades}
        for order_obj in refreshed_orders:
            updated = _alpaca_order_to_trade(order_obj)
            target = existing.get(updated.order.orderId)
            if target:
                target.order = updated.order
                target.orderStatus = updated.orderStatus
                target.raw = updated.raw
            else:
                trade.trades.append(updated)
        trade.orderStatus = _aggregate_status([t.orderStatus for t in trade.trades])
        trade.order_ids = [t.order.orderId for t in trade.trades]
    else:
        updated = _alpaca_order_to_trade(refreshed_orders[0])
        trade.order = updated.order
        trade.orderStatus = updated.orderStatus
        trade.raw = updated.raw
        trade.order_ids = [updated.order.orderId]


def _all_terminal(orders: Sequence[Any]) -> bool:
    terminal = {"filled", "cancelled", "canceled", "expired", "rejected", "done_for_day"}
    for order_obj in orders:
        status = str(getattr(order_obj, "status", "")).lower()
        if status not in terminal:
            return False
    return True


def _to_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _maybe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone().isoformat()
    text = str(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone().isoformat()
    except ValueError:
        return text


def _normalize_expiry(expiry: str) -> str:
    """
    Normalizes an expiration date string to YYYY-MM-DD format.
    Accepts YYYYMMDD, YYMMDD, and YYYY-MM-DD.
    """
    expiry_str = (expiry or "").strip()
    
    # If it contains dashes, assume it's YYYY-MM-DD and validate it.
    if '-' in expiry_str:
        try:
            datetime.strptime(expiry_str, '%Y-%m-%d')
            return expiry_str
        except ValueError:
            # Fall through to the final error if it's not a valid format
            pass

    # Handle YYYYMMDD
    if len(expiry_str) == 8 and expiry_str.isdigit():
        return f"{expiry_str[:4]}-{expiry_str[4:6]}-{expiry_str[6:]}"
    
    # Handle YYMMDD
    if len(expiry_str) == 6 and expiry_str.isdigit():
        return f"20{expiry_str[:2]}-{expiry_str[2:4]}-{expiry_str[4:]}"
    
    raise ValueError(f"Invalid expiry format: '{expiry}'. Expected YYYYMMDD, YYMMDD, or YYYY-MM-DD.")


def _trade_to_summary_dict(trade: TradeEnvelope) -> Dict[str, Any]:
    symbol = trade.order.symbol
    entry = {
        "symbol": symbol,
        "secType": "OPT" if _looks_like_occ(symbol) else "STK",
        "action": trade.order.action,
        "quantity": trade.order.totalQuantity,
        "orderType": trade.order.orderType,
        "status": trade.orderStatus.status,
        "filled": trade.orderStatus.filled,
        "avgFillPrice": trade.orderStatus.avgFillPrice,
        "lastFillTime": trade.orderStatus.updatedAt,
        "description": symbol,
        "orderId": trade.order.orderId,
        "clientOrderId": trade.order.clientOrderId,
    }
    if entry["secType"] == "OPT":
        parsed = _parse_occ_symbol(symbol)
        entry["description"] = f"{parsed['expiry']} {parsed['strike']} {parsed['right']}"
    return entry


def _looks_like_occ(symbol: str) -> bool:
    if not symbol:
        return False
    cleaned = symbol.replace(" ", "")
    if len(cleaned) < 15:
        return False
    first_digit = next((idx for idx, ch in enumerate(cleaned) if ch.isdigit()), None)
    if first_digit is None or len(cleaned) < first_digit + 15:
        return False
    expiry_segment = cleaned[first_digit : first_digit + 6]
    right_segment = cleaned[first_digit + 6]
    strike_segment = cleaned[first_digit + 7 : first_digit + 15]
    return expiry_segment.isdigit() and right_segment in {"C", "P"} and strike_segment.isdigit()


def _extract_expiration_list(chain: Any) -> Set[str]:
    """
    Extracts unique expiration dates (YYYYMMDD) from an Alpaca option chain response.
    The response is expected to be a dictionary where keys are OCC symbols.
    """
    expirations: Set[str] = set()
    if not isinstance(chain, dict):
        return expirations

    for occ_symbol in chain.keys():
        parsed = _parse_occ_symbol(occ_symbol)
        expiry = parsed.get("expiry")
        if expiry:
            expirations.add(expiry)

    return expirations
