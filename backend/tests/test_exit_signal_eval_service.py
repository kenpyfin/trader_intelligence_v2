import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
SRC_PATH = BACKEND_ROOT / "src"
for candidate in (SRC_PATH, BACKEND_ROOT):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from src.services.exit_signal_eval_service import merge_regex_and_agent_evaluations


def test_merge_regex_wins_when_parseable():
    ctx = {
        "initial_credit_received": 1000.0,
        "unrealized_pnl": 600.0,
    }
    cond = "Close at 50% max profit"
    agent = [
        {
            "text": cond,
            "status": "unmet",
            "reason": "agent disagrees",
            "evaluator": "agent",
        }
    ]
    merged = merge_regex_and_agent_evaluations([cond], ctx, agent)
    assert merged[0]["status"] == "met"
    assert merged[0].get("evaluator") == "regex"


def test_merge_uses_agent_when_regex_unknown():
    ctx = {"underlying_price": 316.38}
    agent = [
        {
            "text": "Approaches highs near $351.85",
            "status": "unmet",
            "reason": "Too far from high.",
            "evaluator": "agent",
        }
    ]
    merged = merge_regex_and_agent_evaluations(
        ["Approaches highs near $351.85"],
        ctx,
        agent,
    )
    assert merged[0]["status"] == "unmet"
    assert merged[0].get("evaluator") == "agent"
