# Data Dictionary

## Overview

This document describes the data structure, fields, coordinate systems, and data sources used in the Parcel MVP project.

## Data Source

### Shapefile

**Location**: `data/vellore/vellore_cad.shp`

**Type**: ESRI Shapefile

**Content**: Vellore cadastral (land parcel) boundaries

**Components**:
- `vellore_cad.shp` - Geometry data
- `vellore_cad.shx` - Spatial index
- `vellore_cad.dbf` - Attribute data
- `vellore_cad.prj` - Projection information
- `vellore_cad.cpg` - Code page information
- `vellore_cad.sbn` / `vellore_cad.sbx` - Spatial index files

## Coordinate System

### Source Data

**Coordinate System**: EPSG:4326 (WGS84)

**Units**: Decimal degrees (latitude/longitude)

**Bounds** (approximate for Vellore):
- Latitude: 12.5°N to 13.5°N
- Longitude: 79.0°E to 79.5°E

### Storage

All geometries are stored in **EPSG:4326** in the database:
- Consistent with web mapping standards
- Compatible with Leaflet.js
- No transformation needed for display

### Tile Coordinate System

Tiles use **Web Mercator** (EPSG:3857) tile scheme:
- Standard XYZ tile coordinates
- Compatible with OpenStreetMap, Google Maps
- Conversion handled in `backend/tile_server/utils/tile_utils.py`

## Field Descriptions

### Original Shapefile Fields

Fields from the Vellore cadastral shapefile:

| Field Name | Type | Description | Database Mapping |
|------------|------|-------------|------------------|
| `survey_n_4` | String | Survey number of the parcel | `survey_num` |
| `District` | String | District name (e.g., "Vellore") | `district` |
| `STATE` | String | State name (e.g., "Tamil Nadu") | `state` |
| `TEHSIL` | String | Tehsil (administrative division) name | `tehsil` |
| `v_name` | String | Village name | `v_name` |
| `v_code` | String | Village code (numeric identifier) | `v_code` |
| `gp_name` | String | Gram Panchayat name | `gp_name` |
| `kide` | String | KIDE identifier | `kide` |
| `kide_1` | String | KIDE identifier variant 1 | `kide_1` |
| `kide_2` | String | KIDE identifier variant 2 | `kide_2` |
| `geometry` | Geometry | Parcel boundary (Polygon/MultiPolygon) | `geom` |

### Database Fields

#### parcels_raw Table

Complete set of attributes from shapefile:

| Column | Type | Description | Source |
|--------|------|-------------|--------|
| `parcel_uuid` | UUID | Unique identifier (generated) | ETL generated |
| `geom` | Geometry(MultiPolygon, 4326) | Parcel boundary | Shapefile geometry |
| `kide` | VARCHAR | KIDE identifier | Shapefile `kide` |
| `kide_1` | VARCHAR | KIDE variant 1 | Shapefile `kide_1` |
| `kide_2` | VARCHAR | KIDE variant 2 | Shapefile `kide_2` |
| `survey_num` | VARCHAR | Survey number | Shapefile `survey_n_4` |
| `gp_name` | VARCHAR | Gram Panchayat name | Shapefile `gp_name` |
| `v_name` | VARCHAR | Village name | Shapefile `v_name` |
| `v_code` | VARCHAR | Village code | Shapefile `v_code` |
| `district` | VARCHAR | District name | Shapefile `District` |
| `state` | VARCHAR | State name | Shapefile `STATE` |
| `tehsil` | VARCHAR | Tehsil name | Shapefile `TEHSIL` |

#### parcels Table

Essential attributes subset:

| Column | Type | Description |
|--------|------|-------------|
| `parcel_uuid` | UUID | Unique identifier |
| `geom` | Geometry(MultiPolygon, 4326) | Parcel boundary |
| `district` | VARCHAR | District name |
| `tehsil` | VARCHAR | Tehsil name |
| `v_name` | VARCHAR | Village name |
| `survey_num` | VARCHAR | Survey number |

#### parcels_simplified Table

Simplified geometry for rendering:

| Column | Type | Description |
|--------|------|-------------|
| `parcel_uuid` | UUID | Unique identifier |
| `geom` | Geometry(MultiPolygon, 4326) | Simplified parcel boundary |
| `survey_num` | VARCHAR | Survey number (for labels) |
| `v_code` | VARCHAR | Village code |

## Geometry Details

### Geometry Types

**Source**: Polygon or MultiPolygon

**Storage**: All stored as MultiPolygon for consistency

**Transformation**: Polygons converted to MultiPolygon during ETL

### Geometry Cleaning

Process applied during ETL (`etl/load_vellore.py`):

1. **Invalid Geometry Repair**: `buffer(0)` fixes self-intersections
2. **Type Normalization**: Polygon → MultiPolygon
3. **Null Filtering**: Remove parcels with null geometries

### Geometry Simplification

Applied to `parcels_simplified`:

- **Algorithm**: Douglas-Peucker
- **Tolerance**: 0.00008 degrees (~8.9 meters)
- **Topology**: Preserved
- **Purpose**: Faster rendering, smaller file sizes

## Data Quality

### Validation

- All geometries validated and repaired if needed
- Null geometries filtered out
- Coordinate system verified (EPSG:4326)

### Completeness

- All parcels have UUIDs
- Survey numbers present (may be empty string)
- Administrative fields may have null values

### Accuracy

- Source data accuracy depends on cadastral survey
- Simplification introduces minor geometric differences
- Suitable for visualization and general queries

## Data Volume

**Typical Sizes** (approximate):
- Shapefile: Varies by region
- Database: Depends on number of parcels
- Simplified geometries: ~10-30% smaller than original

**Example** (Vellore region):
- Parcels: Thousands to tens of thousands
- Average geometry complexity: Varies by parcel size
- Database size: Depends on parcel count and complexity

## Administrative Hierarchy

```
State (Tamil Nadu)
  └── District (Vellore)
      └── Tehsil
          └── Village (v_name, v_code)
              └── Gram Panchayat (gp_name)
                  └── Parcel (survey_num)
```

## Field Usage

### Identification

- **parcel_uuid**: Primary key, unique identifier
- **survey_num**: Human-readable identifier
- **v_code**: Village-level grouping

### Administrative

- **district**: Administrative level
- **tehsil**: Sub-district level
- **v_name**: Village name
- **gp_name**: Local governance unit

### Technical

- **kide, kide_1, kide_2**: System identifiers (usage unclear)

## Data Updates

### Adding New Data

1. Prepare shapefile in same format
2. Run ETL pipeline
3. Verify data loaded correctly
4. Clear tile cache if needed

### Updating Existing Data

1. Backup database
2. Update shapefile
3. Re-run ETL (may need to clear tables first)
4. Regenerate affected tiles

## Data Privacy

**Considerations**:
- Cadastral data may be public or restricted
- Check local regulations
- Consider data anonymization if needed
- Implement access controls if required

## Related Documentation

- [DATABASE.md](DATABASE.md) - Database schema
- [ETL.md](ETL.md) - Data loading process
- [TILES.md](TILES.md) - Tile generation

