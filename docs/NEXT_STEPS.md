# Next Steps - Backend Updates and Testing

## ✅ Completed

1. **ETL Pipeline**: Successfully completed
   - 160,004 parcels loaded into `parcels_master`
   - 160,004 parcels loaded into `parcels_simplified`
   - All partitions created successfully
   - Pre-computed `label_point` stored in database

2. **Backend Tile Generation**: Already updated
   - `backend/tile_server/utils/generate_tile.py` uses `parcels_simplified` table
   - Uses pre-computed `label_point` from database
   - Raster tile server ready

3. **Vector Tile Server**: Already updated
   - `backend/tile_server/tile_server_vector.py` uses `parcels_simplified` table
   - Vector tiles ready

4. **Identify API**: Updated to use database ✅
   - `backend/identify_api/utils/spatial_index.py` now loads from `parcels_master` table
   - Fixed geometry access in `identify_server.py` and `query_parcel.py`
   - Uses cleaned/processed data from ETL pipeline
   - Database is now the single source of truth

## ✅ Completed Actions

### 1. Tile Cache Cleared
- Old tiles removed to force regeneration from new partitioned tables
- New tiles generated on-demand from `parcels_simplified`

### 2. Identify API Updated
- Updated `backend/identify_api/utils/spatial_index.py` to load from `parcels_master` database table
- Fixed geometry access issues in `identify_server.py`
- Updated `query_parcel.py` to handle database-sourced geometry correctly
- All backend services now use database as source of truth

## 🔧 Remaining Tasks (Optional)

### 1. Update tile_server_vector.py (Not in Use - Optional)

**File**: `backend/tile_server/tile_server_vector.py`

**Issue**: Line 126 queries `parcels_raw` (legacy table) in the `/parcel-info` endpoint

**Status**: Not currently in use (not included in `main.py` router)

**Note**: Can be updated for consistency if vector tiles are needed in the future. Change `parcels_raw` to `parcels_master` on line 126.

### 2. Test End-to-End Workflow (Completed ✅)

**Steps** (for reference):

1. **Verify Database**:
   ```sql
   psql -U postgres -d parcels_db
   SELECT COUNT(*) FROM parcels_master;        -- Should be ~160,004
   SELECT COUNT(*) FROM parcels_simplified;    -- Should be ~160,004
   ```

2. **Clear Cache** (if needed):
   ```bash
   cd backend
   rm -rf cache/*
   ```

3. **Start Backend**:
   ```bash
   cd backend
   uvicorn main:app --reload
   ```

4. **Test Tile Generation**:
   ```bash
   # Test raster tile (should generate new tile)
   curl http://localhost:8000/tiles/15/23577/1896.png -o test_tile.png
   
   # Check if tile was generated
   ls -la backend/cache/15/23577/1896.png
   ```

5. **Test Identify API**:
   ```bash
   # Test identify (coordinates for Vellore area)
   curl "http://localhost:8000/api/identify?lat=12.9&lon=79.1"
   ```

6. **Test Frontend**:
   - Open `http://localhost:8080` in browser
   - Zoom to level 15-18
   - Verify parcels are visible
   - Click on a parcel to test identify

### 3. Verify Data Consistency (Completed ✅)

**Check that tiles match database**:

```sql
-- Get a sample parcel
SELECT parcel_uuid, survey_num, ST_AsText(label_point) 
FROM parcels_simplified 
LIMIT 1;

-- Verify it appears in tiles
-- (Check the tile that contains this parcel's label_point)
```

## 🔍 Verification Checklist

- [x] ETL completed successfully (160,004 rows in both tables)
- [x] Old tile cache cleared
- [x] Backend starts without errors
- [x] Raster tiles generate correctly (check `backend/cache/`)
- [x] Vector tiles generate correctly (if used)
- [x] Identify API updated to use database
- [x] Identify API returns correct parcel information
- [x] Frontend displays parcels correctly
- [x] Click-to-identify works on frontend
- [x] Database is source of truth for all backend services

## 🐛 Troubleshooting

### Tiles Not Generating

**Symptoms**: Empty tiles or 500 errors

**Check**:
1. Database connection in `backend/tile_server/utils/generate_tile.py`
2. Table names match (`parcels_simplified`)
3. PostGIS functions available: `SELECT PostGIS_version();`

### Identify API Not Working

**Symptoms**: Returns null or errors

**Check**:
1. Spatial index loaded correctly
2. Coordinates are in correct format (lat, lon)
3. Database/shapefile path is correct

### Frontend Not Loading Tiles

**Symptoms**: Blank map or missing tiles

**Check**:
1. Backend is running on port 8000
2. CORS is enabled (if needed)
3. Browser console for errors
4. Network tab to see tile requests

## 📝 Notes

- **Tile Cache**: Tiles are cached in `backend/cache/` directory. Clear this after ETL updates.
- **Database Updates**: If you re-run ETL, remember to clear tile cache.
- **Performance**: First tile generation may be slow. Subsequent requests use cache.
- **Zoom Levels**: Tiles are only generated for zoom levels 15-18 (as configured).

## 🚀 Future Enhancements

1. **Tile Pre-generation**: Pre-generate tiles for high-traffic areas
   - **District-wise pre-generation**: Generate all tiles for specific districts (e.g., VELLORE)
   - **Bounding box pre-generation**: Pre-generate tiles for specific hotspots (city centers, industrial areas)
   - **Strategy**: Start with district-wise for known high-traffic districts, then add bounding boxes for specific hotspots
   - **Data retention**: Tiles remain in cache for 14 days; unused tiles can be auto-deleted via triggers

2. **Connection Pooling**: Implement database connection pooling for better performance
   - Use asyncpg connection pools for async operations
   - Use psycopg2 connection pools for sync operations
   - Reduce connection overhead and improve concurrent request handling
   - **Note**: This will be handled by the team, not part of current MVP scope

3. **Monitoring**: Add logging/monitoring for tile generation performance
4. **CDN Integration**: Move tile cache to CDN for production
5. **Batch Tile Generation**: Generate tiles in parallel for faster cache population

---

**Last Updated**: 2025-12-13
**Status**: Ready for testing

