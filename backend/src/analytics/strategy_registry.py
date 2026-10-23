from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

import pandas as pd

from .swing_ranker import run_dual_mode_ranking


StrategyRunner = Callable[[pd.DataFrame, int], Dict[str, Dict[str, List[dict]]]]


@dataclass(frozen=True)
class StrategyDefinition:
    strategy_id: str
    label: str
    description: str
    documentation_file: str
    runner: StrategyRunner


DEFAULT_STRATEGY_ID = "peer_v1"


STRATEGY_REGISTRY: Dict[str, StrategyDefinition] = {
    DEFAULT_STRATEGY_ID: StrategyDefinition(
        strategy_id=DEFAULT_STRATEGY_ID,
        label="Peer Classification v1",
        description=(
            "Hybrid peer-cluster stock ranking with dual-mode options overlays "
            "(sell_premium and buy_premium)."
        ),
        documentation_file="docs/STOCK_SELECTION_STRATEGIES.md",
        runner=run_dual_mode_ranking,
    ),
}


def get_strategy(strategy_id: str) -> StrategyDefinition:
    if strategy_id not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown stock selection strategy: {strategy_id}")
    return STRATEGY_REGISTRY[strategy_id]


def list_strategies() -> List[dict]:
    return [
        {
            "strategy_id": strategy.strategy_id,
            "label": strategy.label,
            "description": strategy.description,
            "documentation_file": strategy.documentation_file,
            "is_default": strategy.strategy_id == DEFAULT_STRATEGY_ID,
        }
        for strategy in STRATEGY_REGISTRY.values()
    ]
