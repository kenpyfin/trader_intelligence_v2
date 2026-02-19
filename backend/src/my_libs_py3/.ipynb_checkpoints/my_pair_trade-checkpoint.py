import pandas as pd

from .my_lib import *
from .my_strategies import *
from .option import *
from .send_email import *
from .fmp import *
from .TD_Order import *
from .my_trader import *
from .habitica import habiticaImp
from .my_lib import TRADE_CASH


class pair_trade_log:

    def __init__(self, ticker1:str, ticker2:str):
        self.ticker_combo = f"{ticker1}_{ticker2}"
        self.ticker1 = ticker1
        self.ticker2 = ticker2
        self.get_log()


    @staticmethod
    def log_pair_trade(ticker1, ticker2, size1, size2, price1, price2, database="pair_trade_log"):
        timestamp = datetime.now()
        ticker = ticker1 + "_" + ticker2
        mongod = mongo(database, ticker)

        upload_data = pd.DataFrame([{"TimeStamp": timestamp, "Ticker1": ticker1, "Ticker2": ticker2, "size1": size1,
                                     "size2": size2, "Price1": price1, "Price2": price2, "strategy_size1":size1, "strategy_size2":size2}])

        mongod.conn.frame_to_mongo(upload_data)

    @staticmethod
    def get_pair_open_position(database="pair_trade_log",split=True):
        def get_pair_trade_log(ticker_combo, database="pair_trade_log"):

            mongod = mongo(database, ticker_combo)
            try:
                result = pd.DataFrame(mongod.conn.table.find().sort("TimeStamp", -1))
            except Exception as e:
                print(e)
                result = pd.DataFrame()
            return result

        mongod = mongo(database)
        working = mongod.conn.db.list_collection_names()
        sent = []

        for i in working:
            temp = get_pair_trade_log(i)
            if len(temp) > 0 and temp["size1"].sum() != 0:
                sent.append(i)
        if split:
            sent = [(x.split("_")[0], x.split("_")[1]) for x in sent]

        return sent

    @property
    def last_trade_at(self):
        if len(self._myLog) == 0:
            return None
        return self._myLog.sort_values("TimeStamp",ascending=True).iloc[-1]["TimeStamp"]

    @property
    def previous_shares_ticker1(self):
        return self._myLog.sort_values("TimeStamp", ascending=True).iloc[:-1]["size1"].sum()

    @property
    def previous_shares_ticker2(self):
        return self._myLog.sort_values("TimeStamp", ascending=True).iloc[:-1]["size2"].sum()
    @property
    def last_trade_shares_ticker1(self):
        if len(self._myLog) == 0:
            return 0
        return self._myLog.sort_values("TimeStamp", ascending=True).iloc[-1]["size1"]
    @property
    def last_trade_shares_ticker2(self):
        if len(self._myLog) == 0:
            return 0
        return self._myLog.sort_values("TimeStamp", ascending=True).iloc[-1]["size2"]
    @property
    def outstanding_shares_ticker1(self):
        return self._myLog["size1"].sum()
    @property
    def outstanding_shares_ticker2(self):
        return self._myLog["size2"].sum()

    def get_log(self):
        self.tradeLog = mongo("pair_trade_log", self.ticker_combo)
        self._myLog = pd.DataFrame(self.tradeLog.conn.table.find())
        if len(self._myLog) == 0:
            print(f"no pair trade log for {self.ticker1} and {self.ticker2}")
            self._myLog = pd.DataFrame([],columns=['_id', 'TimeStamp', 'Ticker1', 'Ticker2', 'size1', 'size2', 'Price1',
       'Price2'])
        return self._myLog

    @property
    def strategy_sizes(self):
        recent_signal = self_pair_trade(self.ticker1, self.ticker2, method="realtimeday", cash=TRADE_CASH)
        return recent_signal[recent_signal["size1"] != 0].iloc[-1]["size1"], recent_signal[recent_signal["size2"] != 0].iloc[-1]["size2"], recent_signal[recent_signal["size1"] != 0].iloc[-1]


    def fix_unsettle_trade(self):
        habitica = habiticaImp()
        open_position = client.current_positions()
        all_tickers = open_position.symbol.to_list()
        ID = self.last_trade_at

        if self.ticker1 not in all_tickers:
            diff = 0 - self.outstanding_shares_ticker1
            new = self.last_trade_shares_ticker1 + diff
            self.tradeLog.conn.table.update_one({"TimeStamp": ID}, {"$set": {"size1": new}})
            print("Fixed unsettled pair trade to size 0 " + str(self.ticker1))
        else:

            broker_quantity1 = float(open_position.loc[open_position.symbol == self.ticker1, "quantity"])
            ticker1_quantity = self.strategy_sizes[0]
            diff = ticker1_quantity - self.outstanding_shares_ticker1

            new = self.last_trade_shares_ticker1 + diff
            ## only update when broker size is smaller than the outstanding size, and update to strategy suggested size
            if self.outstanding_shares_ticker1 != broker_quantity1:
                habitica.create_a_todo("Unmatch Size for pair trade " + str(self.ticker1))
                # if np.abs(self.outstanding_shares_ticker1) > np.abs(broker_quantity1):
                #     self.tradeLog.conn.table.update_one({"TimeStamp": ID}, {"$set": {"size1": new}})
                #     print("Fixed unsettled pair trade to match size " + str(self.ticker1))

        if self.ticker2 not in all_tickers:
            diff = 0 - self.outstanding_shares_ticker2
            new = self.last_trade_shares_ticker2 + diff
            self.tradeLog.conn.table.update_one({"TimeStamp": ID}, {"$set": {"size2": new}})
            print("Fixed unsettled pair trade to size 0 " + str(self.ticker2))
        else:

            broker_quantity2 = float(open_position.loc[open_position.symbol == self.ticker2, "quantity"])
            ticker2_quantity = self.strategy_sizes[1]
            diff = ticker2_quantity - self.previous_shares_ticker2

            new = self.last_trade_shares_ticker2 + diff
            ## only update when broker size is smaller than the outstanding size, and update to strategy suggested size
            if self.outstanding_shares_ticker2 != broker_quantity2:
                habitica.create_a_todo("Unmatch Size for pair trade " + str(self.ticker2))
                # if np.abs(self.outstanding_shares_ticker2) > np.abs(broker_quantity2):
                #     self.tradeLog.conn.table.update_one({"TimeStamp": ID}, {"$set": {"size2": new}})
                #     send_email("Fixed unsettled pair trade to match size " + str(self.ticker2))
        self.get_log()