# utils/cache_manager.py
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
# Set to False to disable cache logging (faster performance)
ENABLE_CACHE_LOGGING = False

# Use absolute path: cache directory in project root (not backend/cache)
# This ensures consistency between pregenerate_tiles.py and tile server
_backend_dir = Path(__file__).parent.parent.parent  # Go up from utils/ -> tile_server/ -> backend/
_project_root = _backend_dir.parent  # Go up from backend/ -> project root
CACHE_DIR = str(_project_root / "cache")

def _tile_path(z: int, x: int, y: int, state_code: str = None, district_code: str = None) -> str:
    """
    Generate cache path in format: cache/state/district/z/x/y.png
    - state_code: State code (e.g., 'KA') or 'all' if no filter
    - district_code: District code (e.g., '526') or 'all' if no filter
    """
    # Normalize state and district codes
    state_part = (state_code or 'all').upper()
    district_part = (district_code or 'all')
    
    # Path structure: cache/state/district/z/x/y.png
    return os.path.join(CACHE_DIR, state_part, district_part, str(z), str(x), f"{y}.png")

def get_tile_from_cache(z: int, x: int, y: int, state_code: str = None, district_code: str = None) -> bytes | None:
    """
    Get tile from cache. Returns tile data if found, None otherwise.
    Checks cache first before generating new tiles.
    """
    tile_path = _tile_path(z, x, y, state_code, district_code)
    exists = os.path.exists(tile_path)
    
    if exists:
        try:
            with open(tile_path, "rb") as f:
                data = f.read()
            return data
        except Exception as e:
            print(f"[CACHE ERROR] Error reading cached tile {z}/{x}/{y}: {e}")
            return None
    
    return None

def save_tile_to_cache(z: int, x: int, y: int, tile_data: bytes, state_code: str = None, district_code: str = None):
    """
    Save tile to cache in organized structure: cache/state/district/z/x/y.png
    """
    tile_path = _tile_path(z, x, y, state_code, district_code)
    try:
        os.makedirs(os.path.dirname(tile_path), exist_ok=True)
        with open(tile_path, "wb") as f:
            f.write(tile_data)
    except Exception as e:
        print(f"[CACHE ERROR] Error saving tile {z}/{x}/{y} to cache: {e}")
