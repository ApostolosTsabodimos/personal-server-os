#!/bin/bash
# Test health monitoring API endpoints

echo "Testing Health Monitor API Integration"
echo "========================================"
echo ""

# Test 1: Get all health status
echo "1. GET /api/health (all services)"
curl -s http://localhost:5000/api/health | python -m json.tool
echo ""
echo ""

# Test 2: Get single service health
echo "2. GET /api/health/test-service (single service)"
curl -s http://localhost:5000/api/health/test-service | python -m json.tool
echo ""
echo ""

# Test 3: Trigger manual health check
echo "3. POST /api/health/test-service/check (manual check)"
curl -s -X POST http://localhost:5000/api/health/test-service/check | python -m json.tool
echo ""
echo ""

# Test 4: Get health history
echo "4. GET /api/health/test-service/history (history)"
curl -s http://localhost:5000/api/health/test-service/history | python -m json.tool
echo ""
echo ""

# Test 5: Get system stats (includes health summary)
echo "5. GET /api/system/stats (includes health counts)"
curl -s http://localhost:5000/api/system/stats | python -m json.tool
echo ""

echo ""
echo "========================================"
echo "Tests complete!"