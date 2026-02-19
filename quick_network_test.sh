#!/bin/bash
#
# Quick Network Connectivity Test
# Performs basic network tests to verify frontend-backend connectivity
#

set -e

echo "🔍 Quick Network Connectivity Test"
echo "================================="

# Check containers are running
echo "1. Checking container status..."
docker ps --filter "name=trader_intelligence_v2" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo

# Test frontend port
echo "2. Testing frontend port 3111..."
if curl -s -I http://localhost:3111 >/dev/null 2>&1; then
    echo "   ✅ Frontend port 3111 is accessible"
else
    echo "   ❌ Frontend port 3111 is not accessible"
fi
echo

# Test backend port
echo "3. Testing backend port 8511..."
if curl -s -I http://localhost:8511 >/dev/null 2>&1; then
    echo "   ✅ Backend port 8511 is accessible"
else
    echo "   ❌ Backend port 8511 is not accessible"
fi
echo

# Test host.docker.internal from frontend container
echo "4. Testing host.docker.internal resolution from frontend..."
if docker exec trader_intelligence_v2_frontend_1 ping -c 1 host.docker.internal >/dev/null 2>&1; then
    echo "   ✅ host.docker.internal is resolvable from frontend container"
else
    echo "   ❌ host.docker.internal is NOT resolvable from frontend container"
fi
echo

# Test backend connectivity from frontend container
echo "5. Testing backend connectivity from frontend container..."
if docker exec trader_intelligence_v2_frontend_1 wget -qO- --timeout=5 http://host.docker.internal:8511/health >/dev/null 2>&1; then
    echo "   ✅ Backend is accessible from frontend container"
else
    echo "   ❌ Backend is NOT accessible from frontend container"
fi
echo

# Test nginx proxy
echo "6. Testing nginx proxy to backend..."
if curl -s http://localhost:3111/api/health >/dev/null 2>&1; then
    echo "   ✅ Nginx proxy is working correctly"
    echo "   Response from proxy:"
    curl -s http://localhost:3111/api/health | python3 -m json.tool 2>/dev/null || echo "   (Non-JSON response)"
else
    echo "   ❌ Nginx proxy is NOT working"
fi
echo

echo "================================="
echo "Quick test completed!"
echo "For comprehensive testing, run: python3 test_network_connectivity.py"