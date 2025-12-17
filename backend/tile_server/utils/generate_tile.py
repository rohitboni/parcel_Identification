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
import logging

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

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

    # Logging disabled for performance - uncomment if needed for debugging
    # logger.debug(f"Fetched {len(parcels)} parcels")
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
    LINE_WIDTH = 2  # Line width in pixels at render scale (will be ~1px after resize)
    transform = from_bounds(minx, miny, maxx, maxy, RENDER_SIZE, RENDER_SIZE)
    edge_mask = features.rasterize(
        [(p["geometry"].boundary, 1) for p in tile_parcels],
        out_shape=(RENDER_SIZE, RENDER_SIZE),
        transform=transform,
        fill=0,
        dtype=np.uint8
    )
    
    # Dilate the edge mask to make lines thicker
    # Use scipy if available (much faster - ~10-50ms), otherwise use optimized numpy approach
    try:
        from scipy.ndimage import maximum_filter
        # Fast dilation using scipy (if available) - this is very fast (~10-50ms)
        edge_mask_thick = maximum_filter(edge_mask, size=LINE_WIDTH * 2 + 1)
    except ImportError:
        # Fallback: optimized numpy approach using vectorized operations
        # This is much faster than nested loops (~50-150ms vs 200-500ms)
        # Use iterative expansion with vectorized shifts
        edge_mask_thick = edge_mask.copy()
        h, w = edge_mask.shape
        
        # Expand edges iteratively (each iteration expands by 1 pixel)
        for _ in range(LINE_WIDTH):
            # Create expanded version by shifting in all 8 directions and combining
            expanded = edge_mask_thick.copy()
            
            # Shift up, down, left, right (4 directions)
            expanded[1:, :] = np.maximum(expanded[1:, :], edge_mask_thick[:-1, :])  # down
            expanded[:-1, :] = np.maximum(expanded[:-1, :], edge_mask_thick[1:, :])  # up
            expanded[:, 1:] = np.maximum(expanded[:, 1:], edge_mask_thick[:, :-1])  # right
            expanded[:, :-1] = np.maximum(expanded[:, :-1], edge_mask_thick[:, 1:])  # left
            
            # Shift diagonally (4 directions)
            expanded[1:, 1:] = np.maximum(expanded[1:, 1:], edge_mask_thick[:-1, :-1])  # down-right
            expanded[1:, :-1] = np.maximum(expanded[1:, :-1], edge_mask_thick[:-1, 1:])  # down-left
            expanded[:-1, 1:] = np.maximum(expanded[:-1, 1:], edge_mask_thick[1:, :-1])  # up-right
            expanded[:-1, :-1] = np.maximum(expanded[:-1, :-1], edge_mask_thick[1:, 1:])  # up-left
            
            edge_mask_thick = expanded

    rgba = np.zeros((RENDER_SIZE, RENDER_SIZE, 4), dtype=np.uint8)
    rgba[..., 0] = np.where(edge_mask_thick == 1, 0, rgba[..., 0])
    rgba[..., 1] = np.where(edge_mask_thick == 1, 0, rgba[..., 1])
    rgba[..., 2] = np.where(edge_mask_thick == 1, 0, rgba[..., 2])
    rgba[..., 3] = np.where(edge_mask_thick == 1, 255, 0)

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


