# Sample Commands for Tile Pre-generation Script

## Database Summary

**State:** Karnataka (State Code: `KA`)
- **Total Parcels:** 1,019,974

**Top Districts (by parcel count):**
- `630` - Chikkaballapura (323,435 parcels)
- `542` - Kolara (248,592 parcels)  
- `631` - Ramanagara (157,198 parcels)
- `526` - Bengaluru (Rural) (150,804 parcels)
- `525` - Bengaluru (Urban) (139,923 parcels)

---

## Quick Start

### 1. Check Available States/Districts
```bash
# Activate virtual environment first
source venv/bin/activate

# Check database
python scripts/check_db.py
```

### 2. Interactive Mode (Recommended for First Time)
```bash
# Activate virtual environment
source venv/bin/activate

# Run interactive mode
python scripts/pregenerate_tiles.py
```

The script will:
- Show available states
- Let you select a state
- Show districts for that state
- Let you select one or more districts
- Ask for zoom levels and workers
- Confirm before starting

---

## CLI Mode Commands

### Basic Usage
```bash
# Activate virtual environment
source venv/bin/activate

# Generate tiles for a single district (default zoom levels: 15,16,17,18)
python scripts/pregenerate_tiles.py --state-code KA --district-code 630

# Generate tiles for Bengaluru (Rural)
python scripts/pregenerate_tiles.py --state-code KA --district-code 526

# Generate tiles for Bengaluru (Urban)
python scripts/pregenerate_tiles.py --state-code KA --district-code 525
```

### Custom Zoom Levels
```bash
# Generate only zoom levels 15 and 16
python scripts/pregenerate_tiles.py --state-code KA --district-code 630 --zoom-levels 15,16

# Generate only zoom level 17
python scripts/pregenerate_tiles.py --state-code KA --district-code 630 --zoom-levels 17

# Generate all zoom levels (explicit)
python scripts/pregenerate_tiles.py --state-code KA --district-code 630 --zoom-levels 15,16,17,18
```

### Parallel Processing (Faster)
```bash
# Use 8 parallel workers (faster for large districts)
python scripts/pregenerate_tiles.py --state-code KA --district-code 630 --workers 8

# Use 16 parallel workers (very fast, but uses more CPU/memory)
python scripts/pregenerate_tiles.py --state-code KA --district-code 630 --workers 16

# Combine custom zoom levels and workers
python scripts/pregenerate_tiles.py --state-code KA --district-code 630 --zoom-levels 15,16,17,18 --workers 8
```

### Force Regeneration
```bash
# Regenerate tiles even if they exist in cache
python scripts/pregenerate_tiles.py --state-code KA --district-code 630 --force-regenerate

# Force regenerate with custom settings
python scripts/pregenerate_tiles.py --state-code KA --district-code 630 --zoom-levels 15,16 --workers 8 --force-regenerate
```

---

## Complete Examples

### Example 1: Generate tiles for Chikkaballapura (largest district)
```bash
source venv/bin/activate
python scripts/pregenerate_tiles.py --state-code KA --district-code 630 --zoom-levels 15,16,17,18 --workers 8
```

### Example 2: Quick test with only zoom level 15
```bash
source venv/bin/activate
python scripts/pregenerate_tiles.py --state-code KA --district-code 526 --zoom-levels 15 --workers 4
```

### Example 3: Generate for multiple districts (run separately)
```bash
source venv/bin/activate

# District 1
python scripts/pregenerate_tiles.py --state-code KA --district-code 630 --workers 8

# District 2
python scripts/pregenerate_tiles.py --state-code KA --district-code 542 --workers 8

# District 3
python scripts/pregenerate_tiles.py --state-code KA --district-code 631 --workers 8
```

### Example 4: Batch script for all major districts
```bash
#!/bin/bash
source venv/bin/activate

districts=("630" "542" "631" "526" "525")

for district in "${districts[@]}"; do
    echo "Processing district: $district"
    python scripts/pregenerate_tiles.py --state-code KA --district-code $district --workers 8
done
```

---

## Performance Tips

1. **Start Small**: Test with one district and zoom level 15 first
2. **Use Workers**: Increase `--workers` for faster processing (4-8 is good)
3. **Zoom Levels**: Higher zoom levels (17-18) take much longer
4. **Cache**: Script automatically skips tiles that already exist
5. **Monitor**: Watch disk space - tiles can use significant storage

---

## Expected Output

```
Starting tile pre-generation for state_code=KA, district_code=630
Zoom levels: [15, 16, 17, 18]
Force regenerate: False
Parallel workers: 8
Note: Border tiles will include parcels from all adjacent districts
Querying parcel bounding boxes for KA/630...
Found 323435 parcels
Computing tiles from bounding boxes...
Computed 45231 unique tiles across all zoom levels

Processing zoom level 15: 1234 tiles to generate
Progress: 100/1234 tiles processed (8.1%)
Progress: 200/1234 tiles processed (16.2%)
...
Zoom 15 complete: 1234 generated, 0 skipped, 0 errors

...

============================================================
Tile Pre-generation Complete!
============================================================
Total tiles with parcels: 45,231
  Generated: 45,231
  Already cached: 0
  Errors: 0
Duration: 1234.5 seconds (20.6 minutes)
============================================================
```

---

## Troubleshooting

### Database Connection Error
```bash
# Check if database is running
psql -h 127.0.0.1 -U postgres -d parcels_db_new -c "SELECT 1;"

# Check .env file
cat .env
```

### Module Not Found
```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Install dependencies if needed
pip install -r requirements.txt
```

### Out of Memory
```bash
# Reduce number of workers
python scripts/pregenerate_tiles.py --state-code KA --district-code 630 --workers 2
```

