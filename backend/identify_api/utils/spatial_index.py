# backend/identify-api/utils/spatial_index.py

import os
import geopandas as gpd

# Get project root directory (3 levels up from this file: backend/identify_api/utils/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
DEFAULT_SHAPEFILE_PATH = os.path.join(PROJECT_ROOT, "data", "vellore", "vellore_cad.shp")

SHAPEFILE_PATH = os.environ.get("SHAPEFILE_PATH", DEFAULT_SHAPEFILE_PATH)

print("Loading parcels...")

# Load parcels into GeoDataFrame (keep CRS = EPSG:4326 for simplicity)
parcels = gpd.read_file(SHAPEFILE_PATH).to_crs("EPSG:4326")

print(f"Loaded {len(parcels)} parcels")

print("Building spatial index...")
sindex = parcels.sindex
print("Spatial index built")
