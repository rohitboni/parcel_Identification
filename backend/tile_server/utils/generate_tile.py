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
import sys
from pathlib import Path

# Add backend directory to path to import config
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from config import DB_CONFIG, TABLE_SIMPLIFIED

logger = logging.getLogger(__name__)


# Use connection pooling for better performance
try:
    from .performance_optimizer import get_db_connection, return_db_connection
    USE_CONNECTION_POOL = True
except ImportError:
    USE_CONNECTION_POOL = False
    # Fallback to single connection reuse
    _db_connection = None

def connect_db():
    """Get database connection (uses pool if available, otherwise reuses single connection)."""
    if USE_CONNECTION_POOL:
        return get_db_connection()
    else:
        # Fallback: reuse single connection
        global _db_connection
        if _db_connection is None or _db_connection.closed:
            _db_connection = psycopg2.connect(**DB_CONFIG)
        return _db_connection

def fetch_tile_parcels(minx, miny, maxx, maxy, state_code=None, district_code=None):
    """
    Fetch parcels for a tile using optimized query.
    Uses connection reuse and optimized geometry conversion.
    Optional filters: state_code, district_code
    
    Performance optimizations:
    - Uses spatial index (GIST) for fast bounding box queries
    - Filters by state/district to use partition pruning
    - Limits results to 1000 parcels per tile
    """
    conn = connect_db()
    cur = conn.cursor()

    # Build WHERE clause with optional filters
    # IMPORTANT: Put partition filters FIRST for partition pruning
    where_clauses = []
    params = []
    
    if state_code:
        where_clauses.append("state_code = %s")
        params.append(state_code.upper())
    
    if district_code:
        where_clauses.append("district_code = %s")
        params.append(district_code)
    
    # Add spatial filter (uses GIST index)
    where_clauses.append("geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)")
    params.extend([minx, miny, maxx, maxy])
    
    where_clause = " AND ".join(where_clauses)
    
    # Optimized query: Partition filters first, then spatial filter
    # This helps PostgreSQL use partition pruning + spatial index
    query = f"""
        SELECT parcel_uuid,
               survey_num,
               ST_AsEWKB(geom) as geom_wkb,
               ST_AsEWKB(label_point) as label_point_wkb
        FROM {TABLE_SIMPLIFIED}
        WHERE {where_clause}
        LIMIT 1000;
    """

    # Use binary cursor for faster data transfer
    cur.execute(query, params)
    results = cur.fetchall()

    cur.close()
    
    # Return connection to pool if using pooling, otherwise keep it open
    if USE_CONNECTION_POOL:
        return_db_connection(conn)
    # Otherwise, connection stays open for reuse

    # Process results efficiently - batch geometry conversion
    parcels = []
    for row in results:
        parcel_uuid, survey_num, geom_wkb, label_point_wkb = row
        try:
            # Convert WKB to Shapely geometries
            # Note: wkb_loads is faster than ST_AsText conversion
            geom = wkb_loads(geom_wkb.tobytes()) if geom_wkb else None
            label_pt = wkb_loads(label_point_wkb.tobytes()) if label_point_wkb else None
            
            if geom is None:
                continue
                
            parcels.append({
                "uuid": parcel_uuid,
                "survey_num": survey_num,
                "geometry": geom,
                "label_point": label_pt
            })
        except Exception as e:
            logger.debug(f"Error loading geometry for parcel {parcel_uuid}: {e}")
            continue

    return parcels


def generate_raster_tile(z: int, x: int, y: int, state_code=None, district_code=None) -> bytes:
    """
    Generate a 256x256 PNG raster tile showing parcel borders
    and survey numbers inside the polygons.
    
    Uses 2x supersampling (512x512) for smoother, anti-aliased lines.
    
    Optional filters: state_code, district_code
    """
    # Tile bounding box
    minx, miny, maxx, maxy = tile_xyz_to_bounds(x, y, z)
    tile_parcels = fetch_tile_parcels(minx, miny, maxx, maxy, state_code=state_code, district_code=district_code)
    
    if not tile_parcels:
        print(f"[GENERATING] Tile {z}/{x}/{y} - No parcels found, returning empty tile")
        img = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    
    print(f"[GENERATING] Tile {z}/{x}/{y} - Processing {len(tile_parcels)} parcels")

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
        # Draw text with stroke outline for better visibility and darker appearance
        # stroke_width: 2px at render scale (will be ~1px after resize)
        # stroke_fill: white outline makes black text stand out more
        # draw.text(
        #     (px, py), 
        #     str(p["survey_num"]), 
        #     fill="black", 
        #     font=font,
        #     stroke_width=int(2 * RENDER_SCALE),  # Thicker stroke for darker appearance
        #     stroke_fill="white"  # White outline for contrast
        # )

    img = img.resize((TILE_SIZE, TILE_SIZE), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


