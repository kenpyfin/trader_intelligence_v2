

### **An Improved Quantitative Options Analysis and Trading Guideline**

This framework is designed to provide a systematic, robust, and adaptive approach to options analysis, moving from heuristic rules to a data-driven, statistically validated methodology.

---

### **1.0 Core Infrastructure and Pricing Engine**

This section outlines the foundational components, from data acquisition to the core option pricing model, emphasizing accuracy, robustness, and market consistency.

* **1.1 Inputs:**  
  * Ticker, target expiration date, model settings (American/European).  
* **1.2 Data Ingestion (Professional Grade):**  
  * **Real-time and Historical Equity Data:** Source high-quality, corporate-action-adjusted OHLCV data from a provider that offers survivorship-bias-free datasets. This is a critical step to prevent backtests from being skewed by only including companies that are still trading.1  
  * **Historical Options Data:** Acquire granular, intraday historical options data that includes bid/ask quotes for every contract. This is essential for accurate backtesting of transaction costs. Institutional-grade providers include AlgoSeek and TickData.3  
  * **Risk-Free Rate:** Construct a risk-free yield curve by bootstrapping from U.S. Treasury yield data. This is a more reliable and standard industry practice than deriving rates from ETF options, as it provides a cleaner representation of the risk-free rate across various maturities.7  
  * **Corporate Actions:** Utilize a data feed that provides precise dates and terms for dividends, splits, and mergers to ensure historical prices are correctly adjusted.11  
* **1.3 Preprocessing:**  
  * Clean and coerce all options data (strikes, volume, OI) to numeric types.  
  * Apply corporate action adjustments (splits, dividends) to all historical price series to create a continuous and accurate data history.13  
  * Calculate historical volatility (HV) from daily log-returns of the adjusted price series.  
* **1.4 Core Modeling (Enhanced Binomial Tree):**  
  * **Model Selection:** Default to the **Cox-Ross-Rubinstein (CRR)** binomial model. The CRR model is the industry standard that is constructed to be risk-neutral and converges to the Black-Scholes-Merton model, avoiding the theoretical biases of the standard Jarrow-Rudd formulation.14  
  * **Volatility Skew Integration:** To account for the volatility skew, the binomial tree must be fed with a **strike-specific volatility** derived from a calibrated volatility surface for each expiration. This is a critical enhancement to avoid the systematic mispricing of out-of-the-money options that occurs when using a single volatility value for all strikes.19  
  * **Discrete Event Modeling (Earnings):** For options that expire after a known earnings date, augment the pricing model with a **jump-diffusion component** (e.g., based on Merton's model). This explicitly models the potential for large, discontinuous price jumps, providing more realistic valuations around binary events.24  
  * **Parameters:** The model supports time-varying volatility (via the volatility surface), time-varying interest rates (via the Treasury yield curve), and continuous dividend yields. It remains optimized for American or European exercise.  
* **1.5 Greeks Calculation:**  
  * **Delta (Δ) & Gamma (Γ):** Calculated directly from the first and second levels of the binomial tree.  
  * **Theta (Θ):** Calculated directly by comparing the option's value at the root node with the expected discounted value at the next time step.  
  * **Vega (ν):** Calculated by "bumping" the entire volatility surface and repricing. Note the limitation: this measures sensitivity to a parallel shift, while real-world shocks are often non-parallel.  
  * **Portfolio Greeks:** The primary focus should shift from individual Greeks to managing the **net Greek exposures** (Net Delta, Gamma, Vega, Theta) of the entire portfolio.29

---

### **2.0 Multi-Factor Sub-Analyses**

Each sub-analysis generates a signal that is normalized and fed into a final signal integration model. Fixed thresholds are replaced with dynamic, statistical measures.

* **2.1 Trend and Momentum Analysis:**  
  * **Trend Context:** Use SMAs (20/50/100/200) and crossover states (Golden/Death Cross) to define trend conditions. While these are common, their standalone predictive power can be limited and prone to "whipsaws" in non-trending markets.29  
  * **Candlestick Patterns:** Identify patterns (e.g., Hammer, Engulfing) but move away from subjective strength ratings. The predictive power of these patterns is debated, though some machine learning approaches show promise.34  
  * **Signal Normalization:** Convert each raw signal (e.g., price vs. SMA200) into a normalized score (e.g., a z-score or percentile rank based on its rolling historical distribution). This makes signals comparable and adaptive.  
* **2.2 Options Sentiment Analysis:**  
  * **Put/Call Parity Deviation:** Calculate the deviation but instead of a fixed \+/- 0.15% threshold, generate a signal when the deviation exceeds a statistical band (e.g., \+/- 2 standard deviations) of its rolling historical average for that specific ticker.  
  * **Put/Call Volume Ratio:** Compare the current P/C ratio to its own historical distribution (e.g., 252-day lookback). Generate contrarian signals at extreme percentiles (e.g., \>95th percentile for bullish, \<5th percentile for bearish), rather than using fixed levels like 0.7 or 1.0, which vary by asset and market regime.37  
  * **Unusual Option Activity (UOA):** Enhance the Volume \> OI filter by adding a **trade execution context**. Prioritize trades executed at or above the ask (for calls) or at or below the bid (for puts), as this signals greater urgency and conviction.39  
  * **OI Walls:** The existing methodology of identifying high OI strikes as potential support/resistance is statistically sound and can be retained.  
* **2.3 Volatility and Regime Analysis:**  
  * **IV vs. HV Regime:** Compare current IV to recent HV. A signal is generated when the IV/HV ratio exceeds a dynamic threshold based on its historical percentile for that asset, indicating options are statistically "rich" or "cheap."  
  * **Volatility Compression:** The HV(10) vs. HV(50) metric is a valid way to detect "coiling."  
  * **Market Regime Detection:** For a more robust analysis, implement a **Hidden Markov Model (HMM)**. An HMM can statistically identify distinct, unobservable market regimes (e.g., "low-volatility trend," "high-volatility mean-reversion") from market data, allowing for dynamic strategy adaptation.25  
  * **Earnings Catalyst:** Retain the explicit check for an earnings date before expiry as a critical override signal.  
* **2.4 Quantitative Valuation (Relative Value):**  
  * **Objective:** The goal shifts from finding absolute "undervaluation" to identifying **relative value** across the volatility surface.  
  * **Process:**  
    1. Construct the arbitrage-free volatility surface for the target expiration.  
    2. For each option, compare its actual market-implied IV to the value predicted by the smooth, fitted surface.  
    3. Flag options where the market IV deviates significantly (e.g., by a statistically significant margin) from the surface.  
    * **Interpretation:** A call trading at an IV well *below* the fitted smile might be a relative value buying opportunity. A put trading *above* the fitted smile might be a relative value selling opportunity. This approach correctly isolates market pricing anomalies from model specification errors.  
* **2.5 Implied Volatility (IV) Surface Construction:**  
  * **Data Fetch:** For each expiration, collect market IVs for all available strikes.  
  * **Parametric Fitting:** Calibrate a market-standard parametric model, such as the **SABR (Stochastic Alpha, Beta, Rho) model**, to the collected IV data for that expiration.47 This involves finding the SABR parameters that best fit the observed market smile/skew using non-linear least squares optimization.49  
  * **Surface Generation:** Use the calibrated SABR formula to generate a smooth, continuous, and arbitrage-free volatility value for any strike price. This provides the strike-specific volatility needed for the core pricing engine.52

---

### **3.0 Signal Integration & Trade Decision**

This section replaces subjective weighting with a formal, data-driven model for combining signals into a single, actionable score.

* **3.1 Signal Combination:**  
  * **Multi-Factor Model:** Treat the normalized outputs from all sub-analyses as a feature set. Use a **multi-factor model** to determine the optimal, data-driven weights for combining them.55  
  * **Implementation:**  
    * **Baseline:** Start with a "conceptual parity" approach, where all normalized signals are given equal weight.58  
    * **Advanced:** Use multiple linear regression or machine learning models (e.g., Random Forest, Gradient Boosting) to regress historical returns against the signal features. The model's output is a predictive score (e.g., probability of an upward move) that represents a statistically optimized combination of all available information.59

---

### **4.0 Risk Management & Position Sizing**

This section introduces a formal framework for managing portfolio-level risk and systematically allocating capital.

* **4.1 Portfolio-Level Risk Management:**  
  * **Aggregate Greek Exposure:** Actively monitor the **net Delta, Gamma, Vega, and Theta** of the entire portfolio. Establish hard risk limits for each of these aggregate exposures.60  
  * **Dynamic Hedging:** When a risk limit is breached, dynamically hedge the portfolio back to within its target range. For example, if net delta becomes too positive, sell the underlying asset to re-neutralize. For positive-gamma positions, this can evolve into **gamma scalping**, where frequent delta-hedging monetizes volatility.29  
* **4.2 Position Sizing:**  
  * **Kelly Criterion:** Use the **Kelly Criterion** as the theoretical foundation for position sizing. This formula uses the strategy's historical win rate (p) and average profit/loss ratio (b) to calculate the optimal fraction of capital (f∗) to allocate to maximize long-term growth.64  
  * **Practical Implementation:** Never use the "full Kelly" fraction, as it leads to extreme volatility. Implement a **Fractional Kelly** approach (e.g., half-Kelly or quarter-Kelly), which captures a majority of the growth with significantly less risk and drawdown.65 The inputs (  
    p and b) must be derived from rigorous backtesting.

---

### **5.0 Backtesting and Validation Framework**

All strategies must be validated in a rigorous, event-driven backtesting environment before deployment.

* **5.1 Backtesting Engine:**  
  * Utilize a robust, open-source Python backtesting framework like **Zipline** or **backtesting.py**.70  
* **5.2 Simulation Integrity:**  
  * **Avoid Biases:** The backtest must use point-in-time, survivorship-bias-free data to avoid inflated results.1 Code must be carefully structured to prevent any form of lookahead bias, for example by ensuring decisions for a given time period only use information available before that period begins.73  
  * **Model Transaction Costs:** All simulated trades must incorporate realistic costs. Buy orders execute at the historical **ask** price, and sell orders at the historical **bid** price. A model for **slippage** (market impact) based on order size and market liquidity must also be included.76  
  * **Out-of-Sample Testing:** Validate the strategy on an out-of-sample dataset that was not used during the model training or optimization phase to ensure robustness and avoid overfitting.82

#### **Works cited**

1. Survivorship Bias in Backtesting Explained \- LuxAlgo, accessed August 14, 2025, [https://www.luxalgo.com/blog/survivorship-bias-in-backtesting-explained/](https://www.luxalgo.com/blog/survivorship-bias-in-backtesting-explained/)  
2. Backtesting biases \- Portfolio123 \- Help Center \- Customerly, accessed August 14, 2025, [https://portfolio123.customerly.help/en/research-section/backtesting-biases](https://portfolio123.customerly.help/en/research-section/backtesting-biases)  
3. Tick & Aggregated Historical Data for Stocks, Options & Futures, accessed August 14, 2025, [https://www.algoseek.com/](https://www.algoseek.com/)  
4. Download Historical Intraday Data (20 Years Data), accessed August 14, 2025, [https://firstratedata.com/](https://firstratedata.com/)  
5. Best Historical Market Data Providers \- QuantPedia, accessed August 14, 2025, [https://quantpedia.com/best-historical-market-data-providers/](https://quantpedia.com/best-historical-market-data-providers/)  
6. Tick Data: Historical Forex, Options, Stock & Futures Data, accessed August 14, 2025, [https://www.tickdata.com/](https://www.tickdata.com/)  
7. How to estimate the risk-free rate when pricing options \- calibration, accessed August 14, 2025, [https://quant.stackexchange.com/questions/57161/how-to-estimate-the-risk-free-rate-when-pricing-options-calibration](https://quant.stackexchange.com/questions/57161/how-to-estimate-the-risk-free-rate-when-pricing-options-calibration)  
8. options-pricing/riskless-yield-construction-example.ipynb at main \- GitHub, accessed August 14, 2025, [https://github.com/ilchen/options-pricing/blob/main/riskless-yield-construction-example.ipynb](https://github.com/ilchen/options-pricing/blob/main/riskless-yield-construction-example.ipynb)  
9. US Treasury Yield Curve \- QuantConnect.com, accessed August 14, 2025, [https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/treasury-department/us-treasury-yield-curve](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/treasury-department/us-treasury-yield-curve)  
10. Yield Curve Analytics with Python \- FinQuest Institute, accessed August 14, 2025, [https://www.finquestinstitute.com/view-blog-details/yield-curve-analytics-with-python/5f4811ba07716d324019661a/](https://www.finquestinstitute.com/view-blog-details/yield-curve-analytics-with-python/5f4811ba07716d324019661a/)  
11. Tackling Corporate Actions Data Conflicts: An AI-based ..., accessed August 14, 2025, [https://www.spglobal.com/market-intelligence/en/news-insights/research/tackling-corporate-actions-data-conflicts-an-ai-based-recommendation-engine](https://www.spglobal.com/market-intelligence/en/news-insights/research/tackling-corporate-actions-data-conflicts-an-ai-based-recommendation-engine)  
12. Explaining the Main Types of Corporate Action Data (and What They Mean), accessed August 14, 2025, [https://www.exchange-data.com/explaining-the-main-types-of-corporate-action-data-and-what-they-mean/](https://www.exchange-data.com/explaining-the-main-types-of-corporate-action-data-and-what-they-mean/)  
13. Corporate Actions \- QuantConnect.com, accessed August 14, 2025, [https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/corporate-actions](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/corporate-actions)  
14. Option Pricing Using The Binomial Model \- Goddard Consulting, accessed August 14, 2025, [http://www.goddardconsulting.ca/option-pricing-binomial-index.html](http://www.goddardconsulting.ca/option-pricing-binomial-index.html)  
15. Convergence of Three Binomial Models into Black Scholes Model in Establishing Option Prices in Hongkong, India, and Indonesia, accessed August 14, 2025, [https://www.bircu-journal.com/index.php/birci/article/download/2426/pdf](https://www.bircu-journal.com/index.php/birci/article/download/2426/pdf)  
16. Option Pricing \- Alternative Binomial Models \- Goddard Consulting, accessed August 14, 2025, [http://www.goddardconsulting.ca/option-pricing-binomial-alts.html](http://www.goddardconsulting.ca/option-pricing-binomial-alts.html)  
17. Lattice Methods Overview \- Maple Help \- Maplesoft, accessed August 14, 2025, [https://www.maplesoft.com/support/help/Maple/view.aspx?path=Finance/LatticeMethods](https://www.maplesoft.com/support/help/Maple/view.aspx?path=Finance/LatticeMethods)  
18. Jarrow-Rudd Model Formulas \- Macroption, accessed August 14, 2025, [https://www.macroption.com/jarrow-rudd-formulas/](https://www.macroption.com/jarrow-rudd-formulas/)  
19. Volatility Skew: How it Can Signal Market Sentiment \- Investopedia, accessed August 14, 2025, [https://www.investopedia.com/terms/v/volatility-skew.asp](https://www.investopedia.com/terms/v/volatility-skew.asp)  
20. Volatility smile \- Wikipedia, accessed August 14, 2025, [https://en.wikipedia.org/wiki/Volatility\_smile](https://en.wikipedia.org/wiki/Volatility_smile)  
21. Implying the Risk-Neutral Distribution from the Volatility Skew in Options Pricing \- S. Rabbani, accessed August 14, 2025, [https://www.srabbani.com/volatility.pdf](https://www.srabbani.com/volatility.pdf)  
22. Volatility Skew- Understanding Option Premiums Over Different Time Frames and Strikes, accessed August 14, 2025, [https://www.thebluecollarinvestor.com/volatility-skew-understanding-option-premiums-over-different-time-frames-and-strikes/](https://www.thebluecollarinvestor.com/volatility-skew-understanding-option-premiums-over-different-time-frames-and-strikes/)  
23. How precise are price distributions predicted by implied binomial trees? \- EconStor, accessed August 14, 2025, [https://www.econstor.eu/bitstream/10419/65327/1/726286079.pdf](https://www.econstor.eu/bitstream/10419/65327/1/726286079.pdf)  
24. Breaking Down the Binomial Model to Value an Option \- Investopedia, accessed August 14, 2025, [https://www.investopedia.com/articles/financial-theory/binomial-trees-black-scholes-model.asp](https://www.investopedia.com/articles/financial-theory/binomial-trees-black-scholes-model.asp)  
25. The Mathematics Behind Jump Diffusion In Option Pricing \- FasterCapital, accessed August 14, 2025, [https://fastercapital.com/topics/the-mathematics-behind-jump-diffusion-in-option-pricing.html/1](https://fastercapital.com/topics/the-mathematics-behind-jump-diffusion-in-option-pricing.html/1)  
26. A Jump-Diffusion Model for Option Pricing | Management Science \- PubsOnLine, accessed August 14, 2025, [https://pubsonline.informs.org/doi/10.1287/mnsc.48.8.1086.166](https://pubsonline.informs.org/doi/10.1287/mnsc.48.8.1086.166)  
27. Option Pricing Under a Double Exponential Jump Diffusion Model | Management Science, accessed August 14, 2025, [https://pubsonline.informs.org/doi/10.1287/mnsc.1030.0163](https://pubsonline.informs.org/doi/10.1287/mnsc.1030.0163)  
28. Pricing of a Binary Option Under a Mixed Exponential Jump Diffusion Model \- MDPI, accessed August 14, 2025, [https://www.mdpi.com/2227-7390/12/20/3233](https://www.mdpi.com/2227-7390/12/20/3233)  
29. (PDF) Simple Moving Average (SMA) Crossover Strategy with Buy ..., accessed August 14, 2025, [https://www.researchgate.net/publication/370888513\_Simple\_Moving\_Average\_SMA\_Crossover\_Strategy\_with\_Buy\_Sell\_Indicator](https://www.researchgate.net/publication/370888513_Simple_Moving_Average_SMA_Crossover_Strategy_with_Buy_Sell_Indicator)  
30. Option Greek Explained: Definitions & How to Use Them | tastylive, accessed August 14, 2025, [https://www.tastylive.com/concepts-strategies/option-greeks](https://www.tastylive.com/concepts-strategies/option-greeks)  
31. Option Greeks: The 4 Factors to Measure Risk \- Investopedia, accessed August 14, 2025, [https://www.investopedia.com/trading/getting-to-know-the-greeks/](https://www.investopedia.com/trading/getting-to-know-the-greeks/)  
32. Get to Know the Options Greeks | Charles Schwab, accessed August 14, 2025, [https://www.schwab.com/learn/story/get-to-know-option-greeks](https://www.schwab.com/learn/story/get-to-know-option-greeks)  
33. Simple Moving Average (SMA) Crossover Strategy with Buy Sell Indicator, accessed August 14, 2025, [https://ejournal.lincolnrpl.org/index.php/ajmt/article/download/103/138/412](https://ejournal.lincolnrpl.org/index.php/ajmt/article/download/103/138/412)  
34. Enhancing market trend prediction using convolutional neural ..., accessed August 14, 2025, [https://pmc.ncbi.nlm.nih.gov/articles/PMC11935771/](https://pmc.ncbi.nlm.nih.gov/articles/PMC11935771/)  
35. Predictive Power of Adaptive Candlestick Patterns in Forex Market. Eurusd Case \- MDPI, accessed August 14, 2025, [https://www.mdpi.com/2227-7390/8/5/802](https://www.mdpi.com/2227-7390/8/5/802)  
36. The Predictive Power of Candlestick Patterns \- Lund University Publications, accessed August 14, 2025, [https://lup.lub.lu.se/luur/download?func=downloadFile\&recordOId=8877738\&fileOId=8877838](https://lup.lub.lu.se/luur/download?func=downloadFile&recordOId=8877738&fileOId=8877838)  
37. Put/Call Ratio: Key Options Sentiment \- LuxAlgo, accessed August 14, 2025, [https://www.luxalgo.com/blog/putcall-ratio-key-options-sentiment/](https://www.luxalgo.com/blog/putcall-ratio-key-options-sentiment/)  
38. Put-Call Ratio | Calculation, Rationale, & Comparison to VIX | Britannica Money, accessed August 14, 2025, [https://www.britannica.com/money/put-call-ratio](https://www.britannica.com/money/put-call-ratio)  
39. Unusual Options Activity: A Guide to Detecting Market Anomalies, accessed August 14, 2025, [https://www.luxalgo.com/blog/unusual-options-activity-a-guide-to-detecting-market-anomalies/](https://www.luxalgo.com/blog/unusual-options-activity-a-guide-to-detecting-market-anomalies/)  
40. Unusual Options Activity: Insights and Strategies for Traders \- Moomoo, accessed August 14, 2025, [https://www.moomoo.com/us/learn/detail-unusual-options-activity-117647-241178077](https://www.moomoo.com/us/learn/detail-unusual-options-activity-117647-241178077)  
41. Python for Regime-Switching Models in Quantitative Finance | by SR \- Medium, accessed August 14, 2025, [https://medium.com/@deepml1818/python-for-regime-switching-models-in-quantitative-finance-c54d2710f71b](https://medium.com/@deepml1818/python-for-regime-switching-models-in-quantitative-finance-c54d2710f71b)  
42. Market Regime Detection Using Hidden Markov Models | QuestDB, accessed August 14, 2025, [https://questdb.com/glossary/market-regime-detection-using-hidden-markov-models/](https://questdb.com/glossary/market-regime-detection-using-hidden-markov-models/)  
43. Market Regime Change Detection with ML \- QuestDB, accessed August 14, 2025, [https://questdb.com/glossary/market-regime-change-detection-with-ml/](https://questdb.com/glossary/market-regime-change-detection-with-ml/)  
44. Volatility and Market Regimes: How Changing Risk Shapes Market Behavior (with Python Examples) | by Trading Dude | Medium, accessed August 14, 2025, [https://medium.com/@trading.dude/volatility-and-market-regimes-how-changing-risk-shapes-market-behavior-with-python-examples-190de97917d8](https://medium.com/@trading.dude/volatility-and-market-regimes-how-changing-risk-shapes-market-behavior-with-python-examples-190de97917d8)  
45. A Multivariate Regime-switching GARCH Model \- Code Ocean, accessed August 14, 2025, [https://codeocean.com/explore/2bf91781-8f40-4e16-89bb-35c7ce77f43e](https://codeocean.com/explore/2bf91781-8f40-4e16-89bb-35c7ce77f43e)  
46. yonghanjung/RegimeSwitching\_GARCH \- GitHub, accessed August 14, 2025, [https://github.com/yonghanjung/RegimeSwitching\_GARCH](https://github.com/yonghanjung/RegimeSwitching_GARCH)  
47. SABR volatility model \- Wikipedia, accessed August 14, 2025, [https://en.wikipedia.org/wiki/SABR\_volatility\_model](https://en.wikipedia.org/wiki/SABR_volatility_model)  
48. Demystifying the SABR Model and Volatility Surface Arbitrage | by HIYA CHATTERJEE | Medium, accessed August 14, 2025, [https://medium.com/@hiya31/demystifying-the-sabr-model-and-volatility-surface-arbitrage-407a5a7bb064](https://medium.com/@hiya31/demystifying-the-sabr-model-and-volatility-surface-arbitrage-407a5a7bb064)  
49. Calibrate the SABR Model \- MATLAB & Simulink \- MathWorks, accessed August 14, 2025, [https://www.mathworks.com/help/fininst/calibrating-the-sabr-model.html](https://www.mathworks.com/help/fininst/calibrating-the-sabr-model.html)  
50. Implementing the SABR Model, accessed August 14, 2025, [https://medium.com/@fordmanbell/implementing-the-sabr-model-0a4ad8391c4c](https://medium.com/@fordmanbell/implementing-the-sabr-model-0a4ad8391c4c)  
51. On the Calibration of the SABR Model and its Extensions \- Imperial College London, accessed August 14, 2025, [https://www.imperial.ac.uk/media/imperial-college/faculty-of-natural-sciences/department-of-mathematics/math-finance/Cheng\_Luo-thesis.pdf](https://www.imperial.ac.uk/media/imperial-college/faculty-of-natural-sciences/department-of-mathematics/math-finance/Cheng_Luo-thesis.pdf)  
52. Implied Volatility Surface Construction \- DiVA portal, accessed August 14, 2025, [http://www.diva-portal.org/smash/record.jsf?pid=diva2:1191887](http://www.diva-portal.org/smash/record.jsf?pid=diva2:1191887)  
53. Volatility Parametrizations with Random Coefficients: Analytic Flexibility for Implied Volatility Surfaces \- arXiv, accessed August 14, 2025, [https://arxiv.org/html/2411.04041v2](https://arxiv.org/html/2411.04041v2)  
54. Full article: VolGAN: A Generative Model for Arbitrage-Free Implied Volatility Surfaces \- Taylor & Francis Online, accessed August 14, 2025, [https://www.tandfonline.com/doi/full/10.1080/1350486X.2025.2471317](https://www.tandfonline.com/doi/full/10.1080/1350486X.2025.2471317)  
55. Multi-Factor Model: Definition and Formula for Comparing Factors \- Investopedia, accessed August 14, 2025, [https://www.investopedia.com/terms/m/multifactor-model.asp](https://www.investopedia.com/terms/m/multifactor-model.asp)  
56. AI-Driven Multi-Factor Quantitative Trading Strategy | by FMZQuant \- Medium, accessed August 14, 2025, [https://medium.com/@FMZQuant/ai-driven-multi-factor-quantitative-trading-strategy-7ded62032576](https://medium.com/@FMZQuant/ai-driven-multi-factor-quantitative-trading-strategy-7ded62032576)  
57. Multi-factor Intelligent Trading Strategy | by Sword Red \- Medium, accessed August 14, 2025, [https://medium.com/@redsword\_23261/multi-factor-intelligent-trading-strategy-44c2239a517e](https://medium.com/@redsword_23261/multi-factor-intelligent-trading-strategy-44c2239a517e)  
58. macrosynergy.com, accessed August 14, 2025, [https://macrosynergy.com/research/category/quantitative-methods/\#:\~:text=Two%20valid%20methods%20to%20combine,and%20gives%20them%20equal%20weights.](https://macrosynergy.com/research/category/quantitative-methods/#:~:text=Two%20valid%20methods%20to%20combine,and%20gives%20them%20equal%20weights.)  
59. Quantitative Methods Archives | Macrosynergy, accessed August 14, 2025, [https://macrosynergy.com/research/category/quantitative-methods/](https://macrosynergy.com/research/category/quantitative-methods/)  
60. Portfolio Management – A practical guide \- APM, accessed August 14, 2025, [https://www.apm.org.uk/book-shop/portfolio-management-a-practical-guide/](https://www.apm.org.uk/book-shop/portfolio-management-a-practical-guide/)  
61. Gamma Scalping: Real-Time Delta & Gamma Hedging Techniques \- Profitmart, accessed August 14, 2025, [https://profitmart.in/blog/gamma-scalping-and-hedging/](https://profitmart.in/blog/gamma-scalping-and-hedging/)  
62. Gamma Scalping Strategies \- QuestDB, accessed August 14, 2025, [https://questdb.com/glossary/gamma-scalping-strategies/](https://questdb.com/glossary/gamma-scalping-strategies/)  
63. Gamma Scalping: Building an Options Strategy with Python and Alpaca's Trading API, accessed August 14, 2025, [https://alpaca.markets/learn/gamma-scalping](https://alpaca.markets/learn/gamma-scalping)  
64. Use the Kelly criterion for optimal position sizing \- PyQuant News, accessed August 14, 2025, [https://www.pyquantnews.com/the-pyquant-newsletter/use-kelly-criterion-optimal-position-sizing](https://www.pyquantnews.com/the-pyquant-newsletter/use-kelly-criterion-optimal-position-sizing)  
65. The Smart Trader's Guide to Kelly's Criterion \- tastylive, accessed August 14, 2025, [https://www.tastylive.com/news-insights/smart-trader-guide-kellys-criterion](https://www.tastylive.com/news-insights/smart-trader-guide-kellys-criterion)  
66. Position Sizing using the Kelly Criterion. | by Olsonngula \- Medium, accessed August 14, 2025, [https://medium.com/@olsonngula/position-sizing-using-the-kelly-criterion-e6b381bb6bb9](https://medium.com/@olsonngula/position-sizing-using-the-kelly-criterion-e6b381bb6bb9)  
67. KELLY CRITERION | Ed Thorp | Optimal Position Sizing For Stock Trading \- YouTube, accessed August 14, 2025, [https://www.youtube.com/watch?v=THYLv5\_0Vm8](https://www.youtube.com/watch?v=THYLv5_0Vm8)  
68. How to Use Kelly Criterion Trading Options, accessed August 14, 2025, [https://www.environmentaltradingedge.com/trading-education/how-to-use-kelly-criterion-trading-options](https://www.environmentaltradingedge.com/trading-education/how-to-use-kelly-criterion-trading-options)  
69. Position Sizing: The Vital Secret to Success in Stock Investing : r/ValueInvesting \- Reddit, accessed August 14, 2025, [https://www.reddit.com/r/ValueInvesting/comments/12h19ks/position\_sizing\_the\_vital\_secret\_to\_success\_in/](https://www.reddit.com/r/ValueInvesting/comments/12h19ks/position_sizing_the_vital_secret_to_success_in/)  
70. Backtesting.py – An Introductory Guide to Backtesting with Python \- Interactive Brokers LLC, accessed August 14, 2025, [https://www.interactivebrokers.com/campus/ibkr-quant-news/backtesting-py-an-introductory-guide-to-backtesting-with-python/](https://www.interactivebrokers.com/campus/ibkr-quant-news/backtesting-py-an-introductory-guide-to-backtesting-with-python/)  
71. Backtesting.py \- Backtest trading strategies in Python, accessed August 14, 2025, [https://kernc.github.io/backtesting.py/](https://kernc.github.io/backtesting.py/)  
72. QuantRocket \- Data-Driven Trading with Python, accessed August 14, 2025, [https://www.quantrocket.com/](https://www.quantrocket.com/)  
73. Successful Backtesting of Algorithmic Trading Strategies \- Part I | QuantStart, accessed August 14, 2025, [https://www.quantstart.com/articles/Successful-Backtesting-of-Algorithmic-Trading-Strategies-Part-I/](https://www.quantstart.com/articles/Successful-Backtesting-of-Algorithmic-Trading-Strategies-Part-I/)  
74. Look-Ahead Bias In Backtests And How To Detect It | by Michael Harris | Medium, accessed August 14, 2025, [https://mikeharrisny.medium.com/look-ahead-bias-in-backtests-and-how-to-detect-it-ad5e42d97879](https://mikeharrisny.medium.com/look-ahead-bias-in-backtests-and-how-to-detect-it-ad5e42d97879)  
75. Look-Ahead Bias \- Definition and Practical Example \- Corporate Finance Institute, accessed August 14, 2025, [https://corporatefinanceinstitute.com/resources/career-map/sell-side/capital-markets/look-ahead-bias/](https://corporatefinanceinstitute.com/resources/career-map/sell-side/capital-markets/look-ahead-bias/)  
76. How to Avoid Common Mistakes in Backtesting? \- Quantra by QuantInsti, accessed August 14, 2025, [https://quantra.quantinsti.com/glossary/How-to-Avoid-Common-Mistakes-in-Backtesting](https://quantra.quantinsti.com/glossary/How-to-Avoid-Common-Mistakes-in-Backtesting)  
77. How to take into account bid-ask spread differences when back testing? \- Reddit, accessed August 14, 2025, [https://www.reddit.com/r/algotrading/comments/10w4qsy/how\_to\_take\_into\_account\_bidask\_spread/](https://www.reddit.com/r/algotrading/comments/10w4qsy/how_to_take_into_account_bidask_spread/)  
78. Backtesting Options Strategies \- Top Tools and Step-by-Step Guide \- OptionsTrading.org, accessed August 14, 2025, [https://www.optionstrading.org/blog/backtesting-options-strategies-how-to/](https://www.optionstrading.org/blog/backtesting-options-strategies-how-to/)  
79. Modeling bid-ask spread and slippage in backtest : r/algotrading \- Reddit, accessed August 14, 2025, [https://www.reddit.com/r/algotrading/comments/1fxtvhv/modeling\_bidask\_spread\_and\_slippage\_in\_backtest/](https://www.reddit.com/r/algotrading/comments/1fxtvhv/modeling_bidask_spread_and_slippage_in_backtest/)  
80. Using Backtesting to Avoid Slippage in Equities Trading \- Exegy, accessed August 14, 2025, [https://www.exegy.com/avoiding-slippage-equities-trading-with-backtesting/](https://www.exegy.com/avoiding-slippage-equities-trading-with-backtesting/)  
81. Slippage \- Key Concepts \- QuantConnect.com, accessed August 14, 2025, [https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/key-concepts](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/key-concepts)  
82. Expert Guide to Backtesting Trading Strategies & Tools to Use \- QuantVPS, accessed August 14, 2025, [https://www.quantvps.com/blog/backtesting-trading-strategies](https://www.quantvps.com/blog/backtesting-trading-strategies)  
83. Backtesting Options Strategies: Best practices in 2025 \- Forex Tester, accessed August 14, 2025, [https://forextester.com/blog/backtest-options-strategies/](https://forextester.com/blog/backtest-options-strategies/)  
84. Options Backtesting: How to Backtest with Alpaca's Trading API (with Python Examples), accessed August 14, 2025, [https://alpaca.markets/learn/backtesting-your-options-trading-strategies](https://alpaca.markets/learn/backtesting-your-options-trading-strategies)