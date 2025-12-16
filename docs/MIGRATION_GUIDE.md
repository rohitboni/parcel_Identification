# Migration Guide: Legacy Tables → Partitioned Tables

## Overview

This guide covers migrating from the legacy ETL and tables to the new modular ETL and partitioned tables.

## Current State

### Legacy System (Still Active)
- **ETL**: `etl/load_vellore.py` (deprecated)
- **Tables**: `parcels_raw`, `parcels`, `parcels_simplified` (non-partitioned)
- **Tile Generation**: Uses `parcels_simplified` (legacy table)
- **label_point**: Computed on-the-fly in tile generation query

### New System (Ready)
- **ETL**: `etl/pipeline.py` with modular architecture
- **Tables**: `parcels_master`, `parcels_simplified` (partitioned)
- **Tile Generation**: Still uses legacy tables (needs update)
- **label_point**: Pre-computed during ETL and stored

## Migration Steps

### Step 1: Run New ETL Pipeline

Populate the new partitioned tables:

```bash
cd etl
python pipeline.py --config config/vellore_mapping.yaml
```

Verify data loaded:

```sql
-- Check parcels_master
SELECT COUNT(*) FROM parcels_master;
SELECT state_code, district_code, COUNT(*) 
FROM parcels_master 
GROUP BY state_code, district_code;

-- Check parcels_simplified
SELECT COUNT(*) FROM parcels_simplified;

-- Verify label_point was computed
SELECT COUNT(*) FROM parcels_master WHERE label_point IS NOT NULL;
SELECT COUNT(*) FROM parcels_simplified WHERE label_point IS NOT NULL;
```

### Step 2: Update Tile Generation

Update `backend/tile_server/utils/generate_tile.py` to use new tables:

**Current Query** (line 38-46):
```python
query = """
    SELECT parcel_uuid,
           survey_num,
           ST_AsEWKB(geom),
           ST_AsEWKB(ST_PointOnSurface(geom)) AS label_point
    FROM parcels_simplified
    WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
      AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326));
"""
```

**Updated Query** (use pre-computed label_point):
```python
query = """
    SELECT parcel_uuid,
           survey_num,
           ST_AsEWKB(geom),
           ST_AsEWKB(label_point) AS label_point
    FROM parcels_simplified
    WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
      AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326));
"""
```

**Key Changes**:
- Table name: `parcels_simplified` (same, but now partitioned)
- label_point: Use stored `label_point` column instead of `ST_PointOnSurface(geom)`
- Performance: Faster queries (no on-the-fly computation)

### Step 3: Update Identify API (if needed)

The identify API uses an in-memory spatial index loaded from the shapefile. This doesn't need immediate changes, but consider:

1. **Option A**: Keep using shapefile (current approach)
2. **Option B**: Load from `parcels_master` table instead (better for multi-dataset)

For now, Option A is fine. Option B can be implemented later.

### Step 4: Test End-to-End

1. **Clear tile cache** (optional, to force regeneration):
   ```bash
   rm -rf backend/cache/*
   ```

2. **Start backend server**:
   ```bash
   cd backend
   uvicorn main:app --reload
   ```

3. **Test tile generation**:
   - Open frontend map
   - Navigate to Vellore area
   - Verify tiles load correctly
   - Check that survey numbers appear (label_point working)

4. **Test identify API**:
   - Click on parcels
   - Verify parcel information displays correctly

### Step 5: Verify Performance

Compare tile generation performance:

**Before** (computing label_point on-the-fly):
- Query time: ~50-200ms per tile
- CPU usage: Higher (geometry computation)

**After** (using pre-computed label_point):
- Query time: ~10-50ms per tile (expected improvement)
- CPU usage: Lower (just reading stored data)

### Step 6: Deprecate Legacy Tables (Optional)

Once new system is verified working:

1. **Backup legacy tables** (safety):
   ```sql
   CREATE TABLE parcels_raw_backup AS SELECT * FROM parcels_raw;
   CREATE TABLE parcels_backup AS SELECT * FROM parcels;
   CREATE TABLE parcels_simplified_backup AS SELECT * FROM parcels_simplified;
   ```

2. **Monitor new system** for a period (e.g., 1 week)

3. **Drop legacy tables** (when confident):
   ```sql
   DROP TABLE parcels_raw;
   DROP TABLE parcels;
   DROP TABLE parcels_simplified;
   ```

## Rollback Plan

If issues arise:

1. **Revert tile generation** to use `ST_PointOnSurface(geom)` query
2. **Legacy tables still exist** (if not dropped) - can switch back
3. **Legacy ETL** (`etl/load_vellore.py`) still available for reference

## Benefits After Migration

1. **Performance**: Pre-computed label_point = faster tile generation
2. **Scalability**: Partitioned tables = better performance with large datasets
3. **Maintainability**: Modular ETL = easier to extend and test
4. **Flexibility**: YAML config = easy to add new datasets
5. **Data Quality**: Better validation and error handling

## Troubleshooting

### Issue: Tiles not loading after migration

**Check**:
- Verify new tables have data: `SELECT COUNT(*) FROM parcels_simplified;`
- Check tile generation logs for errors
- Verify label_point column exists: `SELECT label_point FROM parcels_simplified LIMIT 1;`

### Issue: label_point is NULL

**Check**:
- Verify ETL config has `compute_label_point: true`
- Check ETL logs for geometry errors
- Verify geometries are valid: `SELECT COUNT(*) FROM parcels_simplified WHERE geom IS NULL;`

### Issue: Partition not created

**Check**:
- Verify triggers exist: `\d+ parcels_master` (should show triggers)
- Check PostgreSQL logs for trigger errors
- Manually create partition if needed (see `knowledge_docs/db_instructions.md`)

## Related Documentation

- [ETL.md](ETL.md) - ETL pipeline details
- [DATABASE.md](DATABASE.md) - Database schema
- [TILES.md](TILES.md) - Tile generation details
- [NEXT_STEPS.md](../etl/NEXT_STEPS.md) - ETL next steps guide

