#!/usr/bin/env python3
"""
Interactive Tile Pre-generation Script

Pre-generates raster tiles for selected states/districts at zoom levels 15-18.
Shows available data from database and allows interactive selection.
"""

import psycopg2
import sys
import os
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from datetime import datetime

# Add backend directory to path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

# Import from backend (cache_manager now uses absolute paths, so no need to change directory)
from config import DB_CONFIG, TABLE_MASTER, TABLE_SIMPLIFIED
from tile_server.utils.tile_utils import bounds_to_tile_xyz, tile_xyz_to_bounds
from tile_server.utils.generate_tile import generate_raster_tile
from tile_server.utils.cache_manager import get_tile_from_cache, save_tile_to_cache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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


def get_bounds_for_area(conn, state_code: Optional[str] = None, district_code: Optional[str] = None) -> Optional[Tuple[float, float, float, float]]:
    """Get bounding box (min_lon, min_lat, max_lon, max_lat) for selected area."""
    cur = conn.cursor()
    try:
        where_clauses = []
        params = []
        
        if state_code:
            where_clauses.append("state_code = %s")
            params.append(state_code.upper())
        
        if district_code:
            where_clauses.append("district_code = %s")
            params.append(district_code)
        
        where_clause = ""
        if where_clauses:
            where_clause = "WHERE " + " AND ".join(where_clauses)
        
        query = f"""
            SELECT 
                ST_XMin(ST_Extent(geom)) as min_lon,
                ST_YMin(ST_Extent(geom)) as min_lat,
                ST_XMax(ST_Extent(geom)) as max_lon,
                ST_YMax(ST_Extent(geom)) as max_lat
            FROM {TABLE_MASTER}
            {where_clause}
        """
        
        cur.execute(query, params)
        result = cur.fetchone()
        
        if result and result[0] is not None:
            return tuple(float(x) for x in result)
        return None
    finally:
        cur.close()


def get_tiles_for_bounds(min_lon: float, min_lat: float, max_lon: float, max_lat: float, zoom: int) -> List[Tuple[int, int, int]]:
    """Get all tile coordinates (z, x, y) for a bounding box at given zoom level."""
    # Get tile coordinates for corners
    min_x, min_y = bounds_to_tile_xyz(min_lon, min_lat, zoom)
    max_x, max_y = bounds_to_tile_xyz(max_lon, max_lat, zoom)
    
    # Ensure we have the correct min/max
    tile_x_min = min(min_x, max_x)
    tile_x_max = max(min_x, max_x)
    tile_y_min = min(min_y, max_y)
    tile_y_max = max(min_y, max_y)
    
    # Generate all tiles in bounding box
    tiles = []
    for x in range(tile_x_min, tile_x_max + 1):
        for y in range(tile_y_min, tile_y_max + 1):
            tiles.append((zoom, x, y))
    
    return tiles


def generate_tile(z: int, x: int, y: int, state_code: Optional[str] = None, district_code: Optional[str] = None) -> bool:
    """Generate a single tile. Returns True if generated, False if cached."""
    try:
        # Check cache first
        cached = get_tile_from_cache(z, x, y, state_code=state_code, district_code=district_code)
        if cached:
            return False  # Already cached
        
        # Generate tile
        tile_data = generate_raster_tile(z, x, y, state_code=state_code, district_code=district_code)
        save_tile_to_cache(z, x, y, tile_data, state_code=state_code, district_code=district_code)
        return True  # Generated
    except Exception as e:
        logger.error(f"Error generating tile {z}/{x}/{y}: {e}")
        return False


def interactive_selection():
    """Interactive selection of states and districts."""
    print("=" * 60)
    print("Tile Pre-generation Script")
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


def pregenerate_tiles_for_area(state_code: str, districts: List[Dict], zoom_levels: List[int] = [15, 16, 17, 18]):
    """Pre-generate tiles for selected area across multiple zoom levels."""
    print("\n" + "=" * 60)
    print("Starting Tile Pre-generation")
    print("=" * 60)
    print(f"State: {state_code}")
    print(f"Districts: {len(districts)}")
    print(f"Zoom levels: {zoom_levels}")
    print("=" * 60)
    
    # Connect to database
    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return
    
    try:
        total_stats = {
            'total_tiles': 0,
            'generated': 0,
            'cached': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
        
        # Process each district
        for district_idx, district in enumerate(districts, 1):
            print(f"\n{'=' * 60}")
            print(f"Processing District {district_idx}/{len(districts)}: {district['name']} ({district['code']})")
            print(f"{'=' * 60}")
            
            # Get bounds for this district
            bounds = get_bounds_for_area(conn, state_code=state_code, district_code=district['code'])
            if not bounds:
                logger.warning(f"No bounds found for district {district['name']}")
                continue
            
            min_lon, min_lat, max_lon, max_lat = bounds
            print(f"Bounds: ({min_lon:.6f}, {min_lat:.6f}) to ({max_lon:.6f}, {max_lat:.6f})")
            
            # Process each zoom level
            for zoom in zoom_levels:
                print(f"\n  Zoom level {zoom}:")
                
                # Get all tiles for this area at this zoom level
                tiles = get_tiles_for_bounds(min_lon, min_lat, max_lon, max_lat, zoom)
                print(f"    Tiles to generate: {len(tiles):,}")
                
                # Generate tiles
                generated = 0
                cached = 0
                errors = 0
                
                for tile_idx, (z, x, y) in enumerate(tiles, 1):
                    if tile_idx % 100 == 0 or tile_idx == len(tiles):
                        print(f"    Progress: {tile_idx:,}/{len(tiles):,} ({100 * tile_idx / len(tiles):.1f}%)", end='\r')
                    
                    result = generate_tile(z, x, y, state_code=state_code, district_code=district['code'])
                    if result is True:
                        generated += 1
                    elif result is False:
                        cached += 1
                    else:
                        errors += 1
                
                print(f"\n    Generated: {generated:,}, Cached: {cached:,}, Errors: {errors:,}")
                
                total_stats['total_tiles'] += len(tiles)
                total_stats['generated'] += generated
                total_stats['cached'] += cached
                total_stats['errors'] += errors
        
        # Final statistics
        total_stats['end_time'] = datetime.now()
        duration = (total_stats['end_time'] - total_stats['start_time']).total_seconds()
        
        print("\n" + "=" * 60)
        print("Tile Pre-generation Complete!")
        print("=" * 60)
        print(f"Total tiles processed: {total_stats['total_tiles']:,}")
        print(f"  Generated: {total_stats['generated']:,}")
        print(f"  Already cached: {total_stats['cached']:,}")
        print(f"  Errors: {total_stats['errors']:,}")
        print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
        print("=" * 60)
        
    finally:
        conn.close()


def main():
    """Main entry point."""
    print("\n" + "=" * 60)
    print("Tile Pre-generation Script")
    print("=" * 60)
    print("This script will pre-generate raster tiles for selected areas.")
    print("Tiles will be cached for faster map loading.")
    print()
    
    # Interactive selection
    state_code, districts = interactive_selection()
    
    if not state_code or not districts:
        print("\nNo selection made. Exiting.")
        return
    
    # Confirm before proceeding
    print("\n" + "=" * 60)
    total_parcels = sum(d['count'] for d in districts)
    print(f"You are about to pre-generate tiles for:")
    print(f"  State: {state_code}")
    print(f"  Districts: {len(districts)}")
    print(f"  Total parcels: {total_parcels:,}")
    print(f"  Zoom levels: 15, 16, 17, 18")
    print("=" * 60)
    
    confirm = input("\nProceed with tile generation? (yes/no): ").strip().lower()
    if confirm != 'yes':
        print("Cancelled.")
        return
    
    # Pre-generate tiles
    pregenerate_tiles_for_area(state_code, districts, zoom_levels=[15, 16, 17, 18])


if __name__ == "__main__":
    main()

