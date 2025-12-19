"""
Service 1: On-Demand Tile Generation Service
Port: 8001 (internal, accessed via API Gateway on port 8000)
Purpose: Serve tiles on-demand (cache-first, generate if missing)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from tile_server.tile_server_raster import router as tile_router

app = FastAPI(title="Tile Generation Service (On-Demand)", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Only include the tile serving endpoint (on-demand generation)
app.include_router(tile_router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "tile-generation-on-demand"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)

