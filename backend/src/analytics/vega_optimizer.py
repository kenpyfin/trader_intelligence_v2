"""
Optimized Vega Calculation System

This module provides efficient Vega calculation methods that avoid full repricing
where possible, using analytical approximations and cached computations for
improved performance in options analysis.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import numpy as np
import math
from typing import Dict, List, Optional, Tuple, Union
from scipy.stats import norm
import logging


class VegaOptimizer:
    """
    Optimized Vega calculation engine with multiple approaches.

    This class provides several methods for calculating Vega with varying
    degrees of accuracy and computational cost, allowing for intelligent
    selection based on the analysis context.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Vega approximation parameters
        self.default_vol_bump = 0.01  # 1% volatility bump
        self.cache = {}  # Cache for repeated calculations

    def calculate_vega_optimized(self, S: float, K: float, r: float, T: float,
                               sigma: float, option_type: str = 'call',
                               method: str = 'auto', div: float = 0.0,
                               cached_price: Optional[float] = None) -> Tuple[float, str]:
        """
        Calculate Vega using the most appropriate method based on option characteristics.

        Args:
            S: Current stock price
            K: Strike price
            r: Risk-free rate
            T: Time to expiration (years)
            sigma: Current volatility
            option_type: 'call' or 'put'
            method: 'auto', 'analytical', 'finite_difference', 'binomial'
            div: Dividend yield
            cached_price: Previously calculated option price (for efficiency)

        Returns:
            Tuple of (vega_value, method_used)
        """
        # Auto-select method based on option characteristics
        if method == 'auto':
            method = self._select_optimal_method(S, K, r, T, sigma, option_type)

        vega_value = None
        method_used = method

        try:
            if method == 'analytical':
                vega_value = self._calculate_vega_analytical(S, K, r, T, sigma, div)

            elif method == 'fast_approximation':
                vega_value = self._calculate_vega_fast_approximation(
                    S, K, r, T, sigma, option_type, div
                )

            elif method == 'finite_difference_cached':
                vega_value = self._calculate_vega_finite_difference_cached(
                    S, K, r, T, sigma, option_type, div, cached_price
                )

            elif method == 'binomial':
                # Fall back to binomial if other methods fail
                vega_value = self._calculate_vega_binomial(
                    S, K, r, T, sigma, option_type, div
                )
            else:
                # Default to analytical
                vega_value = self._calculate_vega_analytical(S, K, r, T, sigma, div)
                method_used = 'analytical'

        except Exception as e:
            self.logger.warning(f"Vega calculation failed with method {method}: {str(e)}")
            # Fall back to analytical method
            try:
                vega_value = self._calculate_vega_analytical(S, K, r, T, sigma, div)
                method_used = 'analytical_fallback'
            except Exception as fallback_error:
                self.logger.error(f"All Vega calculation methods failed: {str(fallback_error)}")
                vega_value = None
                method_used = 'failed'

        return vega_value, method_used

    def _select_optimal_method(self, S: float, K: float, r: float, T: float,
                              sigma: float, option_type: str) -> str:
        """Intelligently select the best Vega calculation method."""
        moneyness = S / K if K > 0 else 1.0
        time_decay_factor = math.sqrt(T) if T > 0 else 0

        # For European-style characteristics or far OTM options, use analytical
        if T < 0.05:  # Very short time to expiry
            return 'fast_approximation'
        elif 0.8 <= moneyness <= 1.2 and T > 0.1:  # Near the money with reasonable time
            return 'analytical'
        elif moneyness < 0.5 or moneyness > 2.0:  # Deep OTM/ITM
            return 'fast_approximation'
        else:
            return 'analytical'

    def _calculate_vega_analytical(self, S: float, K: float, r: float, T: float,
                                 sigma: float, div: float = 0.0) -> float:
        """
        Calculate Vega using Black-Scholes analytical formula.

        This is the most accurate method for European options and provides
        a good approximation for American options when early exercise is unlikely.
        """
        if T <= 0 or sigma <= 0:
            return 0.0

        try:
            d1 = (math.log(S / K) + (r - div + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))

            # Vega = S * sqrt(T) * phi(d1) * exp(-div * T)
            # where phi(d1) is the standard normal PDF
            phi_d1 = (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * d1 ** 2)
            vega = S * math.sqrt(T) * phi_d1 * math.exp(-div * T)

            # Convert to per 1% change in volatility
            vega = vega * 0.01

            return vega

        except (ValueError, ZeroDivisionError, OverflowError) as e:
            self.logger.warning(f"Analytical Vega calculation failed: {str(e)}")
            return 0.0

    def _calculate_vega_fast_approximation(self, S: float, K: float, r: float, T: float,
                                         sigma: float, option_type: str, div: float = 0.0) -> float:
        """
        Fast Vega approximation using simplified formulas.

        This method is computationally efficient and suitable for screening
        large numbers of options where high precision is not critical.
        """
        if T <= 0:
            return 0.0

        try:
            moneyness = S / K if K > 0 else 1.0
            time_factor = math.sqrt(T)

            # Simplified approximation based on moneyness
            if 0.9 <= moneyness <= 1.1:  # Near the money
                base_vega = S * time_factor * 0.4
            elif 0.8 <= moneyness <= 1.2:  # Somewhat near the money
                base_vega = S * time_factor * 0.3
            else:  # Far from the money
                distance_penalty = abs(math.log(moneyness))
                base_vega = S * time_factor * 0.2 * math.exp(-distance_penalty)

            # Adjust for volatility level
            vol_adjustment = min(2.0, max(0.5, sigma / 0.3))  # Normalize around 30% vol
            vega = base_vega * vol_adjustment

            # Convert to per 1% change
            vega = vega * 0.01

            return vega

        except Exception as e:
            self.logger.warning(f"Fast Vega approximation failed: {str(e)}")
            return 0.0

    def _calculate_vega_finite_difference_cached(self, S: float, K: float, r: float, T: float,
                                               sigma: float, option_type: str, div: float = 0.0,
                                               cached_price: Optional[float] = None) -> float:
        """
        Calculate Vega using finite difference with intelligent caching.

        This method reuses previously calculated option prices when available
        to minimize computational overhead.
        """
        vol_bump = self.default_vol_bump

        # Generate cache key
        cache_key = f"{S}_{K}_{r}_{T}_{sigma}_{option_type}_{div}"

        try:
            # If we don't have cached price, calculate it
            if cached_price is None:
                from .analysis import universal_binomial_pricer
                cached_price, _, _, _ = universal_binomial_pricer(
                    S=S, K=K, expiration_date=None, r_input=r,
                    sigma_input=sigma, option_type=option_type, div=div
                )

            if cached_price is None:
                return None

            # Calculate price with bumped volatility
            bumped_sigma = sigma + vol_bump
            from .analysis import universal_binomial_pricer
            bumped_price, _, _, _ = universal_binomial_pricer(
                S=S, K=K, expiration_date=None, r_input=r,
                sigma_input=bumped_sigma, option_type=option_type, div=div
            )

            if bumped_price is None:
                return None

            # Vega = (price_up - price_original) / vol_bump
            vega = (bumped_price - cached_price) / vol_bump
            return vega

        except Exception as e:
            self.logger.warning(f"Finite difference Vega calculation failed: {str(e)}")
            return None

    def _calculate_vega_binomial(self, S: float, K: float, r: float, T: float,
                               sigma: float, option_type: str, div: float = 0.0) -> float:
        """
        Calculate Vega using binomial tree (for comparison/fallback).

        This is the most computationally expensive method but most accurate
        for American options.
        """
        vol_bump = self.default_vol_bump

        try:
            from .analysis import universal_binomial_pricer

            # Calculate base price
            base_price, _, _, _ = universal_binomial_pricer(
                S=S, K=K, expiration_date=None, r_input=r,
                sigma_input=sigma, option_type=option_type, div=div
            )

            if base_price is None:
                return None

            # Calculate bumped price
            bumped_sigma = sigma + vol_bump
            bumped_price, _, _, _ = universal_binomial_pricer(
                S=S, K=K, expiration_date=None, r_input=r,
                sigma_input=bumped_sigma, option_type=option_type, div=div
            )

            if bumped_price is None:
                return None

            vega = (bumped_price - base_price) / vol_bump
            return vega

        except Exception as e:
            self.logger.warning(f"Binomial Vega calculation failed: {str(e)}")
            return None

    def calculate_vega_term_structure(self, S: float, strikes: List[float], r: float,
                                    expirations: List[float], sigma: float,
                                    option_type: str = 'call', div: float = 0.0) -> Dict:
        """
        Calculate Vega across multiple strikes and expirations efficiently.

        This method optimizes calculations for volatility surface analysis
        by reusing computations where possible.
        """
        vega_surface = {}

        for T in expirations:
            if T <= 0:
                continue

            vega_surface[T] = {}

            for K in strikes:
                if K <= 0:
                    continue

                vega, method = self.calculate_vega_optimized(
                    S, K, r, T, sigma, option_type, 'auto', div
                )
                vega_surface[T][K] = {
                    'vega': vega,
                    'method': method
                }

        return vega_surface

    def optimize_vega_calculation_batch(self, option_params_list: List[Dict]) -> List[Dict]:
        """
        Optimize Vega calculations for a batch of options.

        This method identifies opportunities to reuse calculations and
        select optimal methods for each option in the batch.
        """
        results = []

        # Group options by similar characteristics for optimization
        grouped_options = self._group_options_for_optimization(option_params_list)

        for group_key, options_group in grouped_options.items():
            # Select optimal method for the group
            representative_option = options_group[0]
            optimal_method = self._select_optimal_method(
                representative_option['S'], representative_option['K'],
                representative_option['r'], representative_option['T'],
                representative_option['sigma'], representative_option['option_type']
            )

            # Calculate Vegas for all options in the group
            for option_params in options_group:
                vega, method_used = self.calculate_vega_optimized(
                    method=optimal_method, **option_params
                )

                results.append({
                    **option_params,
                    'vega': vega,
                    'method_used': method_used,
                    'group_key': group_key
                })

        return results

    def _group_options_for_optimization(self, option_params_list: List[Dict]) -> Dict[str, List[Dict]]:
        """Group options by similar characteristics for batch optimization."""
        groups = {}

        for params in option_params_list:
            # Create grouping key based on option characteristics
            S, K, T = params['S'], params['K'], params['T']
            moneyness_bucket = self._get_moneyness_bucket(S / K if K > 0 else 1)
            time_bucket = self._get_time_bucket(T)
            option_type = params['option_type']

            group_key = f"{moneyness_bucket}_{time_bucket}_{option_type}"

            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(params)

        return groups

    def _get_moneyness_bucket(self, moneyness: float) -> str:
        """Categorize moneyness for grouping."""
        if moneyness < 0.8:
            return 'deep_otm'
        elif moneyness < 0.95:
            return 'otm'
        elif moneyness < 1.05:
            return 'atm'
        elif moneyness < 1.2:
            return 'itm'
        else:
            return 'deep_itm'

    def _get_time_bucket(self, time_to_expiry: float) -> str:
        """Categorize time to expiry for grouping."""
        if time_to_expiry < 0.05:  # < ~18 days
            return 'very_short'
        elif time_to_expiry < 0.25:  # < 3 months
            return 'short'
        elif time_to_expiry < 0.5:   # < 6 months
            return 'medium'
        else:
            return 'long'


# Global instance for easy access
default_vega_optimizer = VegaOptimizer()


def get_optimized_vega(S: float, K: float, r: float, T: float, sigma: float,
                      option_type: str = 'call', div: float = 0.0,
                      cached_price: Optional[float] = None) -> float:
    """
    Convenience function for optimized Vega calculation.

    Args:
        S: Current stock price
        K: Strike price
        r: Risk-free rate
        T: Time to expiration (years)
        sigma: Volatility
        option_type: 'call' or 'put'
        div: Dividend yield
        cached_price: Previously calculated option price

    Returns:
        Optimized Vega value
    """
    vega, _ = default_vega_optimizer.calculate_vega_optimized(
        S, K, r, T, sigma, option_type, 'auto', div, cached_price
    )
    return vega