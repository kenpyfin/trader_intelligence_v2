import atexit
import os
import socket
import asyncio
import logging
from ib_insync import IB, Stock, Forex, MarketOrder, LimitOrder, Index, Option, Bag, ComboLeg
from ib_insync import util as ibutil
import sys, random, traceback
import pandas as pd
import time
from datetime import datetime

sys.path.append('/home/ken/big_storage/airflowProd/airflow_notebook/My_Trader/my_libs_py3')
from .my_lib import *


tw_port = 4002
TIMEOUT = 60

# Configure ib_insync to be more tolerant of slow responses
import ib_insync
ib_insync.util.logToConsole(logging.WARNING)  # Reduce ib_insync verbosity
# Increase default timeout for requests that commonly fail
ib_insync.util.timeoutReceived = 30  # 2 minute timeout instead of default
ib_insync.client.Client.requestTimeout = 30  # Set request timeout to 2 minutes


class IBTrader:
    def __init__(self):
        # Use an environment variable for the host, defaulting to a common local IP.
        # For Docker on Mac/Windows, 'host.docker.internal' is preferred.
        # For Docker on Linux, the host's network IP is needed.
        self.ip_add = os.getenv('TWS_HOST', '10.0.1.22')
        self.account= os.getenv("TWS_ACCOUNT")
        self.port = tw_port
        print(f"INFO: IBTrader initialized to connect to TWS at {self.ip_add}:{self.port}")
        self.client = IB()
        
        # Configure ib_insync to NOT automatically request completed orders which commonly timeout
        # This prevents the "completed orders request timed out" error
        self.client.RequestTimeout = 30  # 2 minute timeout for all requests
        
        # The connection is now established on-demand by async methods.
        atexit.register(self.disconnect)

    async def connect(self):
        """Establishes connection to TWS/Gateway asynchronously if not already connected."""
        if not self.client.isConnected():
            try:
                print(f"INFO: Connecting to TWS at {self.ip_add}:{self.port}...")
                # Increased timeout to 180s to prevent failures when syncing large option portfolios.
                await self.client.connectAsync(self.ip_add, self.port, clientId=random.randint(0, 1000), timeout=180, account=self.account)
                
                # Disable automatic data syncing to prevent timeout errors
                # This prevents ib_insync from automatically requesting completed orders and other data
                self.client.reqAutoOpenOrders(False)  # Don't auto-request open orders
                
                print("INFO: Connection to TWS established successfully.")
            except (asyncio.TimeoutError, ConnectionRefusedError):
                 print(f"ERROR: Connection to {self.ip_add}:{self.port} timed out or was refused.")
                 print("HINT: Ensure TWS/Gateway is running, API connections are enabled, and the IP is whitelisted.")
                 # The synchronous self.client.connect is removed as it blocks the event loop in an async context.
                 # The exception is allowed to propagate to the caller.
                 raise
            except socket.gaierror:
                print(f"ERROR: Hostname '{self.ip_add}' could not be resolved. This is a DNS lookup failure.")
                print("HINT: If using Docker on Linux, 'host.docker.internal' may not work without extra configuration. Try setting TWS_HOST to your host's IP address (e.g., 10.0.1.22).")
                raise
            except Exception as e:
                print(f"ERROR: An unexpected exception occurred while connecting to TWS: {e}")
                traceback.print_exc()
                raise

    def disconnect(self):
        if self.client.isConnected():
            self.client.disconnect()

    async def get_available_fund(self):
        try:
            await self.connect()
            # Use accountSummaryAsync to avoid blocking the event loop
            summary = await self.client.accountSummaryAsync()
            return float(list(filter(lambda x: x.tag == "AvailableFunds", summary))[0].value)
        except Exception as e:
            raise Exception(e)

    async def get_account_summary(self):
        """Fetches the account summary."""
        try:
            await self.connect()
            return await self.client.accountSummaryAsync()
        except Exception as e:
            raise Exception(f"Error fetching account summary: {e}")

    async def get_position_by_symbol(self, symbol) -> float:
        try:
            await self.connect()
            positions = await self.client.reqPositionsAsync()
            position_list = list(filter(lambda x: x.contract.symbol == symbol, positions))
            if len(position_list) == 0:
                return 0
            else:
                return position_list[0].position
        except Exception as e:
            raise Exception(e)

    async def place_forex_market_order(self, symbol, size):
        try:
            await self.connect()
            order = MarketOrder('BUY' if size >= 0 else "SELL", abs(size))
            contract = Forex(symbol)
            await self.client.qualifyContractsAsync(contract)
            trade = self.client.placeOrder(contract, order)
            await asyncio.sleep(1)  # Allow ib_insync to process and send the order
            return trade
        except Exception as e:
            raise Exception(e)

    async def place_stock_market_order(self, symbol, size):
        """
        Places a stock order using limit price at current market price.
        This ensures orders can be placed outside market hours and will remain active.
        """
        try:
            await self.connect()
            action = 'BUY' if size >= 0 else "SELL"
            quantity = abs(size)
            
            # Get current market price to use as limit price
            current_price = await self.get_current_price(symbol, 'STK')
            if current_price is None:
                # Fallback to market order if price can't be determined
                print(f"WARN: Could not fetch price for {symbol}, using market order")
                order = MarketOrder(action, quantity)
            else:
                # Use limit order at exact market price
                limit_price = round(current_price, 2)
                order = LimitOrder(action, quantity, limit_price)
                print(f"INFO: Placing {action} limit order for {quantity} {symbol} at ${limit_price}")
            
            contract = Stock(symbol, "SMART", "USD")
            await self.client.qualifyContractsAsync(contract)
            trade = self.client.placeOrder(contract, order)
            await asyncio.sleep(1)  # Allow ib_insync to process and send the order
            return trade
        except Exception as e:
            raise Exception(e)

    async def place_stock_limit_order(self, symbol, size, limit_price):
        try:
            await self.connect()
            action = 'BUY' if size > 0 else 'SELL'
            order = LimitOrder(action, abs(size), limit_price)
            contract = Stock(symbol, "SMART", "USD")
            await self.client.qualifyContractsAsync(contract)
            trade = self.client.placeOrder(contract, order)
            await asyncio.sleep(1)  # Allow ib_insync to process and send the order
            return trade
        except Exception as e:
            raise Exception(f"Error placing limit order for {symbol}: {str(e)}")

    async def place_option_order(self, symbol: str, size: int, expiry_date: str, strike: float, right: str, order_type: str = 'MKT', limit_price: float = None, exchange: str = 'SMART'):
        """
        Places an option order asynchronously. For MKT orders, automatically converts to LMT
        orders using current market price to ensure orders can be placed outside market hours.

        Args:
            symbol (str): The underlying symbol.
            size (int): The number of contracts to trade. Positive for buy, negative for sell.
            expiry_date (str): The option's expiration date in YYYYMMDD format.
            strike (float): The option's strike price.
            right (str): The option type, 'C' for Call or 'P' for Put.
            order_type (str): 'MKT' for market order, 'LMT' for limit order.
            limit_price (float, optional): The limit price for LMT orders. Defaults to None.
            exchange (str, optional): The exchange. Defaults to 'SMART'.

        Returns:
            ib_insync.Trade: The trade object.
        """
        try:
            await self.connect()
            action = 'BUY' if size > 0 else 'SELL'
            quantity = abs(size)

            if order_type.upper() == 'MKT':
                # Convert market order to limit order using current market price
                current_price = await self.get_current_price(symbol, 'OPT', expiry_date, strike, right, exchange)
                if current_price is None:
                    # Fallback to market order if price can't be determined
                    print(f"WARN: Could not fetch price for {symbol} {expiry_date} {strike} {right}, using market order")
                    order = MarketOrder(action, quantity)
                else:
                    # Use limit order at exact market price
                    calculated_limit_price = round(current_price, 2)
                    order = LimitOrder(action, quantity, calculated_limit_price)
                    print(f"INFO: Placing {action} limit order for {quantity} {symbol} {expiry_date} {strike}{right} at ${calculated_limit_price:.2f}")
                    
            elif order_type.upper() == 'LMT' and limit_price is not None:
                order = LimitOrder(action, quantity, limit_price)
            else:
                raise ValueError("Invalid order type or missing limit price for LMT order.")

            contract = Option(symbol, expiry_date, strike, right, exchange, tradingClass=symbol)
            await self.client.qualifyContractsAsync(contract)
            
            trade = self.client.placeOrder(contract, order)
            await asyncio.sleep(1)  # Allow ib_insync to process and send the order
            return trade
        except Exception as e:
            raise Exception(f"Error placing option order for {symbol} {expiry_date} K={strike} {right}: {str(e)}")

    async def place_strategy_order(self, symbol: str, legs_data: list, size: int, order_type: str = 'MKT', limit_price: float = None, exchange: str = 'SMART'):
        """
        Places a multi-leg option strategy order asynchronously. For MKT orders, attempts to 
        calculate strategy limit price based on individual leg prices to ensure orders can
        be placed outside market hours.

        Args:
            symbol (str): The underlying symbol.
            legs_data (list): A list of dictionaries, each describing a leg.
                e.g., [{'action': 'BUY', 'quantity': 1, 'expiry_date': '20251219', 'strike': 500, 'right': 'C'}, ...]
            size (int): The number of strategy units to trade. Positive for buy, negative for sell.
            order_type (str): 'MKT' for market order, 'LMT' for limit order.
            limit_price (float, optional): The limit price for the entire strategy. Defaults to None.
            exchange (str, optional): The exchange. Defaults to 'SMART'.

        Returns:
            ib_insync.Trade: The trade object.
        """
        try:
            await self.connect()
            print(f"DEBUG: Placing strategy order for {symbol} with size {size}")
            print(f"DEBUG: Legs data: {legs_data}")
            
            # Create a Bag contract for the combo
            contract = Bag()
            contract.symbol = symbol
            contract.currency = 'USD'
            contract.exchange = exchange
            
            combo_legs = []
            strategy_estimated_price = 0.0
            
            for leg_info in legs_data:
                # Qualify each leg to get its conId
                leg_contract = Option(
                    symbol, 
                    leg_info['expiry_date'], 
                    leg_info['strike'], 
                    leg_info['right'], 
                    exchange, 
                    tradingClass=symbol
                )
                print(f"DEBUG: Qualifying leg: {leg_contract}")
                await self.client.qualifyContractsAsync(leg_contract)
                print(f"DEBUG: Leg qualified: {leg_contract.localSymbol}, conId: {leg_contract.conId}")
                
                # For MKT orders, try to get leg price for strategy pricing
                if order_type.upper() == 'MKT' and limit_price is None:
                    leg_price = await self.get_current_price(symbol, 'OPT', leg_info['expiry_date'], leg_info['strike'], leg_info['right'], exchange)
                    if leg_price is not None:
                        # Add/subtract based on whether we're buying or selling this leg
                        leg_contribution = leg_price * leg_info['quantity']
                        if leg_info['action'] == 'BUY':
                            strategy_estimated_price += leg_contribution
                        else:  # SELL
                            strategy_estimated_price -= leg_contribution
                        print(f"DEBUG: Leg {leg_info['strike']}{leg_info['right']} price: ${leg_price:.2f}, contribution: ${leg_contribution:.2f}")
                
                # Create a ComboLeg for the Bag contract
                combo_leg = ComboLeg()
                combo_leg.conId = leg_contract.conId
                combo_leg.ratio = leg_info['quantity']
                combo_leg.action = leg_info['action']
                combo_leg.exchange = exchange
                combo_legs.append(combo_leg)
                
            contract.comboLegs = combo_legs
            print("DEBUG: Combo contract constructed from qualified legs.")

            # Create the order for the whole strategy
            strategy_action = 'BUY' if size > 0 else 'SELL'
            quantity = abs(size)

            if order_type.upper() == 'MKT':
                # Try to use calculated strategy limit price for execution outside market hours
                if strategy_estimated_price != 0.0:
                    # Use exact estimated strategy price without buffer
                    calculated_limit_price = round(strategy_estimated_price, 2)
                    
                    # Ensure the limit price is positive for buy orders and reasonable for sell orders
                    if strategy_action == 'BUY' and calculated_limit_price > 0:
                        order = LimitOrder(strategy_action, quantity, calculated_limit_price)
                        print(f"INFO: Converting MKT to LMT order at ${calculated_limit_price:.2f}")
                    elif strategy_action == 'SELL' and calculated_limit_price > 0:
                        order = LimitOrder(strategy_action, quantity, calculated_limit_price)
                        print(f"INFO: Converting MKT to LMT order at ${calculated_limit_price:.2f}")
                    else:
                        print("WARN: Could not calculate reasonable strategy limit price, using market order")
                        order = MarketOrder(strategy_action, quantity)
                else:
                    print("WARN: Could not estimate strategy price, using market order")
                    order = MarketOrder(strategy_action, quantity)
            elif order_type.upper() == 'LMT' and limit_price is not None:
                order = LimitOrder(strategy_action, quantity, limit_price)
            else:
                raise ValueError("Invalid order type or missing limit price for LMT order.")

            print(f"DEBUG: Placing order: {order}")
            trade = self.client.placeOrder(contract, order)
            await asyncio.sleep(1)  # Allow ib_insync to process and send the order
            print(f"DEBUG: Order placed successfully. Trade: {trade}")
    
            return trade
        except Exception as e:
            print("--- ORDER PLACEMENT FAILED ---")
            traceback.print_exc()
            print("-----------------------------")
            raise Exception(f"Error placing strategy order for {symbol}: {str(e)}")

    async def wait_for_order_fill(self, trade, timeout=TIMEOUT):
        start_time = time.time()

        while not trade.isDone():
            if time.time() - start_time > timeout:
                self.client.cancelOrder(trade.order)
                break
            await asyncio.sleep(1)  # Use asyncio.sleep for non-blocking wait

        return trade.orderStatus.status

    async def open_positions_symbol(self):
        try:
            await self.connect()
            positions = await self.client.reqPositionsAsync()
            return [x.contract.symbol for x in positions]
        except Exception as e:
            raise Exception(e)

    async def open_positions(self):
        try:
            await self.connect()
            data = await self.client.reqPositionsAsync()
            unpacked_data = []

            for pos in data:
                position_data = {
                    'account': pos.account,
                    'contract_type': type(pos.contract).__name__,
                    'symbol': pos.contract.symbol,
                    'exchange': getattr(pos.contract, 'exchange', None),
                    'currency': getattr(pos.contract, 'currency', None),
                    'localSymbol': pos.contract.localSymbol,
                    'tradingClass': pos.contract.tradingClass,
                    'position': pos.position,
                    'avgCost': pos.avgCost
                }
                # Add option-specific details if the contract is an Option
                if isinstance(pos.contract, Option):
                    position_data['strike'] = pos.contract.strike
                    position_data['right'] = pos.contract.right
                    position_data['expiry'] = pos.contract.lastTradeDateOrContractMonth

                unpacked_data.append(position_data)

            return pd.DataFrame(unpacked_data)
        except Exception as e:
            raise Exception(e)

    async def get_option_expirations(self, symbol: str):
        """
        Fetches all available option expiration dates for a given underlying symbol.
        """
        try:
            await self.connect()
            contract = Stock(symbol, 'SMART', 'USD')
            await self.client.qualifyContractsAsync(contract)
            
            # This request returns a list of chain parameters.
            chains = await self.client.reqSecDefOptParamsAsync(
                underlyingSymbol=contract.symbol,
                futFopExchange='',
                underlyingSecType=contract.secType,
                underlyingConId=contract.conId
            )
            
            # The result is grouped by exchange. We'll collect all unique expirations.
            expirations = set()
            if chains:
                for chain in chains:
                    expirations.update(chain.expirations)
                
            return sorted(list(expirations))
        except Exception as e:
            print(f"Error fetching option expirations for {symbol}: {e}")
            raise

    async def realtimequote(self, ticker):
        try:
            await self.connect()
            if (ticker.upper() == 'VIX'):
                contract = Index(ticker, 'CBOE')  # Use the Index wrapper for VIX
            else:
                contract = Stock(ticker, 'SMART', 'USD')  # Use the Stock wrapper for other tickers

            start = ''
            end = datetime.now()
            ticks = await self.client.reqHistoricalTicksAsync(contract, start, end, 1, 'Trades', useRth=False)
            if ticks:
                return ticks[-1].price
            return None
        except Exception as e:
            raise Exception(e)

    async def get_current_price(self, symbol: str, contract_type: str = 'STK', expiry_date: str = None, strike: float = None, right: str = None, exchange: str = 'SMART'):
        """
        Gets current market price (or last close price if market closed) for any instrument.
        
        Args:
            symbol (str): The symbol
            contract_type (str): 'STK' for stock, 'OPT' for option
            expiry_date (str): Option expiry in YYYYMMDD format (for options only)
            strike (float): Strike price (for options only)  
            right (str): 'C' or 'P' (for options only)
            exchange (str): Exchange, defaults to 'SMART'
            
        Returns:
            float: Current market price or last close price, None if unable to fetch
        """
        try:
            await self.connect()
            
            if contract_type.upper() == 'STK':
                contract = Stock(symbol, exchange, 'USD')
            elif contract_type.upper() == 'OPT':
                contract = Option(symbol, expiry_date, strike, right, exchange, tradingClass=symbol)
            else:
                raise ValueError(f"Unsupported contract type: {contract_type}")
                
            await self.client.qualifyContractsAsync(contract)
            
            # Try to get live market data first
            ticker = self.client.reqMktData(contract, '', False, False)
            await asyncio.sleep(2)  # Allow time for data to arrive
            
            # Check for live prices (bid/ask/last)
            if ticker and hasattr(ticker, 'last') and ticker.last is not None and not pd.isna(ticker.last) and ticker.last > 0:
                self.client.cancelMktData(contract)
                return float(ticker.last)
            elif ticker and hasattr(ticker, 'close') and ticker.close is not None and not pd.isna(ticker.close) and ticker.close > 0:
                self.client.cancelMktData(contract)
                return float(ticker.close)
            elif ticker and hasattr(ticker, 'bid') and hasattr(ticker, 'ask') and ticker.bid is not None and ticker.ask is not None:
                if not pd.isna(ticker.bid) and not pd.isna(ticker.ask) and ticker.bid > 0 and ticker.ask > 0:
                    mid_price = (float(ticker.bid) + float(ticker.ask)) / 2.0
                    self.client.cancelMktData(contract)
                    return mid_price
                    
            # If live data fails, get historical data
            self.client.cancelMktData(contract)
            print(f"INFO: No live data available for {symbol}, fetching historical close price")
            
            hist_data = await self.client.reqHistoricalDataAsync(
                contract,
                endDateTime='',
                durationStr='5 D',  # Get last 5 days of data
                barSizeSetting='1 day',
                whatToShow='MIDPOINT',
                useRTH=True,
                formatDate=1
            )
            
            if hist_data and len(hist_data) > 0:
                # Return the most recent close price
                last_bar = hist_data[-1]
                if hasattr(last_bar, 'close') and last_bar.close is not None and last_bar.close > 0:
                    return float(last_bar.close)
                    
            print(f"WARN: Unable to fetch price for {symbol} {contract_type}")
            return None
            
        except Exception as e:
            print(f"ERROR: Failed to fetch price for {symbol}: {e}")
            return None

    async def get_option_market_data(self, symbol: str, expiry_date: str, strike: float, right: str, exchange: str = 'SMART'):
        """
        Fetches market data for a specific option contract asynchronously.

        Args:
            symbol (str): The underlying symbol (e.g., 'AAPL').
            expiry_date (str): The option's expiration date in YYYYMMDD format.
            strike (float): The option's strike price.
            right (str): The option type, 'C' for Call or 'P' for Put.
            exchange (str): The exchange to trade on, defaults to 'SMART'.

        Returns:
            ib_insync.Ticker: Ticker object containing market data, or None if data retrieval fails.
        """
        try:
            await self.connect() # Ensure connection
            contract = Option(symbol, expiry_date, strike, right, exchange, tradingClass=symbol)
            await self.client.qualifyContractsAsync(contract)
            
            ticker = self.client.reqMktData(contract, '', False, False)
            await asyncio.sleep(2) # Allow time for data to arrive, adjust as needed

            if ticker and (ticker.last is not None and not pd.isna(ticker.last) or ticker.close is not None and not pd.isna(ticker.close)): # Check if we got some price
                self.client.cancelMktData(contract)
                return ticker
            else:
                # Attempt to get historical data if live tick fails or is empty
                hist_data = await self.client.reqHistoricalDataAsync(
                    contract,
                    endDateTime='',
                    durationStr='1 D', # Get data for 1 day
                    barSizeSetting='1 day', # Daily bars
                    whatToShow='MIDPOINT',
                    useRTH=True,
                    formatDate=1
                )
                self.client.cancelMktData(contract) # Clean up subscription
                if hist_data:
                    # Create a mock ticker object from historical data if needed
                    # This part depends on what specific fields you need from the ticker
                    # For simplicity, returning the raw historical data list for now
                    # Or, you can populate a Ticker-like object if consistent structure is required
                    # For example, if you need the close price:
                    # mock_ticker = ibutil.Ticker(contract=contract, close=hist_data[-1].close)
                    # return mock_ticker
                    # For now, let's assume the user might want the last close from historical data
                    # and we can return a simplified structure or the last historical bar.
                    # Returning the last bar's close price as an example.
                    # You might want to return the whole ticker or a more complex object.
                    if hist_data[-1].close:
                         # Create a Ticker object and populate it
                        mock_ticker = ibutil.Ticker(
                            contract=contract,
                            time=datetime.now(), # Or use hist_data[-1].date
                            bid=float('nan'), # Historical data might not have live bid/ask
                            bidSize=0,
                            ask=float('nan'),
                            askSize=0,
                            last=hist_data[-1].close, # Using close as last
                            lastSize=0,
                            volume=hist_data[-1].volume if hasattr(hist_data[-1], 'volume') else 0,
                            close=hist_data[-1].close,
                            # Add other fields as necessary
                        )
                        return mock_ticker
                return None # If both live and historical fail
        except Exception as e:
            # Log the exception or handle it as per your application's needs
            print(f"Error fetching option market data for {symbol} {expiry_date} {strike} {right}: {e}")
            # It might be better to raise the exception or return a specific error indicator
            # For now, returning None to indicate failure
            return None
        
    async def cancel_order(self, trade):
        """
        Cancels an existing order asynchronously.
        
        Args:
            trade: The trade object to cancel
            
        Returns:
            None
        """
        try:
            await self.connect()
            if trade.orderStatus.status not in ["Filled", "Cancelled", "ApiCancelled", "Inactive"]:
                # Send cancel request
                self.client.cancelOrder(trade.order)
                
                # Wait briefly to ensure the cancel request is processed
                await asyncio.sleep(1)
                    
        except Exception as e:
            raise Exception(f"Error cancelling order: {str(e)}")

    async def get_recent_orders(self, count=10):
        """
        Fetches the most recent trades from the current session.
        """
        try:
            await self.connect()
            # client.trades() returns all trades for the session.
            # This is a synchronous call that gets cached data and doesn't trigger network requests
            all_trades = self.client.trades()
            
            # If no trades available, return empty list instead of trying to request completed orders
            if not all_trades:
                print("INFO: No trades found in current session")
                return []
            
            # Sort trades by the execution time of their last fill.
            def get_latest_fill_time(trade):
                try:
                    # Prefer the latest execution fill time if available
                    if trade.fills:
                        latest_fill_time = max(
                            (f.time for f in trade.fills if getattr(f, "time", None)),
                            default=None
                        )
                        if latest_fill_time:
                            return latest_fill_time
                    # Fallback: use latest trade log event time if available
                    if getattr(trade, "log", None):
                        log_times = [getattr(l, "time", None) for l in trade.log if getattr(l, "time", None)]
                        if log_times:
                            return max(log_times)
                    # Final fallback: epoch (tz-aware) to keep sorting stable
                    return datetime.fromtimestamp(0).astimezone()
                except Exception:
                    # Defensive fallback in case of unexpected structures
                    return datetime.fromtimestamp(0).astimezone()

            # Sort trades, most recent first.
            sorted_trades = sorted(all_trades, key=get_latest_fill_time, reverse=True)
            
            recent_trades = sorted_trades[:count]
            
            unpacked_trades = []
            for trade in recent_trades:
                contract = trade.contract
                order = trade.order
                status = trade.orderStatus

                trade_data = {
                    'symbol': contract.symbol,
                    'secType': contract.secType,
                    'action': order.action,
                    'quantity': order.totalQuantity,
                    'orderType': order.orderType,
                    'status': status.status,
                    'filled': status.filled,
                    'avgFillPrice': status.avgFillPrice,
                    'lastFillTime': get_latest_fill_time(trade).isoformat() if status.status == 'Filled' else None,
                    'description': ''
                }

                if isinstance(contract, Option):
                    trade_data['description'] = f"{contract.lastTradeDateOrContractMonth} {contract.strike} {contract.right}"
                elif isinstance(contract, Stock):
                    trade_data['description'] = 'Stock'
                elif isinstance(contract, Forex):
                    trade_data['description'] = 'Forex'

                unpacked_trades.append(trade_data)
                
            return unpacked_trades
        except Exception as e:
            print(f"Error fetching recent orders: {e}")
            traceback.print_exc()
            raise
