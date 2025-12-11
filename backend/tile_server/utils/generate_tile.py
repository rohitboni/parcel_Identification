# backend/tile_server/utils/generate_tile.py

import io
import os
import numpy as np
from PIL import Image, ImageDraw
from shapely.wkb import loads as wkb_loads
from shapely.geometry import box
from rasterio import features
from rasterio.transform import from_bounds
import psycopg2
from .tile_utils import tile_xyz_to_bounds

# ------------------------------
# Database config
# ------------------------------
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", "5432")),
    "database": os.environ.get("DB_NAME", "parcels_db"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", "postgres")
}

# ------------------------------
# Database connection
# ------------------------------
def connect_db():
    return psycopg2.connect(**DB_CONFIG)

# ------------------------------
# Fetch parcels for a tile
# ------------------------------

def fetch_tile_parcels(minx, miny, maxx, maxy):
    conn = connect_db()
    cur = conn.cursor()

    query = """
        SELECT parcel_uuid,
               survey_num,
               ST_AsEWKB(geom),
               ST_AsEWKB(ST_PointOnSurface(geom)) AS label_point
        FROM parcels_simplified
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326));
    """

    cur.execute(query, (minx, miny, maxx, maxy, minx, miny, maxx, maxy))
    results = cur.fetchall()

    cur.close()
    conn.close()

    parcels = []
    for parcel_uuid, survey_num, geom_wkb, label_point_wkb in results:
        parcels.append({
            "uuid": parcel_uuid,
            "survey_num": survey_num,
            "geometry": wkb_loads(geom_wkb.tobytes()),
            "label_point": wkb_loads(label_point_wkb.tobytes())
        })


    return parcels

# ------------------------------
# Generate raster tile
# ------------------------------
def generate_raster_tile(z: int, x: int, y: int) -> bytes:
    """
    Generate a 256x256 PNG raster tile showing parcel borders
    and survey numbers inside the polygons.
    """
    # Tile bounding box
    minx, miny, maxx, maxy = tile_xyz_to_bounds(x, y, z)
    tile_bbox = box(minx, miny, maxx, maxy)

    # Fetch parcels intersecting this tile
    tile_parcels = fetch_tile_parcels(minx, miny, maxx, maxy)
    if not tile_parcels:
        # Return empty transparent tile
        img = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    # ------------------------------
    # Rasterize borders
    # ------------------------------
    transform = from_bounds(minx, miny, maxx, maxy, 256, 256)
    edge_mask = features.rasterize(
        [(p["geometry"].boundary, 1) for p in tile_parcels],
        out_shape=(256, 256),
        transform=transform,
        fill=0,
        dtype=np.uint8
    )

    rgba = np.zeros((256, 256, 4), dtype=np.uint8)
    rgba[..., 0] = np.where(edge_mask == 1, 0, rgba[..., 0])
    rgba[..., 1] = np.where(edge_mask == 1, 0, rgba[..., 1])
    rgba[..., 2] = np.where(edge_mask == 1, 0, rgba[..., 2])
    rgba[..., 3] = np.where(edge_mask == 1, 255, 0)  # alpha

    # ------------------------------
    # Draw survey numbers
    # ------------------------------
    img = Image.fromarray(rgba, "RGBA")
    draw = ImageDraw.Draw(img)

    for p in tile_parcels:
        # point = p["geometry"].representative_point()
        point = p["label_point"]
        px = int((point.x - minx) / (maxx - minx) * 256)
        py = int((maxy - point.y) / (maxy - miny) * 256)  # y-flip for image
        draw.text((px, py), str(p["survey_num"]), fill="black")

    # Save to PNG bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


