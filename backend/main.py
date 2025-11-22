from fastapi import FastAPI

from identify_api.identify_server import router as identify_router
from tile_server.tile_server_raster import router as tile_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Parcel MVP Backend", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # or ["http://127.0.0.1:8080"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(identify_router, prefix="/api")
app.include_router(tile_router)
