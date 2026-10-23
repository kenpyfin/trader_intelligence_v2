import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "backend"
SRC_PATH = BACKEND_ROOT / "src"

for candidate in (SRC_PATH, BACKEND_ROOT):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from src.analytics.peer_classification import preprocess_feature_frame, cluster_peers
from src.analytics.swing_ranker import run_dual_mode_ranking


def _build_frame(n=36):
    rows = []
    for i in range(n):
        rows.append(
            {
                "ticker": f"T{i:03d}",
                "Sector": "Technology" if i % 2 == 0 else "Healthcare",
                "Industry": "Software" if i % 3 == 0 else "Biotech",
                "Market_cap": 20_000_000_000 + i * 100_000_000,
                "ret_10d": 0.01 * ((i % 7) - 3),
                "ret_20d": 0.01 * ((i % 11) - 5),
                "vol_20d": 0.25 + 0.005 * (i % 9),
                "trend_20_60": 0.02 * ((i % 5) - 2),
                "drawdown_20d": -0.05 - 0.01 * (i % 4),
                "adv20_dollar": 10_000_000 + i * 75_000,
                "value_score": 0.4 + 0.01 * (i % 15),
                "quality_score": 0.45 + 0.01 * (i % 12),
                "resilience_score": 0.5 + 0.01 * (i % 10),
                "positioning_score": 0.48 + 0.01 * (i % 8),
                "iv_rank": 0.2 + 0.02 * (i % 20),
                "data_completeness": 0.95,
            }
        )
    return pd.DataFrame(rows)


def test_preprocess_and_cluster_pipeline():
    raw = _build_frame()
    preprocessed, exclusions = preprocess_feature_frame(raw)
    assert not preprocessed.empty
    assert isinstance(exclusions, dict)

    clustered = cluster_peers(preprocessed, min_cluster_size=6)
    assert not clustered.clustered_frame.empty
    assert "cluster_id" in clustered.clustered_frame.columns
    assert "cluster_coherence" in clustered.clustered_frame.columns


def test_dual_mode_ranking_outputs_groups():
    raw = _build_frame()
    preprocessed, _ = preprocess_feature_frame(raw)
    clustered = cluster_peers(preprocessed, min_cluster_size=6)
    grouped = run_dual_mode_ranking(clustered.clustered_frame, top_n_per_group=3)

    assert "sell_premium" in grouped
    assert "buy_premium" in grouped
    assert "clusters" in grouped["sell_premium"]
    assert isinstance(grouped["sell_premium"]["clusters"], list)

