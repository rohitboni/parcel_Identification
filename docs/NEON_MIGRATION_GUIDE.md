# Neon Database Migration Guide

## Overview

The `migrate_neon_data.py` script provides an **interactive migration** tool that allows you to selectively migrate data by state and district.

## Features

- ✅ **Interactive selection** - Query database and choose what to migrate
- ✅ **State selection** - See all available states with parcel counts
- ✅ **District selection** - Choose specific districts or migrate all
- ✅ **Batch processing** - Processes data in configurable batches
- ✅ **Progress tracking** - Real-time progress updates
- ✅ **Duplicate detection** - Warns if data already exists
- ✅ **Non-interactive mode** - Supports automation with CLI arguments

---

## Usage

### Interactive Mode (Recommended)

```bash
python migrate_neon_data.py
```

**Flow:**
1. Script queries database for available states
2. Displays states with parcel counts
3. Prompts: "Select state (1-N):"
4. Displays districts in selected state
5. Prompts: "Select district(s) (1-N, comma-separated, or 'all'):"
6. Shows summary and asks for confirmation
7. Migrates selected data in batches

**Example Session:**
```
============================================================
Neon Database Migration - Interactive Selection
============================================================

Found 1 state(s):

  [1] Karnataka                    (ka   ) -  1,452,025 parcels

Select state (1-1): 1

Selected State: Karnataka (ka)

Found 8 district(s) in Karnataka:

  [1] Tumakuru                     (432056    ) -    432,056 parcels
  [2] Chikkaballapura              (323438    ) -    323,438 parcels
  [3] Kolara                       (248593    ) -    248,593 parcels
  [4] Ramanagara                   (157202    ) -    157,202 parcels
  [5] Bengaluru (Rural)            (150804    ) -    150,804 parcels
  [6] Bengaluru (Urban)            (139923    ) -    139,923 parcels
  [7] Mandya                       (8         ) -          8 parcels
  [8] Chitradurga                  (1         ) -          1 parcels
  [9] ALL districts

Select district(s) (1-9, comma-separated for multiple, or 'all'): 1,2

============================================================
Selected 2 district(s):
============================================================
  ✓ Tumakuru                     (432056    ):    432,056 parcels
  ✓ Chikkaballapura              (323438    ):    323,438 parcels
============================================================
Total parcels to migrate: 755,494
============================================================

Proceed with migration? (yes/no): yes
```

---

### Non-Interactive Mode

For automation or scripting:

```bash
# Migrate specific state/district
python migrate_neon_data.py --state-code=ka --district-code=526 --batch-size=1000

# Migrate multiple districts
python migrate_neon_data.py --state-code=ka --district-code=526 527 528 --batch-size=500
```

**Arguments:**
- `--state-code`: State code (e.g., "ka")
- `--district-code`: One or more district codes
- `--batch-size`: Batch size for inserts (default: 1000)

---

## Migration Process

### What Happens During Migration

1. **Pre-create Partitions**
   - Creates state and district partitions automatically
   - Sets up indexes (GIST spatial, btree on state/district)

2. **Transform Data** (per batch)
   - Reads from `cadastrals` table
   - Transforms geometry: EPSG:32643 → EPSG:4326
   - Maps columns: PascalCase → snake_case
   - Computes `label_point` using `ST_PointOnSurface`
   - Generates UUIDs

3. **Insert Data**
   - Batch insert into `parcels_master_neon`
   - Batch insert into `parcels_simplified_neon`
   - Commits after each batch

4. **Progress Updates**
   - Shows batch progress
   - Shows total progress percentage
   - Logs insert counts

---

## Performance

**Expected Performance:**
- **Batch size:** 1000 rows (default, configurable)
- **Time per batch:** ~2-5 seconds
- **Throughput:** ~200-500 rows/second
- **Total time for 755K parcels:** ~25-60 minutes

**Factors:**
- Network latency (Neon is remote)
- Geometry transformation overhead
- Label point computation
- Batch insert performance

---

## Safety Features

### Duplicate Detection

The script checks if data already exists before migration:

```
WARNING: 432,056 parcels already exist in parcels_master_neon for selected state/districts!
This migration will create duplicates. Continue anyway? Continue? (yes/no):
```

### Validation

- Validates state/district selection
- Checks for null geometries
- Validates required fields
- Handles errors gracefully

---

## Examples

### Example 1: Migrate Single District

```bash
python migrate_neon_data.py
# Select state: 1 (Karnataka)
# Select district: 5 (Bengaluru Rural)
# Confirm: yes
```

### Example 2: Migrate Multiple Districts

```bash
python migrate_neon_data.py
# Select state: 1
# Select districts: 1,2,3 (Tumakuru, Chikkaballapura, Kolara)
# Confirm: yes
```

### Example 3: Migrate All Districts

```bash
python migrate_neon_data.py
# Select state: 1
# Select districts: 9 (ALL districts)
# Confirm: yes
```

### Example 4: Custom Batch Size

```bash
python migrate_neon_data.py --batch-size=500
# Smaller batches = slower but less memory usage
```

---

## Verification

After migration, verify the data:

```sql
-- Check row counts
SELECT COUNT(*) FROM parcels_master_neon;
SELECT COUNT(*) FROM parcels_simplified_neon;

-- Check by district
SELECT district_name, COUNT(*) 
FROM parcels_master_neon 
GROUP BY district_name 
ORDER BY COUNT(*) DESC;

-- Verify geometry CRS
SELECT ST_SRID(geom) FROM parcels_master_neon LIMIT 1;
-- Should return: 4326

-- Check label points
SELECT COUNT(*) as total,
       COUNT(label_point) as with_label_point
FROM parcels_master_neon;
```

---

## Troubleshooting

### Issue: "No states found"
- Check database connection
- Verify `cadastrals` table exists
- Check if data has `State_Code` populated

### Issue: "No districts found"
- Verify selected state has districts
- Check `District_Code` is populated

### Issue: Migration is slow
- Reduce batch size: `--batch-size=500`
- Check network connection to Neon
- Monitor database performance

### Issue: Duplicate data warning
- Data already migrated for selected state/district
- Choose different districts or clear existing data first

---

## Notes

- ✅ Original `cadastrals` table is **never modified**
- ✅ Migration can be run multiple times (creates duplicates)
- ✅ Use interactive mode for first-time migration
- ✅ Use non-interactive mode for automation/CI
- ✅ Progress is logged to console
- ✅ All data transformed to EPSG:4326 for web compatibility

