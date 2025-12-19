#!/bin/bash

# Start all services for the Parcel Identification MVP with API Gateway
# API Gateway: Port 8000 (main entry point)
# Service 1: On-demand tile generation (port 8001 - internal)
# Service 2: Pre-generation service (port 8002 - internal)
# Service 3: Identify API (port 8003 - internal)

echo "🚀 Starting Parcel Identification MVP Services with API Gateway..."
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✅ Virtual environment activated"
fi

# Change to backend directory
cd backend

# Start Service 1: On-demand tile generation (internal)
echo "📦 Starting Service 1: On-demand Tile Generation (port 8001)..."
uvicorn services.tile_service:app --host 127.0.0.1 --port 8001 --reload &
SERVICE1_PID=$!
echo "   PID: $SERVICE1_PID"

# Start Service 2: Pre-generation service (internal)
echo "⚙️  Starting Service 2: Pre-generation Service (port 8002)..."
uvicorn services.pregenerate_service:app --host 127.0.0.1 --port 8002 --reload &
SERVICE2_PID=$!
echo "   PID: $SERVICE2_PID"

# Start Service 3: Identify API (internal)
echo "🔍 Starting Service 3: Identify API (port 8003)..."
uvicorn services.identify_service:app --host 127.0.0.1 --port 8003 --reload &
SERVICE3_PID=$!
echo "   PID: $SERVICE3_PID"

# Wait a moment for services to start
sleep 2

# Start API Gateway (main entry point)
echo "🚪 Starting API Gateway (port 8000)..."
uvicorn services.api_gateway:app --host 127.0.0.1 --port 8000 --reload &
GATEWAY_PID=$!
echo "   PID: $GATEWAY_PID"

echo ""
echo "✅ All services started!"
echo ""
echo "🌐 API Gateway (Main Entry Point):"
echo "  http://127.0.0.1:8000"
echo ""
echo "📋 Available Endpoints (via Gateway):"
echo "  Tiles:              http://127.0.0.1:8000/tiles/{z}/{x}/{y}.png"
echo "  Pre-generation:     http://127.0.0.1:8000/api/pregenerate-viewport"
echo "  Identify:           http://127.0.0.1:8000/api/identify"
echo "  States/Districts:   http://127.0.0.1:8000/api/states-districts"
echo "  Bounds:             http://127.0.0.1:8000/api/bounds"
echo "  Place Labels:       http://127.0.0.1:8000/api/place-labels"
echo ""
echo "🏥 Health Check:"
echo "  http://127.0.0.1:8000/health"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for Ctrl+C
trap "echo ''; echo '🛑 Stopping all services...'; kill $GATEWAY_PID $SERVICE1_PID $SERVICE2_PID $SERVICE3_PID 2>/dev/null; exit" INT

# Keep script running
wait

