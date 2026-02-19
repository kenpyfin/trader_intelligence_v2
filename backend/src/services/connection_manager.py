"""Singleton manager for sharing a single broker client across service calls."""
import asyncio
import time
from typing import Optional
from ..my_libs_py3.TD_Order import AlpacaTrader


class BrokerConnectionManager:
    """Manage lifecycle for a shared AlpacaTrader instance in async contexts."""
    
    _instance: Optional['BrokerConnectionManager'] = None
    _lock = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._trader = None
            cls._instance._connection_lock = None
            cls._instance._last_error_time = 0
            cls._instance._connection_retry_delay = 30  # 30 second cooldown after connection errors
            cls._instance._loop = None  # Track the event loop that owns current resources
        return cls._instance

    def _ensure_lock(self):
        """Ensure the connection lock exists for the current running event loop.
        If the loop changes (e.g., dev reloads), recreate lock and invalidate trader.
        """
        current_loop = asyncio.get_running_loop()
        if self._loop is None or self._loop is not current_loop:
            # Event loop changed: drop existing trader to avoid cross-loop use
            if self._trader is not None:
                try:
                    self._trader.disconnect()
                except Exception:
                    pass
                self._trader = None
            # Create a new lock bound to current loop
            self._connection_lock = asyncio.Lock()
            self._loop = current_loop
    
    async def get_trader(self) -> AlpacaTrader:
        """Get or create the shared AlpacaTrader instance with connection health check."""
        # Ensure lock and resources are bound to current loop
        self._ensure_lock()
        async with self._connection_lock:
            current_time = time.time()
            
            # If we had a recent connection error, wait before retrying
            if current_time - self._last_error_time < self._connection_retry_delay:
                remaining_wait = self._connection_retry_delay - (current_time - self._last_error_time)
                print(f"INFO: Connection manager waiting {remaining_wait:.0f}s before retry due to recent error")
                await asyncio.sleep(remaining_wait)
            
            if self._trader is None:
                try:
                    self._trader = AlpacaTrader()
                    await self._trader.connect()  # Explicitly connect to validate the connection
                    print("INFO: Connection manager established new Alpaca connection")
                except Exception as e:
                    print(f"ERROR: Connection manager failed to establish Alpaca connection: {e}")
                    self._last_error_time = current_time
                    self._trader = None
                    raise
            else:
                # Check if the existing connection is still healthy
                try:
                    if not self._trader.client.is_connected():
                        print("INFO: Connection manager detected disconnected client, reconnecting...")
                        await self._trader.connect()
                except Exception as e:
                    print(f"WARN: Connection health check failed, creating new trader: {e}")
                    try:
                        self._trader.disconnect()
                    except:
                        pass
                    # Create new trader instance (AlpacaTrader handles loop binding internally)
                    self._trader = AlpacaTrader()
                    await self._trader.connect()
                    
            return self._trader
    
    async def disconnect(self):
        """Disconnect the shared trader instance."""
        self._ensure_lock()
        async with self._connection_lock:
            if self._trader is not None:
                try:
                    self._trader.disconnect()
                    print("INFO: Connection manager disconnected Alpaca connection")
                except Exception as e:
                    print(f"WARN: Error during disconnect: {e}")
                finally:
                    self._trader = None
    
    async def reset_connection(self):
        """Force reset the connection (useful after timeouts)."""
        self._ensure_lock()
        async with self._connection_lock:
            if self._trader is not None:
                try:
                    self._trader.disconnect()
                except:
                    pass
                self._trader = None
            print("INFO: Connection manager reset connection")

# Global instance
connection_manager = BrokerConnectionManager()
