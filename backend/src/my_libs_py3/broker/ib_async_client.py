import asyncio
import inspect
from typing import Any

from .base import AsyncBrokerClient


class IBAsyncAsyncClient(AsyncBrokerClient):
    def __init__(self) -> None:
        try:
            from ib_async import IB as AsyncIB  # type: ignore
        except Exception as e:
            raise ImportError("ib_async is not installed or failed to import") from e
        self._AsyncIB = AsyncIB
        self.ib = AsyncIB()
        self.backend = "ib_async"
        # Import ibapi for contract/order conversions
        from ibapi.contract import Contract as IBAPIContract, ComboLeg as IBAPIComboLeg  # type: ignore
        from ibapi.order import Order as IBAPIOrder  # type: ignore
        self._IBAPIContract = IBAPIContract
        self._IBAPIComboLeg = IBAPIComboLeg
        self._IBAPIOrder = IBAPIOrder

    # --- Converters from ib_insync to ibapi ---
    def _to_ibapi_contract(self, c: Any):
        if c is None:
            return None
        if isinstance(c, self._IBAPIContract):
            return c
        cc = self._IBAPIContract()
        # secType
        secType = getattr(c, 'secType', None)
        if not secType:
            name = type(c).__name__.upper()
            secType = {
                'STOCK': 'STK', 'STK': 'STK',
                'FOREX': 'CASH', 'CASH': 'CASH', 'FX': 'CASH',
                'OPTION': 'OPT', 'OPT': 'OPT',
                'INDEX': 'IND', 'IND': 'IND',
                'BAG': 'BAG'
            }.get(name, 'STK')
        cc.secType = secType
        for attr in ('symbol', 'exchange', 'currency', 'localSymbol', 'tradingClass', 'lastTradeDateOrContractMonth', 'multiplier'):
            v = getattr(c, attr, None)
            if v not in (None, ''):
                setattr(cc, attr, v)
        strike = getattr(c, 'strike', None)
        if strike not in (None, ''):
            try:
                cc.strike = float(strike)
            except Exception:
                pass
        right = getattr(c, 'right', None)
        if right:
            cc.right = right
        conId = getattr(c, 'conId', None)
        if conId:
            try:
                cc.conId = int(conId)
            except Exception:
                pass
        comboLegs = getattr(c, 'comboLegs', None)
        if comboLegs:
            legs = []
            for leg in comboLegs:
                l = self._IBAPIComboLeg()
                for a in ('conId', 'ratio', 'action', 'exchange'):
                    v = getattr(leg, a, None)
                    if v not in (None, ''):
                        setattr(l, a, v)
                legs.append(l)
            cc.comboLegs = legs
        if not getattr(cc, 'currency', None):
            cc.currency = 'USD'
        if cc.secType == 'CASH' and not getattr(cc, 'exchange', None):
            cc.exchange = 'IDEALPRO'
        if not getattr(cc, 'exchange', None):
            cc.exchange = 'SMART'
        return cc

    def _to_ibapi_order(self, o: Any):
        if o is None:
            return None
        if isinstance(o, self._IBAPIOrder):
            return o
        order = self._IBAPIOrder()
        action = getattr(o, 'action', None)
        if action:
            order.action = action
        qty = getattr(o, 'totalQuantity', getattr(o, 'quantity', None))
        if qty is not None:
            try:
                order.totalQuantity = int(qty)
            except Exception:
                order.totalQuantity = qty
        otype = getattr(o, 'orderType', None)
        if not otype:
            name = type(o).__name__.upper()
            otype = 'MKT' if name == 'MARKETORDER' else ('LMT' if name == 'LIMITORDER' else 'MKT')
        order.orderType = otype
        lmt = getattr(o, 'lmtPrice', getattr(o, 'limitPrice', None))
        if lmt not in (None, ''):
            order.lmtPrice = float(lmt)
        tif = getattr(o, 'tif', None)
        if tif:
            order.tif = tif
        minQty = getattr(o, 'minQty', None)
        if minQty not in (None, 0):
            try:
                order.minQty = int(minQty)
            except Exception:
                order.minQty = minQty
        return order

    # --- Async methods ---
    async def connect(self, host: str, port: int, clientId: int, timeout: int, account: str = None, readonly: bool = False) -> None:
        res = self.ib.connect(host, port, clientId=clientId, account=account, readonly=readonly)
        if inspect.isawaitable(res):
            await asyncio.wait_for(res, timeout=timeout)

    def disconnect(self) -> None:
        d = getattr(self.ib, 'disconnect', None) or getattr(self.ib, 'close', None)
        if d:
            r = d()
            if inspect.isawaitable(r):
                try:
                    asyncio.get_event_loop().run_until_complete(asyncio.wait_for(r, timeout=5))
                except Exception:
                    pass

    def is_connected(self) -> bool:
        getter = getattr(self.ib, 'isConnected', None) or getattr(self.ib, 'is_connected', None)
        try:
            return bool(getter()) if callable(getter) else bool(getter)
        except Exception:
            return False

    async def account_summary(self):
        m = getattr(self.ib, 'accountSummary', None) or getattr(self.ib, 'account_summary', None)
        res = m()
        return await res if inspect.isawaitable(res) else res

    async def req_positions(self):
        m = getattr(self.ib, 'reqPositions', None) or getattr(self.ib, 'req_positions', None)
        res = m()
        return await res if inspect.isawaitable(res) else res

    async def req_account_updates(self, subscribe: bool, account: str):
        m = getattr(self.ib, 'reqAccountUpdates', None) or getattr(self.ib, 'req_account_updates', None)
        if not m:
            return None
        res = m(bool(subscribe), account)
        return await res if inspect.isawaitable(res) else res

    async def qualify_contracts(self, contract: Any):
        m = getattr(self.ib, 'qualifyContracts', None) or getattr(self.ib, 'qualify_contracts', None)
        res = m(self._to_ibapi_contract(contract))
        return await res if inspect.isawaitable(res) else res

    async def place_order(self, contract: Any, order: Any):
        m = getattr(self.ib, 'placeOrder', None) or getattr(self.ib, 'place_order', None)
        res = m(self._to_ibapi_contract(contract), self._to_ibapi_order(order))
        return await res if inspect.isawaitable(res) else res

    async def cancel_order(self, order: Any):
        m = getattr(self.ib, 'cancelOrder', None) or getattr(self.ib, 'cancel_order', None)
        if not m:
            return None
        res = m(self._to_ibapi_order(order))
        return await res if inspect.isawaitable(res) else res

    async def req_mkt_data(self, contract: Any, genericTickList: str, snapshot: bool, regulatorySnapshot: bool):
        m = getattr(self.ib, 'reqMktData', None) or getattr(self.ib, 'req_mkt_data', None)
        res = m(self._to_ibapi_contract(contract), genericTickList, snapshot, regulatorySnapshot)
        return await res if inspect.isawaitable(res) else res

    async def cancel_mkt_data(self, contract: Any):
        m = getattr(self.ib, 'cancelMktData', None) or getattr(self.ib, 'cancel_mkt_data', None)
        if not m:
            return None
        res = m(self._to_ibapi_contract(contract))
        return await res if inspect.isawaitable(res) else res

    async def req_historical_data(self, contract: Any, **kwargs):
        m = getattr(self.ib, 'reqHistoricalData', None) or getattr(self.ib, 'req_historical_data', None)
        res = m(self._to_ibapi_contract(contract), **kwargs)
        return await res if inspect.isawaitable(res) else res

