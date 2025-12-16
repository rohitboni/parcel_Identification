import geopandas as gpd
import psycopg2
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT")),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}


def load_parcels_from_db():
    """Load parcels from database.
    
    Uses parcels_master table which is the source of truth after ETL.
    """
    logger.info("Loading parcels from database...")
    conn = psycopg2.connect(**DB_CONFIG)
    
    query = """
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
        FROM parcels_master
    """
    
    parcels = gpd.read_postgis(query, conn, geom_col='geom', crs='EPSG:4326')
    conn.close()
    
    if 'geometry' not in parcels.columns and 'geom' in parcels.columns:
        parcels = parcels.rename_geometry('geometry')
    
    return parcels


parcels = load_parcels_from_db()
logger.info(f"Loaded {len(parcels)} parcels from database")

sindex = parcels.sindex
logger.info("Spatial index built")
