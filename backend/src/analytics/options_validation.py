"""
Options data validation utilities for the analysis pipeline.

This module provides validation functions that can be used throughout the
options analysis pipeline to ensure data quality and completeness.
"""

import math
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass

@dataclass
class OptionsDataQualityReport:
    """Comprehensive quality report for options data."""
    valid_strikes_count: int
    complete_greeks_count: int
    invalid_values_count: int
    missing_fields_count: int
    quality_score: float  # 0.0 to 1.0
    issues: List[str]
    recommendations: List[str]

def validate_greeks_structure(greeks_by_strike: Dict[str, Any]) -> OptionsDataQualityReport:
    """
    Validates the structure and quality of greeks_by_strike data.

    Args:
        greeks_by_strike: Dictionary mapping strike prices to greeks data

    Returns:
        OptionsDataQualityReport with detailed validation results
    """
    issues = []
    recommendations = []
    valid_strikes_count = 0
    complete_greeks_count = 0
    invalid_values_count = 0
    missing_fields_count = 0

    if not greeks_by_strike:
        issues.append("No greeks data provided")
        recommendations.append("Ensure options pricing calculations are completing successfully")
        return OptionsDataQualityReport(
            valid_strikes_count=0,
            complete_greeks_count=0,
            invalid_values_count=0,
            missing_fields_count=0,
            quality_score=0.0,
            issues=issues,
            recommendations=recommendations
        )

    expected_greeks = ['delta', 'gamma', 'theta', 'vega', 'rho']
    expected_prices = ['market_price', 'model_price']

    for strike_key, strike_data in greeks_by_strike.items():
        # Validate strike key
        try:
            strike_float = float(strike_key)
            if math.isnan(strike_float) or math.isinf(strike_float):
                issues.append(f"Invalid strike key: {strike_key}")
                continue
            valid_strikes_count += 1
        except (ValueError, TypeError):
            issues.append(f"Non-numeric strike key: {strike_key}")
            continue

        # Validate strike data structure
        if not isinstance(strike_data, dict):
            issues.append(f"Strike {strike_key} has invalid data structure")
            continue

        # Check for call/put data
        has_complete_option = False
        for option_type in ['call', 'put']:
            if option_type not in strike_data:
                continue

            option_data = strike_data[option_type]
            if not isinstance(option_data, dict):
                issues.append(f"Strike {strike_key} {option_type} has invalid structure")
                continue

            # Check for required fields
            missing_greeks = []
            invalid_values = []

            for field in expected_greeks + expected_prices:
                if field not in option_data:
                    missing_greeks.append(field)
                    missing_fields_count += 1
                    continue

                value = option_data[field]
                try:
                    float_val = float(value)
                    if math.isnan(float_val) or math.isinf(float_val):
                        invalid_values.append(f"{field}={value}")
                        invalid_values_count += 1
                    else:
                        # Range validation for specific greeks
                        if field == 'delta':
                            if option_type == 'call' and not (0 <= float_val <= 1):
                                invalid_values.append(f"call delta out of range: {float_val}")
                            elif option_type == 'put' and not (-1 <= float_val <= 0):
                                invalid_values.append(f"put delta out of range: {float_val}")
                        elif field == 'gamma' and float_val < 0:
                            invalid_values.append(f"negative gamma: {float_val}")
                except (ValueError, TypeError):
                    invalid_values.append(f"{field}={value} (not numeric)")
                    invalid_values_count += 1

            # Report issues for this option
            if missing_greeks:
                issues.append(f"Strike {strike_key} {option_type} missing: {', '.join(missing_greeks)}")
            if invalid_values:
                issues.append(f"Strike {strike_key} {option_type} invalid: {', '.join(invalid_values)}")

            # Check if this option is complete
            if not missing_greeks and not invalid_values:
                has_complete_option = True

        if has_complete_option:
            complete_greeks_count += 1

    # Calculate quality score
    if valid_strikes_count > 0:
        completeness_ratio = complete_greeks_count / valid_strikes_count
        error_ratio = max(0, 1 - (invalid_values_count + missing_fields_count) / max(1, valid_strikes_count * 7))  # 7 expected fields
        quality_score = (completeness_ratio + error_ratio) / 2

        # Enhanced logging for quality score debugging
        print(f"LEGACY_QUALITY_DEBUG: Options Validation Quality Score:")
        print(f"  Valid strikes: {valid_strikes_count}")
        print(f"  Complete strikes: {complete_greeks_count}")
        print(f"  Completeness ratio: {completeness_ratio:.4f} ({complete_greeks_count}/{valid_strikes_count})")
        print(f"  Invalid values: {invalid_values_count}")
        print(f"  Missing fields: {missing_fields_count}")
        print(f"  Total expected fields: {valid_strikes_count * 7}")
        print(f"  Error ratio: {error_ratio:.4f} (1 - {invalid_values_count + missing_fields_count}/{valid_strikes_count * 7})")
        print(f"  Final quality score: {quality_score:.4f} (avg of {completeness_ratio:.4f} and {error_ratio:.4f})")
    else:
        quality_score = 0.0
        print(f"LEGACY_QUALITY_DEBUG: No valid strikes - Quality Score = 0.0")

    # Generate recommendations
    if complete_greeks_count == 0:
        recommendations.append("No strikes have complete greeks data - check options pricing calculations")
    elif complete_greeks_count < valid_strikes_count * 0.5:
        recommendations.append("Less than 50% of strikes have complete data - verify data pipeline")

    if invalid_values_count > 0:
        recommendations.append("Invalid numerical values detected - check for NaN/infinity handling")

    if missing_fields_count > 0:
        recommendations.append("Missing greeks fields detected - ensure all greeks are calculated")

    return OptionsDataQualityReport(
        valid_strikes_count=valid_strikes_count,
        complete_greeks_count=complete_greeks_count,
        invalid_values_count=invalid_values_count,
        missing_fields_count=missing_fields_count,
        quality_score=quality_score,
        issues=issues,
        recommendations=recommendations
    )

def validate_options_analysis_output(analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates the options_positioning section of analysis output.

    Args:
        analysis_result: The full analysis result dictionary

    Returns:
        Dictionary with validation results and recommendations
    """
    validation_results = {
        "validation_passed": False,
        "quality_score": 0.0,
        "issues_found": [],
        "recommendations": [],
        "data_metrics": {}
    }

    options_positioning = analysis_result.get("options_positioning", {})

    if not options_positioning:
        validation_results["issues_found"].append("No options_positioning data in analysis result")
        validation_results["recommendations"].append("Verify options analysis is enabled and completing")
        return validation_results

    # Validate strikes
    valid_strikes = options_positioning.get("valid_strikes", [])
    strike_distribution = options_positioning.get("strike_distribution", {})
    analyzed_strikes = strike_distribution.get("analyzed_strikes", [])

    if not valid_strikes and not analyzed_strikes:
        validation_results["issues_found"].append("No valid strikes in options positioning data")
        validation_results["recommendations"].append("Check strike selection logic in options analysis")

    # Validate greeks
    greeks_by_strike = options_positioning.get("greeks_by_strike", {})
    greeks_report = validate_greeks_structure(greeks_by_strike)

    validation_results["data_metrics"].update({
        "valid_strikes_count": len(valid_strikes),
        "analyzed_strikes_count": len(analyzed_strikes),
        "greeks_strikes_count": len(greeks_by_strike),
        "complete_greeks_count": greeks_report.complete_greeks_count,
        "invalid_values_count": greeks_report.invalid_values_count,
        "missing_fields_count": greeks_report.missing_fields_count
    })

    validation_results["quality_score"] = greeks_report.quality_score
    validation_results["issues_found"].extend(greeks_report.issues)
    validation_results["recommendations"].extend(greeks_report.recommendations)

    # Check for opportunities
    total_undervalued = options_positioning.get("total_undervalued_options", 0)
    top_opportunity = options_positioning.get("top_opportunity")

    if total_undervalued == 0:
        validation_results["issues_found"].append("No undervalued options identified")
        validation_results["recommendations"].append("Review pricing model parameters or market data")

    if not top_opportunity:
        validation_results["issues_found"].append("No top opportunity identified")
        validation_results["recommendations"].append("Ensure opportunity ranking logic is working")

    # Overall validation
    min_quality_threshold = 0.5
    validation_results["validation_passed"] = (
        greeks_report.quality_score >= min_quality_threshold and
        len(valid_strikes) > 0 and
        greeks_report.complete_greeks_count > 0
    )

    return validation_results