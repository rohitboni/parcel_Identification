from fastapi import APIRouter, Response, HTTPException, Query
from tile_server.utils.generate_tile import generate_raster_tile
from tile_server.utils.cache_manager import get_tile_from_cache, save_tile_to_cache

router = APIRouter()


@router.get("/tiles/{z}/{x}/{y}.png")
async def get_raster_tile(
    z: int, 
    x: int, 
    y: int,
    state_code: str = None,
    district_code: str = None
):
    """
    Returns a raster tile at the given z/x/y indices.
    Optional filters: state_code, district_code
    
    Cache structure: cache/state/district/z/x/y.png
    - Checks cache first before generating new tiles
    - Prioritizes viewport tiles (generated immediately)
    - Surrounding tiles generated in background
    """
    if z < 15 or z > 18:
        raise HTTPException(status_code=400, detail="z out of allowed range")
    
    # Cache headers for browser caching (1 hour for tiles)
    cache_headers = {
        "Cache-Control": "public, max-age=3600",
        "ETag": f"{state_code or 'all'}-{district_code or 'all'}-{z}-{x}-{y}"
    }
    
    # Check cache first (organized by state/district)
    cached_tile = get_tile_from_cache(z, x, y, state_code=state_code, district_code=district_code)
    if cached_tile:
        print(f"[CACHE HIT] Tile {z}/{x}/{y} served from cache (state={state_code or 'all'}, district={district_code or 'all'})")
        return Response(content=cached_tile, media_type="image/png", headers=cache_headers)

    # Generate new tile if not in cache
    print(f"[GENERATING] Tile {z}/{x}/{y} generating on-demand (state={state_code or 'all'}, district={district_code or 'all'})")
    try:
        tile_img = generate_raster_tile(z, x, y, state_code=state_code, district_code=district_code)
        print(f"[GENERATED] Tile {z}/{x}/{y} generated successfully ({len(tile_img)} bytes)")
    except Exception as e:
        print(f"[ERROR] Tile {z}/{x}/{y} generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Tile generation failed: {e}")

    # Save to cache (organized by state/district)
    save_tile_to_cache(z, x, y, tile_img, state_code=state_code, district_code=district_code)
    print(f"[CACHE SAVED] Tile {z}/{x}/{y} saved to cache")
    return Response(content=tile_img, media_type="image/png", headers=cache_headers)
