from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import List, Optional, Dict, Any, Union
from enum import Enum


# Core request models (backward compatible)
class AnalysisRequest(BaseModel):
    ticker: str
    expiration_date: str  # Expects YYYYMMDD format
    risk_free_rate: float = 0.045  # Default value if not provided
    analysis_method: str = 'holistic-market-edge'
    gpt_model: str = 'gemini-2.5-flash'  # Model to use for verdict analysis
    override_price: Optional[float] = None  # Manual price override for testing/debugging
    caution_mode: bool = False  # Manual override for quality gate


class RiskFreeRateRequest(BaseModel):
    tickers: List[str]
    expiration_date: Optional[str] = None  # Optional for backward compatibility


class SaveVerdictRequest(BaseModel):
    """Payload to save an analysis verdict snapshot for later comparison."""
    verdict: Dict[str, Any]
    label: Optional[str] = None


class ConflictResolveRequest(BaseModel):
    """Payload to reconcile multiple saved verdicts for one ticker."""
    ticker: str
    verdict_ids: List[str]
    model: str = 'gemini-2.5-flash'


# Validation-related enums and models
class ValidationStatus(str, Enum):
    """Status of validation process."""
    COMPLETED = "completed"
    PASSED = "passed"
    FAILED = "failed"
    DISABLED = "disabled"
    ERROR = "error"


class ValidationMode(str, Enum):
    """Validation strictness modes."""
    STRICT = "strict"
    STANDARD = "standard"
    PERMISSIVE = "permissive"


class QualityLevel(str, Enum):
    """Data quality level classifications."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    VERY_POOR = "very_poor"


class AnalysisRecommendation(str, Enum):
    """Analysis recommendations based on data quality."""
    PROCEED = "PROCEED"
    PROCEED_WITH_CAUTION = "PROCEED_WITH_CAUTION"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


# Validation metadata models
class ValidationMetadata(BaseModel):
    """Validation metadata included in analysis responses."""
    validation_enabled: bool = Field(..., description="Whether validation was enabled")
    validation_mode: Optional[ValidationMode] = Field(None, description="Validation mode used")
    validation_status: ValidationStatus = Field(..., description="Status of validation process")
    quality_metrics: Dict[str, Any] = Field(default_factory=dict, description="Quality metrics")
    data_quality_insights: Dict[str, Any] = Field(default_factory=dict, description="Quality insights")
    validation_recommendations: List[str] = Field(default_factory=list, description="Validation-based recommendations")
    note: Optional[str] = Field(None, description="Additional notes about validation")


class QualityWarnings(BaseModel):
    """Quality warnings for moderate data quality."""
    overall_quality_score: float = Field(..., description="Overall quality score (0.0-1.0)")
    quality_level: str = Field(..., description="Human-readable quality level")
    warnings: List[str] = Field(default_factory=list, description="Specific warnings")
    recommended_actions: List[str] = Field(default_factory=list, description="Recommended actions")
    data_quality_concerns: Optional[List[str]] = Field(None, description="Top data quality concerns")
    data_quality_strengths: Optional[List[str]] = Field(None, description="Data quality strengths")


class DataAvailability(BaseModel):
    """Data availability summary."""
    total_option_contracts: int = Field(..., description="Total option contracts found")
    strikes_available: int = Field(..., description="Number of strikes available")
    calls_and_puts_available: int = Field(..., description="Strikes with both calls and puts")


class DataCompleteness(BaseModel):
    """Data completeness assessment."""
    completeness_ratio: float = Field(..., description="Completeness ratio (0.0-1.0)")
    complete_count: int = Field(..., description="Number of complete items")
    total_count: int = Field(..., description="Total number of items")
    required_greeks: Optional[List[str]] = Field(None, description="Required Greeks for completeness")


class DetailedAssessment(BaseModel):
    """Detailed data quality assessment."""
    category_scores: Dict[str, float] = Field(default_factory=dict, description="Scores by category")
    strikes_by_quality: Dict[str, int] = Field(default_factory=dict, description="Strike counts by quality level")
    critical_issues: int = Field(0, description="Number of critical issues")
    high_priority_issues: int = Field(0, description="Number of high priority issues")
    data_completeness: Dict[str, DataCompleteness] = Field(default_factory=dict, description="Completeness by category")


class AnalysisRecommendationDetail(BaseModel):
    """Detailed analysis recommendation."""
    recommendation: AnalysisRecommendation = Field(..., description="Primary recommendation")
    confidence: str = Field(..., description="Confidence level (HIGH, MEDIUM, LOW, VERY_LOW)")
    message: str = Field(..., description="Human-readable message")


# Response models
class AnalysisResponse(BaseModel):
    """Standard analysis response with validation metadata."""
    # Core analysis results (flexible to accommodate existing structure)
    status: Optional[str] = Field(None, description="Analysis status")

    # Market context
    market_context: Optional[Dict[str, Any]] = Field(None, description="Market context data")

    # Options analysis
    options_positioning: Optional[Dict[str, Any]] = Field(None, description="Options positioning analysis")

    # GPT verdict
    gpt_verdict: Optional[Dict[str, Any]] = Field(None, description="GPT-generated verdict")

    # Validation metadata (new)
    validation_metadata: ValidationMetadata = Field(..., description="Validation metadata")

    # Quality warnings (conditional)
    quality_warnings: Optional[QualityWarnings] = Field(None, description="Quality warnings if applicable")

    # Processing information
    processing_time_seconds: Optional[float] = Field(None, description="Processing time in seconds")

    # Additional fields for extensibility
    additional_data: Optional[Dict[str, Any]] = Field(None, description="Additional analysis data")


class DataQualityCheckResponse(BaseModel):
    """Response for data quality check endpoint."""
    status: str = Field(..., description="Check status")
    ticker: str = Field(..., description="Stock ticker")
    expiration_date: str = Field(..., description="Expiration date")
    assessment_timestamp: str = Field(..., description="Assessment timestamp")

    overall_quality_score: float = Field(..., description="Overall quality score (0.0-1.0)")
    quality_level: str = Field(..., description="Quality level description")
    analysis_recommendation: AnalysisRecommendationDetail = Field(..., description="Analysis recommendation")

    data_availability: DataAvailability = Field(..., description="Data availability summary")
    detailed_assessment: Optional[DetailedAssessment] = Field(None, description="Detailed assessment")
    recommendations: Optional[List[str]] = Field(None, description="Improvement recommendations")


# Error response models
class QualityAssessment(BaseModel):
    """Quality assessment details in error responses."""
    overall_score: float = Field(..., description="Overall quality score")
    threshold_used: float = Field(..., description="Quality threshold used")
    validation_mode: str = Field(..., description="Validation mode")
    asset_type: str = Field(..., description="Asset type classification")


class DataQualityIssues(BaseModel):
    """Summary of data quality issues."""
    critical_issues_count: int = Field(0, description="Number of critical issues")
    high_priority_issues_count: int = Field(0, description="Number of high priority issues")
    main_concerns: List[str] = Field(default_factory=list, description="Main concerns")
    affected_categories: List[Dict[str, Any]] = Field(default_factory=list, description="Affected categories")


class AlternativeApproach(BaseModel):
    """Alternative approach suggestion."""
    approach: str = Field(..., description="Approach name")
    reason: str = Field(..., description="Reason for this approach")
    example: str = Field(..., description="Example of how to implement")


class RetryInstructions(BaseModel):
    """Retry instructions for validation failures."""
    same_request_different_date: str = Field(..., description="Try different date instruction")
    lower_quality_threshold: str = Field(..., description="Lower threshold instruction")
    permissive_mode: str = Field(..., description="Permissive mode instruction")
    disable_validation: str = Field(..., description="Disable validation instruction")


class SpecificGuidance(BaseModel):
    """Specific guidance for validation failures."""
    issue: str = Field(..., description="Description of the issue")
    impact: str = Field(..., description="Impact of the issue")
    recommendation: str = Field(..., description="Specific recommendation")


class ValidationFailureResponse(BaseModel):
    """Response for validation failures."""
    status: str = Field("validation_failed", description="Status indicating validation failure")
    error_type: str = Field(..., description="Type of validation error")
    message: str = Field(..., description="Error message")
    ticker: str = Field(..., description="Stock ticker")
    expiration_date: str = Field(..., description="Expiration date")

    quality_assessment: QualityAssessment = Field(..., description="Quality assessment details")
    data_quality_issues: DataQualityIssues = Field(..., description="Data quality issues summary")
    improvement_recommendations: List[str] = Field(default_factory=list, description="Improvement recommendations")

    alternative_approaches: List[AlternativeApproach] = Field(default_factory=list, description="Alternative approaches")
    retry_instructions: RetryInstructions = Field(..., description="Retry instructions")
    specific_guidance: Optional[SpecificGuidance] = Field(None, description="Specific guidance")


class GeneralErrorResponse(BaseModel):
    """General error response with validation context."""
    status: str = Field("error", description="Error status")
    error_type: str = Field(..., description="Type of error")
    message: str = Field(..., description="Error message")
    ticker: str = Field(..., description="Stock ticker")
    expiration_date: str = Field(..., description="Expiration date")
    validation_enabled: bool = Field(..., description="Whether validation was enabled")

    recommendations: List[str] = Field(default_factory=list, description="General recommendations")
    retry_suggestions: Dict[str, str] = Field(default_factory=dict, description="Retry suggestions")


class NoDataResponse(BaseModel):
    """Response when no options data is available."""
    status: str = Field("no_data", description="No data status")
    ticker: str = Field(..., description="Stock ticker")
    expiration_date: str = Field(..., description="Expiration date")
    message: str = Field(..., description="No data message")
    suggestions: List[str] = Field(default_factory=list, description="Suggestions for user")


class QualityCheckErrorResponse(BaseModel):
    """Error response for quality check failures."""
    status: str = Field("error", description="Error status")
    ticker: str = Field(..., description="Stock ticker")
    expiration_date: str = Field(..., description="Expiration date")
    message: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Error type")


# Historical analysis models (extended)
class AnalysisHistoryEntry(BaseModel):
    """Extended analysis history entry with validation metadata."""
    id: Optional[str] = Field(None, description="Entry ID")
    ticker: str = Field(..., description="Stock ticker")
    expiration_date: str = Field(..., description="Expiration date")
    risk_free_rate: float = Field(..., description="Risk-free rate used")
    analysis_method: str = Field(..., description="Analysis method")
    gpt_model: str = Field(..., description="GPT model used")
    override_price: Optional[float] = Field(None, description="Override price")

    # Validation metadata (new)
    validation_enabled: bool = Field(False, description="Whether validation was enabled")
    validation_mode: Optional[str] = Field(None, description="Validation mode used")
    validation_status: Optional[str] = Field(None, description="Validation status")
    quality_score: Optional[float] = Field(None, description="Overall quality score")

    # Timestamps
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    analysis_results: Optional[Dict[str, Any]] = Field(None, description="Analysis results")


# Request models for new endpoints
class DataQualityCheckRequest(BaseModel):
    """Request for data quality check."""
    ticker: str = Field(..., description="Stock ticker symbol")
    expiration_date: str = Field(..., description="Expiration date in YYYYMMDD format")
    detailed: bool = Field(True, description="Include detailed quality breakdown")


class ValidationConfigRequest(BaseModel):
    """Request to configure validation settings."""
    validation_mode: ValidationMode = Field(ValidationMode.STANDARD, description="Validation mode")
    min_quality_threshold: float = Field(0.5, ge=0.0, le=1.0, description="Minimum quality threshold")
    enable_cross_source_validation: bool = Field(True, description="Enable cross-source validation")
    custom_thresholds: Optional[Dict[str, float]] = Field(None, description="Custom category thresholds")


# Union types for flexible responses
AnalysisAPIResponse = Union[
    AnalysisResponse,
    ValidationFailureResponse,
    GeneralErrorResponse,
    NoDataResponse
]

DataQualityAPIResponse = Union[
    DataQualityCheckResponse,
    NoDataResponse,
    QualityCheckErrorResponse
]
