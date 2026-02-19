"""
Comprehensive Test Suite for Validated Analysis Service

This module tests the validated analysis service that integrates data validation
with options analysis, including quality threshold scenarios, error handling,
and analysis recommendations based on data quality.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import date, datetime
from typing import Dict, Any

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Create services directory if it doesn't exist
services_dir = os.path.dirname(__file__)
if not os.path.exists(services_dir):
    os.makedirs(services_dir)

from services.validated_analysis_service import ValidatedAnalysisService


class TestValidatedAnalysisService:
    """Test validated analysis service with comprehensive scenarios."""

    def setup_method(self):
        """Set up test environment."""
        self.service = ValidatedAnalysisService()

    @pytest.fixture
    def excellent_analysis_result(self):
        """Mock excellent analysis result from core analysis service."""
        return {
            'status': 'success',
            'market_context': {
                'current_price': 420.15,
                'price_change': 2.35,
                'price_change_pct': 0.56,
                'volume': 85000000,
                'market_trend': 'bullish'
            },
            'options_positioning': {
                'greeks_by_strike': {
                    '410': {
                        'call': {
                            'bid': 15.20, 'ask': 15.40, 'last': 15.30, 'model_price': 15.32,
                            'delta': 0.75, 'gamma': 0.010, 'theta': -0.15, 'vega': 0.40, 'rho': 0.20,
                            'volume': 800, 'open_interest': 3000
                        },
                        'put': {
                            'bid': 5.80, 'ask': 6.00, 'last': 5.90, 'model_price': 5.88,
                            'delta': -0.25, 'gamma': 0.010, 'theta': -0.12, 'vega': 0.40, 'rho': -0.15,
                            'volume': 600, 'open_interest': 2200
                        }
                    },
                    '420': {
                        'call': {
                            'bid': 8.20, 'ask': 8.40, 'last': 8.30, 'model_price': 8.32,
                            'delta': 0.52, 'gamma': 0.015, 'theta': -0.18, 'vega': 0.45, 'rho': 0.15,
                            'volume': 2000, 'open_interest': 8000
                        },
                        'put': {
                            'bid': 7.80, 'ask': 8.00, 'last': 7.90, 'model_price': 7.88,
                            'delta': -0.48, 'gamma': 0.015, 'theta': -0.16, 'vega': 0.45, 'rho': -0.22,
                            'volume': 1800, 'open_interest': 7200
                        }
                    }
                },
                'total_call_volume': 2800,
                'total_put_volume': 2400,
                'put_call_ratio': 0.86,
                'max_pain': 418.0
            },
            'gpt_verdict': {
                'recommendation': 'BUY',
                'confidence': 0.85,
                'reasoning': 'Strong bullish signals with excellent data quality',
                'risk_assessment': 'MODERATE',
                'position_sizing': 'FULL'
            }
        }

    @pytest.fixture
    def poor_analysis_result(self):
        """Mock poor analysis result with data quality issues."""
        return {
            'status': 'success_with_warnings',
            'market_context': {
                'current_price': 420.00,
                'volume': 15000000  # Lower volume
            },
            'options_positioning': {
                'greeks_by_strike': {
                    '420': {
                        'call': {
                            'bid': None, 'ask': 8.40, 'last': None, 'model_price': None,
                            'delta': None, 'gamma': None, 'theta': -50.0, 'vega': None, 'rho': None,
                            'volume': 3, 'open_interest': 20
                        }
                    }
                },
                'total_call_volume': 3,
                'total_put_volume': 0,
                'data_quality_warnings': [
                    'Missing critical pricing data',
                    'Incomplete Greeks calculations',
                    'Very low liquidity detected'
                ]
            },
            'gpt_verdict': {
                'recommendation': 'HOLD',
                'confidence': 0.35,
                'reasoning': 'Limited data quality affects confidence',
                'risk_assessment': 'HIGH',
                'data_quality_concerns': True
            }
        }

    @pytest.fixture
    def mock_validation_results(self):
        """Mock comprehensive validation results."""
        return {
            'validation_summary': {
                'integration_status': 'completed',
                'core_validation': {
                    'status': 'completed',
                    'overall_quality_score': 0.85
                },
                'enhanced_validation': {
                    'status': 'completed',
                    'quality_score': 0.82
                },
                'cross_source_validation': {
                    'status': 'completed',
                    'consistency_score': 0.90
                }
            },
            'data_quality_metrics': {
                'consolidated_quality_score': 0.86,
                'confidence_level': 'high',
                'processing_mode': 'full_analysis'
            },
            'consolidated_recommendations': {
                'can_proceed': True,
                'processing_mode': 'full_analysis',
                'confidence_level': 'high',
                'recommended_strategies': ['covered_call', 'bull_call_spread', 'long_call'],
                'restrictions': [],
                'improvement_recommendations': []
            },
            'processing_decisions': {
                'gate_decision': 'APPROVE',
                'allow_analysis': True,
                'processing_mode': 'full_analysis'
            },
            'gate_decision': {
                'gate_decision': 'APPROVE',
                'allow_analysis': True,
                'processing_mode': 'full_analysis',
                'focus_strikes': ['410', '420', '430']
            }
        }

    @pytest.fixture
    def mock_poor_validation_results(self):
        """Mock poor validation results."""
        return {
            'validation_summary': {
                'integration_status': 'completed',
                'core_validation': {
                    'status': 'completed',
                    'overall_quality_score': 0.25
                },
                'enhanced_validation': {
                    'status': 'completed',
                    'quality_score': 0.30
                },
                'cross_source_validation': {
                    'status': 'error'
                }
            },
            'data_quality_metrics': {
                'consolidated_quality_score': 0.28,
                'confidence_level': 'very_low',
                'processing_mode': 'basic_analysis'
            },
            'consolidated_recommendations': {
                'can_proceed': False,
                'processing_mode': 'basic_analysis',
                'confidence_level': 'very_low',
                'recommended_strategies': [],
                'restrictions': [
                    'Limited to basic analysis only',
                    'No complex strategy recommendations',
                    'High uncertainty in results'
                ],
                'improvement_recommendations': [
                    'Improve data source quality',
                    'Wait for better market conditions',
                    'Use alternative analysis methods'
                ]
            },
            'processing_decisions': {
                'gate_decision': 'REJECT',
                'allow_analysis': False,
                'rejection_reason': 'Data quality below minimum threshold'
            },
            'gate_decision': {
                'gate_decision': 'REJECT',
                'allow_analysis': False,
                'rejection_reason': 'Data quality below minimum threshold'
            }
        }

    @pytest.mark.asyncio
    async def test_validated_analysis_success_high_quality(self, excellent_analysis_result, mock_validation_results):
        """Test successful validated analysis with high-quality data."""
        with patch('analytics.validation_integration.validate_options_for_analysis') as mock_validate, \
             patch('services.analysis_service.run_full_analysis') as mock_analysis:

            mock_validate.return_value = mock_validation_results
            mock_analysis.return_value = excellent_analysis_result

            result = await self.service.run_validated_analysis(
                ticker="SPY",
                expiration_date=date(2024, 1, 19),
                r_current=0.045,
                methodology="holistic-market-edge",
                gpt_model="gpt-5",
                validation_mode="standard",
                min_quality_threshold=0.5
            )

        # Should succeed and return comprehensive results
        assert result['status'] == 'success'
        assert result['validation_status'] == 'completed'

        # Should include validation metadata
        assert 'validation_report' in result
        assert 'quality_metrics' in result
        assert result['quality_metrics']['consolidated_quality_score'] == 0.86

        # Should include enhanced analysis results
        assert 'analysis_results' in result
        assert result['analysis_results']['market_context']['current_price'] == 420.15

        # Should have validation-enhanced recommendations
        assert 'validation_enhanced_recommendations' in result
        enhanced_recs = result['validation_enhanced_recommendations']
        assert len(enhanced_recs) >= 1
        assert any('high quality data' in rec.lower() for rec in enhanced_recs)

    @pytest.mark.asyncio
    async def test_validated_analysis_rejection_poor_quality(self, mock_poor_validation_results):
        """Test analysis rejection due to poor data quality."""
        with patch('analytics.validation_integration.validate_options_for_analysis') as mock_validate:
            mock_validate.return_value = mock_poor_validation_results

            result = await self.service.run_validated_analysis(
                ticker="TEST",
                expiration_date=date(2024, 1, 19),
                r_current=0.045,
                methodology="holistic-market-edge",
                validation_mode="strict",
                min_quality_threshold=0.7
            )

        # Should reject analysis
        assert result['status'] == 'rejected'
        assert result['error_type'] == 'validation_gate_failure'
        assert result['validation_status'] == 'failed'

        # Should provide detailed explanation
        assert 'message' in result
        assert 'validation_report' in result
        assert 'recommendations' in result

        # Should suggest improvements
        recommendations = result['recommendations']
        assert len(recommendations) >= 3
        assert any('improve data' in rec.lower() for rec in recommendations)

    @pytest.mark.asyncio
    async def test_validated_analysis_with_caution(self):
        """Test analysis that proceeds with caution due to moderate data quality."""
        # Create moderate quality validation results
        moderate_validation = {
            'validation_summary': {
                'integration_status': 'completed',
                'core_validation': {
                    'status': 'completed',
                    'overall_quality_score': 0.65
                }
            },
            'data_quality_metrics': {
                'consolidated_quality_score': 0.62,
                'confidence_level': 'medium',
                'processing_mode': 'standard_analysis'
            },
            'consolidated_recommendations': {
                'can_proceed': True,
                'processing_mode': 'standard_analysis',
                'confidence_level': 'medium',
                'recommended_strategies': ['covered_call', 'long_call'],
                'restrictions': ['Avoid complex strategies', 'Monitor data quality closely'],
                'improvement_recommendations': ['Verify Greeks calculations']
            },
            'gate_decision': {
                'gate_decision': 'APPROVE_WITH_CAUTION',
                'allow_analysis': True,
                'processing_mode': 'standard_analysis'
            }
        }

        moderate_analysis = {
            'status': 'success_with_warnings',
            'market_context': {'current_price': 420.00},
            'options_positioning': {
                'greeks_by_strike': {
                    '420': {
                        'call': {
                            'delta': 0.5, 'volume': 100, 'open_interest': 500
                        }
                    }
                }
            },
            'gpt_verdict': {
                'recommendation': 'HOLD',
                'confidence': 0.65,
                'data_quality_adjusted': True
            }
        }

        with patch('analytics.validation_integration.validate_options_for_analysis') as mock_validate, \
             patch('services.analysis_service.run_full_analysis') as mock_analysis:

            mock_validate.return_value = moderate_validation
            mock_analysis.return_value = moderate_analysis

            result = await self.service.run_validated_analysis(
                ticker="SPY",
                expiration_date=date(2024, 1, 19),
                r_current=0.045,
                validation_mode="standard",
                min_quality_threshold=0.5
            )

        # Should proceed but with warnings
        assert result['status'] == 'success'
        assert result['validation_status'] == 'completed_with_warnings'

        # Should have quality warnings
        assert 'quality_warnings' in result
        quality_warnings = result['quality_warnings']
        assert len(quality_warnings) >= 1

        # Should have restricted strategy recommendations
        validation_summary = result['validation_summary']
        assert len(validation_summary.get('restrictions', [])) >= 1

    @pytest.mark.asyncio
    async def test_cross_source_validation_integration(self, excellent_analysis_result):
        """Test integration with cross-source validation."""
        validation_with_cross_source = {
            'validation_summary': {
                'integration_status': 'completed',
                'cross_source_validation': {
                    'status': 'completed',
                    'finviz_consistency': 0.95,
                    'price_consistency': True,
                    'volume_consistency': True
                }
            },
            'data_quality_metrics': {
                'consolidated_quality_score': 0.90,
                'cross_source_boost': 0.05
            },
            'consolidated_recommendations': {
                'can_proceed': True,
                'processing_mode': 'enhanced_analysis'
            },
            'gate_decision': {
                'gate_decision': 'APPROVE',
                'allow_analysis': True,
                'processing_mode': 'enhanced_analysis'
            }
        }

        with patch('analytics.validation_integration.validate_options_for_analysis') as mock_validate, \
             patch('services.analysis_service.run_full_analysis') as mock_analysis:

            mock_validate.return_value = validation_with_cross_source
            mock_analysis.return_value = excellent_analysis_result

            result = await self.service.run_validated_analysis(
                ticker="SPY",
                expiration_date=date(2024, 1, 19),
                r_current=0.045,
                enable_cross_source_validation=True
            )

        # Should benefit from cross-source validation
        assert result['status'] == 'success'
        assert 'cross_source_validation' in result

        cross_source = result['cross_source_validation']
        assert cross_source['finviz_consistency'] == 0.95

        # Should have enhanced processing mode
        assert result['validation_summary']['processing_mode'] == 'enhanced_analysis'

    @pytest.mark.asyncio
    async def test_target_strategies_filtering(self, excellent_analysis_result, mock_validation_results):
        """Test analysis with target strategy filtering."""
        # Add strategy validation results
        strategy_validation = {
            'covered_call': {
                'gate_decision': 'APPROVE',
                'quality_score_vs_threshold': 0.85,
                'recommended_position_size_factor': 0.9
            },
            'iron_condor': {
                'gate_decision': 'APPROVE_WITH_CAUTION',
                'quality_score_vs_threshold': 0.75,
                'recommended_position_size_factor': 0.6
            },
            'short_straddle': {
                'gate_decision': 'REJECT',
                'quality_score_vs_threshold': 0.65,
                'recommended_position_size_factor': 0.0
            }
        }

        validation_with_strategies = {**mock_validation_results}
        validation_with_strategies['strategy_validation'] = strategy_validation

        with patch('analytics.validation_integration.validate_options_for_analysis') as mock_validate, \
             patch('services.analysis_service.run_full_analysis') as mock_analysis:

            mock_validate.return_value = validation_with_strategies
            mock_analysis.return_value = excellent_analysis_result

            result = await self.service.run_validated_analysis(
                ticker="SPY",
                expiration_date=date(2024, 1, 19),
                r_current=0.045,
                target_strategies=["covered_call", "iron_condor", "short_straddle"]
            )

        # Should filter strategies based on validation
        assert 'strategy_validation' in result
        assert 'filtered_strategies' in result

        filtered = result['filtered_strategies']
        assert 'approved' in filtered
        assert 'conditional' in filtered
        assert 'rejected' in filtered

        assert 'covered_call' in filtered['approved']
        assert 'iron_condor' in filtered['conditional']
        assert 'short_straddle' in filtered['rejected']

    @pytest.mark.asyncio
    async def test_validation_mode_effects(self, excellent_analysis_result):
        """Test different validation modes affect analysis."""
        base_validation = {
            'data_quality_metrics': {
                'consolidated_quality_score': 0.75
            },
            'consolidated_recommendations': {
                'can_proceed': True,
                'processing_mode': 'standard_analysis'
            },
            'gate_decision': {
                'gate_decision': 'APPROVE',
                'allow_analysis': True
            }
        }

        # Test strict mode
        strict_validation = {**base_validation}
        strict_validation['validation_mode_applied'] = 'strict'
        strict_validation['data_quality_metrics']['quality_adjustments'] = {
            'strict_mode_penalty': -0.1
        }

        # Test permissive mode
        permissive_validation = {**base_validation}
        permissive_validation['validation_mode_applied'] = 'permissive'
        permissive_validation['data_quality_metrics']['quality_adjustments'] = {
            'permissive_mode_boost': 0.1
        }

        with patch('analytics.validation_integration.validate_options_for_analysis') as mock_validate, \
             patch('services.analysis_service.run_full_analysis') as mock_analysis:

            mock_analysis.return_value = excellent_analysis_result

            # Test strict mode
            mock_validate.return_value = strict_validation
            strict_result = await self.service.run_validated_analysis(
                ticker="SPY",
                expiration_date=date(2024, 1, 19),
                validation_mode="strict"
            )

            # Test permissive mode
            mock_validate.return_value = permissive_validation
            permissive_result = await self.service.run_validated_analysis(
                ticker="SPY",
                expiration_date=date(2024, 1, 19),
                validation_mode="permissive"
            )

        # Should reflect different validation modes
        assert strict_result['validation_report']['validation_mode_applied'] == 'strict'
        assert permissive_result['validation_report']['validation_mode_applied'] == 'permissive'

    @pytest.mark.asyncio
    async def test_analysis_service_error_handling(self, mock_validation_results):
        """Test handling of analysis service errors."""
        with patch('analytics.validation_integration.validate_options_for_analysis') as mock_validate, \
             patch('services.analysis_service.run_full_analysis') as mock_analysis:

            mock_validate.return_value = mock_validation_results
            # Simulate analysis service error
            mock_analysis.side_effect = Exception("Analysis service failed")

            result = await self.service.run_validated_analysis(
                ticker="SPY",
                expiration_date=date(2024, 1, 19),
                r_current=0.045
            )

        # Should handle gracefully
        assert result['status'] == 'error'
        assert result['error_type'] == 'analysis_failure'
        assert 'Analysis service failed' in result['message']

        # Should still provide validation insights
        assert 'validation_report' in result
        assert 'recommendations' in result

    @pytest.mark.asyncio
    async def test_validation_service_error_handling(self):
        """Test handling of validation service errors."""
        with patch('analytics.validation_integration.validate_options_for_analysis') as mock_validate:
            # Simulate validation service error
            mock_validate.side_effect = Exception("Validation service failed")

            result = await self.service.run_validated_analysis(
                ticker="SPY",
                expiration_date=date(2024, 1, 19),
                r_current=0.045
            )

        # Should handle gracefully
        assert result['status'] == 'error'
        assert result['error_type'] == 'validation_failure'
        assert 'Validation service failed' in result['message']

        # Should provide fallback recommendations
        assert 'recommendations' in result
        recommendations = result['recommendations']
        assert len(recommendations) >= 1
        assert any('validation error' in rec.lower() for rec in recommendations)

    @pytest.mark.asyncio
    async def test_quality_threshold_enforcement(self, mock_validation_results):
        """Test quality threshold enforcement scenarios."""
        # Modify validation to be just below threshold
        low_quality_validation = {**mock_validation_results}
        low_quality_validation['data_quality_metrics']['consolidated_quality_score'] = 0.45
        low_quality_validation['consolidated_recommendations']['can_proceed'] = False
        low_quality_validation['gate_decision']['gate_decision'] = 'REJECT'
        low_quality_validation['gate_decision']['allow_analysis'] = False

        with patch('analytics.validation_integration.validate_options_for_analysis') as mock_validate:
            mock_validate.return_value = low_quality_validation

            # Test with high threshold (should reject)
            high_threshold_result = await self.service.run_validated_analysis(
                ticker="SPY",
                expiration_date=date(2024, 1, 19),
                min_quality_threshold=0.8
            )

            # Test with low threshold (might proceed)
            low_threshold_result = await self.service.run_validated_analysis(
                ticker="SPY",
                expiration_date=date(2024, 1, 19),
                min_quality_threshold=0.3
            )

        # High threshold should reject
        assert high_threshold_result['status'] == 'rejected'
        assert high_threshold_result['validation_status'] == 'failed'

        # Low threshold might proceed (depends on validation logic)
        # At minimum, should provide comprehensive feedback
        assert 'quality_metrics' in low_threshold_result
        assert 'recommendations' in low_threshold_result

    @pytest.mark.asyncio
    async def test_processing_time_tracking(self, excellent_analysis_result, mock_validation_results):
        """Test that processing time is properly tracked."""
        with patch('analytics.validation_integration.validate_options_for_analysis') as mock_validate, \
             patch('services.analysis_service.run_full_analysis') as mock_analysis:

            # Add delay to simulate processing time
            async def slow_validate(*args, **kwargs):
                await asyncio.sleep(0.1)
                return mock_validation_results

            async def slow_analysis(*args, **kwargs):
                await asyncio.sleep(0.1)
                return excellent_analysis_result

            mock_validate.side_effect = slow_validate
            mock_analysis.side_effect = slow_analysis

            result = await self.service.run_validated_analysis(
                ticker="SPY",
                expiration_date=date(2024, 1, 19),
                r_current=0.045
            )

        # Should track processing time
        assert 'processing_time_breakdown' in result
        breakdown = result['processing_time_breakdown']

        assert 'validation_time' in breakdown
        assert 'analysis_time' in breakdown
        assert 'total_time' in breakdown

        # Times should be reasonable
        assert breakdown['validation_time'] >= 0.1
        assert breakdown['analysis_time'] >= 0.1
        assert breakdown['total_time'] >= 0.2

    @pytest.mark.asyncio
    async def test_configuration_parameter_effects(self, excellent_analysis_result, mock_validation_results):
        """Test that service configuration parameters affect behavior."""
        # Configure service with specific settings
        self.service.default_validation_mode = 'strict'
        self.service.default_min_quality_threshold = 0.8
        self.service.enable_cross_source_validation = True
        self.service.enable_strategy_validation = True

        with patch('analytics.validation_integration.validate_options_for_analysis') as mock_validate, \
             patch('services.analysis_service.run_full_analysis') as mock_analysis:

            mock_validate.return_value = mock_validation_results
            mock_analysis.return_value = excellent_analysis_result

            result = await self.service.run_validated_analysis(
                ticker="SPY",
                expiration_date=date(2024, 1, 19),
                r_current=0.045
                # Note: not passing validation_mode, should use service default
            )

        # Should use service configuration
        mock_validate.assert_called_once()
        call_kwargs = mock_validate.call_args[1]

        assert call_kwargs['validation_mode'] == 'strict'
        assert call_kwargs['min_quality_threshold'] == 0.8

    @pytest.mark.asyncio
    async def test_comprehensive_validation_report_structure(self, excellent_analysis_result, mock_validation_results):
        """Test that validation reports have proper structure and completeness."""
        with patch('analytics.validation_integration.validate_options_for_analysis') as mock_validate, \
             patch('services.analysis_service.run_full_analysis') as mock_analysis:

            mock_validate.return_value = mock_validation_results
            mock_analysis.return_value = excellent_analysis_result

            result = await self.service.run_validated_analysis(
                ticker="SPY",
                expiration_date=date(2024, 1, 19),
                r_current=0.045,
                target_strategies=["covered_call", "bull_call_spread"]
            )

        # Should have comprehensive structure
        required_top_level_keys = [
            'status', 'validation_status', 'analysis_results', 'validation_report',
            'quality_metrics', 'validation_summary', 'validation_enhanced_recommendations'
        ]

        for key in required_top_level_keys:
            assert key in result, f"Missing required key: {key}"

        # Validation report should be comprehensive
        validation_report = result['validation_report']
        validation_report_keys = [
            'validation_summary', 'data_quality_metrics', 'consolidated_recommendations'
        ]

        for key in validation_report_keys:
            assert key in validation_report, f"Missing validation report key: {key}"

        # Quality metrics should have required fields
        quality_metrics = result['quality_metrics']
        assert 'consolidated_quality_score' in quality_metrics
        assert 'confidence_level' in quality_metrics


if __name__ == "__main__":
    # Create __init__.py if it doesn't exist
    init_file = os.path.join(os.path.dirname(__file__), '__init__.py')
    if not os.path.exists(init_file):
        with open(init_file, 'w') as f:
            f.write('# Services test package\n')

    # Run tests when executed directly
    pytest.main([__file__, "-v"])