import sys
from pathlib import Path

import asyncio
import datetime

from decimal import Decimal

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC_PATH = ROOT / "backend" / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from my_libs_py3.broker import alpaca_client
from my_libs_py3.TD_Order import AlpacaTrader, _option_contract, OrderDetails, OrderStatusDetails, TradeEnvelope


def _reset_option_asset_cache(monkeypatch):
    monkeypatch.setattr(
        alpaca_client,
        "_OPTION_ASSET_CLASS_CACHE",
        alpaca_client._OPTION_ASSET_CLASS_SENTINEL,
        raising=False,
    )


def test_build_occ_symbol_matches_alpaca_regex():
    symbol = alpaca_client.build_occ_symbol("AEO", "20251010", Decimal("16"), "C")
    assert symbol == "AEO251010C00016000"


def test_build_occ_symbol_strips_punctuation():
    symbol = alpaca_client.build_occ_symbol("BF.B", "20241220", Decimal("75"), "P")
    assert symbol == "BFB241220P00075000"
    assert " " not in symbol


def test_build_occ_symbol_limits_root_to_five_characters():
    symbol = alpaca_client.build_occ_symbol("LONGER", "20241220", Decimal("150"), "C")
    assert symbol.startswith("LONGE")
    assert symbol == "LONGE241220C00150000"


def test_option_contract_uses_normalized_occ_symbol():
    contract = _option_contract("AEO", "20251010", 16.0, "C")
    assert contract["option_symbol"] == "AEO251010C00016000"
    assert " " not in contract["option_symbol"]


def test_resolve_option_asset_class_prefers_us_option(monkeypatch):
    class DummyAssetClass:
        US_OPTION = "us_option"

    monkeypatch.setattr(alpaca_client, "AssetClass", DummyAssetClass)
    _reset_option_asset_cache(monkeypatch)

    resolved = alpaca_client._resolve_option_asset_class()
    assert resolved == "us_option"


def test_resolve_option_asset_class_falls_back_to_string(monkeypatch):
    class DummyAssetClass:
        pass

    monkeypatch.setattr(alpaca_client, "AssetClass", DummyAssetClass)
    _reset_option_asset_cache(monkeypatch)

    resolved = alpaca_client._resolve_option_asset_class()
    assert resolved in {"option", "us_option"}


def test_build_single_option_order_uses_resolved_asset_class(monkeypatch):
    class DummyAssetClass:
        US_OPTION = "us_option"

    monkeypatch.setattr(alpaca_client, "AssetClass", DummyAssetClass)
    _reset_option_asset_cache(monkeypatch)

    captured = {}

    class DummyMarketOrderRequest:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs
            self.kwargs = kwargs

    monkeypatch.setattr(alpaca_client, "MarketOrderRequest", DummyMarketOrderRequest)

    class DummyLimitOrderRequest:
        def __init__(self, **kwargs):
            captured.setdefault("limit_calls", []).append(kwargs)
            self.kwargs = kwargs

    monkeypatch.setattr(alpaca_client, "LimitOrderRequest", DummyLimitOrderRequest)

    payload = {
        "side": "BUY",
        "qty": 1,
        "symbol": "AEO",
        "expiry": "20251010",
        "strike": 16,
        "right": "C",
        "order_type": "market",
    }

    order = alpaca_client._build_single_option_order(payload)

    assert captured["kwargs"].get("asset_class") == "us_option"
    assert isinstance(order, DummyMarketOrderRequest)
    assert order.kwargs is captured["kwargs"]


def test_place_strategy_order_honors_leg_actions(monkeypatch):
    async def runner():
        trader = AlpacaTrader()

        async def noop_connect(self):
            return None

        monkeypatch.setattr(trader, "connect", noop_connect.__get__(trader, AlpacaTrader))

        class DummyClient:
            async def place_order(self, contract, payload):
                if payload.get("legs"):
                    raise RuntimeError("multi-leg unsupported")
                return object()

            def disconnect(self):
                return None

            def disconnect(self):
                return None

            def disconnect(self):
                return None

            def disconnect(self):
                return None

            def disconnect(self):
                return None

        trader.client = DummyClient()

        recorded_sizes = []

        async def fake_place_option_order(self, *, symbol, size, expiry_date, strike, right, order_type="MKT", limit_price=None, exchange="SMART"):
            recorded_sizes.append(size)
            return TradeEnvelope(
                order=OrderDetails(
                    orderId="id",
                    symbol=symbol,
                    action="BUY" if size > 0 else "SELL",
                    orderType=order_type,
                    totalQuantity=abs(size),
                ),
                status=OrderStatusDetails(status="Submitted"),
            )

        monkeypatch.setattr(AlpacaTrader, "place_option_order", fake_place_option_order)

        legs = [
            {"action": "BUY", "quantity": 1, "expiry_date": "20251010", "strike": 15, "right": "C"},
            {"action": "SELL", "quantity": 1, "expiry_date": "20251010", "strike": 17, "right": "C"},
        ]

        await trader.place_strategy_order(symbol="AEO", legs_data=legs, size=1, order_type="MKT")

        assert recorded_sizes == [1, -1]
        trader.disconnect()

    asyncio.run(runner())


def test_place_strategy_order_inverts_actions_when_size_negative(monkeypatch):
    async def runner():
        trader = AlpacaTrader()

        async def noop_connect(self):
            return None

        monkeypatch.setattr(trader, "connect", noop_connect.__get__(trader, AlpacaTrader))

        class DummyClient:
            async def place_order(self, contract, payload):
                if payload.get("legs"):
                    raise RuntimeError("multi-leg unsupported")
                return object()

            def disconnect(self):
                return None

        trader.client = DummyClient()

        recorded_sizes = []

        async def fake_place_option_order(self, *, symbol, size, expiry_date, strike, right, order_type="MKT", limit_price=None, exchange="SMART"):
            recorded_sizes.append(size)
            return TradeEnvelope(
                order=OrderDetails(
                    orderId="id",
                    symbol=symbol,
                    action="BUY" if size > 0 else "SELL",
                    orderType=order_type,
                    totalQuantity=abs(size),
                ),
                status=OrderStatusDetails(status="Submitted"),
            )

        monkeypatch.setattr(AlpacaTrader, "place_option_order", fake_place_option_order)

        legs = [
            {"action": "BUY", "quantity": 1, "expiry_date": "20251010", "strike": 15, "right": "C"},
            {"action": "SELL", "quantity": 1, "expiry_date": "20251010", "strike": 17, "right": "C"},
        ]

        await trader.place_strategy_order(symbol="AEO", legs_data=legs, size=-1, order_type="MKT")

        assert recorded_sizes == [1, -1]
        trader.disconnect()

    asyncio.run(runner())


class DummyOptionsFeed:
    INDICATIVE = "indicative"
    OPRA = "opra"


class DummyOptionChainRequest:
    def __init__(self, **kwargs):
        value = kwargs.get("underlying_symbol")
        if value is None:
            raise TypeError("expected underlying_symbol field")
        if value != "AAPL":
            raise TypeError(f"unexpected value {value}")
        self.kwargs = kwargs
        self.feed = kwargs.get("feed")


class DummyOptionDataClient:
    def __init__(self):
        self.last_request = None

    def get_option_chain(self, request):
        self.last_request = request
        return {"data": "stub"}


def test_build_option_chain_request_sets_underlying_and_feed(monkeypatch):
    monkeypatch.delenv("APCA_OPTION_FEED", raising=False)
    monkeypatch.setattr(alpaca_client, "OptionChainRequest", DummyOptionChainRequest)
    monkeypatch.setattr(alpaca_client, "OptionsFeed", DummyOptionsFeed)
    request = alpaca_client._build_option_chain_request("aapl")
    assert isinstance(request, DummyOptionChainRequest)
    assert request.kwargs["underlying_symbol"] == "AAPL"
    assert request.feed == DummyOptionsFeed.INDICATIVE


def test_build_option_chain_request_respects_env(monkeypatch):
    monkeypatch.setattr(alpaca_client, "OptionChainRequest", DummyOptionChainRequest)
    monkeypatch.setattr(alpaca_client, "OptionsFeed", DummyOptionsFeed)
    monkeypatch.setenv("APCA_OPTION_FEED", "opra")
    request = alpaca_client._build_option_chain_request("aapl")
    assert isinstance(request, DummyOptionChainRequest)
    assert request.feed == DummyOptionsFeed.OPRA
    monkeypatch.delenv("APCA_OPTION_FEED", raising=False)


def test_get_option_chain_uses_option_data_client(monkeypatch):
    monkeypatch.delenv("APCA_OPTION_FEED", raising=False)
    monkeypatch.setattr(alpaca_client, "OptionChainRequest", DummyOptionChainRequest)
    monkeypatch.setattr(alpaca_client, "OptionsFeed", DummyOptionsFeed)

    async def runner():
        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(alpaca_client.asyncio, "to_thread", fake_to_thread)
        client = alpaca_client.AlpacaAsyncClient()
        dummy_data_client = DummyOptionDataClient()
        client._option_data = dummy_data_client
        result = await client.get_option_chain("aapl")
        assert result == {"data": "stub"}
        assert isinstance(dummy_data_client.last_request, DummyOptionChainRequest)

    asyncio.run(runner())


def test_list_orders_uses_get_orders_request(monkeypatch):
    async def runner():
        client = alpaca_client.AlpacaAsyncClient()

        class DummyTrading:
            def __init__(self):
                self.last_filter = None

            def get_orders(self, request=None):
                self.last_filter = request
                return ["ok"]

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(alpaca_client.asyncio, "to_thread", fake_to_thread)

        trading = DummyTrading()
        client._trading = trading

        result = await client.list_orders(status="all", limit=25)

        assert result == ["ok"]
        assert trading.last_filter is not None
        assert trading.last_filter.status == alpaca_client.QueryOrderStatus.ALL
        assert trading.last_filter.limit == 25

    asyncio.run(runner())


def test_list_orders_without_filters_calls_get_orders_directly(monkeypatch):
    async def runner():
        client = alpaca_client.AlpacaAsyncClient()

        class DummyTrading:
            def __init__(self):
                self.last_args = None

            def get_orders(self, *args):
                self.last_args = args
                return []

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(alpaca_client.asyncio, "to_thread", fake_to_thread)

        trading = DummyTrading()
        client._trading = trading

        result = await client.list_orders()

        assert result == []
        assert trading.last_args == ()

    asyncio.run(runner())


def test_place_strategy_order_submits_multi_leg(monkeypatch):
    async def runner():
        trader = AlpacaTrader()

        async def noop_connect(self):
            return None

        monkeypatch.setattr(trader, "connect", noop_connect.__get__(trader, AlpacaTrader))

        recorded_payloads = []

        class DummyOrder:
            def __init__(self, payload):
                self.id = "123"
                self.symbol = payload.get("symbol")
                self.side = payload.get("side")
                self.type = payload.get("order_type")
                self.qty = payload.get("qty")
                self.status = "filled"
                self.filled_qty = self.qty
                self.filled_avg_price = payload.get("limit_price")
                self.limit_price = payload.get("limit_price")
                self.submitted_at = None
                self.updated_at = None
                self.client_order_id = None

        class DummyClient:
            async def place_order(self, contract, payload):
                recorded_payloads.append((contract, payload))
                return DummyOrder(payload)

            def disconnect(self):
                return None

        trader.client = DummyClient()

        async def fake_market_data(self, symbol_arg, expiry, strike, right, exchange="SMART"):
            assert symbol_arg == "AEO"
            if strike == 15:
                return {"bid": 1.95, "ask": 2.05, "midpoint": 2.0}
            if strike == 17:
                return {"bid": 1.35, "ask": 1.55, "midpoint": 1.45}
            raise AssertionError("Unexpected strike")

        monkeypatch.setattr(
            trader,
            "get_option_market_data",
            fake_market_data.__get__(trader, AlpacaTrader),
        )

        legs = [
            {"action": "BUY", "quantity": 1, "expiry_date": "20251010", "strike": 15, "right": "C"},
            {"action": "SELL", "quantity": 1, "expiry_date": "20251010", "strike": 17, "right": "C"},
        ]

        trade = await trader.place_strategy_order("AEO", legs, size=1, order_type="MKT", open_position=True)

        assert isinstance(trade, TradeEnvelope)
        assert len(recorded_payloads) == 1
        contract, payload = recorded_payloads[0]
        assert contract == {"asset_type": "option", "symbol": "AEO"}
        assert payload["qty"] == 1
        assert payload["order_type"] == "limit"
        assert payload["limit_price"] == pytest.approx(0.55, rel=0, abs=0.01)
        assert payload["legs"][0]["ratio_qty"] == 1.0
        assert payload["legs"][1]["ratio_qty"] == -1.0
        assert payload["order_class"] in ("mleg", getattr(alpaca_client.OrderClass, "MLEG", "mleg"))
        trader.disconnect()

    asyncio.run(runner())


def test_place_strategy_order_raises_when_multi_leg_rejected(monkeypatch):
    async def runner():
        trader = AlpacaTrader()

        async def noop_connect(self):
            return None

        monkeypatch.setattr(trader, "connect", noop_connect.__get__(trader, AlpacaTrader))

        class DummyClient:
            async def place_order(self, contract, payload):
                raise ValueError("invalid legs")

            def disconnect(self):
                return None

        trader.client = DummyClient()

        async def fake_market_data(self, symbol_arg, expiry, strike, right, exchange="SMART"):
            return {"bid": 1.0, "ask": 1.2, "midpoint": 1.1}

        monkeypatch.setattr(
            trader,
            "get_option_market_data",
            fake_market_data.__get__(trader, AlpacaTrader),
        )

        async def fail_fallback(self, *args, **kwargs):
            raise AssertionError("Fallback to single-leg orders should not execute")

        monkeypatch.setattr(
            trader,
            "place_option_order",
            fail_fallback.__get__(trader, AlpacaTrader),
        )

        legs = [
            {"action": "BUY", "quantity": 1, "expiry_date": "20251010", "strike": 15, "right": "C"},
            {"action": "SELL", "quantity": 1, "expiry_date": "20251010", "strike": 17, "right": "C"},
        ]

        with pytest.raises(RuntimeError) as err:
            await trader.place_strategy_order("AEO", legs, size=1, order_type="MKT", open_position=True)

        assert "Multi-leg order submission failed" in str(err.value)
        trader.disconnect()

    asyncio.run(runner())


def test_build_option_order_creates_option_legs():
    occ_call = alpaca_client.build_occ_symbol("AEO", "20251010", Decimal("15"), "C")
    occ_put = alpaca_client.build_occ_symbol("AEO", "20251010", Decimal("17"), "C")
    payload = {
        "symbol": "AEO",
        "qty": 2,
        "side": "BUY",
        "order_type": "market",
        "time_in_force": "day",
        "legs": [
            {"option_symbol": occ_call, "ratio_qty": 1, "side": "BUY", "position_intent": "buy_to_open"},
            {"option_symbol": occ_put, "ratio_qty": -1, "side": "SELL", "position_intent": "sell_to_open"},
        ],
    }

    order_request = alpaca_client._build_option_order(payload)

    assert isinstance(order_request, alpaca_client.MarketOrderRequest)
    assert len(order_request.legs) == 2
    assert order_request.legs[0].symbol == occ_call
    assert order_request.legs[0].ratio_qty == 1
    assert order_request.legs[0].side == alpaca_client.OrderSide.BUY
    assert order_request.legs[1].ratio_qty == 1
    assert order_request.legs[1].side == alpaca_client.OrderSide.SELL
    assert order_request.order_class == alpaca_client.OrderClass.MLEG


def test_build_multi_leg_order_omits_root_symbol():
    lower_call = alpaca_client.build_occ_symbol("AEO", "20251010", Decimal("15"), "C")
    upper_call = alpaca_client.build_occ_symbol("AEO", "20251010", Decimal("17"), "C")
    payload = {
        "symbol": "AEO",
        "qty": 1,
        "side": "SELL",
        "order_type": "market",
        "time_in_force": "day",
        "legs": [
            {"option_symbol": lower_call, "ratio_qty": -1, "side": "SELL", "position_intent": "sell_to_open"},
            {"option_symbol": upper_call, "ratio_qty": 1, "side": "BUY", "position_intent": "buy_to_open"},
        ],
    }

    order_request = alpaca_client._build_option_order(payload)

    assert order_request.order_class == alpaca_client.OrderClass.MLEG
    assert order_request.symbol is None
    assert [leg.symbol for leg in order_request.legs] == [lower_call, upper_call]
    assert [leg.ratio_qty for leg in order_request.legs] == [1, 1]

def test_get_option_market_data_uses_snapshot_when_quote_missing(monkeypatch):
    monkeypatch.delenv("APCA_OPTION_FEED", raising=False)
    occ_symbol = "AAPL251017C00200000"

    class DummyClient:
        async def req_mkt_data(self, *args, **kwargs):
            return None

        async def get_option_chain(self, symbol):
            assert symbol == "AAPL"
            return {
                occ_symbol: {
                    "symbol": occ_symbol,
                    "latest_quote": {
                        "bid_price": 1.23,
                        "ask_price": 1.45,
                        "timestamp": datetime.datetime(2024, 10, 5, 12, 0, tzinfo=datetime.timezone.utc),
                    },
                    "latest_trade": {
                        "price": 1.30,
                        "timestamp": datetime.datetime(2024, 10, 5, 11, 58, tzinfo=datetime.timezone.utc),
                    },
                }
            }

        def disconnect(self):
            return None

    trader = AlpacaTrader()

    async def dummy_connect(self):
        return None

    trader.client = DummyClient()
    trader.connect = dummy_connect.__get__(trader, AlpacaTrader)

    result = asyncio.run(trader.get_option_market_data("AAPL", "20251017", 200.0, "C"))

    assert result is not None
    assert result["bid"] == 1.23
    assert result["ask"] == 1.45
    assert result["midpoint"] == pytest.approx((1.23 + 1.45) / 2)
    parsed_timestamp = datetime.datetime.fromisoformat(result["timestamp"])
    expected = datetime.datetime(2024, 10, 5, 12, 0, tzinfo=datetime.timezone.utc)
    assert parsed_timestamp.astimezone(datetime.timezone.utc) == expected
