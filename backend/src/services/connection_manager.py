"""
Connection manager to handle single IBTrader instance across multiple service calls.
This prevents multiple TWS connections from being created simultaneously.
"""
import asyncio
import time
from typing import Optional
from ..my_libs_py3.TD_Order import IBTrader

class IBConnectionManager:
    """Singleton connection manager for IBTrader to prevent multiple TWS connections."""
    
    _instance: Optional['IBConnectionManager'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._trader = None
            cls._instance._connection_lock = asyncio.Lock()
            cls._instance._last_error_time = 0
            cls._instance._connection_retry_delay = 30  # 30 second cooldown after connection errors
        return cls._instance
    
    async def get_trader(self) -> IBTrader:
        """Get or create the shared IBTrader instance with connection health check."""
        async with self._connection_lock:
            current_time = time.time()
            
            # If we had a recent connection error, wait before retrying
            if current_time - self._last_error_time < self._connection_retry_delay:
                remaining_wait = self._connection_retry_delay - (current_time - self._last_error_time)
                print(f"INFO: Connection manager waiting {remaining_wait:.0f}s before retry due to recent error")
                await asyncio.sleep(remaining_wait)
            
            if self._trader is None:
                try:
                    self._trader = IBTrader()
                    await self._trader.connect()  # Explicitly connect to validate the connection
                    print("INFO: Connection manager established new TWS connection")
                except Exception as e:
                    print(f"ERROR: Connection manager failed to establish TWS connection: {e}")
                    self._last_error_time = current_time
                    self._trader = None
                    raise
            else:
                # Check if the existing connection is still healthy
                try:
                    if not self._trader.client.isConnected():
                        print("INFO: Connection manager detected disconnected client, reconnecting...")
                        await self._trader.connect()
                except Exception as e:
                    print(f"WARN: Connection health check failed, creating new trader: {e}")
                    try:
                        self._trader.disconnect()
                    except:
                        pass
                    self._trader = IBTrader()
                    await self._trader.connect()
                    
            return self._trader
    
    async def disconnect(self):
        """Disconnect the shared trader instance."""
        async with self._connection_lock:
            if self._trader is not None:
                try:
                    self._trader.disconnect()
                    print("INFO: Connection manager disconnected TWS connection")
                except Exception as e:
                    print(f"WARN: Error during disconnect: {e}")
                finally:
                    self._trader = None
    
    async def reset_connection(self):
        """Force reset the connection (useful after timeouts)."""
        async with self._connection_lock:
            if self._trader is not None:
                try:
                    self._trader.disconnect()
                except:
                    pass
                self._trader = None
            print("INFO: Connection manager reset connection")

# Global instance
connection_manager = IBConnectionManager()