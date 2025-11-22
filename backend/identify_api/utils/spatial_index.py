# backend/identify-api/utils/spatial_index.py

import geopandas as gpd

SHAPEFILE_PATH = "/home/vamsi/parcel_mvp/data/vellore/vellore_cad.shp"

print("⚙️ Loading parcels...")

# Load parcels into GeoDataFrame (keep CRS = EPSG:4326 for simplicity)
parcels = gpd.read_file(SHAPEFILE_PATH).to_crs("EPSG:4326")

print(f"Loaded {len(parcels)} parcels")

print("⚙️ Building spatial index...")
sindex = parcels.sindex
print("Spatial index built ✔️")
