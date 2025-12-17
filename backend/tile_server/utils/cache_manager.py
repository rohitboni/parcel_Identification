# utils/cache_manager.py
import os
import logging

logger = logging.getLogger(__name__)
# Set to False to disable cache logging (faster performance)
ENABLE_CACHE_LOGGING = False

CACHE_DIR = "cache"

def _tile_path(z: int, x: int, y: int) -> str:
    return os.path.join(CACHE_DIR, str(z), str(x), f"{y}.png")

def get_tile_from_cache(z: int, x: int, y: int) -> bytes | None:
    tile_path = _tile_path(z, x, y)
    exists = os.path.exists(tile_path)
    
    if ENABLE_CACHE_LOGGING:
        logger.debug(f"[CACHE] check {z}/{x}/{y} -> exists={exists}")
    
    if exists:
        with open(tile_path, "rb") as f:
            data = f.read()
        if ENABLE_CACHE_LOGGING:
            logger.debug(f"[CACHE] HIT {z}/{x}/{y} size={len(data)} bytes")
        return data
    
    if ENABLE_CACHE_LOGGING:
        logger.debug(f"[CACHE] MISS {z}/{x}/{y}")
    return None

def save_tile_to_cache(z: int, x: int, y: int, tile_data: bytes):
    tile_path = _tile_path(z, x, y)
    os.makedirs(os.path.dirname(tile_path), exist_ok=True)
    with open(tile_path, "wb") as f:
        f.write(tile_data)
    
    if ENABLE_CACHE_LOGGING:
        logger.debug(f"[CACHE] SAVED {z}/{x}/{y} -> {tile_path} size={len(tile_data)} bytes")
