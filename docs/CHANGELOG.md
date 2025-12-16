# Changelog

Central log of notable changes to the Parcel MVP codebase and docs.

## 2025-12-13 (Current)
- **✅ ETL Pipeline Successfully Completed**: Modular ETL pipeline fully operational
  - Successfully processed 160,631 source rows
  - Loaded 160,004 valid parcels into `parcels_master` table
  - Loaded 160,004 parcels into `parcels_simplified` table (matched by position, using parcel_uuid as foreign key)
  - Fixed duplicate key issues by matching simplified rows to master rows by position instead of survey_num
  - All partitions created successfully (TN state, VELLORE district)
  - Pre-computed `label_point` stored in database for all parcels
- **Database Schema**: Partitioned tables with composite primary keys `(state_code, district_code, parcel_uuid)`
  - Auto-partitioning by state and district with triggers
  - GIST spatial indexes on all partition tables
  - `parcel_uuid` acts as foreign key from `parcels_master` to `parcels_simplified`
- **Backend Updates**: All backend components now use database as source of truth
  - **Raster Tile Server**: Uses `parcels_simplified` and pre-computed `label_point` ✅
  - **Vector Tile Server**: Uses `parcels_simplified` table ✅
  - **Identify API**: Updated to load from `parcels_master` database table instead of shapefile ✅
    - Fixed geometry access issues in `identify_server.py`
    - Now uses cleaned/processed data from ETL pipeline
    - Consistent with tile generation data source
    - Database is now the single source of truth for all backend services
- **Tile Rendering Quality Improvements**: Enhanced border rendering for smoother lines
  - Implemented 2x supersampling (render at 512x512, scale down to 256x256)
  - Uses Lanczos resampling for high-quality anti-aliasing
  - Eliminates pixelation and staggered appearance of parcel borders
  - Font scaling adjusted for high-resolution rendering
  - File: `backend/tile_server/utils/generate_tile.py`
- **Environment Variables for Database Credentials**: Security improvement
  - All database connections now use environment variables (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`)
  - Updated files: `backend/tile_server/utils/generate_tile.py`, `backend/identify_api/utils/spatial_index.py`, `etl/pipeline.py`
  - Uses `python-dotenv` to load `.env` files automatically
  - No fallback defaults - environment variables are required (enforces proper configuration)
  - `.env` and `.env.local` files added to `.gitignore` for security
  - Documentation updated with environment variable usage
- **End-to-End Testing**: Successfully tested complete workflow
  - ETL → Database → Tile Generation → Frontend display ✅
  - Identify API working with database-sourced data ✅

## 2025-12-12
- **ETL Pipeline Implementation**: Successfully implemented and tested modular ETL pipeline
  - Processed 160,000+ parcels with geometry cleaning and label point computation
  - Added validation to filter out rows with null required fields (627 parcels filtered out)
  - ETL now loads data into partitioned tables `parcels_master` and `parcels_simplified`
- **Geometry Simplification Removed**: Disabled geometry simplification for `parcels_simplified` table
  - Both `parcels_master` and `parcels_simplified` now contain original geometry (not simplified)
  - Preserves full geometry precision for tile generation and analysis
  - Simplified ETL process by removing unnecessary simplification step
- **Updated Documentation**: Reflected geometry simplification removal in DATABASE.md and config files

## 2025-01-XX (Previous)
- **New Modular ETL Pipeline**: Implemented industry-standard ETL architecture with configurable field mappings
  - Created `etl/modules/` with separate extract, transform, validate, and load modules
  - Added `etl/pipeline.py` orchestrator with CLI interface
  - Implemented YAML-based configuration system (`etl/config/vellore_mapping.yaml`)
  - Moved `label_point` computation from tile generation to ETL (pre-computed and stored)
  - Geometry utilities separated into `geometry_utils.py` (low-level) and `transform.py` (high-level wrappers)
  - New ETL targets partitioned tables `parcels_master` and `parcels_simplified`
  - Database auto-generates `parcel_uuid` (DEFAULT gen_random_uuid())
  - Added data exploration notebook (`etl/explore_data.ipynb`) for interactive data analysis
- **Documentation**: Updated ETL.md, DATABASE.md, and created NEXT_STEPS.md guide
- **Migration Note**: Legacy ETL (`etl/load_vellore.py`) still exists but is deprecated. Tile generation still uses legacy tables; migration to new tables pending.

## 2025-12-10
- Enforced tile serving only for zoom levels 15–18 in raster tile endpoint (`backend/tile_server/tile_server_raster.py`).
- Updated frontend Leaflet layer to request tiles only for zoom 15–18 (`frontend/map-app/index.html`).
- Documentation updates to reflect zoom constraints (`docs/TILES.md`, `docs/API.md`).
- Created partitioned parent tables `parcels_master` and `parcels_simplified` in PostgreSQL with triggers to auto-create state/district partitions and per-partition indexes (GIST on geom, composite on state_code/district_code). Pending: data migration/new ETL to load these tables.


