# Stock Selection Data Tables

This document catalogs current MongoDB data availability for stock selection in Trader Intelligence and maps each dataset to backend usage.

Audit timestamp: **2026-04-30** (live Mongo inspection against configured host).

---

## Overview

The current system has strong data coverage for:

- broad equity price history (`stocks_daily`, `stocks_10minute`),
- per-ticker implied volatility history (`iv_history`),
- large-scale fundamental snapshots (`all_symbol.screenerModel`).

This is enough to build a robust first version of stock selection based on trend + IV context + fundamentals.

---

## MongoDB Coverage Snapshot

| Database | Collections | Example collections | Selection relevance |
| --- | ---: | --- | --- |
| `stocks_daily` | 32,258 | `AAPL`, `MSFT`, `SPY` | Core daily trend/return features |
| `stocks_10minute` | 29,865 | `AAPL`, `MSFT`, `SPY` | Intraday momentum/liquidity checks |
| `iv_history` | 5,916 | `AAPL`, `NVDA`, `TSLA` | IV rank / vol regime context |
| `all_symbol` | 27 | `screenerModel`, `cantrade`, `momentum` | Fundamental ranking inputs |
| `trader_intelligence` | 3 | `analysis_history`, `verdicts`, `tracked_orders` | Derived signals/history (secondary) |
| `trade_log` | 218 | per-ticker collections | Trading logs (not selection core) |
| `pair_trade_log` | 473 | `TICKER1_TICKER2` collections | Pair-trade logs (not selection core) |

Notes:
- Collection naming is mixed:
  - some DBs use **collection per ticker** (for example `stocks_daily.AAPL`, `iv_history.AAPL`);
  - some DBs use **fixed collection names** (for example `all_symbol.screenerModel`).

---

## Freshness Snapshot (Representative)

| Collection | Min timestamp | Max timestamp | Freshness status |
| --- | --- | --- | --- |
| `stocks_daily.AAPL` (`TimeStamp`) | 2017-09-27 | 2026-04-30 | Good |
| `stocks_10minute.AAPL` (`TimeStamp`) | 2020-04-27 11:00:00 | 2026-04-30 | Good |
| `iv_history.AAPL` (`TimeStamp`) | 2026-02-25 | 2026-04-30 | Good (recent pipeline activity) |
| `all_symbol.screenerModel` (`Refresh_Date`) | 2021-03-15 | 2026-04-30 13:00:07 | Good |
| `trader_intelligence.analysis_history` (`created_at`) | 2025-10-01 | 2026-05-01 00:27:40 | Good |
| `trade_log` (sample collection `PDD`) | 2020-11-16 | 2020-11-17 | Stale for selection use |
| `pair_trade_log` (sample `BJ_SU`) | 2023-10-30 | 2023-11-08 | Stale for selection use |

---

## Field Dictionary by Collection

## 1) Daily Price History: `stocks_daily.<TICKER>`

**Purpose**
- Main source for trend, rolling return, volatility, and regime features.

**Observed fields (sample: `AAPL`)**
- `Ticker`, `TimeStamp`
- `Open`, `High`, `Low`, `Close`, `Volume`
- `Return`, `Fwd_Return`
- `adjClose`, `change`, `changePercent`, `changeOverTime`, `unadjustedVolume`, `vwap`, `label`

**Key pattern**
- Database: `stocks_daily`
- Collection: ticker symbol
- No compound indexes observed (only `_id` on sampled collection).

**Backend usage**
- Default `mongo()` database in [`backend/src/my_libs_py3/db.py`](backend/src/my_libs_py3/db.py).
- Queried by `PriceDataFetcher.get_price_data(..., method='day')` in [`backend/src/my_libs_py3/my_data.py`](backend/src/my_libs_py3/my_data.py).

**Selection value**
- Very high. This is the primary input for trend and momentum factors.

---

## 2) Intraday Price History: `stocks_10minute.<TICKER>`

**Purpose**
- Higher-frequency confirmation for momentum and recency filters.

**Observed fields (sample: `AAPL`)**
- `Ticker`, `TimeStamp`, `Time`
- `Open`, `High`, `Low`, `Close`, `Volume`
- `Return`, `Fwd_Return`

**Key pattern**
- Database: `stocks_10minute`
- Collection: ticker symbol
- No compound indexes observed (only `_id` on sampled collection).

**Backend usage**
- Queried by `PriceDataFetcher.get_price_data(..., method='self_minute')` in [`backend/src/my_libs_py3/my_data.py`](backend/src/my_libs_py3/my_data.py).

**Selection value**
- High for timing/confirmation overlays; optional for first MVP screener.

---

## 3) IV History: `iv_history.<TICKER>`

**Purpose**
- Historical implied volatility context for IV-rank style factors.

**Observed fields (sample: `AAPL`)**
- `Ticker`, `TimeStamp`
- `spot_iv`, `iv_7d`, `iv_30d`, `iv_90d`

**Key pattern**
- Database: `iv_history`
- Collection: ticker symbol
- One record per ticker/day expected by pipeline convention.

**Backend usage**
- IV rank computed in `calculate_iv_rank()` in [`backend/src/analytics/analysis.py`](backend/src/analytics/analysis.py).
- Schema contract documented in [`IV_AND_IV_RANK.md`](IV_AND_IV_RANK.md).

**Selection value**
- Very high. Enables vol regime filters (`iv_rank` high/low/neutral) to pair with trend/fundamental signals.

---

## 4) Fundamental Screener Table: `all_symbol.screenerModel`

**Purpose**
- Broad fundamental ranking universe and sector-based comparisons.

**Observed fields**
- `Ticker`, `Sector`, `Industry`, `Refresh_Date`
- Valuation/quality metrics such as:
  - `P/E`, `P/S`, `P/Cash`, `P/Free Cash Flow`,
  - `Gross Margin`, `Operating Margin`, `Profit Margin`,
  - `Current Ratio`, `Quick Ratio`, `Total Debt/Equity`,
  - `Insider Ownership`, `Institutional Ownership`,
  - `EPS (ttm)`, `Analyst Recom`, `Performance (Week)`,
  - `Sales growth quarter over quarter`.

**Key pattern**
- Database: `all_symbol`
- Collection: `screenerModel`
- Index observed: `Refresh_Date` descending.

**Backend usage**
- Legacy ranking logic reads this collection in `longterm_cumulation.data_feeder()` and computes rank aggregates in [`backend/src/my_libs_py3/TradingPlan.py`](backend/src/my_libs_py3/TradingPlan.py).

**Selection value**
- Very high. Strong candidate for fundamental score components in stock selection.

---

## 5) App-Derived Analysis Data: `trader_intelligence.*`

### `trader_intelligence.analysis_history`

**Observed fields**
- `ticker`, `analysis_method`, `gpt_model`,
- `risk_free_rate`, `override_price`,
- `expiration_date`, `expiration_date_raw`,
- `request_payload`, `analysis_result`, `primary_verdict`,
- `final_bias`, `created_at`.

**Usage**
- Persisted in [`backend/src/services/analysis_history_service.py`](backend/src/services/analysis_history_service.py).

**Selection value**
- Medium. Useful for feedback loops and model diagnostics, not core raw input.

### `trader_intelligence.verdicts`

**Observed fields**
- `ticker`, `expiration_date`, `analysis_method`, `gpt_model`,
- `final_bias`, `label`, `overview`, `data`, `created_at`.

**Usage**
- Persisted in [`backend/src/services/verdict_service.py`](backend/src/services/verdict_service.py).

**Selection value**
- Medium. Could contribute qualitative ranking overlays later.

### `trader_intelligence.tracked_orders`

**Observed fields**
- `ticker`, `expiration_date`, `size`, `is_credit_spread`,
- `legs`, `signature`, `gpt_snapshot`,
- `broker_order_id`, `broker_perm_id`, `ib_order_id`, `ib_perm_id`,
- `broker_trade`, `placed_at`, `status`.

**Usage**
- Persisted in [`backend/src/services/order_tracking_service.py`](backend/src/services/order_tracking_service.py).

**Selection value**
- Low for initial screener; useful for post-selection execution analytics.

---

## 6) Trade Logs (Operational, Not Core Selection Inputs)

### `trade_log.<TICKER>`

**Observed fields**
- `TimeStamp`, `Ticker`, `size`, `raw_size`, `Price`, `Strategy`, optional `Hold_days`.

**Usage**
- Write/read logic in [`backend/src/my_libs_py3/my_trader.py`](backend/src/my_libs_py3/my_trader.py).

### `pair_trade_log.<TICKER1_TICKER2>`

**Observed fields**
- `TimeStamp`, `Ticker1`, `Ticker2`,
- `size1`, `size2`, `Price1`, `Price2`,
- `strategy_size1`, `strategy_size2`.

**Usage**
- Write/read logic in [`backend/src/my_libs_py3/my_pair_trade.py`](backend/src/my_libs_py3/my_pair_trade.py).

**Selection value**
- Low for single-name stock selection; keep as optional behavioral features later.

---

## Code-to-Data Mapping Summary

| Data area | Main reader/writer path | Notes |
| --- | --- | --- |
| Daily/intraday stock bars | [`backend/src/my_libs_py3/my_data.py`](backend/src/my_libs_py3/my_data.py) | `PriceDataFetcher` reads `stocks_daily` and `stocks_10minute` |
| IV rank source | [`backend/src/analytics/analysis.py`](backend/src/analytics/analysis.py) | `calculate_iv_rank()` reads `iv_history.<ticker>` |
| Fundamental ranking reference | [`backend/src/my_libs_py3/TradingPlan.py`](backend/src/my_libs_py3/TradingPlan.py) | Reads `all_symbol.screenerModel` and computes rank-style scores |
| Saved analysis/verdict/tracked orders | [`backend/src/services/analysis_history_service.py`](backend/src/services/analysis_history_service.py), [`backend/src/services/verdict_service.py`](backend/src/services/verdict_service.py), [`backend/src/services/order_tracking_service.py`](backend/src/services/order_tracking_service.py) | Uses `trader_intelligence` DB |
| Trade and pair-trade logs | [`backend/src/my_libs_py3/my_trader.py`](backend/src/my_libs_py3/my_trader.py), [`backend/src/my_libs_py3/my_pair_trade.py`](backend/src/my_libs_py3/my_pair_trade.py) | Operational logs |

---

## Reliability and Quality Notes

1. **Mongo URI handling mismatch**
   - Environment includes `MONGO_URI`, but [`backend/src/my_libs_py3/db.py`](backend/src/my_libs_py3/db.py) hardcodes `mongodb://10.0.1.22:27017`.
   - Impact: deployment portability and environment consistency risk.

2. **`adjusted_prices` persistence path likely broken**
   - [`backend/src/my_libs_py3/my_data.py`](backend/src/my_libs_py3/my_data.py) calls `db = mongo(coll_name="adjusted_prices")` then `db.frame_to_mongo(...)`.
   - The `mongo` wrapper in [`backend/src/my_libs_py3/db.py`](backend/src/my_libs_py3/db.py) does not expose `frame_to_mongo` directly (it exists on `connect_mongo` as `conn.frame_to_mongo`).
   - Impact: adjusted-price write may silently fail or be skipped.

3. **Minimal indexing on large per-ticker collections**
   - Sampled collections mostly only have `_id` index.
   - Impact: slower range queries as symbol/time use grows.

4. **Dual `mongo` abstraction confusion risk**
   - There is also a SQL-oriented class named `mongo` in [`backend/src/my_libs_py3/mysql.py`](backend/src/my_libs_py3/mysql.py).
   - Impact: maintenance confusion when reading legacy code.

---

## Selection Feature Readiness

| Dataset | Readiness | Why |
| --- | --- | --- |
| `stocks_daily` | Ready | Broad coverage, fresh data, known query path |
| `stocks_10minute` | Ready | Broad coverage and fresh data for intraday confirmation |
| `iv_history` | Ready | Fresh daily updates and existing rank logic |
| `all_symbol.screenerModel` | Ready | Large fundamental snapshot with ranking fields and recent refresh |
| `trader_intelligence.*` | Partial | Useful as derived/meta signal layer, not primary market/fundamental source |
| `trade_log` / `pair_trade_log` | Gap (for selection) | Operational logs, stale in sampled collections, low direct selection value |

---

## Candidate Selection Table Spec (Design-Only)

Use this as the first table contract for the new stock selection output.

Updated strategy note:
- For the revised factor-classification peer model (cluster-members, market-regime buckets, dual-mode options ranking), see [`FACTOR_PEER_CLASSIFICATION_SPEC.md`](FACTOR_PEER_CLASSIFICATION_SPEC.md).

| Output field | Type | Source | Description |
| --- | --- | --- | --- |
| `ticker` | string | all core datasets | Symbol key |
| `as_of_date` | datetime | runtime | Snapshot timestamp |
| `trend_score` | float | `stocks_daily` | Composite of medium/long trend and return quality |
| `momentum_score` | float | `stocks_10minute` + `stocks_daily` | Near-term momentum confirmation |
| `iv_rank` | float/null | `iv_history` | Relative IV regime over lookback |
| `fundamental_score` | float | `all_symbol.screenerModel` | Aggregated quality/valuation rank |
| `liquidity_score` | float | `stocks_daily` volume fields | Liquidity confidence proxy |
| `selection_score` | float | computed | Weighted final score |
| `selection_bucket` | string | computed | `core` / `watch` / `exclude` |
| `reasons` | array[string] | computed | Human-readable reason codes |

Suggested initial weighting (tunable):
- `trend_score`: 35%
- `fundamental_score`: 30%
- `iv_rank`-derived component: 20%
- `momentum_score`: 10%
- `liquidity_score`: 5%

---

## Next Build Step (Design-Only)

1. **Build analytics module**
   - Add `backend/src/analytics/stock_selection.py`.
   - Implement pure scoring functions:
     - `compute_trend_score`,
     - `compute_fundamental_score`,
     - `compute_iv_context_score`,
     - `compute_selection_score`.

2. **Build service orchestration**
   - Add `backend/src/services/selection_service.py`.
   - Responsibilities:
     - load universe (from `all_symbol.screenerModel` latest `Refresh_Date`),
     - fetch price/IV slices,
     - join factors,
     - return top-N ranked candidates.

3. **Expose API**
   - Add `backend/src/routers/selection.py` and include it in [`backend/src/main.py`](backend/src/main.py).
   - Minimal endpoints:
     - `POST /selection/run`
     - `GET /selection/latest` (if persistence is later enabled).

4. **Define request/response models**
   - Add `backend/src/models/selection_models.py`.
   - Include:
     - universe controls,
     - factor weights override,
     - minimum liquidity/market-cap/fundamental thresholds.

5. **Create validation notebook**
   - Add `Notebooks/test_stock_selection.ipynb` when pipeline implementation begins, to satisfy local validation workflow before DAG/API hardening.

---

## Appendix: Representative Sample Schemas

`stocks_daily.AAPL`:
- `Ticker`, `TimeStamp`, `Open`, `High`, `Low`, `Close`, `Volume`, `Return`, `Fwd_Return`, `adjClose`, `vwap`, plus change fields.

`iv_history.AAPL`:
- `Ticker`, `TimeStamp`, `spot_iv`, `iv_7d`, `iv_30d`, `iv_90d`.

`all_symbol.screenerModel`:
- `Ticker`, `Sector`, `Refresh_Date`, valuation/profitability/leverage/ownership fields listed above.
