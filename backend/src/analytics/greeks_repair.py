"""
Enhanced Intelligent Greeks Validation and Repair System

This module provides sophisticated data repair mechanisms for partial Greeks data,
with interpolation, mathematical relationships, and fallback strategies optimized
for high-liquidity assets. Enhanced with multi-source validation and quality scoring.
"""

import math
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from scipy import interpolate
from scipy.stats import norm

# Import the new validation components
from .greeks_comparison_validator import GreeksComparisonValidator, GreeksSource
from .finviz_greeks_extractor import FinvizGreeksExtractor


@dataclass
class GreeksRepairResult:
    """Enhanced result of Greeks repair operation."""
    repaired_data: Dict[str, Any]
    repairs_made: List[str]
    interpolated_fields: List[str]
    fallback_fields: List[str]
    quality_score: float  # 0.0 to 1.0
    confidence_score: float  # 0.0 to 1.0
    # Enhanced quality metrics
    source_quality_scores: Dict[str, float]  # Quality scores by source (finviz, calculated, hybrid)
    theoretical_validity_score: float  # How well Greeks satisfy theoretical constraints
    liquidity_adjusted_score: float  # Quality adjusted for market liquidity
    repair_method_scores: Dict[str, float]  # Scores for different repair methods used
    recommended_usage: str  # 'high_confidence', 'medium_confidence', 'low_confidence', 'avoid'


class GreeksValidator:
    """Enhanced validator that repairs Greeks data with multi-source validation and quality scoring."""

    def __init__(self):
        """Initialize the enhanced Greeks validator."""
        self.required_greeks = ['delta', 'gamma', 'theta', 'vega', 'rho']
        self.required_prices = ['market_price', 'model_price']
        self.essential_greeks = ['delta']  # Minimum required for basic analysis
        self.interpolatable_greeks = ['delta', 'gamma', 'vega']  # Can be interpolated
        self.calculable_greeks = ['theta', 'rho']  # Can be calculated from other Greeks

        # Enhanced components
        self.comparison_validator = GreeksComparisonValidator()
        self.finviz_extractor = FinvizGreeksExtractor()

        # Quality thresholds for recommendations
        self.quality_thresholds = {
            'high_confidence': 0.85,
            'medium_confidence': 0.65,
            'low_confidence': 0.45,
            'avoid': 0.0  # Below low_confidence threshold
        }

        # Repair method weights for scoring
        self.repair_method_weights = {
            'original': 1.0,
            'interpolated': 0.75,
            'calculated_relationship': 0.65,
            'finviz_fallback': 0.70,
            'theoretical_fallback': 0.45
        }

    def validate_and_repair_strike(self,
                                 strike: float,
                                 strike_data: Dict[str, Any],
                                 neighboring_strikes: Dict[float, Dict[str, Any]],
                                 spot_price: float,
                                 risk_free_rate: float = 0.05,
                                 time_to_expiry: float = 0.25,
                                 implied_vol: Optional[float] = None) -> GreeksRepairResult:
        """
        Validate and repair Greeks data for a single strike.

        Args:
            strike: The strike price
            strike_data: Current Greeks data for the strike
            neighboring_strikes: Greeks data from nearby strikes for interpolation
            spot_price: Current stock price
            risk_free_rate: Risk-free rate
            time_to_expiry: Time to expiration in years
            implied_vol: Implied volatility if available

        Returns:
            GreeksRepairResult with repaired data and metadata
        """
        repairs_made = []
        interpolated_fields = []
        fallback_fields = []
        repaired_data = {}

        # Process each option type (call/put)
        for option_type in ['call', 'put']:
            if option_type not in strike_data:
                # Create empty option data if missing
                strike_data[option_type] = {}
                repairs_made.append(f"Created missing {option_type} data structure")

            option_data = strike_data[option_type].copy()
            repaired_option = self._repair_option_data(
                strike, option_type, option_data, neighboring_strikes,
                spot_price, risk_free_rate, time_to_expiry, implied_vol
            )

            repaired_data[option_type] = repaired_option['data']
            repairs_made.extend(repaired_option['repairs'])
            interpolated_fields.extend(repaired_option['interpolated'])
            fallback_fields.extend(repaired_option['fallback'])

        # Calculate quality and confidence scores
        quality_score = self._calculate_quality_score(repaired_data)
        confidence_score = self._calculate_confidence_score(
            repaired_data, len(interpolated_fields), len(fallback_fields)
        )

        # Enhanced quality assessment
        enhanced_quality_metrics = self._calculate_enhanced_quality_metrics(
            repaired_data, repairs_made, interpolated_fields, fallback_fields,
            strike, spot_price, time_to_expiry
        )

        return GreeksRepairResult(
            repaired_data=repaired_data,
            repairs_made=repairs_made,
            interpolated_fields=interpolated_fields,
            fallback_fields=fallback_fields,
            quality_score=quality_score,
            confidence_score=confidence_score,
            source_quality_scores=enhanced_quality_metrics['source_quality_scores'],
            theoretical_validity_score=enhanced_quality_metrics['theoretical_validity_score'],
            liquidity_adjusted_score=enhanced_quality_metrics['liquidity_adjusted_score'],
            repair_method_scores=enhanced_quality_metrics['repair_method_scores'],
            recommended_usage=enhanced_quality_metrics['recommended_usage']
        )

    def _repair_option_data(self,
                          strike: float,
                          option_type: str,
                          option_data: Dict[str, Any],
                          neighboring_strikes: Dict[float, Dict[str, Any]],
                          spot_price: float,
                          risk_free_rate: float,
                          time_to_expiry: float,
                          implied_vol: Optional[float]) -> Dict[str, Any]:
        """Repair Greeks data for a single option type."""
        repairs = []
        interpolated = []
        fallback = []

        # 1. Validate and clean existing data
        cleaned_data = self._clean_existing_greeks(option_data, option_type, strike)
        repairs.extend(cleaned_data['repairs'])

        # 2. Interpolate missing Greeks from neighboring strikes
        interpolated_data = self._interpolate_missing_greeks(
            strike, option_type, cleaned_data['data'], neighboring_strikes
        )
        cleaned_data['data'].update(interpolated_data['data'])
        interpolated.extend(interpolated_data['interpolated'])

        # 3. Calculate Greeks using mathematical relationships
        calculated_data = self._calculate_missing_greeks(
            strike, option_type, cleaned_data['data'], spot_price,
            risk_free_rate, time_to_expiry, implied_vol
        )
        cleaned_data['data'].update(calculated_data['data'])
        fallback.extend(calculated_data['calculated'])

        # 4. Apply fallback values for still missing essential Greeks
        fallback_data = self._apply_fallback_values(
            strike, option_type, cleaned_data['data'], spot_price
        )
        cleaned_data['data'].update(fallback_data['data'])
        fallback.extend(fallback_data['fallback'])

        return {
            'data': cleaned_data['data'],
            'repairs': repairs,
            'interpolated': interpolated,
            'fallback': fallback
        }

    def _clean_existing_greeks(self, option_data: Dict[str, Any],
                             option_type: str, strike: float) -> Dict[str, Any]:
        """Clean and validate existing Greeks values."""
        cleaned = {}
        repairs = []

        all_fields = self.required_greeks + self.required_prices

        for field in all_fields:
            if field in option_data and option_data[field] is not None:
                try:
                    value = float(option_data[field])

                    # Check for invalid values
                    if math.isnan(value) or math.isinf(value):
                        repairs.append(f"Removed invalid {field} for {option_type}: {value}")
                        continue

                    # Range validation
                    if self._validate_greek_range(field, value, option_type):
                        cleaned[field] = value
                    else:
                        repairs.append(f"Removed out-of-range {field} for {option_type}: {value}")

                except (ValueError, TypeError):
                    repairs.append(f"Removed non-numeric {field} for {option_type}: {option_data[field]}")

        return {'data': cleaned, 'repairs': repairs}

    def _validate_greek_range(self, field: str, value: float, option_type: str) -> bool:
        """Validate that Greek values are in reasonable ranges."""
        if field == 'delta':
            if option_type == 'call':
                return 0 <= value <= 1
            else:  # put
                return -1 <= value <= 0
        elif field == 'gamma':
            return value >= 0  # Gamma is always positive
        elif field == 'vega':
            return value >= 0  # Vega should be positive
        elif field in ['market_price', 'model_price']:
            return value >= 0  # Prices should be non-negative
        # Theta and rho can be negative, so we're more lenient
        elif field in ['theta', 'rho']:
            return abs(value) < 100  # Reasonable magnitude check

        return True

    def _interpolate_missing_greeks(self,
                                  strike: float,
                                  option_type: str,
                                  option_data: Dict[str, Any],
                                  neighboring_strikes: Dict[float, Dict[str, Any]]) -> Dict[str, Any]:
        """Interpolate missing Greeks from neighboring strikes."""
        interpolated_data = {}
        interpolated_fields = []

        # Get valid neighboring data
        neighbors = self._get_valid_neighbors(strike, option_type, neighboring_strikes)

        if len(neighbors) < 2:
            return {'data': interpolated_data, 'interpolated': interpolated_fields}

        # Sort neighbors by strike
        sorted_neighbors = sorted(neighbors.items())
        strikes = [s for s, _ in sorted_neighbors]

        for field in self.interpolatable_greeks:
            if field not in option_data or option_data[field] is None:
                # Try to interpolate
                values = []
                valid_strikes = []

                for neighbor_strike, neighbor_data in sorted_neighbors:
                    if field in neighbor_data and neighbor_data[field] is not None:
                        try:
                            value = float(neighbor_data[field])
                            if not (math.isnan(value) or math.isinf(value)):
                                values.append(value)
                                valid_strikes.append(neighbor_strike)
                        except (ValueError, TypeError):
                            continue

                if len(values) >= 2 and len(valid_strikes) >= 2:
                    try:
                        # Use linear interpolation (can be extended to spline)
                        if min(valid_strikes) <= strike <= max(valid_strikes):
                            # Interpolation
                            interpolated_value = np.interp(strike, valid_strikes, values)
                        else:
                            # Extrapolation - use nearest neighbor
                            if strike < min(valid_strikes):
                                interpolated_value = values[0]
                            else:
                                interpolated_value = values[-1]

                        # Validate the interpolated value
                        if self._validate_greek_range(field, interpolated_value, option_type):
                            interpolated_data[field] = interpolated_value
                            interpolated_fields.append(f"{option_type}_{field}")

                    except Exception as e:
                        # Interpolation failed, skip
                        continue

        return {'data': interpolated_data, 'interpolated': interpolated_fields}

    def _get_valid_neighbors(self, strike: float, option_type: str,
                           neighboring_strikes: Dict[float, Dict[str, Any]]) -> Dict[float, Dict[str, Any]]:
        """Get valid neighboring strikes for interpolation."""
        neighbors = {}

        for neighbor_strike, neighbor_data in neighboring_strikes.items():
            if (neighbor_strike != strike and
                isinstance(neighbor_data, dict) and
                option_type in neighbor_data and
                isinstance(neighbor_data[option_type], dict)):
                neighbors[neighbor_strike] = neighbor_data[option_type]

        return neighbors

    def _calculate_missing_greeks(self,
                                strike: float,
                                option_type: str,
                                option_data: Dict[str, Any],
                                spot_price: float,
                                risk_free_rate: float,
                                time_to_expiry: float,
                                implied_vol: Optional[float]) -> Dict[str, Any]:
        """Calculate missing Greeks using mathematical relationships."""
        calculated_data = {}
        calculated_fields = []

        # If we have delta and other parameters, we can estimate some Greeks
        if 'delta' in option_data and implied_vol is not None and implied_vol > 0:
            try:
                # Calculate missing rho using Black-Scholes approximation
                if 'rho' not in option_data or option_data['rho'] is None:
                    rho = self._calculate_rho_from_delta(
                        option_data['delta'], strike, spot_price, time_to_expiry, option_type
                    )
                    if rho is not None:
                        calculated_data['rho'] = rho
                        calculated_fields.append(f"{option_type}_rho")

                # Calculate missing theta if we have gamma and vega
                if ('theta' not in option_data or option_data['theta'] is None and
                    'gamma' in option_data and 'vega' in option_data):
                    theta = self._calculate_theta_approximation(
                        option_data.get('gamma'), option_data.get('vega'),
                        spot_price, risk_free_rate, implied_vol, time_to_expiry
                    )
                    if theta is not None:
                        calculated_data['theta'] = theta
                        calculated_fields.append(f"{option_type}_theta")

            except Exception as e:
                # Calculation failed, skip
                pass

        return {'data': calculated_data, 'calculated': calculated_fields}

    def _calculate_rho_from_delta(self, delta: float, strike: float, spot_price: float,
                                time_to_expiry: float, option_type: str) -> Optional[float]:
        """Approximate rho using delta and option characteristics."""
        try:
            # Simple approximation: rho ≈ delta * time_to_expiry * strike * discount_factor
            discount_factor = math.exp(-0.05 * time_to_expiry)  # Rough approximation

            if option_type == 'call':
                rho = delta * time_to_expiry * strike * discount_factor * 0.01
            else:  # put
                rho = (delta - 1) * time_to_expiry * strike * discount_factor * 0.01

            # Sanity check
            if abs(rho) < 100:  # Reasonable magnitude
                return rho
        except:
            pass

        return None

    def _calculate_theta_approximation(self, gamma: float, vega: float, spot_price: float,
                                     risk_free_rate: float, implied_vol: float,
                                     time_to_expiry: float) -> Optional[float]:
        """Approximate theta using gamma-vega relationship."""
        try:
            # Simplified approximation based on Black-Scholes relationships
            # theta ≈ -0.5 * spot^2 * gamma * vol^2 - r * K * e^(-r*T) * N(d2)
            # For simplicity, use a rough approximation
            theta_approx = -0.5 * (spot_price ** 2) * gamma * (implied_vol ** 2)

            # Add interest rate component (simplified)
            theta_approx -= risk_free_rate * spot_price * 0.01  # Rough approximation

            # Convert to per-day basis
            theta_daily = theta_approx / 365.25

            if abs(theta_daily) < 10:  # Reasonable magnitude for daily theta
                return theta_daily
        except:
            pass

        return None

    def _apply_fallback_values(self, strike: float, option_type: str,
                             option_data: Dict[str, Any], spot_price: float) -> Dict[str, Any]:
        """Apply reasonable fallback values for missing essential Greeks."""
        fallback_data = {}
        fallback_fields = []

        # Calculate moneyness for better fallbacks
        moneyness = spot_price / strike

        # Delta fallback (most important)
        if 'delta' not in option_data or option_data['delta'] is None:
            if option_type == 'call':
                if moneyness > 1.1:  # Deep ITM
                    fallback_delta = 0.8
                elif moneyness > 0.9:  # Near ATM
                    fallback_delta = 0.5
                else:  # OTM
                    fallback_delta = 0.2
            else:  # put
                if moneyness < 0.9:  # Deep ITM
                    fallback_delta = -0.8
                elif moneyness < 1.1:  # Near ATM
                    fallback_delta = -0.5
                else:  # OTM
                    fallback_delta = -0.2

            fallback_data['delta'] = fallback_delta
            fallback_fields.append(f"{option_type}_delta")

        # Gamma fallback
        if 'gamma' not in option_data or option_data['gamma'] is None:
            # Gamma is highest near ATM
            if 0.95 <= moneyness <= 1.05:  # Near ATM
                fallback_gamma = 0.1
            else:
                fallback_gamma = 0.05

            fallback_data['gamma'] = fallback_gamma
            fallback_fields.append(f"{option_type}_gamma")

        # Vega fallback
        if 'vega' not in option_data or option_data['vega'] is None:
            # Vega is also highest near ATM
            if 0.95 <= moneyness <= 1.05:
                fallback_vega = 0.2
            else:
                fallback_vega = 0.1

            fallback_data['vega'] = fallback_vega
            fallback_fields.append(f"{option_type}_vega")

        # Theta fallback (negative for long positions)
        if 'theta' not in option_data or option_data['theta'] is None:
            fallback_theta = -0.02  # Rough daily time decay
            fallback_data['theta'] = fallback_theta
            fallback_fields.append(f"{option_type}_theta")

        # Rho fallback
        if 'rho' not in option_data or option_data['rho'] is None:
            if option_type == 'call':
                fallback_rho = 0.1 if moneyness > 1 else 0.05
            else:  # put
                fallback_rho = -0.1 if moneyness < 1 else -0.05

            fallback_data['rho'] = fallback_rho
            fallback_fields.append(f"{option_type}_rho")

        return {'data': fallback_data, 'fallback': fallback_fields}

    def _calculate_quality_score(self, repaired_data: Dict[str, Any]) -> float:
        """Calculate quality score based on completeness of repaired data."""
        total_fields = len(self.required_greeks) * 2  # call and put
        complete_fields = 0

        for option_type in ['call', 'put']:
            if option_type in repaired_data:
                option_data = repaired_data[option_type]
                for greek in self.required_greeks:
                    if greek in option_data and option_data[greek] is not None:
                        complete_fields += 1

        return complete_fields / total_fields

    def _calculate_confidence_score(self, repaired_data: Dict[str, Any],
                                  interpolated_count: int, fallback_count: int) -> float:
        """Calculate confidence score based on repair methods used."""
        total_fields = len(self.required_greeks) * 2
        original_fields = total_fields - interpolated_count - fallback_count

        # Weight original data highest, interpolated medium, fallback lowest
        confidence = (
            original_fields * 1.0 +
            interpolated_count * 0.7 +
            fallback_count * 0.4
        ) / total_fields

        return min(confidence, 1.0)

    def _calculate_enhanced_quality_metrics(self, repaired_data: Dict[str, Any],
                                          repairs_made: List[str],
                                          interpolated_fields: List[str],
                                          fallback_fields: List[str],
                                          strike: float,
                                          spot_price: float,
                                          time_to_expiry: float) -> Dict[str, Any]:
        """Calculate comprehensive quality metrics for enhanced repair result."""
        metrics = {
            'source_quality_scores': {},
            'theoretical_validity_score': 0.0,
            'liquidity_adjusted_score': 0.0,
            'repair_method_scores': {},
            'recommended_usage': 'avoid'
        }

        # Source quality scores (placeholder - would integrate with actual Finviz data)
        metrics['source_quality_scores'] = {
            'calculated': 0.8,  # Default assumption of good calculated quality
            'finviz': 0.0,      # Would be populated with actual Finviz data
            'hybrid': 0.0       # Would be calculated based on combination
        }

        # Theoretical validity score
        validity_scores = []
        for option_type in ['call', 'put']:
            if option_type in repaired_data:
                option_data = repaired_data[option_type]
                option_validity = self._calculate_theoretical_validity(option_data, option_type, strike, spot_price)
                validity_scores.append(option_validity)

        metrics['theoretical_validity_score'] = np.mean(validity_scores) if validity_scores else 0.0

        # Repair method scoring
        total_fields = len(self.required_greeks) * 2  # Greeks × options
        method_breakdown = {
            'original': total_fields - len(interpolated_fields) - len(fallback_fields),
            'interpolated': len(interpolated_fields),
            'fallback': len(fallback_fields)
        }

        weighted_score = 0.0
        for method, count in method_breakdown.items():
            if total_fields > 0:
                proportion = count / total_fields
                weight = self.repair_method_weights.get(method, 0.5)
                weighted_score += proportion * weight

        metrics['repair_method_scores'] = {
            'weighted_average': weighted_score,
            'method_breakdown': method_breakdown
        }

        # Liquidity adjustment (placeholder - would use actual market data)
        base_quality = weighted_score * metrics['theoretical_validity_score']
        liquidity_multiplier = 1.0  # Would be calculated from bid/ask spreads, volume, OI
        metrics['liquidity_adjusted_score'] = base_quality * liquidity_multiplier

        # Determine recommended usage
        final_score = metrics['liquidity_adjusted_score']
        if final_score >= self.quality_thresholds['high_confidence']:
            metrics['recommended_usage'] = 'high_confidence'
        elif final_score >= self.quality_thresholds['medium_confidence']:
            metrics['recommended_usage'] = 'medium_confidence'
        elif final_score >= self.quality_thresholds['low_confidence']:
            metrics['recommended_usage'] = 'low_confidence'
        else:
            metrics['recommended_usage'] = 'avoid'

        return metrics

    def _calculate_theoretical_validity(self, option_data: Dict[str, Any], option_type: str,
                                      strike: float, spot_price: float) -> float:
        """Calculate how well Greeks satisfy theoretical constraints."""
        validity_score = 1.0
        checks_performed = 0
        valid_checks = 0

        delta = option_data.get('delta')
        gamma = option_data.get('gamma')
        theta = option_data.get('theta')
        vega = option_data.get('vega')
        rho = option_data.get('rho')

        # Delta bounds check
        if delta is not None:
            checks_performed += 1
            if option_type == 'call' and 0 <= delta <= 1:
                valid_checks += 1
            elif option_type == 'put' and -1 <= delta <= 0:
                valid_checks += 1

        # Gamma positivity check
        if gamma is not None:
            checks_performed += 1
            if gamma >= 0:
                valid_checks += 1

        # Theta sign check (usually negative for long options)
        if theta is not None:
            checks_performed += 1
            if theta <= 0.1:  # Allow small positive values for edge cases
                valid_checks += 1

        # Vega positivity check
        if vega is not None:
            checks_performed += 1
            if vega >= 0:
                valid_checks += 1

        # Rho reasonableness check
        if rho is not None:
            checks_performed += 1
            if -50 <= rho <= 50:  # Reasonable bounds
                valid_checks += 1

        # Delta-gamma consistency (gamma should be higher for near-the-money options)
        if delta is not None and gamma is not None:
            checks_performed += 1
            moneyness = spot_price / strike if strike > 0 else 1.0

            if option_type == 'call':
                # For calls, gamma should be highest when delta ≈ 0.5
                expected_high_gamma = 0.4 <= delta <= 0.6
                actual_high_gamma = gamma > 0.05  # Arbitrary threshold

                if (expected_high_gamma and actual_high_gamma) or (not expected_high_gamma and not actual_high_gamma):
                    valid_checks += 1

        return valid_checks / checks_performed if checks_performed > 0 else 0.0

    def validate_multi_source_greeks(self, strike: float,
                                   calculated_greeks: Dict[str, Any],
                                   finviz_greeks: Optional[Dict[str, Any]] = None,
                                   market_data: Optional[Dict[str, Any]] = None) -> GreeksRepairResult:
        """
        Enhanced validation using multiple Greek sources with intelligent fallback.

        This method integrates the comparison validator to make optimal decisions
        about which Greeks source to use for each value.
        """
        # If no Finviz data provided, fall back to single-source validation
        if not finviz_greeks:
            return self.validate_and_repair_strike(
                strike, calculated_greeks, {},
                market_data.get('spot_price', 100) if market_data else 100
            )

        # Perform comprehensive comparison
        comparison_results = self.comparison_validator.compare_greeks_comprehensive(
            {strike: finviz_greeks}, {strike: calculated_greeks}, market_data
        )

        # Create hybrid Greeks based on comparison results
        hybrid_greeks = self.comparison_validator.create_hybrid_greeks(
            {strike: finviz_greeks}, {strike: calculated_greeks}, comparison_results
        )

        # Use the hybrid result as the base for further repair if needed
        hybrid_strike_data = hybrid_greeks.get(strike, {})

        # Apply traditional repair mechanisms to the hybrid data
        return self.validate_and_repair_strike(
            strike, hybrid_strike_data, {},
            market_data.get('spot_price', 100) if market_data else 100
        )


# Global instance for easy access
default_greeks_validator = GreeksValidator()