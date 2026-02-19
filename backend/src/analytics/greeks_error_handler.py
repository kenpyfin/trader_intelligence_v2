"""
Enhanced Greeks Calculation Error Handler

This module provides comprehensive error handling and validation for Greeks calculations,
specifically designed to catch, categorize, and recover from calculation failures while
providing detailed diagnostic information for debugging.

Key Features:
- Mathematical edge case validation
- Granular error categorization and logging
- Context-aware error recovery strategies
- Detailed diagnostic information for debugging
- Integration with existing Greeks repair system

Author: Bug Fixer - Greeks Calculation Error Handling Enhancement
"""

import logging
import math
import numpy as np
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple, Union
from contextlib import contextmanager
import traceback
from datetime import datetime


class GreeksCalculationError(Exception):
    """Base exception for Greeks calculation errors"""
    pass


class GreeksErrorCategory(Enum):
    """Categories of Greeks calculation errors"""
    MATHEMATICAL_EDGE_CASE = "mathematical_edge_case"
    INVALID_INPUT_DATA = "invalid_input_data"
    BINOMIAL_TREE_CONSTRUCTION = "binomial_tree_construction"
    DELTA_CALCULATION = "delta_calculation"
    GAMMA_CALCULATION = "gamma_calculation"
    THETA_CALCULATION = "theta_calculation"
    VEGA_CALCULATION = "vega_calculation"
    RHO_CALCULATION = "rho_calculation"
    NUMERICAL_INSTABILITY = "numerical_instability"
    EXTREME_MARKET_CONDITIONS = "extreme_market_conditions"
    DATA_VALIDATION = "data_validation"
    INTERPOLATION_FAILURE = "interpolation_failure"
    FALLBACK_EXHAUSTED = "fallback_exhausted"


@dataclass
class GreeksErrorContext:
    """Context information for Greeks calculation errors"""
    ticker: str
    strike: float
    option_type: str
    expiration_date: str
    spot_price: float
    risk_free_rate: float
    volatility: float
    days_to_expiration: int
    calculation_method: str
    error_timestamp: datetime
    stack_trace: str
    input_parameters: Dict[str, Any]
    intermediate_values: Dict[str, Any]


@dataclass
class GreeksCalculationResult:
    """Result container for Greeks calculations with error handling"""
    success: bool
    greeks: Optional[Dict[str, float]]
    error_category: Optional[GreeksErrorCategory]
    error_message: Optional[str]
    warning_messages: List[str]
    recovery_applied: bool
    recovery_method: Optional[str]
    confidence_score: float
    context: Optional[GreeksErrorContext]
    fallback_used: bool


class GreeksErrorHandler:
    """
    Comprehensive error handler for Greeks calculations with enhanced logging
    and recovery strategies.
    """

    def __init__(self, ticker: str = "UNKNOWN"):
        self.ticker = ticker
        self.logger = logging.getLogger(f"{__name__}.{ticker}")
        self.error_count = 0
        self.warning_count = 0
        self.recovery_count = 0

        # Mathematical validation thresholds
        self.validation_thresholds = {
            'delta': {'min': -1.1, 'max': 1.1, 'reasonable_min': -1.0, 'reasonable_max': 1.0},
            'gamma': {'min': -10.0, 'max': 10.0, 'reasonable_min': 0.0, 'reasonable_max': 5.0},
            'theta': {'min': -100.0, 'max': 100.0, 'reasonable_min': -10.0, 'reasonable_max': 1.0},
            'vega': {'min': -50.0, 'max': 50.0, 'reasonable_min': 0.0, 'reasonable_max': 5.0},
            'rho': {'min': -500.0, 'max': 500.0, 'reasonable_min': -50.0, 'reasonable_max': 50.0}
        }

        # Edge case detection thresholds
        self.edge_case_thresholds = {
            'min_days_to_expiration': 0.5,  # Less than 0.5 days
            'max_volatility': 3.0,  # 300% volatility
            'min_volatility': 0.001,  # 0.1% volatility
            'extreme_moneyness_low': 0.5,  # S/K < 0.5
            'extreme_moneyness_high': 2.0,  # S/K > 2.0
            'min_time_value': 1e-10,  # Extremely low time value
            'numerical_precision': 1e-15  # Numerical precision threshold
        }

    @contextmanager
    def error_context(self, **context_params):
        """Context manager for capturing detailed error information"""
        context_data = {
            'ticker': self.ticker,
            'error_timestamp': datetime.now(),
            'input_parameters': context_params,
            'intermediate_values': {}
        }

        try:
            yield context_data
        except Exception as e:
            context_data['stack_trace'] = traceback.format_exc()
            context_data['error_type'] = type(e).__name__
            context_data['error_message'] = str(e)

            # Log the detailed error with context
            self._log_detailed_error(e, context_data)
            raise

    def validate_input_parameters(self, spot_price: float, strike: float, risk_free_rate: float,
                                volatility: float, days_to_expiration: int, option_type: str) -> Tuple[bool, List[str]]:
        """
        Comprehensive input parameter validation with detailed error messages

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Validate spot price
        if not isinstance(spot_price, (int, float)) or spot_price <= 0:
            errors.append(f"Invalid spot price: {spot_price} (must be positive number)")
        elif math.isnan(spot_price) or math.isinf(spot_price):
            errors.append(f"Invalid spot price: {spot_price} (contains NaN or infinity)")

        # Validate strike price
        if not isinstance(strike, (int, float)) or strike <= 0:
            errors.append(f"Invalid strike price: {strike} (must be positive number)")
        elif math.isnan(strike) or math.isinf(strike):
            errors.append(f"Invalid strike price: {strike} (contains NaN or infinity)")

        # Validate risk-free rate
        if not isinstance(risk_free_rate, (int, float)):
            errors.append(f"Invalid risk-free rate: {risk_free_rate} (must be number)")
        elif math.isnan(risk_free_rate) or math.isinf(risk_free_rate):
            errors.append(f"Invalid risk-free rate: {risk_free_rate} (contains NaN or infinity)")
        elif abs(risk_free_rate) > 1.0:
            errors.append(f"Unusual risk-free rate: {risk_free_rate} (|rate| > 100%)")

        # Validate volatility
        if not isinstance(volatility, (int, float)) or volatility < 0:
            errors.append(f"Invalid volatility: {volatility} (must be non-negative number)")
        elif math.isnan(volatility) or math.isinf(volatility):
            errors.append(f"Invalid volatility: {volatility} (contains NaN or infinity)")
        elif volatility > self.edge_case_thresholds['max_volatility']:
            errors.append(f"Extreme volatility detected: {volatility} (>{self.edge_case_thresholds['max_volatility']*100}%)")
        elif volatility < self.edge_case_thresholds['min_volatility']:
            errors.append(f"Extremely low volatility detected: {volatility} (<{self.edge_case_thresholds['min_volatility']*100}%)")

        # Validate days to expiration
        if not isinstance(days_to_expiration, (int, float)) or days_to_expiration < 0:
            errors.append(f"Invalid days to expiration: {days_to_expiration} (must be non-negative number)")
        elif days_to_expiration < self.edge_case_thresholds['min_days_to_expiration']:
            errors.append(f"Near-expiration detected: {days_to_expiration} days (high gamma risk)")

        # Validate option type
        if option_type not in ['call', 'put']:
            errors.append(f"Invalid option type: {option_type} (must be 'call' or 'put')")

        # Check for extreme moneyness
        if not errors and isinstance(spot_price, (int, float)) and isinstance(strike, (int, float)):
            moneyness = spot_price / strike
            if moneyness < self.edge_case_thresholds['extreme_moneyness_low']:
                errors.append(f"Extreme OTM condition: S/K = {moneyness:.3f} (deep OTM)")
            elif moneyness > self.edge_case_thresholds['extreme_moneyness_high']:
                errors.append(f"Extreme ITM condition: S/K = {moneyness:.3f} (deep ITM)")

        return len(errors) == 0, errors

    def validate_greeks_output(self, greeks: Dict[str, float], option_type: str) -> Tuple[bool, List[str], List[str]]:
        """
        Comprehensive validation of calculated Greeks values

        Returns:
            Tuple of (is_valid, error_messages, warning_messages)
        """
        errors = []
        warnings = []

        for greek_name, value in greeks.items():
            if greek_name not in self.validation_thresholds:
                continue

            thresholds = self.validation_thresholds[greek_name]

            # Check for NaN/infinity
            if math.isnan(value) or math.isinf(value):
                errors.append(f"Invalid {greek_name}: {value} (NaN or infinity)")
                continue

            # Check absolute bounds
            if value < thresholds['min'] or value > thresholds['max']:
                errors.append(f"Out-of-bounds {greek_name}: {value} (bounds: {thresholds['min']} to {thresholds['max']})")
                continue

            # Check reasonable bounds with warnings
            if value < thresholds['reasonable_min'] or value > thresholds['reasonable_max']:
                warnings.append(f"Unusual {greek_name}: {value} (typical range: {thresholds['reasonable_min']} to {thresholds['reasonable_max']})")

            # Specific validations for each Greek
            if greek_name == 'delta':
                if option_type == 'call' and (value < -0.1 or value > 1.1):
                    errors.append(f"Invalid call delta: {value} (should be approximately 0 to 1)")
                elif option_type == 'put' and (value < -1.1 or value > 0.1):
                    errors.append(f"Invalid put delta: {value} (should be approximately -1 to 0)")

            elif greek_name == 'gamma':
                if value < -0.1:  # Gamma should generally be positive
                    warnings.append(f"Negative gamma: {value} (unusual, typically positive)")

            elif greek_name == 'vega':
                if value < -0.1:  # Vega should generally be positive
                    warnings.append(f"Negative vega: {value} (unusual, typically positive)")

        return len(errors) == 0, errors, warnings

    def detect_numerical_instability(self, intermediate_values: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Detect potential numerical instability issues in calculations

        Returns:
            Tuple of (has_instability, instability_messages)
        """
        instabilities = []

        # Check for near-zero denominators
        for key, value in intermediate_values.items():
            if 'denominator' in key.lower() and isinstance(value, (int, float)):
                if abs(value) < self.edge_case_thresholds['numerical_precision']:
                    instabilities.append(f"Near-zero denominator detected in {key}: {value}")

        # Check for extreme ratios
        for key, value in intermediate_values.items():
            if isinstance(value, (int, float)) and abs(value) > 1e10:
                instabilities.append(f"Extreme value detected in {key}: {value}")

        return len(instabilities) > 0, instabilities

    def safe_divide(self, numerator: float, denominator: float, fallback_value: float = 0.0,
                   context_name: str = "division") -> float:
        """
        Safe division with comprehensive error handling and logging

        Args:
            numerator: The numerator value
            denominator: The denominator value
            fallback_value: Value to return if division fails
            context_name: Context description for logging

        Returns:
            Result of division or fallback value
        """
        try:
            # Check for zero denominator
            if abs(denominator) < self.edge_case_thresholds['numerical_precision']:
                self.logger.warning(
                    f"Zero denominator in {context_name}: "
                    f"num={numerator}, den={denominator}, using fallback={fallback_value}"
                )
                return fallback_value

            result = numerator / denominator

            # Check result validity
            if math.isnan(result) or math.isinf(result):
                self.logger.warning(
                    f"Invalid division result in {context_name}: "
                    f"num={numerator}, den={denominator}, result={result}, using fallback={fallback_value}"
                )
                return fallback_value

            return result

        except Exception as e:
            self.logger.error(
                f"Division error in {context_name}: "
                f"num={numerator}, den={denominator}, error={str(e)}, using fallback={fallback_value}"
            )
            return fallback_value

    def calculate_greeks_with_error_handling(self, calculation_func, **kwargs) -> GreeksCalculationResult:
        """
        Execute Greeks calculation with comprehensive error handling

        Args:
            calculation_func: The Greeks calculation function to execute
            **kwargs: Arguments to pass to the calculation function

        Returns:
            GreeksCalculationResult with detailed error handling
        """
        warnings = []
        recovery_applied = False
        recovery_method = None

        # Create error context
        context = GreeksErrorContext(
            ticker=self.ticker,
            strike=kwargs.get('strike', 0.0),
            option_type=kwargs.get('option_type', 'call'),
            expiration_date=str(kwargs.get('expiration_date', 'unknown')),
            spot_price=kwargs.get('spot_price', 0.0),
            risk_free_rate=kwargs.get('risk_free_rate', 0.0),
            volatility=kwargs.get('volatility', 0.0),
            days_to_expiration=kwargs.get('days_to_expiration', 0),
            calculation_method=kwargs.get('calculation_method', 'binomial'),
            error_timestamp=datetime.now(),
            stack_trace='',
            input_parameters=kwargs.copy(),
            intermediate_values={}
        )

        try:
            with self.error_context(**kwargs) as error_context:
                # Step 1: Input validation
                is_valid, validation_errors = self.validate_input_parameters(
                    spot_price=kwargs.get('spot_price', 0.0),
                    strike=kwargs.get('strike', 0.0),
                    risk_free_rate=kwargs.get('risk_free_rate', 0.0),
                    volatility=kwargs.get('volatility', 0.0),
                    days_to_expiration=kwargs.get('days_to_expiration', 0),
                    option_type=kwargs.get('option_type', 'call')
                )

                if not is_valid:
                    error_context['intermediate_values']['validation_errors'] = validation_errors
                    raise GreeksCalculationError(f"Input validation failed: {'; '.join(validation_errors)}")

                # Step 2: Execute calculation
                option_value, greeks, *other_results = calculation_func(**kwargs)
                error_context['intermediate_values']['option_value'] = option_value
                error_context['intermediate_values']['raw_greeks'] = greeks.copy()

                # Step 3: Validate output
                output_valid, output_errors, output_warnings = self.validate_greeks_output(
                    greeks, kwargs.get('option_type', 'call')
                )
                warnings.extend(output_warnings)

                if not output_valid:
                    error_context['intermediate_values']['output_validation_errors'] = output_errors
                    raise GreeksCalculationError(f"Output validation failed: {'; '.join(output_errors)}")

                # Step 4: Check numerical stability
                has_instability, instability_messages = self.detect_numerical_instability(
                    error_context['intermediate_values']
                )
                if has_instability:
                    warnings.extend(instability_messages)

                # Step 5: Calculate confidence score
                confidence_score = self._calculate_confidence_score(greeks, warnings)

                return GreeksCalculationResult(
                    success=True,
                    greeks=greeks,
                    error_category=None,
                    error_message=None,
                    warning_messages=warnings,
                    recovery_applied=recovery_applied,
                    recovery_method=recovery_method,
                    confidence_score=confidence_score,
                    context=context,
                    fallback_used=False
                )

        except Exception as e:
            self.error_count += 1
            error_category = self._categorize_error(e, context)

            self.logger.error(
                f"Greeks calculation failed for {self.ticker} "
                f"strike={kwargs.get('strike', 'unknown')} "
                f"option_type={kwargs.get('option_type', 'unknown')}: "
                f"{str(e)} [Category: {error_category.value}]"
            )

            return GreeksCalculationResult(
                success=False,
                greeks=None,
                error_category=error_category,
                error_message=str(e),
                warning_messages=warnings,
                recovery_applied=recovery_applied,
                recovery_method=recovery_method,
                confidence_score=0.0,
                context=context,
                fallback_used=False
            )

    def _calculate_confidence_score(self, greeks: Dict[str, float], warnings: List[str]) -> float:
        """Calculate confidence score based on Greeks values and warnings"""
        base_confidence = 1.0

        # Reduce confidence for warnings
        warning_penalty = min(0.1 * len(warnings), 0.5)
        base_confidence -= warning_penalty

        # Check Greeks reasonableness
        unreasonable_count = 0
        for greek_name, value in greeks.items():
            if greek_name in self.validation_thresholds:
                thresholds = self.validation_thresholds[greek_name]
                if value < thresholds['reasonable_min'] or value > thresholds['reasonable_max']:
                    unreasonable_count += 1

        # Reduce confidence for unreasonable Greeks
        reasonableness_penalty = 0.2 * unreasonable_count / len(greeks)
        base_confidence -= reasonableness_penalty

        return max(0.0, min(1.0, base_confidence))

    def _categorize_error(self, error: Exception, context: GreeksErrorContext) -> GreeksErrorCategory:
        """Categorize the error based on type and context"""
        error_message = str(error).lower()

        if 'validation failed' in error_message:
            if 'input' in error_message:
                return GreeksErrorCategory.INVALID_INPUT_DATA
            else:
                return GreeksErrorCategory.DATA_VALIDATION

        if 'denominator' in error_message or 'division' in error_message:
            return GreeksErrorCategory.MATHEMATICAL_EDGE_CASE

        if 'delta' in error_message:
            return GreeksErrorCategory.DELTA_CALCULATION
        elif 'gamma' in error_message:
            return GreeksErrorCategory.GAMMA_CALCULATION
        elif 'theta' in error_message:
            return GreeksErrorCategory.THETA_CALCULATION
        elif 'vega' in error_message:
            return GreeksErrorCategory.VEGA_CALCULATION
        elif 'rho' in error_message:
            return GreeksErrorCategory.RHO_CALCULATION

        if context.days_to_expiration < 1 or context.volatility > 2.0:
            return GreeksErrorCategory.EXTREME_MARKET_CONDITIONS

        if isinstance(error, (ValueError, ArithmeticError)):
            return GreeksErrorCategory.NUMERICAL_INSTABILITY

        return GreeksErrorCategory.MATHEMATICAL_EDGE_CASE

    def _log_detailed_error(self, error: Exception, context_data: Dict[str, Any]):
        """Log detailed error information for debugging"""
        self.logger.error(
            f"Detailed Greeks Calculation Error:\n"
            f"  Ticker: {context_data.get('ticker', 'unknown')}\n"
            f"  Error Type: {context_data.get('error_type', 'unknown')}\n"
            f"  Error Message: {context_data.get('error_message', str(error))}\n"
            f"  Input Parameters: {context_data.get('input_parameters', {})}\n"
            f"  Intermediate Values: {context_data.get('intermediate_values', {})}\n"
            f"  Timestamp: {context_data.get('error_timestamp', 'unknown')}\n"
            f"  Stack Trace:\n{context_data.get('stack_trace', 'Not available')}"
        )

    def get_error_summary(self) -> Dict[str, int]:
        """Get summary of errors encountered"""
        return {
            'total_errors': self.error_count,
            'total_warnings': self.warning_count,
            'recoveries_applied': self.recovery_count
        }


# Global error handler instance
def get_greeks_error_handler(ticker: str) -> GreeksErrorHandler:
    """Get or create a Greeks error handler for the specified ticker"""
    return GreeksErrorHandler(ticker=ticker)