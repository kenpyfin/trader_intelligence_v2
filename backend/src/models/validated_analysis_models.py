"""
Enhanced Analysis Models with Validation Support

This module provides Pydantic models for the validated analysis system,
supporting validation parameters, strategy-specific requests, and
comprehensive validation reporting.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

from pydantic import BaseModel, Field
from datetime import date
from typing import List, Optional, Dict, Any, Union
from enum import Enum


class ValidationMode(str, Enum):
    """Validation strictness modes."""
    STRICT = "strict"
    STANDARD = "standard"
    PERMISSIVE = "permissive"


class TradingStrategyName(str, Enum):
    """Supported trading strategy names for validation."""
    COVERED_CALL = "covered_call"
    PROTECTIVE_PUT = "protective_put"
    CASH_SECURED_PUT = "cash_secured_put"
    LONG_CALL = "long_call"
    LONG_PUT = "long_put"
    BULL_CALL_SPREAD = "bull_call_spread"
    BEAR_PUT_SPREAD = "bear_put_spread"
    IRON_CONDOR = "iron_condor"
    BUTTERFLY_SPREAD = "butterfly_spread"
    CALENDAR_SPREAD = "calendar_spread"
    LONG_STRADDLE = "long_straddle"
    LONG_STRANGLE = "long_strangle"
    SHORT_STRADDLE = "short_straddle"
    SHORT_STRANGLE = "short_strangle"
    RATIO_SPREAD = "ratio_spread"
    SYNTHETIC_POSITIONS = "synthetic_positions"
    DELTA_NEUTRAL = "delta_neutral"


class ValidatedAnalysisRequest(BaseModel):
    """Request model for validated analysis with enhanced validation parameters."""

    # Base analysis parameters
    ticker: str = Field(..., description="Stock ticker symbol")
    expiration_date: str = Field(..., description="Option expiration date in YYYYMMDD format")
    risk_free_rate: float = Field(0.045, description="Risk-free interest rate")
    analysis_method: str = Field('holistic-market-edge', description="Analysis methodology")
    gpt_model: str = Field('gemini-2.5-flash', description="Model for verdict generation")
    override_price: Optional[float] = Field(None, description="Manual price override for testing")

    # Validation parameters
    validation_mode: ValidationMode = Field(ValidationMode.STANDARD, description="Validation strictness mode")
    min_quality_threshold: float = Field(0.5, ge=0.0, le=1.0, description="Minimum quality score threshold")
    enable_cross_source_validation: bool = Field(True, description="Enable cross-source validation")

    # Strategy-specific validation
    target_strategies: Optional[List[TradingStrategyName]] = Field(
        None, description="Specific strategies to validate against"
    )
    require_strategy_approval: bool = Field(False, description="Require at least one strategy to pass validation")

    # Advanced validation options
    custom_quality_thresholds: Optional[Dict[str, float]] = Field(
        None, description="Custom quality thresholds for specific validation categories"
    )
    validation_timeout_seconds: Optional[int] = Field(
        60, description="Maximum time allowed for validation process"
    )


class StrategyValidationRequest(BaseModel):
    """Request model for strategy-specific validation."""

    ticker: str = Field(..., description="Stock ticker symbol")
    expiration_date: str = Field(..., description="Option expiration date in YYYYMMDD format")
    strategies: List[TradingStrategyName] = Field(..., description="Strategies to validate")

    # Optional analysis parameters
    risk_free_rate: float = Field(0.045, description="Risk-free interest rate")
    override_price: Optional[float] = Field(None, description="Manual price override")

    # Validation options
    validation_mode: ValidationMode = Field(ValidationMode.STANDARD, description="Validation mode")


class DataQualityCheckRequest(BaseModel):
    """Request model for standalone data quality checking."""

    ticker: str = Field(..., description="Stock ticker symbol")
    expiration_date: str = Field(..., description="Option expiration date in YYYYMMDD format")

    # Quality assessment parameters
    include_cross_source_validation: bool = Field(True, description="Include cross-source validation")
    include_strategy_assessment: bool = Field(False, description="Include strategy suitability assessment")
    detailed_reporting: bool = Field(True, description="Include detailed quality breakdown")


class ValidationSummary(BaseModel):
    """Summary of validation results."""

    overall_validation_status: str = Field(..., description="Overall validation status")
    validation_mode_used: str = Field(..., description="Validation mode that was used")
    quality_threshold_used: float = Field(..., description="Quality threshold that was applied")

    data_quality_assessment: Dict[str, Any] = Field(
        default_factory=dict, description="Detailed data quality metrics"
    )
    validation_highlights: List[str] = Field(
        default_factory=list, description="Key validation highlights"
    )
    quality_improvement_potential: str = Field(
        "", description="Assessment of improvement potential"
    )
    data_reliability_assessment: str = Field(
        "", description="Overall data reliability assessment"
    )


class StrategyValidationResult(BaseModel):
    """Result of strategy-specific validation."""

    strategy: str = Field(..., description="Strategy name")
    gate_decision: str = Field(..., description="Gate decision (APPROVE, APPROVE_WITH_CAUTION, REJECT)")
    decision_confidence: float = Field(..., description="Confidence in the decision (0.0-1.0)")

    quality_metrics: Dict[str, float] = Field(
        default_factory=dict, description="Quality metrics for this strategy"
    )
    recommended_position_size_factor: float = Field(
        0.0, description="Recommended position size multiplier"
    )

    approval_conditions: List[str] = Field(
        default_factory=list, description="Conditions for approval"
    )
    risk_warnings: List[str] = Field(
        default_factory=list, description="Risk warnings specific to this strategy"
    )
    improvement_recommendations: List[str] = Field(
        default_factory=list, description="Recommendations for improving validation"
    )


class CrossSourceValidationResult(BaseModel):
    """Result of cross-source validation."""

    status: str = Field(..., description="Validation status")
    finviz_data_available: bool = Field(False, description="Whether Finviz data was available")
    calculated_data_available: bool = Field(False, description="Whether calculated data was available")

    agreement_score: Optional[float] = Field(None, description="Agreement score between sources")
    recommended_source: Optional[str] = Field(None, description="Recommended data source to use")

    source_quality_comparison: Dict[str, Any] = Field(
        default_factory=dict, description="Quality comparison between sources"
    )
    data_source_recommendations: List[str] = Field(
        default_factory=list, description="Specific recommendations for data source usage"
    )


class ValidatedAnalysisResponse(BaseModel):
    """Response model for validated analysis."""

    status: str = Field(..., description="Analysis status")
    validation_status: str = Field(..., description="Validation status")

    # Core analysis results
    analysis_results: Dict[str, Any] = Field(
        default_factory=dict, description="Core analysis results"
    )

    # Validation results
    validation_report: Dict[str, Any] = Field(
        default_factory=dict, description="Comprehensive validation report"
    )
    quality_metrics: Dict[str, Any] = Field(
        default_factory=dict, description="Quality metrics"
    )

    # Strategy validation (if requested)
    strategy_validation: Optional[Dict[str, Any]] = Field(
        None, description="Strategy-specific validation results"
    )
    filtered_strategies: Optional[Dict[str, Any]] = Field(
        None, description="Filtered strategy recommendations"
    )

    # Cross-source validation (if enabled)
    cross_source_validation: Optional[CrossSourceValidationResult] = Field(
        None, description="Cross-source validation results"
    )

    # Enhanced recommendations
    validation_enhanced_recommendations: List[str] = Field(
        default_factory=list, description="Enhanced recommendations based on validation"
    )
    validation_summary: ValidationSummary = Field(
        ..., description="Comprehensive validation summary"
    )

    # Processing information
    processing_time_seconds: Optional[float] = Field(
        None, description="Total processing time"
    )
    data_sources_used: List[str] = Field(
        default_factory=list, description="Data sources that were used"
    )


class DataQualityReport(BaseModel):
    """Standalone data quality report."""

    ticker: str = Field(..., description="Stock ticker")
    expiration_date: str = Field(..., description="Expiration date")
    assessment_timestamp: str = Field(..., description="When the assessment was performed")

    overall_quality_score: float = Field(..., description="Overall quality score (0.0-1.0)")
    category_scores: Dict[str, float] = Field(
        default_factory=dict, description="Scores by validation category"
    )

    quality_level: str = Field(..., description="Quality level (excellent, good, acceptable, poor, failed)")

    strikes_analysis: Dict[str, Any] = Field(
        default_factory=dict, description="Analysis of strikes by quality"
    )
    issues_summary: Dict[str, Any] = Field(
        default_factory=dict, description="Summary of data quality issues"
    )

    recommendations: List[str] = Field(
        default_factory=list, description="Recommendations for improvement"
    )

    # Cross-source validation results if performed
    cross_source_results: Optional[CrossSourceValidationResult] = Field(
        None, description="Cross-source validation results"
    )


class StrategyRecommendationFilter(BaseModel):
    """Filter for strategy recommendations based on validation."""

    min_approval_confidence: float = Field(0.7, description="Minimum confidence for recommendations")
    allow_conditional_strategies: bool = Field(True, description="Allow conditionally approved strategies")
    max_risk_warnings: int = Field(3, description="Maximum acceptable risk warnings")

    preferred_position_size_factor: float = Field(
        0.5, description="Minimum position size factor for recommendations"
    )


class ValidationConfiguration(BaseModel):
    """Configuration for validation behavior."""

    # Default validation parameters
    default_validation_mode: ValidationMode = Field(ValidationMode.STANDARD)
    default_min_quality_threshold: float = Field(0.5)

    # Cross-source validation settings
    enable_cross_source_by_default: bool = Field(True)
    cross_source_timeout_seconds: int = Field(30)

    # Strategy validation settings
    strategy_validation_timeout_seconds: int = Field(45)
    require_minimum_excellent_strikes: int = Field(1)

    # Quality thresholds by asset type
    high_liquidity_min_quality: float = Field(0.4)
    medium_liquidity_min_quality: float = Field(0.5)
    low_liquidity_min_quality: float = Field(0.6)

    # Advanced settings
    enable_validation_caching: bool = Field(True)
    validation_cache_ttl_minutes: int = Field(15)


# Error models for validation failures
class ValidationError(BaseModel):
    """Validation error details."""

    error_type: str = Field(..., description="Type of validation error")
    error_message: str = Field(..., description="Human-readable error message")
    affected_component: Optional[str] = Field(None, description="Component that failed validation")
    suggested_actions: List[str] = Field(default_factory=list, description="Suggested corrective actions")


class ValidationFailureResponse(BaseModel):
    """Response for validation failures."""

    status: str = Field("validation_failed", description="Status indicating validation failure")
    error_details: ValidationError = Field(..., description="Detailed error information")

    # Partial results if available
    partial_quality_assessment: Optional[Dict[str, Any]] = Field(
        None, description="Partial quality assessment if available"
    )
    alternative_recommendations: List[str] = Field(
        default_factory=list, description="Alternative approaches to consider"
    )

    # Retry suggestions
    retry_suggestions: List[str] = Field(
        default_factory=list, description="Suggestions for retry attempts"
    )