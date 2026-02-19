"""
Test Suite for Extended Analysis Models

This module tests the new analysis models that support validation status,
quality scores, and detailed error reporting fields.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from models.analysis_models import (
    # Core models
    AnalysisRequest,
    RiskFreeRateRequest,
    SaveVerdictRequest,

    # Validation models
    ValidationMetadata,
    QualityWarnings,
    DataAvailability,
    DataCompleteness,
    DetailedAssessment,
    AnalysisRecommendationDetail,

    # Response models
    AnalysisResponse,
    DataQualityCheckResponse,
    ValidationFailureResponse,
    GeneralErrorResponse,
    NoDataResponse,
    QualityCheckErrorResponse,

    # Historical models
    AnalysisHistoryEntry,

    # Enums
    ValidationStatus,
    ValidationMode,
    QualityLevel,
    AnalysisRecommendation
)


class TestCoreModels:
    """Test core request models for backward compatibility."""

    def test_analysis_request_basic(self):
        """Test basic AnalysisRequest functionality."""
        request = AnalysisRequest(
            ticker="SPY",
            expiration_date="20241215"
        )

        assert request.ticker == "SPY"
        assert request.expiration_date == "20241215"
        assert request.risk_free_rate == 0.045  # Default value
        assert request.analysis_method == 'holistic-market-edge'
        assert request.gpt_model == 'gpt-5'
        assert request.override_price is None

    def test_analysis_request_with_overrides(self):
        """Test AnalysisRequest with custom values."""
        request = AnalysisRequest(
            ticker="AAPL",
            expiration_date="20241220",
            risk_free_rate=0.055,
            analysis_method="custom-method",
            gpt_model="gpt-4",
            override_price=150.0
        )

        assert request.ticker == "AAPL"
        assert request.risk_free_rate == 0.055
        assert request.analysis_method == "custom-method"
        assert request.gpt_model == "gpt-4"
        assert request.override_price == 150.0

    def test_risk_free_rate_request_backward_compatibility(self):
        """Test RiskFreeRateRequest backward compatibility."""
        # Old style (should still work)
        request = RiskFreeRateRequest(tickers=["SPY", "QQQ"])
        assert request.tickers == ["SPY", "QQQ"]
        assert request.expiration_date is None

        # New style (with expiration date)
        request_new = RiskFreeRateRequest(
            tickers=["SPY"],
            expiration_date="20241215"
        )
        assert request_new.tickers == ["SPY"]
        assert request_new.expiration_date == "20241215"

    def test_save_verdict_request(self):
        """Test SaveVerdictRequest model."""
        request = SaveVerdictRequest(
            verdict={"recommendation": "BUY", "confidence": 0.85},
            label="test-verdict"
        )

        assert request.verdict == {"recommendation": "BUY", "confidence": 0.85}
        assert request.label == "test-verdict"


class TestValidationModels:
    """Test validation-related models."""

    def test_validation_metadata(self):
        """Test ValidationMetadata model."""
        metadata = ValidationMetadata(
            validation_enabled=True,
            validation_mode=ValidationMode.STANDARD,
            validation_status=ValidationStatus.COMPLETED,
            quality_metrics={"overall_score": 0.85},
            validation_recommendations=["Proceed with analysis"]
        )

        assert metadata.validation_enabled is True
        assert metadata.validation_mode == ValidationMode.STANDARD
        assert metadata.validation_status == ValidationStatus.COMPLETED
        assert metadata.quality_metrics["overall_score"] == 0.85
        assert len(metadata.validation_recommendations) == 1

    def test_quality_warnings(self):
        """Test QualityWarnings model."""
        warnings = QualityWarnings(
            overall_quality_score=0.65,
            quality_level="Good - Analysis results should be reliable",
            warnings=["Moderate data quality detected"],
            recommended_actions=["Monitor data quality closely"],
            data_quality_concerns=["Missing some Greeks"],
            data_quality_strengths=["Complete pricing data"]
        )

        assert warnings.overall_quality_score == 0.65
        assert len(warnings.warnings) == 1
        assert len(warnings.recommended_actions) == 1
        assert len(warnings.data_quality_concerns) == 1
        assert len(warnings.data_quality_strengths) == 1

    def test_data_availability(self):
        """Test DataAvailability model."""
        availability = DataAvailability(
            total_option_contracts=150,
            strikes_available=25,
            calls_and_puts_available=20
        )

        assert availability.total_option_contracts == 150
        assert availability.strikes_available == 25
        assert availability.calls_and_puts_available == 20

    def test_data_completeness(self):
        """Test DataCompleteness model."""
        completeness = DataCompleteness(
            completeness_ratio=0.85,
            complete_count=17,
            total_count=20,
            required_greeks=["delta", "gamma", "theta", "vega", "rho"]
        )

        assert completeness.completeness_ratio == 0.85
        assert completeness.complete_count == 17
        assert completeness.total_count == 20
        assert len(completeness.required_greeks) == 5


class TestResponseModels:
    """Test response models."""

    def test_analysis_response(self):
        """Test AnalysisResponse with validation metadata."""
        validation_metadata = ValidationMetadata(
            validation_enabled=True,
            validation_status=ValidationStatus.COMPLETED,
            quality_metrics={"overall_score": 0.9}
        )

        response = AnalysisResponse(
            status="success",
            market_context={"current_price": 420.50},
            validation_metadata=validation_metadata,
            processing_time_seconds=5.2
        )

        assert response.status == "success"
        assert response.market_context["current_price"] == 420.50
        assert response.validation_metadata.validation_enabled is True
        assert response.processing_time_seconds == 5.2

    def test_data_quality_check_response(self):
        """Test DataQualityCheckResponse model."""
        recommendation = AnalysisRecommendationDetail(
            recommendation=AnalysisRecommendation.PROCEED,
            confidence="HIGH",
            message="Data quality is excellent"
        )

        availability = DataAvailability(
            total_option_contracts=100,
            strikes_available=20,
            calls_and_puts_available=15
        )

        response = DataQualityCheckResponse(
            status="completed",
            ticker="SPY",
            expiration_date="20241215",
            assessment_timestamp="2024-01-01T00:00:00",
            overall_quality_score=0.9,
            quality_level="Excellent",
            analysis_recommendation=recommendation,
            data_availability=availability
        )

        assert response.status == "completed"
        assert response.ticker == "SPY"
        assert response.overall_quality_score == 0.9
        assert response.analysis_recommendation.recommendation == AnalysisRecommendation.PROCEED
        assert response.data_availability.total_option_contracts == 100

    def test_validation_failure_response(self):
        """Test ValidationFailureResponse model."""
        from models.analysis_models import (
            QualityAssessment,
            DataQualityIssues,
            AlternativeApproach,
            RetryInstructions,
            SpecificGuidance
        )

        quality_assessment = QualityAssessment(
            overall_score=0.3,
            threshold_used=0.5,
            validation_mode="standard",
            asset_type="medium_liquidity"
        )

        issues = DataQualityIssues(
            critical_issues_count=5,
            high_priority_issues_count=10,
            main_concerns=["Low data completeness"],
            affected_categories=[{"category": "Greeks", "score": 0.2, "severity": "high"}]
        )

        retry_instructions = RetryInstructions(
            same_request_different_date="Try different expiration date",
            lower_quality_threshold="Lower threshold to 0.3",
            permissive_mode="Use permissive validation mode",
            disable_validation="Disable validation with caution"
        )

        response = ValidationFailureResponse(
            error_type="validation_gate_failure",
            message="Data quality insufficient",
            ticker="TEST",
            expiration_date="20241215",
            quality_assessment=quality_assessment,
            data_quality_issues=issues,
            retry_instructions=retry_instructions
        )

        assert response.status == "validation_failed"
        assert response.error_type == "validation_gate_failure"
        assert response.quality_assessment.overall_score == 0.3
        assert response.data_quality_issues.critical_issues_count == 5


class TestErrorModels:
    """Test error response models."""

    def test_general_error_response(self):
        """Test GeneralErrorResponse model."""
        response = GeneralErrorResponse(
            error_type="analysis_failure",
            message="Analysis failed due to system error",
            ticker="SPY",
            expiration_date="20241215",
            validation_enabled=True,
            recommendations=["Check system status", "Retry later"],
            retry_suggestions={"retry_delay": "5 minutes"}
        )

        assert response.status == "error"
        assert response.error_type == "analysis_failure"
        assert response.validation_enabled is True
        assert len(response.recommendations) == 2

    def test_no_data_response(self):
        """Test NoDataResponse model."""
        response = NoDataResponse(
            ticker="INVALID",
            expiration_date="20241215",
            message="No options data found",
            suggestions=["Check ticker symbol", "Try different date"]
        )

        assert response.status == "no_data"
        assert response.ticker == "INVALID"
        assert len(response.suggestions) == 2


class TestHistoricalModels:
    """Test historical analysis models."""

    def test_analysis_history_entry(self):
        """Test AnalysisHistoryEntry with validation metadata."""
        entry = AnalysisHistoryEntry(
            id="12345",
            ticker="SPY",
            expiration_date="20241215",
            risk_free_rate=0.045,
            analysis_method="holistic-market-edge",
            gpt_model="gpt-5",
            validation_enabled=True,
            validation_mode="standard",
            validation_status="completed",
            quality_score=0.85,
            created_at=datetime.now()
        )

        assert entry.id == "12345"
        assert entry.ticker == "SPY"
        assert entry.validation_enabled is True
        assert entry.validation_mode == "standard"
        assert entry.quality_score == 0.85
        assert entry.created_at is not None


class TestEnums:
    """Test enum definitions."""

    def test_validation_status_enum(self):
        """Test ValidationStatus enum values."""
        assert ValidationStatus.COMPLETED == "completed"
        assert ValidationStatus.PASSED == "passed"
        assert ValidationStatus.FAILED == "failed"
        assert ValidationStatus.DISABLED == "disabled"
        assert ValidationStatus.ERROR == "error"

    def test_validation_mode_enum(self):
        """Test ValidationMode enum values."""
        assert ValidationMode.STRICT == "strict"
        assert ValidationMode.STANDARD == "standard"
        assert ValidationMode.PERMISSIVE == "permissive"

    def test_quality_level_enum(self):
        """Test QualityLevel enum values."""
        assert QualityLevel.EXCELLENT == "excellent"
        assert QualityLevel.GOOD == "good"
        assert QualityLevel.FAIR == "fair"
        assert QualityLevel.POOR == "poor"
        assert QualityLevel.VERY_POOR == "very_poor"

    def test_analysis_recommendation_enum(self):
        """Test AnalysisRecommendation enum values."""
        assert AnalysisRecommendation.PROCEED == "PROCEED"
        assert AnalysisRecommendation.PROCEED_WITH_CAUTION == "PROCEED_WITH_CAUTION"
        assert AnalysisRecommendation.REVIEW_REQUIRED == "REVIEW_REQUIRED"


class TestValidationRules:
    """Test Pydantic validation rules."""

    def test_quality_threshold_validation(self):
        """Test quality threshold validation in ValidationConfigRequest."""
        from models.analysis_models import ValidationConfigRequest

        # Valid threshold
        config = ValidationConfigRequest(min_quality_threshold=0.7)
        assert config.min_quality_threshold == 0.7

        # Invalid threshold (too high)
        with pytest.raises(ValidationError):
            ValidationConfigRequest(min_quality_threshold=1.5)

        # Invalid threshold (negative)
        with pytest.raises(ValidationError):
            ValidationConfigRequest(min_quality_threshold=-0.1)

    def test_required_fields(self):
        """Test required field validation."""
        # ValidationMetadata requires validation_enabled and validation_status
        with pytest.raises(ValidationError):
            ValidationMetadata()  # Missing required fields

        # Should work with required fields
        metadata = ValidationMetadata(
            validation_enabled=True,
            validation_status=ValidationStatus.COMPLETED
        )
        assert metadata.validation_enabled is True


class TestModelIntegration:
    """Test integration between models."""

    def test_analysis_response_with_quality_warnings(self):
        """Test AnalysisResponse with conditional QualityWarnings."""
        validation_metadata = ValidationMetadata(
            validation_enabled=True,
            validation_status=ValidationStatus.COMPLETED
        )

        quality_warnings = QualityWarnings(
            overall_quality_score=0.6,
            quality_level="Fair",
            warnings=["Moderate quality"],
            recommended_actions=["Monitor closely"]
        )

        response = AnalysisResponse(
            validation_metadata=validation_metadata,
            quality_warnings=quality_warnings
        )

        assert response.validation_metadata.validation_enabled is True
        assert response.quality_warnings is not None
        assert response.quality_warnings.overall_quality_score == 0.6

    def test_nested_model_serialization(self):
        """Test that nested models serialize correctly."""
        validation_metadata = ValidationMetadata(
            validation_enabled=True,
            validation_status=ValidationStatus.COMPLETED,
            quality_metrics={"score": 0.8, "categories": {"pricing": 0.9}}
        )

        response = AnalysisResponse(validation_metadata=validation_metadata)

        # Convert to dict (simulates JSON serialization)
        response_dict = response.dict()

        assert response_dict["validation_metadata"]["validation_enabled"] is True
        assert response_dict["validation_metadata"]["quality_metrics"]["score"] == 0.8
        assert response_dict["validation_metadata"]["quality_metrics"]["categories"]["pricing"] == 0.9


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main([__file__, "-v"])