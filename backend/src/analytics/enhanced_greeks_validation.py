"""
Enhanced Greeks Validation System

This module provides sophisticated validation for options Greeks data with intelligent
repair mechanisms, interpolation, and fallback strategies specifically optimized
for partial data scenarios common with high-volume assets like SPY.
"""

import math
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from .greeks_repair import default_greeks_validator, GreeksRepairResult


@dataclass
class EnhancedGreeksValidationResult:
    """Enhanced validation result with detailed repair information."""
    valid_strikes_count: int
    complete_strikes_count: int
    partially_complete_strikes_count: int
    repaired_strikes_count: int
    interpolated_strikes_count: int
    fallback_strikes_count: int

    original_quality_score: float
    enhanced_quality_score: float
    confidence_score: float

    repair_summary: List[str]
    missing_fields_summary: Dict[str, int]

    # Validation categorization
    excellent_strikes: List[float]  # All Greeks present and valid
    good_strikes: List[float]       # Most Greeks present, some interpolated
    acceptable_strikes: List[float] # Partial data with fallbacks
    poor_strikes: List[float]       # Mostly fallback data

    # Detailed repair logs
    strike_repair_details: Dict[float, GreeksRepairResult]


class EnhancedGreeksValidator:
    """Enhanced Greeks validator with intelligent repair capabilities."""

    def __init__(self):
        """Initialize the enhanced validator."""
        self.repair_validator = default_greeks_validator
        self.required_greeks = ['delta', 'gamma', 'theta', 'vega', 'rho']
        self.required_prices = ['market_price', 'model_price']
        self.essential_greeks = ['delta']  # Must have for any meaningful analysis
        self.important_greeks = ['delta', 'gamma', 'vega']  # Core Greeks for analysis

    def validate_and_enhance_greeks_data(self,
                                       greeks_by_strike: Dict[str, Any],
                                       spot_price: float,
                                       risk_free_rate: float = 0.05,
                                       time_to_expiry: float = 0.25,
                                       implied_vol: Optional[float] = None) -> EnhancedGreeksValidationResult:
        """
        Comprehensive validation and enhancement of Greeks data.

        Args:
            greeks_by_strike: Original Greeks data by strike
            spot_price: Current stock price
            risk_free_rate: Risk-free rate
            time_to_expiry: Time to expiration in years
            implied_vol: Implied volatility estimate

        Returns:
            EnhancedGreeksValidationResult with detailed analysis and repairs
        """
        # Initialize tracking variables
        repair_details = {}
        repair_summary = []
        missing_fields_summary = {}

        excellent_strikes = []
        good_strikes = []
        acceptable_strikes = []
        poor_strikes = []

        repaired_count = 0
        interpolated_count = 0
        fallback_count = 0

        # Convert string strikes to float for processing
        processed_strikes = {}
        for strike_key, strike_data in greeks_by_strike.items():
            try:
                float_strike = float(strike_key)
                processed_strikes[float_strike] = strike_data
            except (ValueError, TypeError):
                continue

        # Calculate original quality score
        original_quality = self._calculate_original_quality_score(processed_strikes)

        # Process each strike with intelligent repair
        enhanced_greeks = {}

        for strike, strike_data in processed_strikes.items():
            # Validate and repair this strike
            repair_result = self.repair_validator.validate_and_repair_strike(
                strike=strike,
                strike_data=strike_data,
                neighboring_strikes=processed_strikes,
                spot_price=spot_price,
                risk_free_rate=risk_free_rate,
                time_to_expiry=time_to_expiry,
                implied_vol=implied_vol
            )

            # Store enhanced data
            enhanced_greeks[str(strike)] = repair_result.repaired_data
            repair_details[strike] = repair_result

            # Track repair statistics
            if repair_result.repairs_made:
                repaired_count += 1
            if repair_result.interpolated_fields:
                interpolated_count += 1
            if repair_result.fallback_fields:
                fallback_count += 1

            # Categorize strike quality
            strike_category = self._categorize_strike_quality(repair_result)
            if strike_category == 'excellent':
                excellent_strikes.append(strike)
            elif strike_category == 'good':
                good_strikes.append(strike)
            elif strike_category == 'acceptable':
                acceptable_strikes.append(strike)
            else:
                poor_strikes.append(strike)

            # Update repair summary
            repair_summary.extend(repair_result.repairs_made)

            # Update missing fields summary
            self._update_missing_fields_summary(missing_fields_summary, repair_result)

        # Calculate enhanced metrics
        total_strikes = len(processed_strikes)
        complete_strikes = len(excellent_strikes)
        partially_complete = len(good_strikes) + len(acceptable_strikes)
        enhanced_quality = self._calculate_enhanced_quality_score(repair_details)
        confidence_score = self._calculate_overall_confidence_score(repair_details)

        return EnhancedGreeksValidationResult(
            valid_strikes_count=total_strikes,
            complete_strikes_count=complete_strikes,
            partially_complete_strikes_count=partially_complete,
            repaired_strikes_count=repaired_count,
            interpolated_strikes_count=interpolated_count,
            fallback_strikes_count=fallback_count,

            original_quality_score=original_quality,
            enhanced_quality_score=enhanced_quality,
            confidence_score=confidence_score,

            repair_summary=repair_summary[:20],  # Limit for readability
            missing_fields_summary=missing_fields_summary,

            excellent_strikes=excellent_strikes,
            good_strikes=good_strikes,
            acceptable_strikes=acceptable_strikes,
            poor_strikes=poor_strikes,

            strike_repair_details=repair_details
        )

    def _calculate_original_quality_score(self, greeks_by_strike: Dict[float, Any]) -> float:
        """Calculate quality score before any repairs."""
        if not greeks_by_strike:
            return 0.0

        total_possible_fields = len(self.required_greeks) * 2 * len(greeks_by_strike)  # call and put
        valid_fields = 0

        for strike, strike_data in greeks_by_strike.items():
            if isinstance(strike_data, dict):
                for option_type in ['call', 'put']:
                    if option_type in strike_data and isinstance(strike_data[option_type], dict):
                        option_data = strike_data[option_type]
                        for greek in self.required_greeks:
                            if (greek in option_data and
                                option_data[greek] is not None and
                                not (isinstance(option_data[greek], float) and
                                     (math.isnan(option_data[greek]) or math.isinf(option_data[greek])))):
                                valid_fields += 1

        return valid_fields / max(1, total_possible_fields)

    def _categorize_strike_quality(self, repair_result: GreeksRepairResult) -> str:
        """Categorize the quality of a strike after repair."""
        # Count original vs repaired fields
        total_repairs = len(repair_result.repairs_made)
        interpolated = len(repair_result.interpolated_fields)
        fallback = len(repair_result.fallback_fields)

        quality_score = repair_result.quality_score
        confidence = repair_result.confidence_score

        # Excellent: High quality and confidence, minimal repairs
        if quality_score >= 0.9 and confidence >= 0.8 and fallback <= 2:
            return 'excellent'

        # Good: Good quality, some interpolation acceptable
        elif quality_score >= 0.7 and confidence >= 0.6 and fallback <= 4:
            return 'good'

        # Acceptable: Reasonable quality with more fallbacks
        elif quality_score >= 0.5 and confidence >= 0.4:
            return 'acceptable'

        # Poor: Low quality, mostly fallback data
        else:
            return 'poor'

    def _update_missing_fields_summary(self,
                                     summary: Dict[str, int],
                                     repair_result: GreeksRepairResult):
        """Update the summary of missing fields across all strikes."""
        for field in repair_result.interpolated_fields + repair_result.fallback_fields:
            if field not in summary:
                summary[field] = 0
            summary[field] += 1

    def _calculate_enhanced_quality_score(self,
                                        repair_details: Dict[float, GreeksRepairResult]) -> float:
        """Calculate overall quality score after enhancements."""
        if not repair_details:
            return 0.0

        total_score = sum(result.quality_score for result in repair_details.values())
        return total_score / len(repair_details)

    def _calculate_overall_confidence_score(self,
                                          repair_details: Dict[float, GreeksRepairResult]) -> float:
        """Calculate overall confidence score for the enhanced data."""
        if not repair_details:
            return 0.0

        total_confidence = sum(result.confidence_score for result in repair_details.values())
        return total_confidence / len(repair_details)

    def create_validation_summary(self, result: EnhancedGreeksValidationResult) -> Dict[str, Any]:
        """Create a human-readable summary of the validation results."""
        total_strikes = result.valid_strikes_count

        return {
            "validation_summary": {
                "total_strikes_analyzed": total_strikes,
                "quality_improvement": {
                    "original_score": round(result.original_quality_score, 3),
                    "enhanced_score": round(result.enhanced_quality_score, 3),
                    "improvement": round(result.enhanced_quality_score - result.original_quality_score, 3),
                    "confidence_score": round(result.confidence_score, 3)
                },
                "strike_categories": {
                    "excellent": len(result.excellent_strikes),
                    "good": len(result.good_strikes),
                    "acceptable": len(result.acceptable_strikes),
                    "poor": len(result.poor_strikes)
                },
                "repair_statistics": {
                    "strikes_repaired": result.repaired_strikes_count,
                    "strikes_with_interpolation": result.interpolated_strikes_count,
                    "strikes_with_fallbacks": result.fallback_strikes_count
                },
                "most_common_missing_fields": dict(
                    sorted(result.missing_fields_summary.items(),
                           key=lambda x: x[1], reverse=True)[:10]
                )
            },
            "recommendation": self._generate_recommendation(result),
            "processing_decision": self._make_processing_decision(result)
        }

    def _generate_recommendation(self, result: EnhancedGreeksValidationResult) -> str:
        """Generate processing recommendation based on validation results."""
        total = result.valid_strikes_count
        excellent_pct = len(result.excellent_strikes) / max(1, total) * 100
        good_pct = len(result.good_strikes) / max(1, total) * 100
        acceptable_pct = len(result.acceptable_strikes) / max(1, total) * 100

        enhanced_score = result.enhanced_quality_score
        confidence = result.confidence_score

        if enhanced_score >= 0.8 and confidence >= 0.7:
            return f"PROCEED: High quality data ({enhanced_score:.1%} complete, {confidence:.1%} confidence). {excellent_pct:.0f}% excellent strikes."

        elif enhanced_score >= 0.6 and confidence >= 0.5:
            return f"PROCEED WITH CAUTION: Good quality after enhancements ({enhanced_score:.1%} complete). {good_pct + excellent_pct:.0f}% good/excellent strikes."

        elif enhanced_score >= 0.4 and confidence >= 0.3:
            return f"CONDITIONAL PROCEED: Acceptable quality with significant enhancements. Consider reducing position size."

        else:
            return f"REVIEW REQUIRED: Low quality data even after enhancements ({enhanced_score:.1%} complete, {confidence:.1%} confidence)."

    def _make_processing_decision(self, result: EnhancedGreeksValidationResult) -> Dict[str, Any]:
        """Make processing decision based on enhanced validation."""
        enhanced_score = result.enhanced_quality_score
        confidence = result.confidence_score
        excellent_count = len(result.excellent_strikes)
        total_count = result.valid_strikes_count

        # Decision criteria
        can_proceed = False
        processing_mode = "reject"
        confidence_level = "low"

        if enhanced_score >= 0.7 and confidence >= 0.6:
            can_proceed = True
            processing_mode = "full_analysis"
            confidence_level = "high"
        elif enhanced_score >= 0.5 and confidence >= 0.4 and excellent_count >= 3:
            can_proceed = True
            processing_mode = "reduced_analysis"
            confidence_level = "medium"
        elif enhanced_score >= 0.3 and excellent_count >= 1:
            can_proceed = True
            processing_mode = "basic_analysis"
            confidence_level = "low"

        return {
            "can_proceed": can_proceed,
            "processing_mode": processing_mode,
            "confidence_level": confidence_level,
            "recommended_position_sizing": self._get_position_sizing_recommendation(confidence_level),
            "analysis_limitations": self._get_analysis_limitations(result)
        }

    def _get_position_sizing_recommendation(self, confidence_level: str) -> str:
        """Get position sizing recommendation based on data confidence."""
        if confidence_level == "high":
            return "Normal position sizing acceptable"
        elif confidence_level == "medium":
            return "Reduce position size by 25-50%"
        else:
            return "Limit to small exploratory positions"

    def _get_analysis_limitations(self, result: EnhancedGreeksValidationResult) -> List[str]:
        """Identify analysis limitations based on validation results."""
        limitations = []

        if result.fallback_strikes_count > result.valid_strikes_count * 0.3:
            limitations.append("Significant use of fallback Greek values")

        if result.interpolated_strikes_count > result.valid_strikes_count * 0.5:
            limitations.append("Heavy reliance on interpolated data")

        if len(result.poor_strikes) > result.valid_strikes_count * 0.2:
            limitations.append("High proportion of poor-quality strikes")

        if 'rho' in result.missing_fields_summary and result.missing_fields_summary['rho'] > result.valid_strikes_count * 0.8:
            limitations.append("Interest rate sensitivity (rho) mostly estimated")

        if result.confidence_score < 0.5:
            limitations.append("Low confidence in enhanced data quality")

        return limitations


# Global instance
default_enhanced_validator = EnhancedGreeksValidator()