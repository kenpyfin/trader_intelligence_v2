"""
Tests for Enhanced Greeks Validation System

Tests the intelligent repair mechanisms, interpolation algorithms, and fallback
strategies for partial Greeks data scenarios common with SPY options.
"""

import pytest
import math
from src.analytics.greeks_repair import GreeksValidator, GreeksRepairResult
from src.analytics.enhanced_greeks_validation import EnhancedGreeksValidator


class TestGreeksValidator:
    """Test the core Greeks repair validator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = GreeksValidator()

    def test_clean_existing_greeks_valid_data(self):
        """Test cleaning of valid Greeks data."""
        option_data = {
            'delta': 0.5,
            'gamma': 0.1,
            'theta': -0.02,
            'vega': 0.2,
            'rho': 0.05,
            'market_price': 10.5,
            'model_price': 11.0
        }

        result = self.validator._clean_existing_greeks(option_data, 'call', 380.0)

        assert len(result['data']) == 7
        assert result['data']['delta'] == 0.5
        assert len(result['repairs']) == 0

    def test_clean_existing_greeks_invalid_data(self):
        """Test cleaning of invalid Greeks data."""
        option_data = {
            'delta': float('nan'),
            'gamma': -0.1,  # Invalid: gamma should be positive
            'theta': -0.02,
            'vega': float('inf'),
            'rho': 'invalid',
            'market_price': 10.5
        }

        result = self.validator._clean_existing_greeks(option_data, 'call', 380.0)

        # Should only keep valid theta and market_price
        assert len(result['data']) == 2
        assert 'theta' in result['data']
        assert 'market_price' in result['data']
        assert len(result['repairs']) >= 3  # Multiple repairs needed

    def test_validate_greek_range_delta(self):
        """Test delta range validation."""
        # Valid call delta
        assert self.validator._validate_greek_range('delta', 0.5, 'call')
        assert self.validator._validate_greek_range('delta', 0.0, 'call')
        assert self.validator._validate_greek_range('delta', 1.0, 'call')

        # Invalid call delta
        assert not self.validator._validate_greek_range('delta', -0.1, 'call')
        assert not self.validator._validate_greek_range('delta', 1.1, 'call')

        # Valid put delta
        assert self.validator._validate_greek_range('delta', -0.5, 'put')
        assert self.validator._validate_greek_range('delta', -1.0, 'put')
        assert self.validator._validate_greek_range('delta', 0.0, 'put')

        # Invalid put delta
        assert not self.validator._validate_greek_range('delta', 0.1, 'put')
        assert not self.validator._validate_greek_range('delta', -1.1, 'put')

    def test_interpolate_missing_greeks(self):
        """Test interpolation of missing Greeks from neighbors."""
        # Current strike with missing delta
        option_data = {'gamma': 0.1, 'vega': 0.2}

        # Neighboring strikes with delta data
        neighbors = {
            375.0: {'call': {'delta': 0.6, 'gamma': 0.12}},
            385.0: {'call': {'delta': 0.4, 'gamma': 0.08}}
        }

        result = self.validator._interpolate_missing_greeks(
            strike=380.0,
            option_type='call',
            option_data=option_data,
            neighboring_strikes=neighbors
        )

        # Should interpolate delta = 0.5 (midpoint between 0.6 and 0.4)
        assert 'delta' in result['data']
        assert abs(result['data']['delta'] - 0.5) < 0.01
        assert 'call_delta' in result['interpolated']

    def test_calculate_rho_from_delta(self):
        """Test rho calculation from delta."""
        # Call option
        rho = self.validator._calculate_rho_from_delta(
            delta=0.5, strike=100.0, spot_price=100.0,
            time_to_expiry=0.25, option_type='call'
        )

        assert rho is not None
        assert rho > 0  # Call rho should be positive
        assert abs(rho) < 10  # Reasonable magnitude

        # Put option
        rho = self.validator._calculate_rho_from_delta(
            delta=-0.5, strike=100.0, spot_price=100.0,
            time_to_expiry=0.25, option_type='put'
        )

        assert rho is not None
        assert rho < 0  # Put rho should be negative

    def test_apply_fallback_values(self):
        """Test fallback value generation."""
        # Empty option data
        option_data = {}

        result = self.validator._apply_fallback_values(
            strike=100.0, option_type='call', option_data=option_data, spot_price=100.0
        )

        # Should have fallback values for all required Greeks
        assert 'delta' in result['data']
        assert 'gamma' in result['data']
        assert 'vega' in result['data']
        assert 'theta' in result['data']
        assert 'rho' in result['data']

        # Validate reasonable fallback values
        assert 0 <= result['data']['delta'] <= 1  # Call delta range
        assert result['data']['gamma'] >= 0  # Gamma always positive
        assert result['data']['vega'] >= 0  # Vega always positive
        assert result['data']['theta'] < 0  # Theta usually negative for long positions
        assert result['data']['rho'] > 0  # Call rho positive

    def test_comprehensive_strike_repair(self):
        """Test comprehensive repair of a strike with partial data."""
        strike_data = {
            'call': {
                'delta': 0.5,
                'market_price': 10.0,
                # Missing gamma, theta, vega, rho, model_price
            },
            'put': {
                'gamma': 0.1,
                'market_price': 8.0
                # Missing delta, theta, vega, rho, model_price
            }
        }

        neighbors = {
            375.0: {
                'call': {'delta': 0.6, 'gamma': 0.12, 'vega': 0.25},
                'put': {'delta': -0.4, 'gamma': 0.12, 'vega': 0.25}
            },
            385.0: {
                'call': {'delta': 0.4, 'gamma': 0.08, 'vega': 0.15},
                'put': {'delta': -0.6, 'gamma': 0.08, 'vega': 0.15}
            }
        }

        result = self.validator.validate_and_repair_strike(
            strike=380.0,
            strike_data=strike_data,
            neighboring_strikes=neighbors,
            spot_price=380.0,
            risk_free_rate=0.05,
            time_to_expiry=0.25,
            implied_vol=0.20
        )

        # Check that both call and put have all required Greeks
        for option_type in ['call', 'put']:
            option_data = result.repaired_data[option_type]
            for greek in self.validator.required_greeks:
                assert greek in option_data, f"Missing {greek} for {option_type}"
                assert option_data[greek] is not None, f"{greek} is None for {option_type}"

        # Check that quality and confidence scores are reasonable
        assert 0 <= result.quality_score <= 1
        assert 0 <= result.confidence_score <= 1
        assert len(result.repairs_made) > 0  # Should have made some repairs


class TestEnhancedGreeksValidator:
    """Test the enhanced Greeks validation system."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = EnhancedGreeksValidator()

    def test_spy_partial_data_scenario(self):
        """Test SPY scenario with partial Greeks data."""
        # Simulate SPY data with missing rho and some missing vega
        spy_greeks = {}
        strikes = [370, 375, 380, 385, 390, 395, 400]

        for i, strike in enumerate(strikes):
            strike_data = {
                'call': {
                    'delta': 0.8 - (i * 0.1),
                    'gamma': 0.1 if i % 2 == 0 else None,  # Missing gamma on odd strikes
                    'theta': -0.02,
                    'vega': 0.2 if i < 5 else None,  # Missing vega on far OTM
                    # rho missing for all strikes
                    'market_price': 15.0 - (i * 2),
                    'model_price': 16.0 - (i * 2)
                },
                'put': {
                    'delta': -0.2 - (i * 0.1),
                    'gamma': 0.1 if i % 2 == 0 else None,  # Missing gamma on odd strikes
                    'theta': -0.01,
                    'vega': 0.18 if i < 4 else None,  # Missing vega on far OTM
                    # rho missing for all strikes
                    'market_price': 8.0 + (i * 1.5),
                    'model_price': 8.5 + (i * 1.5)
                }
            }
            spy_greeks[str(strike)] = strike_data

        # Run enhanced validation
        result = self.validator.validate_and_enhance_greeks_data(
            greeks_by_strike=spy_greeks,
            spot_price=385.0,
            risk_free_rate=0.05,
            time_to_expiry=0.25,
            implied_vol=0.20
        )

        # Should have improved quality significantly
        assert result.enhanced_quality_score > result.original_quality_score
        assert result.enhanced_quality_score > 0.6  # Should achieve good quality

        # Should have repaired missing fields
        assert result.repaired_strikes_count > 0
        assert result.interpolated_strikes_count > 0  # Some gamma/vega interpolated
        assert result.fallback_strikes_count > 0  # Rho fallbacks

        # Should categorize strikes appropriately
        assert len(result.excellent_strikes) + len(result.good_strikes) > len(result.poor_strikes)

    def test_create_validation_summary(self):
        """Test creation of validation summary."""
        # Create a mock result
        from src.analytics.enhanced_greeks_validation import EnhancedGreeksValidationResult

        mock_result = EnhancedGreeksValidationResult(
            valid_strikes_count=10,
            complete_strikes_count=6,
            partially_complete_strikes_count=3,
            repaired_strikes_count=7,
            interpolated_strikes_count=4,
            fallback_strikes_count=5,
            original_quality_score=0.4,
            enhanced_quality_score=0.75,
            confidence_score=0.6,
            repair_summary=["Added missing rho", "Interpolated gamma"],
            missing_fields_summary={"call_rho": 10, "put_rho": 10, "call_gamma": 3},
            excellent_strikes=[380.0, 385.0],
            good_strikes=[375.0, 390.0, 395.0],
            acceptable_strikes=[370.0, 400.0],
            poor_strikes=[365.0],
            strike_repair_details={}
        )

        summary = self.validator.create_validation_summary(mock_result)

        # Check summary structure
        assert 'validation_summary' in summary
        assert 'recommendation' in summary
        assert 'processing_decision' in summary

        # Check quality improvement tracking
        validation = summary['validation_summary']
        assert validation['quality_improvement']['improvement'] == 0.35  # 0.75 - 0.4
        assert validation['strike_categories']['excellent'] == 2
        assert validation['strike_categories']['good'] == 3

        # Check processing decision
        decision = summary['processing_decision']
        assert decision['can_proceed'] is True  # Should proceed with 0.75 quality
        assert 'confidence_level' in decision

    def test_processing_decision_logic(self):
        """Test processing decision logic for various quality levels."""
        from src.analytics.enhanced_greeks_validation import EnhancedGreeksValidationResult

        # High quality scenario
        high_quality_result = EnhancedGreeksValidationResult(
            valid_strikes_count=10, complete_strikes_count=8,
            partially_complete_strikes_count=2, repaired_strikes_count=2,
            interpolated_strikes_count=1, fallback_strikes_count=1,
            original_quality_score=0.6, enhanced_quality_score=0.85,
            confidence_score=0.8, repair_summary=[], missing_fields_summary={},
            excellent_strikes=[1, 2, 3, 4, 5], good_strikes=[6, 7, 8],
            acceptable_strikes=[9], poor_strikes=[10], strike_repair_details={}
        )

        decision = self.validator._make_processing_decision(high_quality_result)
        assert decision['can_proceed'] is True
        assert decision['processing_mode'] == 'full_analysis'
        assert decision['confidence_level'] == 'high'

        # Low quality scenario
        low_quality_result = EnhancedGreeksValidationResult(
            valid_strikes_count=10, complete_strikes_count=1,
            partially_complete_strikes_count=2, repaired_strikes_count=8,
            interpolated_strikes_count=6, fallback_strikes_count=8,
            original_quality_score=0.1, enhanced_quality_score=0.25,
            confidence_score=0.2, repair_summary=[], missing_fields_summary={},
            excellent_strikes=[1], good_strikes=[], acceptable_strikes=[2, 3],
            poor_strikes=[4, 5, 6, 7, 8, 9, 10], strike_repair_details={}
        )

        decision = self.validator._make_processing_decision(low_quality_result)
        assert decision['can_proceed'] is False
        assert decision['processing_mode'] == 'reject'

    def test_missing_fields_summary(self):
        """Test tracking of missing fields across strikes."""
        # Simulate validation with specific missing fields pattern
        greeks_data = {
            "380": {
                "call": {"delta": 0.5, "gamma": 0.1},  # Missing theta, vega, rho
                "put": {"delta": -0.5}  # Missing gamma, theta, vega, rho
            },
            "385": {
                "call": {"delta": 0.4, "vega": 0.2},  # Missing gamma, theta, rho
                "put": {"delta": -0.6, "gamma": 0.08}  # Missing theta, vega, rho
            }
        }

        result = self.validator.validate_and_enhance_greeks_data(
            greeks_by_strike=greeks_data,
            spot_price=382.5,
            risk_free_rate=0.05,
            time_to_expiry=0.25,
            implied_vol=0.20
        )

        # Should track missing fields
        missing = result.missing_fields_summary

        # Rho should be missing for all 4 options (2 strikes × 2 option types)
        assert missing.get('call_rho', 0) >= 1
        assert missing.get('put_rho', 0) >= 1

        # Theta should be missing for most options
        assert missing.get('call_theta', 0) + missing.get('put_theta', 0) >= 3


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_spy_far_otm_scenario(self):
        """Test SPY far OTM strikes with incomplete data."""
        validator = EnhancedGreeksValidator()

        # SPY trading at 400, far OTM strikes have limited data
        spy_data = {
            "450": {  # Far OTM call strike
                "call": {
                    "delta": 0.05,
                    "market_price": 0.50,
                    # Missing gamma, theta, vega, rho, model_price
                },
                "put": {
                    "delta": -0.95,
                    "market_price": 49.50,
                    # Missing all other Greeks
                }
            },
            "460": {  # Even farther OTM
                "call": {
                    "market_price": 0.25,
                    # Missing all Greeks
                },
                "put": {
                    "market_price": 59.25,
                    # Missing all Greeks
                }
            }
        }

        result = validator.validate_and_enhance_greeks_data(
            greeks_by_strike=spy_data,
            spot_price=400.0,
            risk_free_rate=0.05,
            time_to_expiry=0.25,
            implied_vol=0.15  # Lower vol for far OTM
        )

        # Should still provide reasonable quality after enhancements
        assert result.enhanced_quality_score > 0.3
        assert result.confidence_score > 0.2

        # Should have applied appropriate fallbacks for far OTM
        assert result.fallback_strikes_count == 2  # Both strikes needed fallbacks

        # Quality should be categorized appropriately (acceptable/poor for far OTM)
        assert len(result.poor_strikes) <= len(result.acceptable_strikes) + len(result.good_strikes)

    def test_mixed_quality_strikes(self):
        """Test mixture of high and low quality strikes."""
        validator = EnhancedGreeksValidator()

        mixed_data = {
            # High quality ATM strike
            "400": {
                "call": {
                    "delta": 0.5, "gamma": 0.1, "theta": -0.02,
                    "vega": 0.2, "rho": 0.05, "market_price": 15.0, "model_price": 15.5
                },
                "put": {
                    "delta": -0.5, "gamma": 0.1, "theta": -0.02,
                    "vega": 0.2, "rho": -0.05, "market_price": 15.0, "model_price": 15.5
                }
            },
            # Medium quality strike (missing some Greeks)
            "410": {
                "call": {
                    "delta": 0.3, "market_price": 8.0, "model_price": 8.2
                    # Missing gamma, theta, vega, rho
                },
                "put": {
                    "delta": -0.7, "gamma": 0.08, "market_price": 22.0
                    # Missing theta, vega, rho, model_price
                }
            },
            # Poor quality strike (minimal data)
            "430": {
                "call": {"market_price": 2.0},  # Only price data
                "put": {"market_price": 32.0}   # Only price data
            }
        }

        result = validator.validate_and_enhance_greeks_data(
            greeks_by_strike=mixed_data,
            spot_price=400.0,
            risk_free_rate=0.05,
            time_to_expiry=0.25,
            implied_vol=0.18
        )

        # Should categorize strikes appropriately
        assert len(result.excellent_strikes) >= 1  # ATM strike should be excellent
        assert len(result.good_strikes) >= 1  # 410 strike should be good after repair
        assert len(result.poor_strikes) >= 1  # 430 strike will remain poor

        # Overall quality should be reasonable due to good ATM data
        assert result.enhanced_quality_score > 0.5
        assert result.confidence_score > 0.4