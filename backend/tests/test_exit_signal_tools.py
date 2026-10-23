import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
SRC_PATH = BACKEND_ROOT / "src"
for candidate in (SRC_PATH, BACKEND_ROOT):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from src.analytics.exit_signal_tools import (
    ExitSignalToolDeps,
    compare_price_to_level,
    compare_spot_to_stated_levels,
    execute_tool,
    get_spot_price,
)


def test_compare_price_to_level_not_near():
    result = compare_price_to_level(316.38, 351.85)
    assert result["is_near_default_3pct"] is False
    assert result["abs_pct_diff"] > 3.0


def test_compare_price_to_level_near():
    result = compare_price_to_level(350.0, 351.85)
    assert result["is_near_default_3pct"] is True


def test_get_spot_price_override():
    deps = ExitSignalToolDeps(spot_overrides={"TEST": 316.38})
    out = get_spot_price("TEST", deps)
    assert out["spot_price"] == 316.38
    assert out["source"] == "override"


def test_execute_tool_compare():
    out = execute_tool(
        "compare_price_to_level",
        {"current_price": 316.38, "level": 351.85},
    )
    assert out["is_near_default_3pct"] is False


def test_execute_tool_unknown():
    out = execute_tool("nonexistent_tool", {})
    assert "error" in out


def test_compare_spot_to_stated_levels_318_vs_350_not_near():
    deps = ExitSignalToolDeps(spot_overrides={"XYZ": 318.0})
    cond = "Underlying price approaches recent highs near $351.85"
    out = compare_spot_to_stated_levels("XYZ", cond, deps=deps)
    assert out["any_stated_level_near_spot"] is False
    assert out["stated_level_comparisons"][0]["abs_pct_diff"] > 3.0

