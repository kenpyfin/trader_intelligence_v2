#!/usr/bin/env python3
"""
Test script to verify DataQualityFallbackManager import and functionality
"""

import sys
import traceback
from datetime import date, datetime


def test_imports():
    """Test that all required imports work correctly."""
    print("=== Testing Imports ===")

    try:
        # Test importing the fallback manager
        from analytics.data_quality_fallback_manager import DataQualityFallbackManager
        print("✅ DataQualityFallbackManager imported successfully")

        # Test importing the config
        from analytics.expiration_fallback_config import create_default_fallback_config, FallbackStrategyConfig
        print("✅ Fallback config imported successfully")

        # Test importing enhanced Greeks validator
        from analytics.enhanced_greeks_validation import EnhancedGreeksValidator
        print("✅ EnhancedGreeksValidator imported successfully")

        return True

    except ImportError as e:
        print(f"❌ Import failed: {e}")
        traceback.print_exc()
        return False


def test_instantiation():
    """Test that DataQualityFallbackManager can be instantiated."""
    print("\n=== Testing Instantiation ===")

    try:
        from analytics.data_quality_fallback_manager import DataQualityFallbackManager
        from analytics.expiration_fallback_config import create_default_fallback_config

        # Test with default config
        config = create_default_fallback_config()
        manager = DataQualityFallbackManager(config)
        print("✅ DataQualityFallbackManager instantiated successfully with custom config")

        # Test with no config (should use default)
        manager_default = DataQualityFallbackManager()
        print("✅ DataQualityFallbackManager instantiated successfully with default config")

        # Test accessing attributes
        print(f"   - Enable fallback: {manager.config.enable_fallback}")
        print(f"   - Max attempts: {manager.config.max_total_attempts}")
        print(f"   - Has decision engine: {manager.decision_engine is not None}")
        print(f"   - Has quality assessor: {manager.quality_assessor is not None}")
        print(f"   - Has Greeks validator: {manager.greeks_validator is not None}")
        print(f"   - Greeks validator type: {type(manager.greeks_validator).__name__}")

        return True

    except Exception as e:
        print(f"❌ Instantiation failed: {e}")
        traceback.print_exc()
        return False


def test_enhanced_greeks_validation():
    """Test that the enhanced Greeks validation functionality works."""
    print("\n=== Testing Enhanced Greeks Validation ===")

    try:
        from analytics.data_quality_fallback_manager import DataQualityFallbackManager
        from analytics.enhanced_greeks_validation import EnhancedGreeksValidator

        # Create manager
        manager = DataQualityFallbackManager()

        # Test that the validator is the correct type
        validator = manager.greeks_validator
        print(f"✅ Validator type: {type(validator).__name__}")

        if not isinstance(validator, EnhancedGreeksValidator):
            print(f"❌ Wrong validator type. Expected EnhancedGreeksValidator, got {type(validator).__name__}")
            return False

        # Test validator methods exist
        required_methods = [
            'validate_and_enhance_greeks_data',
            'create_validation_summary'
        ]

        for method_name in required_methods:
            if hasattr(validator, method_name):
                print(f"✅ Method '{method_name}' exists")
            else:
                print(f"❌ Method '{method_name}' missing")
                return False

        # Test validator attributes
        required_attributes = [
            'repair_validator',
            'required_greeks',
            'required_prices',
            'essential_greeks',
            'important_greeks'
        ]

        for attr_name in required_attributes:
            if hasattr(validator, attr_name):
                attr_value = getattr(validator, attr_name)
                print(f"✅ Attribute '{attr_name}': {attr_value}")
            else:
                print(f"❌ Attribute '{attr_name}' missing")
                return False

        return True

    except Exception as e:
        print(f"❌ Enhanced Greeks validation test failed: {e}")
        traceback.print_exc()
        return False


def test_manager_functionality():
    """Test basic manager functionality."""
    print("\n=== Testing Manager Functionality ===")

    try:
        from analytics.data_quality_fallback_manager import DataQualityFallbackManager

        manager = DataQualityFallbackManager()

        # Test stats functionality
        stats = manager.get_execution_stats()
        print(f"✅ Execution stats retrieved: {stats}")

        # Verify stats structure
        expected_keys = ['total_executions', 'successful_fallbacks', 'success_rate_percent', 'config_summary']
        for key in expected_keys:
            if key in stats:
                print(f"✅ Stats key '{key}': {stats[key]}")
            else:
                print(f"❌ Missing stats key: {key}")
                return False

        return True

    except Exception as e:
        print(f"❌ Manager functionality test failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("DataQualityFallbackManager Integration Test")
    print("=" * 50)

    test_results = []

    # Run tests
    test_results.append(("Imports", test_imports()))
    test_results.append(("Instantiation", test_instantiation()))
    test_results.append(("Enhanced Greeks Validation", test_enhanced_greeks_validation()))
    test_results.append(("Manager Functionality", test_manager_functionality()))

    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)

    passed = 0
    failed = 0

    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:.<30} {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\nTotal: {passed + failed}, Passed: {passed}, Failed: {failed}")

    if failed == 0:
        print("\n🎉 All tests passed! DataQualityFallbackManager is working correctly.")
        return 0
    else:
        print(f"\n❌ {failed} test(s) failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())