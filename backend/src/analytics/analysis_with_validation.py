"""
Enhanced Analysis Module with Core Validation Integration

This module extends the existing analysis pipeline with comprehensive data validation
using the Core Validation Engine. It provides validation gates before analysis
and enhanced quality reporting.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import logging
from datetime import date
from typing import Dict, Any, Optional

# Import existing analysis components
from .analysis import run_analysis as original_run_analysis

# Import validation systems
from .validation_integration import validate_options_for_analysis
from .quality_config import QualityAssessment


def run_analysis_with_validation(ticker: str,
                                expiration_date: date,
                                r_current: float = 0.05,
                                rate_source: str = 'etf',
                                analysis_method: str = 'holistic-market-edge',
                                override_price: float = None,
                                gpt_model: str = 'gpt-5',
                                validation_mode: str = 'strict',
                                min_quality_threshold: float = 0.45) -> Dict[str, Any]:
    """
    Run options analysis with comprehensive data validation.

    This function adds a validation gate before the main analysis pipeline,
    ensuring data quality meets minimum requirements for reliable analysis.

    Args:
        ticker: Stock ticker symbol
        expiration_date: Option expiration date
        r_current: Risk-free rate
        rate_source: Source for risk-free rate ('etf' or 'treasury')
        analysis_method: Analysis methodology to use
        override_price: Manual price override (for testing)
        gpt_model: GPT model for verdict generation
        validation_mode: 'strict', 'standard', or 'permissive'
        min_quality_threshold: Minimum quality score to proceed (0.0-1.0)

    Returns:
        Enhanced analysis results with validation report
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Starting validated analysis for {ticker} expiration {expiration_date}")

    # Set validation thresholds based on mode
    quality_thresholds = {
        'strict': {'min_score': 0.7, 'min_excellent_pct': 0.3, 'max_critical_issues': 3},
        'standard': {'min_score': 0.5, 'min_excellent_pct': 0.1, 'max_critical_issues': 8},
        'permissive': {'min_score': 0.3, 'min_excellent_pct': 0.0, 'max_critical_issues': 15}
    }

    threshold_config = quality_thresholds.get(validation_mode, quality_thresholds['standard'])
    actual_threshold = max(min_quality_threshold, threshold_config['min_score'])

    # Step 1: Run the original analysis to get the options data
    logger.info("Running initial analysis to obtain options data...")
    try:
        initial_analysis = original_run_analysis(
            ticker=ticker,
            expiration_date=expiration_date,
            r_current=r_current,
            rate_source=rate_source,
            analysis_method=analysis_method,
            override_price=override_price,
            gpt_model=gpt_model
        )
    except Exception as e:
        logger.error(f"Initial analysis failed: {e}")
        return {
            'status': 'error',
            'error_type': 'analysis_failure',
            'message': f'Initial analysis failed: {e}',
            'validation_report': None,
            'analysis_results': None,
            'recommendations': ['Fix data source issues and retry analysis']
        }

    # Check if initial analysis was successful
    if initial_analysis.get('status') == 'error':
        return {
            'status': 'error',
            'error_type': 'data_fetch_failure',
            'message': initial_analysis.get('message', 'Unknown data fetch error'),
            'validation_report': None,
            'analysis_results': initial_analysis,
            'recommendations': ['Check ticker symbol and expiration date', 'Verify data source connectivity']
        }

    # Extract options data for validation
    options_data = initial_analysis.get('options_positioning', {}).get('greeks_by_strike', {})
    spot_price = initial_analysis.get('market_context', {}).get('current_price')

    if not options_data:
        return {
            'status': 'error',
            'error_type': 'no_options_data',
            'message': 'No options data available for validation',
            'validation_report': None,
            'analysis_results': initial_analysis,
            'recommendations': [
                'Try a different expiration date with more active options',
                'Check if options are available for this ticker'
            ]
        }

    # Determine asset type for validation
    asset_type = QualityAssessment.determine_asset_type(ticker, len(options_data))
    logger.info(f"Determined asset type: {asset_type}")

    # Step 2: Run comprehensive validation
    logger.info("Running comprehensive data validation...")
    try:
        validation_results = validate_options_for_analysis(
            options_data=options_data,
            ticker=ticker,
            expiration_date=expiration_date.strftime('%Y-%m-%d'),
            spot_price=spot_price,
            asset_type=asset_type
        )
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return {
            'status': 'warning',
            'error_type': 'validation_failure',
            'message': f'Validation system failed, proceeding with analysis: {e}',
            'validation_report': {'status': 'failed', 'error': str(e)},
            'analysis_results': initial_analysis,
            'recommendations': ['Review analysis results with extra caution due to validation failure']
        }

    # Step 3: Check validation gate decision
    gate_decision = validation_results.get('gate_decision', {})
    consolidated_metrics = validation_results.get('data_quality_metrics', {})

    overall_quality = consolidated_metrics.get('consolidated_quality_score', 0.0)
    critical_issues = validation_results.get('validation_summary', {}).get('core_validation', {}).get('critical_issues', 0)

    logger.info(f"Validation complete. Quality score: {overall_quality:.3f}, Critical issues: {critical_issues}")

    # Step 4: Apply validation gate logic
    validation_passed = (
        gate_decision.get('gate_decision') == 'APPROVE' and
        overall_quality >= actual_threshold and
        critical_issues <= threshold_config['max_critical_issues']
    )

    if not validation_passed:
        # Generate detailed rejection reason
        rejection_reasons = []

        if overall_quality < actual_threshold:
            rejection_reasons.append(f"Quality score {overall_quality:.1%} below threshold {actual_threshold:.1%}")

        if critical_issues > threshold_config['max_critical_issues']:
            rejection_reasons.append(f"Too many critical issues ({critical_issues} > {threshold_config['max_critical_issues']})")

        if gate_decision.get('gate_decision') == 'REJECT':
            rejection_reasons.append(f"Gate decision: {gate_decision.get('reason', 'Unknown')}")

        return {
            'status': 'rejected',
            'error_type': 'validation_gate_failure',
            'message': f"Analysis rejected due to insufficient data quality: {'; '.join(rejection_reasons)}",
            'validation_report': validation_results,
            'analysis_results': initial_analysis,  # Include for debugging
            'quality_metrics': {
                'overall_score': overall_quality,
                'threshold_used': actual_threshold,
                'validation_mode': validation_mode,
                'critical_issues_count': critical_issues
            },
            'recommendations': _generate_improvement_recommendations(validation_results, threshold_config)
        }

    # Step 5: Validation passed - enhance analysis with validation insights
    logger.info("Validation passed, enhancing analysis results...")

    # Create enhanced analysis package
    enhanced_analysis = {
        'status': 'success',
        'validation_status': 'passed',
        'validation_report': validation_results,
        'analysis_results': initial_analysis,
        'quality_metrics': {
            'overall_score': overall_quality,
            'validation_mode': validation_mode,
            'threshold_used': actual_threshold,
            'asset_type': asset_type,
            'processing_mode': gate_decision.get('processing_mode', 'standard'),
            'confidence_level': gate_decision.get('confidence_level', 'medium')
        },
        'data_quality_insights': _generate_quality_insights(validation_results),
        'enhanced_strike_recommendations': _generate_enhanced_strike_recommendations(
            validation_results, initial_analysis
        ),
        'risk_adjustments': _generate_risk_adjustments(validation_results, overall_quality)
    }

    # Add validation-aware position sizing recommendations
    enhanced_analysis['position_sizing'] = _generate_position_sizing_recommendations(
        validation_results, overall_quality, gate_decision.get('confidence_level', 'medium')
    )

    # Add monitoring requirements
    enhanced_analysis['monitoring_requirements'] = validation_results.get(
        'processing_decisions', {}
    ).get('monitoring_requirements', ['Standard monitoring protocols sufficient'])

    logger.info("Enhanced analysis complete with validation integration")

    return enhanced_analysis


def _generate_improvement_recommendations(validation_results: Dict[str, Any],
                                        threshold_config: Dict[str, Any]) -> list:
    """Generate recommendations for improving data quality."""
    recommendations = []

    core_validation = validation_results.get('validation_summary', {}).get('core_validation', {})
    category_scores = core_validation.get('category_scores', {})

    # Category-specific recommendations
    if category_scores.get('pricing', 0) < 0.5:
        recommendations.append("Improve pricing data quality: seek sources with complete bid/ask/last prices")

    if category_scores.get('greeks', 0) < 0.5:
        recommendations.append("Address Greeks data gaps: ensure all five Greeks are calculated and valid")

    if category_scores.get('liquidity', 0) < 0.3:
        recommendations.append("Consider more liquid options: focus on higher volume and open interest strikes")

    # Issue-specific recommendations
    critical_issues = core_validation.get('critical_issues', 0)
    if critical_issues > 5:
        recommendations.append("Address critical data quality issues before proceeding with analysis")

    # General recommendations
    recommendations.extend([
        "Consider alternative expiration dates with better data quality",
        "Try multiple data sources and compare results",
        "Use smaller position sizes if data quality concerns persist"
    ])

    return recommendations[:5]  # Limit to top 5 recommendations


def _generate_quality_insights(validation_results: Dict[str, Any]) -> Dict[str, Any]:
    """Generate insights about data quality for user understanding."""
    core_validation = validation_results.get('validation_summary', {}).get('core_validation', {})
    strikes_by_quality = core_validation.get('strikes_by_quality', {})
    category_scores = core_validation.get('category_scores', {})

    total_strikes = sum(strikes_by_quality.values()) or 1

    insights = {
        'data_completeness': {
            'pricing_quality': category_scores.get('pricing', 0),
            'greeks_quality': category_scores.get('greeks', 0),
            'liquidity_quality': category_scores.get('liquidity', 0)
        },
        'strike_quality_distribution': {
            'excellent_pct': (strikes_by_quality.get('excellent', 0) / total_strikes) * 100,
            'good_pct': (strikes_by_quality.get('good', 0) / total_strikes) * 100,
            'acceptable_pct': (strikes_by_quality.get('acceptable', 0) / total_strikes) * 100,
            'usable_pct': ((strikes_by_quality.get('excellent', 0) +
                           strikes_by_quality.get('good', 0)) / total_strikes) * 100
        },
        'key_strengths': _identify_data_strengths(category_scores),
        'key_weaknesses': _identify_data_weaknesses(category_scores),
        'overall_assessment': core_validation.get('recommendation', 'Quality assessment unavailable')
    }

    return insights


def _identify_data_strengths(category_scores: Dict[str, float]) -> list:
    """Identify data quality strengths."""
    strengths = []

    if category_scores.get('pricing', 0) >= 0.8:
        strengths.append("Excellent pricing data completeness")
    if category_scores.get('greeks', 0) >= 0.8:
        strengths.append("Complete and valid Greeks calculations")
    if category_scores.get('liquidity', 0) >= 0.7:
        strengths.append("Good liquidity indicators")

    if not strengths:
        # Find the best category even if not excellent
        best_category = max(category_scores.items(), key=lambda x: x[1])
        if best_category[1] >= 0.5:
            category_name = best_category[0].replace('_', ' ').title()
            strengths.append(f"Reasonable {category_name} quality")

    return strengths


def _identify_data_weaknesses(category_scores: Dict[str, float]) -> list:
    """Identify data quality weaknesses."""
    weaknesses = []

    if category_scores.get('pricing', 0) < 0.5:
        weaknesses.append("Incomplete pricing data (missing bid/ask/last prices)")
    if category_scores.get('greeks', 0) < 0.5:
        weaknesses.append("Missing or invalid Greeks calculations")
    if category_scores.get('liquidity', 0) < 0.4:
        weaknesses.append("Poor liquidity indicators (low volume/OI, wide spreads)")

    return weaknesses


def _generate_enhanced_strike_recommendations(validation_results: Dict[str, Any],
                                            initial_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Generate enhanced strike recommendations based on validation results."""

    focus_strikes = validation_results.get('processing_decisions', {}).get('focus_strikes', {})
    high_confidence = focus_strikes.get('high_confidence', [])
    medium_confidence = focus_strikes.get('medium_confidence', [])

    # Get original analysis recommendations
    original_positioning = initial_analysis.get('options_positioning', {})

    return {
        'high_confidence_strikes': high_confidence[:10],  # Top 10 high confidence strikes
        'medium_confidence_strikes': medium_confidence[:10],  # Top 10 medium confidence strikes
        'total_usable_strikes': len(high_confidence) + len(medium_confidence),
        'data_quality_note': f"Strike recommendations filtered based on data quality validation",
        'original_strike_count': len(original_positioning.get('greeks_by_strike', {})),
        'quality_filtered_count': len(high_confidence) + len(medium_confidence)
    }


def _generate_risk_adjustments(validation_results: Dict[str, Any], overall_quality: float) -> Dict[str, Any]:
    """Generate risk adjustments based on data quality."""

    risk_multiplier = 1.0

    if overall_quality < 0.6:
        risk_multiplier = 1.5  # Increase risk estimates by 50%
    elif overall_quality < 0.8:
        risk_multiplier = 1.25  # Increase risk estimates by 25%

    confidence_adjustments = []

    if overall_quality < 0.7:
        confidence_adjustments.append("Reduce confidence in Greeks accuracy")
    if overall_quality < 0.5:
        confidence_adjustments.append("Increase margin of safety for position sizing")
        confidence_adjustments.append("Monitor positions more frequently")

    return {
        'risk_multiplier': risk_multiplier,
        'confidence_adjustments': confidence_adjustments,
        'quality_based_note': f"Risk adjustments applied based on {overall_quality:.1%} data quality score"
    }


def _generate_position_sizing_recommendations(validation_results: Dict[str, Any],
                                            overall_quality: float,
                                            confidence_level: str) -> Dict[str, Any]:
    """Generate position sizing recommendations based on validation results."""

    base_size = 1.0  # Normal position size

    # Adjust based on quality score
    if overall_quality >= 0.8:
        size_multiplier = 1.0  # Full size
        sizing_note = "Normal position sizing appropriate for high-quality data"
    elif overall_quality >= 0.65:
        size_multiplier = 0.75  # Reduce by 25%
        sizing_note = "Reduce position size by 25% due to moderate data quality concerns"
    elif overall_quality >= 0.5:
        size_multiplier = 0.5  # Reduce by 50%
        sizing_note = "Reduce position size by 50% due to data quality limitations"
    else:
        size_multiplier = 0.25  # Reduce by 75%
        sizing_note = "Limit to exploratory positions (25% of normal size) due to poor data quality"

    # Further adjust based on confidence level
    confidence_adjustments = {
        'high': 1.0,
        'medium': 0.8,
        'low': 0.6,
        'insufficient': 0.3
    }

    size_multiplier *= confidence_adjustments.get(confidence_level, 0.8)

    return {
        'size_multiplier': size_multiplier,
        'recommended_size_pct': size_multiplier * 100,
        'sizing_rationale': sizing_note,
        'confidence_level': confidence_level,
        'quality_score': overall_quality
    }


# Compatibility function to maintain existing interface
def run_analysis_enhanced(ticker: str, expiration_date: date, **kwargs) -> Dict[str, Any]:
    """
    Enhanced analysis function with automatic validation.

    This function provides a drop-in replacement for the original run_analysis
    function but includes comprehensive data validation.
    """
    return run_analysis_with_validation(ticker, expiration_date, **kwargs)