import io
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely.wkb import loads as wkb_loads
from shapely.geometry import box
from rasterio import features
from rasterio.transform import from_bounds
import psycopg2
from .tile_utils import tile_xyz_to_bounds

import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT")),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}


def connect_db():
    return psycopg2.connect(**DB_CONFIG)

def fetch_tile_parcels(minx, miny, maxx, maxy):
    conn = connect_db()
    cur = conn.cursor()

    query = """
        SELECT parcel_uuid,
               survey_num,
               ST_AsEWKB(geom),
               ST_AsEWKB(label_point)
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


def generate_raster_tile(z: int, x: int, y: int) -> bytes:
    """
    Generate a 256x256 PNG raster tile showing parcel borders
    and survey numbers inside the polygons.
    
    Uses 2x supersampling (512x512) for smoother, anti-aliased lines.
    """
    # Tile bounding box
    minx, miny, maxx, maxy = tile_xyz_to_bounds(x, y, z)
    tile_parcels = fetch_tile_parcels(minx, miny, maxx, maxy)
    if not tile_parcels:
        img = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    # Render at higher resolution for smoother lines (2x supersampling)
    TILE_SIZE = 256
    RENDER_SCALE = 2
    RENDER_SIZE = TILE_SIZE * RENDER_SCALE
    transform = from_bounds(minx, miny, maxx, maxy, RENDER_SIZE, RENDER_SIZE)
    edge_mask = features.rasterize(
        [(p["geometry"].boundary, 1) for p in tile_parcels],
        out_shape=(RENDER_SIZE, RENDER_SIZE),
        transform=transform,
        fill=0,
        dtype=np.uint8
    )

    rgba = np.zeros((RENDER_SIZE, RENDER_SIZE, 4), dtype=np.uint8)
    rgba[..., 0] = np.where(edge_mask == 1, 0, rgba[..., 0])
    rgba[..., 1] = np.where(edge_mask == 1, 0, rgba[..., 1])
    rgba[..., 2] = np.where(edge_mask == 1, 0, rgba[..., 2])
    rgba[..., 3] = np.where(edge_mask == 1, 255, 0)

    img = Image.fromarray(rgba, "RGBA")
    draw = ImageDraw.Draw(img)

    try:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/System/Library/Fonts/Helvetica.ttc",  # macOS
        ]
        font_size = int(12 * RENDER_SCALE)  # 24px at 2x scale
        font = None
        for path in font_paths:
            try:
                font = ImageFont.truetype(path, font_size)
                break
            except:
                continue
    except:
        font = None

    for p in tile_parcels:
        point = p["label_point"]
        px = int((point.x - minx) / (maxx - minx) * RENDER_SIZE)
        py = int((maxy - point.y) / (maxy - miny) * RENDER_SIZE)
        draw.text((px, py), str(p["survey_num"]), fill="black", font=font)

    img = img.resize((TILE_SIZE, TILE_SIZE), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


