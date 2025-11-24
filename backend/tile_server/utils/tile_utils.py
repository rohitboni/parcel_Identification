# backend/tile-server/utils/tile_utils.py
import math

# Web Mercator constants
TILE_SIZE = 256
EARTH_RADIUS = 6378137
INITIAL_RESOLUTION = 2 * math.pi * EARTH_RADIUS / TILE_SIZE
ORIGIN_SHIFT = 2 * math.pi * EARTH_RADIUS / 2.0


def tile_xyz_to_bounds(x: int, y: int, z: int):
    """
    Converts a given XYZ tile coordinate to geographic bounding box (minx, miny, maxx, maxy)
    in EPSG:4326 (lat/lon).
    """
    n = 2.0 ** z
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0

    lat_min = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    lat_max = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))

    return (lon_min, lat_min, lon_max, lat_max)


def latlon_to_tile(lat: float, lon: float, zoom: int):
    """
    Converts latitude/longitude to XYZ tile indices at a given zoom.
    """
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y
