from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def _rank01(series: pd.Series, ascending: bool = True) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    return s.rank(pct=True, ascending=ascending).fillna(0.0)


def assign_regime_bucket(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    vol_rank = _rank01(df["vol_20d"], ascending=True)
    trend_rank = _rank01(df["ret_20d"], ascending=True)
    drawdown_rank = _rank01(df["drawdown_20d"], ascending=False)

    bucket = []
    for i in df.index:
        high_vol = vol_rank.loc[i] > 0.6
        strong_trend = trend_rank.loc[i] > 0.55
        weak_trend = trend_rank.loc[i] < 0.35
        deep_drawdown = drawdown_rank.loc[i] < 0.35
        if (not high_vol) and strong_trend:
            bucket.append("calm_trend")
        elif high_vol and strong_trend:
            bucket.append("volatile_trend")
        elif (not high_vol) and weak_trend:
            bucket.append("calm_mean_revert")
        elif high_vol and (weak_trend or deep_drawdown):
            bucket.append("stress")
        else:
            bucket.append("neutral")
    df["regime_bucket"] = bucket
    return df


def compute_mode_scores(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()

    df["fundamental_composite"] = (
        0.30 * _rank01(df["value_score"], ascending=False)
        + 0.40 * _rank01(df["quality_score"], ascending=True)
        + 0.30 * _rank01(df["resilience_score"], ascending=True)
    )
    df["trend_composite"] = (
        0.55 * _rank01(df["trend_20_60"], ascending=True)
        + 0.45 * _rank01(df["ret_20d"], ascending=True)
    )
    df["trend_accel_composite"] = (
        0.60 * _rank01(df["ret_10d"] - df["ret_20d"], ascending=True)
        + 0.40 * _rank01(df["trend_20_60"], ascending=True)
    )
    df["liquidity_composite"] = (
        0.70 * _rank01(df["adv20_dollar"], ascending=True)
        + 0.30 * _rank01(df.get("volume_stability", pd.Series(index=df.index, data=np.nan)), ascending=True)
    )
    df["stability_composite"] = (
        0.50 * _rank01(df["drawdown_20d"], ascending=False)
        + 0.50 * _rank01(df["vol_20d"], ascending=False)
    )

    iv_rank = pd.to_numeric(df["iv_rank"], errors="coerce").fillna(0.5)
    df["iv_expensive_score"] = (iv_rank - 0.5).clip(lower=0.0) * 2.0
    df["iv_cheap_score"] = (0.5 - iv_rank).clip(lower=0.0) * 2.0

    df["score_sell"] = (
        0.30 * df["fundamental_composite"]
        + 0.25 * df["trend_composite"]
        + 0.15 * df["liquidity_composite"]
        + 0.15 * df["stability_composite"]
        + 0.15 * df["iv_expensive_score"]
    )
    df["score_buy"] = (
        0.25 * df["fundamental_composite"]
        + 0.30 * df["trend_accel_composite"]
        + 0.15 * df["liquidity_composite"]
        + 0.10 * df["stability_composite"]
        + 0.20 * df["iv_cheap_score"]
    )
    return df


def _confidence(frame: pd.DataFrame, score_col: str) -> pd.Series:
    alignment = (
        0.4 * _rank01(frame["trend_composite"], ascending=True)
        + 0.4 * _rank01(frame["fundamental_composite"], ascending=True)
        + 0.2 * _rank01(frame[score_col], ascending=True)
    )
    completeness = pd.to_numeric(frame.get("data_completeness"), errors="coerce").fillna(0.0)
    coherence = pd.to_numeric(frame["cluster_coherence"], errors="coerce").fillna(0.0)
    return (0.45 * completeness + 0.35 * coherence + 0.20 * alignment).clip(0.0, 1.0)


def rank_within_clusters(frame: pd.DataFrame, mode: str) -> pd.DataFrame:
    df = frame.copy()
    score_col = "score_sell" if mode == "sell_premium" else "score_buy"
    df["selection_score"] = df[score_col]
    df["mode"] = mode
    df["confidence_score"] = _confidence(df, score_col)
    df = df.sort_values("selection_score", ascending=False)
    df["global_rank"] = np.arange(1, len(df) + 1)
    df["cluster_rank"] = (
        df.groupby("cluster_id")["selection_score"]
        .rank(method="first", ascending=False)
        .astype(int)
    )
    return df


def build_grouped_views(
    ranked_frame: pd.DataFrame,
    top_n_per_group: int,
) -> Dict[str, List[Dict]]:
    df = ranked_frame.copy()
    top_df = df[df["cluster_rank"] <= top_n_per_group].copy()

    def _to_stock_records(group_df: pd.DataFrame) -> List[Dict]:
        records: List[Dict] = []
        for _, row in group_df.sort_values("selection_score", ascending=False).iterrows():
            reasons = []
            if row.get("trend_composite", 0) >= 0.65:
                reasons.append("strong_trend")
            if row.get("fundamental_composite", 0) >= 0.65:
                reasons.append("fundamental_quality")
            if row.get("liquidity_composite", 0) >= 0.65:
                reasons.append("high_liquidity")
            if row.get("mode") == "sell_premium" and row.get("iv_rank", 0.5) >= 0.65:
                reasons.append("iv_expensive")
            if row.get("mode") == "buy_premium" and row.get("iv_rank", 0.5) <= 0.35:
                reasons.append("iv_cheap")
            records.append(
                {
                    "ticker": row["ticker"],
                    "mode": row["mode"],
                    "selection_score": float(row["selection_score"]),
                    "cluster_rank": int(row["cluster_rank"]),
                    "global_rank": int(row["global_rank"]),
                    "confidence_score": float(row["confidence_score"]),
                    "cluster_id": row["cluster_id"],
                    "cluster_size": int(row["cluster_size"]),
                    "cluster_coherence": float(row["cluster_coherence"]),
                    "regime_bucket": row["regime_bucket"],
                    "iv_rank": None if pd.isna(row.get("iv_rank")) else float(row.get("iv_rank")),
                    "fundamental_composite": float(row["fundamental_composite"]),
                    "trend_composite": float(row["trend_composite"]),
                    "liquidity_composite": float(row["liquidity_composite"]),
                    "reasons": reasons,
                }
            )
        return records

    grouped = {"clusters": [], "sectors": [], "regimes": []}

    for cluster_id, grp in top_df.groupby("cluster_id"):
        grouped["clusters"].append(
            {"group_key": cluster_id, "group_label": f"Cluster {cluster_id}", "stocks": _to_stock_records(grp)}
        )
    for sector, grp in top_df.groupby("Sector"):
        grouped["sectors"].append(
            {"group_key": str(sector), "group_label": str(sector), "stocks": _to_stock_records(grp)}
        )
    for regime, grp in top_df.groupby("regime_bucket"):
        grouped["regimes"].append(
            {"group_key": str(regime), "group_label": str(regime), "stocks": _to_stock_records(grp)}
        )
    return grouped


def run_dual_mode_ranking(clustered_frame: pd.DataFrame, top_n_per_group: int = 10) -> Dict[str, Dict[str, List[Dict]]]:
    staged = assign_regime_bucket(clustered_frame)
    staged = compute_mode_scores(staged)
    sell_ranked = rank_within_clusters(staged, "sell_premium")
    buy_ranked = rank_within_clusters(staged, "buy_premium")
    return {
        "sell_premium": build_grouped_views(sell_ranked, top_n_per_group=top_n_per_group),
        "buy_premium": build_grouped_views(buy_ranked, top_n_per_group=top_n_per_group),
    }

