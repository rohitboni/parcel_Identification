# Spatial Queries Documentation

## Overview

This document describes the spatial indexing strategies, query patterns, and performance optimizations used in the Parcel MVP for spatial operations.

## Spatial Indexing Strategies

### 1. In-Memory Spatial Index (Identify API)

**Location**: `backend/identify_api/utils/spatial_index.py`

**Type**: R-tree spatial index (GeoPandas)

**Purpose**: Fast point-in-polygon queries for parcel identification

**Implementation**:
```python
import geopandas as gpd

# Load parcels into GeoDataFrame
parcels = gpd.read_file(SHAPEFILE_PATH).to_crs("EPSG:4326")

# Build spatial index
sindex = parcels.sindex
```

**Characteristics**:
- Built at application startup
- Stored in memory
- Fast candidate selection
- Two-stage query process

**Memory Usage**: Depends on number of parcels and geometry complexity

### 2. Database Spatial Index (PostGIS)

**Type**: GIST (Generalized Search Tree) index

**Purpose**: Fast spatial queries in database

**Creation**: Automatic with PostGIS geometry columns

**Usage**: All spatial queries on geometry columns

**Index Type**: R-tree variant optimized for spatial data

## Query Patterns

### Pattern 1: Point-in-Polygon (Identify API)

**Use Case**: Find parcel containing a given point

**Location**: `backend/identify_api/utils/query_parcel.py`

**Two-Stage Process**:

**Stage 1: Spatial Index Filter**
```python
pt = Point(lon, lat)
candidate_indices = list(sindex.intersection(pt.bounds))
```

- Uses R-tree index to find candidate parcels
- Fast bounding box intersection
- Returns indices of potential matches

**Stage 2: Precise Geometry Check**
```python
candidates = parcels.iloc[candidate_indices]
inside = candidates[candidates.geometry.contains(pt)]
```

- Performs exact point-in-polygon test
- Filters to actual matches
- Returns first matching parcel

**Performance**:
- Stage 1: O(log n) with spatial index
- Stage 2: O(k) where k = number of candidates
- Total: Much faster than checking all parcels

### Pattern 2: Bounding Box Query (Tile Generation)

**Use Case**: Find all parcels intersecting a tile bounding box

**Location**: `backend/tile_server/utils/generate_tile.py`

**Query**:
```sql
SELECT parcel_uuid, survey_num, ST_AsEWKB(geom), 
       ST_AsEWKB(ST_PointOnSurface(geom)) AS label_point
FROM parcels_simplified
WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
  AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326));
```

**Optimization Strategy**:

1. **Bounding Box Operator (`&&`)**:
   - Fast index-based filtering
   - Uses GIST spatial index
   - Returns all geometries whose bounding box intersects

2. **Precise Intersection (`ST_Intersects`)**:
   - Exact geometry check
   - Filters false positives from bounding box
   - More expensive but necessary for accuracy

**Why Two Steps?**:
- `&&` is very fast (index-only operation)
- `ST_Intersects` is slower but accurate
- Combining both optimizes performance

### Pattern 3: Vector Tile Query

**Use Case**: Generate Mapbox Vector Tiles

**Location**: `backend/tile_server/tile_server_vector.py`

**Query**:
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

**Features**:
- Uses CTE (Common Table Expression) for clarity
- `ST_AsMVTGeom`: Transforms geometry to tile coordinates
- `ST_AsMVT`: Generates MVT protobuf format
- Tile extent: 4096 (MVT standard)
- Buffer: 64 pixels (for edge clipping)

## Spatial Functions Used

### PostGIS Functions

**ST_MakeEnvelope(minx, miny, maxx, maxy, srid)**
- Creates bounding box geometry
- Used for tile bounds and query filters

**ST_Intersects(geom1, geom2)**
- Checks if geometries intersect
- Uses spatial index when available
- Returns boolean

**ST_AsEWKB(geometry)**
- Converts geometry to Extended Well-Known Binary
- Used for transferring geometries to application

**ST_PointOnSurface(geometry)**
- Returns a point guaranteed to be inside polygon
- Used for label placement

**ST_AsMVTGeom(geometry, bounds, extent, buffer, clip)**
- Transforms geometry to tile coordinate system
- Clips to tile bounds
- Used for vector tile generation

**ST_AsMVT(features, layer_name, extent, geom_column)**
- Generates Mapbox Vector Tile (MVT) format
- Returns protobuf bytes

**ST_Contains(geometry, point)**
- Checks if geometry contains point
- Used in point-in-polygon queries

**ST_Centroid(geometry)**
- Returns geometric centroid
- May be outside polygon for complex shapes

### Shapely Functions (Python)

**geometry.contains(point)**
- Point-in-polygon test
- Used in identify API

**geometry.boundary**
- Returns boundary of geometry
- Used for rendering parcel edges

**geometry.simplify(tolerance, preserve_topology)**
- Simplifies geometry using Douglas-Peucker
- Used in ETL for `parcels_simplified` table

**geometry.buffer(0)**
- Repairs invalid geometries
- Used in ETL geometry cleaning

## Performance Optimization

### Index Usage

**GIST Indexes**:
- Automatically created on PostGIS geometry columns
- Optimizes bounding box queries (`&&`)
- Optimizes spatial predicates (`ST_Intersects`, `ST_Contains`)

**Verify Index Usage**:
```sql
EXPLAIN ANALYZE
SELECT * FROM parcels_simplified
WHERE geom && ST_MakeEnvelope(79.0, 13.0, 80.0, 14.0, 4326);
```

Look for "Index Scan" in output.

### Query Optimization Tips

1. **Use Bounding Box First**:
   - Always use `&&` before `ST_Intersects`
   - Reduces candidate set dramatically

2. **Simplify Geometries**:
   - Use `parcels_simplified` for rendering
   - Faster queries and smaller data

3. **Limit Result Set**:
   - Use `LIMIT` when appropriate
   - Reduces data transfer

4. **Projection Considerations**:
   - All data in EPSG:4326 (no transformation needed)
   - Consider projected coordinate system for large areas

### In-Memory Index Performance

**R-tree Index (GeoPandas)**:
- O(log n) for spatial queries
- Built once at startup
- Fast candidate selection
- Memory overhead: ~10-20% of data size

**When to Use**:
- Small to medium datasets (< 1M features)
- Frequent point-in-polygon queries
- Low memory constraints

**When Not to Use**:
- Very large datasets
- Memory-constrained environments
- Infrequent queries (database index sufficient)

## Coordinate System Considerations

### EPSG:4326 (WGS84)

**Used Throughout**:
- Database storage
- Spatial queries
- Coordinate input/output

**Characteristics**:
- Geographic coordinate system
- Decimal degrees
- Suitable for web mapping
- No projection distortion

**Limitations**:
- Not optimal for distance calculations
- Area calculations less accurate
- Consider projected CRS for analysis

### Web Mercator (EPSG:3857)

**Used For**:
- Tile coordinate system
- Map display

**Conversion**:
- Handled in tile utilities
- Not stored in database

## Common Spatial Operations

### Distance Calculations

**Not Currently Used**, but possible:

```sql
-- Distance between two points
SELECT ST_Distance(
    ST_MakePoint(79.28, 13.1),
    ST_MakePoint(79.29, 13.11)
);
```

### Area Calculations

**Not Currently Used**, but possible:

```sql
-- Area of parcel (in square degrees - not accurate)
SELECT ST_Area(geom) FROM parcels WHERE parcel_uuid = '...';

-- Area in square meters (requires transformation)
SELECT ST_Area(ST_Transform(geom, 3857)) FROM parcels WHERE ...;
```

### Buffer Operations

**Used in ETL**:
- `buffer(0)` repairs invalid geometries

**Could be Used For**:
- Proximity searches
- Boundary zones

## Troubleshooting Spatial Queries

### Slow Queries

**Check Index Usage**:
```sql
EXPLAIN ANALYZE <your_query>;
```

**Solutions**:
- Ensure spatial index exists
- Use bounding box operator first
- Simplify geometries
- Limit result set

### Incorrect Results

**Common Issues**:
- Coordinate order (lon, lat vs lat, lon)
- Coordinate system mismatch
- Invalid geometries

**Solutions**:
- Verify coordinate order
- Check SRID matches
- Validate geometries

### Memory Issues (In-Memory Index)

**Symptoms**:
- Slow startup
- High memory usage
- Out of memory errors

**Solutions**:
- Use database queries instead
- Load subset of data
- Increase available memory

## Related Documentation

- [DATABASE.md](DATABASE.md) - Database schema
- [TILES.md](TILES.md) - Tile generation
- [API.md](API.md) - API endpoints

