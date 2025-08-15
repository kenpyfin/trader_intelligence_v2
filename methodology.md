# Trader Intelligence: Holistic Analysis Methodology

This document describes the end-to-end methodology used to produce a holistic market view and final trading bias for a given ticker and option expiration. It also maps each step to the backend implementation and notes engineering improvements.

## 1) High-Level Pipeline

- Inputs
  - Ticker, target expiration date, user-selected risk-free rate (or macro, market-implied rate), model settings (binomial variant, American/European).
- Data ingestion
  - Realtime price: FMP realtimequote
  - Option chain for the chosen expiration: Finviz (CSV export)
  - Stock details (dividend yield, earnings date): Finviz
  - Historical OHLCV: PriceDataFetcher (Mongo/IB/FMP/Finviz as needed)
  - IV term structure (ATM IVs): Finviz at target DTEs (7, 30, 90) with fallback
- Preprocessing
  - Clean strikes, volumes, OI (numeric coercion)
  - Historical Volatility (HV) from daily log-returns (annualized with sqrt(252))
  - Earnings date parsing (supports multiple formats; infers year when needed)
  - Build IV curve and generate forward vols for each day to expiry
- Core modeling
  - Price options with a daily-step binomial tree (Jarrow–Rudd by default; CRR optional), supporting:
    - Time-varying σ(t) via forward-vol term structure
    - Time-varying r(t) (constant today but interface accepts arrays/callables)
    - Continuous dividend yield
    - American or European exercise
  - Greeks
    - Delta: from t=1 nodes
    - Gamma: from t=2 nodes via Δ up – Δ down
    - Theta: 2-step finite-difference approximation
    - Vega: reprice after an absolute +1% IV shift to the entire term structure

## 2) Sub-Analyses

### 2.1 Trend and candlestick analysis
- Trend context
  - SMAs: 20/50/100/200
  - Primary trend: price vs SMA200 (Uptrend/Downtrend)
  - Secondary trend: price vs SMA50 (Uptrend/Downtrend)
  - SMA50 vs SMA200 cross state (Golden/Death Cross)
- Candlestick patterns (last 1–3 sessions, volume-aware)
  - Patterns: Hammer, Bullish/Bearish Engulfing, Piercing/Dark Cloud, Morning/Evening Star, Shooting Star, Doji, Spinning Top
  - Volume context: day’s volume vs 10-day average (+10% threshold)
  - Each detection includes interpretation, confirmation trigger (break of high/low), and strength (Strong/Moderate/Weak/Neutral)
- Sentiment mapping and weighting
  - Trend sentiment:
    - Both primary and secondary up → bullish
    - Both down → bearish
    - Mixed → neutral
    - Weight ≈ 1.5
  - Candlesticks:
    - Bullish-only → bullish
    - Bearish-only → bearish
    - Mixed/none → neutral

### 2.2 Options sentiment: parity, volume, OI
- Put/Call parity deviation (near-ATM strikes)
  - (C − P) − (S − K·e^(−rT)); average as % of spot
  - Thresholds:
    - > +0.15% → bullish (calls relatively rich)
    - < −0.15% → bearish (puts relatively rich)
    - Else → neutral
  - Weight ≈ 0.5
- Put/Call volume ratio
  - pc_ratio = total_put_volume / total_call_volume
  - pc_ratio < 0.7 → bullish; > 1.0 → bearish; else neutral
- Unusual Option Activity (UOA)
  - OTM legs with Volume > OI and Volume > 500
  - Rank by Vol/OI ratio; keep top candidates
  - Calls add bullish; puts add bearish (heavier bump ~1.5)
- OI walls (support/resistance)
  - Among OTM puts/calls: max OI strike
  - Condition: OI > 3× group mean and > 1000 → wall (put wall = support, call wall = resistance)

### 2.3 Volatility and movement analysis
- Expected move from ATM straddle
  - EM% ≈ (ATM Call + ATM Put) / Spot × 100
- IV vs HV regime
  - Spot IV estimate (nearest to 0-DTE from IV curve)
  - Compare IV to HV(20)
    - IV > 1.2 × HV → high IV regime (credit-selling bias)
    - IV < 0.8 × HV → low IV regime (debit-buying bias)
    - Else neutral IV regime
- Volatility compression (“coiling”)
  - HV(10) vs HV(50): HV10 < 0.8 × HV50 → compression
  - If earnings within 21D and before expiry, highlight as context
- Earnings timing
  - If earnings date is after today and before expiry → major catalyst

### 2.4 Quantitative valuation (model vs market)
- Strike selection
  - Around spot: up to ~6 ITM and ~6 OTM for each side
- Pricing
  - Model price via binomial tree (time-varying vol/r, dividend yield)
  - Market price priority: midpoint(Bid/Ask) with spread sanity checks
- Undervaluation screen
  - If model > market: compute $ and % undervaluation
  - Sort by Undervalued %; top pick drives directional takeaway:
    - Undervalued Call → bullish
    - Undervalued Put → bearish
- Cross-check
  - If model vs market differs by > $0.10 and > 20%, add a calibration/microstructure caution

### 2.5 IV term structure construction
- Fetch ATM IV at DTEs [7, 30, 90] via Finviz
- If a target date has no chain, search forward up to 7 days; reuse IV with original DTE label
- Ensure a 0-DTE proxy:
  - If 0-DTE missing but other points exist, copy shortest-term IV to DTE=0
- Forward vols (daily)
  - Interpolate spot vol σ(t) across maturities (0…DTE)
  - Convert to forward vols with variance additivity:
    - σ_fwd(i, i+1) = sqrt((σ^2(t+Δ)(t+Δ) − σ^2(t)·t)/Δ), Δ = 1/365

### 2.6 Market‑implied risk‑free rate (optional macro input)
- For liquid ETFs (default: SPY, QQQ, IWM):
  - Synthetic forward: F = S − C + P; r = −(1/T)·ln(F/K)
  - Filter outliers (−5% to 25%); average per ticker; then average across tickers

## 3) Holistic Synthesis and Bias Resolution

- Each sub-module emits:
  - sentiment: bullish/bearish/neutral (or regime/event)
  - summary: concise, human-readable
  - optional weight
- Weighting (key examples)
  - Trend ≈ 1.5; Parity ≈ 0.5; others default to 1 unless specified
- Bias score
  - Sum bullish weights vs bearish weights across directional components (trend, candlestick, parity, volume/oi, undervalued)
- Final bias classification
  - bull > bear + 1 → Bullish
  - bear > bull + 1 → Bearish
  - bull > bear → Slightly Bullish
  - bear > bull → Slightly Bearish
  - otherwise → Neutral
- Additional context (non-directional)
  - IV regime (high/low vs HV)
  - Expected move and compression notes
  - Earnings timing (if before expiry)
- Strategy mapping (guidance)
  - Neutral bias:
    - High IV → premium-selling (iron condor)
    - Low IV → premium-buying (long straddle)
  - Bullish bias:
    - High IV → bull put credit spread
    - Low/neutral IV → bull call debit spread
  - Bearish bias:
    - High IV → bear call credit spread
    - Low/neutral IV → bear put debit spread

## 4) Position- and Strategy-Level Alerts

- Single option (position)
  - Profit/stop alerts vs open price (% thresholds)
  - Delta saturation alerts (|Δ| ≥ 0.8 → behaves like stock)
  - High gamma near expiry (γ > 0.04 and DTE ≤ 45)
  - Theta headwind (daily theta as % of price > 1% when DTE ≤ 45)
  - Vega sensitivity (from +1% IV bump)
  - American early-exercise map with immediate premium at t0
  - ATM with DTE ≤ 21 → theta acceleration alert
- Multi-leg strategy (aggregate)
  - Aggregate model/market P&L vs open cost/credit
  - Net Greeks (Δ, Γ, Θ, Vega)
  - Strategy-level profit/stop alerts
  - Shortest-leg time pressure (DTE ≤ 7) → closure suggestion
  - Delta magnitude: indicates directional bias
  - Vega exposure vs open cost: IV sensitivity
  - Net early-exercise benefit across long American legs

## 5) Safeguards and Assumptions

- Market price extraction priority:
  - Mid(Bid/Ask) with spread sanity checks, else (optional) Last Trade, else (optional) Last Close when enabled
- IV fetch logs and warnings when data is missing or inferred
- Earnings date parsing supports multiple formats; year inferred when omitted
- If IV unavailable, fallback to HV(20) for σ(0); if neither, default to flat 20%
- Binomial discretization error exists; daily step is a practical compromise for speed and American exercise detection
- Vega via finite difference assumes parallel IV shift (no skew/smile dynamics)
- Finviz data quality (spreads, stale last trades) can impact parity/undervaluation
- HV(10)/HV(50) compression heuristic is intentionally simple

---

# Backend Mapping

This section maps the methodology to concrete backend modules, functions, and endpoints.

## A) Data Providers

- FMP realtime price
  - backend/src/my_libs_py3/fmp.py → FMPClient.realtimequote
- Historical OHLCV
  - backend/src/my_libs_py3/my_data.py → PriceDataFetcher.get_price_data(method="td_data")
- Option chain (Finviz)
  - backend/src/my_libs_py3/my_data.py → PriceDataFetcher.get_option_data_finviz
- Stock details (dividend yield, earnings)
  - backend/src/my_libs_py3/my_data.py → PriceDataFetcher.get_stock_details_finviz

## B) Volatility Building Blocks

- Historical Volatility
  - backend/src/services/analysis_service.py → calculate_historical_volatility(prices, lookback_days=20)
- IV term structure (ATM IV with fallback)
  - backend/src/services/analysis_service.py → fetch_iv_term_structure(ticker, price_fetcher, fmp_client, target_dtes=[7,30,90])
- Forward vols (daily)
  - backend/src/services/analysis_service.py → generate_forward_vol_structure(days_to_expiration, key_vol_points)

## C) Option Pricing + Greeks

- Binomial pricer (Jarrow–Rudd default; CRR optional; American/European)
  - backend/src/services/analysis_service.py → universal_binomial_pricer(S, K, expiration_date, r_input, sigma_input, model, option_type, exercise_type, div)
  - Greeks: delta (t=1), gamma (t=2), theta (2-step FD); vega via reprice after +1% IV bump

## D) Sub-Analyses

- Options sentiment: volume, OI, UOA, walls
  - backend/src/services/analysis_service.py → analyze_volume_and_oi_signals(df, S_current)
  - Put/Call ratio thresholds; OTM UOA; OI walls (3× mean and >1000)
- Expected move and compression
  - backend/src/services/analysis_service.py → analyze_high_movement_expectation(S_current, option_chain_df, historical_prices_df, earnings_date, expiration_date)
  - Uses _get_market_price_from_finviz_df to get ATM call/put
- Earnings parsing
  - backend/src/services/analysis_service.py → parse_earnings_date(earnings_str)
- Candlestick/trend analysis
  - backend/src/services/analysis_service.py → analyze_candlestick_patterns(df)
  - Primary/secondary trend and recent patterns with volume context
- Put/Call parity deviation
  - Computed inline in run_full_analysis over selected strikes where both C and P are available:
    - parity_diff = (C − P) − (S − K·e^(−rT))

## E) Holistic Synthesis and Strategy Mapping

- backend/src/services/analysis_service.py → generate_holistic_conclusion(synthesis_data, strikes, S_current)
  - Aggregates sentiments (trend, candlesticks, parity, volume/oi, iv_hv, movement, undervalued)
  - Produces final_bias string and an HTML summary
  - Maps bias + IV regime to suggested strategies and example legs

## F) End-to-End Orchestration

- Full analysis (frontend calls this)
  - backend/src/services/analysis_service.py → run_full_analysis(ticker, expiration_date: date, r_current=0.045)
    - Fetch realtime price (FMP), option chain (Finviz), historical prices (PriceDataFetcher)
    - Compute HV, build IV term structure, generate forward vols
    - Fetch dividend yield and earnings date (Finviz)
    - Run sub-analyses: candlestick, volume/oi, movement/expected-move
    - Valuation loop: model vs market; collect undervalued options
    - Build synthesis_data → generate_holistic_conclusion
    - Return JSON object: status, ticker, S_current, expiration_date (ISO), final_conclusion_html, final_bias, suggested strategy, candlestick_analysis, volume_oi_analysis, movement_analysis, results_df (if any)
- Lean analysis (POC/testing)
  - backend/src/analytics/analysis.py → run_analysis (lighter flow)

---

# API Endpoints and Frontend Contracts

- backend/src/main.py
  - GET /macro-data → macro_service.get_macro_futures_data
  - POST /calculate-risk-free-rate → macro_service.calculate_market_implied_risk_free_rate
  - GET /analysis/expirations/{ticker} → analysis_service.get_option_expirations
  - POST /analysis/stock → analysis_service.run_full_analysis (wrapped in an array; adds DTE before returning)
  - POST /orders/strategy → broker_service.place_strategy_order
  - Portfolio (via backend/src/routers/portfolio.py):
    - GET /portfolio/open-positions → portfolio_service.get_grouped_open_positions
    - POST /portfolio/close-strategy → portfolio_service.close_strategy
    - GET /portfolio/recent-orders → portfolio_service.get_recent_orders_service

- Models
  - backend/src/models/analysis_models.py → AnalysisRequest, RiskFreeRateRequest
  - backend/src/models/order_models.py → OrderLeg, StrategyOrderRequest
  - backend/src/models/portfolio_models.py → PositionLeg, CloseStrategyRequest

- Frontend expectations
  - Analysis.js calls:
    - GET /analysis/expirations/{ticker} → returns array of YYYYMMDD strings
    - POST /analysis/stock (AnalysisRequest) → returns array with one object including final_conclusion_html, final_bias, recommended strategy, S_current, expiration_date, dte, plus analysis sections
    - POST /orders/strategy
    - GET /macro-data and POST /calculate-risk-free-rate
  - Portfolio.js calls:
    - GET /portfolio/open-positions
    - GET /portfolio/recent-orders
    - POST /portfolio/close-strategy

---

# Engineering Notes and Improvements

1) IB async mismatch in historical IB fallback
- Where: backend/src/my_libs_py3/my_data.py → _fetch_from_ib
- Issue: IBTrader.connect is async; calling synchronously causes fetch failures when falling back to IB.
- Options:
  - Add connect_sync in IBTrader that invokes IB().connect(...) synchronously and use it in _fetch_from_ib.
  - Or instantiate a local IB() in _fetch_from_ib and connect there synchronously.

2) Portfolio PnL/market value enrichment
- Where: backend/src/services/portfolio_service.py (consumes IBTrader.open_positions)
- Issue: Missing marketValue/unrealizedPNL → portfolio summary shows zeros.
- Suggestion:
  - For stocks: fetch last via IB and compute marketValue = last × position; unrealizedPNL = (last − avgCost) × position.
  - For options: use multiplier 100; compute similarly (use last or mid).

3) Guard Finviz request exception paths
- Where: backend/src/my_libs_py3/my_data.py → _query_finviz, get_option_data_finviz, get_stock_details_finviz
- Issue: Some except blocks reference response before assignment on failure.
- Fix: Guard with if 'response' in locals() and response is not None before accessing attributes.

4) Liquidity filter strictness (FYI)
- Where: backend/src/services/analysis_service.py → _get_market_price_from_finviz_df
- Behavior: Tight filters for Bid/Ask/Volume/OI without fallback to Last/Close.
- Impact: Improves quality but reduces data availability for parity/expected-move.
- Option: Add an optional fallback flag with staleness checks.

5) Docker Compose mount alignment
- docker-compose.yml mounts both ./backend/src → /app/src and ./backend/my_libs_py3 → /app/my_libs_py3.
- Since imports use src.my_libs_py3, /app/src is sufficient; consider removing the extra mount to reduce confusion.

6) Optional: add connect_sync to IBTrader
- To preserve existing synchronous call sites in my_data, add a connect_sync wrapper; reduces touch points and avoids making my_data async.

---

# Duplication Note

- Core analytics functions (e.g., universal_binomial_pricer, calculate_historical_volatility) exist in both:
  - backend/src/services/analysis_service.py
  - backend/src/analytics/analysis.py
- Recommendation:
  - Make one the single source of truth (prefer services/analysis_service.py) and import where needed to prevent divergence.
