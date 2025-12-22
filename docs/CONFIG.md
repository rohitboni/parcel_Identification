# Configuration Documentation

## Overview

This document describes all configuration settings, file paths, environment variables, and connection strings used throughout the Parcel MVP project.

## Database Configuration

### ETL Pipeline Configuration

**File**: `etl/load_vellore.py` (lines 10-16)

```python
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "parcels_db",
    "user": "postgres",
    "password": "postgres"
}
```

**Usage**: Used by ETL pipeline to connect to PostgreSQL database.

### Tile Server Configuration

**File**: `backend/tile_server/utils/generate_tile.py` (lines 16-22)

```python
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "parcels_db",
    "user": "postgres",
    "password": "postgres"
}
```

**Usage**: Used by raster tile generation for database queries.

### Vector Tile Server Configuration

**File**: `backend/tile_server/tile_server_vector.py` (line 10)

```python
DB_DSN = os.environ.get("DATABASE_URL") or "postgresql://postgres:postgres@127.0.0.1:5432/parcels_db"
```

**Usage**: Connection string for asyncpg connection pool.

**Environment Variable**: `DATABASE_URL` (optional)

**Format**: `postgresql://user:password@host:port/database`

## File Paths

### Shapefile Path

**File**: `etl/load_vellore.py` (line 9)

```python
SHAPEFILE_PATH = "data/vellore/vellore_cad.shp"
```

**Relative Path**: From project root

**Absolute Path Example**: `/home/vamsi/parcel_mvp/data/vellore/vellore_cad.shp`

### Spatial Index Shapefile Path

**File**: `backend/identify_api/utils/spatial_index.py` (line 5)

```python
SHAPEFILE_PATH = "/home/vamsi/parcel_mvp/data/vellore/vellore_cad.shp"
```

**Note**: Currently uses absolute path. Should be made relative or configurable.

### Cache Directory

**File**: `backend/tile_server/utils/cache_manager.py` (line 5)

```python
CACHE_DIR = "cache"
```

**Location**: `backend/cache/`

**Structure**: `cache/{z}/{x}/{y}.png`

**Example**: `backend/cache/12/2945/1898.png`

## Tile Configuration

### Tile Generation Parameters

**File**: `backend/tile_server/utils/generate_tile.py`

- **Tile Size**: 256x256 pixels (standard)
- **Image Format**: PNG with RGBA channels
- **Coordinate System**: EPSG:4326 (WGS84) for input, Web Mercator for tile scheme

### Vector Tile Parameters

**File**: `backend/tile_server/tile_server_vector.py` (lines 11-12)

```python
TILE_BUFFER = 64      # buffer for geometry in tile pixels
TILE_EXTENT = 4096    # MVT internal extent
```

**TILE_BUFFER**: Buffer in pixels for geometry clipping in `ST_AsMVTGeom`

**TILE_EXTENT**: Internal coordinate system extent for MVT (Mapbox Vector Tile) format

### Geometry Simplification

**File**: `etl/load_vellore.py` (line 121)

```python
simplify_tol = 0.00008
```

**Tolerance**: 0.00008 degrees (approximately 8.9 meters at equator)

**Method**: Douglas-Peucker algorithm with topology preservation

**Usage**: Applied to geometries in `parcels_simplified` table

## API Configuration

### CORS Configuration

**File**: `backend/main.py` (lines 9-15)

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # or ["http://127.0.0.1:8080"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Current Setting**: Allows all origins (development only)

**Production Recommendation**: Restrict to specific domains

### Server Configuration

**Default Port**: 8000

**Start Command**: `uvicorn main:app --reload`

**Host**: `127.0.0.1` (localhost)

## Frontend Configuration

### Backend API URL

**File**: `frontend/map-app/index.html` (lines 47, 64)

```javascript
L.tileLayer("http://127.0.0.1:8000/tiles/{z}/{x}/{y}.png", ...)
const url = `http://127.0.0.1:8000/api/identify?lat=${lat}&lon=${lon}`;
```

**Base URL**: `http://127.0.0.1:8000`

**Endpoints**:
- Tiles: `/tiles/{z}/{x}/{y}.png`
- Identify: `/api/identify`

### Map Configuration

**File**: `frontend/map-app/index.html` (line 38)

```javascript
const map = L.map("map").setView([13.1, 79.28], 12);
```

**Center**: Vellore, India (13.1°N, 79.28°E)

**Initial Zoom**: 12

**Tile Layers**:
- OSM Basemap: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`
- Parcel Overlay: `http://127.0.0.1:8000/tiles/{z}/{x}/{y}.png`

## Environment Variables

### Database URL

**Variable**: `DATABASE_URL`

**Usage**: Vector tile server (`backend/tile_server/tile_server_vector.py`)

**Format**: `postgresql://user:password@host:port/database`

**Example**: `postgresql://postgres:postgres@127.0.0.1:5432/parcels_db`

**Default**: Falls back to hardcoded connection string if not set

## Configuration Best Practices

### Security

1. **Database Credentials**: Move to environment variables
2. **CORS Origins**: Restrict to specific domains in production
3. **API Keys**: Use environment variables for any external services

### Development vs Production

**Current State**: Hardcoded values suitable for development

**Production Recommendations**:

1. Use environment variables for all sensitive data
2. Use configuration files (YAML/JSON) for non-sensitive settings
3. Separate configuration for different environments
4. Use secrets management for credentials

## Configuration Files Structure

Recommended structure for production:

```
parcel_mvp/
├── config/
│   ├── development.yaml
│   ├── production.yaml
│   └── .env.example
├── .env                    # Local environment variables (gitignored)
└── ...
```

## Example Environment File

Create `.env` file (not committed to git):

```bash
# Database
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/parcels_db
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=parcels_db
DB_USER=postgres
DB_PASSWORD=postgres

# API
API_HOST=127.0.0.1
API_PORT=8000

# Paths
SHAPEFILE_PATH=data/vellore/vellore_cad.shp
CACHE_DIR=backend/cache

# Tile Settings
TILE_SIZE=256
SIMPLIFY_TOLERANCE=0.00008
```

## Loading Environment Variables

Use `python-dotenv` package:

```python
from dotenv import load_dotenv
import os

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "parcels_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres")
}
```

## Configuration Summary

| Setting | Location | Current Value | Configurable |
|---------|----------|---------------|--------------|
| Database Host | Multiple | `127.0.0.1` | Yes (hardcoded) |
| Database Port | Multiple | `5432` | Yes (hardcoded) |
| Database Name | Multiple | `parcels_db` | Yes (hardcoded) |
| Database User | Multiple | `postgres` | Yes (hardcoded) |
| Database Password | Multiple | `postgres` | Yes (hardcoded) |
| Shapefile Path | ETL | `data/vellore/vellore_cad.shp` | Yes (hardcoded) |
| Cache Directory | Tile Server | `cache` | Yes (hardcoded) |
| Tile Size | Tile Generator | `256` | No (hardcoded) |
| Simplify Tolerance | ETL | `0.00008` | Yes (hardcoded) |
| CORS Origins | Main API | `["*"]` | Yes (hardcoded) |
| API Port | Server | `8000` | Yes (command line) |

## Related Documentation

- [SETUP.md](SETUP.md) - Initial setup instructions
- [DEVELOPMENT.md](DEVELOPMENT.md) - Development workflow
- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment

