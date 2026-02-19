"""
Core Validation Engine for Options Data Quality

This module provides a unified validation system that checks data quality across three
critical categories as specified in the task requirements:

1. Strike prices with complete pricing (bid, ask, last, model price)
2. All five Greeks (Delta, Gamma, Theta, Vega, Rho)
3. Liquidity indicators (volume ≥10, open interest ≥100, bid-ask spread <25% of ask)

The engine provides detailed validation reports and quality scores for comprehensive
options data assessment.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import logging

# Import existing quality configuration
from .quality_config import QualityLevel, QualityAssessment, AssetSpecificThresholds


class ValidationCategory(Enum):
    """Core validation categories."""
    STRIKE_PRICING = "strike_pricing"
    GREEKS_COMPLETENESS = "greeks_completeness"
    LIQUIDITY_INDICATORS = "liquidity_indicators"


class ValidationSeverity(Enum):
    """Validation issue severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class ValidationIssue:
    """Individual validation issue."""
    category: ValidationCategory
    severity: ValidationSeverity
    strike: float
    option_type: str  # 'call' or 'put'
    field: str
    issue_description: str
    current_value: Optional[Union[float, str]]
    expected_range: Optional[Tuple[float, float]]
    recommendation: str


@dataclass
class StrikePricingMetrics:
    """Metrics for strike pricing validation."""
    has_bid: bool = False
    has_ask: bool = False
    has_last: bool = False
    has_model_price: bool = False

    bid_value: Optional[float] = None
    ask_value: Optional[float] = None
    last_value: Optional[float] = None
    model_price_value: Optional[float] = None

    bid_ask_spread: Optional[float] = None
    bid_ask_spread_pct: Optional[float] = None

    pricing_completeness_score: float = 0.0
    pricing_quality_score: float = 0.0


@dataclass
class GreeksCompletenessMetrics:
    """Metrics for Greeks completeness validation."""
    has_delta: bool = False
    has_gamma: bool = False
    has_theta: bool = False
    has_vega: bool = False
    has_rho: bool = False

    delta_value: Optional[float] = None
    gamma_value: Optional[float] = None
    theta_value: Optional[float] = None
    vega_value: Optional[float] = None
    rho_value: Optional[float] = None

    delta_valid: bool = False
    gamma_valid: bool = False
    theta_valid: bool = False
    vega_valid: bool = False
    rho_valid: bool = False

    greeks_completeness_score: float = 0.0
    greeks_validity_score: float = 0.0


@dataclass
class LiquidityMetrics:
    """Metrics for liquidity indicators validation."""
    volume: Optional[float] = None
    open_interest: Optional[float] = None
    bid_ask_spread_pct: Optional[float] = None

    volume_meets_threshold: bool = False  # ≥10
    oi_meets_threshold: bool = False      # ≥100
    spread_meets_threshold: bool = False  # <25% of ask

    liquidity_score: float = 0.0
    volume_score: float = 0.0
    oi_score: float = 0.0
    spread_score: float = 0.0


@dataclass
class StrikeValidationResult:
    """Comprehensive validation result for a single strike."""
    strike: float
    option_type: str

    # Category-specific metrics
    pricing_metrics: StrikePricingMetrics
    greeks_metrics: GreeksCompletenessMetrics
    liquidity_metrics: LiquidityMetrics

    # Overall scores
    overall_quality_score: float = 0.0
    category_scores: Dict[ValidationCategory, float] = field(default_factory=dict)

    # Issues and recommendations
    issues: List[ValidationIssue] = field(default_factory=list)
    quality_level: QualityLevel = QualityLevel.FAILED

    # Processing flags
    passes_validation: bool = False
    requires_repair: bool = True
    can_proceed_with_caution: bool = False


@dataclass
class CoreValidationReport:
    """Comprehensive validation report for all strikes."""
    ticker: str
    expiration_date: str
    validation_timestamp: datetime

    # Summary statistics
    total_strikes: int = 0
    strikes_by_type: Dict[str, int] = field(default_factory=dict)  # call/put counts

    # Category summary scores
    overall_pricing_score: float = 0.0
    overall_greeks_score: float = 0.0
    overall_liquidity_score: float = 0.0
    combined_quality_score: float = 0.0

    # Strike-level results
    strike_results: Dict[Tuple[float, str], StrikeValidationResult] = field(default_factory=dict)

    # Quality distribution
    excellent_strikes: List[Tuple[float, str]] = field(default_factory=list)
    good_strikes: List[Tuple[float, str]] = field(default_factory=list)
    acceptable_strikes: List[Tuple[float, str]] = field(default_factory=list)
    poor_strikes: List[Tuple[float, str]] = field(default_factory=list)
    failed_strikes: List[Tuple[float, str]] = field(default_factory=list)

    # Issues summary
    critical_issues: List[ValidationIssue] = field(default_factory=list)
    high_priority_issues: List[ValidationIssue] = field(default_factory=list)
    all_issues: List[ValidationIssue] = field(default_factory=list)

    # Processing recommendations
    overall_recommendation: str = ""
    processing_decision: Dict[str, Any] = field(default_factory=dict)

    # Asset-specific thresholds used
    asset_type: str = "medium_liquidity"
    thresholds_used: Optional[Any] = None


class CoreValidationEngine:
    """
    Core validation engine for comprehensive options data quality assessment.

    This engine implements the three critical validation categories:
    1. Strike pricing completeness and quality
    2. Greeks completeness and validity
    3. Liquidity indicators assessment
    """

    def __init__(self, asset_type: str = "medium_liquidity"):
        """
        Initialize the core validation engine.

        Args:
            asset_type: Asset liquidity type (high_liquidity, medium_liquidity, low_liquidity)
        """
        self.logger = logging.getLogger(__name__)

        # Initialize quality assessment system
        self.quality_assessment = QualityAssessment(asset_type)
        self.asset_type = asset_type

        # Validation thresholds
        self.pricing_thresholds = {
            'min_completeness': 0.75,  # Need at least 3 of 4 pricing fields
            'max_bid_ask_spread_pct': 25.0,  # 25% of ask as specified in task
            'min_reasonable_price': 0.01,   # Minimum reasonable option price
            'max_reasonable_price': 10000.0  # Maximum reasonable option price
        }

        # Greeks validation bounds (expanded from existing system)
        self.greeks_bounds = {
            'delta': {'call': (-0.05, 1.05), 'put': (-1.05, 0.05)},  # Slight tolerance
            'gamma': {'call': (0, 15), 'put': (0, 15)},             # Extended range
            'theta': {'call': (-15, 2), 'put': (-15, 2)},            # Extended range
            'vega': {'call': (0, 8), 'put': (0, 8)},                 # Extended range
            'rho': {'call': (-75, 75), 'put': (-75, 75)}             # Extended range
        }

        # Liquidity thresholds as specified in task
        self.liquidity_thresholds = {
            'min_volume': 10,           # ≥10 as specified
            'min_open_interest': 100,   # ≥100 as specified
            'max_spread_pct': 25.0      # <25% of ask as specified
        }

        # Category weights for combined scoring
        self.category_weights = {
            ValidationCategory.STRIKE_PRICING: 0.35,
            ValidationCategory.GREEKS_COMPLETENESS: 0.40,
            ValidationCategory.LIQUIDITY_INDICATORS: 0.25
        }

    def validate_options_data(self,
                            options_data: Dict[str, Any],
                            ticker: str,
                            expiration_date: str,
                            spot_price: Optional[float] = None) -> CoreValidationReport:
        """
        Perform comprehensive validation of options data.

        Args:
            options_data: Options data dictionary (greeks_by_strike format)
            ticker: Stock ticker symbol
            expiration_date: Option expiration date string
            spot_price: Current spot price (optional, for relative validations)

        Returns:
            CoreValidationReport with comprehensive validation results
        """
        self.logger.info(f"Starting core validation for {ticker} expiration {expiration_date}")

        # Initialize report
        report = CoreValidationReport(
            ticker=ticker,
            expiration_date=expiration_date,
            validation_timestamp=datetime.now(),
            asset_type=self.asset_type,
            thresholds_used=self.quality_assessment.thresholds
        )

        # Process each strike
        for strike_key, strike_data in options_data.items():
            if not isinstance(strike_data, dict):
                continue

            try:
                strike_float = float(strike_key)
            except (ValueError, TypeError):
                self.logger.warning(f"Invalid strike key: {strike_key}")
                continue

            # Validate calls and puts for this strike
            for option_type in ['call', 'put']:
                if option_type not in strike_data:
                    continue

                option_data = strike_data[option_type]
                if not isinstance(option_data, dict):
                    continue

                # Perform validation for this specific option
                strike_result = self._validate_single_option(
                    strike_float, option_type, option_data, spot_price
                )

                # Store result
                key = (strike_float, option_type)
                report.strike_results[key] = strike_result

                # Update summary statistics
                report.total_strikes += 1
                report.strikes_by_type[option_type] = report.strikes_by_type.get(option_type, 0) + 1

                # Categorize by quality level
                self._categorize_strike_by_quality(report, key, strike_result)

                # Collect issues
                report.all_issues.extend(strike_result.issues)
                for issue in strike_result.issues:
                    if issue.severity == ValidationSeverity.CRITICAL:
                        report.critical_issues.append(issue)
                    elif issue.severity == ValidationSeverity.HIGH:
                        report.high_priority_issues.append(issue)

        # Calculate overall scores and recommendations
        self._calculate_overall_scores(report)
        self._generate_recommendations(report)

        self.logger.info(f"Validation complete. Overall quality score: {report.combined_quality_score:.3f}")

        return report

    def _validate_single_option(self,
                               strike: float,
                               option_type: str,
                               option_data: Dict[str, Any],
                               spot_price: Optional[float] = None) -> StrikeValidationResult:
        """Validate a single option (call or put) at a specific strike."""

        result = StrikeValidationResult(
            strike=strike,
            option_type=option_type,
            pricing_metrics=StrikePricingMetrics(),
            greeks_metrics=GreeksCompletenessMetrics(),
            liquidity_metrics=LiquidityMetrics()
        )

        # Category 1: Strike Pricing Validation
        self._validate_strike_pricing(option_data, result)

        # Category 2: Greeks Completeness Validation
        self._validate_greeks_completeness(option_data, result, option_type)

        # Category 3: Liquidity Indicators Validation
        self._validate_liquidity_indicators(option_data, result)

        # Calculate overall scores
        self._calculate_strike_scores(result)

        # Determine quality level and processing flags
        self._determine_strike_quality_level(result)

        return result

    def _validate_strike_pricing(self, option_data: Dict[str, Any], result: StrikeValidationResult):
        """Validate strike pricing completeness and quality (Category 1)."""
        pricing = result.pricing_metrics
        issues = []

        # Check for required pricing fields
        pricing_fields = {
            'bid': ('bid_price', 'bid'),
            'ask': ('ask_price', 'ask'),
            'last': ('last_price', 'last', 'market_price'),
            'model_price': ('model_price', 'theoretical_price', 'calculated_price')
        }

        for field_name, possible_keys in pricing_fields.items():
            value = None
            found_key = None

            # Try to find the value under different possible keys
            for key in possible_keys:
                if key in option_data and option_data[key] is not None:
                    try:
                        value = float(option_data[key])
                        found_key = key
                        break
                    except (ValueError, TypeError):
                        continue

            # Set metrics based on field
            if field_name == 'bid':
                pricing.has_bid = value is not None and value >= 0
                pricing.bid_value = value
                if not pricing.has_bid and value is not None:
                    issues.append(ValidationIssue(
                        category=ValidationCategory.STRIKE_PRICING,
                        severity=ValidationSeverity.MEDIUM,
                        strike=result.strike,
                        option_type=result.option_type,
                        field='bid_price',
                        issue_description="Negative bid price detected",
                        current_value=value,
                        expected_range=(0, None),
                        recommendation="Verify bid price data source"
                    ))

            elif field_name == 'ask':
                pricing.has_ask = value is not None and value > 0
                pricing.ask_value = value
                if not pricing.has_ask and value is not None:
                    issues.append(ValidationIssue(
                        category=ValidationCategory.STRIKE_PRICING,
                        severity=ValidationSeverity.MEDIUM,
                        strike=result.strike,
                        option_type=result.option_type,
                        field='ask_price',
                        issue_description="Invalid ask price (must be > 0)",
                        current_value=value,
                        expected_range=(0.01, None),
                        recommendation="Verify ask price data source"
                    ))

            elif field_name == 'last':
                pricing.has_last = value is not None and value >= 0
                pricing.last_value = value

            elif field_name == 'model_price':
                pricing.has_model_price = value is not None and value >= 0
                pricing.model_price_value = value

            # Add missing field issue
            if value is None:
                severity = ValidationSeverity.HIGH if field_name in ['bid', 'ask'] else ValidationSeverity.MEDIUM
                issues.append(ValidationIssue(
                    category=ValidationCategory.STRIKE_PRICING,
                    severity=severity,
                    strike=result.strike,
                    option_type=result.option_type,
                    field=f'{field_name}_price',
                    issue_description=f"Missing {field_name} price",
                    current_value=None,
                    expected_range=None,
                    recommendation=f"Obtain {field_name} price from data provider"
                ))

        # Calculate bid-ask spread if both available
        if pricing.has_bid and pricing.has_ask and pricing.bid_value is not None and pricing.ask_value is not None:
            pricing.bid_ask_spread = pricing.ask_value - pricing.bid_value
            if pricing.ask_value > 0:
                pricing.bid_ask_spread_pct = (pricing.bid_ask_spread / pricing.ask_value) * 100

                # Check spread threshold (25% as specified in task)
                if pricing.bid_ask_spread_pct > self.pricing_thresholds['max_bid_ask_spread_pct']:
                    issues.append(ValidationIssue(
                        category=ValidationCategory.STRIKE_PRICING,
                        severity=ValidationSeverity.HIGH,
                        strike=result.strike,
                        option_type=result.option_type,
                        field='bid_ask_spread',
                        issue_description=f"Wide bid-ask spread: {pricing.bid_ask_spread_pct:.1f}%",
                        current_value=pricing.bid_ask_spread_pct,
                        expected_range=(0, self.pricing_thresholds['max_bid_ask_spread_pct']),
                        recommendation="Consider using more liquid options or proceed with caution"
                    ))

        # Calculate pricing scores
        completeness_count = sum([pricing.has_bid, pricing.has_ask, pricing.has_last, pricing.has_model_price])
        pricing.pricing_completeness_score = completeness_count / 4.0

        # Quality score considers spread and reasonableness
        quality_factors = []

        if pricing.pricing_completeness_score >= 0.75:  # At least 3 of 4 fields
            quality_factors.append(0.4)
        elif pricing.pricing_completeness_score >= 0.5:  # At least 2 of 4 fields
            quality_factors.append(0.2)

        if pricing.bid_ask_spread_pct is not None:
            if pricing.bid_ask_spread_pct <= 5:
                quality_factors.append(0.3)  # Excellent spread
            elif pricing.bid_ask_spread_pct <= 15:
                quality_factors.append(0.2)  # Good spread
            elif pricing.bid_ask_spread_pct <= 25:
                quality_factors.append(0.1)  # Acceptable spread (task threshold)

        # Reasonable price levels
        reasonable_prices = [p for p in [pricing.bid_value, pricing.ask_value, pricing.last_value]
                           if p is not None and self.pricing_thresholds['min_reasonable_price'] <= p <= self.pricing_thresholds['max_reasonable_price']]
        if reasonable_prices:
            quality_factors.append(0.3)

        pricing.pricing_quality_score = sum(quality_factors)

        # Add issues to result
        result.issues.extend(issues)

    def _validate_greeks_completeness(self, option_data: Dict[str, Any], result: StrikeValidationResult, option_type: str):
        """Validate Greeks completeness and validity (Category 2)."""
        greeks = result.greeks_metrics
        issues = []

        # Required Greeks as specified in task
        required_greeks = ['delta', 'gamma', 'theta', 'vega', 'rho']

        for greek_name in required_greeks:
            value = option_data.get(greek_name)

            # Check if Greek is present and valid
            has_greek = value is not None
            valid_greek = False

            if has_greek:
                try:
                    float_value = float(value)
                    if not (math.isnan(float_value) or math.isinf(float_value)):
                        # Check if within theoretical bounds
                        bounds = self.greeks_bounds.get(greek_name, {}).get(option_type, (-float('inf'), float('inf')))
                        if bounds[0] <= float_value <= bounds[1]:
                            valid_greek = True
                        else:
                            issues.append(ValidationIssue(
                                category=ValidationCategory.GREEKS_COMPLETENESS,
                                severity=ValidationSeverity.MEDIUM,
                                strike=result.strike,
                                option_type=result.option_type,
                                field=greek_name,
                                issue_description=f"{greek_name.title()} value outside theoretical bounds: {float_value}",
                                current_value=float_value,
                                expected_range=bounds,
                                recommendation=f"Verify {greek_name} calculation methodology"
                            ))
                    else:
                        issues.append(ValidationIssue(
                            category=ValidationCategory.GREEKS_COMPLETENESS,
                            severity=ValidationSeverity.HIGH,
                            strike=result.strike,
                            option_type=result.option_type,
                            field=greek_name,
                            issue_description=f"{greek_name.title()} contains NaN or infinite value",
                            current_value=str(value),
                            expected_range=None,
                            recommendation=f"Recalculate {greek_name} with valid inputs"
                        ))
                except (ValueError, TypeError):
                    issues.append(ValidationIssue(
                        category=ValidationCategory.GREEKS_COMPLETENESS,
                        severity=ValidationSeverity.HIGH,
                        strike=result.strike,
                        option_type=result.option_type,
                        field=greek_name,
                        issue_description=f"{greek_name.title()} is not a valid number: {value}",
                        current_value=value,
                        expected_range=None,
                        recommendation=f"Ensure {greek_name} is properly calculated as numeric value"
                    ))
            else:
                issues.append(ValidationIssue(
                    category=ValidationCategory.GREEKS_COMPLETENESS,
                    severity=ValidationSeverity.CRITICAL,
                    strike=result.strike,
                    option_type=result.option_type,
                    field=greek_name,
                    issue_description=f"Missing {greek_name.title()} value",
                    current_value=None,
                    expected_range=None,
                    recommendation=f"Calculate {greek_name} using binomial or analytical method"
                ))

            # Set metrics
            setattr(greeks, f'has_{greek_name}', has_greek)
            setattr(greeks, f'{greek_name}_valid', valid_greek)
            setattr(greeks, f'{greek_name}_value', value if has_greek else None)

        # Calculate completeness and validity scores
        completeness_count = sum([getattr(greeks, f'has_{greek}') for greek in required_greeks])
        validity_count = sum([getattr(greeks, f'{greek}_valid') for greek in required_greeks])

        greeks.greeks_completeness_score = completeness_count / len(required_greeks)
        greeks.greeks_validity_score = validity_count / len(required_greeks) if completeness_count > 0 else 0.0

        result.issues.extend(issues)

    def _validate_liquidity_indicators(self, option_data: Dict[str, Any], result: StrikeValidationResult):
        """Validate liquidity indicators (Category 3)."""
        liquidity = result.liquidity_metrics
        issues = []

        # Volume validation (≥10 as specified in task)
        volume = option_data.get('volume')
        if volume is not None:
            try:
                volume_float = float(volume)
                liquidity.volume = volume_float
                liquidity.volume_meets_threshold = volume_float >= self.liquidity_thresholds['min_volume']

                if not liquidity.volume_meets_threshold:
                    issues.append(ValidationIssue(
                        category=ValidationCategory.LIQUIDITY_INDICATORS,
                        severity=ValidationSeverity.MEDIUM,
                        strike=result.strike,
                        option_type=result.option_type,
                        field='volume',
                        issue_description=f"Low volume: {volume_float}",
                        current_value=volume_float,
                        expected_range=(self.liquidity_thresholds['min_volume'], None),
                        recommendation="Consider more liquid alternatives"
                    ))
            except (ValueError, TypeError):
                issues.append(ValidationIssue(
                    category=ValidationCategory.LIQUIDITY_INDICATORS,
                    severity=ValidationSeverity.HIGH,
                    strike=result.strike,
                    option_type=result.option_type,
                    field='volume',
                    issue_description=f"Invalid volume value: {volume}",
                    current_value=volume,
                    expected_range=None,
                    recommendation="Verify volume data source"
                ))
        else:
            issues.append(ValidationIssue(
                category=ValidationCategory.LIQUIDITY_INDICATORS,
                severity=ValidationSeverity.MEDIUM,
                strike=result.strike,
                option_type=result.option_type,
                field='volume',
                issue_description="Missing volume data",
                current_value=None,
                expected_range=None,
                recommendation="Obtain volume data from data provider"
            ))

        # Open Interest validation (≥100 as specified in task)
        open_interest = option_data.get('open_interest', option_data.get('openInterest'))
        if open_interest is not None:
            try:
                oi_float = float(open_interest)
                liquidity.open_interest = oi_float
                liquidity.oi_meets_threshold = oi_float >= self.liquidity_thresholds['min_open_interest']

                if not liquidity.oi_meets_threshold:
                    issues.append(ValidationIssue(
                        category=ValidationCategory.LIQUIDITY_INDICATORS,
                        severity=ValidationSeverity.MEDIUM,
                        strike=result.strike,
                        option_type=result.option_type,
                        field='open_interest',
                        issue_description=f"Low open interest: {oi_float}",
                        current_value=oi_float,
                        expected_range=(self.liquidity_thresholds['min_open_interest'], None),
                        recommendation="Consider strikes with higher open interest"
                    ))
            except (ValueError, TypeError):
                issues.append(ValidationIssue(
                    category=ValidationCategory.LIQUIDITY_INDICATORS,
                    severity=ValidationSeverity.HIGH,
                    strike=result.strike,
                    option_type=result.option_type,
                    field='open_interest',
                    issue_description=f"Invalid open interest value: {open_interest}",
                    current_value=open_interest,
                    expected_range=None,
                    recommendation="Verify open interest data source"
                ))
        else:
            issues.append(ValidationIssue(
                category=ValidationCategory.LIQUIDITY_INDICATORS,
                severity=ValidationSeverity.MEDIUM,
                strike=result.strike,
                option_type=result.option_type,
                field='open_interest',
                issue_description="Missing open interest data",
                current_value=None,
                expected_range=None,
                recommendation="Obtain open interest data from data provider"
            ))

        # Bid-ask spread validation (<25% of ask as specified in task)
        # Note: This overlaps with pricing validation but is specifically a liquidity indicator
        if result.pricing_metrics.bid_ask_spread_pct is not None:
            liquidity.bid_ask_spread_pct = result.pricing_metrics.bid_ask_spread_pct
            liquidity.spread_meets_threshold = liquidity.bid_ask_spread_pct < self.liquidity_thresholds['max_spread_pct']

            if not liquidity.spread_meets_threshold:
                issues.append(ValidationIssue(
                    category=ValidationCategory.LIQUIDITY_INDICATORS,
                    severity=ValidationSeverity.HIGH,
                    strike=result.strike,
                    option_type=result.option_type,
                    field='bid_ask_spread',
                    issue_description=f"Wide spread indicates poor liquidity: {liquidity.bid_ask_spread_pct:.1f}%",
                    current_value=liquidity.bid_ask_spread_pct,
                    expected_range=(0, self.liquidity_thresholds['max_spread_pct']),
                    recommendation="Seek more liquid strikes or proceed with extreme caution"
                ))

        # Calculate liquidity scores
        # Volume score
        if liquidity.volume is not None:
            if liquidity.volume >= 100:  # Excellent volume
                liquidity.volume_score = 1.0
            elif liquidity.volume >= 50:  # Good volume
                liquidity.volume_score = 0.8
            elif liquidity.volume >= 10:  # Acceptable volume (task threshold)
                liquidity.volume_score = 0.5
            else:  # Poor volume
                liquidity.volume_score = 0.2

        # Open interest score
        if liquidity.open_interest is not None:
            if liquidity.open_interest >= 1000:  # Excellent OI
                liquidity.oi_score = 1.0
            elif liquidity.open_interest >= 500:  # Good OI
                liquidity.oi_score = 0.8
            elif liquidity.open_interest >= 100:  # Acceptable OI (task threshold)
                liquidity.oi_score = 0.5
            else:  # Poor OI
                liquidity.oi_score = 0.2

        # Spread score
        if liquidity.bid_ask_spread_pct is not None:
            if liquidity.bid_ask_spread_pct <= 5:  # Excellent spread
                liquidity.spread_score = 1.0
            elif liquidity.bid_ask_spread_pct <= 15:  # Good spread
                liquidity.spread_score = 0.8
            elif liquidity.bid_ask_spread_pct < 25:  # Acceptable spread (task threshold)
                liquidity.spread_score = 0.5
            else:  # Poor spread
                liquidity.spread_score = 0.2

        # Combined liquidity score
        scores = [s for s in [liquidity.volume_score, liquidity.oi_score, liquidity.spread_score] if s > 0]
        liquidity.liquidity_score = sum(scores) / len(scores) if scores else 0.0

        result.issues.extend(issues)

    def _calculate_strike_scores(self, result: StrikeValidationResult):
        """Calculate overall scores for a single strike."""
        # Category scores
        result.category_scores = {
            ValidationCategory.STRIKE_PRICING: result.pricing_metrics.pricing_quality_score,
            ValidationCategory.GREEKS_COMPLETENESS: (
                result.greeks_metrics.greeks_completeness_score * 0.6 +
                result.greeks_metrics.greeks_validity_score * 0.4
            ),
            ValidationCategory.LIQUIDITY_INDICATORS: result.liquidity_metrics.liquidity_score
        }

        # Overall quality score (weighted combination)
        result.overall_quality_score = sum(
            score * self.category_weights[category]
            for category, score in result.category_scores.items()
        )

    def _determine_strike_quality_level(self, result: StrikeValidationResult):
        """Determine quality level and processing flags for a strike."""
        score = result.overall_quality_score
        critical_issues = sum(1 for issue in result.issues if issue.severity == ValidationSeverity.CRITICAL)

        # Quality level determination
        if score >= 0.85 and critical_issues == 0:
            result.quality_level = QualityLevel.EXCELLENT
        elif score >= 0.70 and critical_issues == 0:
            result.quality_level = QualityLevel.GOOD
        elif score >= 0.50 and critical_issues <= 1:
            result.quality_level = QualityLevel.ACCEPTABLE
        elif score >= 0.30:
            result.quality_level = QualityLevel.POOR
        else:
            result.quality_level = QualityLevel.FAILED

        # Processing flags
        result.passes_validation = result.quality_level in [QualityLevel.EXCELLENT, QualityLevel.GOOD]
        result.requires_repair = result.quality_level in [QualityLevel.ACCEPTABLE, QualityLevel.POOR]
        result.can_proceed_with_caution = result.quality_level in [QualityLevel.ACCEPTABLE, QualityLevel.POOR] and critical_issues == 0

    def _categorize_strike_by_quality(self, report: CoreValidationReport, key: Tuple[float, str], result: StrikeValidationResult):
        """Categorize strike by quality level for report summary."""
        if result.quality_level == QualityLevel.EXCELLENT:
            report.excellent_strikes.append(key)
        elif result.quality_level == QualityLevel.GOOD:
            report.good_strikes.append(key)
        elif result.quality_level == QualityLevel.ACCEPTABLE:
            report.acceptable_strikes.append(key)
        elif result.quality_level == QualityLevel.POOR:
            report.poor_strikes.append(key)
        else:
            report.failed_strikes.append(key)

    def _calculate_overall_scores(self, report: CoreValidationReport):
        """Calculate overall scores across all strikes."""
        if not report.strike_results:
            return

        results = list(report.strike_results.values())

        # Category averages
        report.overall_pricing_score = np.mean([
            r.category_scores.get(ValidationCategory.STRIKE_PRICING, 0) for r in results
        ])

        report.overall_greeks_score = np.mean([
            r.category_scores.get(ValidationCategory.GREEKS_COMPLETENESS, 0) for r in results
        ])

        report.overall_liquidity_score = np.mean([
            r.category_scores.get(ValidationCategory.LIQUIDITY_INDICATORS, 0) for r in results
        ])

        # Combined score
        report.combined_quality_score = np.mean([r.overall_quality_score for r in results])

    def _generate_recommendations(self, report: CoreValidationReport):
        """Generate processing recommendations based on validation results."""
        score = report.combined_quality_score
        excellent_pct = len(report.excellent_strikes) / max(1, report.total_strikes) * 100
        good_pct = len(report.good_strikes) / max(1, report.total_strikes) * 100
        acceptable_pct = len(report.acceptable_strikes) / max(1, report.total_strikes) * 100
        critical_count = len(report.critical_issues)

        # Overall recommendation
        if score >= 0.8 and critical_count == 0:
            report.overall_recommendation = f"PROCEED: High quality data ({score:.1%} overall). {excellent_pct:.0f}% excellent strikes. All critical validation categories met."

        elif score >= 0.65 and critical_count <= 2:
            report.overall_recommendation = f"PROCEED WITH MONITORING: Good quality data ({score:.1%} overall). {good_pct + excellent_pct:.0f}% good/excellent strikes. Monitor {critical_count} critical issues."

        elif score >= 0.45 and critical_count <= 5:
            report.overall_recommendation = f"PROCEED WITH CAUTION: Acceptable quality after validation ({score:.1%} overall). Focus on {excellent_pct + good_pct + acceptable_pct:.0f}% usable strikes. Address {critical_count} critical issues."

        else:
            report.overall_recommendation = f"REVIEW REQUIRED: Low quality data ({score:.1%} overall, {critical_count} critical issues). Consider alternative expiration dates or data sources."

        # Processing decision
        can_proceed = score >= 0.45 and critical_count <= 10
        processing_mode = "full_analysis" if score >= 0.7 else "reduced_analysis" if score >= 0.5 else "basic_analysis" if can_proceed else "reject"

        report.processing_decision = {
            "can_proceed": can_proceed,
            "processing_mode": processing_mode,
            "confidence_level": "high" if score >= 0.7 else "medium" if score >= 0.5 else "low",
            "focus_strikes": {
                "excellent": report.excellent_strikes,
                "good": report.good_strikes,
                "acceptable": report.acceptable_strikes if score < 0.7 else []
            },
            "avoid_strikes": report.failed_strikes + (report.poor_strikes if score >= 0.6 else []),
            "data_repair_recommended": len(report.acceptable_strikes) + len(report.poor_strikes) > 0,
            "alternative_sources_recommended": critical_count > 5 or score < 0.4
        }


# Global instance for easy access
default_core_validator = CoreValidationEngine()