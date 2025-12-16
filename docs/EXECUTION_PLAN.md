# ETL Pipeline - Execution Plan

## Current Status

✅ **Completed**:
- New modular ETL pipeline implemented
- YAML configuration system created
- All modules (extract, transform, validate, load) ready
- Documentation updated
- Changelog updated

⚠️ **Pending**:
- Run ETL to populate new tables
- Update tile generation to use new tables
- Test end-to-end workflow

## Next Steps - Recommended Sequence

### Phase 1: Run ETL (Do This First) ✅

**Why First?**
- Populates the new partitioned tables
- Validates the entire ETL pipeline works
- Creates data needed for tile generation migration

**Steps**:
```bash
cd etl
python pipeline.py --config config/vellore_mapping.yaml
```

**Verify**:
```sql
SELECT COUNT(*) FROM parcels_master;
SELECT COUNT(*) FROM parcels_simplified;
SELECT COUNT(*) FROM parcels_master WHERE label_point IS NOT NULL;
```

**Expected Outcome**: 
- New tables populated with data
- label_point pre-computed and stored
- Partitions auto-created

### Phase 2: Update Tile Generation (Do This Second) ⚠️

**Why Second?**
- ETL must complete first (needs data in new tables)
- Tile generation currently uses legacy tables
- Small code change, big performance benefit

**What Needs Changing**:

**File**: `backend/tile_server/utils/generate_tile.py`

**Current** (line 38-46):
```python
query = """
    SELECT parcel_uuid,
           survey_num,
           ST_AsEWKB(geom),
           ST_AsEWKB(ST_PointOnSurface(geom)) AS label_point  # ← Computes on-the-fly
    FROM parcels_simplified
    WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
      AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326));
"""
```

**Updated**:
```python
query = """
    SELECT parcel_uuid,
           survey_num,
           ST_AsEWKB(geom),
           ST_AsEWKB(label_point) AS label_point  # ← Uses pre-computed value
    FROM parcels_simplified
    WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
      AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326));
"""
```

**Key Change**: 
- Replace `ST_PointOnSurface(geom)` with `label_point`
- Table name stays the same (`parcels_simplified`) but now uses partitioned version

**Why This Order?**
1. ETL creates the data with pre-computed label_point
2. Tile generation then uses that pre-computed data
3. If we update tile generation first, it will fail (no data in new tables yet)

### Phase 3: Test & Verify

1. **Clear tile cache** (optional):
   ```bash
   rm -rf backend/cache/*
   ```

2. **Start backend**:
   ```bash
   cd backend
   uvicorn main:app --reload
   ```

3. **Test tiles**: Open frontend, verify tiles load with survey numbers

4. **Test identify**: Click parcels, verify information displays

## Why This Sequence?

### Option A: Run ETL First (Recommended) ✅

```
1. Run ETL → Populate new tables
2. Update tile generation → Use new tables
3. Test → Verify everything works
```

**Benefits**:
- Validates ETL works end-to-end
- Creates data needed for tile generation
- Clear separation of concerns
- Easy to debug (if ETL fails, fix it before touching tile generation)

### Option B: Update Tile Generation First ❌

```
1. Update tile generation → But no data in new tables yet!
2. Run ETL → Now data exists
3. Test → Should work now
```

**Problems**:
- Tile generation will fail until ETL runs (no data)
- Harder to debug (is it tile code or missing data?)
- Breaks existing functionality temporarily

## Answer to Your Questions

### Q: Should we run the ETL?

**A: Yes, run it first!** This validates the entire pipeline and creates the data needed for tile generation.

### Q: What about tile generation? Should we update it now or later?

**A: Update it after ETL runs.** Here's why:

1. **ETL must run first** - Tile generation needs data in new tables
2. **Small change, big benefit** - Just replace `ST_PointOnSurface(geom)` with `label_point`
3. **Performance improvement** - Pre-computed label_point = faster tiles
4. **Easy rollback** - If issues, can revert the one-line change

### Q: What about tile_server which was working on old tables?

**A: Update it in Phase 2 (after ETL).** The change is minimal:

- **Current**: Computes `label_point` on every tile request (slow)
- **New**: Uses pre-computed `label_point` from database (fast)
- **Table name**: Same (`parcels_simplified`), but now partitioned version

The tile server will automatically use the new partitioned table once:
1. ETL populates it
2. Query is updated to use `label_point` column

## Migration Strategy Summary

```
┌─────────────────────────────────────────────────────────┐
│ Phase 1: Run ETL (DO THIS FIRST)                        │
│                                                          │
│  python pipeline.py --config config/vellore_mapping.yaml│
│                                                          │
│  ✅ Validates entire ETL pipeline                        │
│  ✅ Populates parcels_master & parcels_simplified       │
│  ✅ Pre-computes label_point                            │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 2: Update Tile Generation (AFTER ETL)            │
│                                                          │
│  Update: backend/tile_server/utils/generate_tile.py    │
│  Change: ST_PointOnSurface(geom) → label_point         │
│                                                          │
│  ✅ Uses pre-computed label_point (faster)              │
│  ✅ Works with partitioned tables                       │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 3: Test & Verify                                  │
│                                                          │
│  - Clear tile cache                                     │
│  - Start backend                                        │
│  - Test tiles load correctly                            │
│  - Test identify API                                    │
└─────────────────────────────────────────────────────────┘
```

## Rollback Plan

If anything goes wrong:

1. **ETL fails**: Fix ETL issues, legacy tables still work
2. **Tile generation breaks**: Revert one-line change in `generate_tile.py`
3. **Data issues**: Legacy tables still exist (if not dropped)

## Expected Timeline

- **Phase 1 (ETL)**: 5-10 minutes (depending on data size)
- **Phase 2 (Tile Update)**: 2 minutes (one-line change)
- **Phase 3 (Testing)**: 5-10 minutes

**Total**: ~15-20 minutes for complete migration

## Success Criteria

✅ ETL completes without errors
✅ New tables have data (verify counts match)
✅ label_point column populated
✅ Tiles load correctly after update
✅ Survey numbers appear on tiles (label_point working)
✅ Identify API works
✅ Performance improved (faster tile generation)

## Related Documentation

- [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) - Detailed migration steps
- [NEXT_STEPS.md](../etl/NEXT_STEPS.md) - ETL next steps
- [ETL.md](ETL.md) - ETL documentation
- [TILES.md](TILES.md) - Tile generation details

