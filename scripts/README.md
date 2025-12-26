# Scripts Directory

This directory contains utility scripts for managing and operating the Parcel Identification MVP system.

## Available Scripts

### `pregenerate_tiles.py`

**Purpose:** Pre-generate raster tiles for districts to improve map loading performance.

**Features:**
- Optimized tile generation (only generates tiles with parcels, no empty tiles)
- Parallel processing for faster generation
- Interactive and CLI modes
- Border-aware (includes parcels from adjacent districts)

**Usage:**
```bash
# Interactive mode
python scripts/pregenerate_tiles.py

# CLI mode
python scripts/pregenerate_tiles.py --state-code KA --district-code 630

# With options
python scripts/pregenerate_tiles.py --state-code KA --district-code 630 --zoom-levels 15,16,17,18 --workers 8
```

**See:** `../SAMPLE_COMMANDS.md` for detailed examples.

---

### `check_db.py`

**Purpose:** Check available states and districts in the database.

**Usage:**
```bash
python scripts/check_db.py
```

**Output:**
- Lists all states with parcel counts
- Lists all districts for each state
- Provides sample commands for tile pre-generation

---

## Running Scripts

All scripts should be run from the project root directory:

```bash
# From project root
cd /path/to/parcel_Identification

# Activate virtual environment
source venv/bin/activate

# Run scripts
python scripts/pregenerate_tiles.py --help
python scripts/check_db.py
```

## Requirements

- Python 3.11+
- Virtual environment activated
- Database connection configured in `.env`
- All dependencies installed (`pip install -r requirements.txt`)

## Notes

- Scripts automatically detect the `backend/` directory for imports
- Database configuration is loaded from `.env` file
- All scripts use the same database configuration as the main application

