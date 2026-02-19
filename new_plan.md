Feasibility summary (given current stack: FMP, Finviz, IB, Mongo, FastAPI + React)            

 • Core pricing engine                                                                        
    • Feasible now: You already have a CRR-capable binomial pricer (via                       
      universal_binomial_pricer) with time-varying r and sigma and American/European support. 
      Greeks (Δ, Γ, Θ) are implemented; Vega via bump is in place. Portfolio Greeks are       
      partially aggregated in strategy analysis.                                              
    • Needed upgrades: Default to CRR, make strike-specific vol input (per-leg) first-class,  
      and add an earnings event adjustment (jump or volatility bump).                         
 • IV surface and relative value                                                              
    • Feasible (per-expiration smile): Finviz export provides IV per strike. You can calibrate
      SABR per expiration and compute residuals (market IV minus fitted IV). This is practical
      without intraday data.                                                                  
    • Not feasible without new data: Arbitrage-free full term surface across maturities with  
      institutional-grade constraints; intraday calibration; execution-side contextual UOA.   
 • Data ingestion and preprocessing                                                           
    • Feasible: Adjust equity history for splits/dividends using FMP endpoints (you already   
      have split calendar). Add a Treasury yield curve from public sources or FMP endpoints;  
      or keep your ETF-parity implied rate as “Alt Rf” alongside a Treasury curve.            
    • Not feasible with current providers: Survivorship-bias-free, intraday options           
      (AlgoSeek/TickData) unless you add a paid provider.                                     
 • Options sentiment and multi-factor                                                         
    • Feasible: Replace fixed thresholds (e.g., P/C ratios, parity deviations) with rolling   
      z-scores/percentiles stored in Mongo. Keep OI walls logic.                              
    • Partially feasible: UOA execution context (at bid/ask side) likely not available via    
      Finviz. You can approximate with volume>>OI + bid/ask spreads/last-trade, but true      
      aggressor-side identification needs a different data source.                            
 • Market regime (HMM)                                                                        
    • Feasible: Implement basic HMM (e.g., hmmlearn) on daily returns/vol features and persist
      model params in Mongo. Start with 2–3 regimes.                                          
 • Risk management and sizing                                                                 
    • Feasible: Portfolio net Greeks and simple risk limits (already partially present).      
      Fractional Kelly sizing requires backtest stats—add once a minimal backtester is in     
      place.                                                                                  
 • Backtesting and validation                                                                 
    • Feasible (simplified): Event-driven, EOD backtests using backtesting.py, model          
      transaction costs using bid/ask from Finviz/IB and basic slippage. Avoid lookahead bias 
      using point-in-time storage. Full intraday options simulation is not feasible without a 
      new data provider.                                                                      
 • Broker integration                                                                         
    • Feasible: You already have IBTrader; expand with recent orders, cancellations, and      
      ensure async lifecycle and error handling are robust.                                   

Upgrade plan (incremental, testable, reversible)                                              

Stage 1: Data hygiene and foundations                                                         

 • Goal: Get clean inputs and a robust risk-free rate; persist rolling stats.                 
 • Scope:                                                                                     
    • Add corporate actions adjustments to historical equity series (splits, dividends) using 
      FMP endpoints. Persist “adjusted” series in Mongo.                                      
    • Add Treasury yield curve builder (bootstrap or piecewise from public Treasury API or FMP
      yields). Keep current ETF-parity implied rate as an alternative, tag which rate was     
      used.                                                                                   
    • Persist rolling time series needed for z-scores/percentiles (e.g., P/C volume ratios,   
      parity deviations) per ticker in Mongo.                                                 
 • Success criteria:                                                                          
    • Unit tests prove split adjustment correctness, dividend yield application, and curve    
      construction sanity (no negative forward rates).                                        
    • Analysis endpoints can switch between Treasury curve and ETF-implied rate.              
 • Code changes (brief):                                                                      
    • backend/src/my_libs_py3/my_data.py: add adjust_with_corporate_actions().                
    • backend/src/analytics/analysis.py: new treasury_curve.py helper; refactor               
      calculate_market_implied_rate usage.                                                    
    • backend/src/services/analysis_service.py: wire new inputs and persist rolling metrics.  
 • Tests:                                                                                     
    • Golden-file tests for adjustments; curve monotonicity checks; caching behavior.         

Stage 2: Pricing engine and surface fit (per-expiration SABR)                                 

 • Goal: Improve pricing realism and enable relative value flags.                             
 • Scope:                                                                                     
    • Default binomial model to CRR; keep Jarrow-Rudd as option.                              
    • Accept strike-specific vol for each priced option; for each K/expiry, derive σ(K) from  
      fitted SABR parameters based on market IVs from Finviz.                                 
    • Compute residuals: market IV – fitted IV; flag statistically significant outliers       
      (z-score across strikes for that expiry).                                               
    • Add event adjustment: If earnings within expiry, apply a jump-variance add-on or a      
      calibrated vol bump to the term structure for that ticker/expiry.                       
 • Success criteria:                                                                          
    • Pricing endpoint returns “relative value” annotations for options with residuals beyond 
      threshold.                                                                              
    • For earnings expirations, prices/Greeks change directionally as expected when enabling  
      event mode.                                                                             
 • Code changes (brief):                                                                      
    • backend/src/analytics/analysis.py: add sabr.py (calibration + IV function). Refactor    
      universal_binomial_pricer caller to feed strike-specific vol term.                      
    • backend/src/services/analysis_service.py: assemble per-expiry market IVs, fit SABR,     
      compute residuals; add “relative_value” in synthesis_data.                              
 • Tests:                                                                                     
    • SABR calibration convergence on synthetic smiles; residuals sanity (mean ~0); CRR vs JR 
      parity on flat vol.                                                                     

Stage 3: Signal normalization and integration                                                 

 • Goal: Replace fixed thresholds with robust, comparable signals.                            
 • Scope:                                                                                     
    • For P/C ratio and parity deviation, compute rolling percentiles/z-scores per ticker     
      (e.g., 252d). Store history in Mongo.                                                   
    • Recast UOA heuristics using relative measures (e.g., volume percentile by strike and    
      DTE). Document limitations due to missing aggressor-side info.                          
    • Add an initial multi-factor integrator: equal-weight normalized features to start;      
      output a composite score and textual rationale.                                         
 • Success criteria:                                                                          
    • API returns normalized signal values and a composite score; frontend visualizes         
      percentiles and historical bands.                                                       
 • Code changes (brief):                                                                      
    • backend/src/services/analysis_service.py: normalization utilities; composite score      
      generator.                                                                              
    • backend/src/analytics/analysis.py: helper to compute rolling stats and persist.         
 • Tests:                                                                                     
    • Deterministic normalization on seeded data; composite score stability test.             

Stage 4: Regime detection and portfolio risk controls                                         

 • Goal: Make strategy suggestions regime-aware; enforce portfolio Greek limits.              
 • Scope:                                                                                     
    • Implement an HMM on daily returns/vol features (2–3 states). Persist fitted model and   
      last inferred state; refresh periodically.                                              
    • Tie strategy suggestions to regime (e.g., favor credit in high-vol regimes).            
    • Compute and display portfolio-level net Greeks; enforce configurable limits with alerts.
      Add basic fractional Kelly calculator using backtest stats placeholders.                
 • Success criteria:                                                                          
    • Regime label exposed via API; suggestions vary by regime and IV regime (high/low).      
    • Portfolio limits generate alerts when exceeded.                                         
 • Code changes (brief):                                                                      
    • backend/src/analytics/regime.py: hmmlearn model, fit/forecast/persist.                  
    • backend/src/services/analysis_service.py: incorporate regime in final bias and          
      suggestions; portfolio limits endpoint.                                                 
 • Tests:                                                                                     
    • HMM fit on synthetic regimes; limit breach unit tests; Kelly boundary checks.           

Stage 5: Backtesting and validation (MVP)                                                     

 • Goal: Validate signals and sizing; establish reproducible tests.                           
 • Scope:                                                                                     
    • Introduce backtesting.py adapter for options strategies using EOD option prices from    
      Finviz/IB where available; simulate bid/ask and simple slippage model; avoid lookahead  
      by point-in-time chain snapshots in Mongo.                                              
    • Compute summary stats (win rate, avg win/loss) to feed fractional Kelly for sizing      
      guidance.                                                                               
    • Add out-of-sample split and simple cross-validation.                                    
 • Success criteria:                                                                          
    • Backtest results available for a small subset (e.g., SPY/QQQ) with reproducible runs and
      stored configs.                                                                         
    • Sizing recommendations populated from backtests in analysis responses.                  
 • Code changes (brief):                                                                      
    • backend/src/backtest/engine.py: wrappers for backtesting.py; slippage/cost models;      
      loaders.                                                                                
    • backend/src/services/backtest_service.py: endpoints to run/report backtests.            
 • Tests:                                                                                     
    • Backtest fixtures on toy data; no lookahead checks; transaction cost application tests. 

Data and provider considerations                                                              

 • Keep current providers for MVP:                                                            
    • Finviz: EOD option chains, bid/ask, IV per option (sufficient for per-expiration SABR). 
    • FMP: equities, splits/dividends, realtime quotes.                                       
    • IB: live quotes and live orders.                                                        
 • Optional upgrades (behind feature flags):                                                  
    • Treasury curve from official Treasury API for higher fidelity.                          
    • Historical options (intraday, trade aggressor): integrate when a paid source is         
      available. Design data interfaces now so swapping providers requires no business-logic  
      changes.                                                                                

Risks and mitigations                                                                         

 • Limited options history (no intraday): constrain backtests to EOD with conservative        
   cost/slippage; clearly label limitations.                                                  
 • UOA execution context unavailable: document as “approximate UOA” using relative volume vs  
   OI.                                                                                        
 • SABR calibration stability on sparse strikes: add robust loss with weights, parameter      
   bounds, and fallback to spline fit if SABR fails.                                          
 • Earnings jump modeling: start with a calibrated vol bump; defer full jump-diffusion lattice
   until data supports it.                                                                    

Minimal code touchpoints (where to implement)                                                 

 • analytics/                                                                                 
    • analysis.py: keep core helpers; add sabr.py; small refactors for strike-specific vol/CRR
      default.                                                                                
    • regime.py: HMM module.                                                                  
 • services/                                                                                  
    • analysis_service.py: orchestrate new features (normalization, SABR fit, regime-aware    
      synthesis).                                                                             
    • backtest_service.py: new.                                                               
 • my_libs_py3/                                                                               
    • my_data.py: corporate action adjustments and rolling metric persistence.                
    • fmp.py: Treasury endpoints if used.                                                     
    • TD_Order.py: enhance order/cancel/status utilities as needed.                           

What to show in the UI (frontend)                                                             

 • Display yield curve source (Treasury vs ETF implied).                                      
 • Show per-expiration SABR smile and residual outliers.                                      
 • Show normalized signal percentiles and historical bands.                                   
 • Regime badge and how it affected the suggestion.                                           
 • Portfolio Greeks vs limits and fractional Kelly sizing suggestion (when available).        
 • Backtest summary (dataset window, in/out-of-sample metrics, costs assumptions).            

