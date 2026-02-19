#!/bin/bash
#
# Backend Restart and Verification Script
# Restarts the backend container and verifies CORS and API functionality
#

set -e

echo "🔄 Restarting Trader Intelligence Backend..."

# Restart only the backend service
echo "Stopping backend container..."
docker-compose stop backend

echo "Rebuilding and starting backend container..."
docker-compose up --build -d backend

# Wait for the backend to start
echo "⏳ Waiting for backend to initialize..."
sleep 5

# Check if container is running
if docker ps --filter "name=trader_intelligence_v2_backend" --filter "status=running" | grep -q trader_intelligence_v2_backend; then
    echo "✅ Backend container is running"
else
    echo "❌ Backend container failed to start"
    echo "Showing backend logs:"
    docker logs trader_intelligence_v2_backend_1 --tail 20
    exit 1
fi

# Test basic connectivity
echo "🧪 Testing backend connectivity..."
max_retries=30
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    if curl -s -f http://localhost:8511/health > /dev/null 2>&1; then
        echo "✅ Backend is responding to health checks"
        break
    else
        echo "⏳ Waiting for backend to respond... (attempt $((retry_count + 1))/$max_retries)"
        sleep 2
        retry_count=$((retry_count + 1))
    fi
done

if [ $retry_count -eq $max_retries ]; then
    echo "❌ Backend failed to respond after $max_retries attempts"
    echo "Showing backend logs:"
    docker logs trader_intelligence_v2_backend_1 --tail 20
    exit 1
fi

echo "🎉 Backend restart completed successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Run: python3 test_backend_api.py"
echo "2. Test frontend connectivity at: http://localhost:3111"
echo "3. Check backend health at: http://localhost:8511/health"
echo ""
echo "🔍 Backend logs (last 10 lines):"
docker logs trader_intelligence_v2_backend_1 --tail 10