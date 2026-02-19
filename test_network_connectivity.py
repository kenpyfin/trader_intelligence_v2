#!/usr/bin/env python3
"""
Network Connectivity Test Suite
Tests all network connections between frontend and backend containers.
"""

import socket
import subprocess
import requests
import json
import time
import sys
from datetime import datetime

# Configuration
FRONTEND_PORT = 3111
BACKEND_PORT = 8511
TIMEOUT = 5

def test_port_open(host, port, description):
    """Test if a port is open and accessible."""
    print(f"Testing {description} ({host}:{port})...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        result = sock.connect_ex((host, port))
        sock.close()

        if result == 0:
            print(f"  ✅ Port {port} is OPEN and accessible")
            return True
        else:
            print(f"  ❌ Port {port} is CLOSED or not accessible")
            return False
    except Exception as e:
        print(f"  ❌ Error testing port: {e}")
        return False

def test_http_endpoint(url, description):
    """Test HTTP endpoint accessibility."""
    print(f"Testing {description} ({url})...")
    try:
        response = requests.get(url, timeout=TIMEOUT)
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            print(f"  ✅ Endpoint is accessible")
            try:
                data = response.json()
                print(f"  Response: {json.dumps(data, indent=2)[:100]}...")
            except:
                print(f"  Response: {response.text[:100]}...")
            return True
        else:
            print(f"  ❌ Endpoint returned error: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"  ❌ Connection failed - service may not be running")
        return False
    except requests.exceptions.Timeout:
        print(f"  ❌ Request timed out after {TIMEOUT}s")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def test_docker_exec(container_name, command, description):
    """Execute a command inside a Docker container."""
    print(f"Testing {description}...")
    try:
        result = subprocess.run(
            ["docker", "exec", container_name] + command,
            capture_output=True,
            text=True,
            timeout=TIMEOUT
        )

        if result.returncode == 0:
            print(f"  ✅ Command succeeded")
            print(f"  Output: {result.stdout.strip()}")
            return True
        else:
            print(f"  ❌ Command failed (exit code: {result.returncode})")
            print(f"  Error: {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ❌ Command timed out after {TIMEOUT}s")
        return False
    except Exception as e:
        print(f"  ❌ Error executing command: {e}")
        return False

def test_dns_resolution():
    """Test DNS resolution of host.docker.internal from frontend container."""
    return test_docker_exec(
        "trader_intelligence_v2_frontend_1",
        ["nslookup", "host.docker.internal"],
        "DNS resolution of host.docker.internal from frontend container"
    )

def test_ping_from_frontend():
    """Test network connectivity from frontend to host."""
    return test_docker_exec(
        "trader_intelligence_v2_frontend_1",
        ["ping", "-c", "1", "host.docker.internal"],
        "Ping from frontend to host.docker.internal"
    )

def test_wget_from_frontend():
    """Test HTTP request from frontend to backend."""
    return test_docker_exec(
        "trader_intelligence_v2_frontend_1",
        ["wget", "-qO-", f"http://host.docker.internal:{BACKEND_PORT}/health"],
        f"HTTP request from frontend to backend health endpoint"
    )

def test_curl_from_frontend():
    """Test curl request from frontend to backend."""
    return test_docker_exec(
        "trader_intelligence_v2_frontend_1",
        ["curl", "-s", "-f", f"http://host.docker.internal:{BACKEND_PORT}/health"],
        f"Curl request from frontend to backend health endpoint"
    )

def test_nginx_proxy():
    """Test nginx proxy functionality."""
    return test_http_endpoint(
        f"http://localhost:{FRONTEND_PORT}/api/health",
        "Nginx proxy to backend health endpoint"
    )

def check_container_status():
    """Check if required containers are running."""
    print("Checking container status...")
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=trader_intelligence_v2", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            containers = result.stdout.strip().split('\n')
            print("  Running containers:")
            for container in containers:
                if container.strip():
                    print(f"    {container}")

            # Check if both containers are running
            running_containers = result.stdout
            frontend_running = "trader_intelligence_v2_frontend_1" in running_containers and "Up" in running_containers
            backend_running = "trader_intelligence_v2_backend_1" in running_containers and "Up" in running_containers

            if frontend_running and backend_running:
                print("  ✅ Both frontend and backend containers are running")
                return True
            else:
                print("  ❌ One or both containers are not running")
                return False
        else:
            print(f"  ❌ Error checking container status: {result.stderr}")
            return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def main():
    """Run all network connectivity tests."""
    print("=" * 70)
    print("TRADER INTELLIGENCE NETWORK CONNECTIVITY TEST SUITE")
    print("=" * 70)
    print(f"Test Time: {datetime.now().isoformat()}")
    print(f"Frontend Port: {FRONTEND_PORT}")
    print(f"Backend Port: {BACKEND_PORT}")
    print("=" * 70)

    results = []

    # 1. Container Status Check
    results.append(("Container Status Check", check_container_status()))
    print()

    # 2. Port Accessibility Tests
    print("🔌 PORT ACCESSIBILITY TESTS")
    print("-" * 40)
    results.append(("Frontend Port (Host)", test_port_open("localhost", FRONTEND_PORT, "Frontend port from host")))
    results.append(("Backend Port (Host)", test_port_open("localhost", BACKEND_PORT, "Backend port from host")))
    print()

    # 3. HTTP Endpoint Tests from Host
    print("🌐 HTTP ENDPOINT TESTS (From Host)")
    print("-" * 40)
    results.append(("Frontend Root", test_http_endpoint(f"http://localhost:{FRONTEND_PORT}/", "Frontend root page")))
    results.append(("Backend Root", test_http_endpoint(f"http://localhost:{BACKEND_PORT}/", "Backend root endpoint")))
    results.append(("Backend Health", test_http_endpoint(f"http://localhost:{BACKEND_PORT}/health", "Backend health endpoint")))
    results.append(("Backend CORS Test", test_http_endpoint(f"http://localhost:{BACKEND_PORT}/cors-test", "Backend CORS test endpoint")))
    print()

    # 4. Container-to-Container Tests
    print("🐳 CONTAINER-TO-CONTAINER TESTS")
    print("-" * 40)
    results.append(("DNS Resolution", test_dns_resolution()))
    results.append(("Ping Test", test_ping_from_frontend()))
    results.append(("Wget Test", test_wget_from_frontend()))
    results.append(("Curl Test", test_curl_from_frontend()))
    print()

    # 5. Proxy Tests
    print("🔀 NGINX PROXY TESTS")
    print("-" * 40)
    results.append(("Nginx Health Proxy", test_nginx_proxy()))
    results.append(("API Macro Data", test_http_endpoint(f"http://localhost:{FRONTEND_PORT}/api/macro-data", "API macro data through proxy")))
    print()

    # Summary
    print("=" * 70)
    print("TEST RESULTS SUMMARY")
    print("=" * 70)

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        emoji = "✅" if result else "❌"
        print(f"{emoji} {test_name:<40} {status}")
        if result:
            passed += 1

    print("-" * 70)
    print(f"TOTAL: {passed}/{total} tests passed ({passed/total*100:.1f}%)")

    if passed == total:
        print("🎉 All network connectivity tests PASSED!")
        print("✅ Frontend and backend are properly connected")
        return 0
    else:
        print("⚠️  Some network connectivity tests FAILED")
        print("🔧 Check Docker configuration and container health")
        return 1

if __name__ == "__main__":
    sys.exit(main())