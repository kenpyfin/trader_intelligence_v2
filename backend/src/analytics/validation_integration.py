"""
Validation Integration Module

This module provides integration utilities for incorporating the Core Validation Engine
into the existing analysis pipeline. It bridges the core validation system with the
current enhanced Greeks validation and analysis workflow.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

# Import core validation engine
from .core_validation_engine import (
    CoreValidationEngine,
    CoreValidationReport,
    ValidationCategory,
    ValidationSeverity,
    QualityLevel
)

# Import existing validation systems for integration
from .enhanced_greeks_validation import EnhancedGreeksValidator, EnhancedGreeksValidationResult
from .quality_config import QualityAssessment
from .greeks_comparison_validator import GreeksComparisonValidator


class ValidationOrchestrator:
    """
    Orchestrates between the new Core Validation Engine and existing validation systems.

    This class provides a unified interface that:
    1. Runs core validation for the three critical categories
    2. Integrates with existing enhanced Greeks validation
    3. Provides consolidated recommendations for the analysis pipeline
    """

    def __init__(self, asset_type: str = "medium_liquidity"):
        """
        Initialize the validation orchestrator.

        Args:
            asset_type: Asset liquidity type (high_liquidity, medium_liquidity, low_liquidity)
        """
        self.logger = logging.getLogger(__name__)

        # Initialize validation engines
        self.core_validator = CoreValidationEngine(asset_type)
        self.enhanced_validator = EnhancedGreeksValidator()
        self.quality_assessment = QualityAssessment(asset_type)
        self.comparison_validator = GreeksComparisonValidator()

        self.asset_type = asset_type

    def run_comprehensive_validation(self,
                                   options_data: Dict[str, Any],
                                   ticker: str,
                                   expiration_date: str,
                                   spot_price: Optional[float] = None,
                                   risk_free_rate: float = 0.05,
                                   time_to_expiry: float = 0.25) -> Dict[str, Any]:
        """
        Run comprehensive validation using both core and enhanced validation systems.

        Args:
            options_data: Options data dictionary (greeks_by_strike format)
            ticker: Stock ticker symbol
            expiration_date: Option expiration date string
            spot_price: Current spot price
            risk_free_rate: Risk-free rate for Greeks validation
            time_to_expiry: Time to expiration in years

        Returns:
            Comprehensive validation results with integrated recommendations
        """
        self.logger.info(f"Starting comprehensive validation for {ticker} {expiration_date}")

        validation_results = {
            'ticker': ticker,
            'expiration_date': expiration_date,
            'validation_timestamp': datetime.now(),
            'asset_type': self.asset_type,
            'validation_summary': {
                'core_validation': None,
                'enhanced_validation': None,
                'integration_status': 'pending'
            },
            'consolidated_recommendations': {},
            'processing_decisions': {},
            'data_quality_metrics': {}
        }

        try:
            # Step 1: Run Core Validation Engine
            self.logger.info("Running core validation engine...")
            core_report = self.core_validator.validate_options_data(
                options_data=options_data,
                ticker=ticker,
                expiration_date=expiration_date,
                spot_price=spot_price
            )

            validation_results['validation_summary']['core_validation'] = {
                'status': 'completed',
                'overall_score': core_report.combined_quality_score,
                'category_scores': {
                    'pricing': core_report.overall_pricing_score,
                    'greeks': core_report.overall_greeks_score,
                    'liquidity': core_report.overall_liquidity_score
                },
                'strikes_by_quality': {
                    'excellent': len(core_report.excellent_strikes),
                    'good': len(core_report.good_strikes),
                    'acceptable': len(core_report.acceptable_strikes),
                    'poor': len(core_report.poor_strikes),
                    'failed': len(core_report.failed_strikes)
                },
                'critical_issues': len(core_report.critical_issues),
                'high_priority_issues': len(core_report.high_priority_issues),
                'recommendation': core_report.overall_recommendation
            }

            # Step 2: Run Enhanced Greeks Validation (for comparison and integration)
            self.logger.info("Running enhanced Greeks validation...")
            enhanced_result = self.enhanced_validator.validate_and_enhance_greeks_data(
                greeks_by_strike=options_data,
                spot_price=spot_price or 100.0,  # Default if not provided
                risk_free_rate=risk_free_rate,
                time_to_expiry=time_to_expiry
            )

            validation_results['validation_summary']['enhanced_validation'] = {
                'status': 'completed',
                'original_quality_score': enhanced_result.original_quality_score,
                'enhanced_quality_score': enhanced_result.enhanced_quality_score,
                'confidence_score': enhanced_result.confidence_score,
                'repair_statistics': {
                    'repaired_strikes': enhanced_result.repaired_strikes_count,
                    'interpolated_strikes': enhanced_result.interpolated_strikes_count,
                    'fallback_strikes': enhanced_result.fallback_strikes_count
                },
                'strike_categorization': {
                    'excellent': len(enhanced_result.excellent_strikes),
                    'good': len(enhanced_result.good_strikes),
                    'acceptable': len(enhanced_result.acceptable_strikes),
                    'poor': len(enhanced_result.poor_strikes)
                }
            }

            # Step 3: Integrate results and create consolidated recommendations
            self.logger.info("Consolidating validation results...")
            consolidated = self._consolidate_validation_results(core_report, enhanced_result)
            validation_results['consolidated_recommendations'] = consolidated['recommendations']
            validation_results['processing_decisions'] = consolidated['decisions']
            validation_results['data_quality_metrics'] = consolidated['metrics']

            # Step 4: Create detailed strike-level analysis summary
            strike_summary = self._create_strike_level_summary(core_report, enhanced_result)
            validation_results['strike_analysis'] = strike_summary

            validation_results['validation_summary']['integration_status'] = 'completed'

            self.logger.info(f"Comprehensive validation completed. Overall recommendation: {consolidated['recommendations']['primary_recommendation']}")

        except Exception as e:
            self.logger.error(f"Validation error: {e}")
            validation_results['validation_summary']['integration_status'] = 'failed'
            validation_results['error'] = str(e)

            # Fallback to basic quality assessment
            try:
                basic_assessment = self._basic_quality_fallback(options_data)
                validation_results['fallback_assessment'] = basic_assessment
            except Exception as fallback_error:
                self.logger.error(f"Fallback assessment failed: {fallback_error}")

        return validation_results

    def _consolidate_validation_results(self,
                                      core_report: CoreValidationReport,
                                      enhanced_result: EnhancedGreeksValidationResult) -> Dict[str, Any]:
        """Consolidate results from core and enhanced validation systems."""

        # Weight the scores (core validation gets higher weight for decision making)
        core_weight = 0.7
        enhanced_weight = 0.3

        consolidated_score = (
            core_report.combined_quality_score * core_weight +
            enhanced_result.enhanced_quality_score * enhanced_weight
        )

        # Determine processing mode based on both systems
        core_can_proceed = core_report.processing_decision.get('can_proceed', False)
        enhanced_can_proceed = enhanced_result.confidence_score >= 0.5

        # Conservative approach - require both systems to agree on proceeding
        can_proceed = core_can_proceed and enhanced_can_proceed

        # Processing mode selection
        if consolidated_score >= 0.75 and core_report.combined_quality_score >= 0.7:
            processing_mode = "full_analysis"
            confidence_level = "high"
        elif consolidated_score >= 0.6 and core_can_proceed:
            processing_mode = "standard_analysis"
            confidence_level = "medium"
        elif consolidated_score >= 0.45 and (core_can_proceed or enhanced_can_proceed):
            processing_mode = "reduced_analysis"
            confidence_level = "low"
        else:
            processing_mode = "reject"
            confidence_level = "insufficient"

        # Generate primary recommendation
        if processing_mode == "full_analysis":
            primary_recommendation = f"PROCEED WITH CONFIDENCE: High quality data (combined score: {consolidated_score:.1%}). Both validation systems recommend full analysis."
        elif processing_mode == "standard_analysis":
            primary_recommendation = f"PROCEED: Good quality data (combined score: {consolidated_score:.1%}). Standard analysis recommended with monitoring."
        elif processing_mode == "reduced_analysis":
            primary_recommendation = f"PROCEED WITH CAUTION: Moderate quality data (combined score: {consolidated_score:.1%}). Use reduced analysis scope and enhanced monitoring."
        else:
            primary_recommendation = f"DO NOT PROCEED: Insufficient data quality (combined score: {consolidated_score:.1%}). Seek alternative data sources or expiration dates."

        # Focus strikes for analysis (intersection of high-quality strikes from both systems)
        core_usable = set(core_report.excellent_strikes + core_report.good_strikes)
        enhanced_excellent = set((s, 'call') for s in enhanced_result.excellent_strikes) | set((s, 'put') for s in enhanced_result.excellent_strikes)
        enhanced_good = set((s, 'call') for s in enhanced_result.good_strikes) | set((s, 'put') for s in enhanced_result.good_strikes)
        enhanced_usable = enhanced_excellent | enhanced_good

        # High confidence strikes (both systems agree)
        high_confidence_strikes = list(core_usable.intersection(enhanced_usable))

        # Medium confidence (either system considers good)
        medium_confidence_strikes = list((core_usable | enhanced_usable) - set(high_confidence_strikes))

        # Avoid strikes (both systems flag as problematic)
        core_avoid = set(core_report.failed_strikes + core_report.poor_strikes)
        enhanced_poor = set((s, 'call') for s in enhanced_result.poor_strikes) | set((s, 'put') for s in enhanced_result.poor_strikes)
        avoid_strikes = list(core_avoid.intersection(enhanced_poor))

        return {
            'recommendations': {
                'primary_recommendation': primary_recommendation,
                'processing_mode': processing_mode,
                'confidence_level': confidence_level,
                'can_proceed': can_proceed,
                'data_repair_recommended': enhanced_result.repaired_strikes_count > 0 or len(core_report.all_issues) > 5,
                'alternative_sources_recommended': len(core_report.critical_issues) > 10 or consolidated_score < 0.3
            },
            'decisions': {
                'focus_strikes': {
                    'high_confidence': high_confidence_strikes[:20],  # Limit for performance
                    'medium_confidence': medium_confidence_strikes[:15],
                    'total_usable': len(high_confidence_strikes) + len(medium_confidence_strikes)
                },
                'avoid_strikes': avoid_strikes,
                'position_sizing_adjustment': self._get_position_sizing_recommendation(consolidated_score, confidence_level),
                'monitoring_requirements': self._get_monitoring_requirements(core_report, enhanced_result)
            },
            'metrics': {
                'consolidated_quality_score': consolidated_score,
                'core_system_score': core_report.combined_quality_score,
                'enhanced_system_score': enhanced_result.enhanced_quality_score,
                'agreement_level': self._calculate_agreement_level(core_report, enhanced_result),
                'data_completeness': {
                    'pricing_completeness': core_report.overall_pricing_score,
                    'greeks_completeness': core_report.overall_greeks_score,
                    'liquidity_completeness': core_report.overall_liquidity_score
                },
                'repair_effectiveness': enhanced_result.enhanced_quality_score - enhanced_result.original_quality_score
            }
        }

    def _create_strike_level_summary(self,
                                   core_report: CoreValidationReport,
                                   enhanced_result: EnhancedGreeksValidationResult) -> Dict[str, Any]:
        """Create detailed strike-level analysis summary."""

        strike_summary = {
            'total_strikes_analyzed': core_report.total_strikes,
            'strikes_by_type': core_report.strikes_by_type,
            'quality_distribution': {
                'core_validation': {
                    'excellent': len(core_report.excellent_strikes),
                    'good': len(core_report.good_strikes),
                    'acceptable': len(core_report.acceptable_strikes),
                    'poor': len(core_report.poor_strikes),
                    'failed': len(core_report.failed_strikes)
                },
                'enhanced_validation': {
                    'excellent': len(enhanced_result.excellent_strikes),
                    'good': len(enhanced_result.good_strikes),
                    'acceptable': len(enhanced_result.acceptable_strikes),
                    'poor': len(enhanced_result.poor_strikes)
                }
            },
            'category_performance': {
                'strike_pricing': {
                    'average_score': core_report.overall_pricing_score,
                    'issues_count': len([i for i in core_report.all_issues if i.category == ValidationCategory.STRIKE_PRICING])
                },
                'greeks_completeness': {
                    'average_score': core_report.overall_greeks_score,
                    'issues_count': len([i for i in core_report.all_issues if i.category == ValidationCategory.GREEKS_COMPLETENESS])
                },
                'liquidity_indicators': {
                    'average_score': core_report.overall_liquidity_score,
                    'issues_count': len([i for i in core_report.all_issues if i.category == ValidationCategory.LIQUIDITY_INDICATORS])
                }
            },
            'repair_impact': {
                'strikes_repaired': enhanced_result.repaired_strikes_count,
                'repair_effectiveness': enhanced_result.enhanced_quality_score - enhanced_result.original_quality_score,
                'confidence_improvement': enhanced_result.confidence_score
            }
        }

        return strike_summary

    def _get_position_sizing_recommendation(self, score: float, confidence_level: str) -> str:
        """Get position sizing recommendation based on validation results."""
        if confidence_level == "high" and score >= 0.8:
            return "Normal position sizing acceptable"
        elif confidence_level == "medium" and score >= 0.6:
            return "Reduce position size by 20-30%"
        elif confidence_level == "low" and score >= 0.4:
            return "Reduce position size by 40-60%"
        else:
            return "Limit to very small exploratory positions only"

    def _get_monitoring_requirements(self,
                                   core_report: CoreValidationReport,
                                   enhanced_result: EnhancedGreeksValidationResult) -> List[str]:
        """Determine monitoring requirements based on validation results."""
        monitoring = []

        if len(core_report.critical_issues) > 0:
            monitoring.append("Critical data quality issues require continuous monitoring")

        if enhanced_result.repaired_strikes_count > core_report.total_strikes * 0.3:
            monitoring.append("High repair rate requires validation of repair quality")

        if core_report.overall_liquidity_score < 0.5:
            monitoring.append("Low liquidity requires monitoring of execution quality")

        if len(core_report.high_priority_issues) > 10:
            monitoring.append("High volume of issues requires systematic data quality tracking")

        if not monitoring:
            monitoring.append("Standard monitoring protocols sufficient")

        return monitoring

    def _calculate_agreement_level(self,
                                 core_report: CoreValidationReport,
                                 enhanced_result: EnhancedGreeksValidationResult) -> float:
        """Calculate agreement level between validation systems."""
        # Simple agreement metric based on quality level correlation
        core_excellent = len(core_report.excellent_strikes)
        core_good = len(core_report.good_strikes)
        enhanced_excellent = len(enhanced_result.excellent_strikes)
        enhanced_good = len(enhanced_result.good_strikes)

        total_strikes = max(core_report.total_strikes, 1)

        # Agreement based on similar proportions of high-quality strikes
        core_high_quality_pct = (core_excellent + core_good) / total_strikes
        enhanced_high_quality_pct = (enhanced_excellent + enhanced_good) / total_strikes

        agreement = 1.0 - abs(core_high_quality_pct - enhanced_high_quality_pct)
        return max(0.0, min(1.0, agreement))

    def _basic_quality_fallback(self, options_data: Dict[str, Any]) -> Dict[str, Any]:
        """Basic quality assessment fallback when validation systems fail."""
        total_strikes = len(options_data)
        valid_strikes = 0

        for strike_key, strike_data in options_data.items():
            if isinstance(strike_data, dict):
                for option_type in ['call', 'put']:
                    if option_type in strike_data and isinstance(strike_data[option_type], dict):
                        option = strike_data[option_type]
                        # Basic check for essential fields
                        has_price = any(k in option for k in ['bid', 'ask', 'last', 'market_price'])
                        has_greek = 'delta' in option
                        if has_price and has_greek:
                            valid_strikes += 1

        basic_score = valid_strikes / max(total_strikes, 1)

        return {
            'basic_quality_score': basic_score,
            'valid_strikes': valid_strikes,
            'total_strikes': total_strikes,
            'recommendation': 'PROCEED WITH EXTREME CAUTION' if basic_score >= 0.3 else 'DO NOT PROCEED',
            'note': 'Fallback assessment due to validation system failure'
        }

    def get_analysis_gate_decision(self, validation_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get analysis gate decision based on validation results.
        This method provides the final go/no-go decision for analysis.
        """
        if validation_results.get('validation_summary', {}).get('integration_status') != 'completed':
            return {
                'gate_decision': 'REJECT',
                'reason': 'Validation system failure',
                'allow_analysis': False,
                'recommended_action': 'Check data sources and retry validation'
            }

        consolidated = validation_results.get('consolidated_recommendations', {})
        processing_mode = consolidated.get('processing_mode', 'reject')
        can_proceed = consolidated.get('can_proceed', False)

        if processing_mode == 'reject' or not can_proceed:
            return {
                'gate_decision': 'REJECT',
                'reason': 'Insufficient data quality',
                'allow_analysis': False,
                'recommended_action': 'Seek alternative data sources or expiration dates'
            }
        else:
            return {
                'gate_decision': 'APPROVE',
                'processing_mode': processing_mode,
                'confidence_level': consolidated.get('confidence_level', 'unknown'),
                'allow_analysis': True,
                'restrictions': validation_results.get('processing_decisions', {}).get('monitoring_requirements', []),
                'focus_strikes': validation_results.get('processing_decisions', {}).get('focus_strikes', {})
            }


# Global instance for easy integration
default_validation_orchestrator = ValidationOrchestrator()


def validate_options_for_analysis(options_data: Dict[str, Any],
                                 ticker: str,
                                 expiration_date: str,
                                 spot_price: Optional[float] = None,
                                 asset_type: str = "medium_liquidity") -> Dict[str, Any]:
    """
    Convenience function for running comprehensive validation.

    This is the main entry point for the analysis pipeline to check data quality
    before proceeding with options analysis.

    Args:
        options_data: Options data dictionary
        ticker: Stock ticker
        expiration_date: Expiration date string
        spot_price: Current spot price (optional)
        asset_type: Asset liquidity classification

    Returns:
        Comprehensive validation results with gate decision
    """
    orchestrator = ValidationOrchestrator(asset_type)

    # Run comprehensive validation
    results = orchestrator.run_comprehensive_validation(
        options_data=options_data,
        ticker=ticker,
        expiration_date=expiration_date,
        spot_price=spot_price
    )

    # Add gate decision
    results['gate_decision'] = orchestrator.get_analysis_gate_decision(results)

    return results