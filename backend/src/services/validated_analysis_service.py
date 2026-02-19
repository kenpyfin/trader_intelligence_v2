"""
Validated Analysis Service

This service integrates comprehensive data validation into the options analysis pipeline.
It performs data quality checks before analysis begins, includes cross-source validation
between Finviz and calculated data, and ensures data quality scores meet thresholds
for strategy recommendations.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import asyncio
import logging
from datetime import date
from typing import Any, Dict, Optional, List

# Import original analysis components
from .analysis_service import run_full_analysis as original_run_full_analysis
from .enhanced_analysis_service import EnhancedAnalysisService

# Import validation systems
from ..analytics.analysis_with_validation import run_analysis_with_validation
from ..analytics.strategy_validation_gates import (
    StrategyValidationGates,
    TradingStrategy,
    validate_for_strategy
)
from ..analytics.validation_integration import validate_options_for_analysis
from ..analytics.quality_config import QualityAssessment
from ..analytics.greeks_comparison_validator import GreeksComparisonValidator


class ValidatedAnalysisService:
    """
    Comprehensive analysis service with integrated validation gates.

    This service provides:
    1. Pre-analysis data quality validation
    2. Cross-source validation between Finviz and calculated Greeks
    3. Strategy-specific validation gates
    4. Quality-threshold-based strategy filtering
    5. Enhanced reporting with validation insights
    """

    def __init__(self):
        """Initialize the validated analysis service."""
        self.logger = logging.getLogger(__name__)

        # Initialize validation components
        self.strategy_gates = StrategyValidationGates()
        self.enhanced_service = EnhancedAnalysisService()
        self.comparison_validator = GreeksComparisonValidator()

        # Default validation settings
        self.default_validation_mode = 'standard'  # 'strict', 'standard', 'permissive'
        self.default_min_quality_threshold = 0.5
        self.enable_cross_source_validation = True

    async def run_validated_analysis(self,
                                   ticker: str,
                                   expiration_date: date,
                                   r_current: float = 0.045,
                                   rate_source: str = 'etf',
                                   methodology: str = 'holistic-market-edge',
                                   gpt_model: str = 'gpt-5',
                                   override_price: float = None,
                                   validation_mode: str = None,
                                   min_quality_threshold: float = None,
                                   target_strategies: List[str] = None) -> Dict[str, Any]:
        """
        Run comprehensive options analysis with integrated validation.

        Args:
            ticker: Stock ticker symbol
            expiration_date: Option expiration date
            r_current: Risk-free rate
            rate_source: Rate source ('etf' or 'treasury')
            methodology: Analysis methodology
            gpt_model: GPT model for verdict generation
            override_price: Manual price override
            validation_mode: 'strict', 'standard', or 'permissive'
            min_quality_threshold: Minimum quality score (0.0-1.0)
            target_strategies: List of strategy names to validate against

        Returns:
            Comprehensive analysis results with validation report
        """
        # Set validation parameters
        validation_mode = validation_mode or self.default_validation_mode
        min_quality_threshold = min_quality_threshold or self.default_min_quality_threshold

        self.logger.info(f"Starting validated analysis for {ticker} (mode: {validation_mode})")

        try:
            # Step 1: Run analysis with validation
            analysis_result = run_analysis_with_validation(
                ticker=ticker,
                expiration_date=expiration_date,
                r_current=r_current,
                rate_source=rate_source,
                analysis_method=methodology,
                override_price=override_price,
                gpt_model=gpt_model,
                validation_mode=validation_mode,
                min_quality_threshold=min_quality_threshold
            )

            # Check if validation rejected the analysis
            if analysis_result.get('status') in ['rejected', 'error']:
                return self._handle_validation_failure(analysis_result, ticker, expiration_date)

            # Step 2: Perform cross-source validation if enabled
            if self.enable_cross_source_validation:
                self.logger.info("Performing cross-source validation...")
                cross_source_results = await self._perform_cross_source_validation(
                    analysis_result, ticker, expiration_date
                )
                analysis_result['cross_source_validation'] = cross_source_results

            # Step 3: Validate against target strategies if specified
            if target_strategies:
                strategy_validation_results = self._validate_strategies(
                    analysis_result, ticker, expiration_date, target_strategies
                )
                analysis_result['strategy_validation'] = strategy_validation_results

                # Filter strategy recommendations based on validation
                analysis_result['filtered_strategies'] = self._filter_strategy_recommendations(
                    strategy_validation_results
                )

            # Step 4: Generate comprehensive validation summary
            analysis_result['validation_summary'] = self._generate_comprehensive_summary(
                analysis_result, validation_mode, min_quality_threshold
            )

            # Step 5: Add validation-aware recommendations
            analysis_result['validation_enhanced_recommendations'] = self._generate_enhanced_recommendations(
                analysis_result
            )

            self.logger.info(f"Validated analysis complete for {ticker}")
            return analysis_result

        except Exception as e:
            self.logger.error(f"Validated analysis failed for {ticker}: {e}")
            return {
                'status': 'error',
                'error_type': 'service_failure',
                'message': f'Validated analysis service failed: {e}',
                'ticker': ticker,
                'expiration_date': expiration_date.isoformat(),
                'recommendations': [
                    'Check system logs for detailed error information',
                    'Try again with simpler analysis methodology',
                    'Contact system administrator if error persists'
                ]
            }

    async def _perform_cross_source_validation(self,
                                             analysis_result: Dict[str, Any],
                                             ticker: str,
                                             expiration_date: date) -> Dict[str, Any]:
        """Perform cross-source validation between Finviz and calculated Greeks."""

        try:
            # Get options data from analysis results
            options_data = analysis_result.get('analysis_results', {}).get(
                'options_positioning', {}
            ).get('greeks_by_strike', {})

            if not options_data:
                return {
                    'status': 'skipped',
                    'reason': 'No options data available for cross-validation'
                }

            # Get Finviz Greeks data
            self.logger.info("Fetching Finviz Greeks for comparison...")
            finviz_greeks, finviz_validation = await self.enhanced_service._fetch_finviz_greeks(
                ticker, expiration_date.strftime('%Y-%m-%d')
            )

            if not finviz_greeks:
                return {
                    'status': 'partial',
                    'reason': 'Finviz data unavailable for comparison',
                    'calculated_data_quality': self._assess_calculated_data_quality(options_data)
                }

            # Perform comprehensive comparison
            comparison_results = self.comparison_validator.compare_greeks_comprehensive(
                finviz_data=finviz_greeks,
                calculated_data=options_data,
                market_data={}  # Could be enhanced with additional market data
            )

            return {
                'status': 'completed',
                'comparison_results': comparison_results,
                'data_source_recommendations': self._generate_source_recommendations(comparison_results),
                'cross_validation_quality_score': self._calculate_cross_validation_score(comparison_results)
            }

        except Exception as e:
            self.logger.error(f"Cross-source validation failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
                'fallback_assessment': 'Using calculated data only due to cross-validation failure'
            }

    def _validate_strategies(self,
                           analysis_result: Dict[str, Any],
                           ticker: str,
                           expiration_date: date,
                           target_strategies: List[str]) -> Dict[str, Any]:
        """Validate options data against specific trading strategies."""

        validation_results = {
            'strategies_tested': target_strategies,
            'validation_results': {},
            'approved_strategies': [],
            'conditional_strategies': [],
            'rejected_strategies': []
        }

        # Get options data and spot price
        analysis_data = analysis_result.get('analysis_results', {})
        options_data = analysis_data.get('options_positioning', {}).get('greeks_by_strike', {})
        spot_price = analysis_data.get('market_context', {}).get('current_price')

        if not options_data:
            validation_results['error'] = 'No options data available for strategy validation'
            return validation_results

        for strategy_name in target_strategies:
            try:
                # Convert string to strategy enum
                strategy_enum = TradingStrategy(strategy_name.lower().replace(' ', '_').replace('-', '_'))

                # Validate strategy
                strategy_result = validate_for_strategy(
                    strategy=strategy_enum,
                    options_data=options_data,
                    ticker=ticker,
                    expiration_date=expiration_date.strftime('%Y-%m-%d'),
                    spot_price=spot_price
                )

                validation_results['validation_results'][strategy_name] = {
                    'gate_decision': strategy_result.gate_decision,
                    'decision_confidence': strategy_result.decision_confidence,
                    'quality_score_vs_threshold': strategy_result.quality_score_vs_threshold,
                    'recommended_position_size_factor': strategy_result.recommended_position_size_factor,
                    'risk_warnings': strategy_result.risk_warnings,
                    'approval_conditions': strategy_result.approval_conditions
                }

                # Categorize strategies by validation result
                if strategy_result.gate_decision == 'APPROVE':
                    validation_results['approved_strategies'].append(strategy_name)
                elif strategy_result.gate_decision == 'APPROVE_WITH_CAUTION':
                    validation_results['conditional_strategies'].append(strategy_name)
                else:
                    validation_results['rejected_strategies'].append(strategy_name)

            except Exception as e:
                self.logger.warning(f"Strategy validation failed for {strategy_name}: {e}")
                validation_results['validation_results'][strategy_name] = {
                    'gate_decision': 'ERROR',
                    'error': str(e)
                }
                validation_results['rejected_strategies'].append(strategy_name)

        return validation_results

    def _filter_strategy_recommendations(self, strategy_validation: Dict[str, Any]) -> Dict[str, Any]:
        """Filter strategy recommendations based on validation results."""

        filtered = {
            'recommended_strategies': [],
            'conditional_strategies': [],
            'not_recommended_strategies': [],
            'filtering_rationale': {}
        }

        for strategy_name, result in strategy_validation.get('validation_results', {}).items():
            gate_decision = result.get('gate_decision', 'REJECT')
            confidence = result.get('decision_confidence', 0.0)

            if gate_decision == 'APPROVE' and confidence >= 0.7:
                filtered['recommended_strategies'].append({
                    'strategy': strategy_name,
                    'confidence': confidence,
                    'position_size_factor': result.get('recommended_position_size_factor', 1.0),
                    'conditions': result.get('approval_conditions', [])
                })

            elif gate_decision in ['APPROVE', 'APPROVE_WITH_CAUTION']:
                filtered['conditional_strategies'].append({
                    'strategy': strategy_name,
                    'confidence': confidence,
                    'position_size_factor': result.get('recommended_position_size_factor', 0.5),
                    'warnings': result.get('risk_warnings', []),
                    'conditions': result.get('approval_conditions', [])
                })

            else:
                filtered['not_recommended_strategies'].append({
                    'strategy': strategy_name,
                    'reason': 'Failed validation gates',
                    'improvement_needed': result.get('improvement_recommendations', [])
                })

            filtered['filtering_rationale'][strategy_name] = f"Gate: {gate_decision}, Confidence: {confidence:.1%}"

        return filtered

    def _handle_validation_failure(self,
                                 failed_result: Dict[str, Any],
                                 ticker: str,
                                 expiration_date: date) -> Dict[str, Any]:
        """Handle cases where validation fails but analysis might be partially useful."""

        # Try to provide some insights even with failed validation
        enhanced_response = {
            'status': failed_result.get('status'),
            'primary_failure_reason': failed_result.get('message'),
            'ticker': ticker,
            'expiration_date': expiration_date.isoformat(),
            'validation_failure_details': failed_result.get('validation_report'),
            'partial_analysis_available': False,
            'alternative_recommendations': []
        }

        # Check if we have partial analysis results that might be useful
        if failed_result.get('analysis_results'):
            enhanced_response['partial_analysis_available'] = True
            enhanced_response['partial_analysis'] = self._extract_safe_insights(
                failed_result['analysis_results']
            )

        # Generate alternative recommendations
        enhanced_response['alternative_recommendations'] = self._generate_alternative_recommendations(
            failed_result, ticker
        )

        # Suggest fallback approaches
        enhanced_response['fallback_options'] = [
            {
                'approach': 'Try different expiration date',
                'rationale': 'Other expiration dates may have better data quality',
                'action': f'Check available expiration dates for {ticker}'
            },
            {
                'approach': 'Use simpler analysis methodology',
                'rationale': 'Reduce data quality requirements',
                'action': 'Switch to basic analysis without complex Greeks requirements'
            },
            {
                'approach': 'Manual data review',
                'rationale': 'Assess data quality manually',
                'action': 'Review raw options data before proceeding with strategies'
            }
        ]

        return enhanced_response

    def _assess_calculated_data_quality(self, options_data: Dict[str, Any]) -> Dict[str, Any]:
        """Assess the quality of calculated Greeks data."""
        if not options_data:
            return {'quality_score': 0.0, 'assessment': 'No data available'}

        total_options = 0
        complete_options = 0
        required_greeks = ['delta', 'gamma', 'theta', 'vega']

        for strike_data in options_data.values():
            for option_type in ['call', 'put']:
                if option_type in strike_data:
                    total_options += 1
                    option_data = strike_data[option_type]
                    if all(greek in option_data and option_data[greek] is not None
                           for greek in required_greeks):
                        complete_options += 1

        quality_score = complete_options / max(total_options, 1)

        return {
            'quality_score': quality_score,
            'total_options': total_options,
            'complete_options': complete_options,
            'assessment': 'Good' if quality_score >= 0.8 else 'Fair' if quality_score >= 0.6 else 'Poor'
        }

    def _generate_source_recommendations(self, comparison_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate recommendations for data source usage based on cross-validation."""
        # This would analyze the comparison results and recommend which source to use
        # Implementation would depend on the structure of comparison_results
        return {
            'preferred_source': 'hybrid',
            'confidence_level': 'medium',
            'rationale': 'Use hybrid approach combining both sources',
            'specific_recommendations': [
                'Use Finviz data for liquid strikes',
                'Use calculated data where Finviz is incomplete',
                'Cross-validate critical strikes with both sources'
            ]
        }

    def _calculate_cross_validation_score(self, comparison_results: Dict[str, Any]) -> float:
        """Calculate a score representing cross-validation quality."""
        # Implementation would analyze agreement between sources
        # Return a score between 0.0 and 1.0
        return 0.75  # Placeholder

    def _generate_comprehensive_summary(self,
                                      analysis_result: Dict[str, Any],
                                      validation_mode: str,
                                      min_quality_threshold: float) -> Dict[str, Any]:
        """Generate comprehensive validation summary."""
        validation_status = analysis_result.get('validation_status', 'unknown')
        quality_metrics = analysis_result.get('quality_metrics', {})

        return {
            'overall_validation_status': validation_status,
            'validation_mode_used': validation_mode,
            'quality_threshold_used': min_quality_threshold,
            'data_quality_assessment': {
                'overall_score': quality_metrics.get('overall_score', 0.0),
                'asset_type': quality_metrics.get('asset_type', 'unknown'),
                'processing_mode': quality_metrics.get('processing_mode', 'unknown'),
                'confidence_level': quality_metrics.get('confidence_level', 'unknown')
            },
            'validation_highlights': self._extract_validation_highlights(analysis_result),
            'quality_improvement_potential': self._assess_improvement_potential(analysis_result),
            'data_reliability_assessment': self._assess_data_reliability(analysis_result)
        }

    def _generate_enhanced_recommendations(self, analysis_result: Dict[str, Any]) -> List[str]:
        """Generate enhanced recommendations based on validation results."""
        recommendations = []

        quality_score = analysis_result.get('quality_metrics', {}).get('overall_score', 0.0)
        confidence_level = analysis_result.get('quality_metrics', {}).get('confidence_level', 'unknown')

        if quality_score >= 0.8:
            recommendations.append("High data quality - proceed with full analysis confidence")
        elif quality_score >= 0.6:
            recommendations.append("Good data quality - standard analysis recommended")
        else:
            recommendations.append("Moderate data quality - use enhanced monitoring")

        if confidence_level == 'low':
            recommendations.append("Consider reducing position sizes due to data quality concerns")

        # Add strategy-specific recommendations if available
        if 'strategy_validation' in analysis_result:
            approved_strategies = analysis_result['strategy_validation'].get('approved_strategies', [])
            if approved_strategies:
                recommendations.append(f"Recommended strategies: {', '.join(approved_strategies)}")

        return recommendations

    def _extract_validation_highlights(self, analysis_result: Dict[str, Any]) -> List[str]:
        """Extract key validation highlights for summary."""
        highlights = []

        if 'data_quality_insights' in analysis_result:
            insights = analysis_result['data_quality_insights']
            strengths = insights.get('key_strengths', [])
            weaknesses = insights.get('key_weaknesses', [])

            if strengths:
                highlights.append(f"Strengths: {', '.join(strengths[:2])}")
            if weaknesses:
                highlights.append(f"Areas for improvement: {', '.join(weaknesses[:2])}")

        return highlights

    def _assess_improvement_potential(self, analysis_result: Dict[str, Any]) -> str:
        """Assess potential for data quality improvement."""
        # Analyze validation results to determine improvement potential
        return "Medium - some data gaps can be addressed with alternative sources"

    def _assess_data_reliability(self, analysis_result: Dict[str, Any]) -> str:
        """Assess overall data reliability."""
        quality_score = analysis_result.get('quality_metrics', {}).get('overall_score', 0.0)

        if quality_score >= 0.8:
            return "High - data meets reliability standards for most strategies"
        elif quality_score >= 0.6:
            return "Medium - data suitable for standard analysis with monitoring"
        else:
            return "Low - data requires careful interpretation and risk adjustment"

    def _extract_safe_insights(self, analysis_results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract safe insights from partial analysis results."""
        safe_insights = {}

        # Extract basic market context that doesn't depend on options data quality
        if 'market_context' in analysis_results:
            safe_insights['market_context'] = {
                'current_price': analysis_results['market_context'].get('current_price'),
                'ticker': analysis_results['market_context'].get('ticker')
            }

        return safe_insights

    def _generate_alternative_recommendations(self,
                                            failed_result: Dict[str, Any],
                                            ticker: str) -> List[str]:
        """Generate alternative recommendations when validation fails."""
        recommendations = []

        error_type = failed_result.get('error_type', 'unknown')

        if error_type == 'validation_gate_failure':
            recommendations.extend([
                f"Try different expiration dates for {ticker} with better liquidity",
                "Consider using manual data review before proceeding",
                "Switch to simpler strategies with lower data quality requirements"
            ])
        elif error_type == 'data_fetch_failure':
            recommendations.extend([
                "Check data source connectivity and try again",
                "Verify ticker symbol and expiration date",
                "Try during market hours for better data availability"
            ])

        recommendations.append("Consider paper trading first to test data quality impact")

        return recommendations[:5]  # Limit to top 5 recommendations


# Global instance for easy access
default_validated_service = ValidatedAnalysisService()


# Convenience functions for backward compatibility
async def run_full_analysis_with_validation(ticker: str,
                                          expiration_date: date,
                                          validation_mode: str = 'standard',
                                          **kwargs) -> Dict[str, Any]:
    """Run full analysis with validation (drop-in replacement for original function)."""
    return await default_validated_service.run_validated_analysis(
        ticker=ticker,
        expiration_date=expiration_date,
        validation_mode=validation_mode,
        **kwargs
    )


async def run_strategy_focused_analysis(ticker: str,
                                      expiration_date: date,
                                      target_strategies: List[str],
                                      **kwargs) -> Dict[str, Any]:
    """Run analysis focused on specific trading strategies."""
    return await default_validated_service.run_validated_analysis(
        ticker=ticker,
        expiration_date=expiration_date,
        target_strategies=target_strategies,
        **kwargs
    )