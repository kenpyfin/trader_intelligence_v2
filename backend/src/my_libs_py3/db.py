import pymongo
import pandas as pd
from datetime import datetime, timedelta
import os

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

class mongo:
    def __init__(self,coll_name = "stocks_daily",table_name=None):
        try:
            self.coll_name = coll_name
            self.conn = connect_mongo(self.coll_name,table_name)
            
            if os.path.exists("/opt/airflow"):
                home_dir="/opt/airflow/notebook"
            else:
                home_dir = "/home/ken/big_storage/airflowProd/airflow_notebook"
            directory = home_dir+ "/My_Trader/file/"

            self.stock_list = os.path.join(directory, "cantrade.csv")
            self.ETF_list = os.path.join(directory, "ETFList.csv")
            self.initiate_list = [self.stock_list,self.ETF_list]
        except:
            print ("Connection Failed")

    def query_database(self,stock, start_date = datetime.now()-timedelta(days =200),end_date=datetime.now()+timedelta(days = 1)):
        
        collection = self.conn.db[stock]

        get = collection.find({"Ticker":stock,"TimeStamp":{"$gte":start_date,"$lte":end_date}}).sort("TimeStamp",pymongo.ASCENDING)
        get_frame = pd.DataFrame(list(get))
        if len(get_frame) == 0:
            print ("no data for " + stock)
            return pd.DataFrame()
            
        get_frame = get_frame.reindex()
        try:    
            get_frame = get_frame.drop("Adj Close",axis =1)
        except:
            pass
     
        return get_frame
