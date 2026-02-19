"""
Integration tests for enhanced options data validation in the analysis pipeline.

Tests the complete flow from analysis output through validation to trader agent input.
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from analytics.options_validation import validate_options_analysis_output, validate_greeks_structure

class TestOptionsValidationIntegration(unittest.TestCase):
    """Integration tests for options validation pipeline."""

    def setUp(self):
        """Set up test data."""
        # Realistic analysis result with good options data
        self.good_analysis_result = {
            "market_data": {
                "current_price": 150.0,
                "volume": 1000000
            },
            "volatility_structure": {
                "iv_rank_proxy": "normal",
                "hv_comparison": {"iv_above_hv": True, "iv_hv_spread": 0.02}
            },
            "options_positioning": {
                "total_undervalued_options": 5,
                "top_opportunity": {
                    "Strike": 150.0,
                    "Type": "Call",
                    "Market Price": 8.50,
                    "Model Price": 9.25,
                    "Undervalued By ($)": 0.75,
                    "Undervalued By (%)": 8.82
                },
                "strike_distribution": {
                    "analyzed_strikes": [145.0, 150.0, 155.0, 160.0],
                    "atm_strike": 150.0,
                    "valid_strikes": [145.0, 150.0, 155.0]
                },
                "greeks_by_strike": {
                    "145.0": {
                        "call": {
                            "market_price": 12.50,
                            "model_price": 12.75,
                            "delta": 0.75,
                            "gamma": 0.06,
                            "theta": -0.08,
                            "vega": 0.22,
                            "rho": 0.04
                        },
                        "put": {
                            "market_price": 7.25,
                            "model_price": 7.50,
                            "delta": -0.25,
                            "gamma": 0.06,
                            "theta": -0.07,
                            "vega": 0.22,
                            "rho": -0.02
                        }
                    },
                    "150.0": {
                        "call": {
                            "market_price": 8.50,
                            "model_price": 9.25,
                            "delta": 0.55,
                            "gamma": 0.08,
                            "theta": -0.10,
                            "vega": 0.28,
                            "rho": 0.035
                        },
                        "put": {
                            "market_price": 8.25,
                            "model_price": 9.00,
                            "delta": -0.45,
                            "gamma": 0.08,
                            "theta": -0.09,
                            "vega": 0.28,
                            "rho": -0.03
                        }
                    }
                }
            }
        }

        # Analysis result with problematic options data
        self.problematic_analysis_result = {
            "market_data": {
                "current_price": 100.0
            },
            "options_positioning": {
                "total_undervalued_options": 0,
                "top_opportunity": None,
                "strike_distribution": {
                    "analyzed_strikes": [95.0, 100.0, 105.0],
                    "valid_strikes": [95.0, 100.0, 105.0]
                },
                "greeks_by_strike": {
                    "100.0": {
                        "call": {
                            "market_price": 5.50,
                            "model_price": 5.75,
                            "delta": 1.2,        # Invalid: > 1
                            "gamma": float('nan'), # Invalid: NaN
                            "theta": -0.05,
                            # Missing vega and rho
                        }
                    },
                    "invalid_strike": {  # Non-numeric key
                        "call": {"delta": 0.4}
                    }
                }
            }
        }

    def test_validate_good_analysis_output(self):
        """Test validation of good analysis output."""
        validation = validate_options_analysis_output(self.good_analysis_result)

        # Should pass validation
        self.assertTrue(validation["validation_passed"])
        self.assertGreater(validation["quality_score"], 0.7)

        # Should have reasonable metrics
        metrics = validation["data_metrics"]
        self.assertEqual(metrics["valid_strikes_count"], 3)
        self.assertEqual(metrics["greeks_strikes_count"], 2)
        self.assertEqual(metrics["complete_greeks_count"], 2)
        self.assertEqual(metrics["invalid_values_count"], 0)

        # Should have few or no issues
        self.assertLessEqual(len(validation["issues_found"]), 1)

    def test_validate_problematic_analysis_output(self):
        """Test validation of problematic analysis output."""
        validation = validate_options_analysis_output(self.problematic_analysis_result)

        # Should fail validation
        self.assertFalse(validation["validation_passed"])
        self.assertLess(validation["quality_score"], 0.5)

        # Should identify issues
        self.assertGreater(len(validation["issues_found"]), 0)
        self.assertGreater(len(validation["recommendations"]), 0)

        # Should detect specific problems
        issues_text = " ".join(validation["issues_found"])
        self.assertIn("No undervalued options", issues_text)
        self.assertIn("No top opportunity", issues_text)

        # Should detect data quality issues
        metrics = validation["data_metrics"]
        self.assertGreater(metrics["invalid_values_count"], 0)
        self.assertGreater(metrics["missing_fields_count"], 0)

    def test_validate_empty_analysis_output(self):
        """Test validation of empty/missing analysis output."""
        empty_result = {"market_data": {"current_price": 100.0}}

        validation = validate_options_analysis_output(empty_result)

        # Should fail validation
        self.assertFalse(validation["validation_passed"])
        self.assertEqual(validation["quality_score"], 0.0)

        # Should identify missing data
        self.assertIn("No options_positioning data", validation["issues_found"])
        self.assertIn("Verify options analysis is enabled", validation["recommendations"])

    def test_greeks_structure_validation_detailed(self):
        """Test detailed greeks structure validation."""
        complex_greeks = {
            "100.0": {
                "call": {
                    "market_price": 5.50,
                    "model_price": 5.75,
                    "delta": 0.55,
                    "gamma": 0.08,
                    "theta": -0.05,
                    "vega": 0.20,
                    "rho": 0.03
                },
                "put": {
                    "market_price": 4.75,
                    "model_price": 5.00,
                    "delta": -0.45,
                    "gamma": 0.08,
                    "theta": -0.04,
                    "vega": 0.20,
                    "rho": -0.025
                }
            },
            "105.0": {
                "call": {
                    "market_price": 3.25,
                    "model_price": 3.50,
                    "delta": 0.35,
                    "gamma": 0.06,
                    "theta": -0.03,
                    "vega": 0.15,
                    "rho": 0.02
                }
                # Missing put - should still be valid
            },
            "110.0": {
                "call": {
                    "delta": 2.0,  # Invalid range
                    "gamma": -0.1, # Invalid negative
                    "theta": float('inf'), # Invalid infinity
                    "vega": None,  # Invalid None
                    "rho": "invalid" # Invalid type
                }
                # Missing market/model prices and put
            }
        }

        report = validate_greeks_structure(complex_greeks)

        # Should identify valid strikes
        self.assertEqual(report.valid_strikes_count, 3)

        # Should identify complete vs incomplete strikes
        self.assertEqual(report.complete_greeks_count, 2)  # 100.0 and 105.0

        # Should detect invalid values
        self.assertGreater(report.invalid_values_count, 0)
        self.assertGreater(report.missing_fields_count, 0)

        # Should provide reasonable quality score
        self.assertGreater(report.quality_score, 0.3)  # Some good data exists
        self.assertLess(report.quality_score, 0.8)     # But has issues

        # Should provide actionable recommendations
        self.assertGreater(len(report.recommendations), 0)
        self.assertGreater(len(report.issues), 0)

    def test_empty_greeks_validation(self):
        """Test validation of empty greeks data."""
        report = validate_greeks_structure({})

        self.assertEqual(report.valid_strikes_count, 0)
        self.assertEqual(report.complete_greeks_count, 0)
        self.assertEqual(report.quality_score, 0.0)
        self.assertIn("No greeks data provided", report.issues)

    def test_malformed_greeks_validation(self):
        """Test validation of completely malformed greeks data."""
        malformed_greeks = {
            "not_a_number": "not_a_dict",
            123: [],  # Wrong types
            "another_bad_key": {
                "call": "not_a_dict",
                "put": None
            }
        }

        report = validate_greeks_structure(malformed_greeks)

        # Should handle malformed data gracefully
        self.assertGreaterEqual(report.valid_strikes_count, 0)
        self.assertEqual(report.complete_greeks_count, 0)
        self.assertEqual(report.quality_score, 0.0)
        self.assertGreater(len(report.issues), 0)

class TestValidationHelpers(unittest.TestCase):
    """Test validation helper functions."""

    def test_quality_score_calculation(self):
        """Test that quality scores are calculated correctly."""
        # Perfect data should score near 1.0
        perfect_greeks = {
            "100.0": {
                "call": {
                    "market_price": 5.50, "model_price": 5.75,
                    "delta": 0.55, "gamma": 0.08, "theta": -0.05,
                    "vega": 0.20, "rho": 0.03
                },
                "put": {
                    "market_price": 4.75, "model_price": 5.00,
                    "delta": -0.45, "gamma": 0.08, "theta": -0.04,
                    "vega": 0.20, "rho": -0.025
                }
            }
        }

        report = validate_greeks_structure(perfect_greeks)
        self.assertGreater(report.quality_score, 0.9)

        # Completely broken data should score near 0.0
        broken_greeks = {
            "100.0": {
                "call": {
                    "delta": float('nan'),
                    "gamma": float('inf'),
                    "theta": None,
                    "vega": "invalid",
                    "rho": []
                }
            }
        }

        report = validate_greeks_structure(broken_greeks)
        self.assertLess(report.quality_score, 0.2)

if __name__ == '__main__':
    unittest.main(verbosity=2)