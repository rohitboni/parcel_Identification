# ETL Pipeline Documentation

## Overview

The ETL pipeline has been rebuilt with a modular, industry-standard architecture. The new ETL supports configurable field mappings via YAML, targets partitioned tables (`parcels_master`, `parcels_simplified`), and pre-computes `label_point` during ETL for better performance.

**Current Status**:
- ✅ New modular ETL implemented and **successfully completed** (`etl/pipeline.py` and `etl/modules/`)
- ✅ YAML configuration system (`etl/config/vellore_mapping.yaml`)
- ✅ Targets partitioned tables with auto-partitioning
- ✅ **Successfully loaded 160,004 parcels into `parcels_master` and `parcels_simplified`**
- ✅ Backend tile generation updated to use new partitioned tables
- ⚠️ Legacy ETL (`etl/load_vellore.py`) still exists but is deprecated
- ⚠️ Legacy tables (`parcels`, `parcels_raw`) can be dropped after verification

## Location

**File**: `etl/load_vellore.py`

## Input Data

**Current source**: `data/vellore/vellore_cad.shp`

Shapefile containing:
- Parcel boundary geometries
- Survey numbers
- Administrative information (village, district, tehsil)
- KIDE identifiers

## ETL Process (current)

### Step 1: Load Shapefile

```python
gdf = gpd.read_file(SHAPEFILE_PATH)
```

- Uses GeoPandas to read shapefile
- Loads into GeoDataFrame with geometry column
- Preserves all attribute columns

### Step 2: Clean Geometries

```python
gdf["clean_geom"] = gdf.geometry.apply(clean_geom)
gdf = gdf[~gdf["clean_geom"].isnull()]
```

**Geometry Cleaning Function** (`clean_geom()`):

1. **Handle None**: Returns None for null geometries
2. **Fix Invalid Geometries**: Uses `buffer(0)` to repair invalid geometries
3. **Normalize Types**: Converts Polygon to MultiPolygon for consistency
4. **Error Handling**: Returns None on exceptions

**Code** (lines 21-31):
```python
def clean_geom(g):
    if g is None:
        return None
    try:
        if not g.is_valid:
            g = g.buffer(0)
        if g.geom_type == "Polygon":
            return MultiPolygon([g])
        return g
    except:
        return None
```

### Step 3: Generate UUIDs

```python
gdf["parcel_uuid"] = [str(uuid.uuid4()) for _ in range(len(gdf))]
```

- Generates unique UUID for each parcel
- Used as primary key across all tables
- Ensures referential integrity

### Step 4: Insert into parcels_raw

**Table**: `parcels_raw`

**Columns Inserted**:
- `parcel_uuid`
- `geom` (as EWKB)
- `kide`, `kide_1`, `kide_2`
- `survey_num` (from `survey_n_4` field)
- `gp_name`
- `v_name`
- `v_code`
- `district` (from `District` field)
- `state` (from `STATE` field)
- `tehsil` (from `TEHSIL` field)

**SQL** (lines 67-71):
```sql
INSERT INTO parcels_raw 
(parcel_uuid, geom, kide, kide_1, kide_2, survey_num, gp_name, v_name, v_code, district, state, tehsil)
VALUES (%s, ST_GeomFromEWKB(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
```

**Geometry Conversion**: 
- Converts Shapely geometry to EWKB using `psycopg2.Binary(row["clean_geom"].wkb)`
- Uses `ST_GeomFromEWKB()` to insert into PostGIS

### Step 5: Insert into parcels

**Table**: `parcels`

**Columns Inserted**:
- `parcel_uuid`
- `geom` (as EWKB)
- `district`
- `tehsil`
- `v_name`
- `survey_num`

**SQL** (lines 97-101):
```sql
INSERT INTO parcels 
(parcel_uuid, geom, district, tehsil, v_name, survey_num)
VALUES (%s, ST_GeomFromEWKB(%s), %s, %s, %s, %s);
```

**Purpose**: Cleaned subset with essential attributes for general queries.

### Step 6: Insert into parcels_simplified (legacy)

**Table**: `parcels_simplified` (legacy, non-partitioned)

**Note**: Legacy ETL performed geometry simplification, but the new modular ETL (**recommended**) does NOT simplify geometries. Both `parcels_master` and `parcels_simplified` contain the original cleaned geometry for maximum precision.

**Legacy Simplification** (deprecated):
- Tolerance: `0.00008` degrees
- Method: Douglas-Peucker with topology preservation
- Purpose: Faster rendering and smaller file sizes

**New ETL**: Uses original geometry (no simplification) for better precision.

**Columns Inserted**:
- `parcel_uuid`
- `geom` (original cleaned geometry, as EWKB - NOT simplified in new ETL)
- `survey_num`
- `v_code`

**SQL** (lines 122-125):
```sql
INSERT INTO parcels_simplified (parcel_uuid, geom, survey_num, v_code)
VALUES (%s, ST_GeomFromEWKB(%s), %s, %s);
```

## Database Configuration

**Location**: Lines 10-16

```python
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "parcels_db",
    "user": "postgres",
    "password": "postgres"
}
```

## Running the ETL

### Prerequisites

1. PostgreSQL with PostGIS extension installed
2. Database `parcels_db` created
3. PostGIS extension enabled: `CREATE EXTENSION postgis;`
4. Shapefile located at `data/vellore/vellore_cad.shp`
5. Python dependencies installed (see `requirements.txt`)

### Execution

```bash
cd parcel_mvp
python etl/load_vellore.py
```

### Output

The script prints progress messages:

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

## Field Mapping

Shapefile fields mapped to database columns:

| Shapefile Field | Database Column | Table(s) |
|----------------|-----------------|----------|
| `survey_n_4` | `survey_num` | All tables |
| `District` | `district` | parcels_raw, parcels |
| `STATE` | `state` | parcels_raw |
| `TEHSIL` | `tehsil` | parcels_raw, parcels |
| `v_name` | `v_name` | parcels_raw, parcels |
| `v_code` | `v_code` | parcels_raw, parcels_simplified |
| `gp_name` | `gp_name` | parcels_raw |
| `kide` | `kide` | parcels_raw |
| `kide_1` | `kide_1` | parcels_raw |
| `kide_2` | `kide_2` | parcels_raw |
| `geometry` | `geom` | All tables |

## Error Handling

- **Invalid Geometries**: Fixed with `buffer(0)`
- **Null Geometries**: Filtered out
- **Type Errors**: Handled with try/except in `clean_geom()`
- **Database Errors**: Will raise exceptions (not caught)

## Performance Considerations

1. **Batch Processing**: Processes rows one at a time (could be optimized)
2. **Geometry Simplification**: Computationally expensive but necessary
3. **Transaction Management**: Commits after each table insert
4. **Memory Usage**: Loads entire shapefile into memory

## Optimization Opportunities

1. **Batch Inserts**: Use `executemany()` for faster inserts
2. **Connection Pooling**: Reuse database connections
3. **Parallel Processing**: Process multiple parcels concurrently
4. **Progress Tracking**: Add progress bars for large datasets

## Data Quality

The ETL process ensures:
- All geometries are valid
- All geometries are MultiPolygon type
- UUIDs are unique
- No null geometries in final tables

## Troubleshooting

### Common Issues

1. **Database Connection Error**
   - Check PostgreSQL is running
   - Verify database credentials
   - Ensure database exists

2. **PostGIS Not Found**
   - Run `CREATE EXTENSION postgis;` in database
   - Verify PostGIS is installed

3. **Shapefile Not Found**
   - Check path: `data/vellore/vellore_cad.shp`
   - Verify all shapefile components (.shp, .shx, .dbf, .prj) exist

4. **Geometry Errors**
   - Check shapefile geometry validity
   - Review `clean_geom()` function output

## New Modular ETL Pipeline

### Architecture

The new ETL follows industry-standard patterns with clear separation of concerns:

```
etl/
├── pipeline.py              # Main orchestrator (CLI entry point)
├── config/
│   └── vellore_mapping.yaml # Field mappings and configuration
├── modules/
│   ├── extract.py          # Data extraction and inspection
│   ├── transform.py        # Field mapping, geometry processing
│   ├── validate.py         # Data quality validation
│   ├── load.py             # Database loading (batch inserts)
│   └── geometry_utils.py   # Low-level geometry operations
└── explore_data.ipynb       # Interactive data exploration
```

### Key Features

1. **Configuration-Driven**: YAML config defines field mappings, transformations, and validation rules
2. **Modular Design**: Each step (extract, transform, validate, load) is a separate, testable module
3. **Pre-computed label_point**: Computed during ETL and stored in database (moved from tile generation)
4. **Database UUID Generation**: Uses `DEFAULT gen_random_uuid()` instead of Python generation
5. **Partitioned Tables**: Targets `parcels_master` and `parcels_simplified` with auto-partitioning
6. **Batch Inserts**: Efficient batch loading for performance

### Running the New ETL

```bash
cd etl
python pipeline.py --config config/vellore_mapping.yaml
```

With custom database settings:

```bash
python pipeline.py \
  --config config/vellore_mapping.yaml \
  --db-host 127.0.0.1 \
  --db-port 5432 \
  --db-name parcels_db \
  --db-user postgres \
  --db-password postgres
```

### Configuration File

The YAML config (`config/vellore_mapping.yaml`) defines:
- **field_mapping**: Source column → Target column mappings
- **transforms**: Computed fields (e.g., `state_code` from `FID_Tamiln`)
- **required_fields**: Validation requirements
- **geometry**: Simplification tolerance, CRS, label point computation

If the YAML file is missing, open `etl/explore_data.ipynb` and run the final "Generate Config Template" cell; it writes the config to `etl/config/vellore_mapping.yaml`.

### ETL Process Flow

1. **Extract**: Load shapefile, inspect schema
2. **Validate Source**: Check required columns, geometry validity
3. **Transform**: 
   - Map fields according to config
   - Apply transformations (string conversion, etc.)
   - Clean geometries (fix invalid, normalize types)
   - Compute label points (ST_PointOnSurface)
   - Simplify geometries for simplified table
4. **Validate Transformed**: Check schema, required fields, geometries
5. **Load**: Batch insert into `parcels_master`, then `parcels_simplified`

### Field Mappings (Vellore)

| Source Field | Target Field | Notes |
|-------------|--------------|-------|
| `STATE` | `state` | Direct mapping |
| `FID_Tamiln` | `state_code` | Transform: int64 → string |
| `FID_vellor` | `district_code` | Transform: int64 → string |
| `District` | `district_name` | Direct mapping |
| `TEHSIL` | `sub_district_name` | Direct mapping |
| `v_name` | `village_name` | Direct mapping |
| `survey_n_4` | `survey_num` | Direct mapping |
| `geometry` | `geom` | Cleaned and normalized |
| - | `label_point` | Computed (ST_PointOnSurface) |
| - | `parcel_uuid` | Auto-generated by database |

### Migration from Legacy ETL

The legacy ETL (`etl/load_vellore.py`) is deprecated but remains for reference. Key differences:

| Feature | Legacy ETL | New ETL |
|---------|-----------|---------|
| Tables | `parcels_raw`, `parcels`, `parcels_simplified` | `parcels_master`, `parcels_simplified` |
| UUID Generation | Python (`uuid.uuid4()`) | Database (`DEFAULT gen_random_uuid()`) |
| label_point | Computed in tile generation | Pre-computed in ETL |
| Configuration | Hardcoded | YAML config file |
| Architecture | Monolithic script | Modular components |
| Partitioning | None | Auto-partitioned by state/district |

### Next Steps

1. ✅ Run new ETL to populate partitioned tables - **Completed**
2. ✅ Update tile generation to use new tables - **Completed**
3. ✅ Update identify API to use database - **Completed**
4. ✅ Test end-to-end workflow - **Completed**
5. ⚠️ Deprecate legacy tables once migration verified - **Pending verification**

## Related Documentation

- [DATABASE.md](DATABASE.md) - Database schema details
- [SETUP.md](SETUP.md) - Environment setup
- [CONFIG.md](CONFIG.md) - Configuration details
- [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) - Migration from legacy to new system

