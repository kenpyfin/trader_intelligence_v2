# Goal
- The goal of the development is to build a sophiscated and reliable trading intelligence app for retail traders. Let's call it trader intelligence.
- The app will connect to powerful data sources, including fundementaion data (Finviz), option (Finviz), realtime pricing (Finviz, FMP).
- The app will connect to broker account for trading actions.
- The app analyze a stock and its option throughoutly and provide best trading advices.
- The app can handle portfolio risk managment.

# Key Features
1. Stock and Option Analysis
As POC in option_trade.py file, user enter a stock and the app analyze its market price movement/pattern and its option, and provide a final trading advice.
Here're some of the analysis points:
 1 Price Trend & Candlestick Analysis:                                                         
    • Determines the primary and secondary market trends using 50-day and 200-day moving averages.                           
    • Identifies recent, significant candlestick patterns (e.g., Hammer, Engulfing, Doji).     
 2 Sentiment Analysis:           
    • Calculates Put-Call Parity to find relative mispricing between puts and calls.           
    • Analyzes the Put/Call ratio based on volume.                                             
    • Scans for Unusual Option Activity (UOA) where volume significantly exceeds open interest.
    • Identifies potential support and resistance "walls" based on high open interest strikes. 
 3 Volatility and Movement Analysis:   
    • Calculates the market-implied move based on the price of the at-the-money (ATM) straddle.
    • Analyzes for volatility compression by comparing short-term (10-day) vs. long-term       
      (50-day) historical volatility.                    
    • Checks if an earnings report is scheduled before the option's expiration date.           
    • Compares the current Implied Volatility (IV) to the Historical Volatility (HV).          
 4 Quantitative Valuation:       
    • Calculates a theoretical "model price" for a range of options using a binomial pricer.   
    • Compares this model price to the current market price to identify potentially undervalued options.  
 5 Holistic Synthesis:                               
    • Combines the results of all the above analyses to generate a single, holistic conclusion 
      and a final directional bias (e.g., Bullish, Bearish, Neutral).    
2. Display Macro Economy Insights
3. Order Placement 
This feature offers the user a quick way to execute the recommendation from the stock and option analysis.