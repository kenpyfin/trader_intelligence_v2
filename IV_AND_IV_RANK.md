# IV Collection and IV Rank

This document describes how **implied volatility (IV)** is collected and how **IV rank** is calculated and used in the Trader Intelligence system.

---

## Overview

The system uses IV in two distinct ways:


| Use                             | Source                                                | Purpose                                                                                 |
| ------------------------------- | ----------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **Real-time IV term structure** | Finviz (with optional Alpaca fallback)                | Single analysis run: spot IV, 7d/30d/90d term structure, IV vs HV comparison            |
| **IV rank**                     | MongoDB `iv_history` (populated by external pipeline) | Percentile of current IV over the past year; drives strategy bias (sell vs buy premium) |


IV rank depends on **historical** IV stored in MongoDB. That history is filled by a separate pipeline (e.g. `collect_iv_history` in My_Trader2.0) that computes IV from the Alpaca option chain and writes one document per ticker per run.

---

## 1. IV Collection (Alpaca)

IV is **computed** from option prices; Alpaca does not provide IV directly.

### Data flow

1. **Spot price:** Alpaca Data API (stock latest quote).
2. **Option chain:** Alpaca Data API `get_option_chain(symbol)` — full chain, no expiration filter.
3. **IV computation:** Back out IV from option premiums using an American binomial model (pyfin).

### Key code

- **Entry point:** `AlpacaTrader.calculate_iv_points_from_data_api(symbol)` in [backend/src/my_libs_py3/TD_Order.py](backend/src/my_libs_py3/TD_Order.py).
- **Logic:** [backend/src/my_libs_py3/iv_from_alpaca.py](backend/src/my_libs_py3/iv_from_alpaca.py).

### Steps inside `iv_from_alpaca`

1. **Parse OCC symbols** in the chain → expiry (YYYYMMDD), right (call/put), strike.
2. **Group by expiry** → for each expiry, list of strikes with mid price (quote midpoint, else bid/ask average, else last trade).
3. **Target tenors:** 7, 30, 90 days to expiration. For each target DTE, pick the expiry closest to that DTE.
4. **ATM selection:** For that expiry, pick the strike closest to spot; prefer call over put for the same strike.
5. **Implied volatility:** From the ATM option’s mid premium, back out IV via `pyfin.Option.imply_volatility()` (American, default risk-free rate 0.05). Only IV in [0.01, 0.99] is accepted.
6. **Output dict:** Keys `"7d"`, `"30d"`, `"90d"` (only tenors that succeeded). Key `"spot"` is set to the shortest available tenor (7d preferred, then 30d, then 90d) for use as `spot_iv` in MongoDB.

### Output shape

```python
# Example
{
    "spot": 0.43,   # Used as spot_iv when writing to MongoDB
    "7d": 0.43,
    "30d": 0.42,
    "90d": 0.41     # May be missing if no suitable expiry
}
```

If the chain is empty or no valid IV can be computed, the function returns `None`.

---

## 2. Pipeline Write to MongoDB (Airflow)

The IV collection pipeline lives in **Airflow**: `airflowProd/notebook/My_Trader2.0/dataCollector.py` → `collect_iv_history()`.

The pipeline:

1. Calls `AlpacaTrader.fetch_iv_points_from_data_api(ticker)` for each tradable ticker.
2. For each ticker with IV data, builds one record with `**TimeStamp = date.today()` at midnight** (no time-of-day).
3. Writes via `connect_mongo("iv_history").update_to_mongo(record, "TimeStamp")` — i.e. **upsert by `TimeStamp`**.

### Multiple runs per day: overwrite

**If you run the pipeline more than once in a day, the stored result is overwritten with the latest run.**  
The document is keyed by `TimeStamp`; since `TimeStamp` is midnight of the current date, every run on the same calendar day matches the same document. `update_to_mongo` uses `update_one({ "TimeStamp": ... }, { "$set": ... }, upsert=True)`, so the second run **updates** that document. You end up with **one document per ticker per day**, holding the **most recent** IV values for that day.

### MongoDB schema contract

- **Database:** `iv_history`
- **Collection:** ticker symbol (e.g. `AAPL`, `GPRO`). Each ticker has its own collection.
- **Document fields:**


| Field       | Type     | Required | Description                                                                                                           |
| ----------- | -------- | -------- | --------------------------------------------------------------------------------------------------------------------- |
| `Ticker`    | string   | Yes      | Ticker symbol (e.g. `"AAPL"`).                                                                                        |
| `TimeStamp` | datetime | Yes      | Midnight of the collection date; used as upsert key so same day = one document.                                       |
| `spot_iv`   | float    | Yes      | Current “spot” IV. Must be the same value as the IV dict’s `"spot"` key from `calculate_iv_points_from_alpaca_chain`. |
| `iv_7d`     | float    | No       | IV for ~7 DTE.                                                                                                        |
| `iv_30d`    | float    | No       | IV for ~30 DTE.                                                                                                       |
| `iv_90d`    | float    | No       | IV for ~90 DTE.                                                                                                       |


Example document:

```json
{
  "Ticker": "AAPL",
  "TimeStamp": "2026-02-25T00:00:00+00:00",
  "spot_iv": 0.3665,
  "iv_7d": 0.3665,
  "iv_30d": 0.4756,
  "iv_90d": null
}
```

If the pipeline runs more than once per day, multiple documents per day are fine; There is at most one document per ticker per day; re-running the same day overwrites it.

---

## 3. IV Rank Calculation

IV rank is the percentile of **current** IV within its **min–max range** over a lookback window (e.g. one year). It is used to decide whether IV is “high” (favor selling premium) or “low” (favor buying premium).

### Where it’s implemented

- [backend/src/analytics/analysis.py](backend/src/analytics/analysis.py): `calculate_iv_rank(ticker, lookback_days=252)`.

### Algorithm

1. **Database:** `connect_mongo("iv_history", ticker)` → database `iv_history`, collection = ticker.
2. **Query:** Documents with `Ticker == ticker` and `TimeStamp >= now - (lookback_days + 30)` days (default: 282 days). Sort by `TimeStamp` ascending. Projection can limit to `spot_iv`.
3. **Extract:** Build a list of `spot_iv` values, skipping documents where `spot_iv` is missing.
4. **Cold start:** If there are fewer than 30 values, return `None` (not enough history).
5. **Rank:**
  - `current_iv = iv_values[-1]`  
  - `min_iv = min(iv_values)`, `max_iv = max(iv_values)`  
  - If `max_iv == min_iv`, return `0.5`.  
  - Otherwise return `(current_iv - min_iv) / (max_iv - min_iv)` (a number in [0, 1]).

### Interpretation

- **most1.0:** Current IV at the maximum over the lookback.
- **0.5:** Current IV in the middle of the range (or flat vol).
- **None:** Cold start (< 30 data points) or error (e.g. MongoDB unreachable).

The GPT verdict uses the same idea as HV rank: e.g. `iv_rank > 0.7` → IV expensive → favor selling premium; `iv_rank < 0.3` → IV cheap → favor buying premium; if `iv_rank` is `None`, it falls back to `hv_rank` with the same thresholds.

---

## 4. Where IV Rank Is Used

- **Analysis payload:** In `run_analysis()`, the result includes `volatility_structure.iv_rank` (float 0–1 or `None`).
- **GPT verdict:** [backend/src/analytics/methodologies/gpt_verdict.py](backend/src/analytics/methodologies/gpt_verdict.py) uses `iv_rank` (and `hv_rank` as fallback) to recommend strategy bias.

---

## 5. Local Validation

Use [Notebooks/test_alpaca.ipynb](Notebooks/test_alpaca.ipynb) to validate without running the full app:

1. **Spot and IV from Alpaca:** Run the cells that call `get_spot_price_from_data_api` and `calculate_iv_points_from_data_api`. Confirm you get a dict with `spot` and at least one of `7d`/`30d`/`90d`.
2. **MongoDB iv_history:** Query `iv_history` for a ticker you know the pipeline has written to. Confirm documents have `Ticker`, `TimeStamp`, `spot_iv`, and optionally `iv_7d`, `iv_30d`, `iv_90d`.
3. **IV rank:** The notebook includes inlined logic that matches `calculate_iv_rank()`. Run it and confirm the rank is in [0, 1] or `None` when there are fewer than 30 points.

MongoDB is configured in [backend/src/my_libs_py3/db.py](backend/src/my_libs_py3/db.py) (default: `mongodb://10.0.1.22:27017`). Ensure the host is reachable from your environment.

---

## 6. Summary Diagram

```
Alpaca (spot + option chain)
        │
        ▼
iv_from_alpaca.calculate_iv_points_from_alpaca_chain()
        │
        ▼
{ "spot", "7d", "30d", "90d" }
        │
        ▼
External pipeline (e.g. collect_iv_history)
        │
        ▼
MongoDB: iv_history DB, collection = ticker, doc = { Ticker, TimeStamp, spot_iv, ... }
        │
        ▼
analysis.calculate_iv_rank(ticker)
        │
        ▼
Float in [0, 1] or None  →  analysis payload & GPT verdict
```

---

## 7. Related Files


| File                                                                                   | Role                                                                                                     |
| -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| [backend/src/my_libs_py3/iv_from_alpaca.py](backend/src/my_libs_py3/iv_from_alpaca.py) | IV computation from Alpaca chain (OCC parsing, ATM, binomial IV).                                        |
| [backend/src/my_libs_py3/TD_Order.py](backend/src/my_libs_py3/TD_Order.py)             | `AlpacaTrader.calculate_iv_points_from_data_api()`; calls `iv_from_alpaca`.                              |
| [backend/src/analytics/analysis.py](backend/src/analytics/analysis.py)                 | `calculate_iv_rank()`, `fetch_iv_term_structure()` (Finviz-based term structure for real-time analysis). |
| [backend/src/my_libs_py3/db.py](backend/src/my_libs_py3/db.py)                         | `connect_mongo()` used for `iv_history` access.                                                          |
| [Notebooks/test_alpaca.ipynb](Notebooks/test_alpaca.ipynb)                             | Local tests for Alpaca IV and IV rank.                                                                   |
| or Alpaca IV and IV rank.                                                              |                                                                                                          |


