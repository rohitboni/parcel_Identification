# Tile Pre-generation Script

## Overview

The `pregenerate_tiles.py` script allows you to pre-generate raster tiles for selected states and districts at zoom levels 15-18. This improves map loading performance by caching tiles in advance.

## Features

- **Interactive Selection**: Shows available states and districts from database
- **Multiple Districts**: Select individual districts or all districts for a state
- **Multiple Zoom Levels**: Generates tiles for zoom levels 15, 16, 17, and 18
- **Progress Tracking**: Shows real-time progress and statistics
- **Cache Management**: Skips already-cached tiles to save time
- **Error Handling**: Continues processing even if individual tiles fail

## Usage

### Basic Usage

```bash
cd /path/to/parcel_identification_MVP
source venv/bin/activate
python pregenerate_tiles.py
```

### Interactive Flow

1. **Select State**: The script shows all available states with parcel counts
   ```
   Found 1 state(s):
     [1] Karnataka                      (KA   ) -  1,452,025 parcels
   ```

2. **Select Districts**: Choose specific districts or all districts
   ```
   Found 14 district(s) in Karnataka:
     [1] Tumakuru                       (542       ) -    432,051 parcels
     [2] Chikkaballapura                (630       ) -    323,435 parcels
     ...
     [15] ALL districts
   ```

3. **Confirm**: Review selection and confirm to proceed
   ```
   You are about to pre-generate tiles for:
     State: KA
     Districts: 2
     Total parcels: 755,486
     Zoom levels: 15, 16, 17, 18
   ```

4. **Generation**: The script processes each district and zoom level
   ```
   Processing District 1/2: Tumakuru (542)
   Bounds: (76.123456, 13.123456) to (77.123456, 14.123456)
   
     Zoom level 15:
       Tiles to generate: 1,234
       Progress: 1,234/1,234 (100.0%)
       Generated: 800, Cached: 434, Errors: 0
   ```

## Output

Tiles are saved to the cache directory following this structure:
```
backend/cache/
  └── {state_code}/
      └── {district_code}/
          └── {z}/
              └── {x}/
                  └── {y}.png
```

Example:
```
backend/cache/KA/542/15/23439/15164.png
```

## Statistics

At the end, the script displays:
- Total tiles processed
- Number of tiles generated (new)
- Number of tiles already cached (skipped)
- Number of errors
- Total duration

Example output:
```
Tile Pre-generation Complete!
============================================================
Total tiles processed: 45,678
  Generated: 30,123
  Already cached: 15,555
  Errors: 0
Duration: 1234.5 seconds (20.6 minutes)
============================================================
```

## Performance Tips

1. **Start Small**: Test with a single district first
2. **Use Filters**: Pre-generate only for areas you'll use frequently
3. **Monitor Progress**: Large areas can take hours to process
4. **Check Cache**: Already-cached tiles are skipped automatically

## Troubleshooting

### Database Connection Error
- Check `.env` file has correct database credentials
- Verify database is running: `psql -U postgres -d parcels_db_new`

### Import Errors
- Ensure you're in the project root directory
- Activate virtual environment: `source venv/bin/activate`
- Check Python path includes backend directory

### Tile Generation Errors
- Check database has data for selected state/district
- Verify PostGIS extension is enabled
- Check disk space (tiles can use significant storage)

## Related Files

- `backend/tile_server/utils/generate_tile.py` - Tile generation logic
- `backend/tile_server/utils/cache_manager.py` - Cache management
- `backend/tile_server/utils/viewport_tiles.py` - Viewport tile utilities
- `backend/config.py` - Database configuration

