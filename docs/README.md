# Parcel MVP - Project Documentation

## Overview

Parcel MVP is a web-based mapping application for displaying and querying cadastral (land parcel) data for Vellore, India. The system provides an interactive map interface where users can view parcel boundaries and click on parcels to retrieve detailed information.

## Quick Start

1. **Setup Environment**: See [SETUP.md](SETUP.md) for installation instructions
2. **Load Data**: Run the ETL pipeline (see [ETL.md](ETL.md))
3. **Start Backend**: `cd backend && uvicorn main:app --reload`
4. **Open Frontend**: Open `frontend/map-app/index.html` in a browser

## Project Structure

```
parcel_mvp/
├── backend/                 # FastAPI backend application
│   ├── main.py             # Main FastAPI app with routers
│   ├── identify_api/       # Parcel identification API
│   │   ├── identify_server.py
│   │   └── utils/
│   │       ├── query_parcel.py    # Point-in-polygon queries
│   │       └── spatial_index.py   # In-memory spatial index
│   ├── tile_server/        # Map tile generation
│   │   ├── tile_server_raster.py  # Raster PNG tiles
│   │   ├── tile_server_vector.py  # Vector MVT tiles (alternative)
│   │   └── utils/
│   │       ├── generate_tile.py   # Tile generation logic
│   │       ├── cache_manager.py   # Tile caching
│   │       └── tile_utils.py      # Coordinate transformations
│   └── cache/              # Generated tile cache (z/x/y.png structure)
├── frontend/
│   └── map-app/
│       └── index.html      # Leaflet.js map interface
├── data/
│   └── vellore/            # Vellore cadastral shapefile
│       └── vellore_cad.shp
├── etl/
│   └── load_vellore.py     # ETL pipeline for loading data
├── docs/                   # Project documentation
├── requirements.txt        # Python dependencies
└── venv/                   # Python virtual environment
```

## Key Components

### Backend (FastAPI)
- **Main API** (`backend/main.py`): FastAPI application with CORS middleware
- **Tile Server**: Generates and serves raster PNG tiles for map display
- **Identify API**: Returns parcel information for clicked coordinates

### Frontend
- **Map Interface**: Leaflet.js-based interactive map
- **Click Handler**: Queries backend API for parcel details

### Database (PostgreSQL + PostGIS)
- **parcels_raw**: Complete original data with all attributes
- **parcels**: Cleaned subset with essential attributes
- **parcels_simplified**: Original geometries (not simplified) for tile generation

## Documentation Index

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and design
- **[API.md](API.md)** - API endpoints and usage
- **[DATABASE.md](DATABASE.md)** - Database schema and setup
- **[ETL.md](ETL.md)** - Data loading pipeline
- **[SETUP.md](SETUP.md)** - Installation and environment setup
- **[CONFIG.md](CONFIG.md)** - Configuration files and settings
- **[DEVELOPMENT.md](DEVELOPMENT.md)** - Development workflow
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Deployment instructions
- **[DATA.md](DATA.md)** - Data dictionary and field descriptions
- **[TILES.md](TILES.md)** - Tile generation and caching
- **[SPATIAL_QUERIES.md](SPATIAL_QUERIES.md)** - Spatial indexing and queries

## Technology Stack

- **Backend**: FastAPI, Python 3.12
- **Spatial Libraries**: GeoPandas, Shapely, Rasterio, PostGIS
- **Database**: PostgreSQL with PostGIS extension
- **Frontend**: Leaflet.js, HTML/JavaScript
- **Image Processing**: PIL/Pillow, NumPy

## Features

- Interactive map with parcel boundaries
- Click-to-identify parcel information
- Raster tile generation with survey number labels
- Tile caching for performance
- Spatial indexing for fast queries
- Original geometry precision (no simplification) for accurate rendering

## Data Source

Vellore cadastral shapefile containing land parcel boundaries with attributes including:
- Survey numbers
- Village names and codes
- District and tehsil information
- Administrative boundaries

## Getting Help

For detailed information on any aspect of the project, refer to the specific documentation files listed above. Each document provides comprehensive coverage of its topic with code examples and references to actual implementation files.

