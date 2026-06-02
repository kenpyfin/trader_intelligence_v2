import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
SRC_PATH = BACKEND_ROOT / "src"

for candidate in (SRC_PATH, BACKEND_ROOT):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from src.analytics.execution_signal_evaluator import (
    build_entry_context,
    evaluate_entry_timing,
    evaluate_exit_timing,
    evaluate_conditions,
)


def _base_analysis_package() -> dict:
    return {
        "dte": 30,
        "final_bias": "Bullish",
        "iv_high": True,
        "iv_low": False,
        "market_data": {
            "current_price": 100.0,
            "implied_volatility": 0.5,
            "historical_volatility": 0.25,
            "iv_hv_ratio": 2.0,
            "days_to_earnings": 10,
        },
        "volatility_structure": {
            "iv_rank": 0.8,
            "hv_rank": 0.6,
        },
        "candlestick_analysis": {
            "technical_indicators": {
                "rsi": 75.0,
                "macd": 2.0,
                "macd_signal": 1.0,
                "sma20": 95.0,
                "sma50": 90.0,
                "sma200": 80.0,
            }
        },
    }


def test_build_entry_context_contains_core_fields():
    pkg = _base_analysis_package()
    ctx = build_entry_context(pkg)
    assert ctx["current_price"] == 100.0
    assert ctx["implied_volatility"] == 0.5
    assert ctx["iv_rank"] == 0.8
    assert ctx["rsi"] == 75.0
    assert ctx["dte"] == 30


def test_evaluate_entry_timing_iv_rank_above_threshold_met():
    pkg = _base_analysis_package()
    ctx = build_entry_context(pkg)
    conds = ["Enter when IV rank above 60%"]
    result = evaluate_entry_timing(conds, ctx)
    assert result["status"] == "enter_now"
    assert result["conditions"][0]["status"] == "met"


def test_evaluate_entry_timing_iv_rank_below_threshold_unmet():
    pkg = _base_analysis_package()
    ctx = build_entry_context(pkg)
    conds = ["Only enter when IV rank below 40%"]
    result = evaluate_entry_timing(conds, ctx)
    assert result["status"] == "wait"
    assert result["conditions"][0]["status"] == "unmet"


def test_evaluate_entry_timing_rsi_overbought_condition():
    pkg = _base_analysis_package()
    ctx = build_entry_context(pkg)
    conds = ["RSI above 70"]
    result = evaluate_entry_timing(conds, ctx)
    assert result["conditions"][0]["status"] == "met"


def test_evaluate_entry_timing_price_above_sma200():
    pkg = _base_analysis_package()
    ctx = build_entry_context(pkg)
    conds = ["Price above SMA200"]
    result = evaluate_entry_timing(conds, ctx)
    assert result["conditions"][0]["status"] == "met"
    assert result["status"] == "enter_now"


def test_evaluate_conditions_unknown_when_no_rules_match():
    ctx = {"current_price": 100.0}
    conds = ["Subjective discretion based on tape reading"]
    result = evaluate_entry_timing(conds, ctx)
    assert result["status"] == "review"
    assert result["conditions"][0]["status"] == "unknown"


def test_evaluate_exit_timing_close_now_when_all_met():
    ctx = {
        "dte": 5,
        "days_to_earnings": 2,
    }
    conds = [
        "Close when DTE below 7",
        "Consider closing within 3 days of earnings",
    ]
    result = evaluate_exit_timing(conds, ctx)
    assert result["status"] == "close_now"


def test_evaluate_exit_timing_wait_when_any_unmet():
    ctx = {
        "dte": 30,
        "days_to_earnings": 40,
    }
    conds = [
        "Close when DTE below 7",
        "Consider closing within 3 days of earnings",
    ]
    result = evaluate_exit_timing(conds, ctx)
    assert result["status"] == "wait"


def test_evaluate_exit_timing_close_on_max_profit_percent():
    ctx = {
        "strategy_is_credit_spread": True,
        "initial_credit_received": 200.0,
        "unrealized_pnl": 120.0,
        "aggregate_unrealized_pnl": 120.0,
        "dte": 10,
    }
    conds = ["Close at 50% max profit"]
    result = evaluate_exit_timing(conds, ctx)
    assert result["status"] == "close_now"
    assert result["conditions"][0]["status"] == "met"


def test_evaluate_exit_timing_stop_loss_multiple_of_credit():
    ctx = {
        "strategy_is_credit_spread": True,
        "initial_credit_received": 100.0,
        "unrealized_pnl": -250.0,
        "aggregate_unrealized_pnl": -250.0,
        "dte": 10,
    }
    conds = ["Stop loss at 2x credit received"]
    result = evaluate_exit_timing(conds, ctx)
    assert result["status"] == "close_now"
    assert result["conditions"][0]["status"] == "met"


def test_evaluate_exit_timing_underlying_below_threshold_or_logic():
    ctx = {
        "underlying_price": 60.74,
        "dte": 50,
        "days_to_earnings": None,
        "unrealized_pnl": -295.0,
        "aggregate_unrealized_pnl": -295.0,
        "strategy_is_credit_spread": None,
        "initial_credit_received": None,
    }
    conds = [
        "Take profit if CFG reaches the $72.50 Call Wall.",
        "Stop out if CFG breaks and closes below the 20-day low of $63.29.",
    ]
    result = evaluate_exit_timing(conds, ctx)
    assert result["status"] == "close_now"


def test_evaluate_conditions_empty_list_review():
    result = evaluate_conditions([], {}, mode="entry")
    assert result["status"] == "review"
    assert result["conditions"] == []

