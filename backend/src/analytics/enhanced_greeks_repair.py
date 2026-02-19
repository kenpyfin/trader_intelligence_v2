"""
Enhanced Greeks Repair System with Comprehensive Error Handling

This module extends the existing Greeks repair system with enhanced error handling,
detailed logging, and improved recovery strategies. It integrates with the new
error handling infrastructure while maintaining compatibility with existing code.

Key Features:
- Enhanced error categorization and logging
- Detailed failure analysis and diagnostics
- Improved interpolation with safety checks
- Advanced fallback strategies with confidence scoring
- Integration with existing Greeks validation system
- Comprehensive error reporting and monitoring

Author: Bug Fixer - Enhanced Greeks Repair Error Handling
"""

import logging
import math
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from .greeks_error_handler import GreeksErrorHandler, GreeksErrorCategory
from .greeks_repair import GreeksValidator, GreeksRepairResult


@dataclass
class EnhancedRepairResult(GreeksRepairResult):
    """Enhanced repair result with additional error handling information"""
    error_categories: List[GreeksErrorCategory] = field(default_factory=list)
    detailed_errors: List[str] = field(default_factory=list)
    recovery_attempts: Dict[str, int] = field(default_factory=dict)
    calculation_context: Dict[str, Any] = field(default_factory=dict)
    repair_timestamp: datetime = field(default_factory=datetime.now)
    safety_checks_passed: Dict[str, bool] = field(default_factory=dict)


class EnhancedGreeksValidator(GreeksValidator):
    """
    Enhanced Greeks validator with comprehensive error handling and logging

    This class extends the existing GreeksValidator with enhanced error handling,
    detailed logging, and improved recovery strategies.
    """

    def __init__(self, ticker: str = "UNKNOWN"):
        super().__init__()
        self.ticker = ticker
        self.logger = logging.getLogger(f"{__name__}.{ticker}")
        self.error_handler = GreeksErrorHandler(ticker)

        # Enhanced repair statistics
        self.repair_stats = {
            'total_repairs': 0,
            'successful_repairs': 0,
            'failed_repairs': 0,
            'interpolation_successes': 0,
            'interpolation_failures': 0,
            'fallback_applications': 0,
            'error_categories': {}
        }

    def validate_and_repair_strike_enhanced(
        self,
        strike: float,
        option_data: Dict[str, Any],
        neighbors: Dict[float, Dict[str, Any]],
        spot_price: float,
        days_to_expiration: int,
        risk_free_rate: float = 0.05
    ) -> EnhancedRepairResult:
        """
        Enhanced strike validation and repair with comprehensive error handling

        Args:
            strike: Strike price to validate and repair
            option_data: Option data for the strike
            neighbors: Neighboring strikes data for interpolation
            spot_price: Current stock price
            days_to_expiration: Days until expiration
            risk_free_rate: Risk-free rate for calculations

        Returns:
            EnhancedRepairResult with detailed repair information and error handling
        """
        self.repair_stats['total_repairs'] += 1
        repair_context = {
            'strike': strike,
            'spot_price': spot_price,
            'days_to_expiration': days_to_expiration,
            'risk_free_rate': risk_free_rate,
            'neighbors_count': len(neighbors),
            'repair_timestamp': datetime.now()
        }

        try:
            self.logger.info(f"Starting enhanced repair for strike {strike}")

            # Step 1: Pre-repair validation and diagnostics
            pre_repair_diagnostics = self._perform_pre_repair_diagnostics(
                strike, option_data, spot_price, days_to_expiration
            )

            # Step 2: Execute base repair with error handling wrapper
            with self.error_handler.error_context(**repair_context) as error_context:
                base_result = self.validate_and_repair_strike(
                    strike, option_data, neighbors, spot_price, days_to_expiration, risk_free_rate
                )
                error_context['intermediate_values']['base_repair_result'] = base_result.__dict__

            # Step 3: Post-repair validation and enhancement
            enhanced_result = self._enhance_repair_result(
                base_result, repair_context, pre_repair_diagnostics
            )

            # Step 4: Safety checks and final validation
            safety_checks = self._perform_safety_checks(enhanced_result)
            enhanced_result.safety_checks_passed = safety_checks

            # Step 5: Update statistics
            if enhanced_result.quality_score > 0.5:
                self.repair_stats['successful_repairs'] += 1
            else:
                self.repair_stats['failed_repairs'] += 1

            self.logger.info(
                f"Enhanced repair completed for strike {strike}: "
                f"quality={enhanced_result.quality_score:.3f}, "
                f"confidence={enhanced_result.confidence_score:.3f}"
            )

            return enhanced_result

        except Exception as e:
            self.repair_stats['failed_repairs'] += 1
            error_category = self._categorize_repair_error(e, repair_context)
            self.repair_stats['error_categories'][error_category.value] = \
                self.repair_stats['error_categories'].get(error_category.value, 0) + 1

            self.logger.error(
                f"Enhanced repair failed for strike {strike}: {str(e)} "
                f"[Category: {error_category.value}]"
            )

            # Return failed result with error information
            return EnhancedRepairResult(
                repaired_data={},
                repairs_made=[f"Repair failed: {str(e)}"],
                interpolated_fields=[],
                fallback_fields=[],
                quality_score=0.0,
                confidence_score=0.0,
                source_quality_scores={},
                theoretical_validity_score=0.0,
                liquidity_adjusted_score=0.0,
                repair_method_scores={},
                recommended_usage='avoid',
                error_categories=[error_category],
                detailed_errors=[str(e)],
                recovery_attempts={},
                calculation_context=repair_context,
                safety_checks_passed={}
            )

    def _perform_pre_repair_diagnostics(
        self,
        strike: float,
        option_data: Dict[str, Any],
        spot_price: float,
        days_to_expiration: int
    ) -> Dict[str, Any]:
        """Perform comprehensive pre-repair diagnostics"""

        diagnostics = {
            'input_validation': {},
            'data_completeness': {},
            'market_conditions': {},
            'risk_factors': []
        }

        try:
            # Input validation diagnostics
            diagnostics['input_validation']['strike_valid'] = (
                isinstance(strike, (int, float)) and strike > 0 and
                not math.isnan(strike) and not math.isinf(strike)
            )

            diagnostics['input_validation']['spot_price_valid'] = (
                isinstance(spot_price, (int, float)) and spot_price > 0 and
                not math.isnan(spot_price) and not math.isinf(spot_price)
            )

            # Data completeness diagnostics
            greek_fields = ['delta', 'gamma', 'theta', 'vega', 'rho']
            market_fields = ['bid', 'ask', 'last_trade', 'volume', 'open_interest']

            for option_type in ['call', 'put']:
                if option_type in option_data:
                    type_data = option_data[option_type]

                    # Greeks completeness
                    greeks_present = sum(1 for field in greek_fields if field in type_data and type_data[field] is not None)
                    diagnostics['data_completeness'][f'{option_type}_greeks_completeness'] = greeks_present / len(greek_fields)

                    # Market data completeness
                    market_data = type_data.get('market_data', {})
                    market_present = sum(1 for field in market_fields if field in market_data and market_data[field] is not None)
                    diagnostics['data_completeness'][f'{option_type}_market_completeness'] = market_present / len(market_fields)

            # Market conditions analysis
            moneyness = spot_price / strike
            diagnostics['market_conditions']['moneyness'] = moneyness
            diagnostics['market_conditions']['is_near_expiration'] = days_to_expiration < 5
            diagnostics['market_conditions']['is_deep_otm'] = moneyness < 0.8 or moneyness > 1.25
            diagnostics['market_conditions']['is_extreme_dte'] = days_to_expiration > 365

            # Risk factor identification
            if days_to_expiration < 2:
                diagnostics['risk_factors'].append('extreme_near_expiration')
            if moneyness < 0.5 or moneyness > 2.0:
                diagnostics['risk_factors'].append('extreme_moneyness')
            if diagnostics['data_completeness'].get('call_greeks_completeness', 0) < 0.5:
                diagnostics['risk_factors'].append('low_greeks_completeness')

        except Exception as e:
            self.logger.warning(f"Pre-repair diagnostics failed: {str(e)}")
            diagnostics['error'] = str(e)

        return diagnostics

    def _enhance_repair_result(
        self,
        base_result: GreeksRepairResult,
        repair_context: Dict[str, Any],
        pre_repair_diagnostics: Dict[str, Any]
    ) -> EnhancedRepairResult:
        """Enhance base repair result with additional error handling information"""

        try:
            # Create enhanced result from base result
            enhanced_result = EnhancedRepairResult(
                repaired_data=base_result.repaired_data,
                repairs_made=base_result.repairs_made,
                interpolated_fields=base_result.interpolated_fields,
                fallback_fields=base_result.fallback_fields,
                quality_score=base_result.quality_score,
                confidence_score=base_result.confidence_score,
                source_quality_scores=base_result.source_quality_scores,
                theoretical_validity_score=base_result.theoretical_validity_score,
                liquidity_adjusted_score=base_result.liquidity_adjusted_score,
                repair_method_scores=base_result.repair_method_scores,
                recommended_usage=base_result.recommended_usage,
                calculation_context=repair_context,
                repair_timestamp=datetime.now()
            )

            # Add enhanced analysis
            enhanced_result.recovery_attempts = self._analyze_recovery_attempts(base_result)
            enhanced_result.detailed_errors = self._extract_detailed_errors(base_result)
            enhanced_result.error_categories = self._categorize_repair_issues(base_result, pre_repair_diagnostics)

            # Enhance quality scoring with safety considerations
            safety_penalty = self._calculate_safety_penalty(enhanced_result, pre_repair_diagnostics)
            enhanced_result.quality_score = max(0.0, enhanced_result.quality_score - safety_penalty)

            return enhanced_result

        except Exception as e:
            self.logger.error(f"Failed to enhance repair result: {str(e)}")
            # Return base result converted to enhanced format
            return EnhancedRepairResult(**base_result.__dict__)

    def _perform_safety_checks(self, repair_result: EnhancedRepairResult) -> Dict[str, bool]:
        """Perform comprehensive safety checks on repair result"""

        safety_checks = {}

        try:
            # Check 1: Greeks bounds validation
            safety_checks['greeks_bounds_valid'] = True
            for option_type in ['call', 'put']:
                if option_type in repair_result.repaired_data:
                    option_data = repair_result.repaired_data[option_type]

                    # Delta bounds check
                    delta = option_data.get('delta')
                    if delta is not None:
                        expected_bounds = (0, 1) if option_type == 'call' else (-1, 0)
                        if not (expected_bounds[0] - 0.1 <= delta <= expected_bounds[1] + 0.1):
                            safety_checks['greeks_bounds_valid'] = False
                            break

            # Check 2: Numerical stability
            safety_checks['numerically_stable'] = True
            for option_type in ['call', 'put']:
                if option_type in repair_result.repaired_data:
                    option_data = repair_result.repaired_data[option_type]
                    for greek in ['delta', 'gamma', 'theta', 'vega', 'rho']:
                        value = option_data.get(greek)
                        if value is not None and (math.isnan(value) or math.isinf(value)):
                            safety_checks['numerically_stable'] = False
                            break

            # Check 3: Reasonableness of repair methods
            safety_checks['repair_methods_reasonable'] = (
                len(repair_result.fallback_fields) < len(repair_result.interpolated_fields) + 2
            )

            # Check 4: Quality threshold met
            safety_checks['quality_threshold_met'] = repair_result.quality_score >= 0.3

            # Check 5: No critical errors
            safety_checks['no_critical_errors'] = not any(
                category in [GreeksErrorCategory.MATHEMATICAL_EDGE_CASE,
                           GreeksErrorCategory.NUMERICAL_INSTABILITY]
                for category in repair_result.error_categories
            )

        except Exception as e:
            self.logger.warning(f"Safety checks failed: {str(e)}")
            safety_checks['safety_check_error'] = True

        return safety_checks

    def _analyze_recovery_attempts(self, repair_result: GreeksRepairResult) -> Dict[str, int]:
        """Analyze recovery attempts from repair result"""

        recovery_attempts = {
            'interpolation_attempts': len(repair_result.interpolated_fields),
            'fallback_attempts': len(repair_result.fallback_fields),
            'total_repairs': len(repair_result.repairs_made)
        }

        # Count specific recovery types
        for repair in repair_result.repairs_made:
            repair_lower = repair.lower()
            if 'interpolat' in repair_lower:
                self.repair_stats['interpolation_successes'] += 1
            elif 'fallback' in repair_lower:
                self.repair_stats['fallback_applications'] += 1

        return recovery_attempts

    def _extract_detailed_errors(self, repair_result: GreeksRepairResult) -> List[str]:
        """Extract detailed error information from repair result"""

        detailed_errors = []

        # Extract from repairs_made that indicate errors
        for repair in repair_result.repairs_made:
            if any(keyword in repair.lower() for keyword in ['removed', 'invalid', 'failed', 'error']):
                detailed_errors.append(repair)

        # Add quality-based errors
        if repair_result.quality_score < 0.3:
            detailed_errors.append(f"Low quality score: {repair_result.quality_score:.3f}")

        if repair_result.confidence_score < 0.4:
            detailed_errors.append(f"Low confidence score: {repair_result.confidence_score:.3f}")

        return detailed_errors

    def _categorize_repair_issues(
        self,
        repair_result: GreeksRepairResult,
        pre_repair_diagnostics: Dict[str, Any]
    ) -> List[GreeksErrorCategory]:
        """Categorize issues found during repair process"""

        categories = []

        # Check for data quality issues
        if len(repair_result.fallback_fields) > len(repair_result.interpolated_fields):
            categories.append(GreeksErrorCategory.DATA_VALIDATION)

        # Check for interpolation failures
        if any('interpolation failed' in repair.lower() for repair in repair_result.repairs_made):
            categories.append(GreeksErrorCategory.INTERPOLATION_FAILURE)

        # Check for extreme market conditions
        risk_factors = pre_repair_diagnostics.get('risk_factors', [])
        if 'extreme_near_expiration' in risk_factors or 'extreme_moneyness' in risk_factors:
            categories.append(GreeksErrorCategory.EXTREME_MARKET_CONDITIONS)

        # Check for mathematical edge cases
        if repair_result.theoretical_validity_score < 0.5:
            categories.append(GreeksErrorCategory.MATHEMATICAL_EDGE_CASE)

        return categories

    def _calculate_safety_penalty(
        self,
        repair_result: EnhancedRepairResult,
        pre_repair_diagnostics: Dict[str, Any]
    ) -> float:
        """Calculate safety penalty to apply to quality score"""

        penalty = 0.0

        # Penalty for high risk factors
        risk_factors = pre_repair_diagnostics.get('risk_factors', [])
        penalty += 0.1 * len(risk_factors)

        # Penalty for excessive fallback usage
        fallback_ratio = len(repair_result.fallback_fields) / max(1, len(repair_result.interpolated_fields) + len(repair_result.fallback_fields))
        if fallback_ratio > 0.6:
            penalty += 0.2

        # Penalty for error categories
        critical_categories = [
            GreeksErrorCategory.MATHEMATICAL_EDGE_CASE,
            GreeksErrorCategory.NUMERICAL_INSTABILITY,
            GreeksErrorCategory.EXTREME_MARKET_CONDITIONS
        ]

        critical_count = sum(1 for cat in repair_result.error_categories if cat in critical_categories)
        penalty += 0.15 * critical_count

        return min(penalty, 0.5)  # Cap penalty at 0.5

    def _categorize_repair_error(self, error: Exception, repair_context: Dict[str, Any]) -> GreeksErrorCategory:
        """Categorize repair errors for statistics and logging"""

        error_message = str(error).lower()

        if 'interpolation' in error_message:
            return GreeksErrorCategory.INTERPOLATION_FAILURE
        elif 'validation' in error_message:
            return GreeksErrorCategory.DATA_VALIDATION
        elif any(word in error_message for word in ['nan', 'infinity', 'divide', 'zero']):
            return GreeksErrorCategory.MATHEMATICAL_EDGE_CASE
        elif repair_context.get('days_to_expiration', 0) < 2:
            return GreeksErrorCategory.EXTREME_MARKET_CONDITIONS
        else:
            return GreeksErrorCategory.DATA_VALIDATION

    def get_repair_statistics(self) -> Dict[str, Any]:
        """Get comprehensive repair statistics"""

        total_attempts = self.repair_stats['total_repairs']
        success_rate = (self.repair_stats['successful_repairs'] / max(1, total_attempts)) * 100

        return {
            'total_repairs_attempted': total_attempts,
            'successful_repairs': self.repair_stats['successful_repairs'],
            'failed_repairs': self.repair_stats['failed_repairs'],
            'success_rate_percent': round(success_rate, 1),
            'interpolation_successes': self.repair_stats['interpolation_successes'],
            'interpolation_failures': self.repair_stats['interpolation_failures'],
            'fallback_applications': self.repair_stats['fallback_applications'],
            'error_categories': dict(self.repair_stats['error_categories']),
            'error_handler_stats': self.error_handler.get_error_summary()
        }

    def create_enhanced_validation_summary(self, repair_results: List[EnhancedRepairResult]) -> Dict[str, Any]:
        """Create comprehensive validation summary from multiple repair results"""

        if not repair_results:
            return {'error': 'No repair results provided'}

        try:
            summary = {
                'total_strikes_processed': len(repair_results),
                'successful_repairs': sum(1 for r in repair_results if r.quality_score > 0.5),
                'quality_distribution': {
                    'high_quality': sum(1 for r in repair_results if r.quality_score > 0.8),
                    'medium_quality': sum(1 for r in repair_results if 0.5 < r.quality_score <= 0.8),
                    'low_quality': sum(1 for r in repair_results if r.quality_score <= 0.5)
                },
                'error_analysis': {
                    'most_common_categories': {},
                    'total_errors': sum(len(r.detailed_errors) for r in repair_results),
                    'critical_errors': sum(1 for r in repair_results
                                         if any(cat in [GreeksErrorCategory.MATHEMATICAL_EDGE_CASE,
                                                       GreeksErrorCategory.NUMERICAL_INSTABILITY]
                                               for cat in r.error_categories))
                },
                'repair_method_effectiveness': {
                    'interpolation_success_rate': 0.0,
                    'fallback_usage_rate': 0.0,
                    'average_quality_by_method': {}
                },
                'safety_analysis': {
                    'all_safety_checks_passed': sum(1 for r in repair_results if all(r.safety_checks_passed.values())),
                    'safety_check_details': {}
                },
                'recommendations': []
            }

            # Calculate error category frequencies
            all_categories = [cat for r in repair_results for cat in r.error_categories]
            for category in all_categories:
                category_name = category.value
                summary['error_analysis']['most_common_categories'][category_name] = \
                    summary['error_analysis']['most_common_categories'].get(category_name, 0) + 1

            # Calculate repair method effectiveness
            total_with_interpolation = sum(1 for r in repair_results if r.interpolated_fields)
            total_with_fallback = sum(1 for r in repair_results if r.fallback_fields)

            if total_with_interpolation > 0:
                summary['repair_method_effectiveness']['interpolation_success_rate'] = \
                    (sum(r.quality_score for r in repair_results if r.interpolated_fields) / total_with_interpolation) * 100

            if total_with_fallback > 0:
                summary['repair_method_effectiveness']['fallback_usage_rate'] = \
                    (total_with_fallback / len(repair_results)) * 100

            # Generate recommendations
            if summary['quality_distribution']['low_quality'] > len(repair_results) * 0.3:
                summary['recommendations'].append("High proportion of low-quality repairs detected - consider improving data sources")

            if summary['error_analysis']['critical_errors'] > 0:
                summary['recommendations'].append("Critical calculation errors detected - review mathematical edge cases")

            if summary['safety_analysis']['all_safety_checks_passed'] < len(repair_results) * 0.8:
                summary['recommendations'].append("Safety check failures detected - review calculation stability")

            return summary

        except Exception as e:
            self.logger.error(f"Failed to create validation summary: {str(e)}")
            return {'error': f'Summary generation failed: {str(e)}'}


# Factory function for enhanced Greeks validator
def create_enhanced_greeks_validator(ticker: str) -> EnhancedGreeksValidator:
    """Create an enhanced Greeks validator instance"""
    return EnhancedGreeksValidator(ticker)


# Enhanced default validator for backward compatibility
enhanced_default_greeks_validator = EnhancedGreeksValidator("DEFAULT")