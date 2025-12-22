import geopandas as gpd
import psycopg2
import os
import logging
import sys
from pathlib import Path

# Add backend directory to path to import config
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from config import DB_CONFIG, TABLE_MASTER

logger = logging.getLogger(__name__)


def load_parcels_from_db():
    """Load parcels from database.
    
    Uses parcels_master table (or parcels_master_neon) which is the source of truth after ETL.
    """
    logger.info(f"Loading parcels from database table: {TABLE_MASTER}")
    conn = psycopg2.connect(**DB_CONFIG)
    
    query = f"""
        SELECT 
            parcel_uuid,
            geom,
            survey_num,
            state_code,
            district_code,
            district_name,
            sub_district_name,
            village_name,
            state
        FROM {TABLE_MASTER}
    """
    
    parcels = gpd.read_postgis(query, conn, geom_col='geom', crs='EPSG:4326')
    conn.close()
    
    if 'geometry' not in parcels.columns and 'geom' in parcels.columns:
        parcels = parcels.rename_geometry('geometry')
    
    return parcels


# Spatial index is now OPTIONAL - query_parcel.py uses database-side queries instead
# This prevents loading 400K+ parcels into memory at startup (which causes timeouts)
# The spatial index is kept for backward compatibility but is not used by default

parcels = None
sindex = None

# Only load if explicitly needed (for small datasets)
# For large datasets (>100K parcels), use database-side queries in query_parcel.py
USE_IN_MEMORY_INDEX = os.getenv("USE_IN_MEMORY_SPATIAL_INDEX", "false").lower() == "true"

if USE_IN_MEMORY_INDEX:
    try:
        logger.info("Loading parcels into memory (USE_IN_MEMORY_SPATIAL_INDEX=true)")
        parcels = load_parcels_from_db()
        logger.info(f"Loaded {len(parcels)} parcels from database table: {TABLE_MASTER}")
        
        if len(parcels) == 0:
            logger.warning(f"WARNING: No parcels loaded from {TABLE_MASTER}! Check database configuration.")
        else:
            # Log bounding box to verify data location
            bbox = parcels.total_bounds
            logger.info(f"Data bounding box: [{bbox[1]:.4f}, {bbox[0]:.4f}] to [{bbox[3]:.4f}, {bbox[2]:.4f}]")
        
        sindex = parcels.sindex
        logger.info("Spatial index built successfully")
    except Exception as e:
        logger.error(f"Error loading parcels: {e}")
        import traceback
        traceback.print_exc()
        # Create empty GeoDataFrame to prevent crashes
        import geopandas as gpd
        from shapely.geometry import Point
        parcels = gpd.GeoDataFrame(geometry=[Point(0, 0)])
        sindex = parcels.sindex
else:
    logger.info("Using database-side spatial queries (recommended for large datasets)")
    logger.info(f"To use in-memory index, set USE_IN_MEMORY_SPATIAL_INDEX=true in .env")
