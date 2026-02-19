"""
Comprehensive Test Suite for Enhanced Greeks System

This test suite validates all components of the enhanced Greeks calculation,
validation, and repair system including Finviz integration, comparison validation,
and hybrid Greeks generation.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from datetime import date, datetime, timedelta
import math

# Import the modules to test
from src.analytics.finviz_greeks_extractor import FinvizGreeksExtractor
from src.analytics.greeks_comparison_validator import GreeksComparisonValidator, GreeksSource
from src.analytics.greeks_repair import GreeksValidator, GreeksRepairResult
from src.analytics.vega_optimizer import VegaOptimizer, get_optimized_vega
from src.services.enhanced_analysis_service import EnhancedAnalysisService


class TestFinvizGreeksExtractor:
    """Test the Finviz Greeks extraction functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.extractor = FinvizGreeksExtractor()

    def test_extract_greeks_from_empty_dataframe(self):
        """Test extraction from empty DataFrame."""
        empty_df = pd.DataFrame()
        result = self.extractor.extract_greeks_from_finviz(empty_df)
        assert result == {}

    def test_extract_greeks_from_valid_finviz_data(self):
        """Test extraction from valid Finviz data."""
        # Create mock Finviz data
        finviz_data = pd.DataFrame({
            'Strike': [100, 105, 110],
            'Type': ['call', 'call', 'call'],
            'Delta': [0.6, 0.4, 0.2],
            'Gamma': [0.05, 0.06, 0.04],
            'Theta': [-0.02, -0.015, -0.01],
            'Vega': [0.25, 0.28, 0.20],
            'Rho': [0.15, 0.12, 0.08],
            'Bid': [5.0, 2.5, 1.0],
            'Ask': [5.5, 3.0, 1.5],
            'Volume': [100, 50, 25],
            'Open Int.': [500, 300, 150],
            'Last Close': [5.2, 2.8, 1.2],
            'IV': [0.25, 0.28, 0.30]
        })

        result = self.extractor.extract_greeks_from_finviz(finviz_data)

        # Validate structure
        assert len(result) == 3  # 3 strikes
        assert 100.0 in result
        assert 'call' in result[100.0]

        # Validate Greeks extraction
        call_100 = result[100.0]['call']
        assert call_100['delta'] == 0.6
        assert call_100['gamma'] == 0.05
        assert call_100['theta'] == -0.02
        assert call_100['vega'] == 0.25
        assert call_100['rho'] == 0.15

        # Validate market data extraction
        market_data = call_100['market_data']
        assert market_data['bid'] == 5.0
        assert market_data['ask'] == 5.5
        assert market_data['mid_price'] == 5.25
        assert market_data['volume'] == 100
        assert market_data['open_interest'] == 500

    def test_extract_greeks_with_mixed_option_types(self):
        """Test extraction with both calls and puts."""
        finviz_data = pd.DataFrame({
            'Strike': [100, 100],
            'Type': ['call', 'put'],
            'Delta': [0.6, -0.4],
            'Gamma': [0.05, 0.05],
            'Theta': [-0.02, -0.018],
            'Vega': [0.25, 0.25],
            'Rho': [0.15, -0.12],
            'Bid': [5.0, 3.0],
            'Ask': [5.5, 3.5],
            'Volume': [100, 80],
            'Open Int.': [500, 400]
        })

        result = self.extractor.extract_greeks_from_finviz(finviz_data)

        assert len(result) == 1  # 1 strike
        assert 100.0 in result
        assert 'call' in result[100.0]
        assert 'put' in result[100.0]

        # Validate call delta
        assert result[100.0]['call']['delta'] == 0.6
        # Validate put delta
        assert result[100.0]['put']['delta'] == -0.4

    def test_validate_finviz_greeks_quality(self):
        """Test Greeks validation functionality."""
        # Create test data with varying quality
        test_data = {
            100.0: {
                'call': {
                    'delta': 0.6, 'gamma': 0.05, 'theta': -0.02, 'vega': 0.25, 'rho': 0.15,
                    'market_data': {'bid': 5.0, 'ask': 5.5}
                }
            },
            105.0: {
                'call': {
                    'delta': None, 'gamma': 0.04, 'theta': -0.015, 'vega': None, 'rho': 0.12,
                    'market_data': {'bid': 2.0, 'ask': 2.8}
                }
            }
        }

        validation = self.extractor.validate_finviz_greeks(test_data)

        assert 'overall_quality' in validation
        assert 'strike_quality' in validation
        assert 'summary' in validation

        # Should have quality scores for both strikes
        assert 100.0 in validation['strike_quality']
        assert 105.0 in validation['strike_quality']

        # Strike 100 should have higher quality (complete data)
        assert validation['strike_quality'][100.0]['completeness_ratio'] > 0.9
        assert validation['strike_quality'][105.0]['completeness_ratio'] < 0.8


class TestGreeksComparisonValidator:
    """Test the Greeks comparison and validation functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.validator = GreeksComparisonValidator()

    def test_compare_greeks_comprehensive_basic(self):
        """Test basic comprehensive comparison."""
        finviz_data = {
            100.0: {
                'call': {'delta': 0.6, 'gamma': 0.05, 'theta': -0.02, 'vega': 0.25, 'rho': 0.15}
            }
        }

        calculated_data = {
            100.0: {
                'call': {'delta': 0.58, 'gamma': 0.052, 'theta': -0.021, 'vega': 0.24, 'rho': 0.14}
            }
        }

        result = self.validator.compare_greeks_comprehensive(finviz_data, calculated_data)

        assert 'metadata' in result
        assert 'quality_metrics' in result
        assert 'strike_comparisons' in result
        assert 'recommendations' in result

        assert result['metadata']['common_strikes'] == 1
        assert 100.0 in result['strike_comparisons']

    def test_determine_recommended_source_logic(self):
        """Test source recommendation logic."""
        # Test case where sources agree closely
        finviz_values = {'delta': 0.6, 'gamma': 0.05, 'theta': -0.02, 'vega': 0.25, 'rho': 0.15}
        calculated_values = {'delta': 0.59, 'gamma': 0.051, 'theta': -0.021, 'vega': 0.24, 'rho': 0.14}
        differences = {k: finviz_values[k] - calculated_values[k] for k in finviz_values.keys()}
        relative_differences = {k: differences[k]/abs(calculated_values[k]) if calculated_values[k] != 0 else None
                              for k in differences.keys()}

        source, confidence = self.validator._determine_recommended_source(
            finviz_values, calculated_values, differences, relative_differences, 'call', None
        )

        assert source in [GreeksSource.FINVIZ, GreeksSource.CALCULATED, GreeksSource.HYBRID]
        assert 0 <= confidence <= 1

    def test_create_hybrid_greeks(self):
        """Test hybrid Greeks creation."""
        finviz_data = {
            100.0: {
                'call': {'delta': 0.6, 'gamma': 0.05, 'theta': -0.02, 'vega': 0.25, 'rho': 0.15}
            }
        }

        calculated_data = {
            100.0: {
                'call': {'delta': 0.58, 'gamma': 0.052, 'theta': -0.021, 'vega': 0.24, 'rho': 0.14}
            }
        }

        # Mock comparison results
        comparison_results = {
            'recommendations': {
                'preferred_source_by_strike': {
                    '100.0_call': 'hybrid'
                }
            }
        }

        hybrid_greeks = self.validator.create_hybrid_greeks(
            finviz_data, calculated_data, comparison_results
        )

        assert 100.0 in hybrid_greeks
        assert 'call' in hybrid_greeks[100.0]

        # Hybrid delta should be average of the two sources
        expected_delta = (0.6 + 0.58) / 2
        assert abs(hybrid_greeks[100.0]['call']['delta'] - expected_delta) < 0.001


class TestGreeksValidator:
    """Test the Greeks validation and repair functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.validator = GreeksValidator()

    def test_validate_and_repair_complete_data(self):
        """Test validation of complete, high-quality data."""
        strike_data = {
            'call': {
                'delta': 0.6, 'gamma': 0.05, 'theta': -0.02, 'vega': 0.25, 'rho': 0.15,
                'market_price': 5.0, 'model_price': 5.2
            },
            'put': {
                'delta': -0.4, 'gamma': 0.05, 'theta': -0.018, 'vega': 0.25, 'rho': -0.12,
                'market_price': 3.0, 'model_price': 3.1
            }
        }

        result = self.validator.validate_and_repair_strike(
            strike=100.0,
            strike_data=strike_data,
            neighboring_strikes={},
            spot_price=100.0
        )

        assert isinstance(result, GreeksRepairResult)
        assert result.quality_score > 0.9  # Should be high quality
        assert result.confidence_score > 0.9
        assert len(result.repairs_made) == 0  # No repairs needed

    def test_validate_and_repair_missing_data(self):
        """Test validation and repair of incomplete data."""
        strike_data = {
            'call': {
                'delta': 0.6, 'gamma': None, 'theta': None, 'vega': None, 'rho': None,
                'market_price': 5.0, 'model_price': 5.2
            }
        }

        result = self.validator.validate_and_repair_strike(
            strike=100.0,
            strike_data=strike_data,
            neighboring_strikes={},
            spot_price=100.0,
            risk_free_rate=0.05,
            time_to_expiry=0.25
        )

        assert isinstance(result, GreeksRepairResult)
        assert len(result.repairs_made) > 0  # Should have made repairs
        assert len(result.fallback_fields) > 0  # Should have used fallbacks

        # Check that missing Greeks were filled
        call_data = result.repaired_data.get('call', {})
        assert call_data.get('gamma') is not None
        assert call_data.get('theta') is not None

    def test_theoretical_validity_checking(self):
        """Test theoretical validity constraints."""
        # Test call delta bounds
        assert self.validator._is_greek_theoretically_valid('delta', 0.6, 'call') == True
        assert self.validator._is_greek_theoretically_valid('delta', 1.2, 'call') == False
        assert self.validator._is_greek_theoretically_valid('delta', -0.1, 'call') == False

        # Test put delta bounds
        assert self.validator._is_greek_theoretically_valid('delta', -0.4, 'put') == True
        assert self.validator._is_greek_theoretically_valid('delta', 0.1, 'put') == False

        # Test gamma positivity
        assert self.validator._is_greek_theoretically_valid('gamma', 0.05, 'call') == True
        assert self.validator._is_greek_theoretically_valid('gamma', -0.01, 'call') == False


class TestVegaOptimizer:
    """Test the optimized Vega calculation functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.optimizer = VegaOptimizer()

    def test_calculate_vega_analytical(self):
        """Test analytical Vega calculation."""
        vega = self.optimizer._calculate_vega_analytical(
            S=100.0, K=100.0, r=0.05, T=0.25, sigma=0.25, div=0.0
        )

        assert vega is not None
        assert vega > 0  # Vega should be positive
        assert 0.01 < vega < 1.0  # Reasonable range

    def test_calculate_vega_fast_approximation(self):
        """Test fast Vega approximation."""
        vega = self.optimizer._calculate_vega_fast_approximation(
            S=100.0, K=100.0, r=0.05, T=0.25, sigma=0.25, option_type='call', div=0.0
        )

        assert vega is not None
        assert vega > 0

        # Test different moneyness levels
        vega_otm = self.optimizer._calculate_vega_fast_approximation(
            S=100.0, K=120.0, r=0.05, T=0.25, sigma=0.25, option_type='call', div=0.0
        )

        # ATM should have higher vega than OTM
        assert vega > vega_otm

    def test_calculate_vega_optimized_method_selection(self):
        """Test optimal method selection."""
        # Test ATM option - should prefer analytical
        method = self.optimizer._select_optimal_method(
            S=100.0, K=100.0, r=0.05, T=0.25, sigma=0.25, option_type='call'
        )
        assert method in ['analytical', 'fast_approximation']

        # Test very short expiry - should prefer fast approximation
        method = self.optimizer._select_optimal_method(
            S=100.0, K=100.0, r=0.05, T=0.01, sigma=0.25, option_type='call'
        )
        assert method == 'fast_approximation'

    def test_get_optimized_vega_convenience_function(self):
        """Test the convenience function for optimized Vega."""
        vega = get_optimized_vega(
            S=100.0, K=100.0, r=0.05, T=0.25, sigma=0.25, option_type='call'
        )

        assert vega is not None
        assert isinstance(vega, (int, float))
        assert vega > 0

    def test_vega_term_structure_calculation(self):
        """Test Vega calculation across term structure."""
        strikes = [95, 100, 105]
        expirations = [0.083, 0.25, 0.5]  # 1 month, 3 months, 6 months

        vega_surface = self.optimizer.calculate_vega_term_structure(
            S=100.0, strikes=strikes, r=0.05, expirations=expirations,
            sigma=0.25, option_type='call'
        )

        assert len(vega_surface) == 3  # 3 expirations
        for T in expirations:
            assert T in vega_surface
            assert len(vega_surface[T]) == 3  # 3 strikes
            for K in strikes:
                assert K in vega_surface[T]
                assert 'vega' in vega_surface[T][K]
                assert 'method' in vega_surface[T][K]


class TestEnhancedAnalysisService:
    """Test the enhanced analysis service integration."""

    def setup_method(self):
        """Setup test fixtures."""
        self.service = EnhancedAnalysisService()

    @patch('src.services.enhanced_analysis_service.get_finviz_greeks_for_analysis')
    @patch('src.services.enhanced_analysis_service.analyze_undervalued_options_with_greeks')
    async def test_analyze_options_enhanced_basic(self, mock_calculated_analysis, mock_finviz_greeks):
        """Test basic enhanced analysis workflow."""
        # Mock Finviz data
        mock_finviz_greeks.return_value = (
            {100.0: {'call': {'delta': 0.6, 'gamma': 0.05}}},
            {'overall_quality': 0.8}
        )

        # Mock calculated analysis
        mock_calculated_analysis.return_value = {
            'greeks_by_strike': {
                100.0: {'call': {'delta': 0.58, 'gamma': 0.052}}
            },
            'undervalued_options': []
        }

        result = await self.service.analyze_options_enhanced(
            ticker='AAPL',
            expiration_date='2024-12-20',
            use_hybrid_greeks=True
        )

        assert 'metadata' in result
        assert 'data_quality' in result
        assert 'options_analysis' in result
        assert result['metadata']['ticker'] == 'AAPL'
        assert result['metadata']['hybrid_greeks_used'] == True

    def test_extract_calculated_greeks(self):
        """Test extraction of calculated Greeks from analysis results."""
        calculated_analysis = {
            'greeks_by_strike': {
                '100': {'call': {'delta': 0.6}},
                '105': {'put': {'delta': -0.4}}
            }
        }

        extracted = self.service._extract_calculated_greeks(calculated_analysis)

        assert 100.0 in extracted
        assert 105.0 in extracted
        assert extracted[100.0]['call']['delta'] == 0.6

    def test_calculate_hybrid_quality_metrics(self):
        """Test hybrid quality metrics calculation."""
        analysis_results = {
            'strikes_analysis': {
                100.0: {
                    'quality_metrics': {
                        'quality_score': 0.9,
                        'confidence_score': 0.85
                    }
                },
                105.0: {
                    'quality_metrics': {
                        'quality_score': 0.7,
                        'confidence_score': 0.75
                    }
                }
            }
        }

        quality_metrics = self.service._calculate_hybrid_quality(analysis_results)

        assert quality_metrics['method'] == 'hybrid'
        assert quality_metrics['strikes_analyzed'] == 2
        assert abs(quality_metrics['overall_score'] - 0.8) < 0.01  # Average of 0.9 and 0.7

    def test_assess_overall_quality(self):
        """Test overall quality assessment logic."""
        # Test excellent quality
        analysis_results = {
            'data_quality': {
                'hybrid_quality': {'overall_score': 0.9}
            }
        }
        assessment = self.service._assess_overall_quality(analysis_results, 0.6)
        assert assessment == 'excellent'

        # Test poor quality
        analysis_results = {
            'data_quality': {
                'calculated_quality': {'overall_score': 0.4}
            }
        }
        assessment = self.service._assess_overall_quality(analysis_results, 0.6)
        assert assessment == 'poor'


class TestIntegrationScenarios:
    """Test end-to-end integration scenarios."""

    def setup_method(self):
        """Setup integration test fixtures."""
        self.extractor = FinvizGreeksExtractor()
        self.validator = GreeksComparisonValidator()
        self.repair_validator = GreeksValidator()

    def test_complete_workflow_high_quality_data(self):
        """Test complete workflow with high-quality data from both sources."""
        # Create high-quality Finviz data
        finviz_df = pd.DataFrame({
            'Strike': [100, 100, 105, 105],
            'Type': ['call', 'put', 'call', 'put'],
            'Delta': [0.6, -0.4, 0.35, -0.25],
            'Gamma': [0.05, 0.05, 0.04, 0.04],
            'Theta': [-0.02, -0.018, -0.015, -0.012],
            'Vega': [0.25, 0.25, 0.22, 0.22],
            'Rho': [0.15, -0.12, 0.10, -0.08],
            'Bid': [5.0, 3.0, 2.0, 1.5],
            'Ask': [5.5, 3.5, 2.5, 2.0]
        })

        # Extract Finviz Greeks
        finviz_greeks = self.extractor.extract_greeks_from_finviz(finviz_df)
        finviz_validation = self.extractor.validate_finviz_greeks(finviz_greeks)

        # Create similar calculated Greeks
        calculated_greeks = {
            100.0: {
                'call': {'delta': 0.58, 'gamma': 0.052, 'theta': -0.021, 'vega': 0.24, 'rho': 0.14},
                'put': {'delta': -0.42, 'gamma': 0.052, 'theta': -0.019, 'vega': 0.24, 'rho': -0.13}
            },
            105.0: {
                'call': {'delta': 0.36, 'gamma': 0.041, 'theta': -0.016, 'vega': 0.21, 'rho': 0.11},
                'put': {'delta': -0.26, 'gamma': 0.041, 'theta': -0.013, 'vega': 0.21, 'rho': -0.09}
            }
        }

        # Perform comparison
        comparison_results = self.validator.compare_greeks_comprehensive(
            finviz_greeks, calculated_greeks
        )

        # Create hybrid Greeks
        hybrid_greeks = self.validator.create_hybrid_greeks(
            finviz_greeks, calculated_greeks, comparison_results
        )

        # Validate results
        assert len(hybrid_greeks) == 2  # 2 strikes
        assert finviz_validation['overall_quality'] > 0.8
        assert comparison_results['metadata']['common_strikes'] == 2
        assert len(comparison_results['recommendations']['preferred_source_by_strike']) > 0

    def test_complete_workflow_low_quality_data(self):
        """Test complete workflow with low-quality data requiring extensive repair."""
        # Create poor-quality data with missing Greeks
        incomplete_data = {
            100.0: {
                'call': {'delta': 0.6, 'gamma': None, 'theta': None, 'vega': None, 'rho': None}
            }
        }

        # Apply repair validation
        repair_result = self.repair_validator.validate_and_repair_strike(
            strike=100.0,
            strike_data=incomplete_data,
            neighboring_strikes={},
            spot_price=100.0
        )

        # Validate repair was performed
        assert len(repair_result.repairs_made) > 0
        assert len(repair_result.fallback_fields) > 0
        assert repair_result.recommended_usage in ['low_confidence', 'medium_confidence', 'avoid']

        # Ensure repaired data is structurally complete
        call_data = repair_result.repaired_data.get('call', {})
        for greek in ['delta', 'gamma', 'theta', 'vega', 'rho']:
            assert call_data.get(greek) is not None


if __name__ == '__main__':
    pytest.main([__file__])