#!/usr/bin/env python3
"""
Backend API Testing Script
Tests the FastAPI backend endpoints and CORS functionality.
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BACKEND_URL = "http://localhost:8511"
TIMEOUT = 10

def test_endpoint(url, description, method="GET", data=None):
    """Test a single endpoint and return the result."""
    print(f"Testing {description}...")
    try:
        if method.upper() == "GET":
            response = requests.get(url, timeout=TIMEOUT)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, timeout=TIMEOUT)

        print(f"  Status Code: {response.status_code}")
        print(f"  Response Time: {response.elapsed.total_seconds():.2f}s")

        if response.status_code == 200:
            try:
                json_response = response.json()
                print(f"  Response: {json.dumps(json_response, indent=2)[:200]}...")
                print("  ✅ SUCCESS")
                return True
            except json.JSONDecodeError:
                print(f"  Response (text): {response.text[:200]}...")
                print("  ✅ SUCCESS (non-JSON)")
                return True
        else:
            print(f"  Error: {response.text}")
            print("  ❌ FAILED")
            return False

    except requests.exceptions.RequestException as e:
        print(f"  Connection Error: {e}")
        print("  ❌ FAILED")
        return False
    except Exception as e:
        print(f"  Unexpected Error: {e}")
        print("  ❌ FAILED")
        return False

def test_cors_headers(url, origin):
    """Test CORS preflight request."""
    print(f"Testing CORS preflight for origin: {origin}")
    try:
        # OPTIONS request for CORS preflight
        headers = {
            'Origin': origin,
            'Access-Control-Request-Method': 'GET',
            'Access-Control-Request-Headers': 'Content-Type'
        }
        response = requests.options(url, headers=headers, timeout=TIMEOUT)

        print(f"  Status Code: {response.status_code}")
        cors_headers = {
            'Access-Control-Allow-Origin': response.headers.get('Access-Control-Allow-Origin'),
            'Access-Control-Allow-Methods': response.headers.get('Access-Control-Allow-Methods'),
            'Access-Control-Allow-Headers': response.headers.get('Access-Control-Allow-Headers'),
            'Access-Control-Allow-Credentials': response.headers.get('Access-Control-Allow-Credentials')
        }

        print("  CORS Headers:")
        for header, value in cors_headers.items():
            if value:
                print(f"    {header}: {value}")

        if cors_headers['Access-Control-Allow-Origin'] in ['*', origin]:
            print("  ✅ CORS CONFIGURED CORRECTLY")
            return True
        else:
            print("  ❌ CORS NOT CONFIGURED FOR THIS ORIGIN")
            return False

    except Exception as e:
        print(f"  CORS Test Error: {e}")
        print("  ❌ CORS TEST FAILED")
        return False

def main():
    """Run all backend tests."""
    print("=" * 60)
    print("TRADER INTELLIGENCE BACKEND API TESTS")
    print("=" * 60)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test Time: {datetime.now().isoformat()}")
    print("=" * 60)

    # Test endpoints
    tests = [
        (f"{BACKEND_URL}/", "Root Endpoint"),
        (f"{BACKEND_URL}/health", "Health Check"),
        (f"{BACKEND_URL}/api/health", "Health Check (API alias)"),
        (f"{BACKEND_URL}/cors-test", "CORS Test Endpoint"),
        (f"{BACKEND_URL}/api/cors-test", "CORS Test (API alias)"),
        (f"{BACKEND_URL}/api/macro-data", "Macro Data"),
        (f"{BACKEND_URL}/api/yield-curve", "Yield Curve"),
    ]

    results = []
    for url, description in tests:
        result = test_endpoint(url, description)
        results.append((description, result))
        print()

    # Test CORS configuration
    print("=" * 60)
    print("CORS CONFIGURATION TESTS")
    print("=" * 60)

    cors_origins = [
        "http://localhost:3111",
        "http://host.docker.internal:3111",
        "http://127.0.0.1:3111"
    ]

    cors_results = []
    for origin in cors_origins:
        result = test_cors_headers(f"{BACKEND_URL}/", origin)
        cors_results.append((f"CORS for {origin}", result))
        print()

    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    all_passed = True
    for description, passed in results + cors_results:
        status = "PASS" if passed else "FAIL"
        print(f"{description}: {status}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Backend is working correctly.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Check the backend configuration.")
        sys.exit(1)

if __name__ == "__main__":
    main()