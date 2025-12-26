"""
Viewport-based tile generation with priority ordering.

Priority Strategy:
1. Viewport tiles (highest priority - generate/serve first)
2. Surrounding tiles in spiral pattern (expanding outward)
3. Background generation for tiles further away

This ensures users see tiles for their current viewport immediately,
while surrounding tiles are pre-generated for smooth panning.
"""
import math
import logging
from typing import List, Tuple, Optional
from .tile_utils import tile_xyz_to_bounds, bounds_to_tile_xyz
from .generate_tile import generate_raster_tile
from .cache_manager import get_tile, save_tile

logger = logging.getLogger(__name__)


def get_viewport_tiles(min_lat: float, min_lon: float, max_lat: float, max_lon: float, zoom: int) -> List[Tuple[int, int, int]]:
    """
    Get all tile coordinates for a viewport bounding box.
    
    Returns list of (z, x, y) tuples for tiles covering the viewport.
    """
    # Get tile coordinates for corners
    min_x, min_y = bounds_to_tile_xyz(min_lon, min_lat, zoom)
    max_x, max_y = bounds_to_tile_xyz(max_lon, max_lat, zoom)
    
    # Ensure we have the correct min/max (tile coordinates can wrap)
    tile_x_min = min(min_x, max_x)
    tile_x_max = max(min_x, max_x)
    tile_y_min = min(min_y, max_y)
    tile_y_max = max(min_y, max_y)
    
    # Generate all tiles in viewport
    tiles = []
    for x in range(tile_x_min, tile_x_max + 1):
        for y in range(tile_y_min, tile_y_max + 1):
            tiles.append((zoom, x, y))
    
    return tiles


def get_surrounding_tiles(center_x: int, center_y: int, zoom: int, radius: int = 2) -> List[Tuple[int, int, int]]:
    """
    Get surrounding tiles in spiral pattern (expanding outward).
    
    Priority order:
    1. Direct neighbors (radius=1)
    2. Next ring (radius=2)
    3. Outer rings (radius=3, 4, ...)
    
    Returns list of (z, x, y) tuples ordered by distance from center.
    """
    tiles = []
    
    # Generate tiles in spiral pattern
    for r in range(1, radius + 1):
        # Generate tiles in a square ring at radius r
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                # Only include tiles on the edge of this ring
                if abs(dx) == r or abs(dy) == r:
                    x = center_x + dx
                    y = center_y + dy
                    tiles.append((zoom, x, y))
    
    # Sort by distance from center (closer tiles first)
    tiles.sort(key=lambda t: abs(t[1] - center_x) + abs(t[2] - center_y))
    
    return tiles


def generate_tiles_for_viewport(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    zoom: int,
    state_code: Optional[str] = None,
    district_code: Optional[str] = None,
    surrounding_radius: int = 2
) -> dict:
    """
    Generate tiles for viewport with priority ordering.
    
    Strategy:
    1. Generate viewport tiles first (immediate priority)
    2. Generate surrounding tiles in spiral pattern (background)
    
    Returns statistics about generation.
    """
    # Calculate center tile for surrounding generation
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    center_x, center_y = bounds_to_tile_xyz(center_lon, center_lat, zoom)
    
    # Get viewport tiles (priority 1)
    viewport_tiles = get_viewport_tiles(min_lat, min_lon, max_lat, max_lon, zoom)
    
    # Get surrounding tiles (priority 2)
    surrounding_tiles = get_surrounding_tiles(center_x, center_y, zoom, surrounding_radius)
    
    # Remove duplicates (viewport tiles might overlap with surrounding)
    viewport_set = set(viewport_tiles)
    surrounding_tiles = [t for t in surrounding_tiles if t not in viewport_set]
    
    stats = {
        "viewport_tiles": len(viewport_tiles),
        "surrounding_tiles": len(surrounding_tiles),
        "generated": 0,
        "cached": 0,
        "errors": 0
    }
    
    # Priority 1: Generate viewport tiles first
    logger.info(f"Generating {len(viewport_tiles)} viewport tiles...")
    for z, x, y in viewport_tiles:
        try:
            # Check S3 first
            cached = get_tile(z, x, y, state_code=state_code, district_code=district_code)
            if cached:
                stats["cached"] += 1
                continue
            
            # Generate tile
            tile_data = generate_raster_tile(z, x, y, state_code=state_code, district_code=district_code)
            save_tile(z, x, y, tile_data, state_code=state_code, district_code=district_code)
            stats["generated"] += 1
        except Exception as e:
            logger.error(f"Error generating viewport tile {z}/{x}/{y}: {e}")
            stats["errors"] += 1
    
    # Priority 2: Generate surrounding tiles (background)
    logger.info(f"Generating {len(surrounding_tiles)} surrounding tiles...")
    for z, x, y in surrounding_tiles:
        try:
            # Check S3 first
            cached = get_tile(z, x, y, state_code=state_code, district_code=district_code)
            if cached:
                stats["cached"] += 1
                continue
            
            # Generate tile
            tile_data = generate_raster_tile(z, x, y, state_code=state_code, district_code=district_code)
            save_tile(z, x, y, tile_data, state_code=state_code, district_code=district_code)
            stats["generated"] += 1
        except Exception as e:
            logger.error(f"Error generating surrounding tile {z}/{x}/{y}: {e}")
            stats["errors"] += 1
    
    return stats

