import sys,os
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import base64
import requests
import json
import csv
import time
import timeit
import pytz
import numpy as np
from pandas import *
import xlrd
from datetime import datetime
import pandas as pd
import numpy as np
from numpy import log, polyfit, sqrt, std, subtract
import statsmodels
import statsmodels.tsa.stattools as ts
import statsmodels.api as sm
from statsmodels.regression.linear_model import OLS
from statsmodels.tsa.tsatools import lagmat, add_trend
from statsmodels.tsa.adfvalues import mackinnonp
import matplotlib.pyplot as plt
import seaborn as sns
import pprint
from datetime import timedelta
from scipy import stats
import scipy
import pymongo
from tqdm import tqdm
import urllib.request, urllib.error, urllib.parse
# import multiprocessing
from ib_insync import IB, util as ibutil
from finvizfinance.stock import Stock


pd.set_option("display.max_columns",80)
pd.options.display.float_format = '{:,.4f}'.format



############################################

## Must use full path for CRONTAB to work
############################################


def read_json(filepath):
    read = []
    with open(filepath, "r") as f:
        read.append(f.readlines())
    read = "".join(read[0]).replace("\n"," ")
    return json.loads(read)

if os.path.exists("/opt/airflow"):
    home_dir="/opt/airflow/notebook"
else:
    home_dir = "/home/ken/big_storage/airflowProd/airflow_notebook"

gecko_download_path = home_dir + "/My_Trader/file/"
gecko_path = "http://10.0.1.22:4444/wd/hub"

# home_dir = "/home/ken/airflowProd/"
# home_dir="/opt/airflow/"
# home_dir=os.getcwd() + "/"

# directory = home_dir + "file/"
directory = home_dir+ "/My_Trader/file/"
working_suggestion = "Trade_suggestion_minute_1st"
universe_file_name = "my_universe_industry_sector_marketcap_earnings.csv"
root_directory = home_dir + "/My_Trader/"

############################################
#Read trading parameter
############################################

# trading_param = read_json(directory+"trading_param.json")


## Timezone
mytz = pytz.timezone("US/Pacific")





def read_mongo_time(x, timezone = "US/Pacific"):
    return change_timezone(datetime.utcfromtimestamp(0) + timedelta(milliseconds= x), timezone)



def unix_time_millis(dt):
    epoch = datetime.utcfromtimestamp(0)
    return (dt - epoch).total_seconds() * 1000


def variance_ratio(ts, lag = 2):
    """
    Returns the variance ratio test result
    """
    # make sure we are working with an array, convert if necessary
    ts = np.asarray(ts)
    
    # Apply the formula to calculate the test
    n = len(ts)
    mu  = sum(ts[1:n]-ts[:n-1])/n;
    m=(n-lag+1)*(1-lag/n);
    b=sum(np.square(ts[1:n]-ts[:n-1]-mu))/(n-1)
    t=sum(np.square(ts[lag:n]-ts[:n-lag]-lag*mu))/m
    return t/(lag*b);


 
def adf(ts, maxlag=1):
    """
    Augmented Dickey-Fuller unit root test
    """
    # make sure we are working with an array, convert if necessary
    ts = np.asarray(ts)
     
    # Get the dimension of the array
    nobs = ts.shape[0]
         
    # Calculate the discrete difference
    tsdiff = np.diff(ts)
     
    # Create a 2d array of lags, trim invalid observations on both sides
    tsdall = statsmodels.tsa.tsatools.lagmat(tsdiff[:, None], maxlag, trim='both', original='in')
    # Get dimension of the array
    nobs = tsdall.shape[0] 
     
    # replace 0 xdiff with level of x
    tsdall[:, 0] = ts[-nobs - 1:-1]  
    tsdshort = tsdiff[-nobs:]
     
    # Calculate the linear regression using an ordinary least squares model    
    results = statsmodels.regression.linear_model.OLS(tsdshort, statsmodels.tsa.tsatools.add_trend(tsdall[:, :maxlag + 1], 'c')).fit()
    adfstat = results.tvalues[0]
     
    # Get approx p-value from a precomputed table (from stattools)
    pvalue = mackinnonp(adfstat, 'c', N=1)
    return pvalue
 
def cadf(x, y):
    """
    Returns the result of the Cointegrated Augmented Dickey-Fuller Test
    """
    # Calculate the linear regression between the two time series
    ols_result = statsmodels.regression.linear_model.OLS(x, y).fit()
     
    # Augmented Dickey-Fuller unit root test
    return adf(ols_result.resid)





#********************************************************

# Some functions

#********************************************************


def change_timezone(utctime, timezonestr):
    
    local = pytz.timezone(timezonestr)
    return utctime.replace(tzinfo = pytz.utc).astimezone(tz = local)




#********************************************************

# Class File

#********************************************************



class write_my_csv:
    def __init__(self, filename, header_list,new_flag=True):
        self.filename = filename
        if new_flag:
            with open(self.filename,"wb") as myfile:
                writer = csv.writer(myfile,delimiter=',')
                writer.writerows(header_list)

    def write_row(self,data_list_tuple):
        with open(self.filename,"ab") as myfile:
            writer = csv.writer(myfile,delimiter=',')
            writer.writerows(data_list_tuple)

        

                



#yahoo finance


# class yahoo_historicals:



#     def get_historicals(self,stock, start,end):

#         # download dataframe
#         #start ="2017-01-01"
#         #end="2017-04-30"
#         data = pdr.get_data_yahoo(stock, start, end)

#         return data


# def update_price():
#     tradeable = pd.read_csv("file/cantrade.csv")
#     tradeable = tradeable.dropna()

#     error = []


#     yahoo = yahoo_historicals()
#     start ="2017-10-1"
#     end=datetime.now()
#     price=pd.DataFrame()




#     for i in list(tradeable.Ticker):
#         trial = 0
#         while trial <3:
#             try:
#                 temp = da.DataReader(i,"yahoo",start,end)
#                 index= pd.MultiIndex.from_product([[i],temp.index])
#                 temp=pd.DataFrame(data=temp.values,index=index,columns=temp.columns)
#                 price = price.append(temp)

#                 print "Finished", i
#                 #time.sleep(5)
#                 trial=3

#             except:
#                 print "error occorded in getting yahool historicals for ", i
#                 trial +=1
#                 if trial == 3:
#                     error.append([i,'get_yahoo_historicals'])
#     # get rid of the multiindex
#     price = price.reset_index()


#     price.Close = price["Adj Close"]
#     price = price.rename(columns={'Unnamed: 0':'Ticker','Unnamed: 1':"TimeStamp"})
#     price["Return"]= price.Close.diff(1)/price.Close

#     '''
#     # make sure DataFrames are the same length

#     price_date = pd.DataFrame()

#     min_date = max(price.loc[price.Ticker==i].TimeStamp.iloc[0] for i in price.Ticker)
#     max_date = min(price.loc[price.Ticker==i].TimeStamp.iloc[-1] for i in price.Ticker)
#     print "2"
#     for i in price.Ticker:
#         price_date = price_date.append(price.loc[price.Ticker==i][(price.loc[price.Ticker==i].TimeStamp>= min_date) & (price.loc[price.Ticker==i].TimeStamp <= max_date)] )

#     price = price_date

#     print "done"

#     '''
gateway = home_dir + "/My_Trader/record-Copy1.txt"
# gateway = home_dir + "record-Copy1.txt"

#     industry_sector_earnings = pd.read_csv("file/my_universe_industry_sector_marketcap_earnings.csv")
#     #earnings = pd.read_csv("my_universe_earnings.csv")

#     industry_sector_earnings = industry_sector_earnings.dropna()



#     for i in list(set(price.Ticker)):

#         #print price .loc[price.Ticker==i]

#         #price.groupby('Ticker').get_group(list(set(price.Ticker))[i])
#         #price.loc[price.Ticker==i,"ADX"]= ta.ADX(price.loc[price.Ticker==i].High.values, price.loc[price.Ticker==i].Low.values, price.loc[price.Ticker==i].Close.values, timeperiod=14)
#         price.loc[price.Ticker==i,"ADXR"]= ta.ADXR(price.loc[price.Ticker==i].High.values, price.loc[price.Ticker==i].Low.values, price.loc[price.Ticker==i].Close.values, timeperiod=14)
#         price.loc[price.Ticker==i,"APO"]= ta.APO(price.loc[price.Ticker==i].Close.values, fastperiod=12, slowperiod=26, matype=0)
#         price.loc[price.Ticker==i,"AROONOSC"]= ta.AROONOSC(price.loc[price.Ticker==i].High.values,price.loc[price.Ticker==i].Close.values, timeperiod=14)
#         price.loc[price.Ticker==i,"CCI"]= ta.CCI(price.loc[price.Ticker==i].High.values,price.loc[price.Ticker==i].Low.values,price.loc[price.Ticker==i].Close.values, timeperiod=14)
#         price.loc[price.Ticker==i,"MFI"]= ta.MFI(price.loc[price.Ticker==i].High.values, price.loc[price.Ticker==i].Low.values, price.loc[price.Ticker==i].Close.values, price.loc[price.Ticker==i].loc[price.Ticker==i].Volume.values.astype(float),timeperiod=14)
#         price.loc[price.Ticker==i,"MACD"], price.loc[price.Ticker==i,"MACD_signal"], price.loc[price.Ticker==i,"MACD_hist"] = ta.MACD(price.loc[price.Ticker==i].Close.values, fastperiod=12, slowperiod=26, signalperiod=9)
#         price.loc[price.Ticker==i,"ROCP"]= ta.ROCP(price.loc[price.Ticker==i].Close.values, timeperiod=10)
#         #price.loc[price.Ticker==i,"ROCR100"]= ta.ROCR100(price.loc[price.Ticker==i].Close.values, timeperiod=10)
#         price.loc[price.Ticker==i,"RSI"]= ta.RSI(price.loc[price.Ticker==i].Close.values, timeperiod=14)

#         print "\nDone:", i



#     final_update = pd.DataFrame()

#     for i in list(set(price.Ticker)):

#         final_update = final_update.append(price.loc[price.Ticker==i].iloc[-1])


#     final_update["Industry"] = np.NaN
#     final_update["Sector"] = np.NaN
#     final_update["Earnings_date"] = np.NaN
#     final_update["Market_cap"] = np.NaN
#     final_update["Industry_weight"] = np.NaN

    # for i in list(set(final_update.Ticker)):
    #     try:
    #         final_update.loc[final_update.Ticker==i,"Industry"] = industry_sector_earnings.loc[industry_sector_earnings.Ticker == i, "Industry"].values[0]
    #     except:

    #         print "nan occorded"

    # for i in list(set(final_update.Ticker)):
    #     try:
    #         final_update.loc[final_update.Ticker==i,"Sector"] = industry_sector_earnings.loc[industry_sector_earnings.Ticker == i, "Sector"].values[0]
    #     except:

    #         print "nan occorded"
    # for i in list(set(final_update.Ticker)):
    #     try:
    #         final_update.loc[final_update.Ticker==i,"Earnings_date"] = industry_sector_earnings.loc[industry_sector_earnings.Ticker == i, "Earnings_date"].values[0]
    #     except:

    #         print "nan occorded"

    # for i in list(set(final_update.Ticker)):
    #     try:
    #         final_update.loc[final_update.Ticker==i,"Market_cap"] = industry_sector_earnings.loc[industry_sector_earnings.Ticker == i, "Market_cap"].values[0]
    #     except:

    #         print "nan occorded"



#     #final_update.to_csv("final"+str(price.loc[price.Ticker==i][-1]["Date"])+".csv")


#     #get industrial makcap_weight

#     for ind in set(final_update.Industry):
#         for tic in set(final_update.loc[final_update.Industry==ind].Ticker):
#             final_update.loc[final_update.Ticker==tic,'Industry_weight']=final_update.loc[final_update.Ticker==tic,"Market_cap"] / final_update.loc[final_update.Industry==ind,"Market_cap"].sum()


#     #final_update = final_update[['Ticker','TimeStamp', 'Open', 'High', 'Low', 'Close', 'Volume',
#     #        'Return','ADXR','AROONOSC','APO','CCI','MACD', 'MACD_hist',
#     #       'MACD_signal','MFI','ROCP','RSI','Industry','Sector']]
#     final_update = final_update[['Ticker','TimeStamp', 'Open', 'High', 'Low', 'Close', 'Volume',
#             'Return','ADXR','AROONOSC','APO','CCI','MACD', 'MACD_hist',
#            'MACD_signal','MFI','ROCP','RSI','Industry','Sector','Market_cap','Industry_weight','Earnings_date']]

#     final_update =final_update.set_index("Ticker")

#     #final_update= final_update.dropna()




#     # Technical points rule

#     final_update["Technical_points"]=0
#     for i in final_update.index:
#         if final_update.loc[i].ADXR >= final_update.loc[final_update.Sector==final_update.loc[i].Sector].max().ADXR:
#             final_update.loc[i,'Technical_points'] += 1
#         if final_update.loc[i].APO >0:
#             final_update.loc[i,'Technical_points'] += 1
#         if final_update.loc[i].AROONOSC >= final_update.loc[final_update.Sector==final_update.loc[i].Sector].max().AROONOSC:
#             final_update.loc[i,'Technical_points'] += 1
#         if final_update.loc[i].CCI <-100:
#             final_update.loc[i,'Technical_points'] += 1
#         if final_update.loc[i].MACD > final_update.loc[i].MACD_signal:
#             final_update.loc[i,'Technical_points'] += 1
#         if final_update.loc[i].MFI <20:
#             final_update.loc[i,'Technical_points'] += 1
#         if final_update.loc[i].ROCP >0:
#             final_update.loc[i,'Technical_points'] += 1

#         print "Technical_points done: ", i
#     final_update= final_update.dropna()

#     final_update.to_csv("file/final_update.csv")
#     #***************************************

#     # get result

#     #***************************************

#     result = pd.DataFrame()
#     for i in set(final_update.Sector):
#         print i
#         print final_update.groupby("Sector").get_group(i).sort_values("Technical_points").iloc[-1].name
#         result = result.append(final_update.groupby("Sector").get_group(i).sort_values("Technical_points").iloc[-1])

#     result.to_csv("file/Trade_suggestion_1st" + str(result.TimeStamp[0])+".csv")

#     result = pd.DataFrame()
#     for i in set(final_update.Sector):
#         print i
#         print final_update.groupby("Sector").get_group(i).sort_values("Technical_points").iloc[-2].name
#         result = result.append(final_update.groupby("Sector").get_group(i).sort_values("Technical_points").iloc[-2])

#     result.to_csv("file/Trade_suggestion_2nd" + str(result.TimeStamp[0])+".csv")

#     result = pd.DataFrame()
#     for i in set(final_update.Sector):
#         print i
#         print final_update.groupby("Sector").get_group(i).sort_values("Technical_points").iloc[-2].name
#         result = result.append(final_update.groupby("Sector").get_group(i).sort_values("Technical_points").iloc[-2])

#     result.to_csv("file/Trade_suggestion_3rd" + str(result.TimeStamp[0])+".csv")
#     #"file/Trade_suggestion_minute_1st" + str(datetime.now())[0:10]+".csv"


#################################################################

#FOLLOWING IS BY SECTORS

#    result = pd.DataFrame()
#    for i in set(final_update.Sector):
#        try:
#            print i
#            print final_update.groupby("Sector").get_group(i).sort_values("Technical_points").iloc[-1].name
#            result = result.append(final_update.groupby("Sector").get_group(i).sort_values("Technical_points").iloc[-1])
#
#        except Exception as e:
#            result = result.append(pd.Series(([np.NaN])),ignore_index=True)
#            print e," no 1st suggestion", i
#            raise
#    if save_file:
#        result.to_csv( directory + save_file_name + "_1st"  +test + str(result.TimeStamp[0])[0:10].replace(":","-")+".csv")
#
#    result_1 = result
#
#    result = pd.DataFrame(columns = result.columns)
#    for i in set(final_update.Sector):
#        try:
#            print i
#            print final_update.groupby("Sector").get_group(i).sort_values("Technical_points").iloc[-2].name
#            result = result.append(final_update.groupby("Sector").get_group(i).sort_values("Technical_points").iloc[-2])
#        except Exception as e:
#            print e," no 2nd suggestion", i
#            result = result.append(pd.Series(pd.Series([np.NaN])),ignore_index=True)
#            pass
#    if save_file:
#        result.to_csv(directory + save_file_name + "_2nd" +test+ str(result.TimeStamp[0])[0:10].replace(":","-")+".csv")
#
#
#    result_2 = result
#
#    result = pd.DataFrame(columns = result.columns)
#    for i in set(final_update.Sector):
#        try:
#            print i
#            print final_update.groupby("Sector").get_group(i).sort_values("Technical_points").iloc[-3].name
#            result =

def remove_salt(x):
    return x.strip("\n").replace("$",'').replace("*",'')
#result.append(final_update.groupby("Sector").get_group(i).sort_values("Technical_points").iloc[-3])
#        except Exception as e:
#            print e," no 3rd suggestion, ", i
#            result = result.append(pd.Series([np.NaN]),ignore_index=True)
#            pass
#    if save_file:
#        result.to_csv(directory + save_file_name + "_3rd" +test+ str(result.TimeStamp[0])[0:10]+".csv")
#
#    result_3 = result
#
#    return result_1, result_2,result_3


#################################################################




#################################################################

def update_fundamentals(robinhood,my_list = False, test_mode=False,skip_can=True):
    # need to feed a logined robinhood instance
    error=[]
    mongod = mongo("all_symbol")
    if not skip_can:
        
#         ## Option 1: use FMP list
#         if type(my_list) ==bool:
#             if test_mode:
#                 universe = robinhood.get_universe()[1:10]
#             else:
#                 universe = robinhood.get_universe()
#         else:
#             universe = my_list
#         stock = list()
 
#         tradeable = universe[universe.price > 10]
#         tradeable.loc[:,"Ticker"] = tradeable["symbol"]
        
        
        ## Option 2: use Finviz list
        if type(my_list) ==bool:
            if test_mode:
                universe = mongod.conn.get_data("SELECT ticker,price,volume FROM all_symbol.`Screener_TOS`")[1:10]
            else:
                universe = mongod.conn.get_data("SELECT ticker,price,volume FROM all_symbol.`Screener_TOS`")
        else:
            universe = my_list
        stock = list()

        tradeable = universe[(universe.Price > 5) & (universe.Volume > 0)]
        
        
        
        tradeable.loc[:,"Symbol"] = tradeable["Ticker"]
        tradeable["Refresh_Date"] = datetime.now().strftime("%Y-%m-%d")
        mongod.conn.to_sql(tradeable,"all_symbol","cantrade",if_exists="append")
################# getting list directly from FMP ###########################
################  
#         tradeable_list = []
#         i = 0
#         trial = 0 
#         while i < len(universe.index):
#         #for i in range(len(universe.index)):
#             try:
#                 if robinhood.istradeable(str(universe.iloc[i])).values[0]:
#                     trade_price= get_price_data([str(universe.iloc[i])],method = "day").iloc[-1]["Close"]
#                     if trade_price > 5.00:
#                         new_get = {"Ticker":str(universe.iloc[i]),"Symbol":str(universe.iloc[i]), "Price":trade_price,"Refresh_Date":datetime.now().strftime("%Y-%m-%d")}
#                         tradeable_list.append(new_get)
#                         mongod.conn.to_sql(pd.DataFrame(new_get,index = [i]),"all_symbol","cantrade",if_exists="append")
                    
# #                         mongod.db["cantrade"].update_one({"Ticker":str(universe.iloc[i])},{"$set":{"Symbol":str(universe.iloc[i]), "Price":trade_price,"Refresh_Date":datetime.now().strftime("%Y-%m-%d")}},upsert=True)
#                     print ("Got cantrade: " + universe.iloc[i])
#                 i+=1
#                 trial = 0
# #                 time.sleep(1)
#             except Exception as e:
#                 print (str(e) + ". Timeout error, waiting\n" +str(universe.iloc[i]) )
#                 time.sleep(2)
#                 if trial >0:
#                     i+=1
#                     trial = 0
#                 trial += 1


#         tradeable = pd.DataFrame(tradeable_list)
        
#         mongod.frame_to_mongo(tradeable,"cantrade",drop_mode = "upsert", index_col = "Ticker")
        ## My own list
        mylist = pd.read_csv(directory+"mylist.csv")
        mylist["Refresh_Date"] = datetime.now().strftime("%Y-%m-%d")
        mylist.loc[:,"Ticker"] = mylist["Symbol"]
        mongod.conn.to_sql(pd.DataFrame(mylist),"all_symbol","cantrade",if_exists="append")
        tradeable = tradeable.append(mylist)
#         ## ETF List
#         mylist = pd.read_csv(directory+"ETFList.csv")
#         mylist["Refresh_Date"] = datetime.now().strftime("%Y-%m-%d")
#         mylist.loc[:,"Ticker"] = mylist["Symbol"]
#         mongod.conn.to_sql(pd.DataFrame(mylist),"all_symbol","cantrade",if_exists="append")
#         tradeable = tradeable.append(mylist)
        #get stock volumn
        
        tradeable.to_csv(directory+'cantrade.csv')
        

#         mongod.frame_to_mongo(tradeable,"cantrade",drop_mode = "drop", index_col = "Ticker")
        print ("cantrade done!\n")


    start = timeit.default_timer()
    if not isinstance(my_list, bool):
        tradeable = pd.DataFrame(my_list, columns=["Ticker"])
    else:
        tradeable = pd.read_csv(directory + "cantrade.csv")
        if "Unnamed: 0" in tradeable.columns:
            tradeable = tradeable.drop("Unnamed: 0", axis=1)

    # Initialize columns
    fund_cols = ['Industry', 'Sector', 'Market_cap', 'Earnings_date', "PEG", "Profit_Margin", 
                 "Avg_Volume", "Inst_Own", "Beta", "Current_Ratio", "PB", "Debt_to_Equity", 
                 "LDebt_to_Equity", "Sales", "ROE"]
    for col in fund_cols:
        tradeable[col] = np.NaN

    def _parse_finviz_value(value_str):
        if not isinstance(value_str, str) or value_str == '-':
            return np.nan
        value_str = value_str.strip()
        try:
            if value_str.endswith('%'):
                return float(value_str.rstrip('%')) / 100.0
            elif value_str.endswith('B'):
                return float(value_str.rstrip('B')) * 1e9
            elif value_str.endswith('M'):
                return float(value_str.rstrip('M')) * 1e6
            elif value_str.endswith('K'):
                return float(value_str.rstrip('K')) * 1e3
            return float(value_str)
        except (ValueError, TypeError):
            return value_str

    for i in range(len(tradeable.index)):
        try:
            ticker = tradeable['Ticker'].iloc[i]
            stock_finviz = Stock(ticker, verbose=0)
            fund = stock_finviz.ticker_fundament()
            
            idx = tradeable.index[i]
            tradeable.loc[idx, 'Industry'] = fund.get('Industry')
            tradeable.loc[idx, 'Sector'] = fund.get('Sector')
            tradeable.loc[idx, 'Market_cap'] = _parse_finviz_value(fund.get('Market Cap'))
            tradeable.loc[idx, 'Earnings_date'] = fund.get('Earnings')
            tradeable.loc[idx, "PEG"] = _parse_finviz_value(fund.get('PEG'))
            tradeable.loc[idx, "Profit_Margin"] = _parse_finviz_value(fund.get('Profit Margin'))
            tradeable.loc[idx, "Avg_Volume"] = _parse_finviz_value(fund.get('Avg Volume'))
            tradeable.loc[idx, "Inst_Own"] = _parse_finviz_value(fund.get('Inst Own'))
            tradeable.loc[idx, "Beta"] = _parse_finviz_value(fund.get('Beta'))
            tradeable.loc[idx, "Current_Ratio"] = _parse_finviz_value(fund.get('Current Ratio'))
            tradeable.loc[idx, "PB"] = _parse_finviz_value(fund.get('P/B'))
            tradeable.loc[idx, "Debt_to_Equity"] = _parse_finviz_value(fund.get('Debt/Eq'))
            tradeable.loc[idx, "LDebt_to_Equity"] = _parse_finviz_value(fund.get('LT Debt/Eq'))
            tradeable.loc[idx, "Sales"] = _parse_finviz_value(fund.get('Sales'))
            tradeable.loc[idx, "ROE"] = _parse_finviz_value(fund.get('ROE'))
            
            print ("get done! ", ticker)
            time.sleep(0.5) # Be respectful to Finviz servers
            
        except Exception as e:
            if test_mode:
                raise
            print ("get error ", tradeable['Ticker'].iloc[i])
            print (e)
            error.append([tradeable['Ticker'].iloc[i],'get_S_I_M_E'])

    error_df = pd.DataFrame(error, columns=['Ticker', 'Error_Step'])
    
    # Save results to CSV
    if not isinstance(my_list, bool):
        tradeable.to_csv(directory + "my_universe_industry_sector_marketcap_earnings.csv", index=False)
        error_df.to_csv(directory + "error.csv", index=False)
    else:
        tradeable.to_csv(directory + "from_error_my_universe_industry_sector_marketcap_earnings.csv", index=False)
        error_df.to_csv(directory + "from_error.csv", index=False)

    stop = timeit.default_timer()
    runtime = stop - start
    print(f"Runtime: {runtime:.2f} seconds")

#################################################################

# Mongo Class

#################################################################


# This function is for mongo class update_db_multi method


# def update_worker(mongo,tickers,now_time):
    
#     for i in tickers:
#         try:
            
#             print (i)

#             quote = da.get_quote_yahoo(i)
#             quote["Ticker"] = quote.index[0]
#             quote = quote.rename( {"regularMarketTime":"TimeStamp", "regularMarketDayHigh": "High","regularMarketDayLow": "Low", "regularMarketOpen":"Open", "regularMarketVolume":"Volume", "regularMarketPrice":"Close"},axis = "columns") 

#             mongo.db = mongo.client["stocks_daily"]
#             collection = mongo.db[i]
            
#             quote["TimeStamp"] = datetime(datetime.utcfromtimestamp(quote["TimeStamp"]).year,datetime.utcfromtimestamp(quote["TimeStamp"]).month,datetime.utcfromtimestamp(quote["TimeStamp"]).day)

            
#             quote_json = json.loads(quote.T.to_json()).values()[0]   
#             collection.update_many({"TimeStamp":quote_json[u'TimeStamp']},{"$set": quote_json },upsert=True)
            
#             ######################

#             mongo.db = mongo.client["stocks_10minute"]
#             collection = mongo.db[i]     
                
#             quote["TimeStamp"] = now_time
          
#             quote_json = json.loads(quote.T.to_json()).values()[0]

#             collection.update_many({"TimeStamp":quote_json[u'TimeStamp']},{"$set": quote_json },upsert=True)
            
#             clear_output()
#             print ("successed " + i)
#         except Exception as e:
#             print ( e)
#             print ("error occored in updating "+ str(i))
#             continue 

# def update_worker(mongo,tickers,now_time,test = False):
    
#     for i in tickers:
#         try:
            
#             print (i)

#             collection = mongo.db[i]
#             quote = da.get_quote_yahoo(i)

#             if mongo.coll_name == "stocks_daily":

#                 quote["regularMarketTime"] = datetime(datetime.utcfromtimestamp(quote["regularMarketTime"]).year,datetime.utcfromtimestamp(quote["regularMarketTime"]).month,datetime.utcfromtimestamp(quote["regularMarketTime"]).day)

#             else:
#                  quote["regularMarketTime"] = now_time
#             quote["Ticker"] = quote.index[0]
#             quote = quote.rename( {"regularMarketTime":"TimeStamp", "regularMarketDayHigh": "High","regularMarketDayLow": "Low", "regularMarketOpen":"Open", "regularMarketVolume":"Volume", "regularMarketPrice":"Close"},axis = "columns") 
#             quote = json.loads(quote.T.to_json()).values()[0]
#             if test:
#                 print ("Success")
#                 return
#             collection.update_many({"TimeStamp":quote[u'TimeStamp']},{"$set": quote },upsert=True)
#             clear_output()
#             print ("successed " + i)
#         except Exception as e:
#             print ( e)
#             print ("error occored in updating "+ str(i))
#             continue 

# def update_worker2(mongo,tickers,test = False):
#     all_quote = pd.DataFrame()
#     now_time = datetime(datetime.utcnow().year,datetime.utcnow().month,datetime.utcnow().day,datetime.utcnow().hour,datetime.utcnow().minute)
#     for i in tickers:
#         try:
#             
#             print (i)

#             collection = mongo.db[i]
#             quote = da.get_quote_yahoo(i)
            
#             if mongo.coll_name == "stocks_daily":

#                 quote["regularMarketTime"] = datetime(datetime.utcfromtimestamp(quote["regularMarketTime"]).year,datetime.utcfromtimestamp(quote["regularMarketTime"]).month,datetime.utcfromtimestamp(quote["regularMarketTime"]).day)

#             else:
#                  quote["regularMarketTime"] = now_time
            
#             quote["Ticker"] = quote.index[0]
#             quote = quote.rename( {"regularMarketTime":"TimeStamp", "regularMarketDayHigh": "High","regularMarketDayLow": "Low", "regularMarketOpen":"Open", "regularMarketVolume":"Volume", "regularMarketPrice":"Close"},axis = "columns")
#             all_quote = all_quote.append(quote)
#             all_quote
#         except Exception as e:
#             print ( e)
#             print ("error occored in updating "+ str(i))
#             continue 

            
#     for j in  tickers:
#         quote = all_quote[all_quote.Ticker == i]


#         quote = json.loads(quote.T.to_json()).values()[0]
#         if test:
#             print ("Success Test")
#             return
#         collection.update_many({"TimeStamp":quote[u'TimeStamp']},{"$set": quote },upsert=True)
#         clear_output()
#         print ("successed " + i)


# class connect_sql():
    
#     def __init__(self, user, pwd ,host='localhost', database = None):
#         # return pandas dataframe
#         self.host = host
#         self.user = user
#         if database == None:
#             self.conn = pymysql.connect(host,
#                                         user=user,
#                                         passwd=pwd,                        
#                                         connect_timeout=5)
#         else:
#             self.conn = pymysql.connect(host,
#                                         user=user,
#                                         passwd=pwd,
#                                         db=database,
#                                         connect_timeout=5)
        
# #         self.cursor = self.conn.cursor()

#     def to_sql(self, data, database, table_name, dtype = None,if_exists = 'fail' ):
# #         check = input("Caution!! Type 'Confirm to continue'")
# #         if check != "Confirm":
# #             print ("no action")
# #             return 

        

#         engine = sa.create_engine("mysql+pymysql://%s:@%s/%s"%(self.user,self.host,database), creator=lambda: self.conn)
        
#         @event.listens_for(engine, "before_cursor_execute")
#         def receive_before_cursor_execute(
#                conn, cursor, statement, params, context, executemany
#                 ):
#                     if executemany:
#                         cursor.fast_executemany = True
        
    
#         if dtype == None:
#             data.to_sql(name=table_name,
#                       con=engine,
#                       schema=database,
#                       index=False,
#                       if_exists=if_exists)    
#         else:
#             data.to_sql(name=table_name,
#                       con=engine,
#                       schema=database,
#                       index=False,
#                       if_exists=if_exists,dtype=dtype)
            
        
#         print ("If no error message, task completed")
# #         self.conn.close()

#     def get_data(self, sql):
#         get = pd.DataFrame()
#         for chunk in pd.read_sql(sql, self.conn,chunksize = 10000):
#             get = get.append(chunk)
# #             print("Finish 1 chunk")
        
#         return get
    

# def read_file(path):
#     with open(path, 'r') as f:
#         return f.read()
    
    
# def get_columns(database,table):
#     conn = connect_sql(database =  database)

#     col_list = []
#     for row in conn.cursor.columns(table =table):
#         col_list.append(row.column_name)

#     return col_list

    
def readgateway(line):
    with open(gateway) as file:
        for i in range(line):
            abc = file.readline()
    abc = remove_salt(abc)
    abc = abc.strip()
    return abc



class connect_mongo:
    def __init__(self, coll_name, table = None):
        self.client = pymongo.MongoClient('mongodb://10.0.1.22:27017',tz_aware=True)
        self.db = self.client[coll_name]
        if table is not None:
            self.table = self.db[table]
    
    def set_table_name(self,table):
        self.table = self.db[table]
    
    
    def delete_duplicates(self,key):

        cursor = self.table.aggregate(
            [
                {"$group": {"_id": "$%s"%key, "unique_id": {"$addToSet": "$_id"}, "count": {"$sum": 1}}},
                {"$match": {"count": { "$gte": 2 }}}
            ]
        )

        response = []
        
        for doc in cursor:
            del doc["unique_id"][0]
            for id in doc["unique_id"]:
                response.append(id)
        return response
    
    def frame_to_mongo(self,data):
        for col in data.columns:
            if "datetime.date" in str(type(data[col].iloc[0])):
                data[col] = data[col].apply(lambda x: datetime.combine(x,datetime.min.time()))
        self.table.insert_many(data.T.to_dict().values())
        
    def update_to_mongo(self,data,key):
        for col in data.columns:
            if "datetime.date" in str(type(data[col].iloc[0])):
                data[col] = data[col].apply(lambda x: datetime.combine(x,datetime.min.time()))
        data_index = list(data.to_dict()[key].values())
        data = list(data.T.to_dict().values())
        for i in range(len(data)):
            self.table.update_one({key:data_index[i]},{"$set":data[i]},upsert=True)


####  SORT THE PRICE SERIES ASCENDING

# class mongo:
    

#     def __init__(self,coll_name = "stocks_daily"):
        
#         self.coll_name = coll_name
#         # self.conn = connect_sql("ken",readgateway(2))
#         self.stock_list = "cantrade.csv"
#         self.ETF_list = "ETFList.csv"
#         self.initiate_list = [self.stock_list,self.ETF_list]
#         print ("Connection Successful")



#     def get_all_quote(self):
#         result = pd.DataFrame()
#         all_stock_1 = pd.read_csv(directory + self.stock_list)
#         all_stock_2 = pd.read_csv(directory + self.ETF_list)
#         all_stock_2 = all_stock_2.rename(columns={"Symbol":"Ticker"})
#         all_stock = all_stock_1.append(all_stock_2)
#         all_stock = all_stock.reset_index()
#         for i in range(99,len(all_stock),100):
#             tic_list = all_stock.Ticker.iloc[i-99:i].astype(str)
#             result = result.append(self.get_ondemand_quote(tic_list))   
#         return result

#     def query_database(self,stock, start_date = datetime.now()-timedelta(days =200),end_date=datetime.now()+timedelta(days = 1)):
        
        
#         sql = '''
        
        
#         select * from `%s`.`%s`
        
#         where TimeStamp between '%s' and '%s'
        
#         order by TimeStamp
        
        
#         '''%(self.coll_name,stock,start_date.date(),end_date.date())
        
# #         print (sql)
#         get_frame= self.conn.get_data(sql)
        

#         if len(get_frame) == 0:
#             print(("no data for " + stock))

#         get_frame = get_frame.reindex()
#         try:    
#             get_frame = get_frame.drop("Adj Close",axis =1)
#         except:
#             pass
     
#         return get_frame


#     def update_db(self,test = False):
#         pre = time.time()
       
#         for j in self.initiate_list:
#             all_stock = pd.read_csv(directory+j)
#             for i in all_stock.Ticker:
#                 try:
#                     print (i)
 
    
#                     quote = da.get_quote_yahoo(i)
#                     if self.coll_name == "stocks_daily":
                    
#                         quote["regularMarketTime"] = datetime.today().date()
                        
#                     else:
#                          quote["regularMarketTime"] = datetime.now()
#                     quote["Ticker"] = quote.index[0]
#                     quote = quote.rename( {"regularMarketTime":"TimeStamp", "regularMarketDayHigh": "High","regularMarketDayLow": "Low", "regularMarketOpen":"Open", "regularMarketVolume":"Volume", "regularMarketPrice":"Close"},axis = "columns") 

#                     if test:
#                         return quote
#                     self.conn.to_sql(quote,self.coll_name,i,if_exists="append")
#                     clear_output()
#                     print(("successed " + i))
#                 except Exception as e:
#                     print ( e)
#                     print(("error occored in updating "+ str(i)))
#                     continue 
#         post = time.time()
#         return post - pre
    
    
    
#     def update_db_multi(self):
#         # Worker function defines in this file outside of the class
#         pre = time.time()
# #         now_time = datetime(datetime.utcnow().year,datetime.utcnow().month,datetime.utcnow().day,datetime.utcnow().hour,datetime.utcnow().minute)
#         now_time = datetime.now()
#         jobs = []
#         pool = multiprocessing.pool.ThreadPool(processes = 4)
#         for j in self.initiate_list:
#             all_stock = pd.read_csv(directory+j)
#             for i in range(0,len(all_stock.Ticker)+1,500):
#                 tickers = all_stock.Ticker.iloc[i:i+499]
#                 pool.apply_async(update_worker,args=(self.coll_name,tickers,now_time))

#         pool.close()
#         pool.join()
#         post = time.time()
#         return post - pre
        
    
    
#     def update_db_new_minute(self):
#         pre = time.time()
            
#         db_name = "stocks_10minute"
#         for j in self.initiate_list:
#             all_stock = pd.read_csv(directory+j)
#             for i in all_stock.Ticker:
#                 try:
#                     print (i)
#                     temp = pd.DataFrame()
#                     quote = get_price_data([i], method = "intraday")
# #                     quote.TimeStamp= quote.TimeStamp.apply(lambda x: \
# #                                 datetime.strptime(x,"%Y-%m-%dT%H:%M:%SZ"))
                    
#                     if len(quote) == 0:
#                         print ("No data from quote")
#                         continue
                    
#                     try:
#                         temp = self.conn.get_data("select * from `%s`.`%s`"%(db_name,i))
                        
#                         temp.to_csv(directory + "Stock_10minutes_Backup/"+str(i)+".csv",index = False)
                    
#                         self.conn.conn.cursor().execute("drop table `%s`.`%s`"%(db_name,i))
#                         self.conn.conn.commit()
#                         print ("Table Dropped")
#                     except:
#                         temp = quote
#                         print ("Probably not exist")
#                         pass
                    
#                     temp = temp.append(quote).drop_duplicates(subset=["TimeStamp"])
#                     self.conn.to_sql(temp,db_name,i,if_exists="append")
# #                     clear_output()
#                     print(("successed " + i))
#                 except Exception as e:
#                     print ( e)
#                     print(("error occored in updating "+ str(i)))
                    
               
#                     continue 
#         post = time.time()
#         return post - pre
    
    
#     def update_db_new_minute_quick(self):
#         pre = time.time()
            
#         db_name = "stocks_10minute"
#         for j in self.initiate_list:
#             all_stock = pd.read_csv(directory+j)
#             for i in all_stock.Ticker:
#                 try:
#                     print (i)
                    
#                     quote = get_price_data([i], method = "intraday", back_day = 0)

#                     if len(quote) == 0:
#                         print ("No data from quote")
#                         continue
           
#                     self.conn.to_sql(quote,db_name,i,if_exists="append")
# #                     clear_output()
#                     print(("successed " + i))
#                 except Exception as e:
#                     print ( e)
#                     print(("error occored in updating "+ str(i)))
               
#                     continue 
#         post = time.time()
#         return post - pre
    
#     def update_db_new_minute_mongo(self):
#         pre = time.time()
#         db_name = "stocks_10minute"
#         mongo_conn = connect_mongo(db_name)
            
        
#         for j in self.initiate_list:
#             all_stock = pd.read_csv(directory+j)
#             for i in all_stock.Ticker:
#                 try:
#                     print (i)
#                     mongo_conn.set_table_name(i)
                    
#                     quote = get_price_data([i], method = "intraday", back_day = 0)

#                     if len(quote) == 0:
#                         print ("No data from quote")
#                         continue
           
#                     mongo_conn.update_to_mongo(quote,"TimeStamp")
# #                     clear_output()
#                     print(("successed " + i))
#                 except Exception as e:
#                     print ( e)
#                     print(("error occored in updating "+ str(i)))
               
#                     continue 
#         post = time.time()
#         return post - pre
    
#     def update_db_new_day(self):
#         pre = time.time()
            
#         db_name = "stocks_daily"
#         for j in self.initiate_list:
#             all_stock = pd.read_csv(directory+j)
#             for i in all_stock.Ticker:
#                 try:
#                     print (i)
#                     temp = pd.DataFrame()
#                     quote = get_price_data([i], method = "realtimeday",back_day = 10)
# #                     quote.TimeStamp= quote.TimeStamp.apply(lambda x: \
# #                                 datetime.strptime(x,"%Y-%m-%dT%H:%M:%SZ"))
#                     if len(quote) == 0:
#                         print ("No data from quote")
#                         continue
#                     try:
#                         temp = self.conn.get_data("select * from `%s`.`%s`"%(db_name,i))
#                         temp.to_csv(directory + "Stock_daily_Backup/"+str(i)+".csv",index = False)
                    
#                         self.conn.conn.cursor().execute("drop table `%s`.`%s`"%(db_name,i))
#                         self.conn.conn.commit()
#                         print ("Table Dropped")
#                     except:
#                         temp = pd.DataFrame()
#                         print ("Probably not exist")
#                         pass
                    
#                     temp = temp.append(quote).drop_duplicates(subset=["TimeStamp"])
#                     self.conn.to_sql(temp,db_name,i,if_exists="append")
# #                     clear_output()
#                     print(("successed " + i))
#                 except Exception as e:
#                     print ( e)
#                     print(("error occored in updating "+ str(i)))
                   
#                     continue 
#         post = time.time()
#         return post - pre
    
    
#     def update_db_new_day_quick(self):
#         pre = time.time()
            
#         db_name = "stocks_daily"
#         for j in self.initiate_list:
#             all_stock = pd.read_csv(directory+j)
#             for i in all_stock.Ticker:
#                 try:
#                     print (i)
                    
#                     quote = get_price_data([i], method = "realtimeday", back_day = 0)

#                     if len(quote) == 0:
#                         print ("No data from quote")
#                         continue
           
#                     self.conn.to_sql(quote,db_name,i,if_exists="append")
# #                     clear_output()
#                     print(("successed " + i))
#                 except Exception as e:
#                     print ( e)
#                     print(("error occored in updating "+ str(i)))
                
#                     continue 
#         post = time.time()
#         return post - pre
    
#     def update_db_new_day_mongo(self):
#         pre = time.time()
#         db_name = "stocks_daily"
#         mongo_conn = connect_mongo(db_name)
            
        
#         for j in self.initiate_list:
#             all_stock = pd.read_csv(directory+j)
#             for i in all_stock.Ticker:
#                 try:
#                     print (i)
#                     mongo_conn.set_table_name(i)
                    
#                     quote = get_price_data([i], method = "realtimeday", back_day = 0)

#                     if len(quote) == 0:
#                         print ("No data from quote")
#                         continue
           
#                     mongo_conn.update_to_mongo(quote,"TimeStamp")
# #                     clear_output()
#                     print(("successed " + i))
#                 except Exception as e:
#                     print ( e)
#                     print(("error occored in updating "+ str(i)))
               
#                     continue 
#         post = time.time()
#         return post - pre
    
#     def ifexist(self, tablename, target,target_col = "TimeStamp"):
#         sql = '''
#         select * from `%s`.`%s`

#         where %s = '%s'

#         '''%(self.coll_name,tablename,target_col,target)
#         try:
#             temp = self.conn.get_data(sql)
#         except:
#             return False
#         if len(temp) == 0:
#             return False
#         else:
#             return True     
 
#     def frame_to_mongo(self,data,collection_str,drop_mode="append",index_col = None):
#         if drop_mode not in ["drop","upsert","append"]:
#             print ("Drop Mode can only be drop, upsert, or append")
#         if drop_mode == "drop":
#             try:
#                 self.conn.conn.cursor().execute("drop table `%s`.`%s`"%(self.coll_name,collection_str))
#             except Exception as e:
#                 print (e)
#                 print ("\n probably table not exist")
#             self.conn.to_sql(data,self.coll_name,collection_str,if_exists="append")
#         elif drop_mode == "upsert":
#             print ("In upsert mode, please make sure column name are matched")
#             try:
#                 temp = self.conn.get_data("select * from `%s`.`%s`"%(self.coll_name,collection_str))
#             except:
#                 print ("Probably table not exist")
#                 temp = pd.DataFrame()
#             if index_col == None:
#                 print ("Please feed a index column for upsert")
#                 raise 
#             elif type(index_col) != list:
#                 index_col = [index_col]
#             temp = temp.append(data).drop_duplicates(subset=index_col)
#             self.conn.to_sql(temp,self.coll_name,collection_str,if_exists="append")
#         elif drop_mode == "append":
#             self.conn.to_sql(data,self.coll_name,collection_str,if_exists="append")
#         else:
#             print ("drop_mode error")
# def update_worker(db_name,tickers,now_time,test = False):
    
#     for i in tickers:
#         try:
#             mongod = mongo(db_name)
# #             mongod = db_name
#             print (i)

#             quote = da.get_quote_yahoo(i)

#             if mongod.coll_name == "stocks_daily":

#                 quote["regularMarketTime"] = datetime(datetime.utcfromtimestamp(quote["regularMarketTime"]).year,datetime.utcfromtimestamp(quote["regularMarketTime"]).month,datetime.utcfromtimestamp(quote["regularMarketTime"]).day)

#             else:
#                  quote["regularMarketTime"] = now_time
#             quote["Ticker"] = quote.index[0]
#             quote = quote.rename( {"regularMarketTime":"TimeStamp", "regularMarketDayHigh": "High","regularMarketDayLow": "Low", "regularMarketOpen":"Open", "regularMarketVolume":"Volume", "regularMarketPrice":"Close"},axis = "columns") 

#             if test:

#                 print ("Success")
#                 return
#             # has to start a different instance
# #             check_db = mongo()
# #             check = check_db.ifexist(i,quote.TimeStamp.iloc[0])
# #             check_db.conn.conn.close()
#             check = mongod.ifexist(i,quote.TimeStamp.iloc[0])
#             if check:
#                 continue
#             mongod.conn.to_sql(quote,mongod.coll_name,i,if_exists="append")

#     #             collection.update_many({"TimeStamp":quote[u'TimeStamp']},{"$set": quote },upsert=True)
#             clear_output()
#             print(("successed " + i))
        
#         except Exception as e:
#             print ( e)
#             print(("error occored in updating "+ str(i)))
#             continue 
#     mongod.conn.conn.close()

  
class mongo:
    

    def __init__(self,coll_name = "stocks_daily",table_name=None):
        try:
            self.coll_name = coll_name
            self.conn = connect_mongo(self.coll_name,table_name)
            self.stock_list = "cantrade.csv"
            self.ETF_list = "ETFList.csv"
            self.initiate_list = [self.stock_list,self.ETF_list]
            # print ("Connection Successful")
        except:
            print ("Connection Failed")



    def query_database(self,stock, start_date = datetime.now()-timedelta(days =200),end_date=datetime.now()+timedelta(days = 1)):
        
        collection = self.conn.db[stock]
        #self.delete_duplicates(stock)
#         start_date=(start_date-datetime.utcfromtimestamp(0)).total_seconds()*1000

#         end_date = (end_date-datetime.utcfromtimestamp(0)).total_seconds()*1000

        get = collection.find({"Ticker":stock,"TimeStamp":{"$gte":start_date,"$lte":end_date}}).sort("TimeStamp",pymongo.ASCENDING)
        get_frame = pd.DataFrame(list(get))
        if len(get_frame) == 0:
            print ("no data for " + stock)
            return
#         if self.coll_name == "stocks_10minute": 
#             get_frame[u'TimeStamp'] = get_frame[u'TimeStamp'].apply(lambda x: change_timezone(datetime.utcfromtimestamp(0) + timedelta(milliseconds= x), "US/Pacific"))
#         else:
#             get_frame[u'TimeStamp'] = get_frame[u'TimeStamp'].apply(lambda x: datetime.utcfromtimestamp(0) + timedelta(milliseconds= x))
        #get_frame = get_frame.rename(columns={"Close":"Adj_close"})
        get_frame = get_frame.reindex()
        try:    
            get_frame = get_frame.drop("Adj Close",axis =1)
        except:
            pass
     
        return get_frame

#     def frame_to_mongo(self,data,collection_str):
#         collection = self.conn.db[collection_str]
#         records = json.loads(data.T.to_json()).values()
#         collection.insert_many(records)
#         collection.find().close()



        
   

           
    
        
                
    
#********************************************************
#********************************************************
#********************************************************
#********************************************************
#********************************************************
#********************************************************
#********************************************************


