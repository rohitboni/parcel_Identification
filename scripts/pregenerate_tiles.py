#!/usr/bin/env python3
"""
Optimized Tile Pre-generation Script

Pre-generates raster tiles for selected states/districts at zoom levels 15-18.
Supports both interactive and CLI modes.

Key Features:
- Optimized: Only generates tiles that contain parcels (no empty tiles)
- Fast: Parallel processing with configurable workers
- Border-aware: Border tiles automatically include parcels from all adjacent districts
- Flexible: Interactive mode for exploration, CLI mode for automation

Usage:
    # Interactive mode (default)
    python pregenerate_tiles.py
    
    # CLI mode
    python pregenerate_tiles.py --state-code TN --district-code VELLORE
    python pregenerate_tiles.py --state-code TN --district-code VELLORE --zoom-levels 15,16,17,18 --workers 8
"""

import psycopg2
import sys
import os
import argparse
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Set
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Load .env from project root (scripts/ is one level down from root)
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)

# Add backend directory to path (scripts folder is one level up from backend)
backend_dir = project_root / "backend"
sys.path.insert(0, str(backend_dir))

# Import from backend
from config import DB_CONFIG, TABLE_MASTER, TABLE_SIMPLIFIED
from tile_server.utils.tile_utils import latlon_to_tile
from tile_server.utils.generate_tile import generate_raster_tile
from tile_server.utils.cache_manager import get_tile, save_tile

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_states_from_db(conn) -> List[Dict]:
    """Get list of states with parcel counts from database."""
    cur = conn.cursor()
    try:
        query = f"""
            SELECT 
                state_code,
                state,
                COUNT(*) as parcel_count
            FROM {TABLE_MASTER}
            WHERE state_code IS NOT NULL AND state IS NOT NULL
            GROUP BY state_code, state
            ORDER BY state_code
        """
        cur.execute(query)
        results = cur.fetchall()
        
        states = []
        for state_code, state_name, count in results:
            states.append({
                'code': state_code,
                'name': state_name,
                'count': count
            })
        return states
    finally:
        cur.close()


def get_districts_from_db(conn, state_code: str) -> List[Dict]:
    """Get list of districts for a state with parcel counts."""
    cur = conn.cursor()
    try:
        query = f"""
            SELECT 
                district_code,
                district_name,
                COUNT(*) as parcel_count
            FROM {TABLE_MASTER}
            WHERE state_code = %s 
                AND district_code IS NOT NULL 
                AND district_name IS NOT NULL
            GROUP BY district_code, district_name
            ORDER BY district_name
        """
        cur.execute(query, (state_code.upper(),))
        results = cur.fetchall()
        
        districts = []
        for district_code, district_name, count in results:
            districts.append({
                'code': district_code,
                'name': district_name,
                'count': count
            })
        return districts
    finally:
        cur.close()


def get_tiles_with_parcels(state_code: str, district_code: str, zoom_levels: List[int]) -> Set[Tuple[int, int, int]]:
    """
    Get all tile coordinates that contain parcels for the given district.
    
    Optimized approach:
    1. Query only bounding boxes (not full geometries) - minimal memory
    2. Compute tiles in Python - fast computation
    3. Use set to avoid duplicates - no overlap issues
    
    Args:
        state_code: State code (e.g., 'TN')
        district_code: District code (e.g., 'VELLORE')
        zoom_levels: List of zoom levels to process
    
    Returns:
        Set of (zoom, x, y) tuples for tiles that contain parcels
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    logger.info(f"Querying parcel bounding boxes for {state_code}/{district_code}...")
    
    # Use simplified table for faster queries
    query = f"""
        SELECT 
            ST_XMin(geom) as minx,
            ST_YMin(geom) as miny,
            ST_XMax(geom) as maxx,
            ST_YMax(geom) as maxy
        FROM {TABLE_SIMPLIFIED}
        WHERE state_code = %s AND district_code = %s;
    """
    
    cur.execute(query, (state_code, district_code))
    parcel_bounds = cur.fetchall()
    
    cur.close()
    conn.close()
    
    if not parcel_bounds:
        logger.warning(f"No parcels found for state_code={state_code}, district_code={district_code}")
        return set()
    
    logger.info(f"Found {len(parcel_bounds)} parcels")
    logger.info("Computing tiles from bounding boxes...")
    
    tiles_with_parcels = set()
    
    for minx, miny, maxx, maxy in parcel_bounds:
        if minx is None or miny is None or maxx is None or maxy is None:
            continue
            
        for zoom in zoom_levels:
            x_min, y_max = latlon_to_tile(maxy, minx, zoom)
            x_max, y_min = latlon_to_tile(miny, maxx, zoom)
            
            for x in range(x_min, x_max + 1):
                for y in range(y_min, y_max + 1):
                    tiles_with_parcels.add((zoom, x, y))
    
    logger.info(f"Computed {len(tiles_with_parcels)} unique tiles across all zoom levels")
    
    return tiles_with_parcels


def generate_tile_safe(z: int, x: int, y: int, state_code: str = None, district_code: str = None, force: bool = False) -> Tuple[bool, int]:
    """
    Generate a single tile, handling errors gracefully.
    
    Note: This function generates tiles with ALL parcels in the tile (not filtered by district).
    This ensures border tiles between adjacent districts contain parcels from all districts.
    
    Args:
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate
        state_code: State code for cache organization (e.g., 'KA')
        district_code: District code for cache organization (e.g., '630')
        force: If True, regenerate even if cached
    
    Returns:
        Tuple (success: bool, generated: int) where generated is 1 if new, 0 if cached
    """
    try:
        # Check S3 only (no local cache) if not forcing regeneration
        if not force:
            existing_tile = get_tile(z, x, y, state_code, district_code)
            if existing_tile:
                return (True, 0)  # Already exists in S3
        
        # Generate tile (includes ALL parcels in tile, regardless of district)
        # This is correct for border tiles that contain parcels from multiple districts
        tile_data = generate_raster_tile(z, x, y)
        
        # Save to S3 only
        save_tile(z, x, y, tile_data, state_code, district_code)
        
        return (True, 1)  # Generated
    except Exception as e:
        logger.error(f"Error generating tile {z}/{x}/{y}: {e}")
        return (False, 0)


def interactive_selection():
    """Interactive selection of states and districts."""
    print("=" * 60)
    print("Tile Pre-generation Script (Interactive Mode)")
    print("=" * 60)
    print()
    
    # Connect to database
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logger.info(f"Connected to database: {DB_CONFIG['database']}")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)
    
    try:
        # Get states
        print("=" * 60)
        print("Loading states from database...")
        print("=" * 60)
        states = get_states_from_db(conn)
        
        if not states:
            print("No states found in database!")
            return None, None
        
        print(f"\nFound {len(states)} state(s):\n")
        for i, state in enumerate(states, 1):
            print(f"  [{i}] {state['name']:<30} ({state['code']:<5}) - {state['count']:>12,} parcels")
        
        # Select state
        while True:
            try:
                choice = input(f"\nSelect state (1-{len(states)}, or 'q' to quit): ").strip()
                if choice.lower() == 'q':
                    return None, None
                
                state_idx = int(choice) - 1
                if 0 <= state_idx < len(states):
                    selected_state = states[state_idx]
                    break
                else:
                    print(f"Please enter a number between 1 and {len(states)}")
            except ValueError:
                print("Please enter a valid number or 'q' to quit")
        
        print(f"\nSelected State: {selected_state['name']} ({selected_state['code']})")
        
        # Get districts for selected state
        print("\n" + "=" * 60)
        print("Loading districts from database...")
        print("=" * 60)
        districts = get_districts_from_db(conn, selected_state['code'])
        
        if not districts:
            print("No districts found for this state!")
            return selected_state['code'], None
        
        print(f"\nFound {len(districts)} district(s) in {selected_state['name']}:\n")
        for i, district in enumerate(districts, 1):
            print(f"  [{i}] {district['name']:<30} ({district['code']:<5}) - {district['count']:>12,} parcels")
        print(f"  [{len(districts) + 1}] ALL districts")
        
        # Select districts
        while True:
            try:
                choice = input(f"\nSelect district(s) (1-{len(districts)}, comma-separated for multiple, '{len(districts) + 1}' for ALL, or 'q' to quit): ").strip()
                if choice.lower() == 'q':
                    return None, None
                
                if choice == str(len(districts) + 1):
                    # ALL districts selected
                    selected_districts = districts
                    break
                
                # Parse comma-separated selections
                indices = [int(x.strip()) - 1 for x in choice.split(',')]
                if all(0 <= idx < len(districts) for idx in indices):
                    selected_districts = [districts[idx] for idx in indices]
                    break
                else:
                    print(f"Please enter numbers between 1 and {len(districts)}, or '{len(districts) + 1}' for ALL")
            except ValueError:
                print("Please enter valid numbers separated by commas, or 'q' to quit")
        
        print("\n" + "=" * 60)
        print("Selected district(s):")
        print("=" * 60)
        for district in selected_districts:
            print(f"  ✓ {district['name']:<30} ({district['code']:<5}): {district['count']:>12,} parcels")
        
        total_parcels = sum(d['count'] for d in selected_districts)
        print("=" * 60)
        print(f"Total parcels: {total_parcels:,}")
        print("=" * 60)
        
        return selected_state['code'], selected_districts
        
    finally:
        conn.close()


def pregenerate_district_tiles(
    state_code: str,
    district_code: str,
    zoom_levels: List[int] = [15, 16, 17, 18],
    force_regenerate: bool = False,
    max_workers: int = 4
):
    """
    Pre-generate all tiles for a district using optimized approach.
    
    Uses optimized approach:
    - Single database query for bounding boxes (minimal memory)
    - Python computation to find tiles (fast)
    - Only generates tiles that actually contain parcels (no empty tiles)
    - Parallel processing for speed
    
    Important: Border tiles (tiles on district boundaries) will automatically contain
    parcels from ALL adjacent districts because tile generation queries all parcels
    in the tile's bounding box, not just parcels from this district. This ensures
    correct rendering of border regions.
    
    Args:
        state_code: State code (e.g., 'TN')
        district_code: District code (e.g., 'VELLORE')
        zoom_levels: List of zoom levels to generate (default: [15, 16, 17, 18])
        force_regenerate: If True, regenerate tiles even if they exist in cache
        max_workers: Number of parallel workers for tile generation
    """
    logger.info(f"Starting tile pre-generation for state_code={state_code}, district_code={district_code}")
    logger.info(f"Zoom levels: {zoom_levels}")
    logger.info(f"Force regenerate: {force_regenerate}")
    logger.info(f"Parallel workers: {max_workers}")
    logger.info("Note: Border tiles will include parcels from all adjacent districts")
    
    # Get all tiles that contain parcels (optimized: 1 query, compute in Python)
    all_tiles = get_tiles_with_parcels(state_code, district_code, zoom_levels)
    
    if not all_tiles:
        logger.warning("No tiles found with parcels")
        return
    
    # Group tiles by zoom level for processing
    tiles_by_zoom = {}
    for zoom, x, y in all_tiles:
        if zoom not in tiles_by_zoom:
            tiles_by_zoom[zoom] = []
        tiles_by_zoom[zoom].append((x, y))
    
    total_tiles = len(all_tiles)
    total_generated = 0
    total_skipped = 0
    total_errors = 0
    start_time = datetime.now()
    
    # Process each zoom level
    for zoom in zoom_levels:
        if zoom not in tiles_by_zoom:
            logger.warning(f"No tiles found for zoom level {zoom}")
            continue
        
        tiles = tiles_by_zoom[zoom]
        logger.info(f"\nProcessing zoom level {zoom}: {len(tiles)} tiles to generate")
        
        # Generate tiles in parallel
        generated_count = 0
        skipped_count = 0
        error_count = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tile generation tasks
            future_to_tile = {
                executor.submit(generate_tile_safe, zoom, x, y, state_code, district_code, force_regenerate): (x, y)
                for x, y in tiles
            }
            
            # Process completed tasks
            for future in as_completed(future_to_tile):
                x, y = future_to_tile[future]
                try:
                    success, generated = future.result()
                    if success:
                        if generated > 0:
                            generated_count += 1
                        else:
                            skipped_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    logger.error(f"Exception for tile {zoom}/{x}/{y}: {e}")
                    error_count += 1
                
                # Progress logging
                processed = generated_count + skipped_count + error_count
                if processed % 100 == 0:
                    logger.info(f"Progress: {processed}/{len(tiles)} tiles processed ({100 * processed / len(tiles):.1f}%)")
        
        logger.info(f"Zoom {zoom} complete: {generated_count} generated, {skipped_count} skipped, {error_count} errors")
        total_generated += generated_count
        total_skipped += skipped_count
        total_errors += error_count
    
    # Summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print("\n" + "=" * 60)
    print("Tile Pre-generation Complete!")
    print("=" * 60)
    print(f"Total tiles with parcels: {total_tiles:,}")
    print(f"  Generated: {total_generated:,}")
    print(f"  Already cached: {total_skipped:,}")
    print(f"  Errors: {total_errors:,}")
    print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
    print("=" * 60)


def pregenerate_tiles_for_districts(
    state_code: str,
    districts: List[Dict],
    zoom_levels: List[int] = [15, 16, 17, 18],
    force_regenerate: bool = False,
    max_workers: int = 4
):
    """Pre-generate tiles for multiple districts."""
    print("\n" + "=" * 60)
    print("Starting Tile Pre-generation")
    print("=" * 60)
    print(f"State: {state_code}")
    print(f"Districts: {len(districts)}")
    print(f"Zoom levels: {zoom_levels}")
    print(f"Parallel workers: {max_workers}")
    print("=" * 60)
    
    total_parcels = sum(d['count'] for d in districts)
    print(f"Total parcels: {total_parcels:,}")
    print("=" * 60)
    
    # Process each district
    for district_idx, district in enumerate(districts, 1):
        print(f"\n{'=' * 60}")
        print(f"Processing District {district_idx}/{len(districts)}: {district['name']} ({district['code']})")
        print(f"{'=' * 60}")
        
        pregenerate_district_tiles(
            state_code=state_code,
            district_code=district['code'],
            zoom_levels=zoom_levels,
            force_regenerate=force_regenerate,
            max_workers=max_workers
        )


def main():
    """Main entry point - supports both interactive and CLI modes."""
    parser = argparse.ArgumentParser(
        description='Pre-generate tiles for districts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (default)
  python pregenerate_tiles.py
  
  # CLI mode - single district
  python pregenerate_tiles.py --state-code TN --district-code VELLORE
  
  # CLI mode - specific zoom levels and workers
  python pregenerate_tiles.py --state-code TN --district-code VELLORE --zoom-levels 15,16 --workers 8
  
  # CLI mode - force regeneration
  python pregenerate_tiles.py --state-code TN --district-code VELLORE --force-regenerate
        """
    )
    
    parser.add_argument(
        '--state-code',
        type=str,
        help='State code (e.g., TN). If not provided, interactive mode is used.'
    )
    
    parser.add_argument(
        '--district-code',
        type=str,
        help='District code (e.g., VELLORE). If not provided, interactive mode is used.'
    )
    
    parser.add_argument(
        '--zoom-levels',
        type=str,
        default='15,16,17,18',
        help='Comma-separated zoom levels (default: 15,16,17,18)'
    )
    
    parser.add_argument(
        '--force-regenerate',
        action='store_true',
        help='Force regeneration of tiles even if they exist in cache'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=4,
        help='Number of parallel workers (default: 4)'
    )
    
    args = parser.parse_args()
    
    # Debug: Check what arguments were parsed
    logger.debug(f"Parsed args - state_code: '{args.state_code}', district_code: '{args.district_code}'")
    
    # Determine mode: CLI or interactive
    # Check if both required arguments are provided (explicit check)
    if args.state_code and args.district_code:
        # CLI mode - validate and run
        print(f"\n{'=' * 60}")
        print(f"CLI Mode: Generating tiles for {args.state_code}/{args.district_code}")
        print(f"{'=' * 60}\n")
        logger.info(f"CLI mode: state_code={args.state_code}, district_code={args.district_code}")
        
        try:
            zoom_levels = [int(z.strip()) for z in args.zoom_levels.split(',')]
        except ValueError:
            logger.error(f"Invalid zoom levels: {args.zoom_levels}")
            sys.exit(1)
        
        # Validate zoom levels
        if not all(15 <= z <= 18 for z in zoom_levels):
            logger.error("Zoom levels must be between 15 and 18")
            sys.exit(1)
        
        # Run pre-generation for single district
        pregenerate_district_tiles(
            state_code=args.state_code,
            district_code=args.district_code,
            zoom_levels=zoom_levels,
            force_regenerate=args.force_regenerate,
            max_workers=args.workers
        )
    else:
        # Interactive mode
        if args.state_code or args.district_code:
            # User provided one but not both - show error
            logger.error("Both --state-code and --district-code are required for CLI mode")
            logger.error("Either provide both arguments or run without arguments for interactive mode")
            parser.print_help()
            sys.exit(1)
        
        # No arguments provided - interactive mode
        print("\n" + "=" * 60)
        print("Tile Pre-generation Script (Interactive Mode)")
        print("=" * 60)
        print("This script will pre-generate raster tiles for selected areas.")
        print("Tiles will be cached for faster map loading.")
        print("Note: Only tiles containing parcels will be generated (optimized).")
        print()
        
        # Interactive selection
        state_code, districts = interactive_selection()
        
        if not state_code or not districts:
            print("\nNo selection made. Exiting.")
            return
        
        # Ask for zoom levels
        print("\n" + "=" * 60)
        zoom_input = input("Enter zoom levels (comma-separated, default: 15,16,17,18): ").strip()
        if zoom_input:
            try:
                zoom_levels = [int(z.strip()) for z in zoom_input.split(',')]
                if not all(15 <= z <= 18 for z in zoom_levels):
                    print("Invalid zoom levels. Using default: 15,16,17,18")
                    zoom_levels = [15, 16, 17, 18]
            except ValueError:
                print("Invalid format. Using default: 15,16,17,18")
                zoom_levels = [15, 16, 17, 18]
        else:
            zoom_levels = [15, 16, 17, 18]
        
        # Ask for workers
        workers_input = input("Enter number of parallel workers (default: 4): ").strip()
        try:
            max_workers = int(workers_input) if workers_input else 4
        except ValueError:
            max_workers = 4
        
        # Confirm before proceeding
        print("\n" + "=" * 60)
        total_parcels = sum(d['count'] for d in districts)
        print(f"You are about to pre-generate tiles for:")
        print(f"  State: {state_code}")
        print(f"  Districts: {len(districts)}")
        print(f"  Total parcels: {total_parcels:,}")
        print(f"  Zoom levels: {zoom_levels}")
        print(f"  Parallel workers: {max_workers}")
        print("=" * 60)
        
        confirm = input("\nProceed with tile generation? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("Cancelled.")
            return
        
        # Pre-generate tiles
        pregenerate_tiles_for_districts(
            state_code=state_code,
            districts=districts,
            zoom_levels=zoom_levels,
            force_regenerate=False,
            max_workers=max_workers
        )


if __name__ == "__main__":
    main()
