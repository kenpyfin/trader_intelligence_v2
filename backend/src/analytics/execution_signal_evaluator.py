import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple


ConditionEval = Dict[str, Any]
TimingResult = Dict[str, Any]


def _safe_float(val: Any) -> Optional[float]:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f


def build_entry_context(analysis_package: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract a compact context bundle for evaluating entry conditions.
    Expects the full analysis_result_package from analysis.run_analysis.
    """
    market_data = analysis_package.get("market_data") or {}
    vol_struct = analysis_package.get("volatility_structure") or {}
    tech = (analysis_package.get("candlestick_analysis") or {}).get("technical_indicators") or {}

    context: Dict[str, Any] = {
        "current_price": market_data.get("current_price"),
        "implied_volatility": market_data.get("implied_volatility"),
        "historical_volatility": market_data.get("historical_volatility"),
        "iv_hv_ratio": market_data.get("iv_hv_ratio"),
        "days_to_earnings": market_data.get("days_to_earnings"),
        "dte": analysis_package.get("dte"),
        "iv_rank": vol_struct.get("iv_rank"),
        "hv_rank": vol_struct.get("hv_rank"),
        "iv_high": analysis_package.get("iv_high"),
        "iv_low": analysis_package.get("iv_low"),
        "rsi": tech.get("rsi"),
        "macd": tech.get("macd"),
        "macd_signal": tech.get("macd_signal"),
        "sma20": tech.get("sma20"),
        "sma50": tech.get("sma50"),
        "sma200": tech.get("sma200"),
        "final_bias": analysis_package.get("final_bias"),
    }
    return context


def _parse_pct(text: str) -> Optional[float]:
    """
    Extract a single percentage value like '40%' or '40 percent' -> 40.0.
    """
    m = re.search(r"(\d+(\.\d+)?)\s*%|\b(\d+(\.\d+)?)\s*percent", text, re.IGNORECASE)
    if not m:
        return None
    num = m.group(1) or m.group(3)
    return _safe_float(num)


def _parse_threshold_value(text: str) -> Optional[float]:
    """
    Fallback: first plain number in the string.
    """
    m = re.search(r"(\d+(\.\d+)?)", text)
    if not m:
        return None
    return _safe_float(m.group(1))


def _compare_numeric(
    value: Optional[float],
    threshold: Optional[float],
    cmp: str,
) -> Optional[bool]:
    if value is None or threshold is None:
        return None
    if cmp == "gt":
        return value > threshold
    if cmp == "lt":
        return value < threshold
    return None


def _eval_iv_condition(text: str, ctx: Dict[str, Any]) -> Optional[bool]:
    """
    Handle simple IV / IV rank / IV vs HV style strings.
    """
    lowered = text.lower()

    # Explicit IV rank above/below N%
    if "iv rank" in lowered:
        rank = ctx.get("iv_rank")
        pct = _parse_pct(text)
        if rank is None or pct is None:
            return None
        threshold = pct / 100.0
        if "above" in lowered or "over" in lowered or "greater" in lowered:
            return _compare_numeric(rank, threshold, "gt")
        if "below" in lowered or "under" in lowered or "less" in lowered:
            return _compare_numeric(rank, threshold, "lt")
        return None

    iv = ctx.get("implied_volatility")
    hv = ctx.get("historical_volatility")
    ratio = ctx.get("iv_hv_ratio")

    # IV > HV / IV < HV
    if "iv > hv" in lowered or "iv over hv" in lowered:
        if ratio is not None:
            return ratio > 1.0
        if iv is not None and hv is not None:
            return iv > hv
        return None
    if "iv < hv" in lowered or "iv under hv" in lowered:
        if ratio is not None:
            return ratio < 1.0
        if iv is not None and hv is not None:
            return iv < hv
        return None

    # High / low IV language using iv_high / iv_low flags
    if "high iv" in lowered or "elevated iv" in lowered:
        flag = ctx.get("iv_high")
        return bool(flag) if flag is not None else None
    if "low iv" in lowered or "depressed iv" in lowered:
        flag = ctx.get("iv_low")
        return bool(flag) if flag is not None else None

    # Absolute IV percent above/below N%
    if "implied vol" in lowered or "iv " in lowered:
        iv_val = ctx.get("implied_volatility")
        pct = _parse_pct(text)
        if iv_val is None or pct is None:
            return None
        threshold = pct / 100.0
        if "above" in lowered or "over" in lowered or "greater" in lowered:
            return _compare_numeric(iv_val, threshold, "gt")
        if "below" in lowered or "under" in lowered or "less" in lowered:
            return _compare_numeric(iv_val, threshold, "lt")
    return None


def _eval_rsi_condition(text: str, ctx: Dict[str, Any]) -> Optional[bool]:
    rsi = ctx.get("rsi")
    if rsi is None:
        return None
    lowered = text.lower()
    if "rsi" not in lowered:
        return None
    thresh = _parse_threshold_value(text)
    if thresh is None:
        # Interpret generic "overbought/oversold"
        if "overbought" in lowered:
            return rsi > 70
        if "oversold" in lowered:
            return rsi < 30
        return None

    if "above" in lowered or "over" in lowered or "greater" in lowered:
        return _compare_numeric(rsi, thresh, "gt")
    if "below" in lowered or "under" in lowered or "less" in lowered:
        return _compare_numeric(rsi, thresh, "lt")
    return None


def _eval_price_vs_sma(text: str, ctx: Dict[str, Any]) -> Optional[bool]:
    price = ctx.get("current_price")
    if price is None:
        return None
    lowered = text.lower()
    if "sma200" in lowered or "200-day" in lowered:
        sma = ctx.get("sma200")
    elif "sma50" in lowered or "50-day" in lowered:
        sma = ctx.get("sma50")
    elif "sma20" in lowered or "20-day" in lowered:
        sma = ctx.get("sma20")
    else:
        return None
    if sma is None:
        return None

    if "above" in lowered or "over" in lowered:
        return price > sma
    if "below" in lowered or "under" in lowered:
        return price < sma
    return None


def _eval_dte_condition(text: str, ctx: Dict[str, Any]) -> Optional[bool]:
    dte = ctx.get("dte")
    if dte is None:
        return None
    lowered = text.lower()
    if "dte" not in lowered and "days to expiry" not in lowered and "days to expiration" not in lowered:
        return None
    thresh = _parse_threshold_value(text)
    if thresh is None:
        return None
    if "less" in lowered or "under" in lowered or "below" in lowered:
        return _compare_numeric(dte, thresh, "lt")
    if "more" in lowered or "over" in lowered or "above" in lowered:
        return _compare_numeric(dte, thresh, "gt")
    return None


def _eval_earnings_condition(text: str, ctx: Dict[str, Any]) -> Optional[bool]:
    days = ctx.get("days_to_earnings")
    if days is None:
        return None
    lowered = text.lower()
    if "earnings" not in lowered:
        return None

    # Common wording: "before earnings", "after earnings", or "within N days of earnings"
    if "before earnings" in lowered:
        return days > 0
    if "after earnings" in lowered:
        return days < 0
    thresh = _parse_threshold_value(text)
    if thresh is not None and ("within" in lowered or "inside" in lowered):
        return abs(days) <= thresh
    return None


def _evaluate_single_condition(text: str, ctx: Dict[str, Any], mode: str) -> ConditionEval:
    """
    Try several lightweight pattern evaluators; return condition status and reason.
    """
    raw = (text or "").strip()
    if not raw:
        return {"text": text, "status": "unknown", "reason": "Empty condition string"}

    # Dispatch based on obvious keywords first
    checks: List[Tuple[str, Optional[bool]]] = []

    # Exit timing / P&L heuristics (only meaningful in exit mode)
    if mode == "exit":
        checks.append(("max_profit", _eval_max_profit_condition(raw, ctx)))
        checks.append(("stop_loss", _eval_stop_loss_condition(raw, ctx)))
        checks.append(("underlying_threshold", _eval_underlying_threshold_condition(raw, ctx)))

    # Volatility-driven conditions
    checks.append(("iv", _eval_iv_condition(raw, ctx)))

    # RSI / momentum
    checks.append(("rsi", _eval_rsi_condition(raw, ctx)))

    # Price vs SMA
    checks.append(("price_sma", _eval_price_vs_sma(raw, ctx)))

    # DTE / days to expiry
    checks.append(("dte", _eval_dte_condition(raw, ctx)))

    # Earnings timing
    checks.append(("earnings", _eval_earnings_condition(raw, ctx)))

    for label, result in checks:
        if result is None:
            continue
        status = "met" if result else "unmet"
        return {
            "text": text,
            "status": status,
            "reason": f"Evaluated using {label} rule: condition is {status} given current context.",
        }

    return {
        "text": text,
        "status": "unknown",
        "reason": "No matching evaluation rule; requires manual judgment.",
    }


def _aggregate_timing(evals: List[ConditionEval], mode: str) -> TimingResult:
    """
    Aggregate per-condition evaluations into a coarse timing label.
    """
    if not evals:
        return {
            "status": "review",
            "label": "No signals available",
            "summary": "No structured conditions were provided; review the narrative guidance manually.",
            "conditions": [],
        }

    parseable = [e for e in evals if e["status"] in ("met", "unmet")]
    if not parseable:
        return {
            "status": "review",
            "label": "Review conditions",
            "summary": "Conditions are present but could not be machine-evaluated. Review them manually before acting.",
            "conditions": evals,
        }

    all_met = all(e["status"] == "met" for e in parseable)
    any_unmet = any(e["status"] == "unmet" for e in parseable)
    any_met = any(e["status"] == "met" for e in parseable)

    if mode == "entry":
        # Entry conditions are usually AND-like: all parseable entry triggers must be satisfied.
        if all_met and not any_unmet:
            return {
                "status": "enter_now",
                "label": "Good time to enter",
                "summary": "All parseable entry conditions are currently satisfied.",
                "conditions": evals,
            }
        if any_unmet:
            return {
                "status": "wait",
                "label": "Entry conditions not met",
                "summary": "At least one parseable entry condition is not satisfied; consider waiting.",
                "conditions": evals,
            }
    else:
        # Exit conditions are usually OR-like: if any stop/take-profit trigger is satisfied, we should close/act.
        if any_met:
            return {
                "status": "close_now",
                "label": "Close now",
                "summary": "At least one parseable exit condition is satisfied; this is an appropriate time to close.",
                "conditions": evals,
            }
        if any_unmet:
            return {
                "status": "wait",
                "label": "Hold / monitor",
                "summary": "None of the parseable exit conditions are satisfied yet; consider holding but monitor closely.",
                "conditions": evals,
            }

    # Fallback
    return {
        "status": "review",
        "label": "Review conditions",
        "summary": "Conditions were evaluated but no clear signal was derived; review manually.",
        "conditions": evals,
    }


def evaluate_conditions(conditions: List[str], context: Dict[str, Any], mode: str = "entry") -> TimingResult:
    """
    Generic entry/exit condition evaluator; used by thin wrappers below.
    """
    mode = mode or "entry"
    texts = [c for c in (conditions or []) if isinstance(c, str) and c.strip()]
    evals = [_evaluate_single_condition(text, context, mode) for text in texts]
    return _aggregate_timing(evals, mode)


def evaluate_entry_timing(conditions: List[str], context: Dict[str, Any]) -> TimingResult:
    """
    Convenience wrapper for entry evaluation.
    """
    return evaluate_conditions(conditions, context, mode="entry")


def build_exit_context_from_portfolio(
    *,
    symbol: str,
    legs: List[Dict[str, Any]],
    underlying_price: Optional[float],
    aggregate_unrealized_pnl: Optional[float],
    aggregate_market_value: Optional[float],
    dte: Optional[int] = None,
    days_to_earnings: Optional[int] = None,
    strategy_is_credit_spread: Optional[bool] = None,
    initial_credit_received: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Compact context bundle for portfolio exit evaluation.
    """
    ctx: Dict[str, Any] = {
        "symbol": symbol,
        "underlying_price": underlying_price,
        "unrealized_pnl": aggregate_unrealized_pnl,
        "aggregate_unrealized_pnl": aggregate_unrealized_pnl,
        "aggregate_market_value": aggregate_market_value,
        "dte": dte,
        "days_to_earnings": days_to_earnings,
        "legs_count": len(legs or []),
        "strategy_is_credit_spread": strategy_is_credit_spread,
        "initial_credit_received": initial_credit_received,
    }
    return ctx


def evaluate_exit_timing(conditions: List[str], context: Dict[str, Any]) -> TimingResult:
    """
    Convenience wrapper for exit / close evaluation.
    """
    return evaluate_conditions(conditions, context, mode="exit")


def aggregate_exit_timing(evals: List[ConditionEval]) -> TimingResult:
    """Aggregate per-condition exit evaluations (OR logic for close_now)."""
    return _aggregate_timing(evals, mode="exit")


def evaluate_exit_timing_hybrid(
    conditions: List[str],
    context: Dict[str, Any],
    agent_evaluations: Optional[List[Dict[str, Any]]] = None,
) -> TimingResult:
    """
    Regex-first exit evaluation; agent cache fills in unknown conditions.
    """
    from src.services.exit_signal_eval_service import merge_regex_and_agent_evaluations

    texts = [c for c in (conditions or []) if isinstance(c, str) and c.strip()]
    merged = merge_regex_and_agent_evaluations(texts, context, agent_evaluations)
    result = aggregate_exit_timing(merged)
    return result


def _eval_max_profit_condition(text: str, ctx: Dict[str, Any]) -> Optional[bool]:
    """
    Example text:
      - "Close at 50% max profit"
      - "Take 60% of max profit"
    """
    lowered = text.lower()
    if "max profit" not in lowered and "max-profit" not in lowered:
        return None
    pct = _parse_pct(text)
    if pct is None:
        return None
    max_profit = ctx.get("initial_credit_received")
    unrealized = ctx.get("unrealized_pnl")
    if max_profit is None or unrealized is None:
        return None
    if max_profit <= 0:
        return None
    target = (pct / 100.0) * max_profit
    return unrealized >= target


def _eval_stop_loss_condition(text: str, ctx: Dict[str, Any]) -> Optional[bool]:
    """
    Example text:
      - "Stop loss at 2x credit received"
      - "Close if loss exceeds 3x the initial credit"
    """
    lowered = text.lower()
    if "stop" not in lowered and "close" not in lowered and "loss" not in lowered:
        return None
    if "credit" not in lowered:
        return None
    mult_match = re.search(r"(\d+(\.\d+)?)\s*x", text, flags=re.IGNORECASE)
    if not mult_match:
        return None
    mult = _safe_float(mult_match.group(1))
    if mult is None:
        return None
    credit = ctx.get("initial_credit_received")
    unrealized = ctx.get("unrealized_pnl")
    if credit is None or unrealized is None:
        return None
    target_loss = -mult * credit
    return unrealized <= target_loss


def _eval_underlying_threshold_condition(text: str, ctx: Dict[str, Any]) -> Optional[bool]:
    """
    Parse simple take-profit / stop-loss style underlying thresholds from narrative text.

    Examples:
      - "Stop out ... below the 20-day low of $63.29"  -> underlying_price < 63.29
      - "Take profit ... reaches the $72.50 Call Wall" -> underlying_price > 72.50

    Rule:
      - if text contains below/under/less than => underlying_price < threshold
      - if text contains above/over/reaches/exceeds => underlying_price > threshold
    """
    underlying = ctx.get("underlying_price")
    if underlying is None:
        return None

    lowered = (text or "").lower()

    direction: Optional[str] = None
    if any(k in lowered for k in ["below", "under", "less than", "undershoot"]):
        direction = "lt"
    elif any(k in lowered for k in ["above", "over", "greater than", "reaches", "exceeds"]):
        direction = "gt"
    else:
        return None

    # Prefer explicit dollar thresholds: "$63.29" beats the earlier "20-day" number.
    dollars = re.findall(r"\$\s*(\d+(\.\d+)?)", text or "")
    if dollars:
        threshold = _safe_float(dollars[0][0])
    else:
        m = re.search(r"(\d+(\.\d+)?)", text or "")
        if not m:
            return None
        threshold = _safe_float(m.group(1))
    if threshold is None:
        return None

    return _compare_numeric(underlying, threshold, direction)

