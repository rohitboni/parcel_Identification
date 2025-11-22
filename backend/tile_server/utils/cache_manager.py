# # utils/cache_manager.py
# import os

# CACHE_DIR = "cache"

# def _tile_path(z: int, x: int, y: int) -> str:
#     """Generate a local cache path for a given z/x/y tile."""
#     return os.path.join(CACHE_DIR, str(z), str(x), f"{y}.png")

# def get_tile_from_cache(z: int, x: int, y: int) -> bytes | None:
#     """Fetch tile from local filesystem cache if it exists."""
#     tile_path = _tile_path(z, x, y)
#     if os.path.exists(tile_path):
#         with open(tile_path, "rb") as f:
#             return f.read()
#     return None

# def save_tile_to_cache(z: int, x: int, y: int, tile_data: bytes):
#     """Save tile to local filesystem cache."""
#     tile_path = _tile_path(z, x, y)
#     os.makedirs(os.path.dirname(tile_path), exist_ok=True)
#     with open(tile_path, "wb") as f:
#         f.write(tile_data)



# utils/cache_manager.py
import os
import time

CACHE_DIR = "cache"

def _tile_path(z: int, x: int, y: int) -> str:
    return os.path.join(CACHE_DIR, str(z), str(x), f"{y}.png")

def get_tile_from_cache(z: int, x: int, y: int) -> bytes | None:
    tile_path = _tile_path(z, x, y)
    start = time.time()
    exists = os.path.exists(tile_path)
    print(f"[CACHE] check {z}/{x}/{y} -> exists={exists} path={tile_path} (t={time.time()-start:.4f}s)")
    if exists:
        with open(tile_path, "rb") as f:
            data = f.read()
        print(f"[CACHE] HIT {z}/{x}/{y} size={len(data)} bytes")
        return data
    print(f"[CACHE] MISS {z}/{x}/{y}")
    return None

def save_tile_to_cache(z: int, x: int, y: int, tile_data: bytes):
    tile_path = _tile_path(z, x, y)
    os.makedirs(os.path.dirname(tile_path), exist_ok=True)
    with open(tile_path, "wb") as f:
        f.write(tile_data)
    print(f"[CACHE] SAVED {z}/{x}/{y} -> {tile_path} size={len(tile_data)} bytes")
