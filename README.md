# Parcel MVP - Cadastral Parcel Data Pipeline

A complete ETL pipeline and web application for visualizing cadastral parcel data with interactive maps, tile generation, and parcel identification.

## Project Overview

This project provides:
- **ETL Pipeline**: Extract, transform, and load cadastral parcel data from shapefiles into PostgreSQL/PostGIS
- **Tile Server**: Generate and serve raster/vector map tiles for parcel visualization
- **Web Frontend**: Interactive map interface using Leaflet.js
- **Identify API**: Query parcel information by clicking on the map

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Database Setup](#database-setup)
- [ETL Pipeline](#etl-pipeline)
- [Backend Setup](#backend-setup)
- [Frontend Setup](#frontend-setup)
- [Running the Application](#running-the-application)
- [Verification](#verification)
- [Next Steps](#next-steps)
- [Documentation](#documentation)

## Prerequisites

Before starting, ensure you have:

1. **PostgreSQL 12+** with **PostGIS extension** installed
2. **Python 3.8+** with `pip` and `venv`
3. **Node.js** (optional, for frontend development)
4. **Git** (for cloning the repository)

### System Requirements

- **OS**: Linux (Ubuntu/WSL), macOS, or Windows with WSL
- **RAM**: Minimum 4GB (8GB+ recommended for large datasets)
- **Disk Space**: ~2GB for data and dependencies

## Quick Start (fresh setup)

1) Clone & install
```bash
git clone <repository-url>
cd parcel_mvp
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2) Ensure database is running and PostGIS enabled
```bash
sudo service postgresql start        # Linux
brew services start postgresql       # macOS
psql -U postgres -c "CREATE DATABASE parcels_db;"
psql -U postgres -d parcels_db -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

3) (Only if config is missing) Generate `etl/config/vellore_mapping.yaml`
Open `etl/explore_data.ipynb` and run the final “Generate Config Template” cell. It writes the config to `etl/config/vellore_mapping.yaml`. If the file already exists, skip this step.

4) Set database credentials (env vars or .env in repo root)
```bash
export DB_HOST=127.0.0.1
export DB_PORT=5432
export DB_NAME=parcels_db
export DB_USER=postgres
export DB_PASSWORD=postgres
```

5) (Optional) Pre-create schema without ETL
```bash
python setup_db.py
```
This creates the partitioned tables, functions, and triggers. You can skip this because the ETL will create them automatically.

6) Run ETL (creates schema if needed and loads data)
```bash
cd etl
python pipeline.py --config config/vellore_mapping.yaml 
```
If `etl/config/vellore_mapping.yaml` is missing, open `etl/explore_data.ipynb`, make necessary changes and run the final "Generate Config Template" cell; it writes the config to `etl/config/vellore_mapping.yaml`.


7) Start backend
```bash
cd ../backend
uvicorn main:app --reload
```
Backend: `http://localhost:8000`

8) Start frontend (new terminal)
```bash
cd frontend/map-app
python3 -m http.server 8080
```
Frontend: `http://localhost:8080`

9) Verify in browser
Open `http://localhost:8080` and confirm tiles and parcel labels load.

## Project Structure

```
parcel_mvp/
├── etl/                          # ETL Pipeline
│   ├── pipeline.py               # Main orchestrator
│   ├── config/
│   │   └── vellore_mapping.yaml # Field mappings and configuration
│   ├── modules/
│   │   ├── extract.py           # Data extraction
│   │   ├── transform.py         # Field mapping and transformations
│   │   ├── validate.py          # Data validation
│   │   ├── load.py              # Database loading
│   │   └── geometry_utils.py    # Geometry utilities
│   └── explore_data.ipynb        # Data exploration notebook
├── backend/                       # FastAPI Backend
│   ├── main.py                  # FastAPI application
│   ├── tile_server/             # Tile generation and serving
│   │   ├── tile_server_raster.py
│   │   ├── tile_server_vector.py
│   │   └── utils/
│   │       ├── generate_tile.py
│   │       └── cache_manager.py
│   ├── identify_api/            # Parcel identification API
│   │   └── utils/
│   │       ├── spatial_index.py
│   │       └── query_parcel.py
│   └── cache/                    # Tile cache (auto-generated)
├── frontend/                     # Web Frontend
│   └── map-app/
│       └── index.html           # Leaflet.js map interface
├── data/                         # Source data (shapefiles)
│   └── vellore/
│       └── vellore_cad.shp
├── docs/                         # Documentation
│   ├── ETL.md                   # ETL pipeline documentation
│   ├── DATABASE.md              # Database schema and setup
│   ├── ARCHITECTURE.md          # System architecture
│   ├── MIGRATION_GUIDE.md       # Migration from legacy ETL
│   └── CHANGELOG.md             # Project changelog
└── requirements.txt              # Python dependencies
```

## Database Setup

### Automatic Setup (Recommended)

The ETL pipeline automatically creates all required tables and partitions when you run it:

```bash
cd etl
python pipeline.py --config config/vellore_mapping.yaml
```

This will:
- Create `parcels_master` and `parcels_simplified` partitioned tables
- Set up auto-partitioning triggers
- Create spatial indexes (GIST) on all partitions
- Load data into the tables

### Standalone Database Setup

If you want to set up the database schema **without** running the ETL (useful for testing or manual setup):

```bash
# Set environment variables (or use .env file)
export DB_HOST=127.0.0.1
export DB_PORT=5432
export DB_NAME=parcels_db
export DB_USER=postgres
export DB_PASSWORD=postgres

# Run setup script
python setup_db.py
```

This creates:
- `parcels_master` and `parcels_simplified` partitioned tables
- Auto-partitioning functions (`create_master_partitions()`, `create_simplified_partitions()`)
- Triggers that automatically create partitions on insert
- Spatial indexes will be created automatically when partitions are created

**Note**: The ETL pipeline uses the same setup logic, so running `setup_db.py` is optional if you're running the ETL.

### Manual SQL Setup (Advanced)

If you need to manually create tables using SQL, see:
- `docs/DATABASE.md` for detailed schema
- `knowledge_docs/db_instructions.md` for SQL scripts
- `create_tables.sql` for reference SQL

### Database Configuration

Database credentials can be configured via **environment variables** (recommended) or CLI arguments.

**Using Environment Variables** (recommended):

Create a `.env` file in the project root:
```bash
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=parcels_db
DB_USER=postgres
DB_PASSWORD=postgres
```

Or export them:
```bash
export DB_HOST=127.0.0.1
export DB_PORT=5432
export DB_NAME=parcels_db
export DB_USER=postgres
export DB_PASSWORD=postgres
```

**Using CLI Arguments** (overrides environment variables):

```bash
python pipeline.py \
  --config config/vellore_mapping.yaml \
  --db-host localhost \
  --db-port 5432 \
  --db-name parcels_db \
  --db-user postgres \
  --db-password your_password
```

**Default values** (if neither env vars nor CLI args provided):
- Host: `127.0.0.1`
- Port: `5432`
- Database: `parcels_db`
- User: `postgres`
- Password: `postgres`

## ETL Pipeline

### Overview

The ETL pipeline follows a modular architecture:

1. **Extract**: Load shapefile and inspect schema
2. **Transform**: Map fields, clean geometries, compute label points
3. **Validate**: Check data quality and required fields
4. **Load**: Batch insert into partitioned tables

### Running the ETL

```bash
cd etl
python pipeline.py --config config/vellore_mapping.yaml
```

If `etl/config/vellore_mapping.yaml` is missing, open `etl/explore_data.ipynb` and run the final "Generate Config Template" cell; it writes the config to `etl/config/vellore_mapping.yaml`.

### Configuration

Edit `etl/config/vellore_mapping.yaml` to customize:
- Field mappings (source → target columns)
- Transformations (string conversion, constants, etc.)
- Required fields for validation
- Geometry settings (CRS, label point computation)

If the config file is missing, open `etl/explore_data.ipynb` and run the final “Generate Config Template” cell; it writes `etl/config/vellore_mapping.yaml`.

### ETL Output

- **parcels_master**: Full parcel data with all attributes
- **parcels_simplified**: Simplified subset for tile generation (same geometry, fewer columns)

Both tables are partitioned by `state_code` and `district_code` for performance.

### Troubleshooting ETL

**Common Issues**:

1. **Database Connection Error**
 ```bash
   # Check PostgreSQL is running
   sudo service postgresql status
   
   # Verify database exists
   psql -U postgres -l | grep parcels_db
   ```

2. **PostGIS Not Found**
   ```sql
   psql -U postgres -d parcels_db -c "CREATE EXTENSION IF NOT EXISTS postgis;"
   ```

3. **Shapefile Not Found**
 ```bash
   # Verify shapefile exists
   ls -la data/vellore/vellore_cad.shp
   ```

4. **Partition Creation Errors**
   - The ETL automatically handles partition creation
   - If errors occur, check PostgreSQL logs: `tail -f /var/log/postgresql/postgresql-*.log`

For more details, see `docs/ETL.md`.

## Backend Setup

### Installation

```bash
cd backend
# Dependencies should already be installed from root requirements.txt
```

### Configuration

Backend database configuration uses **environment variables** (recommended) with sensible defaults.

**Environment Variables**:
```bash
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=parcels_db
DB_USER=postgres
DB_PASSWORD=postgres
```

**Files that use these variables**:
- `backend/tile_server/utils/generate_tile.py` (raster tiles)
- `backend/tile_server/tile_server_vector.py` (vector tiles - uses `DATABASE_URL`)
- `backend/identify_api/utils/spatial_index.py` (identify API)

**Default values** (if environment variables not set):
- Host: `127.0.0.1`
- Port: `5432`
- Database: `parcels_db`
- User: `postgres`
- Password: `postgres`

### Running the Backend

```bash
cd backend
uvicorn main:app --reload
```

**Endpoints**:
- `http://localhost:8000/tiles/{z}/{x}/{y}.png` - Raster tiles (zoom 15-18)
- `http://localhost:8000/tiles/{z}/{x}/{y}.pbf` - Vector tiles
- `http://localhost:8000/api/identify?lat={lat}&lon={lon}` - Identify parcel
- `http://localhost:8000/health` - Health check

### Clearing Tile Cache

After running a new ETL or updating data, clear the tile cache:

```bash
# Remove all cached tiles
rm -rf backend/cache/*

# Or remove specific zoom levels
rm -rf backend/cache/15/*
rm -rf backend/cache/16/*
rm -rf backend/cache/17/*
rm -rf backend/cache/18/*
```

**Note**: Tiles will be regenerated on-demand when requested.

### Backend Components

1. **Raster Tile Server**: Generates PNG tiles with parcel boundaries and labels
2. **Vector Tile Server**: Serves MVT (Mapbox Vector Tiles) for client-side rendering
3. **Identify API**: Returns parcel information for clicked coordinates
4. **Cache Manager**: Stores generated tiles in `backend/cache/` for performance

## Frontend Setup

### Running the Frontend

```bash
cd frontend/map-app
python3 -m http.server 8080
```

Or use any static file server:
```bash
# Using Node.js http-server
npx http-server -p 8080

# Using Python
python -m http.server 8080
```

### Frontend Configuration

Edit `frontend/map-app/index.html` to customize:
- Backend API URL (default: `http://localhost:8000`)
- Map center coordinates
- Default zoom level
- Tile layer settings

### Features

- **Interactive Map**: Pan and zoom with Leaflet.js
- **Parcel Overlay**: Raster tiles showing parcel boundaries and survey numbers
- **Click to Identify**: Click on a parcel to get detailed information
- **Responsive Design**: Works on desktop and mobile devices

## 🎮 Running the Application

### Complete Workflow

1. **Start PostgreSQL**
   ```bash
   sudo service postgresql start
   ```

2. **Run ETL** (if not already done)
   ```bash
   cd etl
   python pipeline.py --config config/vellore_mapping.yaml
   ```

3. **Clear Old Tile Cache** (if updating data)
   ```bash
   rm -rf backend/cache/*
   ```

4. **Start Backend**
   ```bash
   cd backend
   uvicorn main:app --reload
   ```

5. **Start Frontend** (in a new terminal)
   ```bash
   cd frontend/map-app
   python3 -m http.server 8080
   ```

6. **Open Browser**
   ```
   http://localhost:8080
   ```

### Development Mode

For development with auto-reload:

```bash
# Backend (auto-reloads on code changes)
cd backend
uvicorn main:app --reload

# Frontend (if using a dev server)
cd frontend/map-app
# Edit index.html and refresh browser
```

## Verification

### Verify ETL Success

```sql
-- Connect to database
psql -U postgres -d parcels_db

-- Check row counts
SELECT COUNT(*) FROM parcels_master;
SELECT COUNT(*) FROM parcels_simplified;

-- Check partitions
SELECT schemaname, tablename 
FROM pg_tables 
WHERE tablename LIKE 'parcels_%' 
ORDER BY tablename;

-- Verify data
SELECT state_code, district_code, COUNT(*) 
FROM parcels_master 
GROUP BY state_code, district_code;
```

**Expected**: ~160,004 rows in both tables.

### Verify Backend

```bash
# Health check
curl http://localhost:8000/health

# Test tile generation
curl http://localhost:8000/tiles/15/23577/1896.png -o test_tile.png

# Test identify API
curl "http://localhost:8000/api/identify?lat=12.9&lon=79.1"
```

### Verify Frontend

1. Open `http://localhost:8080` in browser
2. Map should load with parcel boundaries visible
3. Zoom to level 15-18 to see parcel details
4. Click on a parcel to see identify information

## 🔜 Next Steps

### Immediate Tasks

1. **Clear Tile Cache**: Remove old tiles from `backend/cache/` to force regeneration with new data
   ```bash
   rm -rf backend/cache/*
   ```

2. **Test End-to-End**: Verify the complete workflow:
   - ETL loads data correctly
   - Backend serves tiles
   - Frontend displays parcels
   - Identify API returns correct information

3. **Update Identify API**: Currently loads from shapefile; should be updated to use database
   - File: `backend/identify_api/utils/spatial_index.py`
   - Should query `parcels_master` instead of shapefile

### Future Enhancements

1. **Performance Optimization**:
   - Add connection pooling for database
   - Implement tile pre-generation for common zoom levels
   - Add CDN for tile caching

2. **Features**:
   - Search parcels by survey number
   - Export parcel data
   - Print/export map views
   - Multi-dataset support

3. **Infrastructure**:
   - Docker containerization
   - CI/CD pipeline
   - Production deployment guide

## 📚 Documentation

Comprehensive documentation is available in the `docs/` folder:

- **[ETL.md](docs/ETL.md)**: Detailed ETL pipeline documentation
- **[DATABASE.md](docs/DATABASE.md)**: Database schema and setup
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)**: System architecture overview
- **[MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md)**: Migration from legacy ETL
- **[CHANGELOG.md](docs/CHANGELOG.md)**: Project changelog

## Troubleshooting

### Common Issues

1. **Port Already in Use**
   ```bash
   # Find process using port 8000
   lsof -i :8000
   # Kill process
   kill -9 <PID>
   ```

2. **Database Connection Refused**
   ```bash
   # Check PostgreSQL is running
   sudo service postgresql status
   # Check connection
   psql -U postgres -d parcels_db -c "SELECT 1;"
   ```

3. **Tiles Not Loading**
   - Clear browser cache
   - Check backend logs for errors
   - Verify tile cache directory exists: `ls -la backend/cache/`

4. **ETL Fails with Partition Errors**
   - Drop and recreate tables (see `docs/DATABASE.md`)
   - Check PostgreSQL version (requires 12+)
   - Verify PostGIS extension is enabled

### Getting Help

- Check documentation in `docs/` folder
- Review error logs in terminal output
- Check PostgreSQL logs: `/var/log/postgresql/postgresql-*.log`

## License

[Add your license information here]

## Contributors

[Add contributor information here]

---

**Last Updated**: 2025-12-13
**Status**: ETL Pipeline Complete | Backend Ready | Frontend Ready
