"""
Service 2: Pre-Generation Service
Port: 8002 (internal, accessed via API Gateway on port 8000)
Purpose: Pre-generate tiles in background for viewport areas
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from tile_server.utils.viewport_tiles import generate_tiles_for_viewport, get_viewport_tiles
from tile_server.utils.cache_manager import check_tile_exists_in_s3, get_tile, save_tile
from tile_server.utils.generate_tile import generate_raster_tile
from tile_server.utils.tile_utils import bounds_to_tile_xyz
import asyncio
import httpx
import psycopg2
import sys
from pathlib import Path

# Add backend directory to path for config import
_backend_dir = Path(__file__).parent.parent  # Go up from services/ -> backend/
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
from config import DB_CONFIG, TABLE_MASTER

app = FastAPI(title="Tile Pre-Generation Service", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/pregenerate-viewport")
async def pregenerate_viewport_tiles(
    min_lat: float = Query(...),
    min_lon: float = Query(...),
    max_lat: float = Query(...),
    max_lon: float = Query(...),
    zoom: int = Query(..., ge=15, le=18),
    state_code: str = Query(None),
    district_code: str = Query(None),
    surrounding_radius: int = Query(2, ge=0, le=5)
):
    """
    Pre-generate tiles for viewport area with priority:
    1. Viewport tiles (generated immediately)
    2. Surrounding tiles (generated in spiral pattern)
    
    This endpoint is called by the frontend when the map viewport changes.
    Tiles are generated in priority order: viewport first, then surrounding.
    """
    print(f"[PRE-GEN] Starting pre-generation for viewport: zoom={zoom}, state={state_code or 'all'}, district={district_code or 'all'}")
    try:
        # Run tile generation in background to avoid blocking
        result = await asyncio.to_thread(
            generate_tiles_for_viewport,
            min_lat, min_lon, max_lat, max_lon, zoom,
            state_code, district_code, surrounding_radius
        )
        print(f"[PRE-GEN] Completed: {result.get('generated', 0)} generated, {result.get('cached', 0)} cached")
        return JSONResponse(result)
    except Exception as e:
        print(f"[PRE-GEN ERROR] {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/check-district-tiles")
async def check_district_tiles(
    state_code: str = Query(...),
    district_code: str = Query(...),
    zoom: int = Query(15, ge=15, le=18),
    sample_size: int = Query(10, ge=1, le=100)
):
    """
    Check if tiles exist in S3 for a district.
    Samples a few tiles from the district extent to estimate coverage.
    
    Returns:
    - exists: True if any tiles exist, False otherwise
    - sample_checked: Number of tiles checked
    - tiles_found: Number of tiles found in S3
    - coverage_estimate: Estimated coverage percentage
    """
    try:
        # Get district bounds
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT 
                ST_XMin(ST_Extent(geom)) as min_lon,
                ST_YMin(ST_Extent(geom)) as min_lat,
                ST_XMax(ST_Extent(geom)) as max_lon,
                ST_YMax(ST_Extent(geom)) as max_lat
            FROM %s
            WHERE state_code = %s AND district_code = %s
        """, (TABLE_MASTER, state_code.upper(), district_code))
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if not result or result[0] is None:
            raise HTTPException(status_code=404, detail=f"No data found for state_code={state_code}, district_code={district_code}")
        
        min_lon, min_lat, max_lon, max_lat = result
        
        # Get all tiles for district extent
        all_tiles = get_viewport_tiles(min_lat, min_lon, max_lat, max_lon, zoom)
        
        if not all_tiles:
            return JSONResponse({
                "exists": False,
                "sample_checked": 0,
                "tiles_found": 0,
                "coverage_estimate": 0.0,
                "total_tiles": 0
            })
        
        # Sample tiles (check first N tiles)
        sample_tiles = all_tiles[:sample_size]
        tiles_found = 0
        
        for z, x, y in sample_tiles:
            if check_tile_exists_in_s3(z, x, y, state_code=state_code, district_code=district_code):
                tiles_found += 1
        
        coverage_estimate = (tiles_found / len(sample_tiles) * 100) if sample_tiles else 0.0
        exists = tiles_found > 0
        
        return JSONResponse({
            "exists": exists,
            "sample_checked": len(sample_tiles),
            "tiles_found": tiles_found,
            "coverage_estimate": round(coverage_estimate, 2),
            "total_tiles": len(all_tiles),
            "bounds": {
                "min_lon": float(min_lon),
                "min_lat": float(min_lat),
                "max_lon": float(max_lon),
                "max_lat": float(max_lat)
            }
        })
    except Exception as e:
        print(f"[CHECK ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/generate-district-tiles")
async def generate_district_tiles(
    state_code: str = Query(...),
    district_code: str = Query(...),
    zoom: int = Query(15, ge=15, le=18),
    max_tiles: int = Query(1000, ge=1, le=10000)
):
    """
    Generate tiles for a district on-demand.
    Gets district bounds, generates all tiles for that extent, and saves to S3.
    
    This is a long-running operation. Returns progress updates.
    """
    try:
        # Get district bounds
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT 
                ST_XMin(ST_Extent(geom)) as min_lon,
                ST_YMin(ST_Extent(geom)) as min_lat,
                ST_XMax(ST_Extent(geom)) as max_lon,
                ST_YMax(ST_Extent(geom)) as max_lat
            FROM %s
            WHERE state_code = %s AND district_code = %s
        """, (TABLE_MASTER, state_code.upper(), district_code))
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if not result or result[0] is None:
            raise HTTPException(status_code=404, detail=f"No data found for state_code={state_code}, district_code={district_code}")
        
        min_lon, min_lat, max_lon, max_lat = result
        
        # Get all tiles for district extent
        all_tiles = get_viewport_tiles(min_lat, min_lon, max_lat, max_lon, zoom)
        
        if not all_tiles:
            return JSONResponse({
                "status": "completed",
                "message": "No tiles to generate for this district",
                "generated": 0,
                "cached": 0,
                "total": 0
            })
        
        # Limit tiles if max_tiles is set
        tiles_to_generate = all_tiles[:max_tiles] if max_tiles < len(all_tiles) else all_tiles
        
        print(f"[GEN DISTRICT] Generating {len(tiles_to_generate)} tiles for {state_code}/{district_code} at zoom {zoom}")
        
        # Generate tiles in background
        stats = {
            "generated": 0,
            "cached": 0,
            "errors": 0,
            "total": len(tiles_to_generate)
        }
        
        # Run generation in thread to avoid blocking
        def generate_tiles():
            for z, x, y in tiles_to_generate:
                try:
                    # Check S3 first
                    existing = get_tile(z, x, y, state_code=state_code, district_code=district_code)
                    if existing:
                        stats["cached"] += 1
                        continue
                    
                    # Generate tile
                    tile_data = generate_raster_tile(z, x, y, state_code=state_code, district_code=district_code)
                    save_tile(z, x, y, tile_data, state_code=state_code, district_code=district_code)
                    stats["generated"] += 1
                    
                    # Progress update every 100 tiles
                    if (stats["generated"] + stats["cached"]) % 100 == 0:
                        print(f"[GEN DISTRICT] Progress: {stats['generated']} generated, {stats['cached']} cached")
                except Exception as e:
                    print(f"[GEN DISTRICT ERROR] Error generating tile {z}/{x}/{y}: {e}")
                    stats["errors"] += 1
            
            return stats
        
        # Run in background thread
        result = await asyncio.to_thread(generate_tiles)
        
        print(f"[GEN DISTRICT] Completed: {result['generated']} generated, {result['cached']} cached, {result['errors']} errors")
        
        return JSONResponse({
            "status": "completed",
            "message": f"Generated {result['generated']} tiles for {state_code}/{district_code}",
            "generated": result["generated"],
            "cached": result["cached"],
            "errors": result["errors"],
            "total": result["total"],
            "bounds": {
                "min_lon": float(min_lon),
                "min_lat": float(min_lat),
                "max_lon": float(max_lon),
                "max_lat": float(max_lat)
            }
        })
    except Exception as e:
        print(f"[GEN DISTRICT ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok", "service": "tile-pregeneration"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)

