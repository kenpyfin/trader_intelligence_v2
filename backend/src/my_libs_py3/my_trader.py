from .my_lib import *
from .send_email import *
from .fmp import *
from .TD_Order import IBTrader
from .my_data import PriceDataFetcher
import talib as ta

#
#def hedge(self,hedge_int = "UVXY"):
#    robinhood = get_robinhood()
#    hedge_int_beta =beta([hedge_int],interval ="minute")[0].iloc[0][0]
#    hedge_int_price = robinhood.get_ask_price(hedge_int)
#    position_beta = robinhood.get_my_position_beta_minute()[0]
#    position_value = robinhood.my_trader.market_value()
#    shares = abs(np.floor(position_value*position_beta/hedge_int_beta/hedge_int_price))
#
#    return shares




#********************************************************

#   Price Modeling

#********************************************************

def fwd_price(ticker,spot0 = None,riskless_rate=0,mat = 1,val_num_steps = 30,val_num_paths = 50000,yield_ = 0 ):
    if spot0 is None:
        trader = IBTrader()
        spot0=trader.realtimequote(ticker)



    price_gett = PriceDataFetcher()
    vol = price_gett.get_price_data([ticker],method = "realtimeday",back_day= 30).Return.std()

    val_random_seed =  int(time.time())
    np.random.seed(val_random_seed)
    dt = float(mat)/ val_num_steps
    sqrt_dt = dt ** 0.5
    
    drift = (riskless_rate - yield_ - (vol ** 2) / 2) * dt
    result = np.empty([val_num_paths, val_num_steps])
    for path_num in range(val_num_paths):
        result1 = np.empty([val_num_steps])
        spot = spot0
        result1[0] = spot
        for step_num in range(1, val_num_steps):
            spot *= np.exp(drift + vol * np.random.normal() * sqrt_dt)
            if hasattr(yield_, '__call__'):
                div_t1, div_t2 = dt * step_num, dt * (step_num + 1)
                div = yield_(div_t1, div_t2)
                if is_number(div): spot -= div
            result1[step_num] = spot

        result[path_num] = result1
    return pd.DataFrame(result).mean().iloc[-1]
    

def fwd_return(ticker,riskless_rate=0,mat = 1,val_num_steps = 30,val_num_paths = 50000):
    price_gett = PriceDataFetcher()
    spot = price_gett.get_price_data([ticker],method = "self_minute").Close.iloc[-1]

    fprice = fwd_price(ticker,spot,riskless_rate,mat,val_num_steps,val_num_paths)
    print (fprice)
        
    return np.log(fprice/spot)


def fix_unsettled_trade_update(ticker, target_size):
    log = get_trade_log(ticker)
    if len(log)== 0:
        return None
    ID = log.iloc[-1]["TimeStamp"]
    last_size = log.iloc[-1]["size"]
    sum_size = log["size"].sum()
    diff = target_size - sum_size

    mongod = mongo("trade_log",ticker)
    mongod.conn.table.update_one({"TimeStamp":ID},{"$set":{"size":float(last_size+diff)}})


    
    
# def fix_unsettled_trade_update(ticker, size=0, partial=False):
#     mongod = mongo("trade_log")
#     db = mongod.db[ticker]
#     log = get_trade_log(ticker)
#     ID = get_trade_log(ticker).iloc[-1]["_id"]
#     if not partial:
#         log = get_trade_log(ticker)
#         ID = get_trade_log(ticker).iloc[-1]["_id"]
#         db.update_one({"_id":ID},{"$set":{"size":0}},upsert=False)
           
#     elif size == 0:
#         print ("Please enter size for partial size fix") 
#     else:
#         db.update_one({"_id":ID},{"$set":{"size":size}},upsert=False)



def log_trade(ticker,size, price, strategy , hold_days = None, database = "trade_log"):
    timestamp = datetime.now()
    mongod = mongo(database,ticker)
    if hold_days == None:
        upload_data = pd.DataFrame([{"TimeStamp":timestamp, "Ticker":ticker,"size":size,"raw_size":size,"Price":price,"Strategy":strategy}])
    else:
        upload_data = pd.DataFrame([{"TimeStamp":timestamp, "Ticker":ticker,"size":size,"raw_size":size,"Price":price,"Strategy":strategy, "Hold_days":hold_days}])
    
    mongod.conn.frame_to_mongo(upload_data)




# def log_trade(ticker,size, price, strategy , database = "trade_log"):
#     timestamp = datetime.now()
#     mongod = mongo(database)
#     mongod.db[ticker].insert({"TimeStamp":timestamp, "Ticker":ticker,"size":size,"Price":price,"Strategy":strategy})
#     collection = mongod.db[ticker]
#     get = collection.find().sort("TimeStamp",pymongo.ASCENDING)
#     get= pd.DataFrame(get)
# #     if get["size"].sum() == 0:
# #         collection.drop()

def is_open(ticker):
    if get_trade_log(ticker)["size"].sum() == 0:
        return False
    else:
        return True

def get_open_opsition(database = "trade_log", stratgy_filter = None): 
    mongod = mongo(database)
    working = mongod.conn.db.list_collection_names()
    sent = []
    if stratgy_filter == None:
        for i in working:
            temp = get_trade_log(i)
            if len(temp) > 0 and temp["size"].sum() != 0:
                sent.append(i)
    else:
        for i in working:
            temp = get_trade_log(i)
            if len(temp) > 0 and temp["size"].sum() != 0 and temp["Strategy"].iloc[0] == stratgy_filter:
                sent.append(i)

    return sent     

def get_trade_log(ticker,database = "trade_log"): 
    mongod = mongo(database,ticker)
    try:
        result = pd.DataFrame(mongod.conn.table.find()) 
    except Exception as e:
        print (e)
        result = pd.DataFrame()
    return result 

# def get_pair_open_opsition(database = "pair_trade_log"):
#     mongod = mongo(database)
#     working = mongod.conn.db.list_collection_names()
#     sent = []
#
#     for i in working:
#         temp = get_pair_trade_log(i)
#         if len(temp) > 0 and temp["size1"].sum() != 0:
#             sent.append(i)
#
#     return sent
#
# def get_pair_trade_log(ticker_combo,database = "pair_trade_log"):
#
#     mongod = mongo(database,ticker_combo)
#     try:
#         result = pd.DataFrame(mongod.conn.table.find().sort("TimeStamp",-1))
#     except Exception as e:
#         print (e)
#         result = pd.DataFrame()
#     return result



def vwap(ticker,method = "intraday", back_day = 1, return_table= False ):
    price_getter = PriceDataFetcher()
    price = price_getter.get_price_data([ticker],method=method,back_day=back_day)

    price["Traded_Cash"] = price.Close * price.Volume

    price["Traded_Cash_cum"] = price["Traded_Cash"].cumsum()

    price["Volume_cum"] = price.Volume.cumsum()

    price["VWAP"] = price["Traded_Cash_cum"]/price["Volume_cum"]
    
    vwap = price["Traded_Cash"].sum()/price.Volume.sum()

    # Round the VWAP price to the appropriate tick size
    if isinstance(ticker, str) and ticker.startswith('/'):  # Futures contract
        vwap = round(vwap * 4) / 4  # For 0.25 tick size
    else:  # Stocks
        vwap = round(vwap * 100) / 100  # For 0.01 tick size

    if return_table:
        return price
    else:
        return vwap


def var_normal(ticker, method = "intraday", sv= 0.05, timeperiod=50):
    price_getter = PriceDataFetcher()
    price = price_getter.get_price_data([ticker],method=method)
    price["Return"] = (price.Close-price.Close.shift(1))/price.Close.shift(1)
    mean = price.Return[-timeperiod:].mean()
    std = price.Return[-timeperiod:].std()
    return abs(mean + std*scipy.special.ndtri(sv))*price.Close.iloc[-1]


def hedge(ticker,method = "self_minute",hedge_int = "VIXY",target_beta =0.0):
    trader = IBTrader()
    hedge_int_beta =beta([hedge_int],interval ="minute")["betas"].iloc[0][0]
    hedge_int_price = trader.realtimequote(hedge_int)
    position_beta = beta([ticker],interval ="minute")["betas"].iloc[0][0]
    position_value = trader.realtimequote(ticker)
    shares = np.ceil(position_value*(target_beta-position_beta)/hedge_int_beta/hedge_int_price)
    return ("To headge %s beta to "%ticker + str(target_beta) + " please trade " + str(shares) + " share of " +str(hedge_int) + "<br>" + "Total Beta is {:1.4f}".format(position_beta))\
            ,shares


def beta(ticker_list,bench = "SPY", interval="day", past_days = 90 ):    
    # will return a dataframe
    price_getter = PriceDataFetcher()
    betas = []
    volos = []
    ben_mark=pd.DataFrame()
    if interval == "day":
        ben_mark= price_getter.get_price_data([bench],"realtimeday",start_date = datetime.now()-timedelta(days=past_days))
        ben_mark=ben_mark.rename(columns ={"Close":bench})
        ben_mark[bench]=ben_mark[bench].astype(float)
        
    elif interval == "minute":
        ben_mark = price_getter.get_price_data([bench],"self_minute",start_date = datetime.now()-timedelta(days=past_days))
        ben_mark=ben_mark.rename(columns ={"Close":bench})
        ben_mark[bench]=ben_mark[bench].astype(float)
    ben_mark[bench + "_bench_re"] = log(ben_mark[bench]/ben_mark[bench].shift(1))
    #print ben_mark[bench + "_bench_re"]
    covmat = np.array([[np.nan, np.nan], [np.nan, np.nan]])
    for i in list(ticker_list):

        new=[]
        ticker = str(i)
        
        try:
            if interval =="day":
                #stock = da.DataReader(str(ticker),"yahoo",datetime.now()-timedelta(days=90),datetime.now())
                stock= price_getter.get_price_data([ticker],"realtimeday",start_date = datetime.now()-timedelta(days=past_days))
                stock = stock.rename(columns = {"Close":ticker})
                stock[ticker] = stock[ticker].astype(float)
            elif interval == "minute":
                stock= price_getter.get_price_data([ticker],"self_minute",start_date = datetime.now()-timedelta(days=past_days))
                stock=stock.rename(columns ={"Close":ticker})
                stock[ticker] = stock[ticker].astype(float)
        except:
            print((ticker+" ticker maybe wrong. Error in getting data"))
            betas.append(np.NaN)
            continue

        # get return and put them in a new dataframe
        
        stock[ticker + "_stock_re"] = log(stock[ticker]/stock[ticker].shift(1))
        #new = pd.concat([ben_mark,stock],axis =1)
        new = pd.DataFrame({bench:ben_mark[bench],bench + "_bench_re":ben_mark[bench + "_bench_re"],ticker:stock[ticker],ticker + "_stock_re":stock[ticker + "_stock_re"]})
        #new = new[[bench,bench + "_bench_re",ticker, ticker + "_bench_re"]]
        new = new.dropna()
        
        #calculate beta using covariance matrix
        print ("Bench first")
        covmat = np.cov(new[bench+ "_bench_re"],new[ticker+ "_stock_re"])
        print(covmat)
        #beta = covmat[0,1]/  np.sqrt(covmat[1,1]*covmat[0,0])
        beta = covmat[0,1]/ covmat[0,0]
        volotity = sqrt(covmat[1,1])
        betas.append(beta)
        volos.append(volotity)
    betas = pd.DataFrame(betas)
    betas.index = ticker_list
    betas.columns=["Beta"]
    return {"betas": betas, "covmat": covmat, "volos": volos}

def self_pair_trade(i, j, cash=2000, back_day=365, if_signal = False, window=20, trader = None, fall_back=True):
    def align_prices(price1, price2):
        for inx in price1.index:
            if inx not in price2.index:
                price1.loc[inx, :] = np.NaN
                price1 = price1.dropna(subset=["Ticker"])
        for inx in price2.index:
            if inx not in price1.index:
                price2.loc[inx, :] = np.NaN
                price2 = price2.dropna(subset=["Ticker"])
        return price1, price2

    def calculate_indicators(price_table, price1, price2, window):
        for i in range(1, len(price_table)):
            j = i - window
            if j < 0:
                j = 0
                
            x_data = price1.log_ret.iloc[j:i]
            y_data = price2.log_ret.iloc[j:i]
            
            if len(x_data.unique()) <= 1 or len(y_data.unique()) <= 1:
                print(f"Warning: Insufficient price variation for regression at index {i}")
                print(f"Unique x values: {len(x_data.unique())}, Unique y values: {len(y_data.unique())}")
                price_table.loc[price_table.index[i], "slope"] = price_table.loc[price_table.index[i-1], "slope"] if i > 1 else 0
            else:
                price_table.loc[price_table.index[i], "slope"] = stats.linregress(x_data, y_data)[0]
            
            # Get the price data using proper indexing
            stock1_slice = price_table.iloc[j:i]["stock1"]
            stock2_slice = price_table.iloc[j:i]["stock2"]
            
            # Calculate hedge ratios using proper DataFrame slices
            price_table.loc[price_table.index[i], "hedge_ratio"] = \
                sm.OLS(stock2_slice, stock1_slice).fit().params[0]
            price_table.loc[price_table.index[i], "hedge_ratio2"] = \
                sm.OLS(stock1_slice, stock2_slice).fit().params[0]

    def buy_line(slope):
        if slope > 0.5:
            return -1.25
        elif slope > 0.75:
            return -1
        elif slope < -0.5:
            return -2.25
        elif slope < -0.75:
            return -2.75
        else:
            return -2

    def sell_line(slope):
        if slope > 0.5:
            return 1.25
        elif slope > 0.75:
            return 1
        elif slope < -0.5:
            return 2.25
        elif slope < -0.75:
            return 2.75
        else:
            return 2

    def initialize_trade_columns(price_table, cash):
        price_table["cash"] = cash
        price_table["buying_power"] = cash
        price_table["margin1"] = 0
        price_table["margin2"] = 0
        price_table["size1"] = 0
        price_table["size2"] = 0
        price_table["holddays"] = 0

    def close_positions(price_table, i):
        price_table.loc[i, "cash"] += (price_table.loc[i, "size1"]) * price_table.loc[i, "stock1"]
        price_table.loc[i, "cash"] += (price_table.loc[i, "size2"]) * price_table.loc[i, "stock2"]
        price_table.loc[i, "buying_power"] = price_table.loc[i, "cash"]
        price_table.loc[i, "size1"] = 0
        price_table.loc[i, "size2"] = 0
        price_table.loc[i, "margin1"] = 0
        price_table.loc[i, "margin2"] = 0
        price_table.loc[i, "holddays"] = 0
        return price_table

    def open_positions(price_table, i, action):


        if action == "buy":
            share_1 = round(price_table.loc[i, "buying_power"] / (
                    price_table.loc[i, "stock1"] + price_table.loc[i, "stock1"] * price_table.loc[i, "hedge_ratio"])) - price_table.loc[i, "size1"]
            share_2 = round(-share_1 * price_table.loc[i, "hedge_ratio"]) - price_table.loc[i, "size2"]

            if price_table.loc[i, "buying_power"] >= abs(share_1) * price_table.loc[i, "stock1"] + abs(share_2) * price_table.loc[i, "stock2"]:
                price_table.loc[i, "size1"] = share_1
                price_table.loc[i, "size2"] = share_2
                price_table.loc[i, "margin2"] = abs(price_table.loc[i, "stock2"] * share_2)
                price_table.loc[i, "cash"] -= (
                            price_table.loc[i, "stock1"] * share_1 + price_table.loc[i, "stock2"] * share_2)
                price_table.loc[i, "buying_power"] = price_table.loc[i, "cash"] - price_table.loc[i, "margin2"]

        elif action == "sell":
            share_2 = round(price_table.loc[i, "buying_power"] / (
                    price_table.loc[i, "stock2"] + price_table.loc[i, "stock2"] * price_table.loc[i, "hedge_ratio2"])) - price_table.loc[i, "size2"]
            share_1 = round(-share_2 * price_table.loc[i, "hedge_ratio2"]) - price_table.loc[i, "size1"]

            if price_table.loc[i, "buying_power"] >= abs(share_1) * price_table.loc[i, "stock1"] + abs(share_2) * price_table.loc[i, "stock2"]:
                price_table.loc[i, "size1"] = share_1
                price_table.loc[i, "size2"] = share_2
                price_table.loc[i, "margin1"] = abs(price_table.loc[i, "stock1"] * share_1)
                price_table.loc[i, "cash"] -= (
                            price_table.loc[i, "stock1"] * share_1 + price_table.loc[i, "stock2"] * share_2)
                price_table.loc[i, "buying_power"] = price_table.loc[i, "cash"] - price_table.loc[i, "margin1"]

        return price_table

    def sync_next_bar(price_table, i, i_1):
        price_table.loc[i_1, "size1"] = price_table.loc[i, "size1"]
        price_table.loc[i_1, "size2"] = price_table.loc[i, "size2"]
        price_table.loc[i_1, "cash"] = price_table.loc[i, "cash"]
        price_table.loc[i_1, "buying_power"] = price_table.loc[i, "buying_power"]
        price_table.loc[i_1, "margin1"] = price_table.loc[i, "margin1"]
        price_table.loc[i_1, "margin2"] = price_table.loc[i, "margin2"]
        price_table.loc[i_1, "holddays"] = price_table.loc[i, "holddays"]
        price_table.loc[i_1, "total_value"] = price_table.loc[i, "total_value"]


    def execute_trades(price_table):
        for i in range(len(price_table)):
            if i != len(price_table) - 1:
                i_1 = price_table.index[i + 1]
            else:
                i_1 = price_table.index[i]
            i = price_table.index[i]

            if price_table.loc[i, "size1"] != 0 or price_table.loc[i, "size2"] != 0:
                price_table.loc[i, "holddays"] += 1

            if price_table.loc[i, "holddays"] >= 7:
                price_table = close_positions(price_table, i)

            if price_table.loc[i, "z_score"] < price_table.loc[i, "buy_line"] and price_table.loc[i, "size1"] <= 0:
                price_table = open_positions(price_table, i, "buy")

            if price_table.loc[i, "z_score"] > price_table.loc[i, "sell_line"] and price_table.loc[i, "size1"] >= 0:
                price_table = open_positions(price_table, i, "sell")

            price_table.loc[i, "total_value"] = price_table.loc[i, "stock1"] * price_table.loc[i, "size1"] + \
                                                price_table.loc[i, "stock2"] * price_table.loc[i, "size2"] + \
                                                price_table.loc[i, "cash"]

            sync_next_bar(price_table, i, i_1)

    price_getter = PriceDataFetcher(trader)
    method = "td_data" if if_signal else "self_minute"
    price1 = price_getter.get_price_data([i], method=method, back_day=back_day, fmp_switch=True, fall_back=fall_back)
    if len(price1) == 0:
        raise Exception("Price not available")
    if not if_signal:
        # resample to Day grain and get averager
        price1['TimeStamp'] = pd.to_datetime(price1['TimeStamp'])
        price1 = price1.set_index("TimeStamp")
        # Exclude non-numeric columns from resampling
        numeric_cols = price1.select_dtypes(include=['float64', 'int64']).columns
        price1_resampled = price1[numeric_cols].resample("D").mean()
        price1 = price1_resampled.dropna(subset=["Close"])
        # Add back the Ticker column after resampling
        price1["Ticker"] = i
    else:
        price1 = price1.set_index("TimeStamp")

    price2 = price_getter.get_price_data([j], method=method, back_day=back_day, fmp_switch=True, fall_back=fall_back)
    if len(price2) == 0:
        raise Exception("Price not available")
    if not if_signal:
        # resample to Day grain and get averager
        price2['TimeStamp'] = pd.to_datetime(price2['TimeStamp'])
        price2 = price2.set_index("TimeStamp")
        # Exclude non-numeric columns from resampling
        numeric_cols = price2.select_dtypes(include=['float64', 'int64']).columns
        price2_resampled = price2[numeric_cols].resample("D").mean()
        price2 = price2_resampled.dropna(subset=["Close"])
        # Add back the Ticker column after resampling
        price2["Ticker"] = j
    else:
        price2 = price2.set_index("TimeStamp")

    price1, price2 = align_prices(price1, price2)

    if len(price1) < int(back_day) / 3 or len(price2) < int(back_day) / 3:
        raise Exception("Not enough valid price history")

    price1["log_ret"] = np.log(price1.Close / price1.Close.shift(1))
    price2["log_ret"] = np.log(price2.Close / price2.Close.shift(1))

    price1["log_ret_mv"] = price1.log_ret.rolling(window).mean()
    price2["log_ret_mv"] = price2.log_ret.rolling(window).mean()

    price1 = price1.fillna(method="bfill")
    price2 = price2.fillna(method="bfill")

    price_table = pd.DataFrame()
    price_table["relative"] = price1.log_ret_mv / price2.log_ret_mv
    price_table["relative_mv"] = price_table["relative"].rolling(window, min_periods=window).mean()
    price_table["relative_mv"] = abs(price_table["relative_mv"])
    

    price1 = price1.rename(columns={"Close": "stock1"})
    price2 = price2.rename(columns={"Close": "stock2"})
    price_table = price_table.join(price1["stock1"])
    price_table = price_table.join(price2["stock2"])
    price_table = price_table.dropna(subset=["stock1", "stock2"])


    calculate_indicators(price_table, price1, price2, window)

    price1["volatility"] = price1.log_ret.rolling(window).std()
    price2["volatility"] = price2.log_ret.rolling(window).std()

    price_table["z_score"] = (price_table["relative"] - price_table["relative_mv"]) / price_table.relative.std()

    # up, mid , low = ta.BBANDS(price1.Close*price_table.hedge_ratio)
    try:
        up, mid, low = ta.BBANDS(price_table["z_score"])
        bb = pd.DataFrame({"up": up, "mid": mid, "low": low})
        price_table = price_table.join(bb)
    except Exception as e:
        if "inputs are all NaN" in str(e):
            pass
        else:
            raise Exception(e)


    price_table = price_table.fillna(method="bfill")

    price_table["buy_line"] = price_table.slope.apply(buy_line)
    price_table["sell_line"] = price_table.slope.apply(sell_line)

    initialize_trade_columns(price_table, cash)

    execute_trades(price_table)


    return price_table



