# backend/tile-server/utils/generate_tile.py

import io
import numpy as np
import geopandas as gpd
from rasterio import features
from rasterio.transform import from_bounds
from PIL import Image
from shapely.geometry import box
from .tile_utils import tile_xyz_to_bounds

# Path to your shapefile
SHAPEFILE_PATH = "/home/vamsi/parcel_mvp/data/vellore/vellore_cad.shp"

# Load once into memory
parcels = gpd.read_file(SHAPEFILE_PATH).to_crs("EPSG:4326")

def generate_raster_tile(z: int, x: int, y: int) -> bytes:
    """
    Generate a 256x256 PNG raster tile from shapefile for given z/x/y.
    """
    # Step 1: Get bounding box for this tile
    minx, miny, maxx, maxy = tile_xyz_to_bounds(x, y, z)
    tile_bbox = box(minx, miny, maxx, maxy)

    # Step 2: Subset polygons that intersect this tile
    tile_data = parcels[parcels.intersects(tile_bbox)]
    if tile_data.empty:
        # Return a fully transparent PNG
        img = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    # Step 3: Clip the data to the tile bbox
    tile_data = gpd.clip(tile_data, tile_bbox)

    # Step 4: Rasterize polygons to a NumPy array
    transform = from_bounds(minx, miny, maxx, maxy, 256, 256)
    mask = features.rasterize(
        [(geom, 1) for geom in tile_data.geometry],
        out_shape=(256, 256),
        transform=transform,
        fill=0,
        dtype=np.uint8
    )

    # # Step 5: Convert mask to RGBA
    # rgba = np.zeros((256, 256, 4), dtype=np.uint8)
    # rgba[..., 1] = mask * 180  # green fill
    # rgba[..., 3] = mask * 255  # alpha (opacity)

    # # Step 6: Save to PNG
    # img = Image.fromarray(rgba, "RGBA")
    # buf = io.BytesIO()
    # img.save(buf, format="PNG")
    # buf.seek(0)
    # return buf.getvalue()
    print("Tile:", z, x, y)
    for g in tile_data.geometry:
        print("   geom ok:", g.is_valid, "bounds:", g.bounds)


    # Step 4: Rasterize polygons (fill)
    transform = from_bounds(minx, miny, maxx, maxy, 256, 256)
    fill_mask = features.rasterize(
        [(geom, 1) for geom in tile_data.geometry],
        out_shape=(256, 256),
        transform=transform,
        fill=0,
        dtype=np.uint8
    )

    # Step 5: Rasterize edges (borders)
    # We can take the boundaries of polygons and rasterize them separately
    edge_mask = features.rasterize(
        [(geom.boundary, 1) for geom in tile_data.geometry],
        out_shape=(256, 256),
        transform=transform,
        fill=0,
        dtype=np.uint8
    )

    # Step 6: Create RGBA array
    rgba = np.zeros((256, 256, 4), dtype=np.uint8)

    # Green fill for parcels
    rgba[..., 1] = fill_mask * 180  # green channel

    # Black borders where edge_mask = 1
    rgba[..., 0] = np.where(edge_mask == 1, 0, rgba[..., 0])
    rgba[..., 1] = np.where(edge_mask == 1, 0, rgba[..., 1])
    rgba[..., 2] = np.where(edge_mask == 1, 0, rgba[..., 2])
    rgba[..., 3] = np.where((fill_mask + edge_mask) > 0, 255, 0)  # alpha

    # Step 7: Save to PNG
    img = Image.fromarray(rgba, "RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


