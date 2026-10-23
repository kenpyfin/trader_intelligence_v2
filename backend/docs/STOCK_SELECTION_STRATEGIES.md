# Stock Selection Strategies

This document is the canonical strategy reference for stock selection outputs exposed by the API and UI.

Data-source and field semantics are defined in [`STOCK_SELECTION_DATA_TABLES.md`](STOCK_SELECTION_DATA_TABLES.md) at the repository root. This strategy document assumes those definitions.

---

## Active Built-In Strategy: `peer_v1`

### Objective

Rank liquid, fundamentally sound stocks for 10-20 day swing workflows by combining:

- peer-aware cluster context,
- market-regime conditioning,
- mode-specific options-volatility bias.

### Data Inputs

- `all_symbol.screenerModel`: sector/industry/fundamental snapshot
- `stocks_daily.<TICKER>`: trend, return, volatility, drawdown, liquidity
- `stocks_10minute.<TICKER>`: short-horizon intraday confirmation (optional)
- `iv_history.<TICKER>`: `spot_iv`, `iv_rank`, and term-slope context

### Core Pipeline

1. Build feature frame from fundamentals + daily/intraday + IV features.
2. Enforce quality guards:
   - required context present (`Sector`, `Industry`),
   - minimum feature completeness,
   - enough data history for rolling metrics.
3. Robust preprocessing:
   - winsorize outliers,
   - median-impute low-missingness features,
   - robust-scale numeric features.
4. Cluster peers using hybrid factor/context distance.
5. Remove low-quality undersized clusters.
6. Assign regime buckets and run mode-specific ranking.

### Composite Components

- `fundamental_composite`
- `trend_composite`
- `trend_accel_composite`
- `liquidity_composite`
- `stability_composite`

### Ranking Modes in `peer_v1`

#### `sell_premium`

Target profile: stable/uptrend names with relatively expensive implied volatility.

`selection_score = 0.30*fundamental_composite + 0.25*trend_composite + 0.15*liquidity_composite + 0.15*stability_composite + 0.15*iv_expensive_score`

#### `buy_premium`

Target profile: improving-trend names with relatively cheap implied volatility.

`selection_score = 0.25*fundamental_composite + 0.30*trend_accel_composite + 0.15*liquidity_composite + 0.10*stability_composite + 0.20*iv_cheap_score`

### Confidence

`confidence_score = 0.45*data_completeness + 0.35*cluster_coherence + 0.20*signal_alignment`

### Exclusions

A ticker is excluded when one or more hard requirements fail (for example missing required context, insufficient completeness, unavailable mandatory market features, or invalid cluster membership quality).

### Output Shape

Each ranked stock includes:

- `ticker`, `mode`, `selection_score`, `confidence_score`
- `cluster_id`, `cluster_size`, `cluster_coherence`
- `cluster_rank`, `global_rank`
- `regime_bucket`, `iv_rank`
- factor composites and human-readable `reasons`

---

## Strategy Selection Contract

- API strategy key: `peer_v1`
- The UI and API may support additional built-in strategy keys over time.
- Unknown strategy keys should fail validation at request boundaries.
