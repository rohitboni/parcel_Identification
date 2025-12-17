# Neon Database Setup Guide

## Overview

This guide explains how to set up partitioned tables in the Neon production database (`india_cadastral_production`) that mirror the structure of the local database but are kept separate.

## Database Structure

### New Tables Created

1. **`parcels_master_neon`** - Full parcel data with all attributes
   - Partitioned by `state_code` → `district_code`
   - Primary key: `(state_code, district_code, parcel_uuid)`
   - Geometry: EPSG:4326 (transformed from source EPSG:32643)

2. **`parcels_simplified_neon`** - Optimized for tile generation
   - Same partitioning structure
   - Contains: `parcel_uuid`, `geom`, `label_point`, `state_code`, `district_code`, `survey_num`

### Source Table

- **`cadastrals`** - Original table (kept intact, not modified)
  - Contains 1,452,025 parcels
  - Geometry in EPSG:32643 (UTM Zone 43N)
  - Column names in PascalCase

## Setup Steps

### Step 1: Create Schema

Run the schema creation script:

```bash
python setup_neon_db.py
```

This will:
- Enable PostGIS extension
- Create `parcels_master_neon` and `parcels_simplified_neon` tables
- Create partition functions and triggers
- Set up auto-partitioning

### Step 2: Migrate Data

Run the migration script to transform and load data:

```bash
# Full migration (all 1.4M+ rows)
python migrate_neon_data.py

# Test with limited rows
python migrate_neon_data.py --limit=1000 --batch-size=500
```

**Migration Process:**
1. Reads from `cadastrals` table
2. Transforms geometry: EPSG:32643 → EPSG:4326
3. Maps columns: PascalCase → snake_case
4. Computes `label_point` using `ST_PointOnSurface`
5. Inserts into partitioned tables in batches

**Expected Time:**
- ~1-2 hours for full migration (1.4M rows)
- Progress logged every batch

### Step 3: Verify Migration

```sql
-- Check row counts
SELECT COUNT(*) FROM parcels_master_neon;
SELECT COUNT(*) FROM parcels_simplified_neon;

-- Check partitions
SELECT schemaname, tablename 
FROM pg_tables 
WHERE tablename LIKE 'parcels_%_neon%' 
ORDER BY tablename;

-- Verify data
SELECT state_code, district_code, COUNT(*) 
FROM parcels_master_neon 
GROUP BY state_code, district_code;
```

## Schema Comparison

| Feature | Local DB | Neon DB |
|---------|----------|---------|
| Master Table | `parcels_master` | `parcels_master_neon` |
| Simplified Table | `parcels_simplified` | `parcels_simplified_neon` |
| Source | Shapefile ETL | `cadastrals` table |
| Geometry CRS | EPSG:4326 | EPSG:4326 (transformed) |
| Partitioning | Yes | Yes |
| Label Points | Pre-computed | Pre-computed |
| Row Count | 160,004 | ~1,452,025 |

## Field Mapping

| Neon Source (cadastrals) | Target (parcels_master_neon) |
|-------------------------|------------------------------|
| `gid` | `source_gid` (preserved) |
| `Survey_Number` | `survey_num` |
| `Village_Name` | `village_name` |
| `Mandal_Name` | `sub_district_name` |
| `District_Name` | `district_name` |
| `State_Name` | `state` |
| `State_Code` | `state_code` (uppercase) |
| `District_Code` | `district_code` |
| `geom` (32643) | `geom` (4326, transformed) |
| - | `label_point` (computed) |
| - | `parcel_uuid` (generated) |

## Usage

After migration, the backend can be configured to use either database:

- **Local DB**: `parcels_master`, `parcels_simplified`
- **Neon DB**: `parcels_master_neon`, `parcels_simplified_neon`

Both databases work independently with the same codebase structure.

## Notes

- Original `cadastrals` table is **not modified** - kept as backup
- Migration is idempotent (can be re-run, but will create duplicates)
- Partitioning happens automatically via triggers
- All geometries are transformed to EPSG:4326 for web compatibility
- Label points are pre-computed for performance

