import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
SRC_PATH = BACKEND_ROOT / "src"
for candidate in (SRC_PATH, BACKEND_ROOT):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from src.services.exit_signal_eval_service import (
    evaluations_for_conditions,
    timing_from_cached_evaluations,
)


def test_timing_from_cached_evaluations_preserves_agent_evaluator():
    conditions = ["Approaches highs near $351.85"]
    cached = [
        {
            "text": "Approaches highs near $351.85",
            "status": "unmet",
            "reason": "10% below high",
            "evaluator": "agent",
            "tools_used": ["compare_price_to_level"],
        }
    ]
    timing = timing_from_cached_evaluations(conditions, cached)
    assert timing["conditions"][0]["status"] == "unmet"
    assert timing["conditions"][0].get("evaluator") == "agent"


def test_evaluations_for_conditions_aligns_by_text():
    cached = [{"text": "Cond A", "status": "met", "evaluator": "agent"}]
    aligned = evaluations_for_conditions(["Cond A", "Cond B"], cached)
    assert aligned[0]["status"] == "met"
    assert aligned[1]["status"] == "unknown"
