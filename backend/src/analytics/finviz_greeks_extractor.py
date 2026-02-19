"""
Finviz Greeks Extraction and Validation System

This module handles the extraction, validation, and quality assessment of Greeks data
from Finviz API responses. It provides utilities to parse Finviz option data and
convert it into standardized Greeks dictionaries for comparison with calculated values.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime, date


class FinvizGreeksExtractor:
    """
    Extracts and validates Greeks data from Finviz API responses.

    This class handles the conversion of Finviz option chain data into standardized
    Greeks dictionaries, performs data quality validation, and provides utilities
    for comparing Finviz Greeks with calculated values.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def extract_greeks_from_finviz(self, finviz_df: pd.DataFrame) -> Dict[str, Dict[str, Dict]]:
        """
        Extract Greeks data from Finviz option chain DataFrame.

        Args:
            finviz_df: DataFrame containing Finviz option chain data with columns:
                      ['Strike', 'Type', 'Delta', 'Gamma', 'Theta', 'Vega', 'Rho', 'Bid', 'Ask', 'Volume', 'Open Int.']

        Returns:
            Dict structured as: {strike: {'call': greeks_dict, 'put': greeks_dict}}
            where greeks_dict contains: {'delta', 'gamma', 'theta', 'vega', 'rho', 'market_data'}
        """
        if finviz_df.empty:
            self.logger.warning("Empty Finviz DataFrame provided")
            return {}

        greeks_by_strike = {}

        for _, row in finviz_df.iterrows():
            try:
                strike = self._parse_numeric(row.get('Strike'))
                option_type = self._normalize_option_type(row.get('Type'))

                if strike is None or option_type is None:
                    continue

                # Extract Greeks
                delta = self._parse_numeric(row.get('Delta'))
                gamma = self._parse_numeric(row.get('Gamma'))
                theta = self._parse_numeric(row.get('Theta'))
                vega = self._parse_numeric(row.get('Vega'))
                rho = self._parse_numeric(row.get('Rho'))

                # Extract market data
                bid = self._parse_numeric(row.get('Bid'))
                ask = self._parse_numeric(row.get('Ask'))
                volume = self._parse_numeric(row.get('Volume'))
                open_interest = self._parse_numeric(row.get('Open Int.'))
                last_close = self._parse_numeric(row.get('Last Close'))
                iv = self._parse_numeric(row.get('IV'))

                # Calculate mid price
                mid_price = None
                if bid is not None and ask is not None and bid > 0 and ask > 0:
                    mid_price = (bid + ask) / 2
                elif last_close is not None and last_close > 0:
                    mid_price = last_close

                # Initialize strike entry if needed
                if strike not in greeks_by_strike:
                    greeks_by_strike[strike] = {}

                # Store Greeks and market data
                greeks_by_strike[strike][option_type] = {
                    'delta': delta,
                    'gamma': gamma,
                    'theta': theta,
                    'vega': vega,
                    'rho': rho,
                    'market_data': {
                        'bid': bid,
                        'ask': ask,
                        'mid_price': mid_price,
                        'volume': volume,
                        'open_interest': open_interest,
                        'implied_volatility': iv,
                        'last_close': last_close
                    }
                }

            except Exception as e:
                self.logger.warning(f"Failed to process Finviz row for strike {row.get('Strike', 'unknown')}: {str(e)}")
                continue

        self.logger.info(f"Extracted Greeks for {len(greeks_by_strike)} strikes from Finviz data")
        return greeks_by_strike

    def validate_finviz_greeks(self, greeks_data: Dict[str, Dict[str, Dict]]) -> Dict[str, Dict]:
        """
        Validate Finviz Greeks data quality and compute validation metrics.

        Args:
            greeks_data: Greeks dictionary from extract_greeks_from_finviz()

        Returns:
            Dict containing validation results: {
                'overall_quality': float,
                'strike_quality': {strike: quality_metrics},
                'summary': validation_summary
            }
        """
        validation_results = {
            'overall_quality': 0.0,
            'strike_quality': {},
            'summary': {
                'total_strikes': len(greeks_data),
                'valid_strikes': 0,
                'complete_greeks': 0,
                'partial_greeks': 0,
                'invalid_strikes': 0
            }
        }

        if not greeks_data:
            return validation_results

        valid_strikes = 0
        total_quality_score = 0.0

        for strike, options in greeks_data.items():
            strike_metrics = self._validate_strike_greeks(strike, options)
            validation_results['strike_quality'][strike] = strike_metrics

            if strike_metrics['is_valid']:
                valid_strikes += 1
                total_quality_score += strike_metrics['quality_score']

                if strike_metrics['completeness_ratio'] >= 0.8:
                    validation_results['summary']['complete_greeks'] += 1
                elif strike_metrics['completeness_ratio'] >= 0.5:
                    validation_results['summary']['partial_greeks'] += 1
            else:
                validation_results['summary']['invalid_strikes'] += 1

        validation_results['summary']['valid_strikes'] = valid_strikes

        if valid_strikes > 0:
            validation_results['overall_quality'] = total_quality_score / valid_strikes

        self.logger.info(f"Finviz Greeks validation: {valid_strikes}/{len(greeks_data)} strikes valid, "
                        f"overall quality: {validation_results['overall_quality']:.3f}")

        return validation_results

    def _validate_strike_greeks(self, strike: float, options: Dict[str, Dict]) -> Dict:
        """Validate Greeks for a single strike."""
        metrics = {
            'is_valid': False,
            'quality_score': 0.0,
            'completeness_ratio': 0.0,
            'issues': []
        }

        expected_greeks = ['delta', 'gamma', 'theta', 'vega', 'rho']
        total_possible = len(expected_greeks) * len(options)  # Greeks × options (call/put)
        valid_greeks = 0

        for option_type, data in options.items():
            if not isinstance(data, dict):
                metrics['issues'].append(f"Invalid data structure for {option_type}")
                continue

            for greek in expected_greeks:
                value = data.get(greek)
                if self._is_valid_greek_value(greek, value, option_type):
                    valid_greeks += 1
                else:
                    metrics['issues'].append(f"Invalid {greek} for {option_type}: {value}")

        if total_possible > 0:
            metrics['completeness_ratio'] = valid_greeks / total_possible
            metrics['quality_score'] = metrics['completeness_ratio']

            # Strike is valid if it has at least 50% valid Greeks
            metrics['is_valid'] = metrics['completeness_ratio'] >= 0.5

        return metrics

    def _is_valid_greek_value(self, greek_name: str, value: Union[float, None], option_type: str) -> bool:
        """Validate individual Greek value based on theoretical constraints."""
        if value is None or not isinstance(value, (int, float)):
            return False

        if np.isnan(value) or np.isinf(value):
            return False

        # Greek-specific validation
        if greek_name == 'delta':
            if option_type == 'call':
                return 0 <= value <= 1
            elif option_type == 'put':
                return -1 <= value <= 0

        elif greek_name == 'gamma':
            return value >= 0  # Gamma is always positive

        elif greek_name == 'theta':
            return -10 <= value <= 1  # Theta typically negative, reasonable bounds

        elif greek_name == 'vega':
            return 0 <= value <= 5  # Vega positive for long options, reasonable upper bound

        elif greek_name == 'rho':
            return -50 <= value <= 50  # Reasonable bounds for rho

        return True

    def _parse_numeric(self, value) -> Optional[float]:
        """Parse numeric value from various formats."""
        if pd.isna(value) or value is None:
            return None

        if isinstance(value, (int, float)):
            if np.isnan(value) or np.isinf(value):
                return None
            return float(value)

        if isinstance(value, str):
            # Handle percentage strings
            if '%' in value:
                try:
                    return float(value.replace('%', '')) / 100
                except ValueError:
                    return None

            # Handle comma-separated numbers
            value = value.replace(',', '')

            try:
                return float(value)
            except ValueError:
                return None

        return None

    def _normalize_option_type(self, option_type: Union[str, None]) -> Optional[str]:
        """Normalize option type to standard format."""
        if not option_type:
            return None

        option_type = str(option_type).lower().strip()

        if option_type in ['call', 'c']:
            return 'call'
        elif option_type in ['put', 'p']:
            return 'put'

        return None

    def create_greeks_comparison_report(self, finviz_greeks: Dict, calculated_greeks: Dict) -> Dict:
        """
        Create a comprehensive comparison report between Finviz and calculated Greeks.

        Args:
            finviz_greeks: Greeks data from extract_greeks_from_finviz()
            calculated_greeks: Greeks data from binomial model

        Returns:
            Dict containing comparison metrics and analysis
        """
        report = {
            'summary': {
                'total_strikes_finviz': len(finviz_greeks),
                'total_strikes_calculated': len(calculated_greeks),
                'common_strikes': 0,
                'average_differences': {},
                'correlation_metrics': {}
            },
            'strike_comparisons': {},
            'quality_assessment': {
                'finviz_preferred_strikes': [],
                'calculated_preferred_strikes': [],
                'hybrid_recommended_strikes': []
            }
        }

        common_strikes = set(finviz_greeks.keys()) & set(calculated_greeks.keys())
        report['summary']['common_strikes'] = len(common_strikes)

        if not common_strikes:
            self.logger.warning("No common strikes found between Finviz and calculated Greeks")
            return report

        # Compare Greeks for common strikes
        differences = {greek: [] for greek in ['delta', 'gamma', 'theta', 'vega', 'rho']}

        for strike in common_strikes:
            strike_comparison = self._compare_strike_greeks(
                strike, finviz_greeks[strike], calculated_greeks.get(strike, {})
            )
            report['strike_comparisons'][strike] = strike_comparison

            # Collect differences for summary statistics
            for greek in differences.keys():
                for option_type in ['call', 'put']:
                    diff = strike_comparison.get(f'{option_type}_differences', {}).get(greek)
                    if diff is not None:
                        differences[greek].append(abs(diff))

        # Calculate summary statistics
        for greek, diff_list in differences.items():
            if diff_list:
                report['summary']['average_differences'][greek] = {
                    'mean_abs_diff': np.mean(diff_list),
                    'median_abs_diff': np.median(diff_list),
                    'max_abs_diff': np.max(diff_list),
                    'std_diff': np.std(diff_list)
                }

        # Generate recommendations
        self._generate_greeks_recommendations(report)

        return report

    def _compare_strike_greeks(self, strike: float, finviz_data: Dict, calculated_data: Dict) -> Dict:
        """Compare Greeks for a single strike between data sources."""
        comparison = {
            'strike': strike,
            'call_differences': {},
            'put_differences': {},
            'finviz_quality': 0.0,
            'calculated_quality': 0.0,
            'recommended_source': 'hybrid'
        }

        for option_type in ['call', 'put']:
            finviz_greeks = finviz_data.get(option_type, {})
            calculated_greeks = calculated_data.get(option_type, {})

            differences = {}
            for greek in ['delta', 'gamma', 'theta', 'vega', 'rho']:
                fv_val = finviz_greeks.get(greek)
                calc_val = calculated_greeks.get(greek)

                if fv_val is not None and calc_val is not None:
                    differences[greek] = fv_val - calc_val

            comparison[f'{option_type}_differences'] = differences

        return comparison

    def _generate_greeks_recommendations(self, report: Dict):
        """Generate recommendations for which Greeks source to use."""
        # Implementation for generating recommendations based on comparison analysis
        # This would analyze the differences and quality metrics to recommend
        # whether to use Finviz, calculated, or hybrid approach for each strike
        pass


# Utility functions
def get_finviz_greeks_for_analysis(ticker: str, expiration_date: str,
                                  finviz_api_client) -> Tuple[Dict, Dict]:
    """
    Convenience function to fetch and extract Finviz Greeks for analysis.

    Args:
        ticker: Stock ticker symbol
        expiration_date: Option expiration date (YYYY-MM-DD)
        finviz_api_client: Instance of the Finviz API client

    Returns:
        Tuple of (greeks_data, validation_results)
    """
    extractor = FinvizGreeksExtractor()

    # Fetch both calls and puts
    calls_df = finviz_api_client.get_option_data_finviz(ticker, 'oc', expiration_date)
    puts_df = finviz_api_client.get_option_data_finviz(ticker, 'op', expiration_date)

    # Combine data
    combined_df = pd.concat([calls_df, puts_df], ignore_index=True)

    if combined_df.empty:
        return {}, {'overall_quality': 0.0}

    # Extract and validate Greeks
    greeks_data = extractor.extract_greeks_from_finviz(combined_df)
    validation_results = extractor.validate_finviz_greeks(greeks_data)

    return greeks_data, validation_results