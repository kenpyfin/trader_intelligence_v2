from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


MIN_CLUSTER_SIZE = 12
DEFAULT_CONTEXT_WEIGHT = 0.15
DEFAULT_FACTOR_WEIGHT = 0.85


def _safe_numeric(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(series, errors="coerce")


def _parse_market_cap_value(value) -> float:
    if value is None:
        return np.nan
    if isinstance(value, (int, float, np.number)):
        return float(value)
    text = str(value).strip().upper().replace(",", "")
    if not text:
        return np.nan
    multiplier = 1.0
    if text.endswith("T"):
        multiplier = 1e12
        text = text[:-1]
    elif text.endswith("B"):
        multiplier = 1e9
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1e6
        text = text[:-1]
    elif text.endswith("K"):
        multiplier = 1e3
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return np.nan


def assign_market_cap_bucket(market_cap: float) -> str:
    if pd.isna(market_cap):
        return "unknown"
    if market_cap < 3e8:
        return "micro"
    if market_cap < 2e9:
        return "small"
    if market_cap < 1e10:
        return "mid"
    if market_cap < 2e11:
        return "large"
    return "mega"


def winsorize_series(series: pd.Series, lower_q: float = 0.01, upper_q: float = 0.99) -> pd.Series:
    s = _safe_numeric(series)
    if s.dropna().empty:
        return s
    lo, hi = s.quantile(lower_q), s.quantile(upper_q)
    return s.clip(lower=lo, upper=hi)


def robust_scale(series: pd.Series) -> pd.Series:
    s = _safe_numeric(series)
    med = s.median()
    iqr = s.quantile(0.75) - s.quantile(0.25)
    if pd.isna(iqr) or iqr == 0:
        return s - med
    return (s - med) / iqr


def _simple_kmeans(matrix: np.ndarray, k: int, iterations: int = 30) -> np.ndarray:
    if len(matrix) == 0:
        return np.array([], dtype=int)
    if len(matrix) <= k:
        return np.arange(len(matrix), dtype=int)
    rng = np.random.default_rng(42)
    idx = rng.choice(len(matrix), size=k, replace=False)
    centroids = matrix[idx].copy()
    labels = np.zeros(len(matrix), dtype=int)
    for _ in range(iterations):
        distances = np.linalg.norm(matrix[:, None, :] - centroids[None, :, :], axis=2)
        new_labels = np.argmin(distances, axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for c in range(k):
            members = matrix[labels == c]
            if len(members) == 0:
                centroids[c] = matrix[rng.integers(0, len(matrix))]
            else:
                centroids[c] = members.mean(axis=0)
    return labels


@dataclass
class ClusterResult:
    clustered_frame: pd.DataFrame
    exclusions_by_reason: Dict[str, int]


def preprocess_feature_frame(feature_frame: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int]]:
    df = feature_frame.copy()
    exclusions: Dict[str, int] = {}
    required_cols = ["ticker", "Sector", "Industry"]
    for col in required_cols:
        missing = df[col].isna() | (df[col].astype(str).str.strip() == "")
        count = int(missing.sum())
        if count:
            exclusions[f"missing_{col.lower()}"] = count
        df = df.loc[~missing]

    if df.empty:
        return df, exclusions

    df["market_cap"] = df["Market_cap"].apply(_parse_market_cap_value)
    df["market_cap_bucket"] = df["market_cap"].apply(assign_market_cap_bucket)

    mandatory_numeric = [
        "ret_10d",
        "ret_20d",
        "vol_20d",
        "trend_20_60",
        "drawdown_20d",
        "adv20_dollar",
        "value_score",
        "quality_score",
        "resilience_score",
        "positioning_score",
        "iv_rank",
    ]
    available = [c for c in mandatory_numeric if c in df.columns]
    if available:
        completeness = df[available].notna().mean(axis=1)
        incomplete_mask = completeness < 0.85
        count = int(incomplete_mask.sum())
        if count:
            exclusions["insufficient_feature_completeness"] = count
        df = df.loc[~incomplete_mask].copy()
        df["data_completeness"] = completeness.loc[df.index]
    else:
        df["data_completeness"] = 1.0

    if df.empty:
        return df, exclusions

    for col in available:
        col_missing = df[col].isna().mean()
        if col_missing <= 0.15:
            df[col] = df[col].fillna(df[col].median())
        else:
            exclusions[f"feature_high_missing_{col}"] = int(df[col].isna().sum())

    for col in available:
        df[col] = robust_scale(winsorize_series(df[col]))

    return df, exclusions


def cluster_peers(
    preprocessed_frame: pd.DataFrame,
    min_cluster_size: int = MIN_CLUSTER_SIZE,
    context_weight: float = DEFAULT_CONTEXT_WEIGHT,
    factor_weight: float = DEFAULT_FACTOR_WEIGHT,
) -> ClusterResult:
    df = preprocessed_frame.copy()
    exclusions: Dict[str, int] = {}
    if df.empty:
        return ClusterResult(df, exclusions)

    numeric_cols = [
        c
        for c in [
            "ret_10d",
            "ret_20d",
            "vol_20d",
            "trend_20_60",
            "drawdown_20d",
            "adv20_dollar",
            "value_score",
            "quality_score",
            "resilience_score",
            "positioning_score",
            "iv_rank",
            "market_cap",
        ]
        if c in df.columns
    ]
    factors = df[numeric_cols].fillna(0.0).to_numpy(dtype=float)

    context = pd.get_dummies(
        df[["Sector", "Industry", "market_cap_bucket"]].astype(str),
        columns=["Sector", "Industry", "market_cap_bucket"],
    ).to_numpy(dtype=float)

    matrix = np.hstack(
        [
            factors * np.sqrt(max(factor_weight, 1e-6)),
            context * np.sqrt(max(context_weight, 1e-6)),
        ]
    )

    n = len(df)
    k = max(4, min(40, int(np.sqrt(n / 2.0))))
    labels = _simple_kmeans(matrix, k)
    df["cluster_id"] = [f"C{int(x):03d}" for x in labels]

    # merge undersized clusters into nearest valid centroid
    changed = True
    while changed:
        changed = False
        counts = df["cluster_id"].value_counts()
        small_clusters = counts[counts < min_cluster_size].index.tolist()
        valid_clusters = counts[counts >= min_cluster_size].index.tolist()
        if not small_clusters or not valid_clusters:
            break
        centroids = {cid: matrix[df["cluster_id"] == cid].mean(axis=0) for cid in counts.index}
        for cid in small_clusters:
            candidates = []
            for tgt in valid_clusters:
                dist = float(np.linalg.norm(centroids[cid] - centroids[tgt]))
                candidates.append((dist, tgt))
            if not candidates:
                continue
            target = sorted(candidates, key=lambda x: x[0])[0][1]
            df.loc[df["cluster_id"] == cid, "cluster_id"] = target
            changed = True

    final_counts = df["cluster_id"].value_counts()
    bad_clusters = final_counts[final_counts < min_cluster_size].index.tolist()
    if bad_clusters:
        bad_mask = df["cluster_id"].isin(bad_clusters)
        exclusions["cluster_below_min_size"] = int(bad_mask.sum())
        df = df.loc[~bad_mask].copy()

    if df.empty:
        return ClusterResult(df, exclusions)

    # cluster coherence: inverse mean distance to centroid
    matrix_df = pd.DataFrame(matrix, index=preprocessed_frame.index)
    matrix_df = matrix_df.loc[df.index]
    coherence = {}
    for cid in df["cluster_id"].unique():
        idx = df.index[df["cluster_id"] == cid]
        points = matrix_df.loc[idx].to_numpy(dtype=float)
        centroid = points.mean(axis=0)
        mean_dist = float(np.linalg.norm(points - centroid, axis=1).mean()) if len(points) else 0.0
        coherence[cid] = 1.0 / (1.0 + mean_dist)
    df["cluster_size"] = df["cluster_id"].map(df["cluster_id"].value_counts()).astype(int)
    df["cluster_coherence"] = df["cluster_id"].map(coherence).astype(float)

    return ClusterResult(df, exclusions)


def build_feature_frame(
    fundamentals: pd.DataFrame,
    daily_metrics: pd.DataFrame,
    intraday_metrics: pd.DataFrame,
    iv_metrics: pd.DataFrame,
) -> pd.DataFrame:
    base = fundamentals.copy()
    for src in [daily_metrics, intraday_metrics, iv_metrics]:
        if src is None or src.empty:
            continue
        cols = [c for c in src.columns if c != "ticker"]
        base = base.merge(src[["ticker"] + cols], on="ticker", how="left")
    return base

