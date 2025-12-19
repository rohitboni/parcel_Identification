# Performance Optimization Guide

## Current Performance Issues

### Identified Bottlenecks

1. **Query Planning Time**: 23.5ms (vs 0.2ms execution)
   - PostgreSQL planner overhead for partitioned tables
   - Can be reduced with prepared statements

2. **Connection Overhead**: ~38ms per new connection
   - Solved with connection pooling

3. **Cache Performance**: < 1ms (excellent)
   - File I/O is fast

## Performance Metrics

### Current Performance (Local DB)

- **Database Query**: 0.2-1ms execution (with spatial index)
- **Query Planning**: 20-25ms (bottleneck for partitioned tables)
- **Geometry Conversion**: ~0.1ms per parcel
- **Tile Generation**: 50-150ms total (depends on parcel count)
- **Cache Read**: < 1ms (excellent)

### Expected Performance After Optimization

- **Database Query**: 0.2-1ms execution
- **Query Planning**: 5-10ms (with prepared statements)
- **Tile Generation**: 30-100ms total
- **Cache Read**: < 1ms

## Optimizations Implemented

### 1. Connection Pooling

**File**: `backend/tile_server/utils/performance_optimizer.py`

**Benefits**:
- Reuses connections instead of creating new ones
- Reduces connection overhead from ~38ms to < 1ms
- Handles concurrent requests better

**Usage**:
```python
from backend.tile_server.utils.performance_optimizer import get_db_connection, return_db_connection

conn = get_db_connection()
# Use connection
return_db_connection(conn)
```

### 2. Query Optimization

**File**: `backend/tile_server/utils/generate_tile.py`

**Changes**:
- Put partition filters (state_code, district_code) FIRST in WHERE clause
- Helps PostgreSQL use partition pruning
- Spatial filter uses GIST index efficiently

**Before**:
```sql
WHERE geom && ST_MakeEnvelope(...) AND state_code = 'KA'
```

**After**:
```sql
WHERE state_code = 'KA' AND district_code = '526' AND geom && ST_MakeEnvelope(...)
```

### 3. Spatial Indexes

**Status**: ✅ Already exists on all partitions

**Indexes**:
- `parcels_simplified_ka_526_geom_idx` (GIST on geom)
- `parcels_simplified_ka_525_geom_idx` (GIST on geom)
- etc.

**Verification**:
```sql
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename LIKE 'parcels_simplified%' 
  AND indexdef LIKE '%GIST%';
```

### 4. Cache-First Strategy

**File**: `backend/tile_server/utils/cache_manager.py`

**Benefits**:
- Cache reads: < 1ms
- Avoids database queries for cached tiles
- Organized by state/district for easy management

## Additional Optimizations (Future)

### 1. Prepared Statements

**Benefit**: Reduces query planning time from 20-25ms to 5-10ms

**Implementation**:
```python
# Prepare statement once
cur.execute("PREPARE tile_query AS SELECT ... WHERE state_code = $1 AND ...")

# Execute multiple times with different parameters
cur.execute("EXECUTE tile_query", (state_code, district_code, ...))
```

### 2. Query Result Caching

**Benefit**: Cache query results for identical bounding boxes

**Implementation**:
- Use Redis or in-memory cache
- Key: `{state_code}_{district_code}_{minx}_{miny}_{maxx}_{maxy}`
- TTL: 5-10 minutes

### 3. Batch Geometry Conversion

**Current**: Converts geometries one by one
**Optimization**: Batch convert using vectorized operations

### 4. Parallel Tile Generation

**Benefit**: Generate multiple tiles simultaneously

**Implementation**:
- Use asyncio or multiprocessing
- Generate viewport tiles in parallel
- Limit concurrent connections to avoid overwhelming DB

## Performance Testing

### Test Query Performance

```python
import time
import psycopg2
from backend.config import DB_CONFIG, TABLE_SIMPLIFIED

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

start = time.time()
cur.execute(f"""
    SELECT COUNT(*) 
    FROM {TABLE_SIMPLIFIED}
    WHERE state_code = 'KA' 
      AND district_code = '526'
      AND geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326);
""", (minx, miny, maxx, maxy))
count = cur.fetchone()[0]
print(f"Query time: {(time.time() - start)*1000:.2f}ms")
```

### Test Cache Performance

```python
from backend.tile_server.utils.cache_manager import get_tile_from_cache
import time

start = time.time()
cached = get_tile_from_cache(z, x, y, state_code='KA', district_code='526')
print(f"Cache read: {(time.time() - start)*1000:.2f}ms")
```

## Monitoring

### Key Metrics to Monitor

1. **Query Planning Time**: Should be < 10ms
2. **Query Execution Time**: Should be < 1ms
3. **Cache Hit Rate**: Should be > 80%
4. **Tile Generation Time**: Should be < 100ms
5. **Connection Pool Usage**: Monitor pool size vs active connections

### Logging

Enable performance logging:
```python
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info(f"Query time: {time_ms}ms")
```

## Troubleshooting Slow Performance

### 1. Check Query Planning Time

```sql
EXPLAIN ANALYZE
SELECT ... FROM parcels_simplified WHERE ...;
```

Look for:
- High "Planning Time" (> 10ms)
- Missing index usage
- Sequential scans instead of index scans

### 2. Check Index Usage

```sql
SELECT schemaname, tablename, indexname 
FROM pg_indexes 
WHERE tablename LIKE 'parcels_simplified%';
```

Ensure GIST indexes exist on all partitions.

### 3. Check Cache Hit Rate

Monitor cache directory:
```bash
ls -lh cache/KA/526/15/*/*.png | wc -l
```

### 4. Check Connection Pool

Monitor active connections:
```sql
SELECT count(*) FROM pg_stat_activity WHERE datname = 'parcels_db_new';
```

### 5. Analyze Table Statistics

Update statistics for better query planning:
```sql
ANALYZE parcels_simplified;
ANALYZE parcels_simplified_ka_526;
```

## Best Practices

1. **Always use filters**: state_code and district_code when possible
2. **Check cache first**: Before generating new tiles
3. **Use connection pooling**: For concurrent requests
4. **Monitor performance**: Track query times and cache hit rates
5. **Update statistics**: Run ANALYZE after data changes

## Expected Performance Targets

- **Cache Hit**: < 1ms
- **Cache Miss (with filters)**: 30-100ms
- **Cache Miss (no filters)**: 50-150ms
- **Concurrent Requests**: Handle 10-20 requests/second

## Related Documentation

- [VIEWPORT_TILE_GENERATION.md](VIEWPORT_TILE_GENERATION.md) - Viewport-based tile generation
- [TILES.md](TILES.md) - Tile generation documentation
- [DATABASE.md](DATABASE.md) - Database setup and optimization

