"""
Test Suite for Core Validation Engine

This module provides comprehensive tests for the core validation engine,
covering all three validation categories and various data quality scenarios.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import pytest
import math
import numpy as np
from datetime import datetime
from typing import Dict, Any

# Import modules under test
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from analytics.core_validation_engine import (
    CoreValidationEngine,
    ValidationCategory,
    ValidationSeverity,
    QualityLevel,
    StrikePricingMetrics,
    GreeksCompletenessMetrics,
    LiquidityMetrics
)

from analytics.validation_integration import (
    ValidationOrchestrator,
    validate_options_for_analysis
)


class TestCoreValidationEngine:
    """Test cases for CoreValidationEngine class."""

    @pytest.fixture
    def validator(self):
        """Create a CoreValidationEngine instance for testing."""
        return CoreValidationEngine(asset_type="medium_liquidity")

    @pytest.fixture
    def perfect_option_data(self):
        """Create perfect quality option data for testing."""
        return {
            "420.0": {
                "call": {
                    "bid": 12.50,
                    "ask": 12.75,
                    "last": 12.60,
                    "model_price": 12.62,
                    "delta": 0.65,
                    "gamma": 0.012,
                    "theta": -0.045,
                    "vega": 0.25,
                    "rho": 0.15,
                    "volume": 150,
                    "open_interest": 1200
                },
                "put": {
                    "bid": 8.20,
                    "ask": 8.45,
                    "last": 8.35,
                    "model_price": 8.33,
                    "delta": -0.35,
                    "gamma": 0.012,
                    "theta": -0.042,
                    "vega": 0.25,
                    "rho": -0.18,
                    "volume": 95,
                    "open_interest": 850
                }
            },
            "425.0": {
                "call": {
                    "bid": 8.90,
                    "ask": 9.10,
                    "last": 9.00,
                    "model_price": 8.98,
                    "delta": 0.55,
                    "gamma": 0.014,
                    "theta": -0.048,
                    "vega": 0.28,
                    "rho": 0.12,
                    "volume": 200,
                    "open_interest": 1500
                },
                "put": {
                    "bid": 11.80,
                    "ask": 12.05,
                    "last": 11.95,
                    "model_price": 11.93,
                    "delta": -0.45,
                    "gamma": 0.014,
                    "theta": -0.045,
                    "vega": 0.28,
                    "rho": -0.22,
                    "volume": 75,
                    "open_interest": 650
                }
            }
        }

    @pytest.fixture
    def poor_quality_data(self):
        """Create poor quality option data for testing."""
        return {
            "420.0": {
                "call": {
                    "bid": None,  # Missing pricing
                    "ask": 12.75,
                    "last": None,
                    "model_price": None,
                    "delta": None,  # Missing Greeks
                    "gamma": float('nan'),  # Invalid Greek
                    "theta": -150.0,  # Out of bounds
                    "vega": None,
                    "rho": None,
                    "volume": 5,  # Below threshold (10)
                    "open_interest": 50  # Below threshold (100)
                },
                "put": {
                    "bid": 1.00,
                    "ask": 2.50,  # Wide spread (60%)
                    "last": 1.75,
                    "model_price": 1.80,
                    "delta": 1.5,  # Out of bounds for put
                    "gamma": -0.01,  # Invalid (negative)
                    "theta": "invalid",  # Non-numeric
                    "vega": 0.25,
                    "rho": 0.15,
                    "volume": 0,
                    "open_interest": 0
                }
            }
        }

    def test_perfect_data_validation(self, validator, perfect_option_data):
        """Test validation of perfect quality data."""
        report = validator.validate_options_data(
            options_data=perfect_option_data,
            ticker="SPY",
            expiration_date="2024-01-19",
            spot_price=422.50
        )

        # Should have high overall scores
        assert report.combined_quality_score >= 0.8
        assert report.overall_pricing_score >= 0.8
        assert report.overall_greeks_score >= 0.8
        assert report.overall_liquidity_score >= 0.5

        # Should have strikes in excellent/good categories
        assert len(report.excellent_strikes) >= 2
        assert len(report.failed_strikes) == 0

        # Should have minimal issues
        assert len(report.critical_issues) == 0
        assert len(report.all_issues) <= 2

        # Should recommend proceeding
        assert "PROCEED" in report.overall_recommendation

    def test_poor_quality_data_validation(self, validator, poor_quality_data):
        """Test validation of poor quality data."""
        report = validator.validate_options_data(
            options_data=poor_quality_data,
            ticker="XYZ",
            expiration_date="2024-01-19",
            spot_price=420.00
        )

        # Should have low overall scores
        assert report.combined_quality_score <= 0.5
        assert report.overall_pricing_score <= 0.6
        assert report.overall_greeks_score <= 0.4
        assert report.overall_liquidity_score <= 0.3

        # Should have strikes in poor/failed categories
        assert len(report.poor_strikes) + len(report.failed_strikes) >= 1
        assert len(report.excellent_strikes) == 0

        # Should have many issues
        assert len(report.critical_issues) >= 3
        assert len(report.all_issues) >= 10

        # Should recommend review or rejection
        assert any(keyword in report.overall_recommendation
                  for keyword in ["REVIEW", "CAUTION", "DO NOT PROCEED"])

    def test_strike_pricing_validation(self, validator):
        """Test specific strike pricing validation logic."""
        # Test missing bid
        option_data = {"ask": 10.0, "last": 9.5, "model_price": 9.8}
        result = validator._validate_single_option(420.0, "call", option_data, 422.0)

        assert not result.pricing_metrics.has_bid
        pricing_issues = [i for i in result.issues if i.category == ValidationCategory.STRIKE_PRICING]
        assert any("Missing bid" in issue.issue_description for issue in pricing_issues)

        # Test wide spread
        option_data = {"bid": 8.0, "ask": 12.0, "last": 10.0}  # 33% spread
        result = validator._validate_single_option(420.0, "call", option_data, 422.0)

        assert result.pricing_metrics.bid_ask_spread_pct == 33.33333333333333
        spread_issues = [i for i in result.issues if "Wide bid-ask spread" in i.issue_description]
        assert len(spread_issues) >= 1

    def test_greeks_completeness_validation(self, validator):
        """Test Greeks completeness validation logic."""
        # Test missing Greeks
        option_data = {"delta": 0.6, "gamma": 0.01}  # Missing theta, vega, rho
        result = validator._validate_single_option(420.0, "call", option_data, 422.0)

        assert result.greeks_metrics.has_delta
        assert result.greeks_metrics.has_gamma
        assert not result.greeks_metrics.has_theta
        assert not result.greeks_metrics.has_vega
        assert not result.greeks_metrics.has_rho

        missing_greeks = [i for i in result.issues
                         if i.category == ValidationCategory.GREEKS_COMPLETENESS
                         and "Missing" in i.issue_description]
        assert len(missing_greeks) == 3  # theta, vega, rho

        # Test out-of-bounds Greeks
        option_data = {
            "delta": 1.5,  # Out of bounds for call (should be 0-1)
            "gamma": -0.01,  # Invalid (should be positive)
            "theta": -50.0,  # Out of bounds
            "vega": 0.25,
            "rho": 0.15
        }
        result = validator._validate_single_option(420.0, "call", option_data, 422.0)

        bounds_issues = [i for i in result.issues
                        if "outside theoretical bounds" in i.issue_description]
        assert len(bounds_issues) >= 2

    def test_liquidity_indicators_validation(self, validator):
        """Test liquidity indicators validation logic."""
        # Test low volume and OI
        option_data = {
            "volume": 5,  # Below threshold (10)
            "open_interest": 50,  # Below threshold (100)
            "bid": 9.0,
            "ask": 11.0  # 18% spread - acceptable
        }
        result = validator._validate_single_option(420.0, "call", option_data, 422.0)

        assert not result.liquidity_metrics.volume_meets_threshold
        assert not result.liquidity_metrics.oi_meets_threshold
        assert result.liquidity_metrics.spread_meets_threshold  # 18% < 25%

        liquidity_issues = [i for i in result.issues
                           if i.category == ValidationCategory.LIQUIDITY_INDICATORS]
        volume_issues = [i for i in liquidity_issues if "Low volume" in i.issue_description]
        oi_issues = [i for i in liquidity_issues if "Low open interest" in i.issue_description]

        assert len(volume_issues) == 1
        assert len(oi_issues) == 1

    def test_asset_type_thresholds(self):
        """Test that different asset types use appropriate thresholds."""
        # High liquidity asset (more lenient)
        high_liq_validator = CoreValidationEngine(asset_type="high_liquidity")

        # Low liquidity asset (more strict)
        low_liq_validator = CoreValidationEngine(asset_type="low_liquidity")

        # Same moderate quality data
        moderate_data = {
            "420.0": {
                "call": {
                    "bid": 10.0,
                    "ask": 10.5,
                    "delta": 0.6,
                    "gamma": 0.01,
                    "theta": -0.05,
                    # Missing vega, rho
                    "volume": 25,
                    "open_interest": 150
                }
            }
        }

        high_liq_report = high_liq_validator.validate_options_data(
            moderate_data, "SPY", "2024-01-19"
        )

        low_liq_report = low_liq_validator.validate_options_data(
            moderate_data, "XYZ", "2024-01-19"
        )

        # High liquidity should be more tolerant
        assert high_liq_report.combined_quality_score >= low_liq_report.combined_quality_score

    def test_empty_data_handling(self, validator):
        """Test handling of empty or invalid data."""
        # Empty data
        empty_report = validator.validate_options_data({}, "SPY", "2024-01-19")
        assert empty_report.total_strikes == 0
        assert empty_report.combined_quality_score == 0.0

        # Invalid strike keys
        invalid_data = {"not_a_number": {"call": {"delta": 0.5}}}
        invalid_report = validator.validate_options_data(invalid_data, "SPY", "2024-01-19")
        assert invalid_report.total_strikes == 0

    def test_quality_level_categorization(self, validator):
        """Test that strikes are correctly categorized by quality level."""
        mixed_quality_data = {
            "420.0": {  # Excellent quality
                "call": {
                    "bid": 12.50, "ask": 12.75, "last": 12.60, "model_price": 12.62,
                    "delta": 0.65, "gamma": 0.012, "theta": -0.045, "vega": 0.25, "rho": 0.15,
                    "volume": 150, "open_interest": 1200
                }
            },
            "425.0": {  # Poor quality
                "call": {
                    "bid": None, "ask": 9.10, "last": None, "model_price": None,
                    "delta": None, "gamma": float('nan'), "theta": -150.0, "vega": None, "rho": None,
                    "volume": 5, "open_interest": 50
                }
            }
        }

        report = validator.validate_options_data(mixed_quality_data, "SPY", "2024-01-19")

        # Should have strikes in different quality categories
        assert len(report.excellent_strikes) + len(report.good_strikes) >= 1
        assert len(report.poor_strikes) + len(report.failed_strikes) >= 1


class TestValidationOrchestrator:
    """Test cases for ValidationOrchestrator class."""

    @pytest.fixture
    def orchestrator(self):
        """Create a ValidationOrchestrator instance for testing."""
        return ValidationOrchestrator(asset_type="medium_liquidity")

    def test_comprehensive_validation_success(self, orchestrator, perfect_option_data):
        """Test successful comprehensive validation."""
        results = orchestrator.run_comprehensive_validation(
            options_data=perfect_option_data,
            ticker="SPY",
            expiration_date="2024-01-19",
            spot_price=422.50
        )

        assert results['validation_summary']['integration_status'] == 'completed'
        assert results['validation_summary']['core_validation']['status'] == 'completed'
        assert results['validation_summary']['enhanced_validation']['status'] == 'completed'

        # Should have consolidated recommendations
        assert 'consolidated_recommendations' in results
        assert 'processing_decisions' in results
        assert 'data_quality_metrics' in results

        # Should recommend proceeding
        recommendations = results['consolidated_recommendations']
        assert recommendations['can_proceed'] is True
        assert recommendations['processing_mode'] in ['full_analysis', 'standard_analysis']

    def test_validation_gate_decision(self, orchestrator, perfect_option_data):
        """Test analysis gate decision making."""
        results = orchestrator.run_comprehensive_validation(
            options_data=perfect_option_data,
            ticker="SPY",
            expiration_date="2024-01-19"
        )

        gate_decision = orchestrator.get_analysis_gate_decision(results)

        assert gate_decision['gate_decision'] == 'APPROVE'
        assert gate_decision['allow_analysis'] is True
        assert 'processing_mode' in gate_decision
        assert 'focus_strikes' in gate_decision

    def test_validation_failure_handling(self, orchestrator):
        """Test handling of validation system failures."""
        # Simulate invalid data that would cause validation to fail
        invalid_data = {"invalid": "structure"}

        results = orchestrator.run_comprehensive_validation(
            options_data=invalid_data,
            ticker="TEST",
            expiration_date="2024-01-19"
        )

        # Should handle gracefully with fallback
        assert 'error' in results or results['validation_summary']['integration_status'] != 'completed'


class TestValidationIntegrationFunction:
    """Test the main integration function."""

    def test_validate_options_for_analysis_success(self, perfect_option_data):
        """Test the main validation function with good data."""
        results = validate_options_for_analysis(
            options_data=perfect_option_data,
            ticker="SPY",
            expiration_date="2024-01-19",
            spot_price=422.50,
            asset_type="high_liquidity"
        )

        # Should have all expected components
        assert 'validation_summary' in results
        assert 'consolidated_recommendations' in results
        assert 'processing_decisions' in results
        assert 'gate_decision' in results

        # Gate decision should approve
        gate = results['gate_decision']
        assert gate['gate_decision'] == 'APPROVE'
        assert gate['allow_analysis'] is True

    def test_validate_options_for_analysis_rejection(self, poor_quality_data):
        """Test the main validation function with poor data."""
        results = validate_options_for_analysis(
            options_data=poor_quality_data,
            ticker="TEST",
            expiration_date="2024-01-19",
            spot_price=420.00
        )

        # Should reject or proceed with extreme caution
        gate = results['gate_decision']
        if gate['gate_decision'] == 'APPROVE':
            # If approved, should be with severe restrictions
            assert gate['processing_mode'] in ['reduced_analysis', 'basic_analysis']
            assert len(gate.get('restrictions', [])) > 0


class TestValidationMetrics:
    """Test validation metrics and scoring calculations."""

    def test_category_scoring(self):
        """Test that category scores are calculated correctly."""
        validator = CoreValidationEngine()

        # Test pricing completeness scoring
        complete_pricing = {"bid": 10.0, "ask": 10.5, "last": 10.2, "model_price": 10.3}
        partial_pricing = {"bid": 10.0, "ask": 10.5}

        complete_result = validator._validate_single_option(420.0, "call", complete_pricing)
        partial_result = validator._validate_single_option(420.0, "call", partial_pricing)

        assert complete_result.pricing_metrics.pricing_completeness_score > partial_result.pricing_metrics.pricing_completeness_score

    def test_liquidity_scoring(self):
        """Test liquidity scoring logic."""
        validator = CoreValidationEngine()

        high_liquidity = {
            "volume": 500, "open_interest": 2000,
            "bid": 10.0, "ask": 10.1  # 1% spread
        }

        low_liquidity = {
            "volume": 5, "open_interest": 20,
            "bid": 10.0, "ask": 15.0  # 33% spread
        }

        high_result = validator._validate_single_option(420.0, "call", high_liquidity)
        low_result = validator._validate_single_option(420.0, "call", low_liquidity)

        assert high_result.liquidity_metrics.liquidity_score > low_result.liquidity_metrics.liquidity_score
        assert high_result.liquidity_metrics.volume_meets_threshold
        assert high_result.liquidity_metrics.oi_meets_threshold
        assert high_result.liquidity_metrics.spread_meets_threshold

        assert not low_result.liquidity_metrics.volume_meets_threshold
        assert not low_result.liquidity_metrics.oi_meets_threshold
        assert not low_result.liquidity_metrics.spread_meets_threshold


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main([__file__, "-v"])