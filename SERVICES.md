# Multi-Service Architecture with API Gateway

The Parcel Identification MVP uses an **API Gateway** as a single entry point that routes requests to **3 backend services** running as independent processes.

## Architecture Overview

```
Frontend (Browser)
    ↓
API Gateway (Port 8000) ← Single Entry Point
    ├─→ Service 1: Tile Generation (Port 8001)
    ├─→ Service 2: Pre-generation (Port 8002)
    └─→ Service 3: Identify API (Port 8003)
```

## API Gateway

- **Port**: `8000` (main entry point)
- **File**: `backend/services/api_gateway.py`
- **Purpose**: Single entry point that routes all requests to appropriate backend services
- **Endpoints**:
  - All endpoints are accessible via port 8000
  - `GET /health` - Health check for gateway and all services

**Start individually:**
```bash
cd backend
uvicorn services.api_gateway:app --host 127.0.0.1 --port 8000 --reload
```

## Service Architecture

### Service 1: On-Demand Tile Generation
- **Port**: `8001` (internal, accessed via API Gateway)
- **File**: `backend/services/tile_service.py`
- **Purpose**: Serve tiles on-demand (cache-first, generate if missing)
- **Endpoints**:
  - `GET /tiles/{z}/{x}/{y}.png` - Get raster tile
  - `GET /health` - Health check

**Access via Gateway**: `http://127.0.0.1:8000/tiles/{z}/{x}/{y}.png`

**Start individually:**
```bash
cd backend
uvicorn services.tile_service:app --host 127.0.0.1 --port 8001 --reload
```

---

### Service 2: Pre-Generation Service
- **Port**: `8002` (internal, accessed via API Gateway)
- **File**: `backend/services/pregenerate_service.py`
- **Purpose**: Pre-generate tiles in background for viewport areas
- **Endpoints**:
  - `GET /api/pregenerate-viewport` - Pre-generate tiles for viewport
  - `GET /health` - Health check

**Access via Gateway**: `http://127.0.0.1:8000/api/pregenerate-viewport`

**Start individually:**
```bash
cd backend
uvicorn services.pregenerate_service:app --host 127.0.0.1 --port 8002 --reload
```

---

### Service 3: Identify API Service
- **Port**: `8003` (internal, accessed via API Gateway)
- **File**: `backend/services/identify_service.py`
- **Purpose**: Parcel identification and metadata endpoints
- **Endpoints**:
  - `GET /api/identify` - Identify parcel at lat/lon
  - `GET /api/states-districts` - Get available states/districts
  - `GET /api/bounds` - Get bounds for filters
  - `GET /api/place-labels` - Get place labels
  - `GET /health` - Health check

**Access via Gateway**: `http://127.0.0.1:8000/api/*`

**Start individually:**
```bash
cd backend
uvicorn services.identify_service:app --host 127.0.0.1 --port 8003 --reload
```

---

## Starting All Services

### Option 1: Use the startup script (recommended)
```bash
./start_services.sh
```

This will start the API Gateway and all 3 backend services in the background and display their PIDs.

### Option 2: Start manually in separate terminals
```bash
# Terminal 1: API Gateway (main entry point)
cd backend && uvicorn services.api_gateway:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2: Tile Service
cd backend && uvicorn services.tile_service:app --host 127.0.0.1 --port 8001 --reload

# Terminal 3: Pre-generation Service
cd backend && uvicorn services.pregenerate_service:app --host 127.0.0.1 --port 8002 --reload

# Terminal 4: Identify API Service
cd backend && uvicorn services.identify_service:app --host 127.0.0.1 --port 8003 --reload
```

---

## Frontend Configuration

The frontend (`frontend/map-app/index.html`) is configured to use the **API Gateway** on port 8000:
- **All requests**: `http://127.0.0.1:8000/*`
- The gateway automatically routes to the appropriate backend service
- No need to know individual service ports

---

## Benefits of API Gateway Architecture

1. **Single Entry Point**: Frontend only needs to know one URL (port 8000)
2. **Simplified Configuration**: No need to manage multiple ports in frontend
3. **Centralized Routing**: All routing logic in one place
4. **Service Isolation**: Each backend service can be scaled independently
5. **Resource Management**: Heavy tile generation doesn't block API requests
6. **Deployment Flexibility**: Services can be deployed on different servers
7. **Fault Tolerance**: If one service fails, others continue working
8. **Health Monitoring**: Gateway provides unified health check for all services
9. **Development**: Easier to debug and test individual services

---

## Health Checks

Check API Gateway and all services:
```bash
curl http://127.0.0.1:8000/health  # API Gateway (shows status of all services)
```

Check individual services directly:
```bash
curl http://127.0.0.1:8001/health  # Tile Service
curl http://127.0.0.1:8002/health  # Pre-generation Service
curl http://127.0.0.1:8003/health  # Identify API Service
```

---

## Stopping Services

If using the startup script, press `Ctrl+C` to stop all services.

If running manually, use `Ctrl+C` in each terminal or find and kill processes:
```bash
# Find processes
ps aux | grep uvicorn

# Kill by port
lsof -ti:8000 | xargs kill  # API Gateway
lsof -ti:8001 | xargs kill  # Tile Service
lsof -ti:8002 | xargs kill  # Pre-generation Service
lsof -ti:8003 | xargs kill  # Identify API Service
```

