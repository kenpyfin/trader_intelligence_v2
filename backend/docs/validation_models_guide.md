# Validation Models Guide

This guide explains the extended analysis models that support the new validation system, including validation status, quality scores, and detailed error reporting fields.

## Overview

The analysis models have been extended to support comprehensive data validation while maintaining backward compatibility. The new models provide:

- **Validation metadata** in all responses
- **Quality scores and warnings** for data quality assessment
- **Detailed error reporting** with actionable recommendations
- **Structured data quality information** for frontend clients

## Core Models

### Request Models

#### `AnalysisRequest` (Enhanced)
```python
class AnalysisRequest(BaseModel):
    ticker: str
    expiration_date: str  # YYYYMMDD format
    risk_free_rate: float = 0.045
    analysis_method: str = 'holistic-market-edge'
    gpt_model: str = 'gpt-5'
    override_price: Optional[float] = None
```

The `AnalysisRequest` remains fully backward compatible. Validation parameters are now passed as query parameters in the API endpoints.

#### `DataQualityCheckRequest` (New)
```python
class DataQualityCheckRequest(BaseModel):
    ticker: str
    expiration_date: str  # YYYYMMDD format
    detailed: bool = True
```

Used for the new `/check-data-quality/{ticker}` endpoint.

### Response Models

#### `AnalysisResponse` (New)
The main analysis response now includes validation metadata:

```python
class AnalysisResponse(BaseModel):
    # Core analysis results (backward compatible)
    status: Optional[str] = None
    market_context: Optional[Dict[str, Any]] = None
    options_positioning: Optional[Dict[str, Any]] = None
    gpt_verdict: Optional[Dict[str, Any]] = None

    # New validation fields
    validation_metadata: ValidationMetadata
    quality_warnings: Optional[QualityWarnings] = None
    processing_time_seconds: Optional[float] = None
```

#### `ValidationMetadata` (Core Validation Info)
```python
class ValidationMetadata(BaseModel):
    validation_enabled: bool
    validation_mode: Optional[ValidationMode] = None
    validation_status: ValidationStatus
    quality_metrics: Dict[str, Any] = {}
    data_quality_insights: Dict[str, Any] = {}
    validation_recommendations: List[str] = []
    note: Optional[str] = None
```

Example usage:
```json
{
  "validation_metadata": {
    "validation_enabled": true,
    "validation_mode": "standard",
    "validation_status": "completed",
    "quality_metrics": {
      "overall_score": 0.85,
      "processing_mode": "full_analysis",
      "confidence_level": "high"
    },
    "validation_recommendations": [
      "Data quality is excellent - proceed with full analysis"
    ]
  }
}
```

### Error Models

#### `ValidationFailureResponse` (Validation Failures)
When validation fails, this detailed error response is returned:

```python
class ValidationFailureResponse(BaseModel):
    status: str = "validation_failed"
    error_type: str
    message: str
    ticker: str
    expiration_date: str
    quality_assessment: QualityAssessment
    data_quality_issues: DataQualityIssues
    improvement_recommendations: List[str]
    alternative_approaches: List[AlternativeApproach]
    retry_instructions: RetryInstructions
    specific_guidance: Optional[SpecificGuidance] = None
```

Example response:
```json
{
  "status": "validation_failed",
  "error_type": "validation_gate_failure",
  "message": "Data quality validation failed",
  "ticker": "XYZ",
  "expiration_date": "20241215",
  "quality_assessment": {
    "overall_score": 0.35,
    "threshold_used": 0.5,
    "validation_mode": "standard",
    "asset_type": "low_liquidity"
  },
  "alternative_approaches": [
    {
      "approach": "Use permissive validation mode",
      "reason": "Lower quality thresholds for analysis",
      "example": "Set validation_mode=permissive in request"
    }
  ],
  "retry_instructions": {
    "permissive_mode": "Set validation_mode=permissive for more lenient validation",
    "disable_validation": "Set enable_validation=false to bypass all validation"
  }
}
```

## Quality Models

### `QualityWarnings` (Moderate Quality Data)
When data quality is acceptable but not ideal, quality warnings are included:

```python
class QualityWarnings(BaseModel):
    overall_quality_score: float
    quality_level: str
    warnings: List[str]
    recommended_actions: List[str]
    data_quality_concerns: Optional[List[str]] = None
    data_quality_strengths: Optional[List[str]] = None
```

### `DataQualityCheckResponse` (Quality Assessment)
For the data quality check endpoint:

```python
class DataQualityCheckResponse(BaseModel):
    status: str
    ticker: str
    expiration_date: str
    assessment_timestamp: str
    overall_quality_score: float
    quality_level: str
    analysis_recommendation: AnalysisRecommendationDetail
    data_availability: DataAvailability
    detailed_assessment: Optional[DetailedAssessment] = None
    recommendations: Optional[List[str]] = None
```

## Enums

### `ValidationStatus`
```python
class ValidationStatus(str, Enum):
    COMPLETED = "completed"
    PASSED = "passed"
    FAILED = "failed"
    DISABLED = "disabled"
    ERROR = "error"
```

### `ValidationMode`
```python
class ValidationMode(str, Enum):
    STRICT = "strict"
    STANDARD = "standard"
    PERMISSIVE = "permissive"
```

### `QualityLevel`
```python
class QualityLevel(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    VERY_POOR = "very_poor"
```

### `AnalysisRecommendation`
```python
class AnalysisRecommendation(str, Enum):
    PROCEED = "PROCEED"
    PROCEED_WITH_CAUTION = "PROCEED_WITH_CAUTION"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
```

## Usage Examples

### 1. Standard Analysis Request (with validation)
```python
# Frontend request
POST /stock?enable_validation=true&validation_mode=standard&min_quality_threshold=0.6
{
    "ticker": "SPY",
    "expiration_date": "20241215",
    "analysis_method": "holistic-market-edge"
}

# Successful response
{
    "market_context": { ... },
    "options_positioning": { ... },
    "gpt_verdict": { ... },
    "validation_metadata": {
        "validation_enabled": true,
        "validation_mode": "standard",
        "validation_status": "completed",
        "quality_metrics": {
            "overall_score": 0.85,
            "confidence_level": "high"
        }
    },
    "processing_time_seconds": 5.2
}
```

### 2. Analysis with Quality Warnings
```python
# Response for moderate quality data
{
    "market_context": { ... },
    "validation_metadata": {
        "validation_enabled": true,
        "validation_status": "completed",
        "quality_metrics": {
            "overall_score": 0.65
        }
    },
    "quality_warnings": {
        "overall_quality_score": 0.65,
        "quality_level": "Fair - Use results with caution and monitoring",
        "warnings": [
            "Moderate data quality - some limitations in analysis reliability"
        ],
        "recommended_actions": [
            "Monitor data quality closely",
            "Consider position size adjustments"
        ],
        "data_quality_concerns": [
            "Missing some Greeks calculations"
        ]
    }
}
```

### 3. Validation Failure
```python
# Response for insufficient data quality (HTTP 422)
{
    "status": "validation_failed",
    "error_type": "validation_gate_failure",
    "message": "Data quality validation failed",
    "ticker": "XYZ",
    "expiration_date": "20241215",
    "quality_assessment": {
        "overall_score": 0.30,
        "threshold_used": 0.50,
        "validation_mode": "standard"
    },
    "retry_instructions": {
        "lower_quality_threshold": "Set min_quality_threshold to 0.3",
        "permissive_mode": "Set validation_mode=permissive",
        "disable_validation": "Set enable_validation=false"
    }
}
```

### 4. Data Quality Check
```python
# Request
GET /check-data-quality/SPY?expiration_date=20241215&detailed=true

# Response
{
    "status": "completed",
    "ticker": "SPY",
    "expiration_date": "20241215",
    "overall_quality_score": 0.90,
    "quality_level": "Excellent - High confidence in analysis results",
    "analysis_recommendation": {
        "recommendation": "PROCEED",
        "confidence": "HIGH",
        "message": "Data quality is excellent - analysis should be highly reliable"
    },
    "data_availability": {
        "total_option_contracts": 150,
        "strikes_available": 25,
        "calls_and_puts_available": 20
    },
    "detailed_assessment": {
        "category_scores": {
            "pricing": 0.95,
            "greeks": 0.90,
            "liquidity": 0.85
        },
        "critical_issues": 0,
        "high_priority_issues": 2
    }
}
```

## HTTP Status Codes

The validation system uses appropriate HTTP status codes:

- **200 OK**: Successful analysis (with or without quality warnings)
- **400 Bad Request**: Invalid request parameters
- **404 Not Found**: No options data available
- **422 Unprocessable Entity**: Data quality below validation threshold
- **500 Internal Server Error**: System errors

## Frontend Integration Tips

### 1. Check Validation Status
Always check the `validation_metadata.validation_status`:
```javascript
if (response.validation_metadata.validation_status === 'completed') {
    // Process successful analysis
    const qualityScore = response.validation_metadata.quality_metrics.overall_score;

    if (response.quality_warnings) {
        // Show quality warnings to user
        displayQualityWarnings(response.quality_warnings);
    }
}
```

### 2. Handle Validation Failures
```javascript
if (response.status === 'validation_failed') {
    // Show validation failure UI
    displayValidationError(response);

    // Offer retry options
    showRetryOptions(response.retry_instructions);
}
```

### 3. Quality-Based UI Adjustments
```javascript
const qualityScore = response.validation_metadata.quality_metrics.overall_score;

if (qualityScore >= 0.8) {
    // High confidence - normal display
    setConfidenceLevel('high');
} else if (qualityScore >= 0.6) {
    // Medium confidence - show warnings
    setConfidenceLevel('medium');
    showQualityWarnings();
} else {
    // Low confidence - prominent warnings
    setConfidenceLevel('low');
    showProminentWarnings();
}
```

## Backward Compatibility

The new models maintain full backward compatibility:

1. **Existing API calls** continue to work unchanged
2. **Default behavior** includes validation (can be disabled with `enable_validation=false`)
3. **Core response structure** remains the same with additional metadata
4. **Error responses** are enhanced but maintain essential information

## Migration Guide

### For API Consumers
1. **No immediate changes required** - existing code continues to work
2. **Recommended**: Start using `validation_metadata` for quality insights
3. **Optional**: Handle new error response formats for better UX

### For Frontend Applications
1. **Phase 1**: Update error handling to use new error response structures
2. **Phase 2**: Implement quality warnings display
3. **Phase 3**: Add pre-analysis quality checks using `/check-data-quality`

### Example Migration
```javascript
// Before
if (response.status === 'error') {
    showError(response.message);
}

// After (enhanced)
if (response.status === 'validation_failed') {
    showValidationError(response);
    showRetryOptions(response.retry_instructions);
} else if (response.status === 'error') {
    showGeneralError(response);
} else if (response.quality_warnings) {
    showQualityWarnings(response.quality_warnings);
}
```

This guide provides comprehensive coverage of the new validation models and their integration into the analysis system. The models are designed to provide rich data quality information while maintaining backward compatibility and enabling sophisticated error handling.