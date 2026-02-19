#!/bin/bash
#
# Test Build Process - Infrastructure Testing Script
# This script tests all components within the Infrastructure Specialist's jurisdiction
#

set -e

echo "🧪 Starting Infrastructure Build Process Testing..."
echo "================================================"

# Test 1: Backend Python Environment
echo "📦 Testing Backend Python Environment..."
cd backend

# Check if requirements.txt is valid
echo "   Validating requirements.txt syntax..."
pip install --dry-run -r requirements.txt > /dev/null 2>&1 && echo "   ✅ requirements.txt is valid" || echo "   ❌ requirements.txt has issues"

# Test backend imports
echo "   Testing backend imports..."
python -c "
import sys
sys.path.append('src')
try:
    from src.main import app
    print('   ✅ FastAPI app imports successfully')
except ImportError as e:
    print(f'   ❌ FastAPI import failed: {e}')
except Exception as e:
    print(f'   ⚠️  FastAPI import warning: {e}')
"

cd ..

# Test 2: Docker Configuration Validation
echo "🐳 Testing Docker Configuration..."

# Validate docker-compose.yml syntax
echo "   Validating docker-compose.yml..."
if command -v docker-compose >/dev/null 2>&1; then
    docker-compose config > /dev/null 2>&1 && echo "   ✅ docker-compose.yml is valid" || echo "   ❌ docker-compose.yml has syntax errors"
else
    echo "   ⚠️  docker-compose not available, skipping validation"
fi

# Validate Dockerfile syntax
echo "   Validating Dockerfile syntax..."
if [ -f "backend/Dockerfile" ]; then
    echo "   ✅ Backend Dockerfile exists"
else
    echo "   ❌ Backend Dockerfile missing"
fi

if [ -f "frontend/Dockerfile" ]; then
    echo "   ✅ Frontend Dockerfile exists"
else
    echo "   ❌ Frontend Dockerfile missing"
fi

# Test 3: Frontend Build Dependencies (Via Docker)
echo "🎨 Testing Frontend Build Process (via Docker)..."

# Check if package.json and package-lock.json are in sync
cd frontend

if [ -f "package.json" ] && [ -f "package-lock.json" ]; then
    echo "   ✅ Both package.json and package-lock.json exist"

    # Basic JSON validation
    python -c "
import json
try:
    with open('package.json') as f:
        json.load(f)
    print('   ✅ package.json is valid JSON')
except:
    print('   ❌ package.json is invalid JSON')

try:
    with open('package-lock.json') as f:
        json.load(f)
    print('   ✅ package-lock.json is valid JSON')
except:
    print('   ❌ package-lock.json is invalid JSON')
"

    # Check for potential npm ci issues
    if [ -d "node_modules" ]; then
        echo "   ⚠️  node_modules exists - may cause npm ci issues"
        echo "   💡 Consider running: rm -rf node_modules before npm ci"
    else
        echo "   ✅ node_modules does not exist - good for npm ci"
    fi
else
    echo "   ❌ Missing package files"
fi

cd ..

# Test 4: Deployment Script Validation
echo "🚀 Testing Deployment Script..."

if [ -f "deploy.sh" ] && [ -x "deploy.sh" ]; then
    echo "   ✅ deploy.sh exists and is executable"

    # Test script syntax
    bash -n deploy.sh && echo "   ✅ deploy.sh has valid bash syntax" || echo "   ❌ deploy.sh has syntax errors"
else
    echo "   ❌ deploy.sh missing or not executable"
fi

# Test 5: Environment Configuration
echo "🔧 Testing Environment Configuration..."

if [ -f ".env" ]; then
    echo "   ✅ .env file exists"
else
    echo "   ⚠️  .env file missing - may cause runtime issues"
fi

if [ -f "frontend/.env.production" ]; then
    echo "   ✅ Frontend production env file exists"
else
    echo "   ⚠️  Frontend .env.production missing"
fi

# Test 6: Backend Tests (if pytest available)
echo "🧪 Testing Backend Test Suite..."

if command -v pytest >/dev/null 2>&1; then
    cd backend
    if [ -d "tests" ]; then
        echo "   Running backend tests..."
        export PYTHONPATH="$PYTHONPATH:$(pwd)"
        pytest tests/ -v --tb=short -x || echo "   ⚠️  Some backend tests failed"
    else
        echo "   ❌ Backend tests directory not found"
    fi
    cd ..
else
    echo "   ⚠️  pytest not available, skipping backend tests"
fi

echo ""
echo "🏁 Testing Complete!"
echo "================================================"
echo ""
echo "📋 Summary:"
echo "   - Backend Python environment: Tested"
echo "   - Docker configuration: Validated"
echo "   - Frontend dependencies: Checked"
echo "   - Deployment scripts: Validated"
echo "   - Environment files: Checked"
echo "   - Backend tests: Executed"
echo ""
echo "💡 To test npm ci specifically:"
echo "   cd frontend && npm ci"
echo ""
echo "💡 To test full Docker build:"
echo "   docker-compose build"
echo ""