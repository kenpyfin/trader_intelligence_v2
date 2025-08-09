import atexit
from ib_insync import IB, Stock, Forex, MarketOrder, LimitOrder, Index, Option, Bag, ComboLeg
from ib_insync import util as ibutil
import sys, random, traceback
import pandas as pd
import time
from datetime import datetime

sys.path.append('/home/ken/big_storage/airflowProd/airflow_notebook/My_Trader/my_libs_py3')
from .my_lib import *


ip_add = "10.0.1.22"
tw_port = 4002
TIMEOUT = 60


class IBTrader:
    def __init__(self):
        self.ip_add = ip_add
        self.port = tw_port
        self.client = IB()
        self.connect()
        atexit.register(self.disconnect)

    def connect(self):
        if not self.client.isConnected():
            try:
                self.client.connect(self.ip_add, self.port, clientId=0)
            except Exception as e:
                time.sleep(60)
                self.client.connect(self.ip_add, self.port, clientId=0)

    def disconnect(self):
        if self.client.isConnected():
            self.client.disconnect()

    def get_available_fund(self):
        try:
            return float(list(filter(lambda x: x.tag == "AvailableFunds", self.client.accountSummary()))[0].value)
        except Exception as e:
            raise Exception(e)

    def get_position_by_symbol(self, symbol) -> float:
        try:
            position_list = list(filter(lambda x: x.contract.symbol == symbol, self.client.positions()))
            if len(position_list) == 0:
                return 0
            else:
                return position_list[0].position
        except Exception as e:
            raise Exception(e)

    def place_forex_market_order(self, symbol, size):
        try:
            order = MarketOrder('BUY' if size >= 0 else "SELL", abs(size))
            contract = Forex(symbol)
            self.client.qualifyContracts(contract)
            trade = self.client.placeOrder(contract, order)
            return trade
        except Exception as e:
            raise Exception(e)

    def place_stock_market_order(self, symbol, size):
        try:
            order = MarketOrder('BUY' if size >= 0 else "SELL", abs(size))
            contract = Stock(symbol, "SMART", "USD")
            self.client.qualifyContracts(contract)
            trade = self.client.placeOrder(contract, order)
            return trade
        except Exception as e:
            raise Exception(e)

    def place_stock_limit_order(self, symbol, size, limit_price):
        try:
            action = 'BUY' if size > 0 else 'SELL'
            order = LimitOrder(action, abs(size), limit_price)
            contract = Stock(symbol, "SMART", "USD")
            self.client.qualifyContracts(contract)
            trade = self.client.placeOrder(contract, order)
            return trade
        except Exception as e:
            raise Exception(f"Error placing limit order for {symbol}: {str(e)}")

    def place_option_order(self, symbol: str, size: int, expiry_date: str, strike: float, right: str, order_type: str = 'MKT', limit_price: float = None, exchange: str = 'SMART'):
        """
        Places an option order.

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
            self.connect()
            action = 'BUY' if size > 0 else 'SELL'
            quantity = abs(size)

            if order_type.upper() == 'MKT':
                order = MarketOrder(action, quantity)
            elif order_type.upper() == 'LMT' and limit_price is not None:
                order = LimitOrder(action, quantity, limit_price)
            else:
                raise ValueError("Invalid order type or missing limit price for LMT order.")

            contract = Option(symbol, expiry_date, strike, right, exchange, tradingClass=symbol)
            self.client.qualifyContracts(contract)
            
            trade = self.client.placeOrder(contract, order)
            return trade
        except Exception as e:
            raise Exception(f"Error placing option order for {symbol} {expiry_date} K={strike} {right}: {str(e)}")

    async def place_strategy_order(self, symbol: str, legs_data: list, size: int, order_type: str = 'MKT', limit_price: float = None, exchange: str = 'SMART'):
        """
        Places a multi-leg option strategy order asynchronously.

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
            self.connect() # Assuming this is fast if already connected.
            print(f"DEBUG: Placing strategy order for {symbol} with size {size}")
            print(f"DEBUG: Legs data: {legs_data}")
            
            # Create a Bag contract for the combo
            contract = Bag()
            contract.symbol = symbol
            contract.currency = 'USD'
            contract.exchange = exchange
            
            combo_legs = []
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
                
                # Create a ComboLeg for the Bag contract
                combo_leg = ComboLeg()
                combo_leg.conId = leg_contract.conId
                combo_leg.ratio = leg_info['quantity']
                combo_leg.action = leg_info['action']
                combo_leg.exchange = exchange
                combo_legs.append(combo_leg)
                
            contract.comboLegs = combo_legs
            print("DEBUG: Qualifying combo contract...")
            await self.client.qualifyContractsAsync(contract)
            print("DEBUG: Combo contract qualified.")

            # Create the order for the whole strategy
            strategy_action = 'BUY' if size > 0 else 'SELL'
            quantity = abs(size)

            if order_type.upper() == 'MKT':
                order = MarketOrder(strategy_action, quantity)
            elif order_type.upper() == 'LMT' and limit_price is not None:
                order = LimitOrder(strategy_action, quantity, limit_price)
            else:
                raise ValueError("Invalid order type or missing limit price for LMT order.")

            print(f"DEBUG: Placing order: {order}")
            trade = await self.client.placeOrderAsync(contract, order)
            print(f"DEBUG: Order placed successfully. Trade: {trade}")
    
            return trade
        except Exception as e:
            print("--- ORDER PLACEMENT FAILED ---")
            traceback.print_exc()
            print("-----------------------------")
            raise Exception(f"Error placing strategy order for {symbol}: {str(e)}")

    def wait_for_order_fill(self, trade, timeout=TIMEOUT):
        ib = self.client
        start_time = time.time()

        while not trade.isDone():
            if time.time() - start_time > timeout:
                self.client.cancelOrder(trade.order)
                break
            ib.sleep(1)  # Poll every second

        return trade.orderStatus.status

    def open_positions_symbol(self):
        try:
            return [x.contract.symbol for x in self.client.positions()]
        except Exception as e:
            raise Exception(e)

    def open_positions(self):
        try:
            data = self.client.positions()
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
                unpacked_data.append(position_data)

            return pd.DataFrame(unpacked_data)
        except Exception as e:
            raise Exception(e)

    def realtimequote(self, ticker):
        try:
            if (ticker.upper() == 'VIX'):
                contract = Index(ticker, 'CBOE')  # Use the Index wrapper for VIX
            else:
                contract = Stock(ticker, 'SMART', 'USD')  # Use the Stock wrapper for other tickers

            start = ''
            end = datetime.now()
            ticks = self.client.reqHistoricalTicks(contract, start, end, 1, 'Trades', useRth=False)
            return ticks[-1].price
        except Exception as e:
            raise Exception(e)

    def get_option_market_data(self, symbol: str, expiry_date: str, strike: float, right: str, exchange: str = 'SMART'):
        """
        Fetches market data for a specific option contract.

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
            self.connect() # Ensure connection
            contract = Option(symbol, expiry_date, strike, right, exchange, tradingClass=symbol)
            self.client.qualifyContracts(contract)
            
            ticker = self.client.reqMktData(contract, '', False, False)
            self.client.sleep(2) # Allow time for data to arrive, adjust as needed

            if ticker and (ticker.last != float('nan') or ticker.close != float('nan')): # Check if we got some price
                return ticker
            else:
                # Attempt to get historical data if live tick fails or is empty
                hist_data = self.client.reqHistoricalData(
                    contract,
                    endDateTime='',
                    durationStr='1 D', # Get data for 1 day
                    barSizeSetting='1 day', # Daily bars
                    whatToShow='MIDPOINT',
                    useRTH=True,
                    formatDate=1
                )
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
        
    def cancel_order(self, trade):
        """
        Cancels an existing order.
        
        Args:
            trade: The trade object to cancel
            
        Returns:
            None
        """
        try:
            if trade.orderStatus.status not in ["Filled", "Cancelled", "ApiCancelled", "Inactive"]:
                # Send cancel request
                self.client.cancelOrder(trade.order)
                
                # Wait briefly to ensure the cancel request is processed
                self.client.sleep(2)
                    
        except Exception as e:
            raise Exception(f"Error cancelling order: {str(e)}")
