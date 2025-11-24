# backend/tile_server/tile_server_raster.py

from fastapi import APIRouter, Response, HTTPException
from tile_server.utils.generate_tile import generate_raster_tile
from tile_server.utils.cache_manager import get_tile_from_cache, save_tile_to_cache

router = APIRouter()

@router.get("/tiles/{z}/{x}/{y}.png")
async def get_raster_tile(z: int, x: int, y: int):
    """
    Returns a raster tile at the given z/x/y indices.
    Checks cache first; if not found, generates and caches.
    """
    # Step 1: Try cache
    cached_tile = get_tile_from_cache(z, x, y)
    if cached_tile:
        return Response(content=cached_tile, media_type="image/png")

    # Step 2: Generate new tile if not cached
    try:
        tile_img = generate_raster_tile(z, x, y)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tile generation failed: {e}")

    # Step 3: Cache the generated tile
    save_tile_to_cache(z, x, y, tile_img)

    # Step 4: Return the image response
    return Response(content=tile_img, media_type="image/png")
