import abc
from typing import Any


class AsyncBrokerClient(abc.ABC):
    backend: str = "unknown"

    @abc.abstractmethod
    async def connect(self, host: str, port: int, clientId: int, timeout: int, account: str = None, readonly: bool = False) -> None:
        ...

    @abc.abstractmethod
    def disconnect(self) -> None:
        ...

    @abc.abstractmethod
    def is_connected(self) -> bool:
        ...

    # Account / portfolio
    @abc.abstractmethod
    async def account_summary(self):
        ...

    @abc.abstractmethod
    async def req_positions(self):
        ...

    # Streaming account updates toggle
    async def req_account_updates(self, subscribe: bool, account: str):
        raise NotImplementedError

    # Contracts
    @abc.abstractmethod
    async def qualify_contracts(self, contract: Any):
        ...

    # Orders
    @abc.abstractmethod
    async def place_order(self, contract: Any, order: Any):
        ...

    async def cancel_order(self, order: Any):
        raise NotImplementedError

    # Market/History data
    @abc.abstractmethod
    async def req_mkt_data(self, contract: Any, genericTickList: str, snapshot: bool, regulatorySnapshot: bool):
        ...

    @abc.abstractmethod
    async def cancel_mkt_data(self, contract: Any):
        ...

    @abc.abstractmethod
    async def req_historical_data(self, contract: Any, **kwargs):
        ...

