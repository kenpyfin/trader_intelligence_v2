#!/usr/bin/env python3
"""
Quick import test for DataQualityFallbackManager
"""

import sys

# Test individual imports
try:
    print("Testing DataQualityFallbackManager import...")
    from analytics.data_quality_fallback_manager import DataQualityFallbackManager
    print("✅ SUCCESS: DataQualityFallbackManager imported")
except Exception as e:
    print(f"❌ FAILED: {e}")
    sys.exit(1)

try:
    print("Testing EnhancedGreeksValidator import...")
    from analytics.enhanced_greeks_validation import EnhancedGreeksValidator
    print("✅ SUCCESS: EnhancedGreeksValidator imported")
except Exception as e:
    print(f"❌ FAILED: {e}")
    sys.exit(1)

try:
    print("Testing configuration import...")
    from analytics.expiration_fallback_config import create_default_fallback_config
    print("✅ SUCCESS: Configuration imported")
except Exception as e:
    print(f"❌ FAILED: {e}")
    sys.exit(1)

# Test instantiation
try:
    print("Testing DataQualityFallbackManager instantiation...")
    config = create_default_fallback_config()
    manager = DataQualityFallbackManager(config)
    print(f"✅ SUCCESS: Manager created with config")

    # Check the Greeks validator type
    validator_type = type(manager.greeks_validator).__name__
    print(f"✅ Greeks validator type: {validator_type}")

    if validator_type == "EnhancedGreeksValidator":
        print("✅ SUCCESS: Correct validator type")
    else:
        print(f"❌ WRONG TYPE: Expected EnhancedGreeksValidator, got {validator_type}")
        sys.exit(1)

except Exception as e:
    print(f"❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n🎉 ALL TESTS PASSED! The fix is working correctly.")