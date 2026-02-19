"""
Strategy Validation Gates System

This module defines minimum data quality requirements for different trading strategies.
Each strategy has specific thresholds for data completeness and quality before analysis
can proceed, preventing low-quality analyses from being generated.

The system provides:
1. Strategy-specific validation thresholds
2. Gate logic for go/no-go decisions
3. Strategy-aware data quality requirements
4. Risk-adjusted validation criteria

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

# Import core validation components
from .core_validation_engine import CoreValidationEngine, CoreValidationReport, ValidationCategory
from .validation_integration import ValidationOrchestrator


class TradingStrategy(Enum):
    """Supported trading strategies with different data quality requirements."""

    # Conservative strategies (require highest data quality)
    COVERED_CALL = "covered_call"
    PROTECTIVE_PUT = "protective_put"
    CASH_SECURED_PUT = "cash_secured_put"

    # Moderate risk strategies (require good data quality)
    LONG_CALL = "long_call"
    LONG_PUT = "long_put"
    BULL_CALL_SPREAD = "bull_call_spread"
    BEAR_PUT_SPREAD = "bear_put_spread"

    # Higher risk strategies (can tolerate moderate data quality)
    IRON_CONDOR = "iron_condor"
    BUTTERFLY_SPREAD = "butterfly_spread"
    CALENDAR_SPREAD = "calendar_spread"

    # Speculative strategies (most tolerant of data quality issues)
    LONG_STRADDLE = "long_straddle"
    LONG_STRANGLE = "long_strangle"
    SHORT_STRADDLE = "short_straddle"
    SHORT_STRANGLE = "short_strangle"

    # Advanced strategies (require specific data characteristics)
    RATIO_SPREAD = "ratio_spread"
    SYNTHETIC_POSITIONS = "synthetic_positions"
    DELTA_NEUTRAL = "delta_neutral"


class StrategyRiskProfile(Enum):
    """Risk profiles that determine validation strictness."""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    SPECULATIVE = "speculative"


@dataclass
class StrategyValidationCriteria:
    """Validation criteria for a specific trading strategy."""

    strategy: TradingStrategy
    risk_profile: StrategyRiskProfile

    # Minimum quality thresholds (0.0 to 1.0)
    min_overall_quality: float = 0.6
    min_pricing_quality: float = 0.7
    min_greeks_quality: float = 0.6
    min_liquidity_quality: float = 0.4

    # Strike requirements
    min_excellent_strikes: int = 2
    min_good_strikes: int = 5
    max_poor_strikes_pct: float = 0.3  # Max 30% poor quality strikes

    # Issue tolerances
    max_critical_issues: int = 5
    max_high_priority_issues: int = 15

    # Strategy-specific requirements
    required_greeks: List[str] = field(default_factory=lambda: ['delta', 'gamma', 'theta', 'vega'])
    preferred_greeks: List[str] = field(default_factory=lambda: ['rho'])

    # Liquidity requirements
    min_volume_threshold: float = 10
    min_open_interest_threshold: float = 100
    max_bid_ask_spread_pct: float = 25.0

    # Position sizing impact
    quality_position_sizing_factor: float = 1.0  # How much quality affects position size

    # Additional validation flags
    requires_accurate_pricing: bool = True
    requires_complete_greeks: bool = True
    requires_high_liquidity: bool = False
    allows_synthetic_data: bool = True

    # Strategy-specific notes
    validation_notes: List[str] = field(default_factory=list)


@dataclass
class StrategyValidationResult:
    """Result of strategy-specific validation."""

    strategy: TradingStrategy
    validation_timestamp: datetime

    # Gate decision
    gate_decision: str = "REJECT"  # "APPROVE", "APPROVE_WITH_CAUTION", "REJECT"
    decision_confidence: float = 0.0

    # Quality assessment
    meets_minimum_requirements: bool = False
    quality_score_vs_threshold: float = 0.0  # How much above/below threshold

    # Detailed validation results
    criteria_met: Dict[str, bool] = field(default_factory=dict)
    quality_metrics: Dict[str, float] = field(default_factory=dict)

    # Risk and position adjustments
    recommended_position_size_factor: float = 0.0
    risk_adjustment_factor: float = 1.0

    # Recommendations and warnings
    approval_conditions: List[str] = field(default_factory=list)
    risk_warnings: List[str] = field(default_factory=list)
    improvement_recommendations: List[str] = field(default_factory=list)

    # Supporting data
    strikes_analysis: Dict[str, Any] = field(default_factory=dict)
    validation_details: Dict[str, Any] = field(default_factory=dict)


class StrategyValidationGates:
    """
    Strategy-specific validation gates system.

    This class implements validation gates tailored to different trading strategies,
    ensuring that data quality meets strategy-specific requirements before analysis.
    """

    def __init__(self):
        """Initialize the strategy validation gates system."""
        self.logger = logging.getLogger(__name__)

        # Initialize validation orchestrator
        self.validation_orchestrator = ValidationOrchestrator()

        # Define strategy criteria
        self.strategy_criteria = self._initialize_strategy_criteria()

        # Cache for validation results
        self._validation_cache = {}

    def _initialize_strategy_criteria(self) -> Dict[TradingStrategy, StrategyValidationCriteria]:
        """Initialize validation criteria for each trading strategy."""

        criteria = {}

        # Conservative Strategies (Highest Quality Requirements)
        criteria[TradingStrategy.COVERED_CALL] = StrategyValidationCriteria(
            strategy=TradingStrategy.COVERED_CALL,
            risk_profile=StrategyRiskProfile.CONSERVATIVE,
            min_overall_quality=0.8,
            min_pricing_quality=0.85,
            min_greeks_quality=0.8,
            min_liquidity_quality=0.7,
            min_excellent_strikes=3,
            min_good_strikes=8,
            max_poor_strikes_pct=0.15,
            max_critical_issues=2,
            max_high_priority_issues=8,
            required_greeks=['delta', 'theta'],
            preferred_greeks=['gamma', 'vega', 'rho'],
            requires_accurate_pricing=True,
            requires_complete_greeks=True,
            requires_high_liquidity=True,
            quality_position_sizing_factor=1.5,
            validation_notes=[
                "Covered calls require high-quality data due to stock ownership",
                "Accurate pricing essential for proper strike selection",
                "High liquidity needed for exit flexibility"
            ]
        )

        criteria[TradingStrategy.PROTECTIVE_PUT] = StrategyValidationCriteria(
            strategy=TradingStrategy.PROTECTIVE_PUT,
            risk_profile=StrategyRiskProfile.CONSERVATIVE,
            min_overall_quality=0.75,
            min_pricing_quality=0.8,
            min_greeks_quality=0.75,
            min_liquidity_quality=0.6,
            min_excellent_strikes=2,
            min_good_strikes=6,
            max_poor_strikes_pct=0.2,
            max_critical_issues=3,
            max_high_priority_issues=10,
            required_greeks=['delta', 'theta'],
            preferred_greeks=['gamma', 'vega'],
            requires_accurate_pricing=True,
            requires_complete_greeks=True,
            requires_high_liquidity=False,
            quality_position_sizing_factor=1.3,
            validation_notes=[
                "Protective puts are insurance - pricing accuracy critical",
                "Delta sensitivity important for hedge effectiveness"
            ]
        )

        criteria[TradingStrategy.CASH_SECURED_PUT] = StrategyValidationCriteria(
            strategy=TradingStrategy.CASH_SECURED_PUT,
            risk_profile=StrategyRiskProfile.CONSERVATIVE,
            min_overall_quality=0.75,
            min_pricing_quality=0.8,
            min_greeks_quality=0.7,
            min_liquidity_quality=0.5,
            min_excellent_strikes=2,
            min_good_strikes=5,
            max_poor_strikes_pct=0.25,
            max_critical_issues=3,
            max_high_priority_issues=10,
            required_greeks=['delta', 'theta'],
            preferred_greeks=['gamma', 'vega'],
            quality_position_sizing_factor=1.2
        )

        # Moderate Risk Strategies
        criteria[TradingStrategy.LONG_CALL] = StrategyValidationCriteria(
            strategy=TradingStrategy.LONG_CALL,
            risk_profile=StrategyRiskProfile.MODERATE,
            min_overall_quality=0.65,
            min_pricing_quality=0.7,
            min_greeks_quality=0.65,
            min_liquidity_quality=0.4,
            min_excellent_strikes=1,
            min_good_strikes=3,
            max_poor_strikes_pct=0.4,
            max_critical_issues=5,
            max_high_priority_issues=15,
            required_greeks=['delta'],
            preferred_greeks=['gamma', 'theta', 'vega'],
            quality_position_sizing_factor=1.0,
            validation_notes=[
                "Long calls are directional - delta accuracy most important",
                "Time decay (theta) monitoring recommended"
            ]
        )

        criteria[TradingStrategy.LONG_PUT] = StrategyValidationCriteria(
            strategy=TradingStrategy.LONG_PUT,
            risk_profile=StrategyRiskProfile.MODERATE,
            min_overall_quality=0.65,
            min_pricing_quality=0.7,
            min_greeks_quality=0.65,
            min_liquidity_quality=0.4,
            min_excellent_strikes=1,
            min_good_strikes=3,
            max_poor_strikes_pct=0.4,
            max_critical_issues=5,
            max_high_priority_issues=15,
            required_greeks=['delta'],
            preferred_greeks=['gamma', 'theta', 'vega'],
            quality_position_sizing_factor=1.0
        )

        criteria[TradingStrategy.BULL_CALL_SPREAD] = StrategyValidationCriteria(
            strategy=TradingStrategy.BULL_CALL_SPREAD,
            risk_profile=StrategyRiskProfile.MODERATE,
            min_overall_quality=0.7,
            min_pricing_quality=0.75,
            min_greeks_quality=0.7,
            min_liquidity_quality=0.5,
            min_excellent_strikes=2,
            min_good_strikes=4,
            max_poor_strikes_pct=0.3,
            max_critical_issues=4,
            max_high_priority_issues=12,
            required_greeks=['delta', 'theta'],
            preferred_greeks=['gamma', 'vega'],
            requires_accurate_pricing=True,
            quality_position_sizing_factor=1.1,
            validation_notes=[
                "Spreads require accurate pricing for both legs",
                "Relative pricing between strikes is critical"
            ]
        )

        criteria[TradingStrategy.BEAR_PUT_SPREAD] = StrategyValidationCriteria(
            strategy=TradingStrategy.BEAR_PUT_SPREAD,
            risk_profile=StrategyRiskProfile.MODERATE,
            min_overall_quality=0.7,
            min_pricing_quality=0.75,
            min_greeks_quality=0.7,
            min_liquidity_quality=0.5,
            min_excellent_strikes=2,
            min_good_strikes=4,
            max_poor_strikes_pct=0.3,
            max_critical_issues=4,
            max_high_priority_issues=12,
            required_greeks=['delta', 'theta'],
            preferred_greeks=['gamma', 'vega'],
            requires_accurate_pricing=True,
            quality_position_sizing_factor=1.1
        )

        # Higher Risk Strategies
        criteria[TradingStrategy.IRON_CONDOR] = StrategyValidationCriteria(
            strategy=TradingStrategy.IRON_CONDOR,
            risk_profile=StrategyRiskProfile.AGGRESSIVE,
            min_overall_quality=0.6,
            min_pricing_quality=0.7,
            min_greeks_quality=0.6,
            min_liquidity_quality=0.4,
            min_excellent_strikes=2,
            min_good_strikes=6,
            max_poor_strikes_pct=0.4,
            max_critical_issues=6,
            max_high_priority_issues=18,
            required_greeks=['delta', 'theta'],
            preferred_greeks=['gamma', 'vega'],
            requires_accurate_pricing=True,
            requires_high_liquidity=True,
            quality_position_sizing_factor=1.0,
            validation_notes=[
                "Iron condors require 4 legs - pricing accuracy essential",
                "High liquidity needed for position management"
            ]
        )

        criteria[TradingStrategy.BUTTERFLY_SPREAD] = StrategyValidationCriteria(
            strategy=TradingStrategy.BUTTERFLY_SPREAD,
            risk_profile=StrategyRiskProfile.AGGRESSIVE,
            min_overall_quality=0.65,
            min_pricing_quality=0.75,
            min_greeks_quality=0.65,
            min_liquidity_quality=0.45,
            min_excellent_strikes=3,
            min_good_strikes=5,
            max_poor_strikes_pct=0.35,
            max_critical_issues=5,
            max_high_priority_issues=15,
            required_greeks=['delta', 'gamma', 'theta'],
            preferred_greeks=['vega'],
            requires_accurate_pricing=True,
            quality_position_sizing_factor=1.0,
            validation_notes=[
                "Butterflies are gamma plays - gamma accuracy critical",
                "Tight spreads require precise pricing"
            ]
        )

        # Speculative Strategies (Most Tolerant)
        criteria[TradingStrategy.LONG_STRADDLE] = StrategyValidationCriteria(
            strategy=TradingStrategy.LONG_STRADDLE,
            risk_profile=StrategyRiskProfile.SPECULATIVE,
            min_overall_quality=0.5,
            min_pricing_quality=0.6,
            min_greeks_quality=0.5,
            min_liquidity_quality=0.3,
            min_excellent_strikes=1,
            min_good_strikes=2,
            max_poor_strikes_pct=0.5,
            max_critical_issues=8,
            max_high_priority_issues=20,
            required_greeks=['delta'],
            preferred_greeks=['gamma', 'theta', 'vega'],
            quality_position_sizing_factor=0.8,
            validation_notes=[
                "Straddles are volatility plays - some data gaps acceptable",
                "Focus on at-the-money strikes"
            ]
        )

        criteria[TradingStrategy.SHORT_STRADDLE] = StrategyValidationCriteria(
            strategy=TradingStrategy.SHORT_STRADDLE,
            risk_profile=StrategyRiskProfile.SPECULATIVE,
            min_overall_quality=0.65,
            min_pricing_quality=0.7,
            min_greeks_quality=0.6,
            min_liquidity_quality=0.5,
            min_excellent_strikes=2,
            min_good_strikes=3,
            max_poor_strikes_pct=0.4,
            max_critical_issues=6,
            max_high_priority_issues=16,
            required_greeks=['delta', 'theta'],
            preferred_greeks=['gamma', 'vega'],
            requires_high_liquidity=True,
            quality_position_sizing_factor=1.2,
            validation_notes=[
                "Short straddles have unlimited risk - higher quality needed",
                "Liquidity essential for position management"
            ]
        )

        # Advanced Strategies
        criteria[TradingStrategy.DELTA_NEUTRAL] = StrategyValidationCriteria(
            strategy=TradingStrategy.DELTA_NEUTRAL,
            risk_profile=StrategyRiskProfile.AGGRESSIVE,
            min_overall_quality=0.75,
            min_pricing_quality=0.8,
            min_greeks_quality=0.85,
            min_liquidity_quality=0.6,
            min_excellent_strikes=3,
            min_good_strikes=6,
            max_poor_strikes_pct=0.2,
            max_critical_issues=3,
            max_high_priority_issues=10,
            required_greeks=['delta', 'gamma', 'theta'],
            preferred_greeks=['vega', 'rho'],
            requires_complete_greeks=True,
            requires_accurate_pricing=True,
            quality_position_sizing_factor=1.4,
            validation_notes=[
                "Delta neutral strategies require highly accurate Greeks",
                "Position rebalancing depends on precise delta calculations"
            ]
        )

        return criteria

    def validate_strategy(self,
                         strategy: TradingStrategy,
                         options_data: Dict[str, Any],
                         ticker: str,
                         expiration_date: str,
                         spot_price: Optional[float] = None,
                         custom_criteria: Optional[StrategyValidationCriteria] = None) -> StrategyValidationResult:
        """
        Validate options data for a specific trading strategy.

        Args:
            strategy: Trading strategy to validate for
            options_data: Options data dictionary
            ticker: Stock ticker symbol
            expiration_date: Option expiration date
            spot_price: Current spot price
            custom_criteria: Optional custom validation criteria

        Returns:
            StrategyValidationResult with gate decision and detailed analysis
        """
        self.logger.info(f"Validating data for {strategy.value} strategy on {ticker}")

        # Get validation criteria for this strategy
        criteria = custom_criteria or self.strategy_criteria.get(strategy)
        if not criteria:
            raise ValueError(f"No validation criteria defined for strategy: {strategy.value}")

        # Create result object
        result = StrategyValidationResult(
            strategy=strategy,
            validation_timestamp=datetime.now()
        )

        try:
            # Run comprehensive validation
            validation_results = self.validation_orchestrator.run_comprehensive_validation(
                options_data=options_data,
                ticker=ticker,
                expiration_date=expiration_date,
                spot_price=spot_price
            )

            # Extract key metrics
            core_validation = validation_results.get('validation_summary', {}).get('core_validation', {})
            category_scores = core_validation.get('category_scores', {})
            strikes_by_quality = core_validation.get('strikes_by_quality', {})

            overall_quality = validation_results.get('data_quality_metrics', {}).get('consolidated_quality_score', 0.0)
            critical_issues = core_validation.get('critical_issues', 0)
            high_priority_issues = core_validation.get('high_priority_issues', 0)

            # Populate quality metrics
            result.quality_metrics = {
                'overall_quality': overall_quality,
                'pricing_quality': category_scores.get('pricing', 0.0),
                'greeks_quality': category_scores.get('greeks', 0.0),
                'liquidity_quality': category_scores.get('liquidity', 0.0),
                'critical_issues_count': critical_issues,
                'high_priority_issues_count': high_priority_issues
            }

            # Populate strikes analysis
            total_strikes = sum(strikes_by_quality.values()) or 1
            result.strikes_analysis = {
                'total_strikes': total_strikes,
                'excellent_strikes': strikes_by_quality.get('excellent', 0),
                'good_strikes': strikes_by_quality.get('good', 0),
                'acceptable_strikes': strikes_by_quality.get('acceptable', 0),
                'poor_strikes': strikes_by_quality.get('poor', 0),
                'failed_strikes': strikes_by_quality.get('failed', 0),
                'poor_strikes_pct': strikes_by_quality.get('poor', 0) / total_strikes * 100
            }

            # Evaluate against strategy criteria
            self._evaluate_criteria(result, criteria, validation_results)

            # Make gate decision
            self._make_gate_decision(result, criteria)

            # Generate recommendations
            self._generate_strategy_recommendations(result, criteria, validation_results)

            result.validation_details = validation_results

        except Exception as e:
            self.logger.error(f"Strategy validation failed: {e}")
            result.gate_decision = "REJECT"
            result.risk_warnings.append(f"Validation system error: {e}")
            result.improvement_recommendations.append("Fix data source issues and retry validation")

        self.logger.info(f"Strategy validation complete: {result.gate_decision} ({result.decision_confidence:.1%} confidence)")

        return result

    def _evaluate_criteria(self,
                          result: StrategyValidationResult,
                          criteria: StrategyValidationCriteria,
                          validation_results: Dict[str, Any]):
        """Evaluate validation results against strategy criteria."""

        quality_metrics = result.quality_metrics
        strikes_analysis = result.strikes_analysis

        # Quality threshold checks
        result.criteria_met['overall_quality'] = quality_metrics['overall_quality'] >= criteria.min_overall_quality
        result.criteria_met['pricing_quality'] = quality_metrics['pricing_quality'] >= criteria.min_pricing_quality
        result.criteria_met['greeks_quality'] = quality_metrics['greeks_quality'] >= criteria.min_greeks_quality
        result.criteria_met['liquidity_quality'] = quality_metrics['liquidity_quality'] >= criteria.min_liquidity_quality

        # Strike quality checks
        result.criteria_met['excellent_strikes'] = strikes_analysis['excellent_strikes'] >= criteria.min_excellent_strikes
        result.criteria_met['good_strikes'] = strikes_analysis['good_strikes'] >= criteria.min_good_strikes
        result.criteria_met['poor_strikes_limit'] = strikes_analysis['poor_strikes_pct'] <= criteria.max_poor_strikes_pct * 100

        # Issue tolerance checks
        result.criteria_met['critical_issues'] = quality_metrics['critical_issues_count'] <= criteria.max_critical_issues
        result.criteria_met['high_priority_issues'] = quality_metrics['high_priority_issues_count'] <= criteria.max_high_priority_issues

        # Calculate how much above/below threshold we are
        result.quality_score_vs_threshold = quality_metrics['overall_quality'] - criteria.min_overall_quality

        # Check if minimum requirements are met
        essential_criteria = ['overall_quality', 'critical_issues', 'excellent_strikes']
        result.meets_minimum_requirements = all(result.criteria_met.get(criterion, False) for criterion in essential_criteria)

    def _make_gate_decision(self,
                           result: StrategyValidationResult,
                           criteria: StrategyValidationCriteria):
        """Make the final gate decision for strategy validation."""

        # Count criteria met
        total_criteria = len(result.criteria_met)
        criteria_met_count = sum(result.criteria_met.values())
        criteria_met_pct = criteria_met_count / max(total_criteria, 1)

        # Base decision on criteria met percentage and critical factors
        if result.meets_minimum_requirements and criteria_met_pct >= 0.8:
            result.gate_decision = "APPROVE"
            result.decision_confidence = min(0.95, 0.6 + criteria_met_pct * 0.4)

        elif result.meets_minimum_requirements and criteria_met_pct >= 0.6:
            result.gate_decision = "APPROVE_WITH_CAUTION"
            result.decision_confidence = min(0.75, 0.3 + criteria_met_pct * 0.5)

        else:
            result.gate_decision = "REJECT"
            result.decision_confidence = min(0.9, 0.9 - criteria_met_pct * 0.3)

        # Adjust confidence based on risk profile
        risk_adjustments = {
            StrategyRiskProfile.CONSERVATIVE: -0.1,
            StrategyRiskProfile.MODERATE: 0.0,
            StrategyRiskProfile.AGGRESSIVE: 0.05,
            StrategyRiskProfile.SPECULATIVE: 0.1
        }

        result.decision_confidence += risk_adjustments.get(criteria.risk_profile, 0.0)
        result.decision_confidence = max(0.0, min(1.0, result.decision_confidence))

        # Calculate position sizing factor
        if result.gate_decision != "REJECT":
            base_factor = 1.0 if result.gate_decision == "APPROVE" else 0.6
            quality_adjustment = result.quality_score_vs_threshold * criteria.quality_position_sizing_factor
            result.recommended_position_size_factor = max(0.1, base_factor + quality_adjustment)
        else:
            result.recommended_position_size_factor = 0.0

        # Calculate risk adjustment factor
        if result.quality_score_vs_threshold < 0:
            # Below threshold - increase risk estimates
            result.risk_adjustment_factor = 1.0 + abs(result.quality_score_vs_threshold) * 2
        else:
            # Above threshold - standard risk
            result.risk_adjustment_factor = 1.0

    def _generate_strategy_recommendations(self,
                                         result: StrategyValidationResult,
                                         criteria: StrategyValidationCriteria,
                                         validation_results: Dict[str, Any]):
        """Generate strategy-specific recommendations and warnings."""

        if result.gate_decision == "APPROVE":
            result.approval_conditions = [
                "Data quality meets all strategy requirements",
                f"Proceed with {result.recommended_position_size_factor:.1%} of normal position size"
            ]

            # Add strategy-specific conditions
            if criteria.requires_high_liquidity and result.quality_metrics['liquidity_quality'] < 0.7:
                result.approval_conditions.append("Monitor liquidity closely during position entry/exit")

            if result.quality_score_vs_threshold < 0.1:
                result.approval_conditions.append("Data quality is near threshold - monitor for degradation")

        elif result.gate_decision == "APPROVE_WITH_CAUTION":
            result.approval_conditions = [
                f"Proceed with caution and {result.recommended_position_size_factor:.1%} position sizing",
                "Enhanced monitoring recommended due to data quality limitations"
            ]

            # Identify specific risk areas
            failed_criteria = [k for k, v in result.criteria_met.items() if not v]
            for criterion in failed_criteria:
                if criterion == 'liquidity_quality':
                    result.risk_warnings.append("Low liquidity may impact execution quality")
                elif criterion == 'pricing_quality':
                    result.risk_warnings.append("Pricing data gaps may affect position valuation")
                elif criterion == 'greeks_quality':
                    result.risk_warnings.append("Greeks accuracy concerns - use wider margin of safety")

        else:  # REJECT
            result.improvement_recommendations.extend([
                "Improve overall data quality before attempting this strategy",
                "Consider alternative expiration dates with better data quality",
                "Try simpler strategies with lower data quality requirements"
            ])

            # Specific improvement areas
            if not result.criteria_met.get('critical_issues', True):
                result.improvement_recommendations.append("Address critical data quality issues first")

            if not result.criteria_met.get('excellent_strikes', True):
                result.improvement_recommendations.append("Find options with more complete and accurate data")

        # Add strategy-specific notes
        result.risk_warnings.extend(criteria.validation_notes)

    def get_strategy_requirements(self, strategy: TradingStrategy) -> Dict[str, Any]:
        """Get the validation requirements for a specific strategy."""
        criteria = self.strategy_criteria.get(strategy)
        if not criteria:
            return {"error": f"No criteria defined for strategy: {strategy.value}"}

        return {
            "strategy": strategy.value,
            "risk_profile": criteria.risk_profile.value,
            "minimum_requirements": {
                "overall_quality": criteria.min_overall_quality,
                "pricing_quality": criteria.min_pricing_quality,
                "greeks_quality": criteria.min_greeks_quality,
                "liquidity_quality": criteria.min_liquidity_quality,
                "excellent_strikes": criteria.min_excellent_strikes,
                "good_strikes": criteria.min_good_strikes,
                "max_critical_issues": criteria.max_critical_issues
            },
            "required_greeks": criteria.required_greeks,
            "preferred_greeks": criteria.preferred_greeks,
            "special_requirements": {
                "requires_accurate_pricing": criteria.requires_accurate_pricing,
                "requires_complete_greeks": criteria.requires_complete_greeks,
                "requires_high_liquidity": criteria.requires_high_liquidity
            },
            "validation_notes": criteria.validation_notes
        }

    def compare_strategies(self, strategies: List[TradingStrategy]) -> Dict[str, Any]:
        """Compare validation requirements across multiple strategies."""
        comparison = {
            "strategies": [],
            "requirements_comparison": {
                "most_lenient": None,
                "most_strict": None,
                "quality_requirements": {},
                "strike_requirements": {}
            }
        }

        min_quality_req = float('inf')
        max_quality_req = 0.0
        most_lenient = None
        most_strict = None

        for strategy in strategies:
            criteria = self.strategy_criteria.get(strategy)
            if not criteria:
                continue

            strategy_info = {
                "strategy": strategy.value,
                "risk_profile": criteria.risk_profile.value,
                "min_overall_quality": criteria.min_overall_quality,
                "min_excellent_strikes": criteria.min_excellent_strikes,
                "max_critical_issues": criteria.max_critical_issues
            }

            comparison["strategies"].append(strategy_info)

            # Track most/least strict
            if criteria.min_overall_quality < min_quality_req:
                min_quality_req = criteria.min_overall_quality
                most_lenient = strategy.value

            if criteria.min_overall_quality > max_quality_req:
                max_quality_req = criteria.min_overall_quality
                most_strict = strategy.value

        comparison["requirements_comparison"]["most_lenient"] = most_lenient
        comparison["requirements_comparison"]["most_strict"] = most_strict
        comparison["requirements_comparison"]["quality_range"] = {
            "min": min_quality_req,
            "max": max_quality_req,
            "spread": max_quality_req - min_quality_req
        }

        return comparison


# Global instance for easy access
default_strategy_gates = StrategyValidationGates()


def validate_for_strategy(strategy: TradingStrategy,
                         options_data: Dict[str, Any],
                         ticker: str,
                         expiration_date: str,
                         spot_price: Optional[float] = None) -> StrategyValidationResult:
    """
    Convenience function to validate options data for a specific trading strategy.

    Args:
        strategy: Trading strategy to validate for
        options_data: Options data dictionary
        ticker: Stock ticker symbol
        expiration_date: Option expiration date
        spot_price: Current spot price

    Returns:
        StrategyValidationResult with gate decision
    """
    return default_strategy_gates.validate_strategy(
        strategy=strategy,
        options_data=options_data,
        ticker=ticker,
        expiration_date=expiration_date,
        spot_price=spot_price
    )