# Database Documentation

## Overview

The Parcel MVP uses PostgreSQL with the PostGIS extension to store cadastral parcel data. The database contains three main tables optimized for different use cases.

## Database Configuration

**Database Name**: `parcels_db`

**Connection Details** (from `etl/load_vellore.py`):
```python
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "parcels_db",
    "user": "postgres",
    "password": "postgres"
}
```

**Connection String**: `postgresql://postgres:postgres@127.0.0.1:5432/parcels_db`

## PostGIS Setup

PostGIS extension must be enabled:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

This enables spatial data types and functions used throughout the application.

## Database Schema Setup

### Automatic Setup (Recommended)

The ETL pipeline automatically creates all required tables, functions, and triggers when you run it:

```bash
cd etl
python pipeline.py --config config/vellore_mapping.yaml
```

### Standalone Setup Script

If you want to set up the database schema **without** running the ETL, use the standalone setup script:

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

This script creates:
- `parcels_master` and `parcels_simplified` partitioned tables
- Auto-partitioning functions (`create_master_partitions()`, `create_simplified_partitions()`)
- Triggers that automatically create partitions on insert
- Spatial indexes (created automatically when partitions are created)

**Note**: The ETL pipeline uses the same setup logic, so running `setup_db.py` is optional if you're running the ETL.

### Manual SQL Setup

If you prefer to use SQL directly, see `create_tables.sql` for the complete SQL script.

## Schema

### Table: parcels_raw

**Purpose**: Complete original data with all shapefile attributes. Used for detailed parcel information queries.

**Columns**:

| Column | Type | Description |
|--------|------|-------------|
| `parcel_uuid` | UUID | Unique identifier for each parcel (generated during ETL) |
| `geom` | Geometry(MultiPolygon, 4326) | Parcel boundary geometry in EPSG:4326 |
| `kide` | VARCHAR | KIDE identifier (from shapefile) |
| `kide_1` | VARCHAR | KIDE identifier variant 1 |
| `kide_2` | VARCHAR | KIDE identifier variant 2 |
| `survey_num` | VARCHAR | Survey number of the parcel |
| `gp_name` | VARCHAR | Gram Panchayat name |
| `v_name` | VARCHAR | Village name |
| `v_code` | VARCHAR | Village code |
| `district` | VARCHAR | District name |
| `state` | VARCHAR | State name |
| `tehsil` | VARCHAR | Tehsil (administrative division) name |

**Geometry**: MultiPolygon in EPSG:4326 (WGS84)

**Indexes**: 
- Spatial GIST index on `geom` (automatic with PostGIS)
- Index on `parcel_uuid` (primary key)

**Usage**: 
- Detailed parcel information queries
- Used by `/parcel-info` endpoint in vector tile server
- Source of truth for all parcel attributes

**ETL Source**: `etl/load_vellore.py` lines 67-92

---

### Table: parcels

**Purpose**: Cleaned subset with essential attributes. Used for general queries.

**Columns**:

| Column | Type | Description |
|--------|------|-------------|
| `parcel_uuid` | UUID | Unique identifier (matches parcels_raw) |
| `geom` | Geometry(MultiPolygon, 4326) | Parcel boundary geometry in EPSG:4326 |
| `district` | VARCHAR | District name |
| `tehsil` | VARCHAR | Tehsil name |
| `v_name` | VARCHAR | Village name |
| `survey_num` | VARCHAR | Survey number |

**Geometry**: MultiPolygon in EPSG:4326 (WGS84)

**Indexes**: 
- Spatial GIST index on `geom`
- Index on `parcel_uuid`

**Usage**: 
- General parcel queries
- Simplified attribute set for common operations

**ETL Source**: `etl/load_vellore.py` lines 97-115

---

### New partitioned tables (ready for use)

Partitioned replacements are now created to support larger datasets and per-state/district sharding. The new modular ETL pipeline (`etl/pipeline.py`) is ready to load data into these tables.

#### Table: parcels_master (partitioned)
- **Partitioning**: LIST by `state_code`, sub-partition LIST by `district_code`
- **Columns**: `parcel_uuid` (UUID, DB-generated), `geom` (MultiPolygon 4326), `label_point` (Point 4326), `state`, `state_code`, `district_code`, `district_name`, `sub_district_name`, `village_name`, `survey_num`, `created_at`
- **PK**: (`state_code`, `district_code`, `parcel_uuid`) - includes all partition keys
- **Indexes per partition**: GIST on `geom`; btree on (`state_code`, `district_code`)
- **Creation**: Trigger `trg_create_master_partitions` auto-creates state partitions (each further partitioned by district) and indexes.

#### Table: parcels_simplified (partitioned)
- **Partitioning**: LIST by `state_code`, sub-partition LIST by `district_code`
- **Columns**: `parcel_uuid` (UUID, matches master), `geom` (MultiPolygon 4326, **original geometry - NOT simplified**), `label_point` (Point 4326), `state_code`, `district_code`, `survey_num`
- **PK**: (`state_code`, `district_code`, `parcel_uuid`) - includes all partition keys
- **Indexes per partition**: GIST on `geom`; btree on (`state_code`, `district_code`)
- **Creation**: Trigger `trg_create_simplified_partitions` auto-creates state partitions (each further partitioned by district) and indexes.
- **Note**: Despite the name "simplified", this table contains the **original geometry** (same as `parcels_master`). Geometry simplification has been disabled to preserve precision. This table is used for tile generation.

> Note: The legacy non-partitioned tables (`parcels`, `parcels_raw`, old `parcels_simplified`) remain for now; the new ETL will target the partitioned tables.

---

## Table Relationships

All three tables share the same `parcel_uuid` as the primary identifier:

```
parcels_raw (parcel_uuid) ←→ parcels (parcel_uuid) ←→ parcels_simplified (parcel_uuid)
```

The UUID is generated once during ETL and used consistently across all tables.

## Spatial Indexes

PostGIS automatically creates GIST (Generalized Search Tree) indexes on geometry columns. These indexes enable fast spatial queries:

- **Bounding box queries**: `geom && ST_MakeEnvelope(...)`
- **Intersection queries**: `ST_Intersects(geom, ...)`
- **Point-in-polygon queries**: `ST_Contains(geom, point)`

## Common Queries

### Tile Generation Query

Used in `backend/tile_server/utils/generate_tile.py`:

```sql
SELECT parcel_uuid,
       survey_num,
       ST_AsEWKB(geom),
       ST_AsEWKB(ST_PointOnSurface(geom)) AS label_point
FROM parcels_simplified
WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
  AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326));
```

This query:
1. Uses bounding box operator (`&&`) for fast index-based filtering
2. Uses `ST_Intersects` for precise geometry check
3. Returns geometries as EWKB (Extended Well-Known Binary)
4. Includes label point for text rendering

### Vector Tile Query

Used in `backend/tile_server/tile_server_vector.py`:

```sql
WITH
bounds AS (
    SELECT ST_MakeEnvelope($1, $2, $3, $4, 4326) AS geom
),
mvtgeom AS (
    SELECT
    parcels_simplified.parcel_uuid::text,
    parcels_simplified.survey_num::text,
    ST_AsMVTGeom(
        parcels_simplified.geom,
        bounds.geom,
        4096,
        64,
        TRUE
    ) AS geom
    FROM parcels_simplified
    JOIN bounds
    ON ST_Intersects(parcels_simplified.geom, bounds.geom)
)
SELECT ST_AsMVT(mvtgeom, 'parcels', 4096, 'geom')
FROM mvtgeom;
```

This query:
1. Creates tile bounding box
2. Transforms geometries to tile coordinates using `ST_AsMVTGeom`
3. Generates Mapbox Vector Tile (MVT) format
4. Uses tile extent of 4096 and buffer of 64 pixels

### Parcel Info Query

Used in `backend/tile_server/tile_server_vector.py`:

```sql
SELECT parcel_uuid::text, survey_num, gp_name, v_name, v_code, 
       district, state, tehsil,
       ST_AsText(ST_Centroid(geom)) AS centroid_wkt
FROM parcels_raw
WHERE parcel_uuid::text = $1
LIMIT 1;
```

## Geometry Cleaning

During ETL (`etl/load_vellore.py`), geometries are cleaned:

1. **Invalid geometry fix**: `g.buffer(0)` for invalid geometries
2. **Type normalization**: Convert Polygon to MultiPolygon
3. **Null filtering**: Remove parcels with null geometries

Function: `clean_geom()` in `etl/load_vellore.py` lines 21-31

## Coordinate System

All geometries are stored in **EPSG:4326** (WGS84):
- Latitude/Longitude in decimal degrees
- Standard for web mapping applications
- Compatible with Leaflet.js and most mapping libraries

## Database Initialization

To set up the database:

1. Create database:
```sql
CREATE DATABASE parcels_db;
```

2. Connect to database and enable PostGIS:
```sql
\c parcels_db
CREATE EXTENSION IF NOT EXISTS postgis;
```

3. Run ETL pipeline:
```bash
python etl/load_vellore.py
```

The ETL script will create tables and insert data.

## Performance Considerations

1. **Spatial Indexes**: Automatic GIST indexes on geometry columns
2. **Simplified Geometries**: Reduced complexity for faster queries
3. **Separate Tables**: Optimized for different use cases
4. **Bounding Box Queries**: Use `&&` operator for fast filtering before precise checks

## Backup and Maintenance

- Regular backups of `parcels_db` database
- Monitor spatial index performance with `EXPLAIN ANALYZE`
- Consider VACUUM ANALYZE after bulk inserts

## Related Documentation

- [ETL.md](ETL.md) - Data loading process
- [SPATIAL_QUERIES.md](SPATIAL_QUERIES.md) - Spatial query patterns
- [CONFIG.md](CONFIG.md) - Database configuration

