import unittest
import sys
import os
import json
import math

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from analytics.methodologies.gpt_verdict import (
    _validate_options_data,
    _sanitize_and_repair_options_data,
    OptionsDataValidation
)

class TestEnhancedOptionsValidation(unittest.TestCase):
    """Comprehensive tests for enhanced options data validation."""

    def setUp(self):
        """Set up test data."""
        # Complete, well-formed options data
        self.complete_data = {
            "valid_strikes": [95.0, 100.0, 105.0],
            "greeks_by_strike": {
                "95.0": {
                    "call": {
                        "market_price": 8.50,
                        "model_price": 8.75,
                        "delta": 0.65,
                        "gamma": 0.08,
                        "theta": -0.05,
                        "vega": 0.15,
                        "rho": 0.03
                    },
                    "put": {
                        "market_price": 3.20,
                        "model_price": 3.45,
                        "delta": -0.35,
                        "gamma": 0.08,
                        "theta": -0.04,
                        "vega": 0.15,
                        "rho": -0.02
                    }
                },
                "100.0": {
                    "call": {
                        "market_price": 5.25,
                        "model_price": 5.50,
                        "delta": 0.50,
                        "gamma": 0.10,
                        "theta": -0.06,
                        "vega": 0.18,
                        "rho": 0.025
                    },
                    "put": {
                        "market_price": 4.75,
                        "model_price": 5.00,
                        "delta": -0.50,
                        "gamma": 0.10,
                        "theta": -0.05,
                        "vega": 0.18,
                        "rho": -0.025
                    }
                }
            },
            "top_opportunity": {
                "Strike": 100.0,
                "Type": "Call",
                "Market Price": 5.25,
                "Model Price": 5.50,
                "Undervalued By ($)": 0.25,
                "Undervalued By (%)": 4.76
            },
            "volatility_structure": {
                "iv_rank_proxy": "normal",
                "hv_comparison": {"iv_above_hv": True, "iv_hv_spread": 0.02}
            },
            "undervalued_opportunities": 3
        }

    def test_complete_valid_data(self):
        """Test validation with complete, well-formed data."""
        validation = _validate_options_data(self.complete_data)

        self.assertEqual(validation.valid_strikes_count, 3)
        self.assertEqual(validation.greeks_count, 2)  # 2 strikes with greeks
        self.assertEqual(validation.complete_greeks_count, 2)
        self.assertEqual(validation.invalid_greeks_count, 0)
        self.assertTrue(validation.top_opportunity_present)
        self.assertTrue(validation.volatility_structure_present)
        self.assertEqual(validation.undervalued_opportunities_count, 3)

        # Should have high scores
        self.assertGreater(validation.data_completeness_score, 0.8)
        self.assertGreater(validation.data_quality_score, 0.8)

        # Should have no errors
        self.assertEqual(len(validation.errors), 0)

    def test_empty_data(self):
        """Test validation with empty data."""
        empty_data = {}
        validation = _validate_options_data(empty_data)

        self.assertEqual(validation.valid_strikes_count, 0)
        self.assertEqual(validation.greeks_count, 0)
        self.assertEqual(validation.complete_greeks_count, 0)
        self.assertEqual(validation.data_completeness_score, 0.0)
        self.assertEqual(validation.data_quality_score, 0.0)

        # Should have errors
        self.assertGreater(len(validation.errors), 0)
        self.assertIn("No valid strikes available", validation.errors)
        self.assertIn("No greeks data available", validation.errors)

    def test_malformed_greeks_data(self):
        """Test validation with malformed greeks data."""
        malformed_data = {
            "valid_strikes": [100.0, 105.0],
            "greeks_by_strike": {
                "100.0": {
                    "call": {
                        "delta": "invalid_number",  # Non-numeric
                        "gamma": float('nan'),      # NaN
                        "theta": float('inf'),      # Infinity
                        "vega": None,              # None
                        "rho": 0.05
                    }
                },
                "105.0": "not_a_dict",  # Wrong type
                "invalid_strike": {     # Non-numeric key
                    "call": {"delta": 0.4}
                }
            },
            "undervalued_opportunities": 0
        }

        validation = _validate_options_data(malformed_data)

        # Should detect invalid data
        self.assertEqual(validation.complete_greeks_count, 0)
        self.assertGreater(validation.invalid_greeks_count, 0)
        self.assertLess(validation.data_quality_score, 0.5)

        # Should have warnings about data issues
        self.assertGreater(len(validation.warnings), 0)

    def test_partial_greeks_data(self):
        """Test validation with partial but valid greeks data."""
        partial_data = {
            "valid_strikes": [100.0, 105.0, 110.0],
            "greeks_by_strike": {
                "100.0": {
                    "call": {
                        "market_price": 5.25,
                        "model_price": 5.50,
                        "delta": 0.50,
                        "gamma": 0.10,
                        "theta": -0.06,
                        "vega": 0.18,
                        "rho": 0.025
                    }
                    # Missing put data
                },
                "105.0": {
                    "call": {
                        "market_price": 3.25,
                        "delta": 0.35,
                        "gamma": 0.08
                        # Missing some greeks
                    },
                    "put": {
                        "market_price": 7.25,
                        "delta": -0.65,
                        "gamma": 0.08,
                        "theta": -0.04,
                        "vega": 0.15,
                        "rho": -0.03
                    }
                }
                # Missing 110.0 strike entirely
            },
            "undervalued_opportunities": 1
        }

        validation = _validate_options_data(partial_data)

        # Should handle partial data gracefully
        self.assertEqual(validation.valid_strikes_count, 3)
        self.assertEqual(validation.greeks_count, 2)
        self.assertEqual(validation.complete_greeks_count, 1)  # Only 100.0 call is complete
        self.assertGreater(validation.invalid_greeks_count, 0)

        # Quality should be moderate (some good data exists)
        self.assertGreater(validation.data_quality_score, 0.2)
        self.assertLess(validation.data_quality_score, 0.8)

    def test_out_of_range_greeks(self):
        """Test validation with out-of-range greeks values."""
        invalid_ranges_data = {
            "valid_strikes": [100.0],
            "greeks_by_strike": {
                "100.0": {
                    "call": {
                        "market_price": 5.25,
                        "model_price": 5.50,
                        "delta": 1.5,    # Invalid: call delta > 1
                        "gamma": -0.1,   # Invalid: negative gamma
                        "theta": -0.06,
                        "vega": 0.18,
                        "rho": 0.025
                    },
                    "put": {
                        "market_price": 4.75,
                        "model_price": 5.00,
                        "delta": 0.2,    # Invalid: put delta should be negative
                        "gamma": 0.10,
                        "theta": -0.05,
                        "vega": 0.18,
                        "rho": -0.025
                    }
                }
            },
            "undervalued_opportunities": 1
        }

        validation = _validate_options_data(invalid_ranges_data)

        # Should detect range violations
        self.assertGreater(len(validation.warnings), 0)

        # Check for specific warnings
        warning_text = " ".join(validation.warnings)
        self.assertIn("delta out of range", warning_text)
        self.assertIn("negative gamma", warning_text)

    def test_data_sanitization_and_repair(self):
        """Test data sanitization and repair functionality."""
        problematic_data = {
            "valid_strikes": [100, "105.5", None, float('inf'), "invalid"],
            "greeks_by_strike": {
                "100": {
                    "call": {
                        "delta": 0.5,
                        "gamma": float('nan'),
                        "theta": -0.05,
                        "vega": None,
                        "rho": "invalid"
                    }
                },
                "invalid_key": {
                    "call": {"delta": 0.3}
                },
                float('nan'): {
                    "call": {"delta": 0.4}
                }
            },
            "undervalued_opportunities": "not_a_number"
        }

        cleaned_data, repair_attempts = _sanitize_and_repair_options_data(problematic_data)

        # Check that data was cleaned
        self.assertIsInstance(cleaned_data["valid_strikes"], list)
        self.assertGreater(len(repair_attempts), 0)

        # Valid strikes should only contain valid floats
        for strike in cleaned_data["valid_strikes"]:
            self.assertIsInstance(strike, (int, float))
            self.assertFalse(math.isnan(strike))
            self.assertFalse(math.isinf(strike))

        # Greeks should only contain valid entries
        for strike_key, strike_data in cleaned_data["greeks_by_strike"].items():
            self.assertIsInstance(strike_data, dict)

            # Strike key should be convertible to float
            try:
                float(strike_key)
            except (ValueError, TypeError):
                self.fail(f"Strike key {strike_key} should be numeric after sanitization")

        # Undervalued opportunities should be numeric
        self.assertIsInstance(cleaned_data["undervalued_opportunities"], (int, float))

    def test_minimal_but_valid_data(self):
        """Test that minimal but valid data can pass validation."""
        minimal_data = {
            "valid_strikes": [100.0],
            "greeks_by_strike": {
                "100.0": {
                    "call": {
                        "market_price": 5.25,
                        "model_price": 5.50,
                        "delta": 0.50,
                        "gamma": 0.10,
                        "theta": -0.06,
                        "vega": 0.18,
                        "rho": 0.025
                    }
                }
            },
            "undervalued_opportunities": 1
        }

        validation = _validate_options_data(minimal_data)

        # Should have some warnings due to limited data
        self.assertGreater(len(validation.warnings), 0)
        self.assertIn("Limited strikes available: 1", validation.warnings)

        # But should still have decent quality score for what exists
        self.assertEqual(validation.complete_greeks_count, 1)
        self.assertEqual(validation.invalid_greeks_count, 0)
        self.assertGreater(validation.data_quality_score, 0.5)

    def test_no_strike_overlap(self):
        """Test case where valid_strikes and greeks_by_strike don't overlap."""
        no_overlap_data = {
            "valid_strikes": [95.0, 100.0, 105.0],
            "greeks_by_strike": {
                "110.0": {
                    "call": {"delta": 0.3, "gamma": 0.05, "theta": -0.02, "vega": 0.1, "rho": 0.01}
                },
                "115.0": {
                    "put": {"delta": -0.2, "gamma": 0.04, "theta": -0.01, "vega": 0.08, "rho": -0.01}
                }
            },
            "undervalued_opportunities": 0
        }

        validation = _validate_options_data(no_overlap_data)

        # Should have error about no overlap
        self.assertIn("No overlap between valid strikes and available greeks", validation.errors)
        self.assertLess(validation.data_quality_score, 0.5)

if __name__ == '__main__':
    unittest.main(verbosity=2)