"""
Service 2: Pre-Generation Service
Port: 8002 (internal, accessed via API Gateway on port 8000)
Purpose: Pre-generate tiles in background for viewport areas
"""

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from tile_server.utils.viewport_tiles import generate_tiles_for_viewport
import asyncio

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

@app.get("/health")
def health():
    return {"status": "ok", "service": "tile-pregeneration"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)

