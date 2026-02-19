"""
Comprehensive Test Suite for Validation Integration Orchestrator

This module tests the integration orchestrator that coordinates core validation,
enhanced validation, cross-source validation, and provides consolidated
recommendations for analysis decisions.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch
from typing import Dict, Any

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from analytics.validation_integration import (
    ValidationOrchestrator,
    validate_options_for_analysis
)
from analytics.core_validation_engine import CoreValidationEngine
from analytics.enhanced_greeks_validation import EnhancedGreeksValidator
from analytics.strategy_validation_gates import StrategyValidationGates


class TestValidationOrchestrator:
    """Test validation orchestrator with comprehensive scenarios."""

    def setup_method(self):
        """Set up test environment."""
        self.orchestrator = ValidationOrchestrator()

    @pytest.fixture
    def excellent_options_data(self):
        """Create excellent quality options data."""
        return {
            "410": {
                "call": {
                    "bid": 15.20, "ask": 15.40, "last": 15.30, "model_price": 15.32,
                    "delta": 0.75, "gamma": 0.010, "theta": -0.15, "vega": 0.40, "rho": 0.20,
                    "volume": 800, "open_interest": 3000,
                    "iv": 0.22, "price_vs_model_pct": 1.2
                },
                "put": {
                    "bid": 5.80, "ask": 6.00, "last": 5.90, "model_price": 5.88,
                    "delta": -0.25, "gamma": 0.010, "theta": -0.12, "vega": 0.40, "rho": -0.15,
                    "volume": 600, "open_interest": 2200,
                    "iv": 0.24, "price_vs_model_pct": -0.8
                }
            },
            "420": {  # ATM strikes
                "call": {
                    "bid": 8.20, "ask": 8.40, "last": 8.30, "model_price": 8.32,
                    "delta": 0.52, "gamma": 0.015, "theta": -0.18, "vega": 0.45, "rho": 0.15,
                    "volume": 2000, "open_interest": 8000,
                    "iv": 0.20, "price_vs_model_pct": 0.5
                },
                "put": {
                    "bid": 7.80, "ask": 8.00, "last": 7.90, "model_price": 7.88,
                    "delta": -0.48, "gamma": 0.015, "theta": -0.16, "vega": 0.45, "rho": -0.22,
                    "volume": 1800, "open_interest": 7200,
                    "iv": 0.21, "price_vs_model_pct": -0.3
                }
            },
            "430": {
                "call": {
                    "bid": 3.10, "ask": 3.25, "last": 3.18, "model_price": 3.20,
                    "delta": 0.28, "gamma": 0.012, "theta": -0.12, "vega": 0.35, "rho": 0.08,
                    "volume": 500, "open_interest": 2000,
                    "iv": 0.19, "price_vs_model_pct": 0.2
                },
                "put": {
                    "bid": 12.60, "ask": 12.85, "last": 12.72, "model_price": 12.75,
                    "delta": -0.72, "gamma": 0.012, "theta": -0.10, "vega": 0.35, "rho": -0.30,
                    "volume": 300, "open_interest": 1200,
                    "iv": 0.18, "price_vs_model_pct": 0.8
                }
            }
        }

    @pytest.fixture
    def poor_options_data(self):
        """Create poor quality options data."""
        return {
            "420": {
                "call": {
                    "bid": None, "ask": 8.40, "last": None, "model_price": None,
                    "delta": None, "gamma": np.nan, "theta": -50.0, "vega": None, "rho": None,
                    "volume": 3, "open_interest": 20,
                    "iv": None, "price_vs_model_pct": None
                },
                "put": {
                    "bid": 5.00, "ask": 10.00, "last": 7.50, "model_price": 7.25,
                    "delta": -2.0, "gamma": -0.01, "theta": 0.5, "vega": 0.45, "rho": -0.22,
                    "volume": 0, "open_interest": 5,
                    "iv": 2.5, "price_vs_model_pct": 25.0  # Extreme mispricings
                }
            }
        }

    @pytest.fixture
    def finviz_data(self):
        """Mock Finviz data for cross-source validation."""
        return {
            "current_price": 420.15,
            "market_cap": "500B",
            "volume": 85000000,
            "avg_volume": 75000000,
            "volatility": "18.50%",
            "beta": 1.05,
            "pe_ratio": 24.5,
            "dividend_yield": "1.85%",
            "sector": "Technology"
        }

    def test_comprehensive_validation_success(self, excellent_options_data, finviz_data):
        """Test successful comprehensive validation with excellent data."""
        with patch('analytics.validation_integration.get_finviz_data') as mock_finviz:
            mock_finviz.return_value = finviz_data

            results = self.orchestrator.run_comprehensive_validation(
                options_data=excellent_options_data,
                ticker="SPY",
                expiration_date="2024-01-19",
                spot_price=420.15,
                asset_type="high_liquidity"
            )

        # Check overall integration status
        assert results['validation_summary']['integration_status'] == 'completed'
        assert results['validation_summary']['core_validation']['status'] == 'completed'
        assert results['validation_summary']['enhanced_validation']['status'] == 'completed'
        assert results['validation_summary']['cross_source_validation']['status'] == 'completed'

        # Check consolidated quality metrics
        assert 'data_quality_metrics' in results
        quality_metrics = results['data_quality_metrics']
        assert quality_metrics['consolidated_quality_score'] >= 0.8
        assert quality_metrics['confidence_level'] in ['high', 'very_high']

        # Check consolidated recommendations
        assert 'consolidated_recommendations' in results
        recommendations = results['consolidated_recommendations']
        assert recommendations['can_proceed'] is True
        assert recommendations['processing_mode'] in ['full_analysis', 'enhanced_analysis']
        assert recommendations['confidence_level'] == 'high'

        # Check processing decisions
        assert 'processing_decisions' in results
        decisions = results['processing_decisions']
        assert decisions['gate_decision'] == 'APPROVE'
        assert decisions['allow_analysis'] is True

    def test_comprehensive_validation_failure(self, poor_options_data, finviz_data):
        """Test comprehensive validation with poor quality data."""
        with patch('analytics.validation_integration.get_finviz_data') as mock_finviz:
            mock_finviz.return_value = finviz_data

            results = self.orchestrator.run_comprehensive_validation(
                options_data=poor_options_data,
                ticker="TEST",
                expiration_date="2024-01-19",
                spot_price=420.00,
                asset_type="medium_liquidity"
            )

        # Should complete but with poor quality scores
        assert results['validation_summary']['integration_status'] == 'completed'

        # Quality metrics should be poor
        quality_metrics = results['data_quality_metrics']
        assert quality_metrics['consolidated_quality_score'] <= 0.4
        assert quality_metrics['confidence_level'] in ['low', 'very_low']

        # Should not recommend proceeding or with severe restrictions
        recommendations = results['consolidated_recommendations']
        if recommendations['can_proceed']:
            assert recommendations['processing_mode'] in ['basic_analysis', 'limited_analysis']
            assert len(recommendations['restrictions']) >= 3
        else:
            assert recommendations['can_proceed'] is False

    def test_cross_source_validation_consistency(self, excellent_options_data):
        """Test cross-source validation detects consistency issues."""
        # Mock Finviz data that's inconsistent with options data
        inconsistent_finviz = {
            "current_price": 380.00,  # Significantly different from spot_price
            "volatility": "50.00%",   # Much higher than implied volatility
            "volume": 1000000,       # Much lower than typical
            "beta": 2.5              # Much higher than normal
        }

        with patch('analytics.validation_integration.get_finviz_data') as mock_finviz:
            mock_finviz.return_value = inconsistent_finviz

            results = self.orchestrator.run_comprehensive_validation(
                options_data=excellent_options_data,
                ticker="SPY",
                expiration_date="2024-01-19",
                spot_price=420.00,
                asset_type="high_liquidity"
            )

        # Should detect cross-source inconsistencies
        cross_source = results['validation_summary']['cross_source_validation']
        assert cross_source['status'] == 'completed'

        # Should have consistency warnings
        issues = cross_source.get('issues', [])
        assert len(issues) >= 2  # Price and volatility mismatches

        # Should affect overall quality score
        quality_metrics = results['data_quality_metrics']
        assert quality_metrics['consolidated_quality_score'] < 0.9  # Reduced due to inconsistencies

    def test_validation_mode_effects(self, excellent_options_data, finviz_data):
        """Test that different validation modes affect results appropriately."""
        # Test strict mode
        with patch('analytics.validation_integration.get_finviz_data') as mock_finviz:
            mock_finviz.return_value = finviz_data

            strict_results = self.orchestrator.run_comprehensive_validation(
                options_data=excellent_options_data,
                ticker="SPY",
                expiration_date="2024-01-19",
                spot_price=420.15,
                validation_mode='strict'
            )

        # Test permissive mode
        with patch('analytics.validation_integration.get_finviz_data') as mock_finviz:
            mock_finviz.return_value = finviz_data

            permissive_results = self.orchestrator.run_comprehensive_validation(
                options_data=excellent_options_data,
                ticker="SPY",
                expiration_date="2024-01-19",
                spot_price=420.15,
                validation_mode='permissive'
            )

        # Strict mode should have higher quality requirements
        strict_score = strict_results['data_quality_metrics']['consolidated_quality_score']
        permissive_score = permissive_results['data_quality_metrics']['consolidated_quality_score']

        # With excellent data, both should score high, but strict might be more demanding
        assert strict_score >= 0.8
        assert permissive_score >= 0.8

    def test_asset_type_specific_validation(self, excellent_options_data, finviz_data):
        """Test that asset type affects validation appropriately."""
        with patch('analytics.validation_integration.get_finviz_data') as mock_finviz:
            mock_finviz.return_value = finviz_data

            # Test high liquidity asset
            high_liq_results = self.orchestrator.run_comprehensive_validation(
                options_data=excellent_options_data,
                ticker="SPY",
                expiration_date="2024-01-19",
                spot_price=420.15,
                asset_type="high_liquidity"
            )

            # Test low liquidity asset
            low_liq_results = self.orchestrator.run_comprehensive_validation(
                options_data=excellent_options_data,
                ticker="OBSCURE",
                expiration_date="2024-01-19",
                spot_price=420.15,
                asset_type="low_liquidity"
            )

        # Both should succeed but with different processing modes
        assert high_liq_results['consolidated_recommendations']['can_proceed'] is True
        assert low_liq_results['consolidated_recommendations']['can_proceed'] is True

        # High liquidity should allow more advanced analysis
        high_liq_mode = high_liq_results['consolidated_recommendations']['processing_mode']
        low_liq_mode = low_liq_results['consolidated_recommendations']['processing_mode']

        analysis_modes_hierarchy = ['basic_analysis', 'standard_analysis', 'full_analysis', 'enhanced_analysis']
        high_liq_index = analysis_modes_hierarchy.index(high_liq_mode) if high_liq_mode in analysis_modes_hierarchy else -1
        low_liq_index = analysis_modes_hierarchy.index(low_liq_mode) if low_liq_mode in analysis_modes_hierarchy else -1

        if high_liq_index >= 0 and low_liq_index >= 0:
            assert high_liq_index >= low_liq_index

    def test_analysis_gate_decision_logic(self, excellent_options_data, poor_options_data, finviz_data):
        """Test analysis gate decision making logic."""
        with patch('analytics.validation_integration.get_finviz_data') as mock_finviz:
            mock_finviz.return_value = finviz_data

            # Test with excellent data
            excellent_results = self.orchestrator.run_comprehensive_validation(
                options_data=excellent_options_data,
                ticker="SPY",
                expiration_date="2024-01-19",
                spot_price=420.15
            )

            excellent_gate = self.orchestrator.get_analysis_gate_decision(excellent_results)

            # Test with poor data
            poor_results = self.orchestrator.run_comprehensive_validation(
                options_data=poor_options_data,
                ticker="TEST",
                expiration_date="2024-01-19",
                spot_price=420.00
            )

            poor_gate = self.orchestrator.get_analysis_gate_decision(poor_results)

        # Excellent data should get approval
        assert excellent_gate['gate_decision'] == 'APPROVE'
        assert excellent_gate['allow_analysis'] is True
        assert excellent_gate['processing_mode'] in ['full_analysis', 'enhanced_analysis']

        # Poor data should be rejected or heavily restricted
        if poor_gate['gate_decision'] == 'APPROVE':
            assert poor_gate['processing_mode'] in ['basic_analysis', 'limited_analysis']
            assert len(poor_gate.get('restrictions', [])) >= 3
        else:
            assert poor_gate['gate_decision'] in ['REJECT', 'APPROVE_WITH_CAUTION']
            assert poor_gate['allow_analysis'] is False

    def test_focus_strikes_identification(self, excellent_options_data, finviz_data):
        """Test that focus strikes are correctly identified."""
        with patch('analytics.validation_integration.get_finviz_data') as mock_finviz:
            mock_finviz.return_value = finviz_data

            results = self.orchestrator.run_comprehensive_validation(
                options_data=excellent_options_data,
                ticker="SPY",
                expiration_date="2024-01-19",
                spot_price=420.15
            )

        gate_decision = self.orchestrator.get_analysis_gate_decision(results)

        # Should identify focus strikes
        assert 'focus_strikes' in gate_decision
        focus_strikes = gate_decision['focus_strikes']

        # Should include ATM and nearby strikes
        assert len(focus_strikes) >= 2
        assert any(abs(float(strike) - 420.15) <= 10 for strike in focus_strikes)

    def test_validation_error_handling(self):
        """Test error handling when validation components fail."""
        # Test with invalid data that causes validation errors
        invalid_data = {"invalid": "structure"}

        results = self.orchestrator.run_comprehensive_validation(
            options_data=invalid_data,
            ticker="TEST",
            expiration_date="2024-01-19",
            spot_price=420.00
        )

        # Should handle gracefully
        assert 'validation_summary' in results
        assert results['validation_summary']['integration_status'] in ['error', 'partial']

        # Should provide fallback recommendations
        if 'consolidated_recommendations' in results:
            recommendations = results['consolidated_recommendations']
            assert recommendations['can_proceed'] is False or len(recommendations.get('restrictions', [])) >= 5

    def test_quality_threshold_enforcement(self, finviz_data):
        """Test that quality thresholds are properly enforced."""
        # Create data that's just below threshold
        marginal_data = {
            "420": {
                "call": {
                    "bid": 8.00, "ask": 8.50, "last": 8.25, "model_price": 8.30,  # 6% spread
                    "delta": 0.52, "gamma": 0.015, "theta": -0.18, "vega": None, "rho": None,  # Missing Greeks
                    "volume": 12, "open_interest": 120,  # Just above minimum thresholds
                    "iv": 0.20, "price_vs_model_pct": 2.0
                }
            }
        }

        with patch('analytics.validation_integration.get_finviz_data') as mock_finviz:
            mock_finviz.return_value = finviz_data

            # Test with high threshold
            high_threshold_results = self.orchestrator.run_comprehensive_validation(
                options_data=marginal_data,
                ticker="SPY",
                expiration_date="2024-01-19",
                spot_price=420.00,
                min_quality_threshold=0.8
            )

            # Test with low threshold
            low_threshold_results = self.orchestrator.run_comprehensive_validation(
                options_data=marginal_data,
                ticker="SPY",
                expiration_date="2024-01-19",
                spot_price=420.00,
                min_quality_threshold=0.3
            )

        # High threshold should be more restrictive
        high_recommendations = high_threshold_results['consolidated_recommendations']
        low_recommendations = low_threshold_results['consolidated_recommendations']

        # Low threshold should be more permissive
        assert low_recommendations['can_proceed'] is True or high_recommendations['can_proceed'] is False

    def test_consolidated_recommendations_quality(self, excellent_options_data, finviz_data):
        """Test that consolidated recommendations are comprehensive and actionable."""
        with patch('analytics.validation_integration.get_finviz_data') as mock_finviz:
            mock_finviz.return_value = finviz_data

            results = self.orchestrator.run_comprehensive_validation(
                options_data=excellent_options_data,
                ticker="SPY",
                expiration_date="2024-01-19",
                spot_price=420.15
            )

        recommendations = results['consolidated_recommendations']

        # Should have all required fields
        required_fields = [
            'can_proceed', 'processing_mode', 'confidence_level',
            'recommended_strategies', 'restrictions', 'improvement_recommendations'
        ]

        for field in required_fields:
            assert field in recommendations

        # Recommended strategies should be appropriate for data quality
        assert len(recommendations['recommended_strategies']) >= 1

        # Should have minimal restrictions with excellent data
        assert len(recommendations['restrictions']) <= 2

        # Improvement recommendations should be minimal with excellent data
        assert len(recommendations['improvement_recommendations']) <= 3


class TestValidationIntegrationFunction:
    """Test the main validation integration function."""

    def test_validate_options_for_analysis_success(self, excellent_options_data, finviz_data):
        """Test the main validation function with excellent data."""
        with patch('analytics.validation_integration.get_finviz_data') as mock_finviz:
            mock_finviz.return_value = finviz_data

            results = validate_options_for_analysis(
                options_data=excellent_options_data,
                ticker="SPY",
                expiration_date="2024-01-19",
                spot_price=420.15,
                asset_type="high_liquidity",
                validation_mode="standard",
                min_quality_threshold=0.5
            )

        # Should have all expected top-level components
        expected_components = [
            'validation_summary', 'data_quality_metrics', 'consolidated_recommendations',
            'processing_decisions', 'gate_decision', 'strike_analysis'
        ]

        for component in expected_components:
            assert component in results

        # Gate decision should approve analysis
        gate = results['gate_decision']
        assert gate['gate_decision'] == 'APPROVE'
        assert gate['allow_analysis'] is True

        # Should provide specific processing guidance
        assert 'processing_mode' in gate
        assert 'focus_strikes' in gate

    def test_validate_options_for_analysis_failure(self, poor_options_data):
        """Test the main validation function with poor data."""
        results = validate_options_for_analysis(
            options_data=poor_options_data,
            ticker="TEST",
            expiration_date="2024-01-19",
            spot_price=420.00,
            asset_type="low_liquidity",
            validation_mode="strict",
            min_quality_threshold=0.7
        )

        # Should complete but reject or severely restrict
        assert 'gate_decision' in results
        gate = results['gate_decision']

        if gate['gate_decision'] == 'APPROVE':
            # If approved, should be with severe restrictions
            assert gate['processing_mode'] in ['basic_analysis', 'limited_analysis']
            assert len(gate.get('restrictions', [])) >= 3
        else:
            assert gate['gate_decision'] in ['REJECT', 'APPROVE_WITH_CAUTION']

        # Should provide improvement recommendations
        recommendations = results['consolidated_recommendations']
        assert len(recommendations['improvement_recommendations']) >= 3

    def test_validate_options_for_analysis_edge_cases(self):
        """Test the main validation function with edge cases."""
        # Empty data
        empty_results = validate_options_for_analysis(
            options_data={},
            ticker="SPY",
            expiration_date="2024-01-19",
            spot_price=420.00
        )

        assert empty_results['gate_decision']['gate_decision'] == 'REJECT'
        assert empty_results['gate_decision']['allow_analysis'] is False

        # Invalid parameters
        with pytest.raises(ValueError):
            validate_options_for_analysis(
                options_data={},
                ticker="",  # Empty ticker
                expiration_date="invalid-date",
                spot_price=0.0
            )

    def test_validate_options_for_analysis_performance(self, excellent_options_data):
        """Test that validation completes within reasonable time."""
        import time

        start_time = time.time()

        results = validate_options_for_analysis(
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="2024-01-19",
            spot_price=420.15
        )

        end_time = time.time()
        processing_time = end_time - start_time

        # Should complete within 10 seconds (generous for testing)
        assert processing_time < 10.0

        # Should have processing time metadata
        assert 'processing_time_seconds' in results
        assert results['processing_time_seconds'] > 0


class TestValidationComponentIntegration:
    """Test integration between different validation components."""

    def test_core_and_enhanced_validation_consistency(self, excellent_options_data):
        """Test that core and enhanced validation results are consistent."""
        orchestrator = ValidationOrchestrator()

        results = orchestrator.run_comprehensive_validation(
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="2024-01-19",
            spot_price=420.15
        )

        core_validation = results['validation_summary']['core_validation']
        enhanced_validation = results['validation_summary']['enhanced_validation']

        # Both should complete successfully with excellent data
        assert core_validation['status'] == 'completed'
        assert enhanced_validation['status'] == 'completed'

        # Quality scores should be reasonably consistent
        if 'overall_quality_score' in core_validation and 'quality_score' in enhanced_validation:
            core_score = core_validation['overall_quality_score']
            enhanced_score = enhanced_validation['quality_score']

            # Should be within reasonable range of each other
            assert abs(core_score - enhanced_score) <= 0.3

    def test_validation_pipeline_error_propagation(self):
        """Test that errors in one validation component don't break the entire pipeline."""
        orchestrator = ValidationOrchestrator()

        # Create data that might cause issues in specific validators
        problematic_data = {
            "420": {
                "call": {
                    "bid": float('inf'), "ask": 8.40, "last": 8.30, "model_price": 8.32,
                    "delta": 0.52, "gamma": float('nan'), "theta": -0.18, "vega": 0.45, "rho": 0.15,
                    "volume": -100, "open_interest": 5000  # Negative volume
                }
            }
        }

        results = orchestrator.run_comprehensive_validation(
            options_data=problematic_data,
            ticker="TEST",
            expiration_date="2024-01-19",
            spot_price=420.00
        )

        # Should handle gracefully and still provide results
        assert 'validation_summary' in results
        assert 'consolidated_recommendations' in results

        # Should indicate issues but not crash
        integration_status = results['validation_summary']['integration_status']
        assert integration_status in ['completed', 'partial', 'error']


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main([__file__, "-v"])