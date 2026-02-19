"""
Greeks Comparison and Validation System

This module provides comprehensive comparison and validation between different sources
of Greeks data (Finviz API vs Calculated) with intelligent decision making for
optimal data quality and reliability.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import math


class GreeksSource(Enum):
    FINVIZ = "finviz"
    CALCULATED = "calculated"
    HYBRID = "hybrid"


@dataclass
class GreeksQualityMetrics:
    """Quality metrics for Greeks data."""
    completeness: float  # 0-1: percentage of non-null Greeks
    validity: float      # 0-1: percentage of theoretically valid Greeks
    consistency: float   # 0-1: internal consistency (e.g., put-call parity)
    liquidity_score: float  # 0-1: based on volume/OI/bid-ask spread
    overall_score: float    # Weighted combination of above


@dataclass
class GreeksComparison:
    """Comparison results between two Greeks sources."""
    strike: float
    option_type: str
    finviz_greeks: Dict[str, Optional[float]]
    calculated_greeks: Dict[str, Optional[float]]
    differences: Dict[str, Optional[float]]
    relative_differences: Dict[str, Optional[float]]
    recommended_source: GreeksSource
    confidence: float


class GreeksComparisonValidator:
    """
    Advanced Greeks comparison and validation system.

    This class provides sophisticated comparison between Finviz and calculated Greeks,
    performs quality assessment, and makes intelligent decisions about which source
    to use for each Greek based on multiple quality factors.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Tolerance thresholds for Greeks comparison
        self.tolerance_thresholds = {
            'delta': {'absolute': 0.05, 'relative': 0.10},    # 5 cents absolute, 10% relative
            'gamma': {'absolute': 0.02, 'relative': 0.15},    # 2 cents absolute, 15% relative
            'theta': {'absolute': 0.01, 'relative': 0.20},    # 1 cent absolute, 20% relative
            'vega': {'absolute': 0.02, 'relative': 0.15},     # 2 cents absolute, 15% relative
            'rho': {'absolute': 0.01, 'relative': 0.25}       # 1 cent absolute, 25% relative
        }

        # Weights for quality scoring
        self.quality_weights = {
            'completeness': 0.30,
            'validity': 0.25,
            'consistency': 0.20,
            'liquidity': 0.25
        }

        # Greeks theoretical bounds
        self.greek_bounds = {
            'delta': {'call': (0, 1), 'put': (-1, 0)},
            'gamma': {'call': (0, 10), 'put': (0, 10)},
            'theta': {'call': (-10, 1), 'put': (-10, 1)},
            'vega': {'call': (0, 5), 'put': (0, 5)},
            'rho': {'call': (-50, 50), 'put': (-50, 50)}
        }

    def compare_greeks_comprehensive(self, finviz_data: Dict, calculated_data: Dict,
                                   market_data: Dict = None) -> Dict:
        """
        Perform comprehensive comparison between Finviz and calculated Greeks.

        Args:
            finviz_data: Greeks data from Finviz extraction
            calculated_data: Greeks data from binomial/analytical calculations
            market_data: Additional market data for liquidity scoring

        Returns:
            Dict containing comprehensive comparison results and recommendations
        """
        comparison_results = {
            'metadata': {
                'total_strikes_analyzed': 0,
                'finviz_strikes': len(finviz_data),
                'calculated_strikes': len(calculated_data),
                'common_strikes': 0,
                'timestamp': pd.Timestamp.now()
            },
            'quality_metrics': {
                'finviz_overall': None,
                'calculated_overall': None
            },
            'strike_comparisons': {},
            'recommendations': {
                'preferred_source_by_strike': {},
                'hybrid_strikes': [],
                'summary': {
                    'finviz_preferred': 0,
                    'calculated_preferred': 0,
                    'hybrid_recommended': 0
                }
            },
            'statistical_analysis': {
                'differences_summary': {},
                'correlation_analysis': {},
                'outlier_detection': {}
            }
        }

        common_strikes = set(finviz_data.keys()) & set(calculated_data.keys())
        comparison_results['metadata']['common_strikes'] = len(common_strikes)
        comparison_results['metadata']['total_strikes_analyzed'] = len(common_strikes)

        if not common_strikes:
            self.logger.warning("No common strikes found for Greeks comparison")
            return comparison_results

        # Perform strike-by-strike comparison
        all_comparisons = []
        for strike in common_strikes:
            strike_comparison = self._compare_strike_comprehensive(
                strike, finviz_data[strike], calculated_data.get(strike, {}), market_data
            )
            comparison_results['strike_comparisons'][strike] = strike_comparison
            all_comparisons.extend(strike_comparison)

        # Calculate overall quality metrics
        comparison_results['quality_metrics']['finviz_overall'] = self._calculate_overall_quality(
            finviz_data, 'finviz'
        )
        comparison_results['quality_metrics']['calculated_overall'] = self._calculate_overall_quality(
            calculated_data, 'calculated'
        )

        # Generate recommendations
        self._generate_comprehensive_recommendations(all_comparisons, comparison_results)

        # Statistical analysis
        comparison_results['statistical_analysis'] = self._perform_statistical_analysis(all_comparisons)

        return comparison_results

    def _compare_strike_comprehensive(self, strike: float, finviz_data: Dict,
                                    calculated_data: Dict, market_data: Dict = None) -> List[GreeksComparison]:
        """Compare Greeks for a single strike across both option types."""
        comparisons = []

        for option_type in ['call', 'put']:
            finviz_greeks = finviz_data.get(option_type, {})
            calculated_greeks = calculated_data.get(option_type, {})

            if not finviz_greeks and not calculated_greeks:
                continue

            # Extract Greeks values
            fv_values = {greek: finviz_greeks.get(greek) for greek in ['delta', 'gamma', 'theta', 'vega', 'rho']}
            calc_values = {greek: calculated_greeks.get(greek) for greek in ['delta', 'gamma', 'theta', 'vega', 'rho']}

            # Calculate differences
            differences = {}
            relative_differences = {}

            for greek in ['delta', 'gamma', 'theta', 'vega', 'rho']:
                fv_val = fv_values[greek]
                calc_val = calc_values[greek]

                if fv_val is not None and calc_val is not None:
                    differences[greek] = fv_val - calc_val
                    if calc_val != 0:
                        relative_differences[greek] = (fv_val - calc_val) / abs(calc_val)
                    else:
                        relative_differences[greek] = None
                else:
                    differences[greek] = None
                    relative_differences[greek] = None

            # Determine recommended source and confidence
            recommended_source, confidence = self._determine_recommended_source(
                fv_values, calc_values, differences, relative_differences,
                option_type, market_data
            )

            comparison = GreeksComparison(
                strike=strike,
                option_type=option_type,
                finviz_greeks=fv_values,
                calculated_greeks=calc_values,
                differences=differences,
                relative_differences=relative_differences,
                recommended_source=recommended_source,
                confidence=confidence
            )

            comparisons.append(comparison)

        return comparisons

    def _determine_recommended_source(self, finviz_values: Dict, calculated_values: Dict,
                                    differences: Dict, relative_differences: Dict,
                                    option_type: str, market_data: Dict = None) -> Tuple[GreeksSource, float]:
        """Determine the recommended Greeks source and confidence level."""
        finviz_score = self._score_greeks_quality(finviz_values, option_type, 'finviz')
        calculated_score = self._score_greeks_quality(calculated_values, option_type, 'calculated')

        # Additional scoring based on market data
        liquidity_score = 1.0
        if market_data:
            liquidity_score = self._calculate_liquidity_score(market_data)

        # Adjust scores based on differences
        agreement_bonus = 0.0
        agreement_count = 0
        total_comparisons = 0

        for greek, diff in differences.items():
            if diff is not None:
                total_comparisons += 1
                threshold = self.tolerance_thresholds[greek]

                # Check if values agree within tolerance
                abs_diff = abs(diff)
                rel_diff = abs(relative_differences.get(greek, float('inf')))

                if (abs_diff <= threshold['absolute'] or
                    rel_diff <= threshold['relative']):
                    agreement_count += 1

        if total_comparisons > 0:
            agreement_ratio = agreement_count / total_comparisons
            agreement_bonus = agreement_ratio * 0.2  # Max 20% bonus for agreement

        # Adjust final scores
        finviz_final_score = finviz_score + agreement_bonus
        calculated_final_score = calculated_score + agreement_bonus

        # Apply liquidity penalty to Finviz (more sensitive to market conditions)
        finviz_final_score *= liquidity_score

        # Decision logic
        score_diff = abs(finviz_final_score - calculated_final_score)

        if score_diff < 0.1:  # Very close scores
            recommended_source = GreeksSource.HYBRID
            confidence = 0.6 + (agreement_ratio * 0.3)
        elif finviz_final_score > calculated_final_score:
            recommended_source = GreeksSource.FINVIZ
            confidence = min(0.95, 0.6 + score_diff)
        else:
            recommended_source = GreeksSource.CALCULATED
            confidence = min(0.95, 0.6 + score_diff)

        return recommended_source, confidence

    def _score_greeks_quality(self, greeks_values: Dict[str, Optional[float]],
                             option_type: str, source: str) -> float:
        """Score the quality of Greeks values."""
        if not greeks_values:
            return 0.0

        scores = {
            'completeness': 0.0,
            'validity': 0.0,
            'consistency': 0.0
        }

        # Completeness score
        non_null_count = sum(1 for v in greeks_values.values() if v is not None)
        scores['completeness'] = non_null_count / len(greeks_values)

        # Validity score (theoretical bounds)
        valid_count = 0
        total_count = 0

        for greek, value in greeks_values.items():
            if value is not None:
                total_count += 1
                if self._is_greek_theoretically_valid(greek, value, option_type):
                    valid_count += 1

        scores['validity'] = valid_count / total_count if total_count > 0 else 0.0

        # Consistency score (relationships between Greeks)
        scores['consistency'] = self._calculate_greeks_consistency(greeks_values, option_type)

        # Source-specific adjustments
        if source == 'finviz':
            # Finviz might have more complete data but could be less accurate
            scores['completeness'] *= 1.1  # Slight bonus for completeness
            scores['validity'] *= 0.95     # Slight penalty for potential inaccuracy
        elif source == 'calculated':
            # Calculated values should be more theoretically consistent
            scores['consistency'] *= 1.1  # Bonus for theoretical consistency

        # Weighted average
        quality_score = (
            scores['completeness'] * 0.4 +
            scores['validity'] * 0.35 +
            scores['consistency'] * 0.25
        )

        return min(1.0, quality_score)

    def _is_greek_theoretically_valid(self, greek: str, value: float, option_type: str) -> bool:
        """Check if a Greek value is within theoretical bounds."""
        if math.isnan(value) or math.isinf(value):
            return False

        bounds = self.greek_bounds.get(greek, {}).get(option_type)
        if not bounds:
            return True  # No bounds defined, assume valid

        return bounds[0] <= value <= bounds[1]

    def _calculate_greeks_consistency(self, greeks_values: Dict, option_type: str) -> float:
        """Calculate consistency score based on relationships between Greeks."""
        consistency_score = 1.0

        delta = greeks_values.get('delta')
        gamma = greeks_values.get('gamma')
        theta = greeks_values.get('theta')
        vega = greeks_values.get('vega')

        # Check delta-gamma relationship (gamma should be higher for ATM options)
        if delta is not None and gamma is not None:
            if option_type == 'call':
                # For calls, gamma should be highest when delta ≈ 0.5
                expected_gamma_level = 4 * abs(delta * (1 - delta))  # Parabolic relationship
                if gamma > 0 and expected_gamma_level > 0:
                    gamma_consistency = min(1.0, gamma / (expected_gamma_level * 2))
                    consistency_score *= (0.7 + 0.3 * gamma_consistency)

        # Check theta sign (should typically be negative for long options)
        if theta is not None:
            if theta > 0:  # Unusual for long options
                consistency_score *= 0.8

        # Check vega reasonableness (should correlate with gamma)
        if gamma is not None and vega is not None:
            if gamma > 0 and vega <= 0:  # Inconsistent
                consistency_score *= 0.7

        return consistency_score

    def _calculate_liquidity_score(self, market_data: Dict) -> float:
        """Calculate liquidity score based on market data."""
        if not market_data:
            return 1.0

        bid = market_data.get('bid', 0)
        ask = market_data.get('ask', 0)
        volume = market_data.get('volume', 0)
        open_interest = market_data.get('open_interest', 0)

        liquidity_score = 1.0

        # Bid-ask spread penalty
        if bid > 0 and ask > bid:
            spread_ratio = (ask - bid) / ask
            if spread_ratio > 0.25:  # Very wide spread
                liquidity_score *= 0.6
            elif spread_ratio > 0.15:  # Wide spread
                liquidity_score *= 0.8

        # Volume penalty
        if volume < 10:  # Low volume
            liquidity_score *= 0.7

        # Open interest penalty
        if open_interest < 100:  # Low open interest
            liquidity_score *= 0.8

        return liquidity_score

    def _calculate_overall_quality(self, greeks_data: Dict, source: str) -> GreeksQualityMetrics:
        """Calculate overall quality metrics for a Greeks source."""
        if not greeks_data:
            return GreeksQualityMetrics(0, 0, 0, 0, 0)

        total_completeness = 0
        total_validity = 0
        total_consistency = 0
        total_liquidity = 0
        total_count = 0

        for strike, options in greeks_data.items():
            for option_type, greeks in options.items():
                if not isinstance(greeks, dict):
                    continue

                total_count += 1

                # Extract Greeks values
                greeks_values = {
                    greek: greeks.get(greek)
                    for greek in ['delta', 'gamma', 'theta', 'vega', 'rho']
                }

                # Calculate individual scores
                completeness = sum(1 for v in greeks_values.values() if v is not None) / len(greeks_values)

                validity = sum(
                    1 for greek, value in greeks_values.items()
                    if value is not None and self._is_greek_theoretically_valid(greek, value, option_type)
                ) / sum(1 for v in greeks_values.values() if v is not None or 1)

                consistency = self._calculate_greeks_consistency(greeks_values, option_type)

                # Liquidity score from market data
                market_data = greeks.get('market_data', {})
                liquidity = self._calculate_liquidity_score(market_data)

                total_completeness += completeness
                total_validity += validity
                total_consistency += consistency
                total_liquidity += liquidity

        if total_count == 0:
            return GreeksQualityMetrics(0, 0, 0, 0, 0)

        avg_completeness = total_completeness / total_count
        avg_validity = total_validity / total_count
        avg_consistency = total_consistency / total_count
        avg_liquidity = total_liquidity / total_count

        overall_score = (
            avg_completeness * self.quality_weights['completeness'] +
            avg_validity * self.quality_weights['validity'] +
            avg_consistency * self.quality_weights['consistency'] +
            avg_liquidity * self.quality_weights['liquidity']
        )

        return GreeksQualityMetrics(
            avg_completeness, avg_validity, avg_consistency, avg_liquidity, overall_score
        )

    def _generate_comprehensive_recommendations(self, comparisons: List[GreeksComparison], results: Dict):
        """Generate comprehensive recommendations based on all comparisons."""
        finviz_count = 0
        calculated_count = 0
        hybrid_count = 0

        for comparison in comparisons:
            strike_key = f"{comparison.strike}_{comparison.option_type}"

            if comparison.recommended_source == GreeksSource.FINVIZ:
                finviz_count += 1
                results['recommendations']['preferred_source_by_strike'][strike_key] = 'finviz'
            elif comparison.recommended_source == GreeksSource.CALCULATED:
                calculated_count += 1
                results['recommendations']['preferred_source_by_strike'][strike_key] = 'calculated'
            else:  # HYBRID
                hybrid_count += 1
                results['recommendations']['preferred_source_by_strike'][strike_key] = 'hybrid'
                results['recommendations']['hybrid_strikes'].append(strike_key)

        results['recommendations']['summary']['finviz_preferred'] = finviz_count
        results['recommendations']['summary']['calculated_preferred'] = calculated_count
        results['recommendations']['summary']['hybrid_recommended'] = hybrid_count

    def _perform_statistical_analysis(self, comparisons: List[GreeksComparison]) -> Dict:
        """Perform statistical analysis of Greeks differences."""
        analysis = {
            'differences_summary': {},
            'correlation_analysis': {},
            'outlier_detection': {}
        }

        # Collect differences by Greek
        differences_by_greek = {greek: [] for greek in ['delta', 'gamma', 'theta', 'vega', 'rho']}

        for comparison in comparisons:
            for greek, diff in comparison.differences.items():
                if diff is not None and not math.isnan(diff):
                    differences_by_greek[greek].append(diff)

        # Statistical summary for each Greek
        for greek, diffs in differences_by_greek.items():
            if diffs:
                analysis['differences_summary'][greek] = {
                    'count': len(diffs),
                    'mean': np.mean(diffs),
                    'median': np.median(diffs),
                    'std': np.std(diffs),
                    'min': np.min(diffs),
                    'max': np.max(diffs),
                    'abs_mean': np.mean(np.abs(diffs)),
                    'percentile_95': np.percentile(np.abs(diffs), 95) if len(diffs) > 1 else 0
                }

        return analysis

    def create_hybrid_greeks(self, finviz_data: Dict, calculated_data: Dict,
                            comparison_results: Dict) -> Dict:
        """
        Create hybrid Greeks by intelligently combining Finviz and calculated values.

        Args:
            finviz_data: Greeks from Finviz
            calculated_data: Greeks from calculations
            comparison_results: Results from comprehensive comparison

        Returns:
            Dict with hybrid Greeks optimized for quality
        """
        hybrid_greeks = {}
        recommendations = comparison_results.get('recommendations', {}).get('preferred_source_by_strike', {})

        all_strikes = set(finviz_data.keys()) | set(calculated_data.keys())

        for strike in all_strikes:
            hybrid_greeks[strike] = {}

            for option_type in ['call', 'put']:
                strike_key = f"{strike}_{option_type}"
                preferred_source = recommendations.get(strike_key, 'hybrid')

                finviz_greeks = finviz_data.get(strike, {}).get(option_type, {})
                calculated_greeks = calculated_data.get(strike, {}).get(option_type, {})

                if preferred_source == 'finviz' and finviz_greeks:
                    hybrid_greeks[strike][option_type] = finviz_greeks.copy()
                elif preferred_source == 'calculated' and calculated_greeks:
                    hybrid_greeks[strike][option_type] = calculated_greeks.copy()
                else:  # Hybrid approach
                    hybrid_greeks[strike][option_type] = self._create_hybrid_option_greeks(
                        finviz_greeks, calculated_greeks
                    )

        return hybrid_greeks

    def _create_hybrid_option_greeks(self, finviz_greeks: Dict, calculated_greeks: Dict) -> Dict:
        """Create hybrid Greeks for a single option."""
        hybrid = {}

        for greek in ['delta', 'gamma', 'theta', 'vega', 'rho']:
            fv_val = finviz_greeks.get(greek)
            calc_val = calculated_greeks.get(greek)

            if fv_val is not None and calc_val is not None:
                # Use weighted average, favoring the more reliable source
                # For now, equal weighting - could be enhanced with confidence scores
                hybrid[greek] = (fv_val + calc_val) / 2
            elif fv_val is not None:
                hybrid[greek] = fv_val
            elif calc_val is not None:
                hybrid[greek] = calc_val
            else:
                hybrid[greek] = None

        # Preserve market data from Finviz if available
        if 'market_data' in finviz_greeks:
            hybrid['market_data'] = finviz_greeks['market_data']
        elif 'market_data' in calculated_greeks:
            hybrid['market_data'] = calculated_greeks['market_data']

        return hybrid