# Setup Guide

## Overview

This guide covers the complete setup process for the Parcel MVP project, including system requirements, dependencies, database setup, and initial data loading.

## System Requirements

### Operating System
- Linux (Ubuntu/Debian recommended)
- macOS
- Windows (with WSL recommended)

### Software Requirements
- Python 3.12 or higher
- PostgreSQL 12 or higher
- PostGIS 3.0 or higher
- pip (Python package manager)

## Step 1: Clone/Download Project

```bash
# If using git
git clone <repository-url>
cd parcel_mvp

# Or navigate to project directory
cd parcel_mvp
```

## Step 2: Install PostgreSQL and PostGIS

### Ubuntu/Debian

```bash
# Install PostgreSQL
sudo apt update
sudo apt install postgresql postgresql-contrib

# Install PostGIS
sudo apt install postgis postgresql-12-postgis-3

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### macOS

```bash
# Using Homebrew
brew install postgresql
brew install postgis
brew services start postgresql
```

### Windows

Download and install from:
- PostgreSQL: https://www.postgresql.org/download/windows/
- PostGIS: https://postgis.net/windows_downloads/

## Step 3: Create Database

```bash
# Switch to postgres user
sudo -u postgres psql

# Or on macOS/Windows, use psql directly
psql -U postgres
```

In PostgreSQL prompt:

```sql
-- Create database
CREATE DATABASE parcels_db;

-- Connect to database
\c parcels_db

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- Verify PostGIS installation
SELECT PostGIS_version();

-- Exit
\q
```

## Step 4: Set Up Python Environment

### Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### Install Dependencies

```bash
# Install from requirements.txt
pip install -r requirements.txt
```

**Key Dependencies**:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `geopandas` - Spatial data manipulation
- `shapely` - Geometric operations
- `rasterio` - Raster processing
- `psycopg2-binary` - PostgreSQL adapter
- `pillow` - Image processing
- `numpy` - Numerical operations

## Step 5: Verify Data Files

Ensure shapefile exists:

```bash
ls -la data/vellore/vellore_cad.shp
```

Required shapefile components:
- `vellore_cad.shp` - Geometry data
- `vellore_cad.shx` - Index file
- `vellore_cad.dbf` - Attribute data
- `vellore_cad.prj` - Projection information

## Step 6: Configure Database Connection

Edit `etl/load_vellore.py` if needed (lines 10-16):

```python
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "parcels_db",
    "user": "postgres",
    "password": "postgres"  # Change if different
}
```

**Note**: For production, use environment variables (see [CONFIG.md](CONFIG.md)).

## Step 7: Run ETL Pipeline

Load data into database:

```bash
# Ensure virtual environment is activated
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows

# Run ETL
python etl/load_vellore.py
```

Expected output:
```
🚀 Loading Vellore shapefile...
✅ Shapefile loaded: <count> rows
🧼 Cleaning geometry...
✅ Valid geometries: <count>
🔑 Generated UUIDs for parcels
📥 Inserting into parcels_raw...
✅ parcels_raw inserted
📥 Inserting into parcels...
✅ parcels inserted
🌀 Generating simplified geometries...
✅ parcels_simplified inserted
🎉 ETL COMPLETE — Vellore data loaded successfully ✅
```

## Step 8: Verify Database Setup

```bash
psql -U postgres -d parcels_db
```

```sql
-- Check tables exist
\dt

-- Check row counts
SELECT 'parcels_raw' as table_name, COUNT(*) FROM parcels_raw
UNION ALL
SELECT 'parcels', COUNT(*) FROM parcels
UNION ALL
SELECT 'parcels_simplified', COUNT(*) FROM parcels_simplified;

-- Check PostGIS functions
SELECT ST_AsText(ST_Centroid(geom)) FROM parcels LIMIT 1;

-- Exit
\q
```

## Step 9: Start Backend Server

```bash
# Navigate to backend directory
cd backend

# Start FastAPI server
uvicorn main:app --reload

# Or using Python module syntax
python -m uvicorn main:app --reload
```

Server will start at: `http://127.0.0.1:8000`

**API Documentation**: `http://127.0.0.1:8000/docs` (FastAPI auto-generated)

## Step 10: Open Frontend

### Option 1: Direct File Open

Open `frontend/map-app/index.html` in a web browser.

### Option 2: Local Web Server

```bash
# Using Python HTTP server
cd frontend/map-app
python3 -m http.server 8080

# Open in browser
# http://127.0.0.1:8080
```

**Note**: Frontend expects backend at `http://127.0.0.1:8000`

## Verification Checklist

- [ ] PostgreSQL installed and running
- [ ] PostGIS extension enabled
- [ ] Database `parcels_db` created
- [ ] Python virtual environment created and activated
- [ ] Dependencies installed from `requirements.txt`
- [ ] Shapefile data present in `data/vellore/`
- [ ] ETL pipeline completed successfully
- [ ] Database tables populated
- [ ] Backend server running on port 8000
- [ ] Frontend accessible in browser
- [ ] Map displays with parcel tiles
- [ ] Click-to-identify functionality works

## Troubleshooting

### PostgreSQL Connection Issues

**Error**: `psycopg2.OperationalError: could not connect to server`

**Solutions**:
- Verify PostgreSQL is running: `sudo systemctl status postgresql`
- Check connection settings in `DB_CONFIG`
- Verify database exists: `psql -U postgres -l`
- Check PostgreSQL is listening: `sudo netstat -tlnp | grep 5432`

### PostGIS Extension Error

**Error**: `extension "postgis" does not exist`

**Solutions**:
- Install PostGIS: `sudo apt install postgresql-12-postgis-3`
- Enable extension: `CREATE EXTENSION postgis;`
- Verify: `SELECT PostGIS_version();`

### Shapefile Not Found

**Error**: `FileNotFoundError: data/vellore/vellore_cad.shp`

**Solutions**:
- Verify file path is correct
- Check all shapefile components exist (.shp, .shx, .dbf, .prj)
- Run ETL from project root directory

### Import Errors

**Error**: `ModuleNotFoundError: No module named 'fastapi'`

**Solutions**:
- Activate virtual environment: `source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`
- Verify installation: `pip list | grep fastapi`

### Port Already in Use

**Error**: `Address already in use`

**Solutions**:
- Change port: `uvicorn main:app --port 8001`
- Kill existing process: `lsof -ti:8000 | xargs kill`
- Use different port in frontend configuration

## Next Steps

After setup:
1. Review [DEVELOPMENT.md](DEVELOPMENT.md) for development workflow
2. Check [CONFIG.md](CONFIG.md) for configuration options
3. Read [ARCHITECTURE.md](ARCHITECTURE.md) for system overview
4. Explore [API.md](API.md) for API usage

## Related Documentation

- [CONFIG.md](CONFIG.md) - Configuration details
- [ETL.md](ETL.md) - ETL pipeline details
- [DATABASE.md](DATABASE.md) - Database schema
- [DEVELOPMENT.md](DEVELOPMENT.md) - Development guide

