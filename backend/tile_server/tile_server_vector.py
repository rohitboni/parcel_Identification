# tile_server.py
import math
import os
import asyncio
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import PlainTextResponse
import asyncpg
from typing import Tuple

DB_DSN = os.environ.get("DATABASE_URL") or "postgresql://postgres:postgres@127.0.0.1:5432/parcels_db"
TILE_BUFFER = 64      # buffer for geometry in tile pixels (used in ST_AsMVTGeom)
TILE_EXTENT = 4096    # MVT internal extent

app = FastAPI(title="Parcel Tile Server (MVP)")

# ---------- helper: tile -> lon/lat bbox (EPSG:4326) ----------
def tile_xyz_to_lonlat_bbox(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
    """
    Return bbox in EPSG:4326 lon/lat: (minx, miny, maxx, maxy)
    Using Web Mercator tile scheme (XYZ, Google/OSM).
    """
    n = 2.0 ** z
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0

    # helper to convert tile y to latitude (in degrees)
    def tile_y_to_lat(y_tile):
        # convert to Mercator y -> latitude
        merc_n = math.pi * (1 - 2 * y_tile / n)
        lat = math.degrees(math.atan(math.sinh(merc_n)))
        return lat

    lat_max = tile_y_to_lat(y)
    lat_min = tile_y_to_lat(y + 1)

    return (lon_min, lat_min, lon_max, lat_max)

# ---------- DB pool ----------
db_pool: asyncpg.pool.Pool | None = None

@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=10)
    # Optionally test connection
    async with db_pool.acquire() as conn:
        await conn.execute("SELECT 1")

@app.on_event("shutdown")
async def shutdown():
    global db_pool
    if db_pool:
        await db_pool.close()

# ---------- Tile endpoint ----------
@app.get("/tiles/{z:int}/{x:int}/{y:int}.pbf", response_class=Response)
async def get_tile(z: int, x: int, y: int):
    """
    Serve vector tile (MVT / .pbf) for given z/x/y.
    Returns protobuf (ST_AsMVT) bytes.
    """
    # basic sanity checks
    if z < 0 or z > 22:
        raise HTTPException(status_code=400, detail="z out of range")
    if x < 0 or y < 0:
        raise HTTPException(status_code=400, detail="invalid x/y")

    bbox = tile_xyz_to_lonlat_bbox(z, x, y)
    minx, miny, maxx, maxy = bbox

    # SQL: use ST_AsMVT with ST_AsMVTGeom to clip & scale geometries to tile
    # Keep properties minimal to reduce tile size (parcel_uuid, survey_num, v_name)
    # sql = f"""
    # WITH
    #   bounds AS (
    #     SELECT ST_MakeEnvelope($1, $2, $3, $4, 4326) AS geom
    #   ),
    #   mvtgeom AS (
    #     SELECT
    #       parcel_uuid::text,
    #       survey_num::text,
    #       v_code::text,
    #       ST_AsMVTGeom(
    #         geom,
    #         bounds.geom,
    #         {TILE_EXTENT},
    #         {TILE_BUFFER},
    #         TRUE
    #       ) AS geom
    #     FROM parcels_simplified, bounds
    #     WHERE ST_Intersects(geom, bounds.geom)
    #   )
    # SELECT ST_AsMVT(mvtgeom, 'parcels', {TILE_EXTENT}, 'geom') FROM mvtgeom;
    # """
    sql = f"""
    WITH
    bounds AS (
        SELECT ST_MakeEnvelope($1, $2, $3, $4, 4326) AS geom
    ),
    mvtgeom AS (
        SELECT
        parcels_simplified.parcel_uuid::text,
        parcels_simplified.survey_num::text,
        parcels_simplified.v_code::text,
        ST_AsMVTGeom(
            parcels_simplified.geom,
            bounds.geom,
            {TILE_EXTENT},
            {TILE_BUFFER},
            TRUE
        ) AS geom
        FROM parcels_simplified
        JOIN bounds
        ON ST_Intersects(parcels_simplified.geom, bounds.geom)
    )
    SELECT ST_AsMVT(mvtgeom, 'parcels', {TILE_EXTENT}, 'geom')
    FROM mvtgeom;
    """


    # fetch single bytea value
    try:
        async with db_pool.acquire() as conn:
            # fetchval returns bytes (Postgres bytea => Python bytes)
            tile_bytes = await conn.fetchval(sql, minx, miny, maxx, maxy)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # If no features, return 204 No Content or empty pbf — we'll return empty body with 204
    if not tile_bytes:
        # return empty tile (204)
        return Response(content=b"", status_code=204)

    # Return the pbf bytes
    return Response(content=bytes(tile_bytes), media_type="application/vnd.mapbox-vector-tile", headers={
        "Cache-Control": "public, max-age=60"   # short cache for MVP; later use CDN
    })

# ---------- Simple parcel info endpoint ----------
@app.get("/parcel-info")
async def parcel_info(parcel_uuid: str):
    """
    Return attributes for a parcel by parcel_uuid.
    """
    if not parcel_uuid:
        raise HTTPException(status_code=400, detail="missing parcel_uuid")

    sql = """
    SELECT parcel_uuid::text, survey_num, gp_name, v_name, v_code, district, state, tehsil,
           ST_AsText(ST_Centroid(geom)) AS centroid_wkt
    FROM parcels_raw
    WHERE parcel_uuid::text = $1
    LIMIT 1;
    """

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(sql, parcel_uuid)

    if not row:
        raise HTTPException(status_code=404, detail="parcel not found")

    # convert to dict
    return dict(row)

# ---------- Health check ----------
@app.get("/health", response_class=PlainTextResponse)
async def health():
    return "ok"
