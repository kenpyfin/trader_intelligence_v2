from abc import ABC
from my_libs_py3 import *

class TradingPlan(ABC):

    '''

    This is the base class for each trading plan

    In the docstring, you should specify

    - Trading style

    - Trading type

    - Take profit style

    - Take loss style

    - Bail-out indicator

    '''


    def __init__(self,trader):
        self._position_size = None
        self._holding_period = None
        self._position_money = None
        self.strategy_name = None
        self.trader = trader
        self.buying_power = self.robinhood.get_buying_power()
        self.cash_reserve = trading_param["cash_reserve"]



    # TODO
    # need some extra structure to look at what indicator to look at

    def buying_power_check(self) -> bool:
        return self.buying_power > self.cash_reserve

    def _buy_action(self, inst: str, size: float):
        pass

    def _sell_action(self, inst: str, size: float):
        if self.robinhood.place_sell_bulk_checkup(ticker_list=[inst],
                                                  quantity_list=[log["size"].sum()]) == "Trade Success!":
            log_trade(inst, -log["size"].sum(), self.robinhood.get_last_price(inst), self.strategy_name)


    def data_feeder(self):
        pass


    @property
    def holding_period(self):
        return self._holding_period
    @holding_period.setter
    def holding_period(self, value):
        self._holding_period = value

    @property
    def position_money(self):
        return self._position_money
    @position_money.setter
    def position_money(self, value):
        self._position_money = value

    @property
    def stop_loss(self):
        return self._stop_loss
    @stop_loss.setter
    def stop_loss(self, value):
        self._stop_loss = value

    def instrument_selector(self):
        pass

    def entry_signal(self, inst: str) -> bool:
        pass

    def exit_signal(self, inst: str) -> bool:
        pass

    def take_profit(self) -> bool:
        pass

    def bail_out(self) -> bool:
        pass

    def _the_log(self, inst: str):
        log = get_trade_log(inst)
        log = log[log.Strategy == self.strategy_name]
        return log

    def check_log(self):
        '''

        A method to go through open position

        '''
        result = []
        tickers = get_open_opsition()
        for i in tickers:
            i.encode("ASCII")
            log = self._the_log(i)
            if len(log) == 0:
                continue
            result.append(i)
        print("pass log check")
        return result


    def trade_executor(self):
        pass



#########################

## subclass

#########################


class longterm_cumulation(TradingPlan):

    def __init__(self):
        super().__init__()
        self.strategy_name = "Fundamental"
        self.position_money = trading_param["fundamental_money"]


    def data_feeder(self):
        mongod = mongo("all_symbol", "screenerModel")

        ## This line gets the max refresh_date
        tos = pd.DataFrame(mongod.conn.table.find({}, {"Refresh_Date": 1, "_id": 0}).sort("Refresh_Date", -1).limit(1))[
            "Refresh_Date"].iloc[0]

        fun_table = pd.DataFrame(mongod.conn.table.find({"Refresh_Date": tos}, {"_id": 0}))

        target = ["P/Cash", "Analyst Recom", "P/S", "Total Debt/Equity", "P/Free Cash Flow", "P/E", "Insider Ownership",
                  "Gross Margin", "Current Ratio", "Sales growth quarter over quarter", "Profit Margin", "Quick Ratio",
                  "Performance (Week)", "Institutional Ownership", "EPS (ttm)", "Operating Margin"]

        fun_table["sum_rank"] = pd.DataFrame.sum(fun_table[target], axis=1, skipna=True, numeric_only=True)
        fun_table["avg_rank"] = pd.DataFrame.mean(fun_table[target], axis=1, skipna=True, numeric_only=True)
        return fun_table

    # def check_log(self):
    #     tickers = get_open_opsition()


    def instrument_selector(self):
        fun_table = self.data_feeder()

        for i in fun_table.index:
            relative_rank = fun_table.loc[i, "avg_rank"] / fun_table.loc[
                fun_table.Sector == fun_table.loc[i, "Sector"], "Sector"].count()
            fun_table.loc[i, "relative_rank"] = relative_rank
        #     fun_table.loc[i,"relative_rank"] = fun_table.loc[i,"avg_rank"]

        fun_table = fun_table.sort_values("relative_rank")

        target_list = fun_table.Ticker.to_list()

        return target_list

    def entry_signal(self, inst: str) -> bool:
        ##  Check buy signal
        # check we have enough buying power after reserver

        price_14 = get_price_data([inst], method='day', back_day=14)
        price_31 = get_price_data([inst], method='day', back_day=31)
        price_60 = get_price_data([inst], method='day', back_day=60)
        price_180 = get_price_data([inst], method='day', back_day=180)
        quote = realtimequote(inst).price.iloc[0]

        return self.buying_power_check() and quote < price_14.Close.mean() and \
                        quote > price_31.Close.mean() and quote > price_60.Close.mean()

    def exit_signal(self, inst: str) -> bool:
        try:
            cost = self.robinhood.get_average_cost(inst)
        except:
            send_email("%s not in portfolio" % inst)
            return False
        quote = realtimequote(inst).price.iloc[0]
        if (quote - cost) / cost > trading_param["fundamental_harvest"]:
            send_email("Fundamental Out-Of-List Sell: %s" % inst)
            return True
        elif inst not in self.instrument_selector()[:20]:
            send_email("Fundamental Cumulation Sell: %s" %inst)
            return True
        else:
            return False

    def trade_executor(self):
        # buy on low or buy on high
        for i in self.instrument_selector()[:8]:
            if self.entry_signal(i):
                quote = realtimequote(i).price.iloc[0]
                size = np.ceil(self.position_money / quote)
                self._buy_action(i,size)
                send_email("Fundamental Cumulation Sell: %s" % i)

        # sell signal
        for i in self.check_log():
            if self.exit_signal(i):
                size = np.ceil(self._the_log(i)["size"].sum() * trading_param["fundamental_harvest_prop"])
                self._sell_action(i,size)



        print("pass fundamental")





