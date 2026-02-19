import os
import json
import re
import requests
import logging
import time
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple
import traceback
from dataclasses import dataclass, field
from enum import Enum
import random
import threading
from typing import Callable
from ..quality_config import QualityAssessment, QualityLevel
from ..strike_normalization import default_normalizer
from ..enhanced_greeks_validation import default_enhanced_validator

# Configure structured logging for GPT verdict generation
logger = logging.getLogger('gpt_verdict')
logger.setLevel(logging.DEBUG)

# Create console handler if not exists
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

class FailureCategory(Enum):
    """Categorizes different types of failures for better diagnostics."""
    API_TIMEOUT = "api_timeout"
    API_ERROR = "api_error"
    JSON_PARSE_ERROR = "json_parse_error"
    DATA_VALIDATION_ERROR = "data_validation_error"
    MALFORMED_RESPONSE = "malformed_response"
    EMPTY_RESPONSE = "empty_response"
    NETWORK_ERROR = "network_error"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMIT_ERROR = "rate_limit_error"

@dataclass
class APICallMetrics:
    """Tracks detailed metrics for API calls."""
    stage: str
    model: str
    temperature: float
    timeout: int
    start_time: float
    end_time: Optional[float] = None
    status_code: Optional[int] = None
    response_size: Optional[int] = None
    request_size: Optional[int] = None
    success: bool = False
    failure_category: Optional[FailureCategory] = None
    error_message: Optional[str] = None

    @property
    def duration(self) -> float:
        """Returns duration in seconds."""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

@dataclass
class OptionsDataValidation:
    """Tracks options data quality and validation results with graduated assessment."""
    valid_strikes_count: int
    greeks_count: int
    filtered_greeks_count: int
    top_opportunity_present: bool
    volatility_structure_present: bool
    undervalued_opportunities_count: int
    data_completeness_score: float  # 0.0 to 1.0
    data_quality_score: float  # 0.0 to 1.0 - quality of existing data
    complete_greeks_count: int  # strikes with full greeks for both calls and puts
    invalid_greeks_count: int  # strikes with invalid/NaN greeks values
    warnings: list
    errors: list
    repair_attempts: list  # track what data repairs were attempted
    quality_assessment_result: Optional[Dict] = None  # graduated quality assessment details
    enhanced_greeks_validation: Optional[Dict] = None  # enhanced validation with repairs

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

@dataclass
class RetryConfig:
    """Configuration for retry logic with exponential backoff."""
    max_attempts: int = 3
    base_delay: float = 1.0  # Initial delay in seconds
    max_delay: float = 60.0  # Maximum delay in seconds
    exponential_base: float = 2.0
    jitter: bool = True  # Add randomness to prevent thundering herd
    retryable_categories: set = field(default_factory=lambda: {
        FailureCategory.API_TIMEOUT,
        FailureCategory.NETWORK_ERROR,
        FailureCategory.RATE_LIMIT_ERROR,
        FailureCategory.API_ERROR  # Some API errors might be transient
    })

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number (0-indexed)."""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            # Add ±25% jitter to prevent thundering herd
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0.1, delay)  # Minimum 100ms delay

@dataclass
class TimeoutConfig:
    """Separate timeout configuration for different agent stages."""
    analyst_timeout: int = 180  # 3 minutes for analyst
    trader_timeout: int = 240   # 4 minutes for trader (more complex payload)

    def get_timeout(self, stage: str) -> int:
        """Get appropriate timeout for the stage."""
        if stage.lower() == "trader":
            return self.trader_timeout
        return self.analyst_timeout

@dataclass
class CircuitBreakerState:
    """Tracks circuit breaker state for failure prevention."""
    failure_count: int = 0
    last_failure_time: float = 0.0
    state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    failure_threshold: int = 5
    recovery_timeout: float = 300.0  # 5 minutes
    half_open_success_threshold: int = 2

class CircuitBreaker:
    """Circuit breaker pattern implementation to prevent cascading failures."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 300.0):
        self.state = CircuitBreakerState(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout
        )
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        """Check if execution is allowed based on circuit breaker state."""
        with self._lock:
            now = time.time()

            if self.state.state == "CLOSED":
                return True
            elif self.state.state == "OPEN":
                if now - self.state.last_failure_time >= self.state.recovery_timeout:
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                    self.state.state = "HALF_OPEN"
                    self.state.failure_count = 0
                    return True
                return False
            elif self.state.state == "HALF_OPEN":
                return True

            return False

    def record_success(self):
        """Record successful execution."""
        with self._lock:
            if self.state.state == "HALF_OPEN":
                self.state.failure_count = 0
                if hasattr(self.state, 'success_count'):
                    self.state.success_count += 1
                else:
                    self.state.success_count = 1

                if self.state.success_count >= self.state.half_open_success_threshold:
                    logger.info("Circuit breaker transitioning to CLOSED after successful recovery")
                    self.state.state = "CLOSED"
                    self.state.failure_count = 0
            elif self.state.state == "CLOSED":
                self.state.failure_count = 0

    def record_failure(self):
        """Record failed execution."""
        with self._lock:
            self.state.failure_count += 1
            self.state.last_failure_time = time.time()

            if self.state.state == "CLOSED" and self.state.failure_count >= self.state.failure_threshold:
                logger.warning(f"Circuit breaker OPENING due to {self.state.failure_count} failures")
                self.state.state = "OPEN"
            elif self.state.state == "HALF_OPEN":
                logger.warning("Circuit breaker returning to OPEN from HALF_OPEN due to failure")
                self.state.state = "OPEN"

# Global circuit breakers for each agent type
_circuit_breakers = {
    "Analyst": CircuitBreaker(failure_threshold=5, recovery_timeout=300.0),
    "Trader": CircuitBreaker(failure_threshold=3, recovery_timeout=600.0)  # More sensitive for trader
}

@dataclass
class RetryMetrics:
    """Tracks retry attempts and outcomes."""
    total_attempts: int = 0
    successful_attempt: Optional[int] = None
    final_failure_category: Optional[FailureCategory] = None
    total_retry_time: float = 0.0
    delays_used: list = field(default_factory=list)
    circuit_breaker_triggered: bool = False

def _sanitize_and_repair_options_data(options_data: Dict[str, Any]) -> tuple[Dict[str, Any], list[str]]:
    """Attempts to repair common data quality issues in options data."""
    import math

    repair_attempts = []
    cleaned_data = options_data.copy()

    # Ensure basic structure exists
    if "valid_strikes" not in cleaned_data:
        cleaned_data["valid_strikes"] = []
        repair_attempts.append("Added missing valid_strikes field")

    if "greeks_by_strike" not in cleaned_data:
        cleaned_data["greeks_by_strike"] = {}
        repair_attempts.append("Added missing greeks_by_strike field")

    # Clean and validate strikes
    valid_strikes = cleaned_data.get("valid_strikes", [])
    cleaned_strikes = []

    for strike in valid_strikes:
        try:
            float_strike = float(strike)
            if not (math.isnan(float_strike) or math.isinf(float_strike)):
                cleaned_strikes.append(float_strike)
            else:
                repair_attempts.append(f"Removed invalid strike: {strike}")
        except (ValueError, TypeError):
            repair_attempts.append(f"Removed non-numeric strike: {strike}")

    cleaned_data["valid_strikes"] = cleaned_strikes

    # Clean greeks data
    greeks_by_strike = cleaned_data.get("greeks_by_strike", {})
    cleaned_greeks = {}

    for strike_key, strike_data in greeks_by_strike.items():
        # Validate strike key
        try:
            float_key = float(strike_key)
            if math.isnan(float_key) or math.isinf(float_key):
                repair_attempts.append(f"Removed strike with invalid key: {strike_key}")
                continue
        except (ValueError, TypeError):
            repair_attempts.append(f"Removed strike with non-numeric key: {strike_key}")
            continue

        # Validate strike data structure
        if not isinstance(strike_data, dict):
            repair_attempts.append(f"Removed strike {strike_key} with non-dict data")
            continue

        cleaned_strike_data = {}

        # Clean option data (calls and puts)
        for option_type in ['call', 'put']:
            if option_type in strike_data and isinstance(strike_data[option_type], dict):
                option_data = strike_data[option_type]
                cleaned_option_data = {}

                # Clean greeks values
                expected_greeks = ['delta', 'gamma', 'theta', 'vega', 'rho', 'market_price', 'model_price']

                for key, value in option_data.items():
                    try:
                        if key in expected_greeks and value is not None:
                            float_val = float(value)
                            if not (math.isnan(float_val) or math.isinf(float_val)):
                                cleaned_option_data[key] = float_val
                            else:
                                repair_attempts.append(f"Removed invalid {key} for {strike_key} {option_type}: {value}")
                        else:
                            # Keep non-numeric fields as-is
                            cleaned_option_data[key] = value
                    except (ValueError, TypeError):
                        repair_attempts.append(f"Removed non-numeric {key} for {strike_key} {option_type}: {value}")

                if cleaned_option_data:  # Only add if there's valid data
                    cleaned_strike_data[option_type] = cleaned_option_data

        if cleaned_strike_data:  # Only add if there's valid option data
            cleaned_greeks[strike_key] = cleaned_strike_data

    cleaned_data["greeks_by_strike"] = cleaned_greeks

    # Ensure numeric fields have reasonable defaults
    if "undervalued_opportunities" not in cleaned_data or not isinstance(cleaned_data["undervalued_opportunities"], (int, float)):
        cleaned_data["undervalued_opportunities"] = 0
        repair_attempts.append("Set default undervalued_opportunities to 0")

    return cleaned_data, repair_attempts

def _validate_options_data(options_data: Dict[str, Any]) -> OptionsDataValidation:
    """Validates options data completeness and quality with enhanced checks."""
    import math

    warnings = []
    errors = []
    repair_attempts = []

    # Check basic structure
    valid_strikes = options_data.get("valid_strikes", [])
    greeks_by_strike = options_data.get("greeks_by_strike", {})
    top_opportunity = options_data.get("top_opportunity")
    volatility_structure = options_data.get("volatility_structure", {})
    undervalued_count = options_data.get("undervalued_opportunities", 0)

    # Validate valid_strikes
    if not valid_strikes:
        errors.append("No valid strikes available")
    elif len(valid_strikes) < 3:
        warnings.append(f"Limited strikes available: {len(valid_strikes)}")

    # Validate greeks data existence
    if not greeks_by_strike:
        errors.append("No greeks data available")
        return OptionsDataValidation(
            valid_strikes_count=len(valid_strikes),
            greeks_count=0,
            filtered_greeks_count=0,
            top_opportunity_present=bool(top_opportunity),
            volatility_structure_present=bool(volatility_structure),
            undervalued_opportunities_count=undervalued_count,
            data_completeness_score=0.0,
            data_quality_score=0.0,
            complete_greeks_count=0,
            invalid_greeks_count=0,
            warnings=warnings,
            errors=errors,
            repair_attempts=repair_attempts
        )

    # Deep validation of greeks structure
    complete_greeks_count = 0
    invalid_greeks_count = 0
    expected_greeks = ['delta', 'gamma', 'theta', 'vega', 'rho']

    # Check each strike's greeks data quality
    for strike_key, strike_data in greeks_by_strike.items():
        if not isinstance(strike_data, dict):
            invalid_greeks_count += 1
            warnings.append(f"Strike {strike_key} has non-dict greeks data")
            continue

        # Check for call and put data
        has_call = 'call' in strike_data and isinstance(strike_data['call'], dict)
        has_put = 'put' in strike_data and isinstance(strike_data['put'], dict)

        if not has_call and not has_put:
            invalid_greeks_count += 1
            warnings.append(f"Strike {strike_key} missing both call and put data")
            continue

        # Validate greeks values for available option types
        complete_option_count = 0
        missing_fields_this_strike = []
        invalid_values_this_strike = []

        for option_type in ['call', 'put']:
            if option_type not in strike_data or not isinstance(strike_data[option_type], dict):
                missing_fields_this_strike.append(f"{option_type}_data")
                continue

            option_data = strike_data[option_type]
            option_complete = True

            # Check for required greeks
            for greek in expected_greeks:
                field_name = f"{option_type}_{greek}"
                if greek not in option_data:
                    option_complete = False
                    missing_fields_this_strike.append(field_name)
                    continue

                value = option_data[greek]
                # Validate numerical values
                if value is None:
                    option_complete = False
                    missing_fields_this_strike.append(field_name)
                    continue

                try:
                    float_val = float(value)
                    if math.isnan(float_val) or math.isinf(float_val):
                        option_complete = False
                        invalid_values_this_strike.append(f"{field_name}={value}")
                        warnings.append(f"Strike {strike_key} {option_type} has invalid {greek}: {value}")
                        continue

                    # Range checks for specific greeks
                    if greek == 'delta':
                        if option_type == 'call' and not (0 <= float_val <= 1):
                            invalid_values_this_strike.append(f"{field_name}={float_val}_out_of_range")
                            warnings.append(f"Strike {strike_key} call delta out of range: {float_val}")
                        elif option_type == 'put' and not (-1 <= float_val <= 0):
                            invalid_values_this_strike.append(f"{field_name}={float_val}_out_of_range")
                            warnings.append(f"Strike {strike_key} put delta out of range: {float_val}")
                    elif greek == 'gamma' and float_val < 0:
                        invalid_values_this_strike.append(f"{field_name}={float_val}_negative")
                        warnings.append(f"Strike {strike_key} {option_type} negative gamma: {float_val}")

                except (ValueError, TypeError):
                    option_complete = False
                    invalid_values_this_strike.append(f"{field_name}={value}_not_numeric")
                    warnings.append(f"Strike {strike_key} {option_type} {greek} not numeric: {value}")

            if option_complete:
                complete_option_count += 1

        # Log detailed field-level issues for debugging (first 3 strikes for brevity)
        if len(list(greeks_by_strike.keys())) <= 3 or any(issue for issue in [missing_fields_this_strike, invalid_values_this_strike]):
            if missing_fields_this_strike or invalid_values_this_strike:
                print(f"FIELD_DEBUG: Strike {strike_key} issues:")
                if missing_fields_this_strike:
                    print(f"  Missing fields: {missing_fields_this_strike}")
                if invalid_values_this_strike:
                    print(f"  Invalid values: {invalid_values_this_strike}")

        # Strike is complete if it has at least one complete option type
        if complete_option_count > 0:
            complete_greeks_count += 1
        else:
            invalid_greeks_count += 1

    # ROBUST STRIKE KEY NORMALIZATION AND ANALYSIS
    strike_analysis = default_normalizer.analyze_strike_mismatch(
        valid_strikes, greeks_by_strike, "valid_strikes", "greeks_by_strike"
    )

    # Log detailed analysis
    default_normalizer.log_strike_analysis(strike_analysis)

    # Extract normalized metrics
    strike_overlap = strike_analysis["summary"]["overlapping_strikes"]
    total_valid_strikes = strike_analysis["summary"]["total_strikes_set1"]
    overlap_ratio = strike_analysis["summary"]["overlap_ratio"]

    # Add warnings/errors based on overlap
    if strike_overlap == 0:
        errors.append("No overlap between valid strikes and available greeks")
        print("🚨 ZERO OVERLAP DETECTED - This causes 0.33 quality score!")
    elif overlap_ratio < 0.5:
        warnings.append(f"Low strike overlap: {strike_overlap}/{total_valid_strikes} ({overlap_ratio:.1%})")
    elif overlap_ratio < 0.8:
        warnings.append(f"Moderate strike overlap: {strike_overlap}/{total_valid_strikes} ({overlap_ratio:.1%})")

    # Calculate completeness score (presence of data)
    completeness_factors = [
        1.0 if valid_strikes else 0.0,
        1.0 if greeks_by_strike else 0.0,
        1.0 if top_opportunity else 0.5,
        1.0 if volatility_structure else 0.5,
        min(1.0, undervalued_count / 5.0) if undervalued_count > 0 else 0.0
    ]
    completeness_score = sum(completeness_factors) / len(completeness_factors)

    # GRADUATED QUALITY ASSESSMENT SYSTEM
    if len(greeks_by_strike) > 0:
        # Individual quality factors
        completeness_factor = complete_greeks_count / len(greeks_by_strike)
        validity_factor = 1.0 - (invalid_greeks_count / len(greeks_by_strike))
        # Use the robust overlap ratio from strike analysis
        overlap_factor = overlap_ratio

        # Determine asset type for appropriate thresholds
        ticker_hint = "SPY" if len(valid_strikes) > 50 else "UNKNOWN"
        asset_type = QualityAssessment.determine_asset_type(ticker_hint, len(valid_strikes))
        quality_assessor = QualityAssessment(asset_type)

        # Get graduated quality assessment
        overall_level, can_proceed, assessment_details = quality_assessor.assess_overall_quality(
            completeness_score=completeness_score,
            quality_score=(completeness_factor + validity_factor + overlap_factor) / 3,
            overlap_score=overlap_factor,
            complete_strikes=complete_greeks_count,
            total_strikes=len(valid_strikes)
        )

        # Use the combined score from assessment
        quality_score = assessment_details["combined_score"]

        # Enhanced logging with graduated levels
        print(f"GRADUATED_QUALITY_DEBUG: Comprehensive Quality Assessment:")
        print(f"  Asset Type: {asset_type}")
        print(f"  Overall Level: {overall_level.value.upper()}")
        print(f"  Can Proceed: {can_proceed}")
        print(f"  Combined Score: {quality_score:.4f}")
        print(f"  Component Factors:")
        print(f"    Completeness: {completeness_factor:.4f} ({assessment_details['component_levels']['completeness']})")
        print(f"    Validity: {validity_factor:.4f} ({assessment_details['component_levels']['quality']})")
        print(f"    Overlap: {overlap_factor:.4f} ({assessment_details['component_levels']['overlap']})")
        print(f"  Thresholds: Pass={assessment_details['thresholds_used']['pass_threshold']:.2f}, Fallback={assessment_details['thresholds_used']['fallback_threshold']:.2f}")

        # Store assessment for later use
        quality_assessment_result = assessment_details
    else:
        quality_score = 0.0
        can_proceed = False
        overall_level = QualityLevel.FAILED
        quality_assessment_result = {"overall_level": "failed", "can_proceed": False}
        print(f"GRADUATED_QUALITY_DEBUG: No greeks data - Quality Level = FAILED")

    # ENHANCED GREEKS VALIDATION WITH INTELLIGENT REPAIR
    enhanced_validation_result = None
    if len(greeks_by_strike) > 0:
        print(f"ENHANCED_GREEKS_DEBUG: Running enhanced Greeks validation...")

        # Estimate parameters for enhanced validation
        spot_price = 400.0  # Default for SPY-like assets
        if len(valid_strikes) > 0:
            # Estimate spot price from ATM strike
            strikes_list = []
            for strike_key in valid_strikes:
                try:
                    strikes_list.append(float(strike_key))
                except:
                    continue
            if strikes_list:
                spot_price = sum(strikes_list) / len(strikes_list)  # Rough ATM estimate

        # Run enhanced validation
        enhanced_result = default_enhanced_validator.validate_and_enhance_greeks_data(
            greeks_by_strike=greeks_by_strike,
            spot_price=spot_price,
            risk_free_rate=0.05,
            time_to_expiry=0.25,  # Rough estimate
            implied_vol=0.20  # Default vol estimate
        )

        # Create validation summary
        enhanced_validation_result = default_enhanced_validator.create_validation_summary(enhanced_result)

        # Log enhanced validation results
        print(f"ENHANCED_GREEKS_DEBUG: Enhanced Validation Results:")
        print(f"  Original Quality: {enhanced_result.original_quality_score:.3f}")
        print(f"  Enhanced Quality: {enhanced_result.enhanced_quality_score:.3f}")
        print(f"  Confidence Score: {enhanced_result.confidence_score:.3f}")
        print(f"  Strikes by Category:")
        print(f"    Excellent: {len(enhanced_result.excellent_strikes)}")
        print(f"    Good: {len(enhanced_result.good_strikes)}")
        print(f"    Acceptable: {len(enhanced_result.acceptable_strikes)}")
        print(f"    Poor: {len(enhanced_result.poor_strikes)}")
        print(f"  Repairs: {enhanced_result.repaired_strikes_count} strikes repaired")
        print(f"  Recommendation: {enhanced_validation_result['recommendation']}")

        # Update quality scores if enhancement significantly improved them
        if (enhanced_result.enhanced_quality_score > quality_score * 1.2 and
            enhanced_result.confidence_score > 0.5):
            print(f"ENHANCED_GREEKS_DEBUG: Using enhanced quality score due to significant improvement")
            quality_score = enhanced_result.enhanced_quality_score
            complete_greeks_count = len(enhanced_result.excellent_strikes) + len(enhanced_result.good_strikes)

    return OptionsDataValidation(
        valid_strikes_count=len(valid_strikes),
        greeks_count=len(greeks_by_strike),
        filtered_greeks_count=len(greeks_by_strike),
        top_opportunity_present=bool(top_opportunity),
        volatility_structure_present=bool(volatility_structure),
        undervalued_opportunities_count=undervalued_count,
        data_completeness_score=completeness_score,
        data_quality_score=quality_score,
        complete_greeks_count=complete_greeks_count,
        invalid_greeks_count=invalid_greeks_count,
        warnings=warnings,
        errors=errors,
        repair_attempts=repair_attempts,
        quality_assessment_result=quality_assessment_result if len(greeks_by_strike) > 0 else None,
        enhanced_greeks_validation=enhanced_validation_result
    )

def _sanitize_for_json(obj: Any, max_list_len: int = 200) -> Any:
    """
    Recursively convert objects to JSON-safe types.
    - Truncates long lists to avoid overlong prompts.
    - Converts pandas/numpy types where possible.
    """
    try:
        import numpy as np  # local import to avoid hard dependency if not used
        import pandas as pd
    except Exception:
        np = None
        pd = None

    # Primitive types
    if obj is None or isinstance(obj, (str, int, float, bool)):
        # Replace NaN/Inf with None
        try:
            if isinstance(obj, float):
                if (obj != obj) or obj in (float("inf"), float("-inf")):
                    return None
        except Exception:
            pass
        return obj

    # Date and datetime
    if isinstance(obj, (date,)):
        return obj.isoformat()

    # Numpy types
    if np is not None:
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()

    # Pandas DataFrame / Series
    if 'pandas' in str(type(obj)).lower():
        try:
            import pandas as pd  # type: ignore
            if isinstance(obj, pd.DataFrame):
                # limit rows/cols to keep prompt manageable
                df = obj.copy()
                if len(df) > max_list_len:
                    df = df.head(max_list_len)
                return df.to_dict(orient="records")
            if isinstance(obj, pd.Series):
                return obj.to_dict()
        except Exception:
            return str(obj)

    # Dict
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v, max_list_len=max_list_len) for k, v in obj.items()}

    # List/Tuple/Set
    if isinstance(obj, (list, tuple, set)):
        seq = list(obj)
        if len(seq) > max_list_len:
            seq = seq[:max_list_len]
        return [_sanitize_for_json(x, max_list_len=max_list_len) for x in seq]

    # Fallback
    return str(obj)


def _build_analyst_messages(ticker: str, expiration_date: str, analysis_payload: Dict[str, Any], use_web_search: bool = False) -> Dict[str, Any]:
    """
    Stage 1: The Analyst.
    Focuses on synthesizing data into a market thesis (Bias, Rationale, Risks).
    """
    system = (
        "You are a Senior Quantitative Analyst. Your goal is to synthesize market data into a clear, professional trading thesis. "
        "You do NOT execute trades; you provide the directional bias and risk assessment for the execution trader. "
        "\n\n"
        "DATA SOURCES TO ANALYZE:\n"
        "1. MACRO CONTEXT: Check `macro_context` (SPY Trend, VIX Regime). Is the broad market supportive?\n"
        "2. FUNDAMENTALS: Check `stock_fundamentals` (Valuation, Growth). Is this a quality asset?\n"
        "3. TECHNICALS: Check `technical_analysis` (Trend, RSI, Support/Resistance).\n"
        "4. VOLATILITY: Check `volatility_structure` (HV Rank, IV vs HV). Is vol cheap or expensive?\n"
        "5. SENTIMENT: Check `options_positioning` (Put/Call Parity, Flows).\n"
        "\n\n"
        "OUTPUT REQUIREMENTS - CRITICAL:\n"
        "- Return ONLY valid JSON. Do NOT include markdown, code blocks, or explanatory text.\n"
        "- **YOU MUST INCLUDE ALL REQUIRED FIELDS** (missing any field will cause system failure):\n"
        "  1. final_bias (REQUIRED: must be \"Bullish\", \"Bearish\", or \"Neutral\")\n"
        "  2. confidence_level (REQUIRED: must be \"High\", \"Medium\", or \"Low\")\n"
        "  3. rationale (REQUIRED: CANNOT BE EMPTY - must be 15-20 sentences of detailed analysis)\n"
        "  4. summary_html (REQUIRED: CANNOT BE EMPTY - must be valid HTML with <h4>, <ul>, <li>)\n"
        "  5. key_reasoning_points (REQUIRED: must be a non-empty list of 3-5 key drivers)\n"
        "  6. risk_factors (REQUIRED: must be a non-empty list of 2-3 primary risks)\n"
        "  7. actionable_ideas (REQUIRED: must be a non-empty list of 1-3 actionable trading ideas)\n"
        "\n"
        "FIELD SPECIFICATIONS:\n"
        "- `final_bias`: Your directional thesis. Choose ONE: \"Bullish\", \"Bearish\", or \"Neutral\".\n"
        "- `confidence_level`: Your confidence in this thesis. Choose ONE: \"High\", \"Medium\", or \"Low\".\n"
        "- `rationale`: A COMPREHENSIVE 15-20 sentence professional analysis that:\n"
        "  * Cites specific data points from the analysis (e.g., 'VIX at 12 signals complacency', 'HV Rank at 85% shows elevated vol')\n"
        "  * Explains WHY you chose this bias\n"
        "  * Discusses key support/resistance levels, trend context, and volatility implications\n"
        "  * MUST NOT be empty or generic - this is the core of your analysis\n"
        "- `summary_html`: Valid HTML (no markdown) with:\n"
        "  * An <h4> title (e.g., '<h4>Market Analysis Summary</h4>')\n"
        "  * A <ul> list with <li> items for key findings\n"
        "  * Optional inline badges: '<span style=\"background: #e3f2fd; padding: 4px 8px;\">Bullish Signal</span>'\n"
        "  * MUST NOT be empty or placeholder text\n"
        "- `key_reasoning_points`: Array of 3-5 strings. Example: [\"VIX near 52-week lows\", \"Technical support holding\", \"IV skew bullish\"]\n"
        "- `risk_factors`: Array of 2-3 strings listing primary risks. Example: [\"Earnings surprise risk\", \"Macro economic data\"]\n"
        "- `actionable_ideas`: Array of 1-3 strings with specific trade ideas. Example: [\"Consider selling OTM puts at 160 support\", \"Bull call spread targeting 180\"]\n"
        "\n"
        "COMPLETE Example JSON Output (copy this structure exactly):\n"
        "{\n"
        "  \"final_bias\": \"Bullish\",\n"
        "  \"confidence_level\": \"High\",\n"
        "  \"rationale\": \"[15-20 sentences of detailed analysis citing specific data points from the provided analysis]\",\n"
        "  \"summary_html\": \"<h4>Market Analysis</h4><ul><li>Technical: [finding]</li><li>Volatility: [finding]</li><li>Sentiment: [finding]</li></ul>\",\n"
        "  \"key_reasoning_points\": [\"Driver 1 with specific data\", \"Driver 2 with specific data\", \"Driver 3 with specific data\"],\n"
        "  \"risk_factors\": [\"Risk 1 description\", \"Risk 2 description\"],\n"
        "  \"actionable_ideas\": [\"Specific trade idea 1\", \"Specific trade idea 2\"]\n"
        "}\n"
        "\n"
        "CRITICAL REMINDERS:\n"
        "✓ ALL fields must be present and non-empty\n"
        "✓ rationale MUST be 15-20 sentences (not 1-2 sentences)\n"
        "✓ summary_html MUST be valid HTML (not markdown or plain text)\n"
        "✓ Lists must contain actual values (not empty arrays)\n"
        "✓ Return ONLY the JSON object - nothing else"
    )

    if use_web_search:
        system += " You MUST use web search to find recent catalysts/earnings."

    user_content = f"Analyze {ticker} for expiration {expiration_date}.\n\n"
    
    # Add sections
    sections = ["macro_context", "stock_fundamentals", "technical_analysis", "volatility_structure", "parity_analysis", "volume_oi_analysis", "synthesis_data"]
    for sec in sections:
        if sec in analysis_payload and analysis_payload[sec]:
            user_content += f"<{sec}>\n{json.dumps(analysis_payload[sec])}\n</{sec}>\n"

    return [{"role": "system", "content": system}, {"role": "user", "content": user_content}]


def _build_trader_messages(ticker: str, expiration_date: str, analyst_verdict: Dict[str, Any], options_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stage 2: The Trader.
    Focuses on execution strategy based on the Analyst's bias.
    """
    system = (
        "You are a Senior Options Execution Trader. Your goal is to construct the optimal trading strategy based on the Analyst's thesis. "
        "You must select specific strikes and define entry/exit rules. "
        "\n\n"
        "EXECUTION RULES:\n"
        "1. ALIGNMENT: Your strategy MUST align with the Analyst's `final_bias`.\n"
        "2. VOLATILITY AWARENESS: Use `volatility_structure` (IV vs HV, HV Rank). High Vol -> Sell Premium (Credit Spreads). Low Vol -> Buy Premium (Debit Spreads/Long calls).\n"
        "3. STRIKE SELECTION: Choose strikes ONLY from `valid_strikes`. Use Delta/Gamma to justify.\n"
        "4. LIQUIDITY: Avoid strikes with low Volume/OI.\n"
        "\n\n"
        "OUTPUT REQUIREMENTS:\n"
        "- Return valid JSON ONLY.\n"
        "- `execution_recommendations`: The full strategy object with primary_strategy, position_sizing, entry_conditions, exit_conditions.\n"
        "- `primary_strategy` must include: type, description, confidence, time_horizon, legs (array of leg objects).\n"
        "- Each leg must include: action (Buy/Sell), strike (number), right (Call/Put), quantity (number).\n"
        "\n"
        "Example JSON Output:\n"
        "{\n"
        "  \"execution_recommendations\": {\n"
        "    \"primary_strategy\": {\n"
        "      \"type\": \"Bull Call Spread\",\n"
        "      \"description\": \"Debit spread targeting moderate upside with limited risk\",\n"
        "      \"confidence\": \"High\",\n"
        "      \"time_horizon\": \"2-4 weeks\",\n"
        "      \"legs\": [\n"
        "        {\"action\": \"Buy\", \"strike\": 270, \"right\": \"Call\", \"quantity\": 1},\n"
        "        {\"action\": \"Sell\", \"strike\": 275, \"right\": \"Call\", \"quantity\": 1}\n"
        "      ]\n"
        "    },\n"
        "    \"alternative_strategies\": [],\n"
        "    \"position_sizing\": {\"suggested_allocation\": \"5% portfolio\", \"risk_level\": \"Moderate\", \"justification\": \"Defined risk exposure\"},\n"
        "    \"entry_conditions\": [\"Confirm bullish momentum continues\", \"Wait for slight pullback to entry\"],\n"
        "    \"exit_conditions\": [\"Target 50% max profit\", \"Stop if underlying breaks support\"],\n"
        "    \"stop_loss_guidance\": \"Close position if loss exceeds 20% of debit paid\",\n"
        "    \"profit_target_guidance\": \"Consider closing at 50% of max potential profit\"\n"
        "  }\n"
        "}"
    )

    user_content = f"Construct a strategy for {ticker} (Exp: {expiration_date}).\n\n"
    user_content += f"<analyst_verdict>\n{json.dumps(analyst_verdict)}\n</analyst_verdict>\n"

    # Smartly truncate options data if too large to prevent token overflow/truncation
    max_strikes = 40
    data_to_send = options_data.copy()
    
    if len(data_to_send.get("valid_strikes", [])) > max_strikes:
        valid_strikes = sorted([float(x) for x in data_to_send["valid_strikes"]])
        mid_idx = len(valid_strikes) // 2
        start_idx = max(0, mid_idx - (max_strikes // 2))
        end_idx = start_idx + max_strikes
        
        subset_strikes = valid_strikes[start_idx:end_idx]
        data_to_send["valid_strikes"] = subset_strikes
        
        # Filter greeks to match subset
        if "greeks_by_strike" in data_to_send:
            full_greeks = data_to_send["greeks_by_strike"]
            subset_greeks = {}
            for s in subset_strikes:
                s_str = str(s)
                # Try exact string match or float match
                if s_str in full_greeks:
                    subset_greeks[s_str] = full_greeks[s_str]
                else:
                    # Fallback: look for matching float key
                    for k, v in full_greeks.items():
                        try:
                            if abs(float(k) - s) < 0.001:
                                subset_greeks[k] = v
                                break
                        except:
                            continue
            data_to_send["greeks_by_strike"] = subset_greeks

    user_content += f"<options_chain_data>\n{json.dumps(data_to_send)}\n</options_chain_data>\n"

    return [{"role": "system", "content": system}, {"role": "user", "content": user_content}]


def _openai_chat_completion_with_retry(
    messages,
    model: str = "gpt-5",
    temperature: float = 0.2,
    stage: str = "unknown",
    retry_config: Optional[RetryConfig] = None,
    timeout_config: Optional[TimeoutConfig] = None
) -> Tuple[Dict[str, Any], APICallMetrics, RetryMetrics]:
    """
    Enhanced API call with retry logic, circuit breaker, and separate timeouts.

    Returns:
        Tuple of (response_dict, api_metrics, retry_metrics)
    """
    if retry_config is None:
        retry_config = RetryConfig()
    if timeout_config is None:
        timeout_config = TimeoutConfig()

    # Initialize retry metrics
    retry_metrics = RetryMetrics()
    circuit_breaker = _circuit_breakers.get(stage, _circuit_breakers["Analyst"])

    # Check circuit breaker state
    if not circuit_breaker.can_execute():
        retry_metrics.circuit_breaker_triggered = True
        logger.error(f"Circuit breaker OPEN for {stage} - blocking execution", extra={
            "stage": stage,
            "circuit_state": circuit_breaker.state.state,
            "failure_count": circuit_breaker.state.failure_count
        })

        # Create failure metrics for circuit breaker
        dummy_metrics = APICallMetrics(
            stage=stage,
            model=model,
            temperature=temperature,
            timeout=timeout_config.get_timeout(stage),
            start_time=time.time(),
            end_time=time.time(),
            failure_category=FailureCategory.API_ERROR,
            error_message="Circuit breaker OPEN - too many recent failures"
        )
        return None, dummy_metrics, retry_metrics

    retry_start_time = time.time()

    for attempt in range(retry_config.max_attempts):
        retry_metrics.total_attempts += 1

        logger.info(f"Attempt {attempt + 1}/{retry_config.max_attempts} for {stage}", extra={
            "attempt": attempt + 1,
            "max_attempts": retry_config.max_attempts,
            "stage": stage
        })

        try:
            # Get appropriate timeout for this stage
            timeout = timeout_config.get_timeout(stage)

            # Make the API call
            result, api_metrics = _openai_chat_completion(
                messages, model, temperature, timeout, stage
            )

            if result is not None:
                # Success!
                retry_metrics.successful_attempt = attempt + 1
                retry_metrics.total_retry_time = time.time() - retry_start_time
                circuit_breaker.record_success()

                logger.info(f"{stage} succeeded on attempt {attempt + 1}", extra={
                    "attempt": attempt + 1,
                    "total_retry_time": retry_metrics.total_retry_time,
                    "api_duration": api_metrics.duration
                })

                return result, api_metrics, retry_metrics

            # Check if this failure is retryable
            if api_metrics.failure_category not in retry_config.retryable_categories:
                logger.info(f"Non-retryable failure for {stage}: {api_metrics.failure_category.value}")
                retry_metrics.final_failure_category = api_metrics.failure_category
                circuit_breaker.record_failure()
                retry_metrics.total_retry_time = time.time() - retry_start_time
                return None, api_metrics, retry_metrics

            # Record failure for circuit breaker
            circuit_breaker.record_failure()

            # If not the last attempt, apply exponential backoff
            if attempt < retry_config.max_attempts - 1:
                delay = retry_config.calculate_delay(attempt)
                retry_metrics.delays_used.append(delay)

                logger.warning(f"{stage} attempt {attempt + 1} failed, retrying in {delay:.2f}s", extra={
                    "attempt": attempt + 1,
                    "failure_category": api_metrics.failure_category.value,
                    "error_message": api_metrics.error_message,
                    "retry_delay": delay
                })

                time.sleep(delay)
            else:
                logger.error(f"{stage} failed after {retry_config.max_attempts} attempts", extra={
                    "final_failure_category": api_metrics.failure_category.value,
                    "final_error_message": api_metrics.error_message
                })

                retry_metrics.final_failure_category = api_metrics.failure_category

        except Exception as e:
            logger.error(f"Unexpected error in retry loop for {stage}", extra={
                "attempt": attempt + 1,
                "error": str(e),
                "traceback": traceback.format_exc()
            })

            # Create failure metrics for unexpected error
            failure_metrics = APICallMetrics(
                stage=stage,
                model=model,
                temperature=temperature,
                timeout=timeout_config.get_timeout(stage),
                start_time=time.time(),
                end_time=time.time(),
                failure_category=FailureCategory.API_ERROR,
                error_message=f"Unexpected error: {str(e)}"
            )

            circuit_breaker.record_failure()
            retry_metrics.final_failure_category = FailureCategory.API_ERROR
            retry_metrics.total_retry_time = time.time() - retry_start_time
            return None, failure_metrics, retry_metrics

    # All retries exhausted
    retry_metrics.total_retry_time = time.time() - retry_start_time
    return None, api_metrics, retry_metrics

def _extract_choice_content(ch: dict) -> str:
    try:
        msg = ch.get("message", {}) if isinstance(ch, dict) else {}
        content_val = msg.get("content")
        # Some providers (or the Responses API) may return a list of blocks
        if isinstance(content_val, list):
            parts = []
            for item in content_val:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text") or "")
                elif isinstance(item, str):
                    parts.append(item)
            content = "\n".join([p for p in parts if p]).strip()
        else:
            content = (content_val or "").strip()
        
        # Function/tool-call fallbacks
        if not content:
            # tool_calls (OpenAI tool calling)
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                try:
                    fn = tool_calls[0].get("function", {})
                    args = fn.get("arguments")
                    if isinstance(args, (dict, list)):
                        content = json.dumps(args)
                    elif isinstance(args, str):
                        content = args
                except Exception:
                    pass
            # legacy function_call
            if not content and isinstance(msg.get("function_call"), dict):
                args = msg["function_call"].get("arguments")
                if isinstance(args, (dict, list)):
                    content = json.dumps(args)
                elif isinstance(args, str):
                    content = args
        return content
    except Exception as e:
        print(f"WARNING: Error extracting content from choice: {e}")
        return ""


def _openai_chat_completion(messages, model: str = "gpt-5", temperature: float = 0.2, timeout: int = None, stage: str = "unknown") -> Tuple[Dict[str, Any], APICallMetrics]:
    """
    Enhanced OpenAI-compatible completion with comprehensive error handling and diagnostics.
    Uses chat/completions for chat models, completions for non-chat models.
    Honors OPENAI_API_BASE and OPENAI_API_KEY from environment.

    Returns:
        Tuple of (response_dict, metrics)
    """
    # Initialize metrics tracking
    metrics = APICallMetrics(
        stage=stage,
        model=model,
        temperature=temperature,
        timeout=timeout or int(os.getenv("GPT_VERDICT_TIMEOUT", "180")),
        start_time=time.time()
    )

    base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    key = os.getenv("OPENAI_API_KEY")

    logger.info(f"Starting {stage} API call", extra={
        "model": model,
        "temperature": temperature,
        "timeout": metrics.timeout,
        "message_count": len(messages),
        "api_base": base
    })

    if not key:
        metrics.failure_category = FailureCategory.AUTHENTICATION_ERROR
        metrics.error_message = "OPENAI_API_KEY not set"
        logger.error("Authentication failed: OPENAI_API_KEY not set")
        raise RuntimeError("OPENAI_API_KEY not set")

    # Calculate request size for monitoring
    try:
        request_content = json.dumps(messages)
        metrics.request_size = len(request_content.encode('utf-8'))
        logger.debug(f"Request payload size: {metrics.request_size} bytes")
    except Exception as e:
        logger.warning(f"Failed to calculate request size: {e}")

    # Validate API key format
    if not key.startswith(('sk-', 'org-')):
        logger.debug(f"Using custom API key format: {key[:20]}...")

    # Use environment variable for timeout, default to 180 seconds (3 minutes)
    if timeout is None:
        timeout = metrics.timeout

    # Determine endpoint based on model type
    # GPT realtime models and some others use completions endpoint
    is_realtime_model = "realtime" in model.lower() or model.startswith("gpt-4o-realtime")
    is_completions_model = is_realtime_model or model in ["text-davinci-003", "text-davinci-002", "davinci", "curie", "babbage", "ada"]
    
    if is_completions_model:
        url = f"{base}/completions"
        # Convert messages to single prompt for completions endpoint
        prompt = ""
        for msg in messages:
            if msg["role"] == "system":
                prompt += f"System: {msg['content']}\n\n"
            elif msg["role"] == "user":
                prompt += f"User: {msg['content']}\n\n"
        prompt += "Assistant:"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": 4000,
            "stream": False
        }
        
        # Add temperature only for models that support it
        if not model.startswith("gpt-5") and not model.startswith("o3"):
            payload["temperature"] = temperature
            
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        
        logger.debug(f"Making completions request to {url}", extra={
            "payload_keys": list(payload.keys()),
            "model_in_payload": payload.get('model')
        })

        try:
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
            metrics.end_time = time.time()
            metrics.status_code = resp.status_code

            logger.info(f"Completions API response received", extra={
                "status_code": resp.status_code,
                "duration": metrics.duration
            })

            # Calculate response size
            if hasattr(resp, 'content'):
                metrics.response_size = len(resp.content)
                logger.debug(f"Response size: {metrics.response_size} bytes")

            resp.raise_for_status()

        except requests.exceptions.Timeout as e:
            metrics.end_time = time.time()
            metrics.failure_category = FailureCategory.API_TIMEOUT
            metrics.error_message = f"API timeout after {timeout}s"
            logger.error(f"API timeout for {stage}", extra={
                "timeout": timeout,
                "duration": metrics.duration,
                "error": str(e)
            })
            return None, metrics

        except requests.exceptions.HTTPError as e:
            metrics.end_time = time.time()
            if resp.status_code == 401:
                metrics.failure_category = FailureCategory.AUTHENTICATION_ERROR
            elif resp.status_code == 429:
                metrics.failure_category = FailureCategory.RATE_LIMIT_ERROR
            else:
                metrics.failure_category = FailureCategory.API_ERROR

            metrics.error_message = f"HTTP {resp.status_code}: {str(e)}"
            logger.error(f"HTTP error for {stage}", extra={
                "status_code": resp.status_code,
                "error": str(e),
                "response_text": resp.text[:500] if hasattr(resp, 'text') else "No response text"
            })
            return None, metrics

        except requests.exceptions.ConnectionError as e:
            metrics.end_time = time.time()
            metrics.failure_category = FailureCategory.NETWORK_ERROR
            metrics.error_message = f"Connection error: {str(e)}"
            logger.error(f"Network error for {stage}", extra={
                "error": str(e)
            })
            return None, metrics

        except Exception as e:
            metrics.end_time = time.time()
            metrics.failure_category = FailureCategory.API_ERROR
            metrics.error_message = f"Unexpected error: {str(e)}"
            logger.error(f"Unexpected API error for {stage}", extra={
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            return None, metrics

        # Parse response
        try:
            data = resp.json()
            logger.debug(f"Response parsed successfully", extra={
                "response_keys": list(data.keys())
            })
        except json.JSONDecodeError as e:
            metrics.failure_category = FailureCategory.MALFORMED_RESPONSE
            metrics.error_message = f"Invalid JSON response: {str(e)}"
            logger.error(f"Invalid JSON response for {stage}", extra={
                "error": str(e),
                "response_text": resp.text[:500] if hasattr(resp, 'text') else "No response text"
            })
            return None, metrics

        # Check for empty response or missing choices
        if "choices" not in data or not data["choices"]:
            metrics.failure_category = FailureCategory.EMPTY_RESPONSE
            metrics.error_message = "No choices in API response"
            logger.error(f"Empty choices in response for {stage}", extra={
                "response_data": data
            })
            return None, metrics

        # Prefer text, but some proxies may return message-style payloads even on /completions
        choice0 = data["choices"][0]
        content = (choice0.get("text") or "").strip()
        if not content and isinstance(choice0, dict) and "message" in choice0:
            msg = choice0.get("message") or {}
            content = (msg.get("content") or "").strip()
            # Some non-standard providers return content as a list of blocks
            if not content and isinstance(msg.get("content"), list):
                try:
                    blocks = msg.get("content")
                    parts = []
                    for b in blocks:
                        if isinstance(b, dict) and b.get("type") == "text":
                            parts.append(b.get("text") or "")
                        elif isinstance(b, str):
                            parts.append(b)
                    content = "\n".join([p for p in parts if p]).strip()
                except Exception:
                    content = ""
            # Function/tool-call fallbacks
            if not content:
                # tool_calls (OpenAI tool calling)
                tool_calls = msg.get("tool_calls")
                if isinstance(tool_calls, list) and tool_calls:
                    try:
                        fn = tool_calls[0].get("function", {})
                        args = fn.get("arguments")
                        if isinstance(args, (dict, list)):
                            content = json.dumps(args)
                        elif isinstance(args, str):
                            content = args
                    except Exception:
                        pass
                # legacy function_call
                if not content and isinstance(msg.get("function_call"), dict):
                    args = msg["function_call"].get("arguments")
                    if isinstance(args, (dict, list)):
                        content = json.dumps(args)
                    elif isinstance(args, str):
                        content = args
        
        # Check for empty content
        if not content:
            metrics.failure_category = FailureCategory.EMPTY_RESPONSE
            metrics.error_message = "Empty content in completions response"
            logger.warning(f"Empty content in completions response for {stage}", extra={
                "full_response": data
            })
            # Do not raise here; allow downstream fallback to handle gracefully
            content = ""
    else:
        url = f"{base}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 4000,
            "stream": False
        }
        # Prefer structured JSON output if the provider supports it
        payload_with_json_mode = dict(payload)
        payload_with_json_mode["response_format"] = {"type": "json_object"}

        # Add temperature only for models that support it
        if not model.startswith("gpt-5") and not model.startswith("o3"):
            payload["temperature"] = temperature
            payload_with_json_mode["temperature"] = temperature
            
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        
        logger.debug(f"Making chat completions request to {url}", extra={
            "payload_keys_json_mode": list(payload_with_json_mode.keys()),
            "model_in_payload": payload.get('model'),
            "messages_count": len(messages)
        })

        # Try JSON mode first, then gracefully fall back if the provider/model doesn't support it
        data = None
        json_mode_attempted = False

        try:
            # First attempt with JSON mode
            json_mode_attempted = True
            resp = requests.post(url, headers=headers, data=json.dumps(payload_with_json_mode), timeout=timeout)
            metrics.end_time = time.time()
            metrics.status_code = resp.status_code

            logger.info(f"Chat API response received (JSON mode)", extra={
                "status_code": resp.status_code,
                "duration": metrics.duration
            })

            if hasattr(resp, 'content'):
                metrics.response_size = len(resp.content)

            resp.raise_for_status()
            data = resp.json()

        except requests.exceptions.HTTPError as http_err:
            body = getattr(http_err, 'response', None)
            body_text = body.text if body is not None else ''
            logger.warning(f"Chat API JSON mode failed, retrying without JSON mode", extra={
                "status_code": getattr(body, 'status_code', 'NA'),
                "error_snippet": body_text[:200]
            })

            # Retry without response_format
            try:
                resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
                metrics.end_time = time.time()
                metrics.status_code = resp.status_code

                logger.info(f"Chat API response received (fallback)", extra={
                    "status_code": resp.status_code,
                    "duration": metrics.duration
                })

                if hasattr(resp, 'content'):
                    metrics.response_size = len(resp.content)

                resp.raise_for_status()
                data = resp.json()

            except requests.exceptions.Timeout as e:
                metrics.end_time = time.time()
                metrics.failure_category = FailureCategory.API_TIMEOUT
                metrics.error_message = f"API timeout after {timeout}s (fallback)"
                logger.error(f"API timeout for {stage} (fallback)", extra={
                    "timeout": timeout,
                    "duration": metrics.duration
                })
                return None, metrics

            except Exception as fallback_e:
                metrics.end_time = time.time()
                metrics.failure_category = FailureCategory.API_ERROR
                metrics.error_message = f"Fallback request failed: {str(fallback_e)}"
                logger.error(f"Fallback request failed for {stage}", extra={
                    "error": str(fallback_e),
                    "original_error": str(http_err)
                })
                return None, metrics

        except requests.exceptions.Timeout as e:
            metrics.end_time = time.time()
            metrics.failure_category = FailureCategory.API_TIMEOUT
            metrics.error_message = f"API timeout after {timeout}s"
            logger.error(f"API timeout for {stage}", extra={
                "timeout": timeout,
                "duration": metrics.duration,
                "json_mode_attempted": json_mode_attempted
            })
            return None, metrics

        except Exception as e:
            metrics.end_time = time.time()
            metrics.failure_category = FailureCategory.API_ERROR
            metrics.error_message = f"Chat API error: {str(e)}"
            logger.error(f"Chat API error for {stage}", extra={
                "error": str(e),
                "json_mode_attempted": json_mode_attempted,
                "traceback": traceback.format_exc()
            })
            return None, metrics

        # Validate response data
        if data is None:
            metrics.failure_category = FailureCategory.EMPTY_RESPONSE
            metrics.error_message = "Received null response data"
            logger.error(f"Null response data for {stage}")
            return None, metrics

        logger.debug(f"Response parsed successfully", extra={
            "response_keys": list(data.keys())
        })

        # Check for empty response or missing choices
        if "choices" not in data or not data["choices"]:
            metrics.failure_category = FailureCategory.EMPTY_RESPONSE
            metrics.error_message = "No choices in chat API response"
            logger.error(f"Empty choices in chat response for {stage}", extra={
                "response_data": data
            })
            return None, metrics
            
        # Robustly extract content from the first choice
        choice = data["choices"][0]
        content = _extract_choice_content(choice)

        if not content:
            metrics.failure_category = FailureCategory.EMPTY_RESPONSE
            metrics.error_message = "Empty content extracted from choice"
            logger.error(f"Empty content extracted for {stage}", extra={
                "choice_data": choice
            })
            return None, metrics

        # Mark as successful if we got content
        metrics.success = True
        logger.info(f"{stage} API call completed successfully", extra={
            "duration": metrics.duration,
            "response_length": len(content)
        })
    
    def _extract_json_from_response(text: str, stage: str = "unknown") -> Tuple[dict, JSONParsingDiagnostics]:
        """
        Extract JSON from potentially malformed response text with comprehensive diagnostics.

        This method is designed to be extremely flexible and forgiving in parsing,
        ensuring that even minimal or slightly malformed responses can be processed.
        
        Args:
            text: The response text to parse
            stage: The stage name ("Analyst" or "Trader") to adjust validation requirements
        """
        # Initialize diagnostics with enhanced logging
        diagnostics = JSONParsingDiagnostics(
            raw_response=text[:2000],  # Increase logging preview
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

        # Log comprehensive input information
        logger.info("JSON Extraction Attempt", extra={
            "response_length": len(text),
            "response_preview": text[:500],  # Increased preview for more context
            "truncated": len(text) > 500,
            "non_printable_chars": sum(1 for c in text if not c.isprintable())
        })

        # Detailed logging of input characteristics
        try:
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
        except Exception as hint_error:
            logger.error("Error while collecting JSON parsing hints", extra={
                "error": str(hint_error)
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
            
            # Handle specific truncation artifacts (e.g. "0b" at end)
            s = re.sub(r'"\s*0b\s*$', '"', s.strip())
            s = re.sub(r'\s*0b\s*$', '', s.strip())
            
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

        # Helper to check if a dict looks like a valid verdict
        def _is_valid_verdict(d: dict) -> bool:
            """
            Validate verdict with more lenient criteria to ensure frontend compatibility.

            Goal: Allow minimal responses to still be considered valid.

            Args:
                d (dict): The verdict dictionary to validate

            Returns:
                bool: Whether the verdict can be considered valid
            """
            # Extremely minimal validation to ensure some basic structure exists
            if not isinstance(d, dict):
                logger.warning("Verdict is not a dictionary", extra={
                    "verdict_type": type(d),
                    "verdict_str": str(d)[:200]
                })
                return False

            # Log details about the verdict for debugging
            logger.info("Verdict validation details", extra={
                "keys_present": list(d.keys()),
                "final_bias": d.get('final_bias', 'Not found'),
                "confidence_level": d.get('confidence_level', 'Not found')
            })

            # Be extremely lenient: just ensure the dictionary is not completely empty
            # and has at least one potentially useful field
            useful_fields = [
                'final_bias',
                'confidence_level',
                'summary_html',
                'rationale',
                'key_reasoning_points',
                'execution_recommendations'
            ]

            # Check if any useful field exists and is not None/empty
            for field in useful_fields:
                field_value = d.get(field)
                if field_value not in [None, '', [], {}]:
                    logger.debug(f"Found non-empty field: {field}", extra={
                        "field_value": str(field_value)[:200]
                    })
                    return True

            logger.warning("No useful fields found in verdict", extra={
                "all_keys": list(d.keys())
            })
            return False

        def _validate_and_score_result(result: dict) -> int:
            """Score result based on completeness and set diagnostics."""
            if not isinstance(result, dict):
                return -1

            diagnostics.extracted_json_keys = list(result.keys())
            
            # Stage-aware field requirements
            if stage == "Trader":
                # Trader stage only needs execution_recommendations
                required_fields = ['execution_recommendations']
                critical_fields = set()  # No critical fields for Trader stage
            else:
                # Analyst stage needs all fields
                required_fields = ['rationale', 'summary_html', 'final_bias', 'execution_recommendations']
                critical_fields = {'rationale', 'summary_html'}
            
            diagnostics.missing_required_fields = [f for f in required_fields if f not in result]

            # Check for CRITICAL fields that must be non-empty (for Analyst stage only)
            missing_critical = []
            for field in critical_fields:
                field_value = result.get(field)
                # Check if field is missing or empty (empty string, None, etc.)
                if not field_value or (isinstance(field_value, str) and len(field_value.strip()) == 0):
                    missing_critical.append(field)
                    logger.warning(f"CRITICAL FIELD EMPTY: {field} = {repr(field_value)[:100]}")

            # Score based on presence of key fields
            score = sum(1 for k in required_fields if k in result)

            # Penalty for missing critical analysis fields (only for Analyst stage)
            if missing_critical:
                score = score - len(missing_critical)

            max_score = len(required_fields)
            logger.debug(f"JSON validation score: {score}/{max_score} (stage: {stage})", extra={
                "extracted_keys": diagnostics.extracted_json_keys,
                "missing_fields": diagnostics.missing_required_fields,
                "missing_critical_fields": missing_critical,
                "stage": stage
            })
            return score

        # 1) Direct parse
        logger.debug("Attempting direct JSON parse")
        res = _try_parse(text.strip(), "direct")
        if isinstance(res, dict):
            score = _validate_and_score_result(res)
            # Stage-aware threshold: Trader needs score >= 1, Analyst needs score >= 3
            threshold = 1 if stage == "Trader" else 3
            if score >= threshold:
                diagnostics.direct_parse_success = True
                diagnostics.final_success = True
                logger.info(f"Direct JSON parse successful (score: {score}, threshold: {threshold})")
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

            # Stage-aware threshold
            threshold = 1 if stage == "Trader" else 3
            if best_score >= threshold:
                diagnostics.code_block_parse_success = True
                diagnostics.final_success = True
                logger.info(f"Code block parse successful with score {best_score} (threshold: {threshold})")
                return best_candidate, diagnostics
            elif best_score >= (threshold - 1):  # Fallback: return candidate with partial score
                diagnostics.code_block_parse_success = True
                diagnostics.final_success = True
                logger.warning(f"Code block parse with moderate score {best_score} (below strict threshold {threshold})")
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

            # Stage-aware threshold
            threshold = 1 if stage == "Trader" else 3
            if best_brace_score >= threshold:
                diagnostics.balanced_brace_parse_success = True
                diagnostics.final_success = True
                logger.info(f"Balanced brace parse successful with score {best_brace_score} (threshold: {threshold})")
                return best_brace_candidate, diagnostics
            elif best_brace_score >= (threshold - 1):
                # Log for debugging but don't accept yet - try other methods
                logger.debug(f"Balanced brace candidate found with score {best_brace_score}, but below strict threshold {threshold} - trying other extraction methods")
                # Don't return yet - let it try greedy as fallback

        # 4) Fallback: greedy first/last braces (as a last resort)
        logger.debug("Attempting greedy brace extraction as final fallback")
        greedy = re.search(r"\{.*\}", text, re.DOTALL)
        if greedy:
            res = _try_parse(greedy.group(0), "greedy")
            if isinstance(res, dict):
                score = _validate_and_score_result(res)
                # Stage-aware threshold
                threshold = 1 if stage == "Trader" else 3
                if score >= threshold:
                    diagnostics.greedy_parse_success = True
                    diagnostics.final_success = True
                    logger.info(f"Greedy parse succeeded with score {score} (threshold: {threshold})")
                    return res, diagnostics
                elif score >= (threshold - 1):  # Accept partial if all else fails
                    logger.warning(f"Accepting greedy parse with score {score} (below strict threshold {threshold})")
                    diagnostics.greedy_parse_success = True
                    diagnostics.final_success = True
                    return res, diagnostics

        # No valid JSON found - log details for debugging
        logger.error("All JSON parsing attempts failed", extra={
            "parsing_attempts": diagnostics.parsing_attempts,
            "errors": diagnostics.parsing_errors,
            "response_preview": text[:500] if text else "",
            "response_length": len(text) if text else 0,
            "has_execution_recommendations": "execution_recommendations" in text if text else False,
            "has_rationale": "rationale" in text if text else False,
            "has_summary_html": "summary_html" in text if text else False
        })
        return None, diagnostics
    
    # Try to extract valid JSON from the response
    print(f"DEBUG CONTENT: {repr(content)}")
    parsed_json, json_diagnostics = _extract_json_from_response(content, stage=stage)

    # Log parsing diagnostics
    if json_diagnostics.final_success:
        logger.info(f"JSON parsing successful for {stage}", extra={
            "attempts": json_diagnostics.parsing_attempts,
            "extracted_keys": json_diagnostics.extracted_json_keys,
            "missing_fields": json_diagnostics.missing_required_fields
        })
    else:
        logger.error(f"JSON parsing failed for {stage}", extra={
            "attempts": json_diagnostics.parsing_attempts,
            "errors": json_diagnostics.parsing_errors,
            "response_length": json_diagnostics.raw_response_length
        })

    if parsed_json is not None:
        # Validate that essential fields are present and add defaults if missing
        if 'execution_recommendations' not in parsed_json:
            print("WARNING: execution_recommendations missing from GPT response, adding default structure")
            parsed_json['execution_recommendations'] = {
                "primary_strategy": {
                    "type": "GPT Response Missing", 
                    "description": "GPT did not provide execution recommendations", 
                    "confidence": "Low", 
                    "time_horizon": "Unknown",
                    "legs": []
                },
                "alternative_strategies": [],
                "position_sizing": {"suggested_allocation": "Conservative allocation", "risk_level": "Conservative", "justification": "No GPT guidance provided"},
                "entry_conditions": [],
                "exit_conditions": [],
                "stop_loss_guidance": "Use standard risk management",
                "profit_target_guidance": "Use standard profit targets"
            }
        elif not isinstance(parsed_json['execution_recommendations'], dict):
            print(f"WARNING: execution_recommendations is not a dict: {type(parsed_json['execution_recommendations'])}")
            parsed_json['execution_recommendations'] = {
                "primary_strategy": {
                    "type": "Invalid Format", 
                    "description": "GPT returned malformed execution recommendations", 
                    "confidence": "Low", 
                    "time_horizon": "Unknown",
                    "legs": []
                },
                "alternative_strategies": [],
                "position_sizing": {"suggested_allocation": "Conservative allocation", "risk_level": "Conservative", "justification": "Malformed GPT response"},
                "entry_conditions": [],
                "exit_conditions": [],
                "stop_loss_guidance": "Use standard risk management",
                "profit_target_guidance": "Use standard profit targets"
            }
        
        # Ensure required subfields exist
        exec_rec = parsed_json['execution_recommendations']
        if 'primary_strategy' not in exec_rec:
            exec_rec['primary_strategy'] = {"type": "Missing Primary", "description": "GPT did not provide primary strategy", "confidence": "Low", "time_horizon": "Unknown", "legs": []}
        elif not isinstance(exec_rec['primary_strategy'], dict):
            exec_rec['primary_strategy'] = {"type": "Invalid Primary", "description": "GPT returned malformed primary strategy", "confidence": "Low", "time_horizon": "Unknown", "legs": []}
        else:
            # Ensure primary_strategy has legs array
            if 'legs' not in exec_rec['primary_strategy']:
                exec_rec['primary_strategy']['legs'] = []
            elif not isinstance(exec_rec['primary_strategy']['legs'], list):
                exec_rec['primary_strategy']['legs'] = []
        if 'position_sizing' not in exec_rec:
            exec_rec['position_sizing'] = {"suggested_allocation": "Conservative allocation", "risk_level": "Conservative", "justification": "No GPT guidance provided"}
        if 'entry_conditions' not in exec_rec:
            exec_rec['entry_conditions'] = []
        if 'exit_conditions' not in exec_rec:
            exec_rec['exit_conditions'] = []
        if 'alternative_strategies' not in exec_rec:
            exec_rec['alternative_strategies'] = []
        if 'stop_loss_guidance' not in exec_rec:
            exec_rec['stop_loss_guidance'] = "Use standard risk management"
        if 'profit_target_guidance' not in exec_rec:
            exec_rec['profit_target_guidance'] = "Use standard profit targets"
            
        # Ensure other required top-level fields exist
        # Only set final_bias for Analyst stage, not Trader
        if stage != "Trader" and 'final_bias' not in parsed_json:
            parsed_json['final_bias'] = 'Neutral'
        # Only generate summary_html for Analyst stage, not Trader
        if stage != "Trader" and 'summary_html' not in parsed_json:
            print("WARNING: Adding fallback summary_html - Analyst did not include this field")
            # Generate a basic HTML summary from rationale instead of error message
            rationale = parsed_json.get('rationale', 'No rationale provided.')
            final_bias = parsed_json.get('final_bias', 'Neutral')
            confidence = parsed_json.get('confidence_level', 'Medium')
            
            # Truncate at sentence boundary to avoid mid-sentence cuts
            truncated_rationale = rationale[:300]
            if len(rationale) > 300:
                last_period = truncated_rationale.rfind('.')
                last_exclamation = truncated_rationale.rfind('!')
                last_question = truncated_rationale.rfind('?')
                last_sentence = max(last_period, last_exclamation, last_question)
                if last_sentence > 200:  # Ensure we have substantial content
                    truncated_rationale = truncated_rationale[:last_sentence + 1]
                else:
                    truncated_rationale += '...'
            
            parsed_json['summary_html'] = f"""
            <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #1976d2;">
                <h4 style="margin: 0 0 10px 0; color: #1976d2;">AI Analysis Summary</h4>
                <div style="display: flex; gap: 10px; margin-bottom: 10px;">
                    <span style="background: #e3f2fd; padding: 4px 8px; border-radius: 3px; font-size: 12px; color: #0d47a1;">{final_bias}</span>
                    <span style="background: #fff3e0; padding: 4px 8px; border-radius: 3px; font-size: 12px; color: #e65100;">{confidence} Confidence</span>
                </div>
                <p style="margin: 0; line-height: 1.5; color: #333;">{truncated_rationale}</p>
            </div>
            """.strip()
        # Check for missing critical fields and log warnings
        # Only check Analyst fields for Analyst stage, not Trader
        missing_critical_fields = []

        if stage != "Trader":
            # Analyst stage requires these fields
            if 'rationale' not in parsed_json or not parsed_json.get('rationale'):
                parsed_json['rationale'] = 'GPT did not provide rationale'
                missing_critical_fields.append('rationale')
                logger.error(f"CRITICAL: {stage} did not provide 'rationale' field - using placeholder")

            if 'summary_html' not in parsed_json or not parsed_json.get('summary_html'):
                missing_critical_fields.append('summary_html')
                logger.error(f"CRITICAL: {stage} did not provide 'summary_html' field - check summary_html generation logic")

            if 'key_reasoning_points' not in parsed_json:
                parsed_json['key_reasoning_points'] = []
                logger.warning(f"WARNING: {stage} did not provide 'key_reasoning_points' - using empty array")

            if 'actionable_ideas' not in parsed_json:
                parsed_json['actionable_ideas'] = []
                logger.warning(f"WARNING: {stage} did not provide 'actionable_ideas' - using empty array")

            if 'risk_factors' not in parsed_json:
                parsed_json['risk_factors'] = []
                logger.warning(f"WARNING: {stage} did not provide 'risk_factors' - using empty array")

        if 'search_performed' not in parsed_json:
            parsed_json['search_performed'] = False
        if 'sources' not in parsed_json:
            parsed_json['sources'] = []

        # Attach model info so downstream save includes it
        if isinstance(parsed_json, dict):
            parsed_json.setdefault('model', model)

        if missing_critical_fields:
            logger.error(f"{stage} response is missing CRITICAL fields: {missing_critical_fields}", extra={
                "missing_fields": missing_critical_fields,
                "response_keys": list(parsed_json.keys()) if isinstance(parsed_json, dict) else []
            })

        logger.info(f"{stage} completed (with missing field fallbacks)" if missing_critical_fields else f"{stage} completed successfully", extra={
            "has_execution_recommendations": bool(parsed_json.get('execution_recommendations')),
            "final_keys": list(parsed_json.keys()) if isinstance(parsed_json, dict) else [],
            "missing_critical_fields": missing_critical_fields
        })
        return parsed_json, metrics
    
    # Log the problematic response for debugging
    if content:
        metrics.failure_category = FailureCategory.JSON_PARSE_ERROR
        metrics.error_message = "Failed to parse response as JSON"
        logger.error(f"Failed to parse {stage} response as JSON", extra={
            "response_preview": content[:500],
            "response_length": len(content),
            "parsing_errors": json_diagnostics.parsing_errors if 'json_diagnostics' in locals() else []
        })
        summary_html = f"<h5>AI Verdict (Unparsed)</h5><div style='background: #fff3cd; padding: 10px; border-radius: 4px; margin-bottom: 10px;'><strong>⚠️ Note:</strong> AI response could not be parsed as JSON</div><pre style='white-space: pre-wrap; background: #f8f9fa; padding: 10px; border-radius: 4px;'>{content[:1000]}</pre>"
        rationale = "Model response was not valid JSON; returning raw text."
    else:
        metrics.failure_category = FailureCategory.EMPTY_RESPONSE
        metrics.error_message = "Completely empty response"
        logger.error(f"{stage} returned completely empty response")
        summary_html = f"<h5>AI Verdict (Empty Response)</h5><div style='background: #f8d7da; padding: 10px; border-radius: 4px; margin-bottom: 10px;'><strong>⚠️ Error:</strong> AI service returned an empty response</div>"
        rationale = "AI service returned an empty response."
    
    # Fallback if model didn't return parseable JSON
    fallback = {
        "execution_recommendations": {
            "primary_strategy": {"type": "Unknown", "description": "Unable to parse AI response", "confidence": "Low", "time_horizon": "Unknown"},
            "alternative_strategies": [],
            "position_sizing": {"suggested_allocation": "Unknown", "risk_level": "Conservative", "justification": "Unable to parse AI response"},
            "entry_conditions": [],
            "exit_conditions": [],
            "stop_loss_guidance": "Use standard risk management",
            "profit_target_guidance": "Use standard profit targets"
        },
        "search_performed": False,
        "sources": [],
        "model": model
    }

    # Only include Analyst fields if we are in the Analyst stage or unknown
    # This prevents overwriting valid Analyst data when Trader stage fails
    if stage != "Trader":
        fallback.update({
            "final_bias": "Neutral",
            "summary_html": summary_html,
            "rationale": rationale,
            "key_reasoning_points": [],
            "actionable_ideas": [],
            "risk_factors": []
        })

    return fallback, metrics


def generate_gpt_verdict(
    ticker: str,
    expiration_date: str,
    analysis_result: Dict[str, Any],
    model: str = "gpt-5",
    use_web_search: bool = False,
    retry_config: Optional[RetryConfig] = None,
    timeout_config: Optional[TimeoutConfig] = None
) -> Dict[str, Any]:
    """
    Enhanced 2-stage GPT Verdict generation with retry logic, circuit breaker, and separate timeouts:
    1. Analyst Agent: Generates market thesis, bias, and rationale.
    2. Trader Agent: Generates specific execution strategy based on Analyst's thesis.

    Args:
        retry_config: Custom retry configuration (uses defaults if None)
        timeout_config: Custom timeout configuration (uses defaults if None)

    Returns verdict dict with embedded error diagnostics when failures occur.
    """
    if retry_config is None:
        retry_config = RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            max_delay=30.0  # Shorter max for faster recovery
        )

    if timeout_config is None:
        timeout_config = TimeoutConfig(
            analyst_timeout=int(os.getenv("GPT_ANALYST_TIMEOUT", "180")),  # 3 minutes
            trader_timeout=int(os.getenv("GPT_TRADER_TIMEOUT", "240"))     # 4 minutes
        )

    session_start = time.time()
    logger.info(f"Starting GPT verdict generation with retry support", extra={
        "ticker": ticker,
        "expiration_date": expiration_date,
        "model": model,
        "use_web_search": use_web_search,
        "retry_max_attempts": retry_config.max_attempts,
        "analyst_timeout": timeout_config.analyst_timeout,
        "trader_timeout": timeout_config.trader_timeout
    })

    # Stage 1: Analyst Agent with Retry Logic
    logger.info("Starting Stage 1: Analyst Agent")
    analyst_messages = _build_analyst_messages(ticker, expiration_date, analysis_result, use_web_search)

    analyst_result, analyst_metrics, analyst_retry_metrics = _openai_chat_completion_with_retry(
        messages=analyst_messages,
        model=model,
        temperature=0.3,
        stage="Analyst",
        retry_config=retry_config,
        timeout_config=timeout_config
    )

    # Handle analyst response with retry information
    if analyst_result is None:
        logger.error("Analyst Agent failed after all retry attempts", extra={
            "retry_attempts": analyst_retry_metrics.total_attempts,
            "total_retry_time": analyst_retry_metrics.total_retry_time,
            "final_failure": analyst_retry_metrics.final_failure_category.value if analyst_retry_metrics.final_failure_category else "unknown",
            "circuit_breaker_triggered": analyst_retry_metrics.circuit_breaker_triggered,
            "delays_used": analyst_retry_metrics.delays_used
        })
        # Return minimal fallback structure with retry information
        return {
            "final_bias": "Neutral",
            "summary_html": "<p>Analyst Agent failed to generate analysis after multiple attempts.</p>",
            "rationale": f"Analyst Agent failed: {analyst_metrics.error_message}",
            "key_reasoning_points": [],
            "actionable_ideas": [],
            "risk_factors": [],
            "execution_recommendations": {
                "primary_strategy": {
                    "type": "System Error",
                    "description": "Unable to generate recommendations due to analyst failure",
                    "confidence": "Low",
                    "time_horizon": "Unknown",
                    "legs": []
                }
            },
            "error_details": {
                "stage": "Analyst",
                "category": analyst_metrics.failure_category.value if analyst_metrics.failure_category else "unknown",
                "message": analyst_metrics.error_message,
                "duration": analyst_metrics.duration,
                "retry_info": {
                    "attempts": analyst_retry_metrics.total_attempts,
                    "total_retry_time": analyst_retry_metrics.total_retry_time,
                    "circuit_breaker_triggered": analyst_retry_metrics.circuit_breaker_triggered,
                    "delays_used": analyst_retry_metrics.delays_used
                }
            }
        }

    # Log analyst success with retry information
    logger.info("Analyst Agent completed successfully", extra={
        "duration": analyst_metrics.duration,
        "response_size": analyst_metrics.response_size,
        "returned_fields": list(analyst_result.keys()) if isinstance(analyst_result, dict) else [],
        "has_summary_html": bool(analyst_result.get('summary_html') if isinstance(analyst_result, dict) else False),
        "retry_attempts": analyst_retry_metrics.total_attempts,
        "successful_attempt": analyst_retry_metrics.successful_attempt,
        "total_retry_time": analyst_retry_metrics.total_retry_time
    })

    # Stage 2: Trader Agent - Enhanced options data validation
    logger.info("Starting Stage 2: Trader Agent")
    raw_options_data = analysis_result.get("options_positioning", {})

    # Enhanced options data filtering with comprehensive validation
    greeks = raw_options_data.get("greeks_by_strike", {})
    valid_strikes = raw_options_data.get("strike_distribution", {}).get("valid_strikes", [])

    logger.debug("Processing options data", extra={
        "raw_greeks_count": len(greeks),
        "valid_strikes_count": len(valid_strikes),
        "raw_strikes": valid_strikes[:10] if valid_strikes else []  # First 10 for debugging
    })

    # Ensure valid_strikes are floats for comparison
    valid_strikes_float = []
    invalid_strikes = []

    for s in valid_strikes:
        try:
            valid_strikes_float.append(float(s))
        except (ValueError, TypeError) as e:
            invalid_strikes.append(s)
            logger.warning(f"Invalid strike value: {s}, error: {e}")

    if invalid_strikes:
        logger.warning(f"Found {len(invalid_strikes)} invalid strikes", extra={
            "invalid_strikes": invalid_strikes[:5]  # First 5 for logging
        })

    # Filter greeks with detailed logging
    filtered_greeks = {}
    filtering_errors = []

    for k, v in greeks.items():
        try:
            if float(k) in valid_strikes_float:
                filtered_greeks[k] = v
            else:
                logger.debug(f"Strike {k} not in valid strikes, filtering out")
        except (ValueError, TypeError) as e:
            filtering_errors.append(f"Strike {k}: {str(e)}")

    if filtering_errors:
        logger.warning(f"Encountered {len(filtering_errors)} filtering errors", extra={
            "errors": filtering_errors[:5]
        })

    # Construct options data package
    raw_options_data_package = {
        "valid_strikes": valid_strikes_float,  # Use cleaned float strikes
        "undervalued_opportunities": raw_options_data.get("total_undervalued_options", 0),
        "top_opportunity": raw_options_data.get("top_opportunity"),
        "greeks_by_strike": filtered_greeks,
        "volatility_structure": analysis_result.get("volatility_structure", {})
    }

    # Attempt to sanitize and repair data before validation
    options_data, repair_attempts = _sanitize_and_repair_options_data(raw_options_data_package)

    if repair_attempts:
        logger.info(f"Applied {len(repair_attempts)} data repairs", extra={
            "repairs": repair_attempts[:10]  # Log first 10 repairs
        })

    # Validate options data quality with enhanced checks
    options_validation = _validate_options_data(options_data)

    logger.info("Enhanced options data validation completed", extra={
        "completeness_score": options_validation.data_completeness_score,
        "quality_score": options_validation.data_quality_score,
        "valid_strikes_count": options_validation.valid_strikes_count,
        "greeks_count": options_validation.greeks_count,
        "complete_greeks_count": options_validation.complete_greeks_count,
        "invalid_greeks_count": options_validation.invalid_greeks_count,
        "warnings_count": len(options_validation.warnings),
        "errors_count": len(options_validation.errors),
        "repair_attempts_count": len(repair_attempts)
    })

    # ENHANCED DECISION LOGIC WITH GRADUATED QUALITY LEVELS
    # The quality assessment already determined can_proceed based on asset-specific thresholds
    # We'll use that decision but also preserve backward compatibility

    # Get the assessment result stored during validation
    if hasattr(options_validation, 'quality_assessment_result'):
        assessment_result = options_validation.quality_assessment_result
        can_proceed = assessment_result.get('can_proceed', False)
        overall_level = assessment_result.get('overall_level', 'failed')
    else:
        # Fallback to original logic if assessment not available
        min_completeness_score = 0.3
        min_quality_score = 0.5

        completeness_sufficient = options_validation.data_completeness_score >= min_completeness_score
        quality_sufficient = options_validation.data_quality_score >= min_quality_score

        # Fixed fallback threshold ordering (was counterintuitive)
        can_proceed = (completeness_sufficient and quality_sufficient) or (
            options_validation.data_completeness_score >= 0.2 and
            options_validation.data_quality_score >= 0.6 and  # Fixed: was 0.7 (higher than main!)
            options_validation.complete_greeks_count > 0
        )
        overall_level = "legacy_assessment"

    print(f"DECISION_DEBUG: Final Processing Decision:")
    print(f"  Can Proceed: {can_proceed}")
    print(f"  Quality Level: {overall_level}")
    print(f"  Completeness Score: {options_validation.data_completeness_score:.4f}")
    print(f"  Quality Score: {options_validation.data_quality_score:.4f}")

    # Enhanced logic: Check for caution mode eligibility
    assessment_result = getattr(options_validation, 'quality_assessment_result', {})
    can_proceed_with_caution = assessment_result.get('can_proceed_with_caution', False)

    if not can_proceed:
        logger.error("Options data quality insufficient for trader agent", extra={
            "completeness_score": options_validation.data_completeness_score,
            "quality_score": options_validation.data_quality_score,
            "complete_greeks_count": options_validation.complete_greeks_count,
            "invalid_greeks_count": options_validation.invalid_greeks_count,
            "can_proceed_with_caution": can_proceed_with_caution,
            "errors": options_validation.errors[:5],  # Log first 5 errors
            "warnings": options_validation.warnings[:5]  # Log first 5 warnings
        })

        # Return analyst output with enhanced error details
        final_verdict = analyst_result.copy() if isinstance(analyst_result, dict) else {}

        # Create user-friendly issue descriptions
        issues = []
        recommendations = []

        # Analyze specific issues
        if options_validation.data_completeness_score < 0.5:
            issues.append({
                "description": f"Limited data coverage ({options_validation.data_completeness_score:.1%})",
                "impact": "Strategies may not cover full market scenarios",
                "severity": "warning" if options_validation.data_completeness_score > 0.3 else "error"
            })
            recommendations.append("Try a more liquid expiration date or ticker")

        if options_validation.data_quality_score < 0.5:
            issues.append({
                "description": f"Data quality concerns ({options_validation.data_quality_score:.1%})",
                "impact": "Greeks calculations may be inaccurate",
                "severity": "warning" if options_validation.data_quality_score > 0.3 else "error"
            })
            recommendations.append("Consider using a different analysis method")

        if options_validation.complete_greeks_count < 5:
            issues.append({
                "description": f"Limited strike coverage ({options_validation.complete_greeks_count} complete strikes)",
                "impact": "Strategy recommendations may be incomplete",
                "severity": "warning"
            })
            recommendations.append("Try an expiration with more active options")

        # Create detailed error description
        error_details = []
        if hasattr(options_validation, 'quality_assessment_result'):
            combined_score = assessment_result.get('combined_score', 0)
            error_details.append(f"Combined quality score {combined_score:.1%} below threshold")
        else:
            # Fallback error details
            if options_validation.data_completeness_score < min_completeness_score:
                error_details.append(f"Completeness score {options_validation.data_completeness_score:.2f} below {min_completeness_score}")
            if options_validation.data_quality_score < min_quality_score:
                error_details.append(f"Quality score {options_validation.data_quality_score:.2f} below {min_quality_score}")
            if options_validation.complete_greeks_count == 0:
                error_details.append("No strikes with complete greeks data")

        final_verdict.update({
            "execution_recommendations": {
                "primary_strategy": {
                    "type": "Data Quality Error",
                    "description": f"Options data validation failed: {'; '.join(error_details)}",
                    "confidence": "Low",
                    "time_horizon": "Unknown",
                    "legs": []
                }
            },
            "error_details": {
                "stage": "Trader",
                "category": "data_validation_error",
                "message": "Enhanced validation failed multiple criteria",
                "validation_scores": {
                    "completeness": options_validation.data_completeness_score,
                    "quality": options_validation.data_quality_score
                },
                "data_metrics": {
                    "valid_strikes": options_validation.valid_strikes_count,
                    "complete_greeks": options_validation.complete_greeks_count,
                    "invalid_greeks": options_validation.invalid_greeks_count
                },
                "validation_errors": options_validation.errors,
                "validation_warnings": options_validation.warnings,
                "repair_attempts": repair_attempts
            },
            # NEW: Enhanced quality assessment details for frontend
            "quality_assessment": {
                "overall_quality_level": overall_level,
                "combined_score": assessment_result.get('combined_score', options_validation.data_quality_score),
                "completeness_score": options_validation.data_completeness_score,
                "quality_score": options_validation.data_quality_score,
                "overlap_score": assessment_result.get('component_scores', {}).get('overlap', 0.0),
                "pass_threshold": assessment_result.get('thresholds_used', {}).get('pass_threshold', 0.6),
                "can_proceed_with_caution": can_proceed_with_caution,
                "caution_threshold": assessment_result.get('caution_threshold', 0.35),
                "asset_type": assessment_result.get('asset_type', 'standard'),
                "strike_count": options_validation.valid_strikes_count + options_validation.invalid_greeks_count,
                "valid_strikes": options_validation.valid_strikes_count,
                "issues": issues,
                "recommendations": recommendations
            }
        })
        return final_verdict

    # Execute trader agent call with retry logic
    trader_messages = _build_trader_messages(ticker, expiration_date, analyst_result, options_data)

    trader_result, trader_metrics, trader_retry_metrics = _openai_chat_completion_with_retry(
        messages=trader_messages,
        model=model,
        temperature=0.1,
        stage="Trader",
        retry_config=retry_config,
        timeout_config=timeout_config
    )

    # Handle trader response with retry information
    if trader_result is None:
        logger.error("Trader Agent failed after all retry attempts", extra={
            "retry_attempts": trader_retry_metrics.total_attempts,
            "total_retry_time": trader_retry_metrics.total_retry_time,
            "final_failure": trader_retry_metrics.final_failure_category.value if trader_retry_metrics.final_failure_category else "unknown",
            "circuit_breaker_triggered": trader_retry_metrics.circuit_breaker_triggered,
            "delays_used": trader_retry_metrics.delays_used,
            "analyst_keys": list(analyst_result.keys()) if isinstance(analyst_result, dict) else [],
            "options_data_keys": list(options_data.keys()),
            "options_completeness": options_validation.data_completeness_score
        })

        # Return analyst output with error details for trader failure
        final_verdict = analyst_result.copy() if isinstance(analyst_result, dict) else {}
        final_verdict.update({
            "execution_recommendations": {
                "primary_strategy": {
                    "type": "Trader Agent Failed",
                    "description": f"Trader Agent failed after {trader_retry_metrics.total_attempts} attempts: {trader_metrics.error_message}",
                    "confidence": "Low",
                    "time_horizon": "Unknown",
                    "legs": []
                }
            },
            "error_details": {
                "stage": "Trader",
                "category": trader_metrics.failure_category.value if trader_metrics.failure_category else "unknown",
                "message": trader_metrics.error_message,
                "duration": trader_metrics.duration,
                "retry_info": {
                    "attempts": trader_retry_metrics.total_attempts,
                    "total_retry_time": trader_retry_metrics.total_retry_time,
                    "circuit_breaker_triggered": trader_retry_metrics.circuit_breaker_triggered,
                    "delays_used": trader_retry_metrics.delays_used
                },
                "options_validation": {
                    "score": options_validation.data_completeness_score,
                    "warnings": options_validation.warnings,
                    "errors": options_validation.errors
                }
            }
        })
        return final_verdict

    # Log trader success with retry information
    logger.info("Trader Agent completed successfully", extra={
        "duration": trader_metrics.duration,
        "response_size": trader_metrics.response_size,
        "returned_fields": list(trader_result.keys()) if isinstance(trader_result, dict) else [],
        "retry_attempts": trader_retry_metrics.total_attempts,
        "successful_attempt": trader_retry_metrics.successful_attempt,
        "total_retry_time": trader_retry_metrics.total_retry_time
    })

    # Merge results and log final success
    # IMPORTANT: Preserve Analyst's fields (final_bias, rationale, summary_html, etc.) and only add Trader's execution_recommendations
    if isinstance(analyst_result, dict) and isinstance(trader_result, dict):
        final_verdict = {**analyst_result}  # Start with Analyst's result
        # Only merge Trader's execution_recommendations, not other fields that might overwrite Analyst's work
        if 'execution_recommendations' in trader_result:
            final_verdict['execution_recommendations'] = trader_result['execution_recommendations']
        # Preserve Trader's model info if different
        if 'model' in trader_result and trader_result['model'] != analyst_result.get('model'):
            final_verdict['trader_model'] = trader_result['model']
    else:
        final_verdict = {}

    session_duration = time.time() - session_start
    logger.info("GPT verdict generation completed successfully", extra={
        "total_duration": session_duration,
        "analyst_duration": analyst_metrics.duration,
        "trader_duration": trader_metrics.duration,
        "final_verdict_keys": list(final_verdict.keys()),
        "has_execution_recommendations": bool(final_verdict.get('execution_recommendations')),
        # Comprehensive retry metrics
        "total_api_calls": analyst_retry_metrics.total_attempts + trader_retry_metrics.total_attempts,
        "analyst_retry_info": {
            "attempts": analyst_retry_metrics.total_attempts,
            "successful_attempt": analyst_retry_metrics.successful_attempt,
            "retry_time": analyst_retry_metrics.total_retry_time
        },
        "trader_retry_info": {
            "attempts": trader_retry_metrics.total_attempts,
            "successful_attempt": trader_retry_metrics.successful_attempt,
            "retry_time": trader_retry_metrics.total_retry_time
        },
        "circuit_breaker_events": {
            "analyst_triggered": analyst_retry_metrics.circuit_breaker_triggered,
            "trader_triggered": trader_retry_metrics.circuit_breaker_triggered
        }
    })

    # Add retry summary to final verdict for monitoring
    final_verdict['_retry_summary'] = {
        "session_duration": session_duration,
        "analyst_attempts": analyst_retry_metrics.total_attempts,
        "trader_attempts": trader_retry_metrics.total_attempts,
        "total_retry_time": analyst_retry_metrics.total_retry_time + trader_retry_metrics.total_retry_time,
        "circuit_breaker_events": analyst_retry_metrics.circuit_breaker_triggered or trader_retry_metrics.circuit_breaker_triggered
    }

    return final_verdict

