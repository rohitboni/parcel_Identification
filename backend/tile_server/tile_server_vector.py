import math
import os
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import PlainTextResponse
import asyncpg
from typing import Tuple

DB_DSN = os.environ.get("DATABASE_URL") or "postgresql://postgres:postgres@127.0.0.1:5432/parcels_db"
TILE_BUFFER = 64
TILE_EXTENT = 4096

app = FastAPI(title="Parcel Tile Server (MVP)")


def tile_xyz_to_lonlat_bbox(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
    """
    Return bbox in EPSG:4326 lon/lat: (minx, miny, maxx, maxy)
    Using Web Mercator tile scheme (XYZ, Google/OSM).
    """
    n = 2.0 ** z
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0

    def tile_y_to_lat(y_tile):
        merc_n = math.pi * (1 - 2 * y_tile / n)
        lat = math.degrees(math.atan(math.sinh(merc_n)))
        return lat

    lat_max = tile_y_to_lat(y)
    lat_min = tile_y_to_lat(y + 1)

    return (lon_min, lat_min, lon_max, lat_max)


db_pool: asyncpg.pool.Pool | None = None

@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=10)
    async with db_pool.acquire() as conn:
        await conn.execute("SELECT 1")

@app.on_event("shutdown")
async def shutdown():
    global db_pool
    if db_pool:
        await         db_pool.close()


@app.get("/tiles/{z:int}/{x:int}/{y:int}.pbf", response_class=Response)
async def get_tile(z: int, x: int, y: int):
    """Serve vector tile (MVT / .pbf) for given z/x/y."""
    if z < 0 or z > 22:
        raise HTTPException(status_code=400, detail="z out of range")
    if x < 0 or y < 0:
        raise HTTPException(status_code=400, detail="invalid x/y")

    bbox = tile_xyz_to_lonlat_bbox(z, x, y)
    minx, miny, maxx, maxy = bbox

    sql = f"""
    WITH
    bounds AS (
        SELECT ST_MakeEnvelope($1, $2, $3, $4, 4326) AS geom
    ),
    mvtgeom AS (
        SELECT
        parcels_simplified.parcel_uuid::text,
        parcels_simplified.survey_num::text,
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

    try:
        async with db_pool.acquire() as conn:
            # fetchval returns bytes (Postgres bytea => Python bytes)
            tile_bytes = await conn.fetchval(sql, minx, miny, maxx, maxy)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not tile_bytes:
        return Response(content=b"", status_code=204)

    return Response(content=bytes(tile_bytes), media_type="application/vnd.mapbox-vector-tile", headers={
        "Cache-Control": "public, max-age=60"
    })


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

    return dict(row)


@app.get("/health", response_class=PlainTextResponse)
async def health():
    return "ok"
