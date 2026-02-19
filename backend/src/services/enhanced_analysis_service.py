"""
Enhanced Analysis Service with Hybrid Greeks Integration

This service integrates all the enhanced Greeks calculation, validation, and repair
mechanisms to provide superior options analysis with multi-source data validation.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import date, timedelta, datetime
import json
import logging
from typing import Any, Dict, Optional, List, Tuple

# Import enhanced components
from ..analytics.finviz_greeks_extractor import FinvizGreeksExtractor, get_finviz_greeks_for_analysis
from ..analytics.greeks_comparison_validator import GreeksComparisonValidator
from ..analytics.greeks_repair import GreeksValidator, default_greeks_validator
from ..analytics.vega_optimizer import VegaOptimizer, get_optimized_vega

# Import existing analysis components
from ..analytics.analysis import analyze_undervalued_options_with_greeks
from ..my_libs_py3.my_data import PriceDataFetcher
from .analysis_service import universal_binomial_pricer  # Existing binomial pricer


class EnhancedAnalysisService:
    """
    Enhanced analysis service with hybrid Greeks and multi-source validation.

    This service coordinates between Finviz API data, calculated Greeks, and
    intelligent repair mechanisms to provide the highest quality options analysis.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Initialize enhanced components
        self.finviz_extractor = FinvizGreeksExtractor()
        self.comparison_validator = GreeksComparisonValidator()
        self.greeks_validator = default_greeks_validator
        self.vega_optimizer = VegaOptimizer()

        # Initialize data fetcher
        self.price_fetcher = PriceDataFetcher()

    async def analyze_options_enhanced(
        self,
        ticker: str,
        expiration_date: str,
        use_hybrid_greeks: bool = True,
        quality_threshold: float = 0.6
    ) -> Dict[str, Any]:
        """
        Perform enhanced options analysis with hybrid Greeks validation.

        Args:
            ticker: Stock ticker symbol
            expiration_date: Option expiration date (YYYY-MM-DD)
            use_hybrid_greeks: Whether to use hybrid Greeks approach
            quality_threshold: Minimum quality threshold for analysis inclusion

        Returns:
            Enhanced analysis results with quality metrics
        """
        analysis_results = {
            'metadata': {
                'ticker': ticker,
                'expiration_date': expiration_date,
                'analysis_timestamp': datetime.now(),
                'hybrid_greeks_used': use_hybrid_greeks,
                'quality_threshold': quality_threshold
            },
            'data_quality': {
                'finviz_quality': None,
                'calculated_quality': None,
                'hybrid_quality': None,
                'overall_assessment': 'pending'
            },
            'options_analysis': {},
            'greeks_comparison': {},
            'quality_report': {},
            'performance_metrics': {
                'calculation_method_breakdown': {},
                'processing_time_ms': 0
            }
        }

        start_time = datetime.now()

        try:
            # Step 1: Fetch Finviz Greeks data
            self.logger.info(f"Fetching Finviz Greeks for {ticker} expiration {expiration_date}")
            finviz_greeks, finviz_validation = await self._fetch_finviz_greeks(
                ticker, expiration_date
            )

            # Step 2: Perform traditional analysis to get calculated Greeks
            self.logger.info(f"Performing calculated Greeks analysis for {ticker}")
            calculated_analysis = await self._perform_calculated_analysis(
                ticker, expiration_date
            )

            # Step 3: Extract calculated Greeks from analysis
            calculated_greeks = self._extract_calculated_greeks(calculated_analysis)

            # Step 4: Perform comprehensive comparison if both sources available
            if finviz_greeks and calculated_greeks and use_hybrid_greeks:
                self.logger.info("Performing comprehensive Greeks comparison")
                comparison_results = self.comparison_validator.compare_greeks_comprehensive(
                    finviz_greeks, calculated_greeks, None
                )
                analysis_results['greeks_comparison'] = comparison_results

                # Step 5: Create hybrid Greeks
                hybrid_greeks = self.comparison_validator.create_hybrid_greeks(
                    finviz_greeks, calculated_greeks, comparison_results
                )

                # Step 6: Apply enhanced repair and validation
                repaired_analysis = await self._apply_enhanced_repair(
                    hybrid_greeks, ticker, expiration_date
                )

                analysis_results['options_analysis'] = repaired_analysis
                analysis_results['data_quality']['hybrid_quality'] = self._calculate_hybrid_quality(
                    repaired_analysis
                )

            else:
                # Fallback to single-source analysis
                self.logger.info("Using single-source analysis (calculated Greeks only)")
                analysis_results['options_analysis'] = calculated_analysis
                analysis_results['data_quality']['calculated_quality'] = self._calculate_calculated_quality(
                    calculated_analysis
                )

            # Step 7: Generate quality report
            analysis_results['quality_report'] = self._generate_quality_report(
                finviz_validation, calculated_analysis, analysis_results.get('greeks_comparison')
            )

            # Step 8: Calculate performance metrics
            end_time = datetime.now()
            analysis_results['performance_metrics']['processing_time_ms'] = (
                (end_time - start_time).total_seconds() * 1000
            )
            analysis_results['performance_metrics']['calculation_method_breakdown'] = self._get_method_breakdown(
                analysis_results
            )

            # Step 9: Overall quality assessment
            analysis_results['data_quality']['overall_assessment'] = self._assess_overall_quality(
                analysis_results, quality_threshold
            )

            self.logger.info(f"Enhanced analysis completed for {ticker} in "
                           f"{analysis_results['performance_metrics']['processing_time_ms']:.1f}ms")

        except Exception as e:
            self.logger.error(f"Enhanced analysis failed for {ticker}: {str(e)}")
            analysis_results['error'] = str(e)
            analysis_results['data_quality']['overall_assessment'] = 'failed'

        return analysis_results

    async def _fetch_finviz_greeks(self, ticker: str, expiration_date: str) -> Tuple[Dict, Dict]:
        """Fetch and validate Finviz Greeks data."""
        try:
            finviz_greeks, validation_results = get_finviz_greeks_for_analysis(
                ticker, expiration_date, self.price_fetcher
            )
            return finviz_greeks, validation_results
        except Exception as e:
            self.logger.warning(f"Failed to fetch Finviz Greeks for {ticker}: {str(e)}")
            return {}, {'overall_quality': 0.0, 'error': str(e)}

    async def _perform_calculated_analysis(self, ticker: str, expiration_date: str) -> Dict:
        """Perform traditional calculated Greeks analysis."""
        try:
            # Use existing analysis function but with enhanced error handling
            analysis_results = analyze_undervalued_options_with_greeks(
                ticker=ticker,
                expiration_date=expiration_date,
                price_fetcher=self.price_fetcher
            )
            return analysis_results
        except Exception as e:
            self.logger.error(f"Calculated analysis failed for {ticker}: {str(e)}")
            return {'error': str(e), 'undervalued_options': [], 'greeks_by_strike': {}}

    def _extract_calculated_greeks(self, calculated_analysis: Dict) -> Dict:
        """Extract Greeks from calculated analysis results."""
        if 'greeks_by_strike' not in calculated_analysis:
            return {}

        greeks_by_strike = {}
        for strike, strike_data in calculated_analysis['greeks_by_strike'].items():
            greeks_by_strike[float(strike)] = strike_data

        return greeks_by_strike

    async def _apply_enhanced_repair(self, hybrid_greeks: Dict, ticker: str,
                                   expiration_date: str) -> Dict:
        """Apply enhanced repair mechanisms to hybrid Greeks."""
        repaired_results = {
            'strikes_analysis': {},
            'repair_summary': {
                'total_strikes': len(hybrid_greeks),
                'high_confidence': 0,
                'medium_confidence': 0,
                'low_confidence': 0,
                'avoided': 0
            },
            'undervalued_options': []
        }

        # Get market data for context
        current_price = await self._get_current_stock_price(ticker)

        for strike, strike_data in hybrid_greeks.items():
            try:
                # Apply enhanced validation and repair
                repair_result = self.greeks_validator.validate_multi_source_greeks(
                    strike=strike,
                    calculated_greeks=strike_data,
                    finviz_greeks=None,  # Already integrated in hybrid
                    market_data={'spot_price': current_price}
                )

                # Store repair result
                repaired_results['strikes_analysis'][strike] = {
                    'repaired_greeks': repair_result.repaired_data,
                    'quality_metrics': {
                        'quality_score': repair_result.quality_score,
                        'confidence_score': repair_result.confidence_score,
                        'recommended_usage': repair_result.recommended_usage,
                        'theoretical_validity_score': repair_result.theoretical_validity_score
                    },
                    'repair_details': {
                        'repairs_made': repair_result.repairs_made,
                        'interpolated_fields': repair_result.interpolated_fields,
                        'fallback_fields': repair_result.fallback_fields
                    }
                }

                # Update summary counts
                usage = repair_result.recommended_usage
                if usage == 'high_confidence':
                    repaired_results['repair_summary']['high_confidence'] += 1
                elif usage == 'medium_confidence':
                    repaired_results['repair_summary']['medium_confidence'] += 1
                elif usage == 'low_confidence':
                    repaired_results['repair_summary']['low_confidence'] += 1
                else:
                    repaired_results['repair_summary']['avoided'] += 1

                # Identify undervalued options (simplified logic)
                self._identify_undervalued_from_repaired(
                    strike, repair_result, repaired_results['undervalued_options']
                )

            except Exception as e:
                self.logger.warning(f"Failed to repair Greeks for strike {strike}: {str(e)}")
                repaired_results['repair_summary']['avoided'] += 1

        return repaired_results

    async def _get_current_stock_price(self, ticker: str) -> float:
        """Get current stock price for analysis context."""
        try:
            # Use existing price fetching logic
            price_data = self.price_fetcher.get_current_price(ticker)
            return price_data.get('price', 100.0) if price_data else 100.0
        except:
            self.logger.warning(f"Could not fetch current price for {ticker}, using default")
            return 100.0

    def _identify_undervalued_from_repaired(self, strike: float, repair_result, undervalued_list: List):
        """Identify undervalued options from repaired Greeks data."""
        # Simplified undervaluation logic - could be enhanced
        if repair_result.recommended_usage in ['high_confidence', 'medium_confidence']:
            for option_type in ['call', 'put']:
                option_data = repair_result.repaired_data.get(option_type, {})
                model_price = option_data.get('model_price')
                market_price = option_data.get('market_price')

                if model_price and market_price and model_price > market_price * 1.05:
                    undervalued_list.append({
                        'Strike': strike,
                        'Type': option_type.capitalize(),
                        'Model Price': model_price,
                        'Market Price': market_price,
                        'Undervaluation %': ((model_price - market_price) / market_price) * 100,
                        'Quality Score': repair_result.quality_score,
                        'Recommended Usage': repair_result.recommended_usage
                    })

    def _calculate_hybrid_quality(self, analysis_results: Dict) -> Dict:
        """Calculate quality metrics for hybrid analysis."""
        strikes_analysis = analysis_results.get('strikes_analysis', {})

        if not strikes_analysis:
            return {'overall_score': 0.0, 'method': 'hybrid'}

        quality_scores = []
        confidence_scores = []

        for strike_data in strikes_analysis.values():
            metrics = strike_data.get('quality_metrics', {})
            quality_scores.append(metrics.get('quality_score', 0.0))
            confidence_scores.append(metrics.get('confidence_score', 0.0))

        return {
            'overall_score': np.mean(quality_scores),
            'confidence_score': np.mean(confidence_scores),
            'method': 'hybrid',
            'strikes_analyzed': len(strikes_analysis)
        }

    def _calculate_calculated_quality(self, analysis_results: Dict) -> Dict:
        """Calculate quality metrics for calculated-only analysis."""
        greeks_by_strike = analysis_results.get('greeks_by_strike', {})

        if not greeks_by_strike:
            return {'overall_score': 0.0, 'method': 'calculated'}

        # Simplified quality calculation for calculated Greeks
        total_strikes = len(greeks_by_strike)
        valid_strikes = sum(
            1 for strike_data in greeks_by_strike.values()
            if any(
                option_data.get('delta') is not None
                for option_data in strike_data.values()
                if isinstance(option_data, dict)
            )
        )

        quality_score = valid_strikes / total_strikes if total_strikes > 0 else 0.0

        return {
            'overall_score': quality_score,
            'method': 'calculated',
            'strikes_analyzed': total_strikes,
            'valid_strikes': valid_strikes
        }

    def _generate_quality_report(self, finviz_validation: Dict, calculated_analysis: Dict,
                               comparison_results: Optional[Dict]) -> Dict:
        """Generate comprehensive quality report."""
        report = {
            'finviz_assessment': finviz_validation,
            'calculated_assessment': {
                'data_available': 'greeks_by_strike' in calculated_analysis,
                'error': calculated_analysis.get('error'),
                'strikes_count': len(calculated_analysis.get('greeks_by_strike', {}))
            },
            'comparison_assessment': None,
            'recommendations': []
        }

        if comparison_results:
            report['comparison_assessment'] = {
                'common_strikes': comparison_results['metadata']['common_strikes'],
                'finviz_preferred': comparison_results['recommendations']['summary']['finviz_preferred'],
                'calculated_preferred': comparison_results['recommendations']['summary']['calculated_preferred'],
                'hybrid_recommended': comparison_results['recommendations']['summary']['hybrid_recommended']
            }

        # Generate recommendations
        if finviz_validation.get('overall_quality', 0) > 0.8:
            report['recommendations'].append("High-quality Finviz Greeks available - recommend hybrid approach")
        elif calculated_analysis.get('greeks_by_strike'):
            report['recommendations'].append("Use calculated Greeks - Finviz quality insufficient")
        else:
            report['recommendations'].append("Insufficient data quality - analysis may be unreliable")

        return report

    def _get_method_breakdown(self, analysis_results: Dict) -> Dict:
        """Get breakdown of calculation methods used."""
        breakdown = {
            'vega_analytical': 0,
            'vega_binomial': 0,
            'rho_finite_difference': 0,
            'rho_approximation': 0,
            'greeks_hybrid': 0,
            'greeks_finviz_only': 0,
            'greeks_calculated_only': 0
        }

        # This would be populated based on actual method tracking
        # For now, return placeholder
        return breakdown

    def _assess_overall_quality(self, analysis_results: Dict, threshold: float) -> str:
        """Assess overall quality of analysis results."""
        data_quality = analysis_results.get('data_quality', {})

        # Get the highest quality score available
        quality_scores = [
            data_quality.get('hybrid_quality', {}).get('overall_score', 0),
            data_quality.get('calculated_quality', {}).get('overall_score', 0),
            data_quality.get('finviz_quality', {}).get('overall_quality', 0)
        ]

        max_quality = max(quality_scores)

        if max_quality >= 0.85:
            return 'excellent'
        elif max_quality >= 0.70:
            return 'good'
        elif max_quality >= threshold:
            return 'acceptable'
        else:
            return 'poor'


# Global instance for easy access
enhanced_analysis_service = EnhancedAnalysisService()


async def analyze_options_with_hybrid_greeks(ticker: str, expiration_date: str,
                                           use_hybrid: bool = True,
                                           quality_threshold: float = 0.6) -> Dict[str, Any]:
    """
    Convenience function for enhanced options analysis.

    Args:
        ticker: Stock ticker symbol
        expiration_date: Option expiration date (YYYY-MM-DD)
        use_hybrid: Whether to use hybrid Greeks approach
        quality_threshold: Minimum quality threshold

    Returns:
        Enhanced analysis results
    """
    return await enhanced_analysis_service.analyze_options_enhanced(
        ticker, expiration_date, use_hybrid, quality_threshold
    )