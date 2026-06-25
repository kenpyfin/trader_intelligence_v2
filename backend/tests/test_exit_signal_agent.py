import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
SRC_PATH = BACKEND_ROOT / "src"
for candidate in (SRC_PATH, BACKEND_ROOT):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from src.analytics.exit_signal_agent import (
    _parse_batch_evaluations,
    _parse_condition_eval,
    evaluate_exit_condition_with_agent,
    evaluate_exit_conditions_with_agent,
)


from src.analytics.exit_signal_tools import ExitSignalToolDeps


def test_parse_condition_eval_json():
    raw = json.dumps(
        {
            "text": "Price near highs",
            "status": "unmet",
            "reason": "Spot 316.38 is 10% below 351.85.",
            "tools_used": ["get_spot_price"],
        }
    )
    out = _parse_condition_eval(raw, "Price near highs", ["get_spot_price"], [])
    assert out["status"] == "unmet"
    assert "316" in out["reason"]
    assert out["evaluator"] == "agent"


def test_evaluate_exit_condition_agent_mocked_tool_then_json():
    tool_response = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "compare_price_to_level",
                                "args": {"current_price": 316.38, "level": 351.85},
                            }
                        }
                    ]
                },
            }
        ]
    }
    final_response = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "text": "Underlying approaches highs near $351.85",
                                    "status": "unmet",
                                    "reason": "316.38 is ~10% below 351.85, not near.",
                                    "tools_used": ["compare_price_to_level"],
                                }
                            )
                        }
                    ]
                },
            }
        ]
    }

    deps = ExitSignalToolDeps(spot_overrides={"XYZ": 316.38})
    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return tool_response, None
        return final_response, None

    with patch("src.analytics.exit_signal_agent._gemini_generate", side_effect=fake_generate):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            result = evaluate_exit_condition_with_agent(
                ticker="XYZ",
                condition_text="Underlying price approaches recent highs near $351.85",
                deps=deps,
            )

    assert result["status"] == "unmet"
    assert "compare_price_to_level" in result.get("tools_used", [])
    assert len(calls) >= 2


def test_parse_batch_single_object_matches_by_text_not_only_first():
    conditions = [
        "Approaches highs near $351.85",
        "IV expansion before earnings",
    ]
    raw = json.dumps(
        {
            "text": "IV expansion before earnings",
            "status": "met",
            "reason": "IV rank elevated",
            "tools_used": ["get_iv_context"],
        }
    )
    rows = _parse_batch_evaluations(raw, conditions, ["get_iv_context"], [])
    assert rows[0]["status"] == "unknown"
    assert rows[1]["status"] == "met"


def test_parse_batch_evaluations_all_conditions_array():
    conditions = [
        "Approaches highs near $351.85",
        "IV expansion before earnings",
    ]
    raw = json.dumps(
        {
            "evaluations": [
                {
                    "text": "Approaches highs near $351.85",
                    "status": "unmet",
                    "reason": "318 vs 351",
                    "tools_used": ["compare_spot_to_stated_levels"],
                },
                {
                    "text": "IV expansion before earnings",
                    "status": "met",
                    "reason": "IV rank elevated",
                    "tools_used": ["get_iv_context"],
                },
            ]
        }
    )
    rows = _parse_batch_evaluations(raw, conditions, ["a", "b"], [])
    assert len(rows) == 2
    assert rows[0]["status"] == "unmet"
    assert rows[1]["status"] == "met"


def test_evaluate_all_conditions_single_session():
    tool_response = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "get_spot_price",
                                "args": {"ticker": "XYZ"},
                            }
                        }
                    ]
                },
            }
        ]
    }
    final_response = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "evaluations": [
                                        {
                                            "text": "Cond A",
                                            "status": "unmet",
                                            "reason": "A reason",
                                            "tools_used": ["get_spot_price"],
                                        },
                                        {
                                            "text": "Cond B",
                                            "status": "met",
                                            "reason": "B reason",
                                            "tools_used": ["get_spot_price"],
                                        },
                                    ]
                                }
                            )
                        }
                    ]
                },
            }
        ]
    }

    deps = ExitSignalToolDeps(spot_overrides={"XYZ": 100.0})
    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return tool_response, None
        return final_response, None

    with patch("src.analytics.exit_signal_agent._gemini_generate", side_effect=fake_generate):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            results = evaluate_exit_conditions_with_agent(
                ticker="XYZ",
                conditions=["Cond A", "Cond B"],
                deps=deps,
            )

    assert len(results) == 2
    assert results[0]["status"] == "unmet"
    assert results[1]["status"] == "met"
    assert len(calls) == 2


def test_evaluate_all_conditions_retries_when_first_response_incomplete():
    conditions = ["Cond A", "Cond B"]
    tool_response = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "get_spot_price",
                                "args": {"ticker": "XYZ"},
                            }
                        }
                    ]
                },
            }
        ]
    }
    partial_response = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "evaluations": [
                                        {
                                            "text": "Cond A",
                                            "status": "unmet",
                                            "reason": "A only",
                                            "tools_used": ["get_spot_price"],
                                        }
                                    ]
                                }
                            )
                        }
                    ]
                },
            }
        ]
    }
    complete_response = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "evaluations": [
                                        {
                                            "text": "Cond A",
                                            "status": "unmet",
                                            "reason": "A reason",
                                            "tools_used": ["get_spot_price"],
                                        },
                                        {
                                            "text": "Cond B",
                                            "status": "met",
                                            "reason": "B reason",
                                            "tools_used": ["get_spot_price"],
                                        },
                                    ]
                                }
                            )
                        }
                    ]
                },
            }
        ]
    }

    deps = ExitSignalToolDeps(spot_overrides={"XYZ": 100.0})
    calls = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return tool_response, None
        if len(calls) == 2:
            return partial_response, None
        return complete_response, None

    with patch("src.analytics.exit_signal_agent._gemini_generate", side_effect=fake_generate):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            results = evaluate_exit_conditions_with_agent(
                ticker="XYZ",
                conditions=conditions,
                deps=deps,
            )

    assert len(results) == 2
    assert results[0]["status"] == "unmet"
    assert results[1]["status"] == "met"
    assert len(calls) == 3
    assert "incomplete" in calls[2]["contents"][-1]["parts"][0]["text"].lower()
