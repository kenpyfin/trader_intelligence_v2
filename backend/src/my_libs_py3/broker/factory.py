import logging
import os

from .base import AsyncBrokerClient


def get_broker_client(backend: str = None) -> AsyncBrokerClient:
    backend = (backend or os.getenv("BROKER_BACKEND", "alpaca")).lower()
    if backend in {"alpaca", "alpaca_async"}:
        from .alpaca_client import AlpacaAsyncClient

        return AlpacaAsyncClient()
    if backend == "ib_async":
        try:
            from .ib_async_client import IBAsyncAsyncClient

            return IBAsyncAsyncClient()
        except Exception as exc:
            logging.warning("ib_async requested but unavailable (%s); falling back to ib_insync", exc)
    from .ib_insync_client import IBInsyncAsyncClient

    return IBInsyncAsyncClient()


def get_ib_client(backend: str = None) -> AsyncBrokerClient:
    return get_broker_client(backend)
