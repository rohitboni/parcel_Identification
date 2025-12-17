# Dual Database Setup - Local & Neon

## Overview

The system now supports **two separate databases** that work independently:

1. **Local Database** (`parcels_db`) - Vellore data (160K parcels)
2. **Neon Production Database** (`india_cadastral_production`) - Karnataka data (1.4M parcels)

Both databases use the **same schema structure** but are kept completely separate.

---

## Database Comparison

### Local Database (parcels_db)

**Connection:** PostgreSQL on localhost  
**Tables:**
- `parcels_master` (partitioned)
- `parcels_simplified` (partitioned)

**Data:**
- **Source:** Shapefile ETL (`data/vellore/vellore_cad.shp`)
- **Rows:** 160,004 parcels
- **State:** Tamil Nadu (TN)
- **District:** Vellore
- **Geometry CRS:** EPSG:4326 (already in WGS84)

**ETL:** `etl/pipeline.py` → Loads from shapefile

---

### Neon Database (india_cadastral_production)

**Connection:** Neon PostgreSQL (AWS ap-southeast-1)  
**Tables:**
- `cadastrals` (original, source table - **not modified**)
- `parcels_master_neon` (partitioned) - **NEW**
- `parcels_simplified_neon` (partitioned) - **NEW**

**Data:**
- **Source:** Existing `cadastrals` table
- **Rows:** 1,452,025 parcels (to be migrated)
- **State:** Karnataka (ka)
- **Districts:** 8 districts
- **Geometry CRS:** EPSG:32643 (UTM) → Transformed to EPSG:4326

**Migration:** `migrate_neon_data.py` → Transforms from `cadastrals` table

---

## Schema Structure

Both databases use **identical schema** (just different table names):

### parcels_master / parcels_master_neon

```sql
CREATE TABLE parcels_master_neon (
    parcel_uuid           UUID NOT NULL DEFAULT gen_random_uuid(),
    geom                  geometry(MultiPolygon, 4326) NOT NULL,
    label_point           geometry(Point, 4326),
    state                 TEXT NOT NULL,
    state_code            TEXT NOT NULL,
    district_code         TEXT NOT NULL,
    district_name         TEXT NOT NULL,
    sub_district_name     TEXT,
    village_name          TEXT,
    survey_num            TEXT NOT NULL,
    created_at            TIMESTAMP DEFAULT now(),
    source_gid            INTEGER,  -- Only in Neon (references cadastrals.gid)
    PRIMARY KEY (state_code, district_code, parcel_uuid)
) PARTITION BY LIST (state_code);
```

### parcels_simplified / parcels_simplified_neon

```sql
CREATE TABLE parcels_simplified_neon (
    parcel_uuid     UUID NOT NULL,
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    label_point     geometry(Point, 4326) NOT NULL,
    state_code      TEXT NOT NULL,
    district_code   TEXT NOT NULL,
    survey_num      TEXT,
    PRIMARY KEY (state_code, district_code, parcel_uuid)
) PARTITION BY LIST (state_code);
```

---

## Setup Instructions

### For Neon Database

#### Step 1: Create Schema

```bash
python setup_neon_db.py
```

This creates:
- `parcels_master_neon` table
- `parcels_simplified_neon` table
- Partition functions and triggers
- Auto-partitioning setup

#### Step 2: Migrate Data

```bash
# Full migration (all 1.4M rows - takes ~1-2 hours)
python migrate_neon_data.py

# Test migration (first 1000 rows)
python migrate_neon_data.py --limit=1000 --batch-size=500
```

**What the migration does:**
1. Reads from `cadastrals` table
2. Transforms geometry: EPSG:32643 → EPSG:4326
3. Maps columns: `Survey_Number` → `survey_num`, etc.
4. Computes `label_point` using `ST_PointOnSurface`
5. Generates UUIDs for each parcel
6. Inserts into partitioned tables in batches
7. Creates partitions automatically via triggers

#### Step 3: Verify

```sql
-- Check row counts
SELECT COUNT(*) FROM parcels_master_neon;
SELECT COUNT(*) FROM parcels_simplified_neon;

-- Check partitions created
SELECT tablename FROM pg_tables 
WHERE tablename LIKE 'parcels_%_neon%' 
ORDER BY tablename;

-- Verify data distribution
SELECT state_code, district_code, COUNT(*) 
FROM parcels_master_neon 
GROUP BY state_code, district_code;
```

---

## Field Mapping (Neon → Partitioned Tables)

| Source (cadastrals) | Target (parcels_master_neon) | Transformation |
|---------------------|------------------------------|----------------|
| `gid` | `source_gid` | Direct copy (preserved) |
| `Survey_Number` | `survey_num` | Direct copy |
| `Village_Name` | `village_name` | Direct copy |
| `Mandal_Name` | `sub_district_name` | Direct copy |
| `District_Name` | `district_name` | Direct copy |
| `State_Name` | `state` | Direct copy |
| `State_Code` | `state_code` | Uppercase conversion |
| `District_Code` | `district_code` | Direct copy |
| `geom` (32643) | `geom` (4326) | **ST_Transform(geom, 4326)** |
| - | `label_point` | **ST_PointOnSurface(geom)** |
| - | `parcel_uuid` | **gen_random_uuid()** |

---

## Key Features

### 1. **Separate Tables**
- Local: `parcels_master`, `parcels_simplified`
- Neon: `parcels_master_neon`, `parcels_simplified_neon`
- No conflicts, completely independent

### 2. **Same Structure**
- Identical schema (except `source_gid` in Neon)
- Same partitioning strategy
- Same indexes and triggers

### 3. **Auto-Partitioning**
- Both databases use triggers for auto-partitioning
- Partitions created on first insert
- Two-level: state → district

### 4. **Geometry Handling**
- **Local:** Already EPSG:4326 (no transformation)
- **Neon:** Transformed from EPSG:32643 → EPSG:4326 during migration

### 5. **Label Points**
- **Local:** Computed during ETL
- **Neon:** Computed during migration
- Both pre-computed for performance

---

## Backend Configuration

The backend can be configured to use either database by changing:

1. **Database connection config** (environment variables or code)
2. **Table names** in queries:
   - Local: `parcels_master`, `parcels_simplified`
   - Neon: `parcels_master_neon`, `parcels_simplified_neon`

### Example: Tile Generation Query

**Local DB:**
```sql
SELECT ... FROM parcels_simplified WHERE ...
```

**Neon DB:**
```sql
SELECT ... FROM parcels_simplified_neon WHERE ...
```

---

## Migration Performance

**Expected Performance:**
- **Batch size:** 1000 rows (configurable)
- **Time per batch:** ~2-5 seconds
- **Total time (1.4M rows):** ~1-2 hours
- **Progress:** Logged every batch

**Optimizations:**
- Batch inserts (1000 rows at a time)
- Pre-created partitions (avoids trigger overhead)
- Geometry transformation in SQL (efficient)
- Label point computation in SQL (efficient)

---

## Verification Queries

### Check Migration Status

```sql
-- Compare counts
SELECT 
    (SELECT COUNT(*) FROM cadastrals) as source_count,
    (SELECT COUNT(*) FROM parcels_master_neon) as master_count,
    (SELECT COUNT(*) FROM parcels_simplified_neon) as simplified_count;

-- Check geometry CRS
SELECT ST_SRID(geom) as srid FROM parcels_master_neon LIMIT 1;
-- Should return: 4326

-- Check sample data
SELECT parcel_uuid, survey_num, village_name, district_name, state_code
FROM parcels_master_neon 
LIMIT 5;

-- Verify label points exist
SELECT COUNT(*) as total,
       COUNT(label_point) as with_label_point
FROM parcels_master_neon;
```

---

## Next Steps

After migration completes:

1. **Update backend code** to support both databases (or create separate config)
2. **Test tile generation** with Neon database
3. **Test identify API** with Neon database
4. **Update frontend** if needed for different data sources

---

## Files Created

1. **`setup_neon_db.py`** - Creates schema (tables, functions, triggers)
2. **`migrate_neon_data.py`** - Migrates data from cadastrals to partitioned tables
3. **`docs/NEON_DB_SCHEMA.md`** - Schema analysis of Neon database
4. **`docs/NEON_SETUP.md`** - Setup instructions
5. **`docs/DUAL_DATABASE_SETUP.md`** - This document

---

## Important Notes

- ✅ Original `cadastrals` table is **NOT modified** - kept as backup
- ✅ Migration can be re-run (but will create duplicates - use with caution)
- ✅ Both databases work independently
- ✅ Same codebase can work with both (just change table names/config)
- ✅ Partitioning happens automatically via triggers
- ✅ All geometries in EPSG:4326 for web compatibility

