import asyncio
import logging
from typing import Any

import ib_insync
from ib_insync import IB

from .base import AsyncBrokerClient


class IBInsyncAsyncClient(AsyncBrokerClient):
    def __init__(self) -> None:
        self.ib = IB()
        self.backend = "ib_insync"
        # Reduce verbosity a bit by default
        try:
            ib_insync.util.logToConsole(logging.WARNING)
        except Exception:
            pass

    async def connect(self, host: str, port: int, clientId: int, timeout: int, account: str = None, readonly: bool = False) -> None:
        try:
            ib_insync.util.useAsyncio()
        except Exception:
            pass
        await self.ib.connectAsync(host, port, clientId=clientId, timeout=timeout, account=account, readonly=readonly)

    def disconnect(self) -> None:
        try:
            self.ib.disconnect()
        except Exception:
            pass

    def is_connected(self) -> bool:
        return bool(self.ib.isConnected())

    # Account / portfolio
    async def account_summary(self):
        return await self.ib.accountSummaryAsync()

    async def req_positions(self):
        return await self.ib.reqPositionsAsync()

    async def req_account_updates(self, subscribe: bool, account: str):
        return self.ib.reqAccountUpdates(bool(subscribe), account)

    # Contracts
    async def qualify_contracts(self, contract: Any):
        return await self.ib.qualifyContractsAsync(contract)

    # Orders
    async def place_order(self, contract: Any, order: Any):
        trade = self.ib.placeOrder(contract, order)
        await asyncio.sleep(0)  # yield control
        return trade

    async def cancel_order(self, order: Any):
        return self.ib.cancelOrder(order)

    # Market/History data
    async def req_mkt_data(self, contract: Any, genericTickList: str, snapshot: bool, regulatorySnapshot: bool):
        return self.ib.reqMktData(contract, genericTickList, snapshot, regulatorySnapshot)

    async def cancel_mkt_data(self, contract: Any):
        return self.ib.cancelMktData(contract)

    async def req_historical_data(self, contract: Any, **kwargs):
        return await self.ib.reqHistoricalDataAsync(contract, **kwargs)

