import json
import re
import logging
from dataclasses import dataclass, field
from typing import Tuple, Optional, List

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('gpt_verdict')

@dataclass
class JSONParsingDiagnostics:
    """Detailed diagnostics for JSON parsing attempts."""
    raw_response: str
    raw_response_length: int
    direct_parse_success: bool
    code_block_parse_success: bool
    balanced_brace_parse_success: bool
    greedy_parse_success: bool
    final_success: bool
    parsing_attempts: int
    extracted_json_keys: list
    missing_required_fields: list
    parsing_errors: list

def _extract_json_from_response(text: str) -> Tuple[dict, JSONParsingDiagnostics]:
    """
    Extract JSON from potentially malformed response text with comprehensive diagnostics.
    Replicated for reproduction.
    """
    diagnostics = JSONParsingDiagnostics(
        raw_response=text[:2000],
        raw_response_length=len(text),
        direct_parse_success=False,
        code_block_parse_success=False,
        balanced_brace_parse_success=False,
        greedy_parse_success=False,
        final_success=False,
        parsing_attempts=0,
        extracted_json_keys=[],
        missing_required_fields=[],
        parsing_errors=[]
    )

    logger.info("JSON Extraction Attempt", extra={
        "response_length": len(text),
        "response_preview": text[:500],
        "truncated": len(text) > 500,
        "non_printable_chars": sum(1 for c in text if not c.isprintable())
    })

    # Check for potential JSON-like structures
    potential_json_starts = [
        text.find('{'),
        text.find('['),
        text.find('{"'),
        text.find("{'")
    ]
    potential_json_starts = [x for x in potential_json_starts if x != -1]

    logger.debug("JSON Parsing Hints", extra={
        "first_potential_json_index": min(potential_json_starts) if potential_json_starts else -1,
        "brackets_count": {
            'curly_open': text.count('{'),
            'curly_close': text.count('}'),
            'square_open': text.count('['),
            'square_close': text.count(']')
        }
    })

    def _clean_json_like(s: str) -> str:
        # Normalize smart quotes to plain quotes
        s = s.replace('"', '"').replace('"', '"').replace(''', "'").replace(''', "'")
        # Remove comments
        s = re.sub(r"//.*?$", "", s, flags=re.MULTILINE)
        s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
        # Replace Python/JS literals
        s = re.sub(r"\bTrue\b", "true", s)
        s = re.sub(r"\bFalse\b", "false", s)
        s = re.sub(r"\bNone\b", "null", s)
        s = re.sub(r"\bNaN\b", "null", s)
        s = re.sub(r"\bInfinity\b", "null", s)
        # Remove trailing commas before } or ]
        s = re.sub(r",\s*([}\]])", r"\1", s)
        return s.strip()

    def _try_parse(s: str, method: str):
        diagnostics.parsing_attempts += 1
        try:
            result = json.loads(s)
            logger.debug(f"JSON parse succeeded with {method}")
            return result
        except json.JSONDecodeError as e:
            diagnostics.parsing_errors.append(f"{method} direct parse: {str(e)}")
            pass

        # Try cleaning and parse again
        try:
            cleaned = _clean_json_like(s)
            result = json.loads(cleaned)
            logger.debug(f"JSON parse succeeded with {method} (after cleaning)")
            return result
        except json.JSONDecodeError as e:
            diagnostics.parsing_errors.append(f"{method} cleaned parse: {str(e)}")
            return None

    def _validate_and_score_result(result: dict) -> int:
        """Score result based on completeness and set diagnostics."""
        if not isinstance(result, dict):
            return -1

        diagnostics.extracted_json_keys = list(result.keys())
        required_fields = ['rationale', 'summary_html', 'final_bias', 'execution_recommendations']
        diagnostics.missing_required_fields = [f for f in required_fields if f not in result]

        # Check for CRITICAL fields that must be non-empty (for Analyst stage)
        critical_fields = {'rationale', 'summary_html'}
        missing_critical = []
        for field in critical_fields:
            field_value = result.get(field)
            # Check if field is missing or empty (empty string, None, etc.)
            if not field_value or (isinstance(field_value, str) and len(field_value.strip()) == 0):
                missing_critical.append(field)
                logger.warning(f"CRITICAL FIELD EMPTY: {field} = {repr(field_value)[:100]}")

        # Score based on presence of key fields
        score = sum(1 for k in required_fields if k in result)

        # Penalty for missing critical analysis fields
        if missing_critical:
            score = score - len(missing_critical)

        logger.debug(f"JSON validation score: {score}/4", extra={
            "extracted_keys": diagnostics.extracted_json_keys,
            "missing_fields": diagnostics.missing_required_fields,
            "missing_critical_fields": missing_critical
        })
        return score

    # 1) Direct parse
    logger.debug("Attempting direct JSON parse")
    res = _try_parse(text.strip(), "direct")
    if isinstance(res, dict):
        score = _validate_and_score_result(res)
        if score >= 3:  # Require at least 3/4 fields (rationale + summary_html + one of final_bias/exec_rec)
            diagnostics.direct_parse_success = True
            diagnostics.final_success = True
            logger.info("Direct JSON parse successful")
            return res, diagnostics

    # 2) Code blocks first (json-marked then generic)
    logger.debug("Attempting code block extraction")
    code_block_patterns = [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```"]
    candidates = []

    for i, pattern in enumerate(code_block_patterns):
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        logger.debug(f"Found {len(matches)} matches for pattern {i}")

        for match_idx, match in enumerate(matches):
            res = _try_parse(match, f"code_block_p{i}_m{match_idx}")
            if isinstance(res, dict):
                candidates.append((res, _validate_and_score_result(res)))

    # Return the best candidate from code blocks
    if candidates:
        candidates.sort(key=lambda x: x[1], reverse=True)  # Sort by score
        best_candidate, best_score = candidates[0]

        if best_score >= 3:  # Require at least 3/4 fields (rationale + summary_html)
            diagnostics.code_block_parse_success = True
            diagnostics.final_success = True
            logger.info(f"Code block parse successful with score {best_score}")
            return best_candidate, diagnostics
        elif best_score >= 2:  # Fallback: return candidate with partial score
            diagnostics.code_block_parse_success = True
            diagnostics.final_success = True
            logger.warning(f"Code block parse with moderate score {best_score} (below strict threshold)")
            return best_candidate, diagnostics

    # 3) Balanced brace scan to extract candidate JSON objects
    def _balanced_object_candidates(s: str):
        in_string = False
        escape = False
        depth = 0
        start_idx = None
        for i, ch in enumerate(s):
            if in_string:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            else:
                if ch == '"':
                    in_string = True
                    continue
                if ch == '{':
                    if depth == 0:
                        start_idx = i
                    depth += 1
                    continue
                if ch == '}':
                    if depth > 0:
                        depth -= 1
                        if depth == 0 and start_idx is not None:
                            yield s[start_idx:i+1]
                            start_idx = None
                    continue
        return

    # Scan candidates from balanced braces
    logger.debug("Attempting balanced brace extraction")
    brace_candidates = []
    brace_count = 0

    for candidate_str in _balanced_object_candidates(text):
        brace_count += 1
        res = _try_parse(candidate_str, f"balanced_brace_{brace_count}")
        if isinstance(res, dict):
            score = _validate_and_score_result(res)
            brace_candidates.append((res, score))

    logger.debug(f"Found {len(brace_candidates)} valid brace candidates from {brace_count} attempts")

    # Pick best from brace candidates
    if brace_candidates:
        brace_candidates.sort(key=lambda x: x[1], reverse=True)
        best_brace_candidate, best_brace_score = brace_candidates[0]

        if best_brace_score >= 3:  # Raised threshold from 2 to 3 to avoid partial JSON
            diagnostics.balanced_brace_parse_success = True
            diagnostics.final_success = True
            logger.info(f"Balanced brace parse successful with score {best_brace_score}")
            return best_brace_candidate, diagnostics
        elif best_brace_score >= 2:
            # Log for debugging but don't accept yet - try other methods
            logger.debug(f"Balanced brace candidate found with score {best_brace_score}, but below strict threshold - trying other extraction methods")
            # Don't return yet - let it try greedy as fallback

    # 4) Fallback: greedy first/last braces (as a last resort)
    logger.debug("Attempting greedy brace extraction as final fallback")
    greedy = re.search(r"\{.*\}", text, re.DOTALL)
    if greedy:
        res = _try_parse(greedy.group(0), "greedy")
        if isinstance(res, dict):
            score = _validate_and_score_result(res)
            if score >= 3:  # Require good score even for greedy extraction
                diagnostics.greedy_parse_success = True
                diagnostics.final_success = True
                logger.info(f"Greedy parse succeeded with score {score}")
                return res, diagnostics
            elif score >= 2:  # Accept partial if all else fails
                logger.warning(f"Accepting greedy parse with score {score} (below strict threshold)")
                diagnostics.greedy_parse_success = True
                diagnostics.final_success = True
                return res, diagnostics

    return None, diagnostics

# Test content provided by user
content = """{
  "final_bias": "Bullish",
  "confidence_level": "Medium",
  "rationale": "The macro context shows a strong supportive backdrop with the SPY in a clear uptrend trading at 684.34, well above its 200-day SMA of 617.13, signifying favorable broad market conditions for risk assets including TSLA. Market sentiment is bullish overall, which underpins a constructive framework for Tesla. TSLA’s technicals suggest a positive setup: the current price is $446.75, well above the 200-day SMA of 341.62, indicating a long-term uptrend. The RSI at 58.4 is neutral-to-mildly bullish, favoring further upward momentum without being overbought. The MACD is bullish, with the MACD line above its signal line, supporting a continuation of the positive momentum. Price has broken above the 50-day SMA (~434.35) recently, which is a strong technical signal often correlating with a sustained rally. Tesla’s recent resistance sits near $467.45 for the 20-day high, with key longer-term resistance at the yearly high near $488.54, both of which are within reach if momentum continues. Volatility structure shows implied volatility (IV) aligned with historical volatility (HV), with an HV rank around 20%, indicating relatively low to moderate vol levels which often favors directional moves without excessive premium inflation. The options skew and parity suggest no obvious mispricing or arbitrage, reinforcing a stable volatility environment. Options positioning highlights a low put/call ratio around 0.56, reflecting call dominance and a bullish options market bias. There is significant unusual activity with large volumes and open interest in OTM calls around strikes $447.5 to $462.5, indicating sustained bullish interest. Additionally, a substantial put wall at $140 strike offers a very distant strong support level, while a call wall at $460 creates a near-term resistance target that the market seems to be focused on. Fundamental data is limited but shows a profit margin around 5.5%, which is positive for a growth name like Tesla, though higher investments in AI and autonomy development may pressure margins near term. Analyst commentary also shows optimism on Tesla’s autonomous vehicle progress and core business strength supporting a target price near $509, adding fundamental validation to the technical and sentiment bullishness. From a risk perspective, Tesla faces margin pressure from elevated investments and external macroeconomic or regulatory uncertainties could derail momentum. The implied move of 2.88% to expiration suggests a relatively contained expected volatility, meaning a breakout beyond key levels would be significant. Overall, the synthesis of a strong macro uptrend, constructive technicals with recent SMA breakouts, supportive sentiment in options flows, and stable volatility environment supports a bullish view on TSLA into December 2025 expiration. The medium confidence rating reflects some fundamental uncertainty and the proximity of resistance levels that must be overcome for a more confident stronger bullish tenor.",
  "summary_html": "<h4>TSLA Market Analysis Summary</h4><ul><li>Macro: Broad market in strong uptrend, supportive environment for growth stocks<span style=\\"background: #e3f2fd; padding: 4px 8px;\\">Bullish Signal</span></li><li>Technical: Price above 200-day SMA at $446.75, RSI neutral at 58.4, MACD bullish, recent breakout above 50-day SMA</li><li>Volatility: IV aligned with HV, HV rank low at ~20%, indicating moderate volatility environment</li><li>Options Sentiment: Low put/call ratio around 0.56, unusual call buying on strikes $447.5-$462.5, strong put wall at $140 support</li><li>Fundamentals: Positive profit margin ~5.5%, ongoing margin pressure from investments, strong analyst target near $509</li></ul>",
  "key_reasoning_points": [
    "Macro uptrend with SPY above 200-day SMA at 684.34",
    "TSLA price above 200-day SMA at 341.62 and recent breakout above 50-day SMA",
    "RSI neutral at 58.4 and MACD bullish indicating upward momentum",
    "Low volatility rank (~20%) with IV in line with HV supporting stable pricing",
    "Options flows show bullish call buying and low put/call ratio (~0.56)"
  ],
  "risk_factors": [
    "Margin pressure from rising investments in AI and autonomy",
    "Potential resistance near $460 call wall could cap near-term gains",
    "Macro or regulatory shocks that could impair growth outlook"
  ],
  "actionable_ideas": [
    "Consider long call spreads targeting $460-$470 strikes to capitalize on momentum",
    "Monitor price action for sustained close above 50-day SMA (~$434) as entry confirmation",
    "Watch for volume and open interest shifts near $460 call wall to gauge breakout strength"
  ]
}"""

print(f"Testing content length: {len(content)}")
parsed_json, diagnostics = _extract_json_from_response(content)
print(f"\nParsing Result: {diagnostics.final_success}")
print(f"Parsing Method: {diagnostics.direct_parse_success=}, {diagnostics.code_block_parse_success=}, {diagnostics.balanced_brace_parse_success=}, {diagnostics.greedy_parse_success=}")
if parsed_json:
    print(f"\nParsed keys: {list(parsed_json.keys())}")
else:
    print(f"\nParsing Errors: {diagnostics.parsing_errors}")
