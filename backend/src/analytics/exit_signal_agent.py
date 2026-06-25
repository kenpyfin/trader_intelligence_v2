"""
Gemini tool-calling agent for evaluating natural-language exit conditions.

Pure agent path: one session evaluates ALL conditions for a strategy.
The model chooses tools, gathers shared market data once, then judges each condition.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.analytics.exit_signal_tools import (
    AGENT_VERSION,
    GEMINI_FUNCTION_DECLARATIONS,
    ExitSignalToolDeps,
    execute_tool,
)
from src.analytics.methodologies.gpt_verdict import _resolve_gemini_model

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-2.5-flash")
BASE_MAX_TOOL_TURNS = int(os.getenv("EXIT_SIGNAL_AGENT_MAX_TURNS", "12"))


SYSTEM_PROMPT = """You are an exit-condition evaluator for options strategies.

You receive a ticker and a numbered list of exit conditions for ONE open strategy.
Evaluate EVERY condition in a single session.

Process:
1. Read all conditions. Plan which market facts you need (may overlap across conditions).
2. Call tools to gather facts. Reuse data across conditions — do not repeat identical tool calls unnecessarily.
3. Judge each condition from tool outputs only. Never invent prices or indicators.
4. Return JSON with an "evaluations" array — one object per input condition, same order and exact condition text.

Each evaluation object:
- text: copy the condition string exactly as given
- status: met | unmet | unknown
- reason: cite numbers from tools; explain your judgment
- tools_used: tool names you relied on for this condition (subset of session tools)

Top-level JSON shape:
{
  "evaluations": [ { "text": "...", "status": "...", "reason": "...", "tools_used": [] }, ... ],
  "tool_trace_summary": "optional one-line session summary"
}

Guidance (use judgment, not keyword rules):
- "Near" / "approaches" a cited $ level: compare spot to that $ level, not only a rolling high.
- Rolling recent high ≠ a specific $ price written in the condition.
- If data is missing for a condition, status is unknown and say what was missing.

You do NOT recommend new trades. You only judge these exit conditions.
"""


def _max_turns_for_conditions(count: int) -> int:
    return max(BASE_MAX_TOOL_TURNS, count * 4)


def _normalize_condition_texts(conditions: List[str]) -> List[str]:
    return [c.strip() for c in (conditions or []) if isinstance(c, str) and c.strip()]


def _extract_function_calls(candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
    calls = []
    content = candidate.get("content") or {}
    for part in content.get("parts") or []:
        if "functionCall" in part:
            fc = part["functionCall"]
            calls.append(
                {
                    "name": fc.get("name"),
                    "args": fc.get("args") or {},
                }
            )
    return calls


def _gemini_generate(
    *,
    model: str,
    contents: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    response_json: bool = False,
    temperature: float = 0.2,
    timeout: int = 180,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None, "GEMINI_API_KEY not set"

    resolved = _resolve_gemini_model(model)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{resolved}:generateContent"

    payload: Dict[str, Any] = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 4096,
        },
    }
    if tools:
        payload["tools"] = [{"functionDeclarations": tools}]
    if response_json:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    try:
        resp = requests.post(url, params={"key": key}, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        logger.error("Gemini exit-signal request failed: %s", exc)
        return None, str(exc)


def _append_model_turn(contents: List[Dict[str, Any]], response: Dict[str, Any]) -> None:
    candidates = response.get("candidates") or []
    if not candidates:
        return
    model_content = candidates[0].get("content")
    if model_content:
        contents.append(model_content)


def _append_tool_responses(
    contents: List[Dict[str, Any]],
    function_calls: List[Dict[str, Any]],
    deps: ExitSignalToolDeps,
    tool_trace: List[Dict[str, Any]],
) -> List[str]:
    tools_used: List[str] = []
    parts = []
    for fc in function_calls:
        name = fc.get("name") or ""
        args = fc.get("args") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        tools_used.append(name)
        result = execute_tool(name, args, deps)
        tool_trace.append({"tool": name, "args": args, "result": result})
        parts.append(
            {
                "functionResponse": {
                    "name": name,
                    "response": result,
                }
            }
        )
    if parts:
        contents.append({"role": "user", "parts": parts})
    return tools_used


def _parse_json_payload(raw: str) -> Optional[Any]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


_MISSING_EVAL_REASON = "Agent did not return an evaluation for this condition."


def _is_missing_evaluation(row: Dict[str, Any]) -> bool:
    reason = (row.get("reason") or "").lower()
    return row.get("status") == "unknown" and "did not return" in reason


def _has_missing_evaluations(parsed: List[Dict[str, Any]], condition_texts: List[str]) -> bool:
    if len(parsed) != len(condition_texts):
        return True
    return any(_is_missing_evaluation(row) for row in parsed)


def _merge_evaluations(
    prior: List[Dict[str, Any]],
    new: List[Dict[str, Any]],
    condition_texts: List[str],
) -> List[Dict[str, Any]]:
    """Keep prior met/unmet rows; fill in newly resolved missing slots."""
    merged: List[Dict[str, Any]] = []
    for i, expected in enumerate(condition_texts):
        old_row = prior[i] if i < len(prior) else None
        new_row = new[i] if i < len(new) else None
        if new_row and not _is_missing_evaluation(new_row):
            merged.append(dict(new_row))
        elif old_row and not _is_missing_evaluation(old_row):
            merged.append(dict(old_row))
        elif new_row:
            merged.append(dict(new_row))
        elif old_row:
            merged.append(dict(old_row))
        else:
            merged.append(_evaluation_row(text=expected, reason=_MISSING_EVAL_REASON))
        merged[-1]["text"] = expected
    return merged


def _match_single_object_to_condition(data: Dict[str, Any], condition_texts: List[str]) -> Optional[str]:
    """Map a legacy single-object agent payload to the best matching condition."""
    obj_text = (data.get("text") or "").strip().lower()
    if obj_text:
        for cond in condition_texts:
            key = cond.strip().lower()
            if key == obj_text or obj_text in key or key in obj_text:
                return cond
    if len(condition_texts) == 1:
        return condition_texts[0]
    return None


def _evaluation_row(
    *,
    text: str,
    status: str = "unknown",
    reason: str = "",
    tools_used: Optional[List[str]] = None,
    tool_trace: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    st = str(status).lower()
    if st not in ("met", "unmet", "unknown"):
        st = "unknown"
    return {
        "text": text,
        "status": st,
        "reason": reason,
        "tools_used": list(tools_used or []),
        "tool_trace": list(tool_trace or []),
        "evaluator": "agent",
        "agent_version": AGENT_VERSION,
    }


def _parse_batch_evaluations(
    raw: str,
    condition_texts: List[str],
    session_tools_used: List[str],
    tool_trace: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Parse agent JSON with evaluations[] and align to input conditions."""
    data = _parse_json_payload(raw)

    rows_by_text: Dict[str, Dict[str, Any]] = {}
    rows_by_index: List[Dict[str, Any]] = []

    if isinstance(data, dict):
        evals = data.get("evaluations")
        if isinstance(evals, list):
            for item in evals:
                if not isinstance(item, dict):
                    continue
                row = _evaluation_row(
                    text=(item.get("text") or "").strip(),
                    status=item.get("status", "unknown"),
                    reason=item.get("reason") or data.get("tool_trace_summary") or "",
                    tools_used=item.get("tools_used") or session_tools_used,
                    tool_trace=tool_trace,
                )
                rows_by_index.append(row)
                key = row["text"].strip().lower()
                if key:
                    rows_by_text[key] = row
        elif "status" in data:
            matched = _match_single_object_to_condition(data, condition_texts)
            if matched:
                rows_by_text[matched.strip().lower()] = _evaluation_row(
                    text=matched,
                    status=data.get("status", "unknown"),
                    reason=data.get("reason") or "",
                    tools_used=data.get("tools_used") or session_tools_used,
                    tool_trace=tool_trace,
                )

    aligned: List[Dict[str, Any]] = []
    used_index_rows: set[int] = set()
    for i, expected in enumerate(condition_texts):
        key = expected.strip().lower()
        row = rows_by_text.get(key)
        if row is not None:
            for j, candidate in enumerate(rows_by_index):
                if candidate is row:
                    used_index_rows.add(j)
                    break
        if row is None:
            for j, candidate in enumerate(rows_by_index):
                if j not in used_index_rows:
                    row = dict(candidate)
                    row["text"] = expected
                    used_index_rows.add(j)
                    break
        if row is None:
            row = _evaluation_row(
                text=expected,
                status="unknown",
                reason=_MISSING_EVAL_REASON,
                tools_used=session_tools_used,
                tool_trace=tool_trace,
            )
        else:
            row = dict(row)
            row["text"] = expected
            row["tool_trace"] = tool_trace
            row["agent_version"] = AGENT_VERSION
        aligned.append(row)

    return aligned


def _parse_condition_eval(
    raw: str,
    condition_text: str,
    tools_used: List[str],
    tool_trace: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Parse single-condition JSON (legacy / thin wrapper)."""
    rows = _parse_batch_evaluations(raw, [condition_text], tools_used, tool_trace)
    return rows[0] if rows else _evaluation_row(
        text=condition_text,
        reason="Agent did not return parseable JSON.",
        tools_used=tools_used,
        tool_trace=tool_trace,
    )


def _build_user_prompt(
    ticker: str,
    condition_texts: List[str],
    portfolio_context: Optional[Dict[str, Any]] = None,
) -> str:
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(condition_texts))
    ctx_block = ""
    if portfolio_context:
        try:
            ctx_block = f"\nPortfolio context:\n{json.dumps(portfolio_context, default=str)}\n"
        except TypeError:
            ctx_block = ""

    return (
        f"Ticker: {ticker}\n"
        f"Exit conditions to evaluate ({len(condition_texts)} total):\n{numbered}\n"
        f"{ctx_block}\n"
        "Call tools as needed for all conditions, then respond with JSON containing "
        '"evaluations" (one entry per condition, same order).'
    )


def _build_completion_prompt(condition_texts: List[str]) -> str:
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(condition_texts))
    return (
        f"Your previous JSON was incomplete. Evaluate ALL {len(condition_texts)} exit conditions below "
        "using tool outputs already gathered in this session.\n"
        f"{numbered}\n\n"
        "Respond with JSON only: an evaluations array with exactly one object per condition above, "
        "same order, exact condition text copied into each text field."
    )


def _request_final_json_answer(
    *,
    model: str,
    contents: List[Dict[str, Any]],
    condition_texts: List[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Structured JSON retry after tool gathering (no further tool calls)."""
    prompt_contents = list(contents)
    prompt_contents.append(
        {
            "role": "user",
            "parts": [{"text": _build_completion_prompt(condition_texts)}],
        }
    )
    response, err = _gemini_generate(
        model=model,
        contents=prompt_contents,
        tools=None,
        response_json=True,
        temperature=0.1,
    )
    if err or not response:
        return None, err
    candidates = response.get("candidates") or []
    if not candidates:
        return None, "Empty Gemini response on JSON retry."
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text_parts = [p.get("text", "") for p in parts if "text" in p]
    return "\n".join(text_parts).strip() or None, None


def _run_exit_agent_loop(
    *,
    ticker: str,
    condition_texts: List[str],
    model: str,
    deps: ExitSignalToolDeps,
    portfolio_context: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[List[Dict[str, Any]]], List[str], List[Dict[str, Any]], Optional[str]]:
    """
    Run Gemini tool loop once for all conditions.
    Returns (parsed_evaluations, tools_used, tool_trace, error).
    """
    contents: List[Dict[str, Any]] = [
        {"role": "user", "parts": [{"text": _build_user_prompt(ticker, condition_texts, portfolio_context)}]},
    ]
    all_tools_used: List[str] = []
    tool_trace: List[Dict[str, Any]] = []
    max_turns = _max_turns_for_conditions(len(condition_texts))
    best_raw: Optional[str] = None
    best_parsed: Optional[List[Dict[str, Any]]] = None

    for _turn in range(max_turns):
        response, err = _gemini_generate(
            model=model,
            contents=contents,
            tools=GEMINI_FUNCTION_DECLARATIONS,
            response_json=False,
            temperature=0.2,
        )
        if err or not response:
            return None, all_tools_used, tool_trace, err

        candidates = response.get("candidates") or []
        if not candidates:
            return None, all_tools_used, tool_trace, "Empty Gemini response."

        candidate = candidates[0]
        finish = (candidate.get("finishReason") or "").upper()
        function_calls = _extract_function_calls(candidate)

        if function_calls:
            _append_model_turn(contents, response)
            used = _append_tool_responses(contents, function_calls, deps, tool_trace)
            all_tools_used.extend(used)
            continue

        parts = (candidate.get("content") or {}).get("parts") or []
        text_parts = [p.get("text", "") for p in parts if "text" in p]
        raw = "\n".join(text_parts).strip()

        if finish in ("STOP", "MAX_TOKENS") or raw:
            parsed = _parse_batch_evaluations(
                raw,
                condition_texts,
                list(dict.fromkeys(all_tools_used)),
                tool_trace,
            )
            if best_parsed:
                parsed = _merge_evaluations(best_parsed, parsed, condition_texts)
            best_parsed = parsed
            best_raw = raw

            if not _has_missing_evaluations(parsed, condition_texts):
                return parsed, list(dict.fromkeys(all_tools_used)), tool_trace, None

            if _turn < max_turns - 1:
                _append_model_turn(contents, response)
                contents.append(
                    {
                        "role": "user",
                        "parts": [{"text": _build_completion_prompt(condition_texts)}],
                    }
                )
                continue

    if best_parsed and _has_missing_evaluations(best_parsed, condition_texts):
        json_raw, json_err = _request_final_json_answer(
            model=model,
            contents=contents,
            condition_texts=condition_texts,
        )
        if json_raw:
            parsed = _parse_batch_evaluations(
                json_raw,
                condition_texts,
                list(dict.fromkeys(all_tools_used)),
                tool_trace,
            )
            merged = _merge_evaluations(best_parsed, parsed, condition_texts)
            if not _has_missing_evaluations(merged, condition_texts):
                return merged, list(dict.fromkeys(all_tools_used)), tool_trace, None
            best_parsed = merged
            best_raw = json_raw

    if best_parsed is not None:
        return best_parsed, list(dict.fromkeys(all_tools_used)), tool_trace, None

    return None, all_tools_used, tool_trace, "Exceeded maximum tool turns without a final answer."


def evaluate_exit_conditions_with_agent(
    *,
    ticker: str,
    conditions: List[str],
    model: str = DEFAULT_GEMINI_MODEL,
    deps: Optional[ExitSignalToolDeps] = None,
    portfolio_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Evaluate all exit conditions in one agent session (shared tool calls)."""
    sym = (ticker or "").strip().upper()
    texts = _normalize_condition_texts(conditions)
    if not sym or not texts:
        return []

    deps = deps or ExitSignalToolDeps()
    parsed, tools_used, tool_trace, err = _run_exit_agent_loop(
        ticker=sym,
        condition_texts=texts,
        model=model,
        deps=deps,
        portfolio_context=portfolio_context,
    )

    if err:
        return [
            _evaluation_row(
                text=t,
                reason=f"Gemini error: {err}",
                tools_used=tools_used,
                tool_trace=tool_trace,
            )
            for t in texts
        ]

    if parsed:
        return parsed

    return _parse_batch_evaluations("", texts, tools_used, tool_trace)


def evaluate_exit_condition_with_agent(
    *,
    ticker: str,
    condition_text: str,
    model: str = DEFAULT_GEMINI_MODEL,
    deps: Optional[ExitSignalToolDeps] = None,
    portfolio_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate one condition (delegates to batch evaluator with a single-item list)."""
    rows = evaluate_exit_conditions_with_agent(
        ticker=ticker,
        conditions=[condition_text],
        model=model,
        deps=deps,
        portfolio_context=portfolio_context,
    )
    text = (condition_text or "").strip()
    if rows:
        return rows[0]
    return _evaluation_row(text=text, reason="No evaluation returned.")


def pending_agent_evaluations(conditions: List[str]) -> List[Dict[str, Any]]:
    """Placeholder while async agent refresh has not completed."""
    return [
        {
            "text": text,
            "status": "unknown",
            "reason": "Awaiting agent evaluation (refresh in progress).",
            "tools_used": [],
            "tool_trace": [],
            "evaluator": "pending",
        }
        for text in _normalize_condition_texts(conditions)
    ]
