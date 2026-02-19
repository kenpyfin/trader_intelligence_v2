"""
Comprehensive Test Suite for Strategy Validation Gates

This module tests all 17 trading strategies' validation gates with various data
quality scenarios, edge cases, and threshold-based filtering.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import pytest
import numpy as np
from typing import Dict, Any

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from analytics.strategy_validation_gates import (
    StrategyValidationGates,
    GateDecision,
    StrategyValidationResult
)


class TestStrategyValidationGates:
    """Test strategy validation gates with comprehensive scenarios."""

    def setup_method(self):
        """Set up test environment."""
        self.gates = StrategyValidationGates()

    @pytest.fixture
    def excellent_options_data(self):
        """Create excellent quality options data for all strategies."""
        return {
            "400": {
                "call": {
                    "bid": 25.80, "ask": 26.00, "last": 25.90, "model_price": 25.85,
                    "delta": 0.85, "gamma": 0.008, "theta": -0.12, "vega": 0.35, "rho": 0.25,
                    "volume": 500, "open_interest": 2000
                },
                "put": {
                    "bid": 1.20, "ask": 1.35, "last": 1.28, "model_price": 1.30,
                    "delta": -0.15, "gamma": 0.008, "theta": -0.08, "vega": 0.35, "rho": -0.18,
                    "volume": 300, "open_interest": 1500
                }
            },
            "420": {  # ATM
                "call": {
                    "bid": 8.20, "ask": 8.40, "last": 8.30, "model_price": 8.32,
                    "delta": 0.52, "gamma": 0.015, "theta": -0.18, "vega": 0.45, "rho": 0.15,
                    "volume": 1500, "open_interest": 5000
                },
                "put": {
                    "bid": 7.80, "ask": 8.00, "last": 7.90, "model_price": 7.88,
                    "delta": -0.48, "gamma": 0.015, "theta": -0.16, "vega": 0.45, "rho": -0.22,
                    "volume": 1200, "open_interest": 4200
                }
            },
            "440": {
                "call": {
                    "bid": 1.10, "ask": 1.25, "last": 1.18, "model_price": 1.20,
                    "delta": 0.12, "gamma": 0.006, "theta": -0.06, "vega": 0.28, "rho": 0.08,
                    "volume": 400, "open_interest": 1800
                },
                "put": {
                    "bid": 20.50, "ask": 20.75, "last": 20.60, "model_price": 20.62,
                    "delta": -0.88, "gamma": 0.006, "theta": -0.04, "vega": 0.28, "rho": -0.35,
                    "volume": 200, "open_interest": 900
                }
            },
            "460": {  # Deep OTM
                "call": {
                    "bid": 0.05, "ask": 0.15, "last": 0.10, "model_price": 0.08,
                    "delta": 0.02, "gamma": 0.001, "theta": -0.01, "vega": 0.05, "rho": 0.01,
                    "volume": 50, "open_interest": 200
                },
                "put": {
                    "bid": 39.80, "ask": 40.20, "last": 40.00, "model_price": 39.95,
                    "delta": -0.98, "gamma": 0.001, "theta": -0.01, "vega": 0.05, "rho": -0.45,
                    "volume": 25, "open_interest": 100
                }
            }
        }

    @pytest.fixture
    def poor_options_data(self):
        """Create poor quality options data that should fail most strategies."""
        return {
            "420": {
                "call": {
                    "bid": None, "ask": 8.40, "last": None, "model_price": None,
                    "delta": None, "gamma": np.nan, "theta": -50.0, "vega": None, "rho": None,
                    "volume": 2, "open_interest": 15
                },
                "put": {
                    "bid": 5.00, "ask": 10.00, "last": 7.50, "model_price": 7.25,  # 50% spread
                    "delta": -2.0, "gamma": -0.01, "theta": 0.5, "vega": 0.45, "rho": -0.22,  # Invalid Greeks
                    "volume": 0, "open_interest": 5
                }
            }
        }

    @pytest.fixture
    def marginal_options_data(self):
        """Create marginal quality data at threshold boundaries."""
        return {
            "420": {
                "call": {
                    "bid": 8.00, "ask": 8.50, "last": 8.25, "model_price": 8.30,  # 6% spread
                    "delta": 0.52, "gamma": 0.015, "theta": -0.18, "vega": None, "rho": 0.15,  # Missing vega
                    "volume": 10, "open_interest": 100  # Exactly at thresholds
                },
                "put": {
                    "bid": 7.50, "ask": 8.20, "last": 7.85, "model_price": 7.90,  # 8.5% spread
                    "delta": -0.48, "gamma": 0.015, "theta": None, "vega": 0.45, "rho": -0.22,  # Missing theta
                    "volume": 8, "open_interest": 80  # Below thresholds
                }
            }
        }

    def test_covered_call_strategy_validation(self, excellent_options_data, poor_options_data):
        """Test covered call strategy validation."""
        strategy = "covered_call"

        # Test with excellent data
        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert result.gate_decision == GateDecision.APPROVE
        assert result.decision_confidence >= 0.8
        assert result.quality_score_vs_threshold >= 0.8
        assert result.recommended_position_size_factor >= 0.8

        # Test with poor data
        poor_result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=poor_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert poor_result.gate_decision in [GateDecision.REJECT, GateDecision.APPROVE_WITH_CAUTION]
        assert poor_result.recommended_position_size_factor <= 0.5

    def test_cash_secured_put_strategy_validation(self, excellent_options_data, poor_options_data):
        """Test cash-secured put strategy validation."""
        strategy = "cash_secured_put"

        # Test with excellent data
        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert result.gate_decision == GateDecision.APPROVE
        assert len(result.risk_warnings) <= 2  # Should have minimal warnings with good data

        # Test with poor data
        poor_result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=poor_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert len(poor_result.risk_warnings) >= 3  # Should have many warnings
        assert len(poor_result.improvement_recommendations) >= 2

    def test_protective_put_strategy_validation(self, excellent_options_data, marginal_options_data):
        """Test protective put strategy validation."""
        strategy = "protective_put"

        # Test with excellent data
        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert result.gate_decision == GateDecision.APPROVE
        assert "Protective put approved" in " ".join(result.approval_conditions)

        # Test with marginal data
        marginal_result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=marginal_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # Should be approved with caution due to missing Greeks
        assert marginal_result.gate_decision in [GateDecision.APPROVE_WITH_CAUTION, GateDecision.APPROVE]
        assert marginal_result.recommended_position_size_factor < 1.0

    def test_long_call_strategy_validation(self, excellent_options_data):
        """Test long call strategy validation."""
        strategy = "long_call"

        # Test with excellent data
        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert result.gate_decision == GateDecision.APPROVE
        assert result.quality_score_vs_threshold >= 0.6  # Long call has moderate requirements

        # Verify Greeks requirements are met
        assert any("Greeks completeness" in cond for cond in result.approval_conditions)

    def test_long_put_strategy_validation(self, excellent_options_data):
        """Test long put strategy validation."""
        strategy = "long_put"

        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert result.gate_decision == GateDecision.APPROVE
        assert result.quality_score_vs_threshold >= 0.6

        # Should focus on put options
        assert any("put" in cond.lower() for cond in result.approval_conditions)

    def test_short_call_strategy_validation(self, excellent_options_data, poor_options_data):
        """Test short call strategy validation (high risk)."""
        strategy = "short_call"

        # Even with excellent data, should have strict requirements
        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # Short strategies have higher quality requirements
        if result.gate_decision == GateDecision.APPROVE:
            assert result.quality_score_vs_threshold >= 0.8
            assert len(result.risk_warnings) >= 1  # Should warn about unlimited risk

        # Test with poor data - should reject
        poor_result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=poor_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert poor_result.gate_decision == GateDecision.REJECT
        assert "unlimited risk" in " ".join(poor_result.risk_warnings).lower()

    def test_short_put_strategy_validation(self, excellent_options_data):
        """Test short put strategy validation (high risk)."""
        strategy = "short_put"

        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # Should have high quality requirements for short strategies
        if result.gate_decision == GateDecision.APPROVE:
            assert result.quality_score_vs_threshold >= 0.8
            assert len(result.risk_warnings) >= 1

    def test_bull_call_spread_strategy_validation(self, excellent_options_data, marginal_options_data):
        """Test bull call spread strategy validation."""
        strategy = "bull_call_spread"

        # Test with excellent data
        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert result.gate_decision == GateDecision.APPROVE
        assert result.quality_score_vs_threshold >= 0.7  # Spreads need good data

        # Should require multiple strikes
        assert any("multiple strikes" in cond.lower() for cond in result.approval_conditions)

        # Test with marginal data
        marginal_result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=marginal_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # Should be more restrictive with marginal data
        if marginal_result.gate_decision == GateDecision.APPROVE:
            assert marginal_result.recommended_position_size_factor <= 0.7

    def test_bear_put_spread_strategy_validation(self, excellent_options_data):
        """Test bear put spread strategy validation."""
        strategy = "bear_put_spread"

        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert result.gate_decision == GateDecision.APPROVE
        assert result.quality_score_vs_threshold >= 0.7

        # Should focus on put spread requirements
        assert any("put" in cond.lower() and "spread" in cond.lower()
                  for cond in result.approval_conditions)

    def test_iron_condor_strategy_validation(self, excellent_options_data, poor_options_data):
        """Test iron condor strategy validation (complex strategy)."""
        strategy = "iron_condor"

        # Test with excellent data
        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # Iron condor has very high requirements
        assert result.quality_score_vs_threshold >= 0.8
        if result.gate_decision == GateDecision.APPROVE:
            assert len(result.approval_conditions) >= 4  # Complex strategy requirements

        # Test with poor data - should reject
        poor_result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=poor_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert poor_result.gate_decision == GateDecision.REJECT
        assert len(poor_result.improvement_recommendations) >= 3

    def test_iron_butterfly_strategy_validation(self, excellent_options_data):
        """Test iron butterfly strategy validation (complex strategy)."""
        strategy = "iron_butterfly"

        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # Iron butterfly has very high requirements
        assert result.quality_score_vs_threshold >= 0.8

        # Should require excellent Greeks and liquidity
        assert any("greeks" in cond.lower() for cond in result.approval_conditions)
        assert any("liquidity" in cond.lower() for cond in result.approval_conditions)

    def test_long_straddle_strategy_validation(self, excellent_options_data, marginal_options_data):
        """Test long straddle strategy validation."""
        strategy = "long_straddle"

        # Test with excellent data
        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert result.gate_decision == GateDecision.APPROVE
        assert result.quality_score_vs_threshold >= 0.7

        # Should require both calls and puts at same strike
        assert any("straddle" in cond.lower() for cond in result.approval_conditions)

        # Test with marginal data
        marginal_result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=marginal_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # Missing Greeks should affect straddle approval
        if marginal_result.gate_decision == GateDecision.APPROVE:
            assert marginal_result.recommended_position_size_factor <= 0.8

    def test_short_straddle_strategy_validation(self, excellent_options_data, poor_options_data):
        """Test short straddle strategy validation (high risk)."""
        strategy = "short_straddle"

        # Even with excellent data, should have very strict requirements
        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # Short straddle has highest quality requirements
        if result.gate_decision == GateDecision.APPROVE:
            assert result.quality_score_vs_threshold >= 0.85
            assert len(result.risk_warnings) >= 2  # Should warn about unlimited risk

        # Test with poor data - should definitely reject
        poor_result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=poor_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert poor_result.gate_decision == GateDecision.REJECT

    def test_long_strangle_strategy_validation(self, excellent_options_data):
        """Test long strangle strategy validation."""
        strategy = "long_strangle"

        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert result.gate_decision == GateDecision.APPROVE
        assert result.quality_score_vs_threshold >= 0.7

        # Should require different strikes for call and put
        assert any("strangle" in cond.lower() for cond in result.approval_conditions)

    def test_short_strangle_strategy_validation(self, excellent_options_data):
        """Test short strangle strategy validation (high risk)."""
        strategy = "short_strangle"

        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # Short strangle has high requirements
        if result.gate_decision == GateDecision.APPROVE:
            assert result.quality_score_vs_threshold >= 0.8
            assert len(result.risk_warnings) >= 1

    def test_collar_strategy_validation(self, excellent_options_data):
        """Test collar strategy validation."""
        strategy = "collar"

        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert result.gate_decision == GateDecision.APPROVE
        assert result.quality_score_vs_threshold >= 0.6  # Collar is protective, less strict

        # Should require both call and put positions
        assert any("collar" in cond.lower() for cond in result.approval_conditions)

    def test_calendar_spread_strategy_validation(self, excellent_options_data, poor_options_data):
        """Test calendar spread strategy validation."""
        strategy = "calendar_spread"

        # Test with excellent data
        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert result.gate_decision == GateDecision.APPROVE
        assert result.quality_score_vs_threshold >= 0.75  # Calendar spreads need good Greeks

        # Should emphasize time decay analysis
        assert any("time" in cond.lower() or "theta" in cond.lower()
                  for cond in result.approval_conditions)

        # Test with poor data
        poor_result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=poor_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # Calendar spreads are sensitive to poor Greeks data
        assert poor_result.gate_decision in [GateDecision.REJECT, GateDecision.APPROVE_WITH_CAUTION]

    def test_invalid_strategy_handling(self):
        """Test handling of invalid strategy names."""
        with pytest.raises(ValueError, match="Unknown strategy"):
            self.gates.validate_strategy(
                strategy="invalid_strategy",
                options_data={},
                ticker="SPY",
                expiration_date="20241215",
                spot_price=420.0
            )

    def test_empty_options_data_handling(self):
        """Test handling of empty options data."""
        result = self.gates.validate_strategy(
            strategy="covered_call",
            options_data={},
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert result.gate_decision == GateDecision.REJECT
        assert "No options data available" in " ".join(result.improvement_recommendations)

    def test_strategy_requirements_retrieval(self):
        """Test getting strategy requirements."""
        # Test valid strategy
        requirements = self.gates.get_strategy_requirements("covered_call")

        assert "error" not in requirements
        assert "min_quality_threshold" in requirements
        assert "required_greeks" in requirements
        assert "min_liquidity_requirements" in requirements
        assert "risk_characteristics" in requirements

        # Test invalid strategy
        invalid_requirements = self.gates.get_strategy_requirements("invalid_strategy")
        assert "error" in invalid_requirements

    def test_strategy_comparison(self):
        """Test comparing multiple strategies."""
        strategies = ["covered_call", "cash_secured_put", "iron_condor", "long_call"]

        comparison = self.gates.compare_strategies(strategies)

        assert "comparison_results" in comparison
        assert "strictness_ranking" in comparison
        assert "complexity_ranking" in comparison
        assert "liquidity_requirements_comparison" in comparison

        # Iron condor should be strictest
        strictness = comparison["strictness_ranking"]
        assert strictness[0]["strategy"] == "iron_condor"

        # Covered call should be least strict
        assert strictness[-1]["strategy"] == "covered_call"

    def test_position_size_factor_calculation(self, excellent_options_data, marginal_options_data, poor_options_data):
        """Test position size factor recommendations across quality levels."""
        strategy = "bull_call_spread"

        # Excellent data should allow full position size
        excellent_result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=excellent_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # Marginal data should reduce position size
        marginal_result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=marginal_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # Poor data should significantly reduce position size or reject
        poor_result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=poor_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # Position size should decrease with data quality
        if all(r.gate_decision != GateDecision.REJECT for r in [excellent_result, marginal_result, poor_result]):
            assert excellent_result.recommended_position_size_factor >= marginal_result.recommended_position_size_factor
            assert marginal_result.recommended_position_size_factor >= poor_result.recommended_position_size_factor

    def test_risk_warnings_generation(self, excellent_options_data):
        """Test that appropriate risk warnings are generated."""
        high_risk_strategies = ["short_call", "short_put", "short_straddle", "short_strangle"]

        for strategy in high_risk_strategies:
            result = self.gates.validate_strategy(
                strategy=strategy,
                options_data=excellent_options_data,
                ticker="SPY",
                expiration_date="20241215",
                spot_price=420.0
            )

            # High-risk strategies should always have warnings
            assert len(result.risk_warnings) >= 1

            # Should mention unlimited risk for naked short positions
            if strategy in ["short_call", "short_put"]:
                assert any("unlimited" in warning.lower() for warning in result.risk_warnings)

    def test_improvement_recommendations_quality(self, poor_options_data):
        """Test that improvement recommendations are specific and actionable."""
        strategy = "iron_condor"  # Complex strategy that will have many recommendations

        result = self.gates.validate_strategy(
            strategy=strategy,
            options_data=poor_options_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        assert result.gate_decision == GateDecision.REJECT
        assert len(result.improvement_recommendations) >= 3

        # Recommendations should be specific
        recommendations_text = " ".join(result.improvement_recommendations).lower()
        assert any(keyword in recommendations_text
                  for keyword in ["greeks", "liquidity", "pricing", "spread", "volume"])

    def test_threshold_based_filtering(self):
        """Test that strategies are properly filtered based on quality thresholds."""
        # Create data that meets some thresholds but not others
        threshold_data = {
            "420": {
                "call": {
                    "bid": 8.00, "ask": 8.20, "last": 8.10, "model_price": 8.12,  # Good pricing
                    "delta": 0.52, "gamma": 0.015, "theta": -0.18,  # Missing vega, rho
                    "volume": 100, "open_interest": 500  # Good liquidity
                }
            }
        }

        # Low-requirement strategy should pass
        low_req_result = self.gates.validate_strategy(
            strategy="covered_call",
            options_data=threshold_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # High-requirement strategy should be more restrictive
        high_req_result = self.gates.validate_strategy(
            strategy="iron_condor",
            options_data=threshold_data,
            ticker="SPY",
            expiration_date="20241215",
            spot_price=420.0
        )

        # Covered call should be more lenient than iron condor
        if low_req_result.gate_decision == GateDecision.APPROVE:
            assert high_req_result.gate_decision in [GateDecision.REJECT, GateDecision.APPROVE_WITH_CAUTION]
            assert high_req_result.recommended_position_size_factor <= low_req_result.recommended_position_size_factor


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main([__file__, "-v"])