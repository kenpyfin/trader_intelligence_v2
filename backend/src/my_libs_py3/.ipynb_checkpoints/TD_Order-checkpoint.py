import atexit
from ib_insync import IB, Stock, Forex, MarketOrder, Index
from ib_insync import util as ibutil
import sys, random
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
                self.client.connect(self.ip_add, self.port, clientId=random.randint(0, 1000))
            except Exception as e:
                time.sleep(60)
                self.client.connect(self.ip_add, self.port, clientId=random.randint(0, 1000) + 1)

    def disconnect(self):
        if self.client.isConnected():
            self.client.disconnect()

    def get_available_fund(self):
        try:
            return float(list(filter(lambda x: x.tag == "AvailableFunds", self.client.accountSummary()))[0].value)
        except Exception as e:
            raise Exception(e)

    def get_position_by_symbol(self, symbol):
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
            self.wait_for_order_fill(trade)
            return trade
        except Exception as e:
            raise Exception(e)

    def place_stock_market_order(self, symbol, size):
        try:
            order = MarketOrder('BUY' if size >= 0 else "SELL", abs(size))
            contract = Stock(symbol, "SMART", "USD")
            self.client.qualifyContracts(contract)
            trade = self.client.placeOrder(contract, order)
            self.wait_for_order_fill(trade)
            return trade
        except Exception as e:
            raise Exception(e)

    def wait_for_order_fill(self, trade, timeout=TIMEOUT):
        ib = self.client
        start_time = time.time()
        order_filled = False

        def on_filled(trade, order):
            nonlocal order_filled
            self.order_filled = True

        def on_cancel(trade, order):
            nonlocal order_filled
            order_filled = True
            ib.sleep(0)

        trade.fillEvent += on_filled
        trade.cancelledEvent += on_cancel


        while not order_filled:
            if time.time() - start_time > timeout:
                if trade.orderStatus.status == "Submitted":
                    ib.cancelOrder(trade.order)
                break
            ib.sleep(5)  # Polling interval

        trade.fillEvent -= on_filled
        trade.cancelledEvent -= on_cancel

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
